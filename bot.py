#!/usr/bin/env python3
"""Run with Python 3.11+. A single process owns the long-polling connection."""
import argparse
import fcntl
import logging
import os
from pathlib import Path
import signal
import time
from ege.app import App
from ege.config import Config, load_env
from ege.db import Database
from ege.telegram import Telegram, TelegramError

log=logging.getLogger('ege')


def whoami():
    load_env()
    token=os.getenv('BOT_TOKEN','')
    if not token or token=='PASTE_BOT_TOKEN':
        raise ValueError('Сначала укажите BOT_TOKEN в .env.')
    api=Telegram(token)
    info=api.call('getMe')
    if api.call('getWebhookInfo').get('url'):
        raise ValueError('У бота включён webhook. Используйте отдельного нового бота; существующий webhook не изменён.')
    print('Откройте @'+info['username']+' и отправьте /id. Здесь появится ваш числовой ID. Ctrl+C — выход.')
    offset=0
    while True:
        for update in api.call('getUpdates',offset=offset,timeout=20,allowed_updates=['message']):
            offset=update['update_id']+1
            msg=update.get('message',{})
            if msg.get('chat',{}).get('type')=='private' and msg.get('text')=='/id':
                uid=msg['from']['id']
                print(f'Telegram ID: {uid}. Сверьте с ответом в своём чате и укажите OWNER_ID в .env.')
                api.call('sendMessage',chat_id=uid,text=f'Твой Telegram ID: {uid}. Укажи его как OWNER_ID в .env.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--whoami',action='store_true',help='Show ID after /id, without assigning an owner')
    args=parser.parse_args()
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    if args.whoami:
        return whoami()
    cfg=Config.read()
    Path(cfg.database).parent.mkdir(parents=True,exist_ok=True)
    lock=open(cfg.database+'.lock','a')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        raise ValueError('Этот бот уже запущен с той же базой данных.') from None
    api=Telegram(cfg.token)
    log.info('Connecting to Telegram; IPv4 preferred')
    me=api.call('getMe')
    if api.call('getWebhookInfo').get('url'):
        raise ValueError('Обнаружен webhook. Остановитесь: используйте отдельного нового бота или отключите webhook самостоятельно.')
    db=Database(cfg.database,cfg.timezone)
    previous_bot=db.meta('bot_id')
    if previous_bot and previous_bot!=str(me['id']):
        raise ValueError('Эта база принадлежит другому боту. Выберите другой DATABASE_PATH.')
    db.set_meta('bot_id',me['id'])
    app=App(cfg,db,api)
    commands=[('menu','Главное меню'),('continue','Продолжить задачу'),('learn','Учиться с нуля'),('practice','Тренировка'),('review','Повторить ошибки'),('stats','Прогресс'),('settings','Настройки'),('help','Помощь'),('privacy','Данные и приватность')]
    api.call('setMyCommands',commands=[{'command':c,'description':d} for c,d in commands])
    running=True
    def stop(*_):
        nonlocal running
        running=False
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    offset=int(db.meta('offset','0'))
    backoff=1
    log.info('Bot started; no message contents or tokens are logged')
    try:
        while running:
            try:
                updates=api.call('getUpdates',offset=offset,timeout=20,allowed_updates=['message','callback_query'])
                for update in updates:
                    try:
                        app.handle(update)
                    except TelegramError as exc:
                        log.warning('Update delivery failed: code=%s; /continue restores the saved exercise',exc.code)
                        if exc.code in (401,409):
                            raise
                    except Exception as exc:
                        log.error('Update failed: %s',type(exc).__name__)
                    # Session/outcome persist before offset; duplicate answers cannot add a second attempt.
                    offset=update['update_id']+1
                    db.set_meta('offset',offset)
                app.reminders()
                backoff=1
            except TelegramError as exc:
                if exc.code in (401,409):
                    log.error('Stopped: token invalid or another polling instance is active (code=%s)',exc.code)
                    raise SystemExit(2)
                log.warning('Connection unavailable: code=%s; retry in %ss',exc.code,backoff)
                time.sleep(backoff)
                backoff=min(30,backoff*2)
    finally:
        db.close()
        lock.close()


if __name__=='__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (ValueError,TelegramError) as error:
        # TelegramError.__str__ deliberately hides raw URLs/response details.
        raise SystemExit(str(error)) from None
