# EGE Informatics Trainer

A Russian-language Telegram tutor with deterministic exercise generators,
step-by-step explanations, hints, review topics and persistent progress.
The curriculum includes Fano coding, truth tables, binary algorithms, program
counting, combinatorics and audio/image storage calculations. No LLM or model API is required.

## Test without Telegram

Python 3.11+ (Linux recommended):

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The tests use a fake Telegram API and temporary/in-memory SQLite databases.

## Run your bot

```sh
cp .env.example .env
# Fill BOT_TOKEN using your own BotFather bot.
python bot.py --whoami
# Send /id, stop the process, and set OWNER_ID to your own numeric ID.
python bot.py
```

Keep `PUBLIC_ACCESS=false` for an owner-only bot. The normal runner requires a
nonzero owner ID and uses a Linux process lock (`fcntl`); use Linux or WSL for running
the service. The pure generators and offline tests can be used independently.
The default public template uses UTC; set your own IANA timezone.

## Architecture

- `ege/exam.py`, `ege/tasks.py`: seedable generators, answers and guided steps.
- `ege/app.py`, `ege/ui.py`: interaction state machine and rendering.
- `ege/db.py`: SQLite progress, unfinished exercises and review state.
- `ege/telegram.py`: Bot API transport; `backup.py`: database backups.

See [the full Russian guide](docs/guide.ru.md). This is a practice tool, not an
official examination service; the generated curriculum covers selected task families.
Optional Telegram rich formatting features depend on the Bot API capabilities available to your bot.

Русский: тренажёр ЕГЭ по информатике с генерацией задач, подсказками и сохранением прогресса.
