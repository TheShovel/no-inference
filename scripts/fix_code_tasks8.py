#!/usr/bin/env python3
"""Round 8: probe3 round-3 data fixes — new tasks + extra patterns."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / 'data' / 'knowledge' / 'code_tasks'


def load(name):
    with open(BASE / name, encoding='utf-8') as fh:
        return json.load(fh)


def save(name, data):
    with open(BASE / name, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write('\n')


def task(data, tid):
    items = data.get('tasks', []) if isinstance(data, dict) else data
    for t in items:
        if t['task'] == tid:
            return t
    raise KeyError(tid)


def new_task(tid, patterns, intro, notes, languages, default_lang=None):
    t = {
        'task': tid,
        'patterns': patterns,
        'intro': intro,
        'notes': notes,
        'languages': languages,
    }
    if default_lang:
        t['default_lang'] = default_lang
    return t


# 19_testing: pytest catches "test that checks this raises"
d19 = load('19_testing.json')
pt = task(d19, 'pytest_test')
pt['patterns'] = pt['patterns'] + [
    r'\b(?:write|create)\b.*\b(?:unit\s+)?test\b.*\b(?:raises?|error|exception)\b',
    r'\btest\b.*\b(?:raises?|exceptions?)\b',
]
save('19_testing.json', d19)

# 13: periodic_request reversed pattern; center_div + responsive_navbar
d13 = load('13_python_utils.json')
pr = task(d13, 'periodic_request')
pr['patterns'] = pr['patterns'] + [
    r'\b(?:request|api|call|fetch)\b.*\b(?:every|each)\s+\d+\s+seconds?\b',
]
d13.append(new_task(
    'center_div',
    [r'\bcenter\b.*\bdiv\b',
     r'\bcenter\s+(?:a\s+|the\s+)?(?:div|element|item)\b'],
    "Here's how to center a div with CSS.",
    "Flexbox is the modern way: justify-content + align-items on the parent. For a single element, place-items: center on a grid container is even shorter.",
    {
        'css': "/* Center horizontally AND vertically with flexbox: */\n"
               ".parent {\n"
               "    display: flex;\n"
               "    justify-content: center;   /* horizontal */\n"
               "    align-items: center;       /* vertical */\n"
               "    min-height: 100vh;         /* give it height to center in */\n"
               "}\n"
               "\n"
               "/* Even shorter with grid: */\n"
               ".parent {\n"
               "    display: grid;\n"
               "    place-items: center;       /* both axes at once */\n"
               "    min-height: 100vh;\n"
               "}\n"
               "\n"
               "/* Center TEXT inside a block: */\n"
               ".child {\n"
               "    text-align: center;\n"
               "}\n"
               "\n"
               "/* Center a block element horizontally: */\n"
               ".block {\n"
               "    margin: 0 auto;\n"
               "    width: fit-content;\n"
               "}",
    },
    default_lang='css',
))
d13.append(new_task(
    'responsive_navbar',
    [r'\bresponsive\b.*\bnavbar\b',
     r'\bnavbar\b.*\b(?:mobile|responsive)\b'],
    "Here's how to make a responsive navbar with CSS.",
    "The pattern: a horizontal flex nav on desktop, a hamburger/stacked column on small screens via a media query. Use max-width: 768px as the breakpoint.",
    {
        'css': ".navbar {\n"
               "    display: flex;\n"
               "    justify-content: space-between;\n"
               "    align-items: center;\n"
               "    padding: 0 1rem;\n"
               "    background: #2c3e50;\n"
               "}\n"
               "\n"
               ".nav-links {\n"
               "    display: flex;\n"
               "    gap: 1.5rem;\n"
               "    list-style: none;\n"
               "}\n"
               "\n"
               ".nav-links a {\n"
               "    color: #fff;\n"
               "    text-decoration: none;\n"
               "}\n"
               "\n"
               "/* Mobile: stack the links vertically */\n"
               "@media (max-width: 768px) {\n"
               "    .navbar {\n"
               "        flex-direction: column;\n"
               "    }\n"
               "    .nav-links {\n"
               "        flex-direction: column;\n"
               "        align-items: center;\n"
               "        padding: 0;\n"
               "    }\n"
               "}",
        'html': '<nav class="navbar">\n'
                '  <div class="logo">MySite</div>\n'
                '  <ul class="nav-links">\n'
                '    <li><a href="#">Home</a></li>\n'
                '    <li><a href="#">About</a></li>\n'
                '    <li><a href="#">Contact</a></li>\n'
                '  </ul>\n'
                '</nav>',
    },
    default_lang='css',
))
save('13_python_utils.json', d13)

print('done')
