import json
import math
import random
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
from ege.app import App
from ege.config import Config
from ege.db import Database
from ege.tasks import SKILLS, WARMUP_SKILLS, Task, compatible, generate, matches, parse_answer
from ege.telegram import TelegramError
from ege.ui import Card, UI, button


class FakeAPI:
    def __init__(self):
        self.calls=[]
        self.mid=100
        self.reject_rich=False
        self.reject_icons=False
        self.network=False

    def call(self, method, **payload):
        self.calls.append((method,payload))
        if self.network:
            raise TelegramError(0,'Network error')
        if self.reject_rich and (method=='sendRichMessage' or 'rich_message' in payload):
            raise TelegramError(404,'Not Found')
        if self.reject_icons and 'icon_custom_emoji_id' in json.dumps(payload):
            raise TelegramError(400,'custom emoji is not allowed')
        if method.startswith('send'):
            self.mid+=1
        return {'message_id':payload.get('message_id',self.mid)}


class GeneratorTests(unittest.TestCase):
    def test_foundation_answers_against_reference(self):
        r=random.Random(414)
        for skill in WARMUP_SKILLS:
            for _ in range(150):
                t=generate(skill,r)
                p=t.params
                if skill=='fano':
                    self.assertTrue(all(compatible(c,[x for x in p['codes'] if x!=c]) for c in p['codes']))
                    valid=[c for c in t.choices if compatible(c,p['codes'])]
                    self.assertEqual(valid,[t.answer])
                    self.assertEqual(len(set(t.choices)),4)
                elif skill in ('not','and','or','imp','mixed'):
                    x,y,z=p['x'],p['y'],p['z']
                    refs={'not':1-x,'and':x*y,'or':int(x+y>0),'imp':int(x==0 or y==1)}
                    if skill=='mixed':
                        a={'(x ∧ ¬y) ∨ z':int((x==1 and y==0) or z==1),'¬x ∨ (y ∧ z)':int(x==0 or y==z==1),'(x ∨ y) ∧ ¬z':int((x==1 or y==1) and z==0)}[t.plain_formula]
                    else:
                        a=refs[skill]
                    self.assertEqual(t.answer,str(a))
                else:
                    if skill=='executor':
                        a=p['start']
                        for cmd in p['commands']:
                            a=a+p['add'] if cmd==1 else a*p['mul']
                    elif skill=='image':
                        a=p['w']*p['h']*p['bits']/8192
                    elif skill=='audio':
                        a=p['hz']*p['depth']*p['channels']*p['seconds']/8192
                    elif skill=='ratio':
                        a=p['rf']*p['df']*p['cf']
                    elif skill=='words':
                        a=p['n']**p['length']
                    else:
                        a=(math.ceil(p['chars']*math.ceil(math.log2(p['n']))/8)+p['extra'])*p['count']/1024
                    self.assertEqual(float(t.answer),a)
                self.assertEqual(t.steps[-1].answer,t.answer)
                self.assertEqual(Task.load(t.dump()),t)

    def test_input(self):
        self.assertTrue(matches(' 1 024,00 ','1024'))
        self.assertFalse(matches('01','1',binary=True))
        for invalid in ('NaN','inf','1e3','1/2','2 Кбайт','-1','', '9'*40):
            with self.assertRaises(ValueError):
                parse_answer(invalid)


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.db=Database(':memory:')
        self.api=FakeAPI()
        self.app=App(Config('test',42),self.db,self.api)
        self.db.user(42)

    def tearDown(self):
        self.db.close()

    def message(self,text,uid=42):
        return self.app.handle({'message':{'from':{'id':uid},'chat':{'id':uid,'type':'private'},'text':text}})

    def callback(self,action,revision=None):
        u=self.db.user(42)
        return self.app.handle({'callback_query':{'id':'test','from':{'id':42},'message':{'message_id':u['card_id'],'chat':{'id':42,'type':'private'}},'data':f'{revision if revision is not None else u["revision"]}:{action}'}})

    def test_six_topics_and_three_media_variants(self):
        for skill in SKILLS:
            self.app.new(42,skill)
            s=self.db.session(42)
            self.app.answer(42,s['task']['answer'])
            self.assertTrue(self.db.session(42)['done'])
        self.assertEqual(self.db.stats(42)['correct'],len(SKILLS))

    def test_independent_duplicate_stale_buttons(self):
        self.app.new(42,'words')
        s=self.db.session(42)
        rev=self.db.user(42)['revision']
        self.message(s['task']['answer'])
        self.app.answer(42,s['task']['answer'])
        self.callback('new:audio',rev)
        self.assertEqual(self.db.stats(42)['attempts'],1)
        self.assertEqual(self.db.stats(42)['independent'],1)
        self.assertEqual(self.db.session(42)['task']['id'],s['task']['id'])

    def test_hints_do_not_count_as_independent(self):
        self.app.new(42,'audio')
        s=self.db.session(42)
        self.callback('hint:'+s['task']['id'])
        self.message(s['task']['answer'])
        self.assertEqual(self.db.stats(42)['assisted'],1)
        self.assertEqual(self.db.stats(42)['streak'],0)

    def test_guided_errors_and_steps(self):
        self.app.new(42,'mixed',guided=True)
        s=self.db.session(42)
        self.app.answer(42,str(1-int(s['task']['steps'][0]['answer'])))
        self.assertEqual(self.db.session(42)['step'],0)
        for step in s['task']['steps']:
            self.app.answer(42,step['answer'])
        self.assertEqual(self.db.stats(42)['correct'],1)
        self.assertEqual(self.db.stats(42)['independent'],0)
        self.assertEqual(self.db.reviews(42)[0]['skill'],'mixed')

    def test_review_requires_two_independent_successes(self):
        self.app.new(42,'words')
        self.app.answer(42,'999999')
        self.assertEqual(len(self.db.reviews(42)),1)
        for i in range(2):
            self.app.new(42,'words',review=True)
            self.app.answer(42,self.db.session(42)['task']['answer'])
            self.assertEqual(len(self.db.reviews(42)),1 if i==0 else 0)

    def test_reveal_and_reset_confirmation(self):
        self.app.new(42,'image')
        self.callback('reveal:'+self.db.session(42)['task']['id'])
        self.assertEqual(self.db.stats(42)['correct'],0)
        self.assertEqual(self.db.stats(42)['attempts'],1)
        self.callback('confirm:today')
        self.assertEqual(self.db.stats(42)['attempts'],1)
        self.callback('reset:today')
        self.assertEqual(self.db.stats(42)['attempts'],0)
        self.assertFalse(self.db.session(42))
        self.assertEqual(len(self.db.reviews(42)),1)

    def test_private_access_and_groups(self):
        self.message('/start',uid=7)
        self.assertIsNone(self.db.conn.execute('SELECT * FROM users WHERE uid=7').fetchone())
        self.app.handle({'message':{'from':{'id':42},'chat':{'id':-10,'type':'group'},'text':'/start'}})
        self.assertEqual(len(self.api.calls),1)

    def test_theory_does_not_consume_answer(self):
        self.app.new(42,'mixed')
        self.callback('lesson:mixed:0')
        self.message('1')
        self.assertEqual(self.db.stats(42)['attempts'],0)
        self.assertTrue(self.db.session(42)['assisted'])

    def test_bad_input_and_empty_review(self):
        self.app.review(42)
        self.app.new(42,'audio')
        self.message('abc')
        self.assertFalse(self.db.session(42)['done'])
        self.assertEqual(self.db.stats(42)['attempts'],0)

    def test_settings_and_opt_in_reminder(self):
        self.assertFalse(self.db.user(42)['reminder'])
        self.message('/remind 25:00')
        self.assertFalse(self.db.user(42)['reminder'])
        self.message('/remind 20:00')
        self.assertTrue(self.db.user(42)['reminder'])
        now=datetime(2026,9,21,20,0,10,tzinfo=ZoneInfo('Asia/Barnaul'))
        with patch.object(self.db,'now',return_value=now):
            self.app.reminders()
            self.app.reminders()
        sent=[p for m,p in self.api.calls if m=='sendMessage' and p.get('text','').startswith('Время небольшой')]
        self.assertEqual(len(sent),1)
        self.message('/remind off')
        self.assertFalse(self.db.user(42)['reminder'])

    def test_emoji_from_reply_owner_only(self):
        self.app.handle({'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'/emoji learn','reply_to_message':{'entities':[{'type':'custom_emoji','custom_emoji_id':'12345'}]}}})
        self.assertEqual(self.db.meta('emoji:learn'),'12345')
        keyboard=self.api.calls[-1][1]['reply_markup']
        self.assertIn('12345',json.dumps(keyboard))

    def test_rich_and_plain_payloads(self):
        self.app.new(42,'image')
        method,payload=self.api.calls[-1]
        self.assertEqual(method,'sendRichMessage')
        math_blocks=[b for b in payload['rich_message']['blocks'] if b['type']=='mathematical_expression']
        self.assertFalse(math_blocks)
        self.app.new(42,'truth')
        payload=self.api.calls[-1][1]
        math_blocks=[b for b in payload['rich_message']['blocks'] if b['type']=='mathematical_expression']
        self.assertEqual(len(math_blocks),2)
        self.app.action(42,'render:plain')
        self.assertIn('parse_mode',self.api.calls[-1][1])

    def test_rich_fallback_and_no_retry_on_network(self):
        self.api.reject_rich=True
        self.app.home(42)
        self.assertEqual(self.api.calls[-1][0],'sendMessage')
        self.assertEqual(self.db.user(42)['rendering'],'plain')
        self.api.network=True
        before=len(self.api.calls)
        with self.assertRaises(TelegramError):
            self.app.home(42)
        self.assertEqual(len(self.api.calls),before+1)

    def test_emoji_fallback(self):
        self.db.set_meta('emoji:learn','1234')
        self.api.reject_icons=True
        self.app.home(42)
        self.assertNotIn('icon_custom_emoji_id',json.dumps(self.api.calls[-1]))

    def test_no_answer_leak_in_task(self):
        self.app.new(42,'words')
        payload=self.api.calls[-1][1]
        content=json.dumps(payload,ensure_ascii=False)
        self.assertNotIn('Ответ:',content)
        self.assertNotIn('explanation',content)

    def test_html_escaping(self):
        self.assertNotIn('<script>',Card('<script>',['a & b']).html())
        self.assertIn('&amp;',Card('x',['a & b']).html())

    def test_unknown_action_is_noop(self):
        self.app.action(42,'new:invalid')
        self.assertFalse(self.db.session(42))

    def test_user_isolation(self):
        self.app.config.public=True
        self.message('/start',uid=7)
        self.app.new(42,'audio')
        self.app.new(7,'words')
        self.app.answer(7,self.db.session(7)['task']['answer'])
        self.assertEqual(self.db.stats(7)['correct'],1)
        self.assertEqual(self.db.stats(42)['correct'],0)
        self.assertFalse(self.db.session(42)['done'])


class PersistenceTests(unittest.TestCase):
    def test_session_and_stats_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'db.sqlite3')
            db=Database(path)
            api=FakeAPI()
            app=App(Config('x',42),db,api)
            db.user(42)
            app.new(42,'mixed',guided=True)
            s=db.session(42)
            app.answer(42,s['task']['steps'][0]['answer'])
            db.close()
            db=Database(path)
            self.assertEqual(db.session(42)['step'],1)
            app=App(Config('x',42),db,api)
            for step in s['task']['steps'][1:]:
                app.answer(42,step['answer'])
            self.assertEqual(db.stats(42)['correct'],1)
            db.close()


if __name__=='__main__':
    unittest.main()
