import json
from pathlib import Path
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo


class Database:
    def __init__(self, path, timezone='Asia/Barnaul'):
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        PRAGMA busy_timeout=5000;
        CREATE TABLE IF NOT EXISTS users(
            uid INTEGER PRIMARY KEY, session TEXT NOT NULL DEFAULT '{}',
            rendering TEXT NOT NULL DEFAULT 'rich', reminder INTEGER NOT NULL DEFAULT 0,
            reminder_time TEXT NOT NULL DEFAULT '20:00', last_reminder TEXT NOT NULL DEFAULT '',
            card_id INTEGER, revision INTEGER NOT NULL DEFAULT 0,
            daily_goal INTEGER NOT NULL DEFAULT 10);
        CREATE TABLE IF NOT EXISTS attempts(
            uid INTEGER NOT NULL REFERENCES users(uid), task_id TEXT NOT NULL,
            day TEXT NOT NULL, skill TEXT NOT NULL, correct INTEGER NOT NULL,
            independent INTEGER NOT NULL, outcome TEXT NOT NULL,
            created TEXT NOT NULL, PRIMARY KEY(uid, task_id));
        CREATE INDEX IF NOT EXISTS attempts_user_day ON attempts(uid, day);
        CREATE TABLE IF NOT EXISTS review(
            uid INTEGER NOT NULL REFERENCES users(uid), skill TEXT NOT NULL,
            successes INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(uid, skill));
        CREATE TABLE IF NOT EXISTS lessons(
            uid INTEGER NOT NULL REFERENCES users(uid), skill TEXT NOT NULL,
            page INTEGER NOT NULL DEFAULT 0, completed INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(uid, skill));
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        PRAGMA user_version=1;
        ''')
        self.tz = ZoneInfo(timezone)

    def now(self):
        return datetime.now(self.tz)

    def day(self):
        return self.now().date().isoformat()

    def user(self, uid):
        with self.conn:
            self.conn.execute('INSERT OR IGNORE INTO users(uid) VALUES (?)', (uid,))
        return dict(self.conn.execute('SELECT * FROM users WHERE uid=?', (uid,)).fetchone())

    def set_user(self, uid, **fields):
        allowed = {'session','rendering','reminder','reminder_time','last_reminder','card_id','revision','daily_goal'}
        if not fields or not fields.keys() <= allowed:
            raise ValueError('Invalid user fields')
        with self.conn:
            self.conn.execute('UPDATE users SET '+','.join(k+'=?' for k in fields)+' WHERE uid=?', (*fields.values(),uid))

    def session(self, uid):
        return json.loads(self.user(uid)['session'])

    def store(self, uid, session):
        self.set_user(uid, session=json.dumps(session, ensure_ascii=False))

    def meta(self, key, default=None):
        row = self.conn.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key, value):
        with self.conn:
            self.conn.execute('INSERT INTO meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key,str(value)))

    def finish(self, uid, task, session, correct, outcome):
        independent = correct and not session.get('assisted')
        with self.conn:
            inserted = self.conn.execute('INSERT OR IGNORE INTO attempts VALUES (?,?,?,?,?,?,?,?)',
                (uid,task.id,self.day(),task.skill,int(correct),int(independent),outcome,self.now().isoformat())).rowcount
            if not inserted:
                return False
            if not correct or session.get('errors',0):
                self.conn.execute('INSERT INTO review(uid,skill) VALUES (?,?) ON CONFLICT(uid,skill) DO UPDATE SET successes=0', (uid,task.skill))
            elif independent:
                self.conn.execute('UPDATE review SET successes=successes+1 WHERE uid=? AND skill=?', (uid,task.skill))
                self.conn.execute('DELETE FROM review WHERE uid=? AND skill=? AND successes>=2', (uid,task.skill))
            session.update(done=True, correct=bool(correct), outcome=outcome)
            self.conn.execute('UPDATE users SET session=? WHERE uid=?', (json.dumps(session,ensure_ascii=False),uid))
        return True

    def stats(self, uid, day=None):
        where = 'uid=?' + (' AND day=?' if day else '')
        args = (uid,day) if day else (uid,)
        rows = list(self.conn.execute('SELECT * FROM attempts WHERE '+where+' ORDER BY created, rowid', args))
        correct = sum(r['correct'] for r in rows)
        independent = sum(r['independent'] for r in rows)
        streak = 0
        for r in reversed(rows):
            if not r['independent']:
                break
            streak += 1
        return {'attempts':len(rows),'correct':correct,'independent':independent,'assisted':correct-independent,'streak':streak,
                'accuracy':round(100*correct/len(rows)) if rows else None}

    def skill_stats(self, uid):
        return [dict(r) for r in self.conn.execute('SELECT skill,count(*) AS attempts,sum(independent) AS independent FROM attempts WHERE uid=? GROUP BY skill', (uid,))]

    def reviews(self, uid):
        return [dict(r) for r in self.conn.execute('SELECT skill,successes FROM review WHERE uid=? ORDER BY successes,skill', (uid,))]

    def lesson(self, uid, skill, page, completed=False):
        with self.conn:
            self.conn.execute('INSERT INTO lessons VALUES (?,?,?,?) ON CONFLICT(uid,skill) DO UPDATE SET page=excluded.page,completed=MAX(lessons.completed,excluded.completed)', (uid,skill,page,int(completed)))

    def reset_today(self, uid):
        with self.conn:
            self.conn.execute('DELETE FROM attempts WHERE uid=? AND day=?', (uid,self.day()))
            # A previously answered task must not become countable twice after reset.
            self.conn.execute("UPDATE users SET session='{}' WHERE uid=?", (uid,))

    def delete_progress(self, uid):
        with self.conn:
            for table in ('attempts','review','lessons'):
                self.conn.execute(f'DELETE FROM {table} WHERE uid=?', (uid,))
            self.conn.execute("UPDATE users SET session='{}',reminder=0 WHERE uid=?", (uid,))

    def close(self):
        self.conn.close()
