from dataclasses import dataclass
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo


def load_env(path='.env'):
    """Minimal dotenv reader; values are data, never shell commands."""
    if not Path(path).exists():
        return
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'[A-Z_][A-Z_0-9]*', key):
            raise ValueError('Неверная строка .env: ожидается ИМЯ=значение')
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))


@dataclass
class Config:
    token: str
    owner: int
    database: str = 'data/ege.sqlite3'
    timezone: str = 'Asia/Barnaul'
    public: bool = False

    @classmethod
    def read(cls):
        load_env()
        token = os.getenv('BOT_TOKEN', '')
        if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}', token):
            raise ValueError('Укажите BOT_TOKEN в .env (не публикуйте токен).')
        owner = int(os.getenv('OWNER_ID', '0'))
        if owner <= 0:
            raise ValueError('Укажите числовой OWNER_ID. Его можно узнать командой python3 bot.py --whoami.')
        tz = os.getenv('TIMEZONE', 'Asia/Barnaul')
        ZoneInfo(tz)
        return cls(token, owner, os.getenv('DATABASE_PATH', 'data/ege.sqlite3'), tz, os.getenv('PUBLIC_ACCESS','false').lower()=='true')
