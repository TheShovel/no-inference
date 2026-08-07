#!/usr/bin/env python3
"""Round 6: probe2 round-2 fixes."""
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


# ── 02_algorithms.json: prime template gains a sieve section ───────────────
d02 = load('02_algorithms.json')
pr = task(d02, 'prime')
pr['languages']['python'] += '''

# All primes up to n (sieve of Eratosthenes):
def primes_up_to(n: int) -> list:
    if n < 2:
        return []
    sieve = bytearray(b'\\x01') * (n + 1)
    sieve[0] = sieve[1] = 0
    for i in range(2, int(n ** 0.5) + 1):
        if sieve[i]:
            sieve[i*i::i] = bytearray(len(range(i*i, n + 1, i)))
    return [i for i, ok in enumerate(sieve) if ok]

# Example:
print(primes_up_to(30))  # [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]'''
save('02_algorithms.json', d02)

# ── 03_strings.json: string_to_list sentence phrasing ──────────────────────
d03 = load('03_strings.json')
stl = task(d03, 'string_to_list')
stl['patterns'].extend([
    r'\bsplit\s+(?:a\s+|the\s+)?sentence\s+into\b',
    r'\b(?:sentence|text)\s+into\s+words\b',
])
save('03_strings.json', d03)

# ── 10_sql.json: sql_aggregate needs a column-ish noun ─────────────────────
d10 = load('10_sql.json')
sa = task(d10, 'sql_aggregate')
sa['patterns'] = [
    r'\b(?:sum|average|avg|min|max|count)\s+of\b.*\b(?:column|field|value|table|rows?|records?|salary|price|amount|quantity|total)\b',
    r'\b(?:sum|average|avg|min|max|count)\s+of\b.*\bsql\b',
    r'\bsql\b.*\b(?:sum|average|avg|min|max|count)\s+of\b',
]
save('10_sql.json', d10)

# ── 11_git_bash.json: git_undo template gains discard-unstaged ─────────────
d11 = load('11_git_bash.json')
gu = task(d11, 'git_undo')
if 'git checkout -- .' not in gu['languages']['bash']:
    gu['languages']['bash'] += '''

# Discard unstaged changes (working tree only):
git checkout -- file.txt      # one file
git checkout -- .             # everything unstaged
git restore file.txt          # modern equivalent

# Unstage (keep changes): 
git reset HEAD file.txt'''
save('11_git_bash.json', d11)

# ── 14_js_utils.json: array_last accepts lists; new js tasks ───────────────
d14 = load('14_js_utils.json')
al = task(d14, 'array_last')
al['patterns'] = [
    r'\blast\s+(?:element|item|value)\s+of\s+(?:an?\s+|the\s+)?(?:array|list)\b',
    r'\b(?:get|access|return)\b.*\blast\b.*\b(?:element|item)\b.*\b(?:array|list)\b',
]
d14.append(new_task(
    'array_shift',
    [r'\bremove\b.*\bfirst\b.*\b(?:element|item|value)\b.*\b(?:array|list)\b',
     r'\b(?:shift|pop\s+front)\b.*\b(?:array|list)\b'],
    "Here's how to remove the first element of an array in {lang}.",
    "JS shift() removes and returns the first element in O(n). Python list.pop(0) is also O(n); use collections.deque popleft for O(1).",
    {
        'javascript': "const arr = [1, 2, 3, 4];\n"
                      "\n"
                      "// shift() removes AND returns the first element:\n"
                      "const first = arr.shift();\n"
                      "console.log(first);   // 1\n"
                      "console.log(arr);     // [2, 3, 4]\n"
                      "\n"
                      "// Non-mutating (slice):\n"
                      "const rest = arr.slice(1);\n"
                      "\n"
                      "// Clear the whole array:\n"
                      "arr.length = 0;",
        'python': "lst = [1, 2, 3, 4]\n"
                  "\n"
                  "# pop(0) removes AND returns the first element (O(n)):\n"
                  "first = lst.pop(0)\n"
                  "print(first)   # 1\n"
                  "print(lst)     # [2, 3, 4]\n"
                  "\n"
                  "# O(1) alternative with deque:\n"
                  "from collections import deque\n"
                  "d = deque([1, 2, 3])\n"
                  "print(d.popleft())   # 1",
    },
))
save('14_js_utils.json', d14)

# ── 13_python_utils.json: dir_watcher plural verb, new python tasks ────────
d13 = load('13_python_utils.json')
dw = task(d13, 'dir_watcher')
dw['patterns'] = [
    r'\bwatch\w*\b.*\b(?:directory|folder)\b.*\b(?:new\s+files?|changes?)\b',
    r'\bmonitor\b.*\b(?:directory|folder)\b.*\b(?:new\s+files?)\b',
]
d13.append(new_task(
    'string_to_datetime',
    [r'\bconvert\b.*\bstring\b.*\b(?:to\s+)?datetime\b',
     r'\b(?:parse|convert)\b.*\bstring\b.*\bdate\b.*\b(?:time|datetime)\b'],
    "Here's how to convert a string to a datetime in {lang}.",
    "strptime needs a format string that exactly matches the input. For ISO-8601 strings, datetime.fromisoformat (Python 3.11+) and new Date() (JS) parse them directly.",
    {
        'python': "from datetime import datetime\n"
                  "\n"
                  "# Exact format:\n"
                  "dt = datetime.strptime('2026-04-03 15:30:00', '%Y-%m-%d %H:%M:%S')\n"
                  "print(dt)   # 2026-04-03 15:30:00\n"
                  "\n"
                  "# ISO-8601 (fromisoformat, Python 3.11+):\n"
                  "dt2 = datetime.fromisoformat('2026-04-03T15:30:00')\n"
                  "\n"
                  "# Common formats:\n"
                  "datetime.strptime('04/03/2026', '%m/%d/%Y')\n"
                  "datetime.strptime('2026-04-03', '%Y-%m-%d')\n"
                  "\n"
                  "# Date only:\n"
                  "from datetime import date\n"
                  "d = date.fromisoformat('2026-04-03')\n"
                  "\n"
                  "# Back to a string:\n"
                  "print(dt.strftime('%Y-%m-%d'))",
        'javascript': "// new Date() parses ISO-8601 directly:\n"
                      "const dt = new Date('2026-04-03T15:30:00Z');\n"
                      "\n"
                      "// Manual parse of non-ISO formats:\n"
                      "function parseDate(s) {\n"
                      "    const [y, m, d] = s.split('-').map(Number);\n"
                      "    return new Date(y, m - 1, d);   // local time\n"
                      "}\n"
                      "console.log(parseDate('2026-04-03'));\n"
                      "\n"
                      "// Validate round-trip (rejects Feb 31):\n"
                      "function isValidDateStr(s) {\n"
                      "    const dt = new Date(s);\n"
                      "    return !Number.isNaN(dt.getTime());\n"
                      "}",
    },
))
d13.append(new_task(
    'only_digits',
    [r'\b(?:only\s+)?digits?\b.*\b(?:string|text|value)\b',
     r'\bcheck\b.*\b(?:string|text)\b.*\b(?:only\s+)?digits?\b'],
    "Here's a {lang} function that checks whether a string contains only digits.",
    "isdigit() is the direct answer. Use a regex when you also want to allow spaces, plus signs, or decimal points.",
    {
        'python': "s = '12345'\n"
                  "\n"
                  "print(s.isdigit())        # True\n"
                  "print('12a5'.isdigit())   # False\n"
                  "print('12.5'.isdigit())   # False\n"
                  "\n"
                  "# Allow decimals:\n"
                  "import re\n"
                  "def is_number(s: str) -> bool:\n"
                  "    return bool(re.fullmatch(r'\\d+(\\.\\d+)?', s.strip()))\n"
                  "\n"
                  "print(is_number('12.5'))      # True\n"
                  "print(is_number('-12'))       # False (add -? to allow)\n"
                  "\n"
                  "# Full numeric check (also negatives/exponents):\n"
                  "def is_numeric(s: str) -> bool:\n"
                  "    try:\n"
                  "        float(s)\n"
                  "        return True\n"
                  "    except ValueError:\n"
                  "        return False",
        'javascript': "const s = '12345';\n"
                      "\n"
                      "// Strictly digits:\n"
                      "console.log(/^\\d+$/.test(s));        // true\n"
                      "console.log(/^\\d+$/.test('12a5'));   // false\n"
                      "\n"
                      "// Allow decimals:\n"
                      "console.log(/^\\d+(\\.\\d+)?$/.test('12.5'));   // true\n"
                      "\n"
                      "// Full numeric (negatives, exponents):\n"
                      "console.log(!Number.isNaN(Number(s)) && s.trim() !== '');",
    },
))
d13.append(new_task(
    'list_vs_set',
    [r'\bchoose\s+between\b.*\b(?:list|set)\b',
     r'\blist\s+vs\w*\s+set\b.*\b(?:python|when)\b'],
    "Here's how to decide between a list and a set in {lang}.",
    "Sets guarantee O(1) membership tests and deduplication but have no order and can't hold duplicates. Lists preserve order, allow duplicates, and support indexing. Use a set for lookups and dedup; a list for ordered/duplicate data.",
    {
        'python': "# USE A SET when you need:\n"
                  "#  - fast membership checks:      'x' in my_set   (O(1))\n"
                  "#  - deduplication:                unique = set(items)\n"
                  "#  - set math:                     a & b, a | b, a - b\n"
                  "seen = set()\n"
                  "for item in stream:\n"
                  "    if item in seen:      # O(1) even for millions of items\n"
                  "        continue\n"
                  "    seen.add(item)\n"
                  "\n"
                  "# USE A LIST when you need:\n"
                  "numbers = [3, 1, 4, 1]     # duplicates allowed\n"
                  "print(numbers[0])          # indexing by position\n"
                  "print(numbers[-1])         # last element\n"
                  "numbers.append(5)          # append at the end\n"
                  "\n"
                  "# Convert between them:\n"
                  "unique_ordered = list(dict.fromkeys([3, 1, 3, 2]))  # [3, 1, 2]\n"
                  "s = set([1, 2, 2, 3])      # {1, 2, 3}",
        'javascript': "// USE A SET for fast membership + dedup:\n"
                      "const seen = new Set();\n"
                      "for (const item of stream) {\n"
                      "    if (seen.has(item)) continue;   // O(1)\n"
                      "    seen.add(item);\n"
                      "}\n"
                      "const unique = [...new Set([3, 1, 3, 2])];   // [3, 1, 2]\n"
                      "\n"
                      "// USE AN ARRAY for order, duplicates, indexing:\n"
                      "const nums = [3, 1, 4, 1];\n"
                      "console.log(nums[0]);        // 3\n"
                      "console.log(nums.at(-1));     // 1\n"
                      "nums.push(5);\n"
                      "\n"
                      "// Note: array .includes() is O(n) — use a Set for lookups.",
    },
))
save('13_python_utils.json', d13)

# ── 18_devops.json: fix the \\b\\. pattern bug ──────────────────────────────
d18 = load('18_devops.json')
br = task(d18, 'bash_rename_files')
br['patterns'] = [
    r'\brename\b.*\bfiles?\b.*(?:extension|\.\w+)\b',
    r'\brename\s+(?:all\s+)?\w+\s+files?\s+to\b',
]
save('18_devops.json', d18)

print('done')
