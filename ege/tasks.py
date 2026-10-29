"""Pure, seedable exercise generators. No eval, network or external models."""
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
import random
import re
import secrets

TOPICS = {
    'logic': ('Логика', 'Таблицы истинности · №2'),
    'fano': ('Кодирование', 'Условие Фано · №4'),
    'executor': ('Алгоритмы', 'Двоичные преобразования · №5; программы · №13 проекта 2027'),
    'media': ('Изображения и звук', 'Кодирование информации · №7'),
    'words': ('Слова', 'Комбинаторика и порядок слов · №8'),
    'records': ('Объём данных', 'Идентификаторы и алфавиты · №11'),
}
SKILLS = {
    'not': ('НЕ', 'logic'), 'and': ('И', 'logic'), 'or': ('ИЛИ', 'logic'),
    'imp': ('Следование', 'logic'), 'mixed': ('Выражения', 'logic'),
    'truth': ('Столбцы таблицы · №2', 'logic'),
    'fano': ('Кратчайший код · №4', 'fano'),
    'fano_sum': ('Два неизвестных кода · №4', 'fano'),
    'fano_word': ('Минимум бит в слове · №4', 'fano'),
    'binary': ('Двоичный алгоритм · №5', 'executor'),
    'executor': ('Количество программ', 'executor'),
    'image': ('Изображение', 'media'), 'audio': ('Аудиозапись', 'media'),
    'ratio': ('Изменение звука', 'media'), 'words': ('Подсчёт слов', 'words'),
    'image_palette': ('Максимум цветов · №7', 'media'),
    'audio_time': ('Длительность записи · №7', 'media'),
    'words_rank': ('Номер слова · №8', 'words'),
    'records': ('Идентификаторы', 'records'),
    'records_length': ('Максимальная длина · №11', 'records'),
    'records_alphabet': ('Мощность алфавита · №11', 'records'),
}

WARMUP_SKILLS = frozenset(('not', 'and', 'or', 'imp', 'mixed'))
EXAM_SKILLS = tuple(s for s in SKILLS if s not in WARMUP_SKILLS)


@dataclass
class Step:
    question: str
    answer: str
    explanation: str
    answer_kind: str = 'number'


@dataclass
class Task:
    skill: str
    title: str
    question: str
    answer: str
    steps: list[Step]
    hints: list[str]
    formula: str = ''
    plain_formula: str = ''
    choices: list[str] = field(default_factory=list)
    unit: str = ''
    params: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: secrets.token_hex(5))
    answer_kind: str = 'number'
    formula_role: str = 'hint'
    level: str = 'ЕГЭ · тематическая практика'
    table: list[list[str]] = field(default_factory=list)
    version: int = 2

    def dump(self):
        return asdict(self)

    @classmethod
    def load(cls, data):
        data = dict(data)
        # Retain historical results, but allow App to replace unfinished v1 tasks.
        data.setdefault('version', 1)
        if data['version'] == 1:
            data.setdefault('answer_kind', 'binary' if data['skill'] == 'fano' else 'number')
            data.setdefault('formula_role', 'condition' if data['skill'] in WARMUP_SKILLS else 'hint')
            data.setdefault('level', 'Разминка · предыдущая версия')
        return cls(**{**data, 'steps': [Step(**s) for s in data['steps']]})


def parse_answer(text, binary=False, kind=None):
    text = text.strip()
    kind = kind or ('binary' if binary else 'number')
    if kind == 'letters':
        text = text.lower()
        if len(text) != 4 or set(text) != set('wxyz'):
            raise ValueError('Пришли четыре латинские буквы w, x, y, z без пробелов, каждую ровно один раз.')
        return text
    if kind == 'binary':
        if not re.fullmatch(r'[01]{1,32}', text):
            raise ValueError('Нужна последовательность из 0 и 1. Начальные нули важны.')
        return text
    text = text.replace(' ', '').replace('\u00a0', '').replace(',', '.')
    if len(text) > 32 or not re.fullmatch(r'\d+(?:\.\d+)?', text):
        raise ValueError('Пришли только неотрицательное число, без единиц измерения.')
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError('Не удалось прочитать число.') from exc


def matches(text, answer, binary=False, kind=None):
    return parse_answer(text, binary, kind) == parse_answer(answer, binary, kind)


def compatible(code, codes):
    return all(not code.startswith(c) and not c.startswith(code) for c in codes)


def generate(skill, rng=None):
    r = rng or random.SystemRandom()
    if skill not in SKILLS:
        raise ValueError('Unknown skill')
    if skill not in WARMUP_SKILLS:
        from .exam import generate_exam
        return generate_exam(skill, r)
    if skill in ('not', 'and', 'or', 'imp', 'mixed'):
        x, y, z = (r.randrange(2) for _ in range(3))
        if skill == 'not':
            a = 1-x
            formula, plain = r'\neg x', '¬x'
            q = f'x = {x}. Чему равно НЕ x?'
            steps = [Step(f'НЕ {x} = ?', str(a), f'НЕ меняет значение на противоположное: ¬{x} = {a}.')]
            hints = ['0 — ложь, 1 — истина.', 'НЕ переворачивает значение: 0 становится 1, а 1 — 0.']
        elif skill in ('and', 'or', 'imp'):
            op, tex, rule = {
                'and': ('∧', r'\land', 'И даёт 1, только если оба значения равны 1.'),
                'or': ('∨', r'\lor', 'ИЛИ даёт 1, если хотя бы одно значение равно 1.'),
                'imp': ('→', r'\to', 'Следование даёт 0 только в случае 1 → 0. Во всех остальных случаях — 1.'),
            }[skill]
            a = {'and': x & y, 'or': x | y, 'imp': int(not x or y)}[skill]
            formula, plain = f'x {tex} y', f'x {op} y'
            q = f'x = {x}, y = {y}. Найди значение выражения.'
            steps = [Step(f'{x} {op} {y} = ?', str(a), f'{rule} Здесь {x} {op} {y} = {a}.')]
            hints = [rule, 'Подставь значения вместо букв. Сравни получившуюся пару с правилом.']
        else:
            variant = r.randrange(3)
            q = f'x = {x}, y = {y}, z = {z}. Найди значение выражения.'
            if variant == 0:
                b, c, a = 1-y, x & (1-y), (x & (1-y)) | z
                formula, plain = r'(x \land \neg y) \lor z', '(x ∧ ¬y) ∨ z'
                steps = [Step('Чему равно ¬y?', str(b), f'¬{y} = {b}: меняем значение на противоположное.'), Step(f'Чему равно x ∧ ¬y, то есть {x} ∧ {b}?', str(c), f'{x} ∧ {b} = {c}. И требует две единицы.'), Step(f'Осталось {c} ∨ {z}. Чему это равно?', str(a), f'{c} ∨ {z} = {a}. ИЛИ требует хотя бы одну единицу.')]
            elif variant == 1:
                b, c, a = y & z, 1-x, (1-x) | (y & z)
                formula, plain = r'\neg x \lor (y \land z)', '¬x ∨ (y ∧ z)'
                steps = [Step('Чему равно y ∧ z?', str(b), f'{y} ∧ {z} = {b}: И требует две единицы.'), Step('Чему равно ¬x?', str(c), f'¬{x} = {c}.'), Step(f'Чему равно {c} ∨ {b}?', str(a), f'{c} ∨ {b} = {a}: ИЛИ требует хотя бы одну единицу.')]
            else:
                b, c, a = x | y, 1-z, (x | y) & (1-z)
                formula, plain = r'(x \lor y) \land \neg z', '(x ∨ y) ∧ ¬z'
                steps = [Step('Чему равно x ∨ y?', str(b), f'{x} ∨ {y} = {b}.'), Step('Чему равно ¬z?', str(c), f'¬{z} = {c}.'), Step(f'Чему равно {b} ∧ {c}?', str(a), f'{b} ∧ {c} = {a}: И требует две единицы.')]
            hints = ['Сначала вычисляй выражения в скобках. Внутри: НЕ, затем И, затем ИЛИ.', 'Не меняй значения букв. Записывай результат каждой операции отдельно.']
        return Task(skill, SKILLS[skill][0], q, str(a), steps, hints, formula, plain, ['0','1'], params={'x': x, 'y': y, 'z': z}, formula_role='condition', level='Разминка · основы логики')
