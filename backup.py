"""Consistent SQLite backup while the bot runs. No raw file copy of a live WAL DB."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import sqlite3

parser=argparse.ArgumentParser()
parser.add_argument('--database',default='data/ege.sqlite3')
parser.add_argument('--output',default='backups')
args=parser.parse_args()
os.umask(0o077)
source_path=Path(args.database).resolve()
if not source_path.is_file():
    raise SystemExit('Database does not exist')
folder=Path(args.output)
folder.mkdir(parents=True,exist_ok=True)
target=folder/('ege-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
with sqlite3.connect(source_path.as_uri()+'?mode=ro',uri=True) as source, sqlite3.connect(target) as destination:
    source.backup(destination)
    if destination.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
        raise SystemExit('Backup integrity check failed')
print(target)
