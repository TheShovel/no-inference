#!/usr/bin/env python3
"""Round 4 data fixes: group_dicts JS idiom + for_loop while examples."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / 'data' / 'knowledge' / 'code_tasks'

# 1. group_dicts JS: idiomatic, no param shadowing, matches editor idiom
d13 = json.load(open(BASE / '13_python_utils.json'))
gd = [t for t in d13 if t['task'] == 'group_dicts'][0]
gd['languages']['javascript'] = (
    "const people = [\n"
    "    { name: 'alice', dept: 'eng' },\n"
    "    { name: 'bob', dept: 'sales' },\n"
    "    { name: 'carol', dept: 'eng' },\n"
    "    { name: 'dave', dept: 'sales' },\n"
    "];\n"
    "\n"
    "function groupBy(items, keyFn) {\n"
    "    const out = {};\n"
    "    for (const item of items) {\n"
    "        const g = keyFn(item);\n"
    "        (out[g] = out[g] || []).push(item);\n"
    "    }\n"
    "    return out;\n"
    "}\n"
    "\n"
    "console.log(groupBy(people, p => p.dept));"
)
json.dump(d13, open(BASE / '13_python_utils.json', 'w'), indent=2, ensure_ascii=False)

# 2. for_loop python: add while-loop examples
d04 = json.load(open(BASE / '04_basics.json'))
fl = [t for t in d04['tasks'] if t['task'] == 'for_loop'][0]
fl['languages']['python'] = (
    '# Loop over a range:\n'
    'for i in range(5):\n'
    '    print(i)        # 0 1 2 3 4\n'
    '\n'
    '# Loop over a collection:\n'
    "for item in ['a', 'b', 'c']:\n"
    '    print(item)\n'
    '\n'
    '# With index (enumerate):\n'
    "for idx, item in enumerate(['a', 'b', 'c']):\n"
    '    print(idx, item)\n'
    '\n'
    '# Range with start and step:\n'
    'for i in range(1, 10, 2):\n'
    '    print(i)        # 1 3 5 7 9\n'
    '\n'
    '# While loop (runs while a condition holds):\n'
    'i = 0\n'
    'while i < 5:\n'
    '    print(i)\n'
    "    i += 1          # don't forget to advance — or it never stops\n"
    '\n'
    '# while vs for: use for when iterating over a known collection/range;\n'
    '# use while when the end condition is computed (reading input, polling).'
)
json.dump(d04, open(BASE / '04_basics.json', 'w'), indent=2, ensure_ascii=False)
print('done')
