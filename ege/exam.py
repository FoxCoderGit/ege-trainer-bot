"""Original exam-style task families. Exact integer arithmetic, no AI or eval.

Numbering follows the published draft for 2027 (checked 2026-09-20).
These are authored analogues, not copies or a complete FIPI question bank.
"""
from fractions import Fraction
from itertools import permutations, product
from math import comb

from .tasks import Task, Step, compatible


def ceildiv(a, b):
    return (a + b - 1) // b


def noun(n, one, few, many):
    if 11 <= n % 100 <= 14:
        return many
    return one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many


def step(question, answer, explanation, kind='number'):
    return Step(question, str(answer), explanation, kind)


def free_roots(codes):
    """Minimal free subtrees of a binary prefix-code tree."""
    def visit(prefix):
        if any(prefix.startswith(c) for c in codes):
            return []
        if not any(c.startswith(prefix) for c in codes):
            return [prefix]
        return visit(prefix + '0') + visit(prefix + '1')
    return visit('')


def best_pair(codes, weights=(1, 1)):
    """Two new leaves: different free subtrees, or sibling leaves in one.

    Descending farther can only increase a positive weighted length.
    Therefore this finite candidate set includes a global optimum.
    """
    roots = free_roots(codes)
    candidates = list(permutations(roots, 2))
    candidates += [(p+'0', p+'1') for p in roots]
    return min(candidates, key=lambda pair: (
        sum(w * len(c) for w, c in zip(weights, pair)), pair))


def fano_task(skill, r):
    leaves = ['0', '1']
    for _ in range(r.randint(4, 7)):
        candidates = [c for c in leaves if len(c) < 4]
        p = r.choice(candidates)
        leaves.remove(p)
        leaves.extend((p+'0', p+'1'))
    omitted = set(r.sample(leaves, r.randint(2, 3)))
    codes = sorted(set(leaves) - omitted)
    letters = list('АБВГДЕЖЗИК')
    known = dict(zip(letters, codes))
    unknown_count = 1 if skill == 'fano' else 2
    unknown = letters[len(codes):len(codes)+unknown_count]
    alphabet = list(known) + unknown
    heading = ('Для передачи сообщений, содержащих только буквы ' + ', '.join(alphabet) +
               ', используется двоичный код, удовлетворяющий условию Фано.\n'
               'Известны кодовые слова: ' + '; '.join(f'{a} — {c}' for a, c in known.items()) + '.\n')
    note = '\nУсловие Фано: ни одно кодовое слово не является началом другого.'
    roots = sorted(free_roots(codes), key=lambda c: (len(c), c))
    hints = ['Строй двоичное дерево. Известный код закрывает свою вершину и всех её потомков.',
             'Нельзя брать ни продолжение известного кода, ни его начало. Ищи свободные ветви от корня.']
    params = {'known': known, 'codes': codes, 'unknown': unknown}
    roots_text = ', '.join(roots)
    if skill == 'fano':
        answer = roots[0]
        question = (heading + f'Найдите кратчайшее кодовое слово для буквы {unknown[0]}. '
                    'Если таких слов несколько, укажите наименьшее по двоичному числовому значению. '
                    'Начальные нули сохраняйте.' + note)
        steps = [step('Какова минимальная длина свободного кода?', len(answer),
                      f'Корни свободных ветвей: {roots_text}. Кратчайшая длина — {len(answer)}.'),
                 step('Запишите наименьший из кратчайших свободных кодов.', answer,
                      f'Сначала минимизируем длину, затем значение: {answer}.', 'binary')]
        return Task(skill, 'Кратчайший код · №4', question, answer, steps, hints,
                    params=params, answer_kind='binary')
    weights = (1, 1)
    word = ''
    if skill == 'fano_word':
        chars = [a for a in known for _ in range(r.randint(0, 2))]
        chars += [unknown[0]] * r.randint(2, 5) + [unknown[1]] * r.randint(1, 4)
        r.shuffle(chars)
        word = ''.join(chars)
        weights = tuple(word.count(a) for a in unknown)
    pair = best_pair(codes, weights)
    cost = sum(w * len(c) for w, c in zip(weights, pair))
    fixed = sum(word.count(a) * len(c) for a, c in known.items())
    params.update(word=word, weights=weights, example_pair=pair)
    explanation = (f'Свободные ветви: {roots_text}. Два кода можно разместить в разных ветвях '
                   'либо разделить одну свободную ветвь на двух потомков. '
                   f'Оптимальный пример: {unknown[0]} — {pair[0]}, {unknown[1]} — {pair[1]}.')
    if skill == 'fano_sum':
        question = heading + f'Для букв {" и ".join(unknown)} коды не заданы. Найдите минимальную сумму длин этих двух кодовых слов.' + note
        steps = [step('Какова длина самого короткого свободного кода до добавления двух новых букв?', len(roots[0]),
                      f'Корни свободных ветвей: {roots_text}. Минимальная длина — {len(roots[0])}. '
                      'Этот код не обязательно можно занять целиком: нужно оставить место второй букве.'),
                 step('Какова минимальная сумма длин двух кодов?', cost,
                      explanation + f' {len(pair[0])} + {len(pair[1])} = {cost} бит. Неизвестные коды проверяются также друг с другом.')]
        answer = cost
    else:
        question = heading + f'Коды букв {" и ".join(unknown)} неизвестны. Какое минимальное количество бит требуется для кодирования слова {word}?' + note
        steps = [step('Сколько бит занимают все вхождения букв с известными кодами?', fixed,
                      ' + '.join(f'{word.count(a)} × {len(c)}' for a, c in known.items()) + f' = {fixed}.'),
                 step('Каков минимальный вклад двух неизвестных букв в длину сообщения?', cost,
                      explanation + f' Вклад: {weights[0]} × {len(pair[0])} + {weights[1]} × {len(pair[1])} = {cost}.'),
                 step('Какова минимальная длина всего сообщения?', fixed+cost,
                      f'Известные и неизвестные буквы: {fixed} + {cost} = {fixed+cost} бит.')]
        hints[1] = 'Учитывай частоту каждой буквы в слове. Более частой букве выгоден более короткий код; два новых кода должны быть совместимы.'
        answer = fixed + cost
    return Task(skill, 'Длина сообщения · №4' if word else 'Два кодовых слова · №4', question,
                str(answer), steps, hints, unit='бит', params=params)


def logic_value(node, values):
    if isinstance(node, str):
        return values[node]
    op = node[0]
    a = logic_value(node[1], values)
    if op == 'not':
        return 1-a
    b = logic_value(node[2], values)
    return {'and': a & b, 'or': a | b, 'imp': int(not a or b), 'eq': int(a == b)}[op]


def logic_text(node, latex=False):
    if isinstance(node, str):
        return node
    if node[0] == 'not':
        if not isinstance(node[1], str) and node[1][0] == 'not':
            return logic_text(node[1][1], latex)
        return ('\\neg ' if latex else '¬') + logic_text(node[1], latex)
    signs = {'and': ('∧', r'\land'), 'or': ('∨', r'\lor'),
             'imp': ('→', r'\to'), 'eq': ('≡', r'\equiv')}
    return f'({logic_text(node[1], latex)} {signs[node[0]][latex]} {logic_text(node[2], latex)})'


def truth_solutions(node, rows):
    """Enumerate column mappings, respecting distinct (possibly incomplete) rows."""
    solutions = []
    for order in permutations('wxyz'):
        possibilities = []
        for row in rows:
            matches = []
            for bits in product((0, 1), repeat=4):
                if all(v is None or v == b for v, b in zip(row[:4], bits)):
                    if logic_value(node, dict(zip(order, bits))) == row[4]:
                        matches.append(bits)
            possibilities.append(matches)
        possibilities.sort(key=len)
        def assign(i, used):
            if i == len(possibilities):
                return True
            return any(assign(i+1, used | {bits}) for bits in possibilities[i] if bits not in used)
        if assign(0, set()):
            solutions.append(''.join(order))
    return solutions


def truth_task(r):
    # This asymmetric function has three zero rows identifying all four variables.
    # Renaming, selected literal negations and output inversion give variants.
    names = r.sample(list('wxyz'), 4)
    first_negation = r.randrange(2)
    negations = [first_negation, first_negation, r.randrange(2), r.randrange(2)]
    a, b, c, d = [('not', n) if neg else n for n, neg in zip(names, negations)]
    node = ('or', ('imp', ('eq', a, ('not', b)), ('not', ('imp', d, a))), ('not', c))
    target = 0
    if r.randrange(2):
        node, target = ('not', node), 1
    order = r.sample(list('wxyz'), 4)
    rows = [list(bits)+[target] for bits in product((0, 1), repeat=4)
            if logic_value(node, dict(zip(order, bits))) == target]
    r.shuffle(rows)
    if truth_solutions(node, rows) != [''.join(order)]:
        raise AssertionError('Truth function is not identifiable')
    # Remove cells only while retaining a unique column mapping.
    cells = [(i, j) for i in range(len(rows)) for j in range(4)]
    r.shuffle(cells)
    removed = 0
    for i, j in cells:
        old, rows[i][j] = rows[i][j], None
        if truth_solutions(node, rows) == [''.join(order)]:
            removed += 1
            if removed == 3:
                break
        else:
            rows[i][j] = old
    answer = ''.join(order)
    # Enumerate target-valued rows for the worked explanation.
    solution_rows = [bits for bits in product((0, 1), repeat=4)
                     if logic_value(node, dict(zip('wxyz', bits))) == target]
    table = [['A', 'B', 'C', 'D', 'F']] + [['—' if v is None else str(v) for v in row] for row in rows]
    explanation = ('В порядке w, x, y, z нужное значение F дают наборы: ' +
                   '; '.join(''.join(map(str, bits)) for bits in solution_rows) + '. '
                   'Сопоставляем их с известными ячейками; строки должны быть различными. '
                   'Единственное соответствие: ' + ', '.join(f'{col} → {var}' for col, var in zip('ABCD', order)) + '.')
    return Task('truth', 'Таблица истинности · №2',
                'Функция F задана выражением ниже. Приведён фрагмент из различных строк её таблицы истинности. '
                'Столбцы A, B, C, D соответствуют переменным w, x, y, z в неизвестном порядке. '
                'Прочерк (или ?) означает незаполненную ячейку. Определите порядок переменных в столбцах A, B, C, D. '
                'В ответе запишите четыре латинские буквы подряд.', answer,
                [step(f'Сколько наборов w, x, y, z дают F = {target}?', len(solution_rows),
                      f'Перебор 16 наборов даёт {len(solution_rows)} подходящих строк: ' +
                      '; '.join(''.join(map(str, b)) for b in solution_rows) + '.'),
                 step('Запишите порядок переменных в столбцах A, B, C, D.', answer, explanation, 'letters')],
                ['Сначала найди наборы переменных, при которых F принимает указанное в таблице значение.',
                 'Проверяй соответствие сразу по всем строкам. Пустая ячейка может быть 0 или 1, но строки нельзя повторять.'],
                logic_text(node, True), logic_text(node), params={'node': node, 'rows': rows},
                answer_kind='letters', formula_role='condition', table=table)


def binary_result(n, tails):
    return int(bin(n)[2:] + tails[n % 2], 2)


def binary_task(r):
    tails = r.sample(['00', '01', '10', '11', '001', '101'], 2)
    threshold = r.randint(90, 700)
    variant = r.choice(['input', 'output'])
    # R >= N for these append-only algorithms, so values above this bound
    # cannot beat the first admissible result already found.
    first = next(n for n in range(1, threshold+2) if binary_result(n, tails) > threshold)
    candidates = [(binary_result(n, tails), n) for n in range(1, binary_result(first, tails)+1)]
    best_r, best_n = min((v, n) for v, n in candidates if v > threshold)
    answer = first if variant == 'input' else best_r
    witness = first if variant == 'input' else best_n
    result = binary_result(witness, tails)
    question = (f'На вход алгоритма поступает натуральное число N. Строится его двоичная запись. '
                f'Если N чётное, справа дописывается {tails[0]}, иначе справа дописывается {tails[1]}. '
                'Полученная запись является двоичной записью числа R.\n' +
                (f'Найдите наименьшее N, для которого R > {threshold}.' if variant == 'input' else
                 f'Найдите наименьшее возможное R, большее {threshold}.') + ' Ответ запишите в десятичной системе.')
    rules = '; '.join(f'{"чётное" if parity == 0 else "нечётное"} N: R = {2**len(t)}N + {int(t, 2)}' for parity, t in enumerate(tails))
    return Task('binary', 'Двоичный алгоритм · №5', question, str(answer),
                [step('Чему равен десятичный множитель N при дописывании суффикса для чётного N?', 2**len(tails[0]),
                      f'Дописать {len(tails[0])} разряда — умножить на 2^{len(tails[0])} = {2**len(tails[0])}.'),
                 step('Теперь найдите требуемый минимум, проверив обе ветви алгоритма.', answer,
                      f'{rules}. Для каждой ветви решаем строгое неравенство и учитываем чётность N. '
                      f'Оптимальный N = {witness}: {bin(witness)[2:]} → {bin(result)[2:]} = {result}. Ответ: {answer}.')],
                ['Дописать k бит справа — умножить число на 2^k и прибавить значение суффикса.',
                 'Рассмотри чётные и нечётные N отдельно. Проверь, что спрашивают: минимум N или минимум R.'],
                params={'tails': tails, 'threshold': threshold, 'variant': variant})


def path_count(start, end, add, mul, forbidden=None):
    ways = {start: 1 if start != forbidden else 0}
    for value in range(start+1, end+1):
        ways[value] = 0 if value == forbidden else (ways.get(value-add, 0) +
                      (ways.get(value//mul, 0) if value % mul == 0 else 0))
    return ways.get(end, 0)


def executor_task(r):
    start, end = r.randint(1, 5), r.randint(28, 60)
    add, mul = 1, r.choice([2, 3])
    required = r.randint(start+4, end-7)
    forbidden = r.choice([n for n in range(start+1, end) if n != required])
    a = path_count(start, required, add, mul, forbidden)
    b = path_count(required, end, add, mul, forbidden)
    question = (f'Исполнитель преобразует число на экране. Команды: 1 — прибавить {add}; 2 — умножить на {mul}. '
                f'Сколько существует программ, преобразующих {start} в {end}, если траектория обязательно содержит '
                f'{required} и не содержит {forbidden}? Траектория — все числа, полученные при выполнении команд. '
                'Разные последовательности команд считаются разными программами.')
    formula = r'P(a,c)=P(a,b)\cdot P(b,c)'
    return Task('executor', 'Количество программ · №13 (проект 2027)', question, str(a*b),
                [step(f'Сколько путей из {start} в {required} без числа {forbidden}?', a,
                      f'Пусть P({start}) = 1. Для других n складываем P(n−1) и P(n/{mul}), если n делится на {mul}. '
                      f'За границами участка и в запрещённой точке путей 0. Получаем {a}.'),
                 step(f'Сколько путей из {required} в {end} без числа {forbidden}?', b,
                      f'Считаем заново от P({required}) = 1 по тому же правилу. Получаем {b}.'),
                 step('Сколько программ проходит через обязательную точку?', a*b,
                      f'Команды только увеличивают число, поэтому через {required} проходят один раз. {a} × {b} = {a*b}.')],
                ['Раздели траекторию по обязательной точке. Запрет действует на обоих участках.',
                 'В каждой точке суммируй числа путей из возможных предшественников. Число путей через обязательную точку — произведение.'],
                formula, 'P(a → c через b) = P(a → b) × P(b → c)',
                params={'start': start, 'end': end, 'required': required, 'forbidden': forbidden, 'add': add, 'mul': mul})


def image_task(skill, r):
    w, h = r.choice([320, 640, 800, 1024, 1280]), r.choice([240, 480, 600, 720, 960])
    pixels = w*h
    if skill == 'image_palette':
        bits = r.randint(3, 12)
        header = r.choice([128, 256, 512, 1024])
        low = ceildiv(ceildiv(pixels*bits, 8)+header, 1024)
        high = (ceildiv(pixels*(bits+1), 8)+header-1)//1024
        limit = r.randint(low, high)
        available = limit*1024-header
        capacity = available*8//pixels
        answer = 2**capacity
        return Task(skill, 'Максимум цветов · №7',
                    f'Для хранения растрового изображения {w} × {h} пикселей отведено не более {limit} Кбайт, '
                    f'включая заголовок размером {header} байт. Каждый пиксель кодируется одинаковым целым числом бит; '
                    'сжатия нет. Какое максимальное число цветов может содержать палитра? 1 Кбайт = 1024 байта.', str(answer),
                    [step('Сколько байт остаётся для пикселей?', available, f'{limit} × 1024 − {header} = {available}.'),
                     step('Какое максимальное целое число бит можно выделить на пиксель?', capacity,
                          f'⌊{available} × 8 / {pixels}⌋ = {capacity}. Округляем вниз, чтобы уложиться в лимит.'),
                     step('Какова максимальная мощность палитры?', answer, f'2^{capacity} = {answer} цветов.')],
                    ['Сначала вычти заголовок из общего лимита в байтах.', 'Максимум бит на пиксель округляется вниз. Число цветов равно 2 в этой степени.'],
                    params={'w': w, 'h': h, 'header': header, 'limit': limit})
    colors = r.choice([17, 33, 100, 128, 200, 257, 1000, 4096])
    bits = (colors-1).bit_length()
    count, header, retained = r.randint(3, 12), r.choice([512, 1024, 2048]), r.choice([60, 75, 80, 100])
    raw = ceildiv(pixels*bits, 8)
    packed = ceildiv(raw*retained, 100)
    total = count*(packed+header)
    answer = ceildiv(total, 1024)
    return Task(skill, 'Хранение изображений · №7',
                f'Нужно сохранить {count} {noun(count, "изображение", "изображения", "изображений")} размером {w} × {h} пикселей. '
                f'Мощность палитры: {colors}. '
                'Пиксель кодируется минимальным одинаковым целым числом бит. '
                f'После сжатия данные пикселей каждого изображения занимают {retained}% исходного объёма '
                f'(результат округляется вверх до целого байта). К каждому файлу добавляется несжимаемый заголовок {header} байт. '
                'Какое минимальное целое число Кбайт потребуется для всех файлов вместе? '
                'Дополнительного округления размера отдельного файла до Кбайт нет. 1 Кбайт = 1024 байта.', str(answer),
                [step('Сколько бит нужно на один пиксель?', bits, f'2^{bits-1} < {colors} ≤ 2^{bits}; нужно {bits} бит.'),
                 step('Каков объём несжатых пикселей одного изображения в байтах?', raw, f'⌈{w} × {h} × {bits} / 8⌉ = {raw}.'),
                 step('Сколько байт занимает один файл после сжатия с заголовком?', packed+header,
                      f'⌈{raw} × {retained} / 100⌉ + {header} = {packed+header}.'),
                 step('Сколько целых Кбайт требуется на все файлы?', answer,
                      f'⌈{count} × {packed+header} / 1024⌉ = {answer}.')],
                ['Число цветов может не быть степенью двойки. Выбирай минимальное i, для которого 2^i ≥ число цветов.',
                 'Сжимается только блок пикселей. Заголовок добавляй после сжатия; до Кбайт округляй общий объём.'],
                r'I=\left\lceil n\left(\left\lceil WHi\cdot p/(8\cdot100)\right\rceil+H_0\right)/1024\right\rceil',
                'Общий объём = число файлов × (сжатые пиксели + заголовок), затем округление до Кбайт вверх.',
                unit='Кбайт', params={'w': w, 'h': h, 'colors': colors, 'count': count, 'header': header, 'retained': retained})


def audio_task(skill, r):
    hz, depth, channels = r.choice([22050, 32000, 44100, 48000]), r.choice([8, 16, 24]), r.choice([1, 2])
    label = 'моно' if channels == 1 else 'стерео'
    per_second = hz*depth*channels//8
    common = f'Запись в формате {label}, частота {hz} Гц, глубина кодирования {depth} бит. Сжатия нет. '
    if skill == 'audio_time':
        limit, header = r.randint(8, 90), r.choice([1024, 4096, 8192])
        available = limit*2**20-header
        answer = available//per_second
        return Task(skill, 'Длительность записи · №7', common +
                    f'Под файл выделено не более {limit} Мбайт; заголовок занимает {header} байт. '
                    'Определите максимальную целую длительность записи в секундах. 1 Мбайт = 2^20 байт.', str(answer),
                    [step('Сколько байт занимает одна секунда?', per_second, f'{hz} × {depth} × {channels} / 8 = {per_second}.'),
                     step('Сколько байт доступно для звуковых данных?', available, f'{limit} × 2^20 − {header} = {available}.'),
                     step('Какова максимальная целая длительность?', answer,
                          f'⌊{available} / {per_second}⌋ = {answer}. Ещё одна секунда превысит лимит.')],
                    ['Вычти заголовок из лимита памяти.', 'Раздели доступные байты на байты в секунду. Максимум целых секунд округляется вниз.'],
                    unit='с', params={'hz': hz, 'depth': depth, 'channels': channels, 'limit': limit, 'header': header})
    minutes, seconds = r.randint(1, 5), r.randint(1, 59)
    duration = minutes*60+seconds
    raw = duration*per_second
    answer = ceildiv(raw, 1024)
    return Task(skill, 'Объём аудиозаписи · №7', common +
                f'Длительность — {minutes} мин {seconds} с. Заголовок не учитывается. '
                'Определите минимальное целое количество Кбайт, достаточное для хранения записи. 1 Кбайт = 1024 байта.', str(answer),
                [step('Какова длительность в секундах?', duration, f'{minutes} × 60 + {seconds} = {duration} с.'),
                 step('Каков точный объём записи в байтах?', raw, f'{hz} × {depth} × {channels} × {duration} / 8 = {raw}.'),
                 step('Сколько целых Кбайт достаточно для записи?', answer, f'⌈{raw} / 1024⌉ = {answer}. Для достаточного объёма округляем вверх.')],
                ['Переведи минуты в секунды и учти число каналов.', 'Объём в битах: частота × глубина × каналы × секунды. Затем переводи единицы и округляй только в конце.'],
                r'I=\left\lceil fbtc/(8\cdot1024)\right\rceil', 'Кбайт = округление вверх(f × b × t × c / 8 / 1024)',
                unit='Кбайт', params={'hz': hz, 'depth': depth, 'channels': channels, 'duration': duration})


def ratio_task(r):
    old_rate, new_rate = r.choice([(48000, 32000), (24000, 48000), (32000, 48000)])
    old_depth, new_depth = r.choice([(16, 24), (24, 16), (8, 16)])
    old_channels, new_channels = r.choice([(1, 2), (2, 1), (2, 2)])
    old_speed, new_speed = r.choice([(2, 5), (5, 2), (3, 4)])
    factor = Fraction(new_rate*new_depth*new_channels*old_speed, old_rate*old_depth*old_channels*new_speed)
    old_time = factor.denominator * r.randint(6, 40)
    answer = old_time*factor.numerator//factor.denominator
    return Task('ratio', 'Звук и время передачи · №7',
                f'Одна и та же запись сначала сохранена с частотой {old_rate} Гц, глубиной {old_depth} бит '
                f'и числом каналов {old_channels}. При скорости передачи {old_speed} Мбит/с файл передавался {old_time} с. '
                f'Запись той же длительности сохранили с частотой {new_rate} Гц, глубиной {new_depth} бит '
                f'и числом каналов {new_channels}. Новый файл передают со скоростью {new_speed} Мбит/с. '
                'Сжатия, заголовков и накладных расходов нет. Сколько секунд длится новая передача?', str(answer),
                [step('Сколько бит в секунду содержит исходная запись?', old_rate*old_depth*old_channels,
                      f'{old_rate} × {old_depth} × {old_channels} = {old_rate*old_depth*old_channels} бит/с.'),
                 step('Сколько бит в секунду содержит новая запись?', new_rate*new_depth*new_channels,
                      f'{new_rate} × {new_depth} × {new_channels} = {new_rate*new_depth*new_channels} бит/с.'),
                 step('Какое время передачи нового файла в секундах?', answer,
                      f'Время меняется пропорционально объёму и обратно пропорционально скорости: '
                      f'{old_time} × ({new_rate}/{old_rate}) × ({new_depth}/{old_depth}) × '
                      f'({new_channels}/{old_channels}) × ({old_speed}/{new_speed}) = {answer} с.')],
                ['Найди отношение объёмов новых и старых звуковых данных.',
                 'Для времени передачи отношение скоростей переворачивается: старая скорость / новая скорость.'],
                r't_2=t_1\frac{f_2b_2c_2}{f_1b_1c_1}\frac{v_1}{v_2}',
                't₂ = t₁ × (f₂/f₁) × (b₂/b₁) × (c₂/c₁) × (v₁/v₂)',
                unit='с', params={'old_rate': old_rate, 'new_rate': new_rate, 'old_depth': old_depth, 'new_depth': new_depth,
                                 'old_channels': old_channels, 'new_channels': new_channels,
                                 'old_speed': old_speed, 'new_speed': new_speed, 'old_time': old_time})


def words_task(skill, r):
    alphabet = sorted(r.sample(list('АБВГДЕКЛМНОПРСТ'), r.randint(4, 6)))
    length = r.randint(4, 6)
    special = r.choice(alphabet)
    if skill == 'words_rank':
        banned = alphabet[:r.randint(1, 2)]
        parity = r.randrange(2)
        minimum = r.randint(1, 2)
        # Exhaustive search is bounded by 6^6; no rejection loops.
        answer_word = None
        for rank, word in enumerate(product(alphabet, repeat=length), 1):
            if rank % 2 == parity and word[0] not in banned and word.count(special) >= minimum:
                answer_word, answer = ''.join(word), rank
                break
        if answer_word is None:
            raise AssertionError('Empty word-rank domain')
        index = answer-1
        positional = ' + '.join(f'{alphabet.index(a)} × {len(alphabet)}^{length-i-1}' for i, a in enumerate(answer_word))
        return Task(skill, 'Номер слова · №8',
                    f'Все слова длины {length} из букв {", ".join(alphabet)} записаны в алфавитном порядке '
                    'и пронумерованы с 1. Буквы могут повторяться. '
                    f'Найдите номер первого слова с {"чётным" if parity == 0 else "нечётным"} номером, '
                    f'которое не начинается ни с одной из букв {", ".join(banned)} и содержит не менее '
                    f'{"одного вхождения" if minimum == 1 else "двух вхождений"} буквы {special}. '
                    'Словом считается любая последовательность букв.', str(answer),
                    [step('Каково основание системы счисления для нумерации этих слов?', len(alphabet),
                          f'В алфавите {len(alphabet)} букв: используем цифры от 0 до {len(alphabet)-1}.'),
                     step('Каков номер первого подходящего слова?', answer,
                          f'Первое подходящее слово — {answer_word}. Заменяем буквы цифрами 0…{len(alphabet)-1}: '
                          f'номер − 1 = {positional} = {index}; номер = {answer}. '
                          'При поиске учитываются одновременно начальная буква, число вхождений и чётность номера.')],
                    ['Сначала упорядочь алфавит. Номер минус один — запись в системе счисления с основанием, равным размеру алфавита.',
                     'Ищи первое допустимое слово по порядку и проверяй чётность именно номера, а не последней цифры записи номера минус один.'],
                    params={'alphabet': alphabet, 'length': length, 'special': special, 'banned': banned, 'parity': parity, 'minimum': minimum})
    k = r.randint(1, 2)
    variant = r.choice(['first', 'adjacent'])
    n = len(alphabet)
    if variant == 'first':
        placements = comb(length-1, k)
        restriction = f'буква {special} встречается ровно {k} {noun(k, "раз", "раза", "раз")}, причём слово не начинается с этой буквы'
        explanation = f'Первую позицию занимать нельзя: выбираем {k} позиций из {length-1}. Число способов = {placements}.'
    else:
        placements = comb(length-k+1, k)
        restriction = f'буква {special} встречается ровно {k} {noun(k, "раз", "раза", "раз")} и никакие два её вхождения не стоят рядом'
        explanation = f'Для {k} несоседних позиций в строке длины {length} число способов равно C({length-k+1}, {k}) = {placements}.'
    filling = (n-1)**(length-k)
    answer = placements*filling
    return Task(skill, 'Слова с ограничениями · №8',
                f'Сколько слов длины {length} можно составить из букв {", ".join(alphabet)}, если {restriction}? '
                'Остальные буквы могут повторяться без ограничений. Слово — любая последовательность букв.', str(answer),
                [step(f'Сколькими способами можно выбрать позиции для буквы {special}?', placements, explanation),
                 step('Сколькими способами заполняются остальные позиции при фиксированных специальных позициях?', filling,
                      f'Для каждой из {length-k} позиций доступно {n-1} букв: ({n-1})^{length-k} = {filling}.'),
                 step('Сколько слов удовлетворяет всем условиям?', answer, f'{placements} × {filling} = {answer}.')],
                ['Сначала выбери допустимые позиции для буквы с ограничением.',
                 'Оставшиеся позиции нельзя заполнять этой же буквой: иначе нарушится требование «ровно».'],
                params={'alphabet': alphabet, 'length': length, 'special': special, 'k': k, 'variant': variant})


def records_task(skill, r):
    alphabet = r.choice([10, 26, 33, 52, 62, 90, 130, 200, 300, 1000])
    bits = (alphabet-1).bit_length()
    length, count, extra = r.randint(15, 180), r.randint(1200, 16000), r.randint(3, 24)
    record = ceildiv(length*bits, 8)+extra
    total = record*count
    common = ('Используется посимвольное кодирование: все символы кодируются одинаковым минимально возможным числом бит. '
              'На каждый идентификатор отводится минимальное целое число байт. ')
    params = {'alphabet': alphabet, 'length': length, 'count': count, 'extra': extra}
    if skill == 'records':
        answer = ceildiv(total, 1024)
        return Task(skill, 'Память для идентификаторов · №11',
                    f'Для {count} {noun(count, "объекта", "объектов", "объектов")} хранят идентификаторы длиной {length} '
                    f'{noun(length, "символ", "символа", "символов")} из алфавита мощностью {alphabet}. '
                    + common + f'Кроме идентификатора, для каждого объекта хранят {extra} {noun(extra, "байт", "байта", "байт")} дополнительных данных. '
                    'Определите минимальное целое число Кбайт для хранения всех записей. 1 Кбайт = 1024 байта.', str(answer),
                    [step('Сколько бит требуется на символ?', bits, f'2^{bits-1} < {alphabet} ≤ 2^{bits}: {bits} бит.'),
                     step('Сколько байт требуется на один идентификатор?', record-extra,
                          f'⌈{length} × {bits} / 8⌉ = {record-extra} байт.'),
                     step('Сколько байт занимают все записи?', total, f'({record-extra} + {extra}) × {count} = {total}.'),
                     step('Сколько целых Кбайт необходимо?', answer, f'⌈{total} / 1024⌉ = {answer}.')],
                    ['Мощность алфавита округляется до ближайшей сверху степени двойки, чтобы определить число бит.',
                     'Округляй до байта каждый идентификатор до умножения на количество объектов.'],
                    unit='Кбайт', params=params)
    limit = ceildiv(total, 1024)
    budget = limit*1024//count-extra
    params['limit'] = limit
    if skill == 'records_length':
        answer = budget*8//bits
        question = (f'Для {count} {noun(count, "объекта", "объектов", "объектов")} выделено не более {limit} Кбайт памяти. Идентификаторы имеют одинаковую длину '
                    f'и используют алфавит мощностью {alphabet}. ' + common +
                    f'Дополнительные данные каждого объекта занимают {extra} {noun(extra, "байт", "байта", "байт")}. '
                    'Какова максимально возможная длина идентификатора в символах? 1 Кбайт = 1024 байта.')
        last = step('Какова максимальная длина идентификатора?', answer,
                    f'На символ нужно {bits} бит; ⌊{budget} × 8 / {bits}⌋ = {answer}. Следующий символ уже не помещается.')
    else:
        capacity = budget*8//length
        answer = 2**capacity
        question = (f'Для {count} {noun(count, "объекта", "объектов", "объектов")} выделено не более {limit} Кбайт памяти. Длина каждого идентификатора — '
                    f'{length} {noun(length, "символ", "символа", "символов")}. ' + common +
                    f'Дополнительные данные каждого объекта занимают {extra} {noun(extra, "байт", "байта", "байт")}. '
                    'Найдите максимально возможную мощность алфавита. 1 Кбайт = 1024 байта.')
        last = step('Какова максимальная мощность алфавита?', answer,
                    f'⌊{budget} × 8 / {length}⌋ = {capacity} бит на символ. Максимум символов алфавита: 2^{capacity} = {answer}.')
    return Task(skill, 'Обратная задача · №11', question, str(answer),
                [step('Сколько целых байт можно выделить на одну запись?', budget+extra,
                      f'⌊{limit} × 1024 / {count}⌋ = {budget+extra}. Лимит нельзя превышать.'),
                 step('Сколько байт остаётся на идентификатор одной записи?', budget,
                      f'{budget+extra} − {extra} = {budget}.'), last],
                ['Сначала вычисли максимально допустимое целое число байт на одну запись.',
                 'После вычитания служебных данных переведи доступные байты в биты и найди нужный максимум.'], params=params)


def generate_exam(skill, r):
    if skill.startswith('fano'):
        return fano_task(skill, r)
    if skill == 'truth':
        return truth_task(r)
    if skill == 'binary':
        return binary_task(r)
    if skill == 'executor':
        return executor_task(r)
    if skill.startswith('image'):
        return image_task(skill, r)
    if skill.startswith('audio'):
        return audio_task(skill, r)
    if skill == 'ratio':
        return ratio_task(r)
    if skill.startswith('words'):
        return words_task(skill, r)
    if skill.startswith('records'):
        return records_task(skill, r)
    raise ValueError('Unknown exam skill: '+skill)
