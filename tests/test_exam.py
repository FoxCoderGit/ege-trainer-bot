"""Independent brute-force oracles, boundary cases and UI regression coverage."""
import json
import math
import random
import socket
import unittest
from fractions import Fraction
from functools import lru_cache
from itertools import permutations, product
from unittest.mock import Mock, patch

from ege.exam import best_pair, free_roots
from ege.tasks import EXAM_SKILLS, SKILLS, WARMUP_SKILLS, Task, generate, matches, parse_answer
from ege.lessons import LESSONS
from ege.telegram import ipv4_preferred_connection
import test_bot as base


def valid_code(candidate, known):
    return all(candidate[:len(code)] != code and code[:len(candidate)] != candidate for code in known)


def binary_candidates(maximum=5):
    return [''.join(bits) for length in range(1, maximum+1) for bits in product('01', repeat=length)]


def independent_logic(expr, values):
    if isinstance(expr, str):
        return bool(values[expr])
    op, first, *rest = expr
    a = independent_logic(first, values)
    if op == 'not':
        return not a
    b = independent_logic(rest[0], values)
    if op == 'and':
        return a and b
    if op == 'or':
        return a or b
    if op == 'eq':
        return a == b
    if op == 'imp':
        return not (a and not b)
    raise AssertionError(op)


def independent_truth(task):
    rows = task.params['rows']
    holes = [(i,j) for i,row in enumerate(rows) for j in range(4) if row[j] is None]
    possible = set()
    for values in product((0,1), repeat=len(holes)):
        filled = [row[:4] for row in rows]
        for (i,j),value in zip(holes,values):
            filled[i][j] = value
        if len(set(map(tuple,filled))) != len(rows):
            continue
        for order in permutations('wxyz'):
            if all(independent_logic(task.params['node'], dict(zip(order,bits))) == row[4]
                   for bits,row in zip(filled,rows)):
                possible.add(''.join(order))
    return possible


def reference(task):
    p, skill = task.params, task.skill
    if skill.startswith('fano'):
        codes = list(p['known'].values())
        pool = [c for c in binary_candidates() if valid_code(c,codes)]
        if skill == 'fano':
            return min(pool, key=lambda c:(len(c),int(c,2)))
        weights = [p['word'].count(a) for a in p['unknown']] if skill == 'fano_word' else [1,1]
        costs = [weights[0]*len(a)+weights[1]*len(b) for a,b in permutations(pool,2) if valid_code(a,[b])]
        fixed = sum(p['word'].count(a)*len(c) for a,c in p['known'].items())
        return min(costs)+fixed
    if skill == 'truth':
        return independent_truth(task)
    if skill == 'binary':
        outputs=[]
        for n in range(1,p['threshold']+2):
            value = int(format(n,'b')+p['tails'][n%2],2)
            if value > p['threshold']:
                outputs.append((n,value))
        return min(n for n,v in outputs) if p['variant']=='input' else min(v for n,v in outputs)
    if skill == 'executor':
        @lru_cache(None)
        def walk(n,seen):
            if n > p['end'] or n == p['forbidden']:
                return 0
            seen = seen or n == p['required']
            if n == p['end']:
                return int(seen)
            return walk(n+p['add'],seen)+walk(n*p['mul'],seen)
        return walk(p['start'],False)
    if skill == 'image':
        bits = next(i for i in range(1,32) if 2**i >= p['colors'])
        raw = math.ceil(Fraction(p['w']*p['h']*bits,8))
        packed = math.ceil(Fraction(raw*p['retained'],100))
        return math.ceil(Fraction((packed+p['header'])*p['count'],1024))
    if skill == 'image_palette':
        valid = [i for i in range(1,32) if math.ceil(Fraction(p['w']*p['h']*i,8))+p['header'] <= p['limit']*1024]
        return 2**max(valid)
    if skill == 'audio':
        return math.ceil(Fraction(p['hz']*p['depth']*p['channels']*p['duration'],8192))
    if skill == 'audio_time':
        per_second=Fraction(p['hz']*p['depth']*p['channels'],8)
        answer=0
        while (answer+1)*per_second+p['header'] <= p['limit']*2**20:
            answer+=1
        return answer
    if skill == 'ratio':
        old_size = p['old_time']*p['old_speed']*10**6
        duration = Fraction(old_size,p['old_rate']*p['old_depth']*p['old_channels'])
        new_size = duration*p['new_rate']*p['new_depth']*p['new_channels']
        return new_size/(p['new_speed']*10**6)
    if skill == 'words':
        answer=0
        for word in product(p['alphabet'], repeat=p['length']):
            if word.count(p['special']) != p['k']:
                continue
            if p['variant']=='first' and word[0]==p['special']:
                continue
            if p['variant']=='adjacent' and any(a==b==p['special'] for a,b in zip(word,word[1:])):
                continue
            answer+=1
        return answer
    if skill == 'words_rank':
        for index,word in enumerate(product(p['alphabet'],repeat=p['length']),1):
            if word[0] not in p['banned'] and word.count(p['special'])>=p['minimum'] and index%2==p['parity']:
                return index
        raise AssertionError('No valid word')
    bits = next(i for i in range(1,32) if 2**i >= p['alphabet'])
    if skill == 'records':
        return math.ceil(Fraction((math.ceil(Fraction(p['length']*bits,8))+p['extra'])*p['count'],1024))
    if skill == 'records_length':
        valid = [length for length in range(1,1000)
                 if (math.ceil(Fraction(length*bits,8))+p['extra'])*p['count'] <= p['limit']*1024]
        return max(valid)
    if skill == 'records_alphabet':
        valid = [b for b in range(1,32)
                 if (math.ceil(Fraction(p['length']*b,8))+p['extra'])*p['count'] <= p['limit']*1024]
        return 2**max(valid)
    raise AssertionError(skill)


class ExamGenerationTests(unittest.TestCase):
    def test_1600_exam_variants_against_independent_oracles(self):
        for skill in EXAM_SKILLS:
            for seed in range(100):
                with self.subTest(skill=skill,seed=seed):
                    task=generate(skill,random.Random(seed))
                    expected=reference(task)
                    if skill=='truth':
                        self.assertEqual(expected,{task.answer})
                    elif skill=='fano':
                        self.assertEqual(expected,task.answer)
                    else:
                        self.assertEqual(Fraction(task.answer),expected)
                    self.assertEqual(task.steps[-1].answer,task.answer)
                    self.assertFalse(task.choices)
                    self.assertEqual(task.formula_role,'condition' if skill=='truth' else 'hint')
                    loaded=Task.load(json.loads(json.dumps(task.dump())))
                    self.assertEqual(loaded.answer,task.answer)
                    for item in task.steps:
                        self.assertTrue(matches(item.answer,item.answer,kind=item.answer_kind))

    def test_each_exam_family_has_variety(self):
        for skill in EXAM_SKILLS:
            signatures=set()
            for seed in range(40):
                task=generate(skill,random.Random(seed))
                signatures.add((task.question,task.plain_formula,str(task.table)))
            self.assertGreater(len(signatures),30,skill)

    def test_all_lessons_exist(self):
        self.assertEqual(set(SKILLS),set(LESSONS))
        self.assertEqual(len(EXAM_SKILLS),16)

    def test_fano_pair_single_free_branch(self):
        self.assertEqual(free_roots(['0']),['1'])
        self.assertEqual(best_pair(['0']),('10','11'))
        self.assertEqual(best_pair(['00'],(5,1)),('1','01'))
        for codes in (['00','01','10'],['00','10'],['0'],['000','011','10']):
            pool=[c for c in binary_candidates() if valid_code(c,codes)]
            for weights in ((1,1),(1,9),(9,1),(3,4)):
                pair=best_pair(codes,weights)
                expected=min(weights[0]*len(a)+weights[1]*len(b) for a,b in permutations(pool,2) if valid_code(a,[b]))
                self.assertEqual(sum(w*len(c) for w,c in zip(weights,pair)),expected)

    def test_answer_types(self):
        self.assertTrue(matches(' WXYZ ','wxyz',kind='letters'))
        self.assertFalse(matches('001','1',kind='binary'))
        for value in ('wwxy','w x y z','хуzw','abcd','wxy'):
            with self.assertRaises(ValueError):
                parse_answer(value,kind='letters')
        for value in ('0b11','2','', '1'*33):
            with self.assertRaises(ValueError):
                parse_answer(value,kind='binary')


class ExamFlowTests(unittest.TestCase):
    setUp = base.FlowTests.setUp
    tearDown = base.FlowTests.tearDown
    message = base.FlowTests.message
    callback = base.FlowTests.callback

    def payload(self):
        return json.dumps(self.api.calls[-1][1],ensure_ascii=False)

    def test_no_formula_leak_in_both_render_modes(self):
        for rendering in ('rich','plain'):
            self.db.set_user(42,rendering=rendering)
            for skill in EXAM_SKILLS:
                self.app.new(42,skill)
                task=Task.load(self.db.session(42)['task'])
                payload=self.api.calls[-1][1]
                if skill!='truth':
                    if rendering=='rich':
                        self.assertFalse(any(b['type']=='mathematical_expression' for b in payload['rich_message']['blocks']))
                    elif task.plain_formula:
                        self.assertNotIn(task.plain_formula,payload['text'])
                else:
                    self.assertIn('w',self.payload())
                    if rendering=='plain':
                        self.assertIn('<pre>',payload['text'])

    def test_formula_only_after_second_hint(self):
        self.app.new(42,'audio')
        s=self.db.session(42)
        self.callback('hint:'+s['task']['id'])
        self.assertNotIn('mathematical_expression',self.payload())
        self.callback('hint:'+s['task']['id'])
        self.assertIn('mathematical_expression',self.payload())
        self.assertTrue(self.db.session(42)['assisted'])
        self.assertNotIn('Подсказка 3/',self.payload())

    def test_every_exam_guided_flow_accepts_typed_steps(self):
        for skill in EXAM_SKILLS:
            self.app.new(42,skill,guided=True)
            task=Task.load(self.db.session(42)['task'])
            for item in task.steps:
                self.message(item.answer)
            self.assertTrue(self.db.session(42)['done'],skill)
            self.assertTrue(self.db.session(42)['correct'],skill)
        self.assertEqual(self.db.stats(42)['independent'],0)

    def test_mixed_mode_does_not_include_warmups(self):
        for _ in range(80):
            self.app.new(42,'all')
            self.assertNotIn(self.db.session(42)['task']['skill'],WARMUP_SKILLS)

    def test_old_unfinished_session_replaced_without_scoring(self):
        self.app.new(42,'fano')
        s=self.db.session(42)
        old_id=s['task']['id']
        for key in ('version','answer_kind','formula_role','level','table'):
            s['task'].pop(key)
        self.db.store(42,s)
        self.app.answer(42,s['task']['answer'])
        self.assertNotEqual(self.db.session(42)['task']['id'],old_id)
        self.assertEqual(self.db.stats(42)['attempts'],0)

    def test_letters_invalid_format_not_scored(self):
        self.app.new(42,'truth')
        self.message('1')
        self.assertFalse(self.db.session(42)['done'])
        self.assertEqual(self.db.stats(42)['attempts'],0)

    def test_card_sizes_remain_small(self):
        for skill in SKILLS:
            self.db.set_user(42,rendering='plain')
            self.app.new(42,skill,guided=True)
            s=self.db.session(42)
            for item in s['task']['steps']:
                self.assertLess(len(self.api.calls[-1][1].get('text','')),4000)
                self.app.answer(42,item['answer'])
            self.assertLess(len(self.api.calls[-1][1].get('text','')),4000)


class NetworkTests(unittest.TestCase):
    def test_ipv4_first_and_ipv6_fallback(self):
        ipv6=(socket.AF_INET6,socket.SOCK_STREAM,6,'',('::1',443,0,0))
        ipv4=(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))
        first, second = Mock(), Mock()
        with patch('socket.getaddrinfo',return_value=[ipv6,ipv4]), patch('socket.socket',side_effect=[first,second]) as ctor:
            self.assertIs(ipv4_preferred_connection(('example.com',443),3),first)
            self.assertEqual(ctor.call_args.args[0],socket.AF_INET)
        first.connect.side_effect=OSError('IPv4 unavailable')
        with patch('socket.getaddrinfo',return_value=[ipv6,ipv4]), patch('socket.socket',side_effect=[first,second]):
            self.assertIs(ipv4_preferred_connection(('example.com',443),3),second)
            first.close.assert_called_once()


if __name__=='__main__':
    unittest.main()
