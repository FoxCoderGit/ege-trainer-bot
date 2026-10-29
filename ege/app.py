"""Private-chat tutor. Deterministic callbacks, persisted sessions, explicit consent."""
from datetime import timedelta
import json
import logging
import random
import re
from .lessons import LESSONS
from .tasks import SKILLS, TOPICS, EXAM_SKILLS, WARMUP_SKILLS, Task, generate, matches, parse_answer
from .telegram import TelegramError
from .ui import Card, UI, button

log = logging.getLogger(__name__)
BACK = [[button('В меню','home')]]


class App:
    def __init__(self, config, db, api):
        self.config, self.db, self.api = config, db, api
        self.ui = UI(api, db)

    def show(self, uid, card, rows=None, fresh=False, screen='menu'):
        self.db.set_meta(f'screen:{uid}',screen)
        self.ui.show(uid,card,rows if rows is not None else BACK,fresh)

    def icon(self, key):
        return self.db.meta('emoji:'+key)

    def home(self, uid, fresh=False):
        u=self.db.user(uid)
        stats=self.db.stats(uid,self.db.day())
        goal=u['daily_goal']
        left=max(0,goal-stats['correct'])
        done='Цель выполнена.' if not left else f'До цели осталось: {left}.'
        card=Card('Практика ЕГЭ',[
            'ЕГЭ · информатика\nПонимание начинается с одного шага.',
            f'Сегодня: {stats["correct"]} / {goal} верных ответов. {done}\nСамостоятельно: {stats["independent"]} · с помощью: {stats["assisted"]}',
        ],footer='Без таймера. Без ИИ. Задачи и ответы рассчитываются программой.')
        rows=[]
        if self.db.session(uid).get('task'):
            rows.append([button('Продолжить','resume','primary')])
        if not stats['attempts'] and not self.db.stats(uid)['attempts']:
            card.paragraphs.append('Если логика пока непонятна, начни с «Учиться с нуля → Логика → НЕ».')
        rows += [
            [button('Учиться с нуля','learn','primary',self.icon('learn'))],
            [button('Задания ЕГЭ','practice',icon=self.icon('practice'))],
            [button('Повторить ошибки','review',icon=self.icon('review')),button('Прогресс','stats',icon=self.icon('stats'))],
            [button('Настройки','settings'),button('О боте','about')],
        ]
        self.show(uid,card,rows,fresh)

    def choose_topic(self, uid, learning=False):
        prefix='ltopic' if learning else 'topic'
        rows=[[button(name,f'{prefix}:{key}')] for key,(name,_) in TOPICS.items()]
        if not learning:
            rows.insert(0,[button('Смешанная тренировка','new:all','primary')])
        rows+=BACK
        self.show(uid,Card('Учиться с нуля' if learning else 'Выбери тему',[
            'Короткое правило → пример → практика.' if learning else 'Экзаменационные типы задач. Ответ вводится сообщением; подсказки открываются по запросу.'
        ],footer='Тематический тренажёр, не полный вариант. Основы логики — в «Учиться с нуля».'),rows)

    def topic(self, uid, key, learning=False):
        if key not in TOPICS:
            return
        rows=[]
        for skill,(name,topic) in SKILLS.items():
            if topic==key:
                if not learning and skill in WARMUP_SKILLS:
                    continue
                action=f'lesson:{skill}:0' if learning else f'new:{skill}'
                lesson=self.db.conn.execute('SELECT completed,page FROM lessons WHERE uid=? AND skill=?',(uid,skill)).fetchone()
                if learning and lesson:
                    action=f'lesson:{skill}:{lesson["page"]}'
                    name+= ' · прочитано' if lesson['completed'] else ' · продолжить'
                rows.append([button(name,action)])
        rows.append([button('Все темы','learn' if learning else 'practice')])
        if key == 'logic' and not learning:
            rows.insert(-1, [button('Разобраться в знаках с нуля', 'ltopic:logic')])
        self.show(uid,Card(TOPICS[key][0],[TOPICS[key][1],
            ('Начни с НЕ, затем И, ИЛИ и следования.' if learning else 'Определи переменные по фрагменту таблицы истинности. Ответ — порядок четырёх букв.') if key=='logic' else 'Можно сначала прочитать правило, а затем решить похожий пример.'
        ]),rows)

    def lesson(self, uid, skill, page=0):
        if skill not in LESSONS:
            return
        pages=LESSONS[skill]
        page=max(0,min(page,len(pages)-1))
        self.db.lesson(uid,skill,page,page==len(pages)-1)
        title,text=pages[page]
        rows=[]
        nav=[]
        if page:
            nav.append(button('Назад',f'lesson:{skill}:{page-1}'))
        if page<len(pages)-1:
            nav.append(button('Дальше',f'lesson:{skill}:{page+1}','primary'))
        if nav:
            rows.append(nav)
        if self.db.session(uid).get('task'):
            rows.append([button('Вернуться к задаче','resume')])
        rows.append([button('Попробовать по шагам',f'guided:{skill}','primary')])
        rows.append([button('Решить самостоятельно',f'new:{skill}')])
        rows.append([button('Выбрать урок','learn'),button('В меню','home')])
        self.show(uid,Card(title,[text],footer=f'{SKILLS[skill][0]} · карточка {page+1} из {len(pages)}'),rows)

    def new(self, uid, scope, guided=False, review=False):
        if scope=='all':
            topic=random.choice(list(TOPICS))
            choices=[s for s in EXAM_SKILLS if SKILLS[s][1]==topic]
            skill=random.choice(choices)
        elif scope in SKILLS:
            skill=scope
        else:
            return
        previous=self.db.session(uid).get('task',{})
        task=generate(skill)
        for _ in range(8):
            if task.question!=previous.get('question') or task.plain_formula!=previous.get('plain_formula'):
                break
            task=generate(skill)
        session={'task':task.dump(),'scope':scope,'guided':guided,'review':review,'step':0,
                 'hints':0,'assisted':guided,'errors':0,'done':False,'notice':''}
        self.db.store(uid,session)
        self.task_card(uid)

    def task_card(self, uid, fresh=False):
        s=self.db.session(uid)
        if not s.get('task'):
            return self.home(uid,fresh)
        t=Task.load(s['task'])
        if s.get('done'):
            return self.result(uid,fresh)
        if t.version < 2:
            # v1 exercises may be ambiguous and leak formulas; do not score them.
            return self.new(uid, s.get('scope', t.skill), s.get('guided', False), s.get('review', False))
        paragraphs=[t.question]
        if s['guided']:
            step=t.steps[s['step']]
            paragraphs.append(f'Шаг {s["step"]+1} из {len(t.steps)}\n{step.question}')
        if s.get('notice'):
            paragraphs.append(s['notice'])
        for i in range(s['hints']):
            paragraphs.append(f'Подсказка {i+1}\n{t.hints[i]}')
        token=t.id
        rows=[]
        kind=t.steps[s['step']].answer_kind if s['guided'] else t.answer_kind
        show_choices=bool(t.choices) and not s['guided']
        if show_choices:
            rows += [[button(value,f'answer:{token}:{idx}') for idx,value in list(enumerate(t.choices))[start:start+2]] for start in range(0,len(t.choices),2)]
        else:
            instructions={'binary':'Пришли двоичный код сообщением. Начальные нули важны.',
                          'letters':'Пришли порядок латинских букв w, x, y, z без пробелов.'}
            paragraphs.append(instructions.get(kind, 'Пришли ответ одним числом'+(f', без «{t.unit}».' if t.unit and not s['guided'] else '.')))
        help_row=[]
        if s['hints'] < len(t.hints):
            help_row.append(button(f'Подсказка {s["hints"]+1}/{len(t.hints)}',f'hint:{token}'))
        help_row.append(button('Показать решение',f'reveal:{token}'))
        rows.append(help_row)
        if not s['guided'] and len(t.steps)>1:
            rows.append([button('Решаем по шагам',f'steps:{token}','primary')])
        rows.append([button('Теория',f'lesson:{t.skill}:0'),button('В меню','home')])
        mode='С помощью' if s['assisted'] else 'Самостоятельно'
        visible=t.formula_role=='condition' or s['hints']>=len(t.hints) or s['guided']
        self.show(uid,Card(t.title,paragraphs,t.formula if visible else '',t.plain_formula if visible else '',
                         mode+' · '+t.level+(' · повторение ошибок' if s['review'] else ''),table=t.table),rows,fresh,screen='task')

    def answer(self, uid, raw, task_id=None):
        s=self.db.session(uid)
        if not s.get('task') or s.get('done'):
            return
        t=Task.load(s['task'])
        if t.version < 2:
            return self.task_card(uid, fresh=True)
        if task_id and t.id!=task_id:
            return
        answer=t.steps[s['step']].answer if s['guided'] else t.answer
        try:
            kind=t.steps[s['step']].answer_kind if s['guided'] else t.answer_kind
            ok=matches(raw,answer,kind=kind)
        except ValueError as exc:
            s['notice']=str(exc)
            self.db.store(uid,s)
            return self.task_card(uid,fresh=True)
        if s['guided']:
            if not ok:
                s['errors']+=1
                s['notice']='Пока не сходится. '+t.steps[s['step']].explanation+'\nТеперь введи результат этого шага.'
                self.db.store(uid,s)
                return self.task_card(uid,fresh=True)
            s['notice']='Верно. '+t.steps[s['step']].explanation
            s['step']+=1
            if s['step']<len(t.steps):
                self.db.store(uid,s)
                return self.task_card(uid,fresh=True)
        self.db.finish(uid,t,s,ok,'guided' if s['guided'] else ('correct' if ok else 'wrong'))
        self.result(uid,fresh=s['guided'] or not bool(t.choices))

    def result(self, uid, fresh=False):
        s=self.db.session(uid)
        t=Task.load(s['task'])
        title=('Верно · ' if s.get('correct') else 'Разбор · ')+t.title
        note='Решено с помощью — отдельно от самостоятельных ответов.' if s.get('assisted') and s.get('correct') else ('Самостоятельное решение засчитано.' if s.get('correct') else 'Эта тема добавлена в повторение.')
        paragraphs=[f'Ответ: {t.answer}'+(f' {t.unit}' if t.unit else ''), '\n'.join(f'{i+1}. {step.explanation}' for i,step in enumerate(t.steps)),note]
        stats=self.db.stats(uid,self.db.day())
        footer=f'Сегодня верно: {stats["correct"]} · серия без помощи: {stats["streak"]}'
        rows=[[button('Следующая задача',f'next:{t.id}','primary')],
              [button('Похожая задача',f'new:{t.skill}'),button('Теория',f'lesson:{t.skill}:0')],
              [button('Прогресс','stats'),button('В меню','home')]]
        route=['not','and','or','imp','mixed']
        if t.skill in route[:-1] and s.get('correct'):
            next_skill=route[route.index(t.skill)+1]
            rows.insert(2,[button('Следующий урок: '+SKILLS[next_skill][0],f'lesson:{next_skill}:0')])
        self.show(uid,Card(title,paragraphs,t.formula,t.plain_formula,footer),rows,fresh,screen='result')

    def review(self, uid):
        reviews=self.db.reviews(uid)
        if not reviews:
            return self.show(uid,Card('Повторение ошибок',['Пока нет тем для повторения. Они появятся после ошибки или просмотра решения.']),[[button('К тренировке','practice','primary')]]+BACK)
        lines=[f'{SKILLS[r["skill"]][0]} · {r["successes"]} / 2' for r in reviews]
        rows=[[button(SKILLS[r['skill']][0],f'reviewnew:{r["skill"]}')] for r in reviews]+BACK
        self.show(uid,Card('Повторить ошибки',['\n'.join(lines),'Два верных самостоятельных решения подряд по теме убирают её из этого списка. Задачи будут с новыми данными.']),rows)

    def stats(self, uid):
        today=self.db.stats(uid,self.db.day())
        total=self.db.stats(uid)
        accuracy='—' if today['accuracy'] is None else str(today['accuracy'])+'%'
        lines=[f'{SKILLS[r["skill"]][0]}: {r["independent"]} самостоятельно / {r["attempts"]} завершено' for r in self.db.skill_stats(uid)]
        paragraphs=[f'Сегодня\nВерно: {today["correct"]} из {today["attempts"]}\nСамостоятельно: {today["independent"]}\nС помощью: {today["assisted"]}\nТочность: {accuracy}\nСерия без помощи: {today["streak"]}',
                    f'За всё время\nЗавершено: {total["attempts"]} · верно: {total["correct"]}',
                    '\n'.join(lines) if lines else 'Начни с одной задачи — здесь появится статистика.']
        self.show(uid,Card('Твой прогресс',paragraphs,footer='Просмотр ответа считается незачтённой попыткой. Это учебная статистика, не прогноз баллов ЕГЭ.'),[[button('Повторить ошибки','review'),button('В меню','home')]])

    def settings(self, uid):
        u=self.db.user(uid)
        rich=u['rendering']=='rich'
        reminder='включены' if u['reminder'] else 'выключены'
        self.show(uid,Card('Настройки',[
            f'Формулы: {"LaTeX" if rich else "обычный текст"}\nЦель: {u["daily_goal"]} верных ответов\nНапоминания: {reminder}\nВремя: {u["reminder_time"]} · {self.config.timezone}',
            'Если формулы отображаются неправильно, включи обычный текст. Время напоминания меняется командой /remind 20:00.',
            'Напоминание в этом боте не отключает отдельное напоминание ChatGPT.'
        ]),[[button('Обычный текст' if rich else 'Включить LaTeX','render:plain' if rich else 'render:rich')],
             [button('Выключить напоминания' if u['reminder'] else 'Включить напоминания','remind:0' if u['reminder'] else 'remind:1')],
             [button('Цель 5','goal:5'),button('Цель 10','goal:10'),button('Цель 20','goal:20')],
             [button('Сбросить день','confirm:today'),button('Удалить прогресс','confirm:all','danger')]]+BACK)

    def confirm(self, uid, scope):
        if scope not in ('today','all'):
            return
        text='Сбросить сегодняшние результаты и текущую задачу? Уроки и список ошибок останутся.' if scope=='today' else 'Удалить всю историю решений, уроков и ошибок, очистить текущую задачу и выключить напоминания?'
        self.show(uid,Card('Подтверждение',[text]),[[button('Да, удалить',f'reset:{scope}','danger'),button('Отмена','settings')]])

    def about(self, uid):
        self.show(uid,Card('Учиться в своём темпе',[
            'Все задания генерируются кодом. ИИ и платные API не используются. Варианты могут повторяться: набор параметров конечный.',
            'В тренировке — экзаменационные типы задач по логике, кодированию, алгоритмам, звуку, изображениям, словам и памяти. Простые операции логики выделены в обучение с нуля. Это не полный вариант и не все подтипы ЕГЭ.',
            'Нумерация сверена с проектом демоверсии ФИПИ 2027 на 20.09.2026. Проект может измениться. Задачи авторские, не официальный банк ФИПИ.',
            'Команды: /menu, /continue, /learn, /practice, /review, /stats, /settings, /help.\n/privacy — какие данные хранятся.',
            'Числовой ответ вводи сообщением. Теория и подсказки помечают текущую задачу как решаемую с помощью.'
        ]))

    def emoji(self, uid, text, message):
        if uid!=self.config.owner:
            return
        parts=text.split()
        keys=('learn','practice','review','stats')
        if len(parts)!=2 or parts[1] not in keys:
            return self.show(uid,Card('Оформление',[
                'Пришли одно премиум-эмодзи. Ответь на него командой /emoji learn.\nДругие роли: practice, review, stats.\n/emoji_clear — убрать выбранные значки.',
                'Выбирай значки из одного набора. Владелец бота в BotFather должен иметь Premium; OWNER_ID сам по себе не передаёт владение.'
            ]),fresh=True)
        reply=message.get('reply_to_message',{})
        ids=[e.get('custom_emoji_id') for e in reply.get('entities',[])+reply.get('caption_entities',[]) if e.get('type')=='custom_emoji']
        if not ids:
            return self.show(uid,Card('Нужен премиум-эмодзи',['Ответь командой на сообщение с одним custom emoji. Обычный символ или стикер не подходят.']),fresh=True)
        self.db.set_meta('emoji:'+parts[1],ids[0])
        self.home(uid,fresh=True)

    def handle(self, update):
        cb=update.get('callback_query')
        message=cb.get('message',{}) if cb else update.get('message',{})
        sender=cb.get('from',{}) if cb else message.get('from',{})
        uid=sender.get('id')
        chat=message.get('chat',{})
        if not uid or chat.get('type')!='private' or chat.get('id')!=uid:
            if cb:
                self.api.call('answerCallbackQuery',callback_query_id=cb['id'],text='Открой личный чат с ботом.')
            return
        if not self.config.public and uid!=self.config.owner:
            if cb:
                self.api.call('answerCallbackQuery',callback_query_id=cb['id'],text='Это личный тренажёр.')
            else:
                self.api.call('sendMessage',chat_id=uid,text='Этот тренажёр доступен только владельцу.')
            return
        u=self.db.user(uid)
        if cb:
            data=cb.get('data','')
            rev,sep,action=data.partition(':')
            valid=sep and rev.isdigit() and int(rev)==u['revision'] and message.get('message_id')==u['card_id']
            self.api.call('answerCallbackQuery',callback_query_id=cb['id'],text='' if valid else 'Это старая карточка. Открой /menu.')
            if not valid:
                return
            return self.action(uid,action)
        text=message.get('text','').strip()
        if text.startswith('/'):
            cmd=text.split()[0].split('@')[0].lower()
            actions={'/start':'home','/menu':'home','/continue':'resume','/learn':'learn','/practice':'practice','/review':'review','/stats':'stats','/settings':'settings','/help':'about'}
            if cmd in actions:
                # A command places navigation below the user's message.
                self.db.set_user(uid,card_id=None)
                return self.action(uid,actions[cmd])
            if cmd=='/privacy':
                return self.show(uid,Card('Твои данные',[
                    'На сервере хранятся Telegram ID, текущая задача, результаты, прогресс уроков и настройки. Полная переписка, телефон и имя не сохраняются. Другим сервисам обучения данные не отправляются.',
                    'Удалить учебные данные можно в «Настройки → Удалить прогресс». ID и настройки интерфейса останутся для работы бота. Резервные копии сервера управляются его владельцем.'
                ]),fresh=True)
            if cmd=='/remind':
                value=text.partition(' ')[2].strip()
                if value=='off':
                    self.db.set_user(uid,reminder=0)
                elif re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',value):
                    self.db.set_user(uid,reminder=1,reminder_time=value)
                else:
                    return self.show(uid,Card('Время напоминания',['Пример: /remind 20:00\nВыключить: /remind off\nЧасовой пояс: '+self.config.timezone]),fresh=True)
                return self.settings(uid)
            if cmd=='/emoji':
                return self.emoji(uid,text,message)
            if cmd=='/emoji_clear' and uid==self.config.owner:
                for key in ('learn','practice','review','stats'):
                    self.db.set_meta('emoji:'+key,'')
                return self.home(uid,fresh=True)
            return self.show(uid,Card('Команда не найдена',['Открой /menu или /help.']),fresh=True)
        s=self.db.session(uid)
        if text and s.get('task') and not s.get('done') and self.db.meta(f'screen:{uid}')=='task':
            reply=message.get('reply_to_message')
            if reply and reply.get('message_id')!=u['card_id']:
                return self.show(uid,Card('Ответ на старую карточку',['Текущую задачу можно открыть кнопкой ниже.']),[[button('Продолжить','resume','primary')]],fresh=True)
            return self.answer(uid,text)
        self.show(uid,Card('Продолжим?',['Выбери урок или тренировку в меню. Чтобы вернуться к незавершённой задаче, нажми «Продолжить».']),[[button('Продолжить','resume','primary'),button('В меню','home')]],fresh=True)

    def action(self, uid, data):
        p=data.split(':')
        name=p[0]
        simple={'home':self.home,'resume':self.task_card,'learn':lambda u:self.choose_topic(u,True),
                'practice':self.choose_topic,'review':self.review,'stats':self.stats,'settings':self.settings,'about':self.about}
        if name in simple:
            return simple[name](uid)
        if name in ('topic','ltopic') and len(p)==2:
            return self.topic(uid,p[1],name=='ltopic')
        if name=='lesson' and len(p)==3 and p[2].isdigit():
            s=self.db.session(uid)
            if s.get('task') and not s.get('done') and s['task']['skill']==p[1]:
                s['assisted']=True
                self.db.store(uid,s)
            return self.lesson(uid,p[1],int(p[2]))
        if name in ('new','guided','reviewnew') and len(p)==2:
            return self.new(uid,p[1],name=='guided',name=='reviewnew')
        if name=='render' and len(p)==2 and p[1] in ('plain','rich'):
            self.db.set_user(uid,rendering=p[1],card_id=None)
            return self.settings(uid)
        if name=='remind' and len(p)==2 and p[1] in ('0','1'):
            self.db.set_user(uid,reminder=int(p[1]))
            return self.settings(uid)
        if name=='goal' and len(p)==2 and p[1] in ('5','10','20'):
            self.db.set_user(uid,daily_goal=int(p[1]))
            return self.settings(uid)
        if name=='confirm' and len(p)==2:
            return self.confirm(uid,p[1])
        if name=='reset' and len(p)==2:
            if p[1]=='today':
                self.db.reset_today(uid)
            elif p[1]=='all':
                self.db.delete_progress(uid)
            return self.home(uid)
        s=self.db.session(uid)
        if not s.get('task') or len(p)<2 or s['task']['id']!=p[1]:
            return
        t=Task.load(s['task'])
        if name=='next' and s.get('done'):
            return self.new(uid,s['scope'],s['guided'],s['review'])
        if s.get('done'):
            return self.result(uid)
        if name=='answer' and len(p)==3 and p[2].isdigit() and int(p[2])<len(t.choices):
            return self.answer(uid,t.choices[int(p[2])],t.id)
        if name=='hint':
            s['hints']=min(len(t.hints),s['hints']+1)
            s['assisted']=True
            self.db.store(uid,s)
            return self.task_card(uid)
        if name=='steps':
            s.update(guided=True,assisted=True,step=0,notice='Разберём по одному действию.')
            self.db.store(uid,s)
            return self.task_card(uid)
        if name=='reveal':
            s['assisted']=True
            self.db.finish(uid,t,s,False,'revealed')
            return self.result(uid)

    def reminders(self):
        now=self.db.now()
        for row in self.db.conn.execute('SELECT * FROM users WHERE reminder=1').fetchall():
            if not self.config.public and row['uid']!=self.config.owner:
                continue
            if row['last_reminder']==now.date().isoformat():
                continue
            h,m=map(int,row['reminder_time'].split(':'))
            due=now.replace(hour=h,minute=m,second=0,microsecond=0)
            if not due<=now<due+timedelta(hours=1):
                continue
            # At-most-once reservation: an ambiguous delivery is not resent.
            self.db.set_user(row['uid'],last_reminder=now.date().isoformat())
            try:
                self.api.call('sendMessage',chat_id=row['uid'],text='Время небольшой тренировки. Открой /menu — начни с одной задачи.')
            except TelegramError as exc:
                if exc.code==403:
                    self.db.set_user(row['uid'],reminder=0)
                log.warning('Reminder delivery failed: code=%s',exc.code)
