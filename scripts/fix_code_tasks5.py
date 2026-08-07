#!/usr/bin/env python3
"""Round 5: probe2 battery fixes — new tasks + hijack guards."""
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


# ── 02_algorithms.json: nth_prime first + is_even phrasings ───────────────
d02 = load('02_algorithms.json')
d02['tasks'].insert(0, new_task(
    'nth_prime',
    [r'\bnth\s+prime\b'],
    "Here's a {lang} function that computes the nth prime number.",
    "A sieve of Eratosthenes with a growable bound is the practical approach; each n-th prime p(n) is below n(ln n + ln ln n) for n ≥ 6, so that's a safe upper bound to sieve to.",
    {
        'python': "def nth_prime(n: int) -> int:\n"
                  "    \"\"\"Return the n-th prime (1-based: nth_prime(1) == 2).\"\"\"\n"
                  "    if n < 1:\n"
                  "        raise ValueError('n must be >= 1')\n"
                  "    # Upper bound: p(n) < n(ln n + ln ln n) for n >= 6\n"
                  "    import math\n"
                  "    if n < 6:\n"
                  "        limit = 15\n"
                  "    else:\n"
                  "        limit = int(n * (math.log(n) + math.log(math.log(n)))) + 10\n"
                  "    sieve = bytearray(b'\\x01') * (limit + 1)\n"
                  "    sieve[0] = sieve[1] = 0\n"
                  "    for i in range(2, int(limit ** 0.5) + 1):\n"
                  "        if sieve[i]:\n"
                  "            sieve[i*i::i] = bytearray(len(range(i*i, limit + 1, i)))\n"
                  "    count = 0\n"
                  "    for i, is_prime in enumerate(sieve):\n"
                  "        if is_prime:\n"
                  "            count += 1\n"
                  "            if count == n:\n"
                  "                return i\n"
                  "    raise ValueError('bound too small')\n"
                  "\n"
                  "# Example:\n"
                  "print(nth_prime(1))    # 2\n"
                  "print(nth_prime(10))   # 29\n"
                  "print(nth_prime(100))  # 541",
    },
))
ie = task(d02, 'is_even')
ie['patterns'].append(r'\b(?:even|odd)\s+or\s+(?:odd|even)\b')
ie['patterns'].append(r'\bis\s+this\s+number\s+(?:even|odd)\b')
sl = task(d02, 'sort_list')
sl['patterns'].extend([
    r'\bsort\s+(?:a\s+|the\s+|this\s+)?(?:list|array|slice|vector)\s+(?:in\s+)?(?:descending|reverse)\b',
    r'\b(?:descending|reverse)\s+order\b.*\bsort\b',
])
save('02_algorithms.json', d02)

# ── 03_strings.json pattern fixes ──────────────────────────────────────────
d03 = load('03_strings.json')
save('03_strings.json', d03)

# ── 05_sysadmin.json: sys_port/sys_kill extra phrasings ────────────────────
d05 = load('05_sysadmin.json')
sp = task(d05, 'sys_port')
sp['patterns'].extend([
    r'\b(?:see|list|show|find|check)\b.*\bopen\s+ports?\b',
    r'\bss\s+-tulpn\b',
])
sk = task(d05, 'sys_kill')
sk['patterns'].extend([
    r'\bfind\b.*\bprocess\b.*\bby\s+name\b',
    r'\bpgrep\b',
])
d05['tasks'].append(new_task(
    'bash_command_exists',
    [r'\b(?:check|test|see)\b.*\b(?:if\s+)?(?:a\s+)?command\s+exists\b',
     r'\bcommand\s+exists\b'],
    "Here's how to check whether a command exists in {lang}.",
    "command -v is the POSIX way; type is bash-specific. Use the if/else form when you need to act on the result, and set a default when the tool is optional.",
    {
        'bash': "# command -v works in sh/bash/zsh:\nif command -v jq >/dev/null 2>&1; then\n    echo 'jq is installed'\nelse\n    echo 'jq is missing — install it with: sudo apt install jq'\nfi\n\n# One-liner with a default:\nJQ=\"$(command -v jq || echo /usr/local/bin/jq)\"\n\n# Bash-only: type\ntype -P git >/dev/null 2>&1 && echo 'git present'\n\n# Check a version (some tools exit nonzero without args):\npython3 --version >/dev/null 2>&1 && echo 'python3 available'",
        'python': "import shutil\n\n# shutil.which returns the path or None:\nif shutil.which('ffmpeg'):\n    print('ffmpeg is available')\nelse:\n    print('ffmpeg is missing')\n\n# Version check:\nimport subprocess\nresult = subprocess.run(['python3', '--version'], capture_output=True, text=True)\nprint(result.stdout.strip())",
    },
    default_lang='bash',
))
save('05_sysadmin.json', d05)

# ── 08_file_io.json: read_file must not swallow \"read file and count words\" ─
d08 = load('08_file_io.json')
rf = task(d08, 'read_file')
rf['patterns'] = [
    r'^(?!.*\bcount\b.*\bwords?\b).*\bread\s+(?:a\s+)?file\b',
    r'\bread\s+file\s+line\s+by\s+line\b',
    r'\bopen\s+(?:and\s+)?read\s+(?:a\s+)?file\b',
    r'\bread\s+text\s+file\b',
]
save('08_file_io.json', d08)

# ── 09_http.json: regex_phone extra phrasing ───────────────────────────────
d07 = load('07_regex.json')
rp = task(d07, 'regex_phone')
rp['patterns'].append(r'\bcheck\s+if\s+(?:a\s+)?string\s+is\s+(?:a\s+)?valid\s+phone\s+number\b')
save('07_regex.json', d07)

# ── 17_sql_adv.json: left-join "customers who made no orders" ─────────────
d17 = load('17_sql_adv.json')
lj = task(d17, 'sql_left_join')
lj['patterns'].append(r'\b(?:customers?|users?)\b.*\b(?:who\s+)?(?:made\s+no|without|with\s+no|never\s+)\s+orders?\b')
save('17_sql_adv.json', d17)

# ── 11_git_bash.json: git_undo discard changes ─────────────────────────────
d11 = load('11_git_bash.json')
gu = task(d11, 'git_undo')
gu['patterns'].extend([
    r'\bdiscard\b.*\b(?:unstaged\s+)?changes?\b',
    r'\bundo\b.*\bchanges?\b',
])
save('11_git_bash.json', d11)

# ── 12_more.json: random_number plural, count_words Counter ────────────────
d12 = load('12_more.json')
rn = task(d12, 'random_number')
rn['patterns'].append(r'\brandom\s+numbers?\b')
cw = task(d12, 'count_words')
cw['languages']['python'] = (
    "from collections import Counter\n"
    "\n"
    "def count_words(text: str) -> dict:\n"
    "    \"\"\"Return {word: count} for a piece of text.\"\"\"\n"
    "    return dict(Counter(text.lower().split()))\n"
    "\n"
    "# Example:\n"
    "text = 'the cat and the dog and the bird'\n"
    "print(count_words(text))\n"
    "# {'the': 3, 'cat': 1, 'and': 2, 'dog': 1, 'bird': 1}\n"
    "\n"
    "# Word counts from a file:\n"
    "with open('notes.txt', encoding='utf-8') as f:\n"
    "    counts = Counter(f.read().lower().split())\n"
    "\n"
    "# Most common words:\n"
    "print(counts.most_common(5))"
)
save('12_more.json', d12)

# ── 13_python_utils.json: new python tasks ─────────────────────────────────
d13 = load('13_python_utils.json')
new13 = [
    new_task(
        'second_largest',
        [r'\bsecond\s+(?:largest|biggest|highest|maximum)\b'],
        "Here's a {lang} function that finds the second largest number in a list.",
        "Sorting and indexing is clearest; the two-pass max() version avoids a full sort. For huge lists, heapq.nlargest(2, items)[-1] is O(n log 2).",
        {
            'python': "def second_largest(numbers: list) -> float:\n"
                      "    if len(numbers) < 2:\n"
                      "        raise ValueError('need at least two numbers')\n"
                      "    return sorted(numbers)[-2]\n"
                      "\n"
                      "# Without sorting (two passes):\n"
                      "def second_largest_linear(numbers: list) -> float:\n"
                      "    if len(numbers) < 2:\n"
                      "        raise ValueError('need at least two numbers')\n"
                      "    largest = max(numbers)\n"
                      "    return max(n for n in numbers if n != largest)\n"
                      "\n"
                      "# Examples:\n"
                      "print(second_largest([3, 7, 2, 9, 5]))        # 7\n"
                      "print(second_largest_linear([3, 7, 2, 9, 5]))  # 7",
            'javascript': "function secondLargest(numbers) {\n"
                          "    if (numbers.length < 2) throw new Error('need at least two numbers');\n"
                          "    const sorted = [...numbers].sort((a, b) => a - b);\n"
                          "    return sorted[sorted.length - 2];\n"
                          "}\n"
                          "\n"
                          "console.log(secondLargest([3, 7, 2, 9, 5]));  // 7",
        },
    ),
    new_task(
        'count_vowels',
        [r'\bcount\b.*\bvowels?\b',
         r'\bvowels?\s+in\s+(?:a\s+|the\s+)?string\b'],
        "Here's a {lang} function that counts vowels in a string.",
        "The straightforward loop with a membership check is O(n). For performance-critical code, a translation table or regex does the same job in C speed.",
        {
            'python': "def count_vowels(s: str) -> int:\n"
                      "    return sum(1 for ch in s.lower() if ch in 'aeiou')\n"
                      "\n"
                      "# Examples:\n"
                      "print(count_vowels('hello'))      # 2\n"
                      "print(count_vowels('AEIOU'))      # 5\n"
                      "print(count_vowels('rhythm'))     # 0\n"
                      "\n"
                      "# Per-vowel breakdown:\n"
                      "from collections import Counter\n"
                      "def vowel_counts(s: str):\n"
                      "    return Counter(ch for ch in s.lower() if ch in 'aeiou')\n"
                      "print(vowel_counts('banana'))   # Counter({'a': 3})",
            'javascript': "function countVowels(s) {\n"
                          "    const m = s.toLowerCase().match(/[aeiou]/g);\n"
                          "    return m ? m.length : 0;\n"
                          "}\n"
                          "\n"
                          "console.log(countVowels('hello'));   // 2\n"
                          "console.log(countVowels('rhythm'));  // 0",
        },
    ),
    new_task(
        'find_duplicates',
        [r'\bfind\b.*\b(?:duplicate\w*|repeated\w*)\b.*\b(?:elements?|items?|values?|numbers?)\b.*\b(?:list|array)\b'],
        "Here's a {lang} function that finds the duplicate elements in a list.",
        "Counter tells you which items repeat and how often. The set-based version keeps first-seen order and stops storing counts.",
        {
            'python': "from collections import Counter\n"
                      "\n"
                      "def find_duplicates(items: list) -> list:\n"
                      "    \"\"\"Items that appear more than once, in first-seen order.\"\"\"\n"
                      "    counts = Counter(items)\n"
                      "    return [item for item, n in counts.items() if n > 1]\n"
                      "\n"
                      "# Without Counter:\n"
                      "def find_duplicates_fast(items: list) -> list:\n"
                      "    seen, dupes = set(), []\n"
                      "    for item in items:\n"
                      "        if item in seen and item not in dupes:\n"
                      "            dupes.append(item)\n"
                      "        seen.add(item)\n"
                      "    return dupes\n"
                      "\n"
                      "# Examples:\n"
                      "print(find_duplicates([1, 2, 3, 2, 4, 1, 5]))  # [1, 2]",
            'javascript': "function findDuplicates(items) {\n"
                          "    const seen = new Set();\n"
                          "    const dupes = new Set();\n"
                          "    for (const item of items) {\n"
                          "        if (seen.has(item)) dupes.add(item);\n"
                          "        seen.add(item);\n"
                          "    }\n"
                          "    return [...dupes];\n"
                          "}\n"
                          "\n"
                          "console.log(findDuplicates([1, 2, 3, 2, 4, 1, 5]));  // [1, 2]",
        },
    ),
    new_task(
        'list_to_numbers',
        [r'\bconvert\b.*\blist\s+of\s+strings?\b.*\b(?:to\s+)?(?:integers?|numbers?|ints?)\b',
         r'\b(?:list|array)\s+of\s+strings?\b.*\b(?:to\s+)?(?:int|number)s?\b'],
        "Here's how to convert a list of strings to numbers in {lang}.",
        "Python's map(int, items) applies the conversion lazily; a comprehension is clearer when you need to handle bad input. In JS, Number() is strict and parseInt() reads a prefix.",
        {
            'python': "items = ['1', '2', '3', '4']\n"
                      "\n"
                      "# Map (lazy):\n"
                      "nums = list(map(int, items))\n"
                      "print(nums)   # [1, 2, 3, 4]\n"
                      "\n"
                      "# Comprehension (recommended):\n"
                      "nums = [int(x) for x in items]\n"
                      "\n"
                      "# Floats:\n"
                      "floats = [float(x) for x in ['1.5', '2.5']]\n"
                      "\n"
                      "# Ignore non-numeric entries:\n"
                      "messy = ['1', 'x', '3']\n"
                      "clean = [int(x) for x in messy if x.isdigit()]\n"
                      "print(clean)   # [1, 3]",
            'javascript': "const items = ['1', '2', '3', '4'];\n"
                          "\n"
                          "// Number() — strict, NaN for bad input:\n"
                          "const nums = items.map(Number);\n"
                          "console.log(nums);   // [1, 2, 3, 4]\n"
                          "\n"
                          "// parseInt — reads a prefix, needs a radix:\n"
                          "const nums2 = items.map(s => parseInt(s, 10));\n"
                          "\n"
                          "// Filter out NaN results:\n"
                          "const clean = items.map(Number).filter(n => !Number.isNaN(n));",
        },
    ),
    new_task(
        'dict_has_key',
        [r'\b(?:check|test|see|determine)\b.*\b(?:if\s+)?(?:a\s+)?key\s+exists\b.*\b(?:dict|dictionary)\b',
         r'\bkey\s+exists\b.*\b(?:dict|dictionary)\b'],
        "Here's how to check whether a key exists in a dictionary in {lang}.",
        "Python's 'in' checks the keys directly. .get() with a default handles the missing case in one call. In JS, 'in' includes inherited keys — use Object.hasOwn for own keys only.",
        {
            'python': "d = {'a': 1, 'b': 2}\n"
                      "\n"
                      "# Membership:\n"
                      "print('a' in d)          # True\n"
                      "print('z' in d)          # False\n"
                      "\n"
                      "# Get with a default (no KeyError):\n"
                      "value = d.get('z', 'default')\n"
                      "print(value)             # 'default'\n"
                      "\n"
                      "# Try/except when you must distinguish:\n"
                      "try:\n"
                      "    v = d['z']\n"
                      "except KeyError:\n"
                      "    v = 'default'",
            'javascript': "const d = { a: 1, b: 2 };\n"
                          "\n"
                          "// 'in' includes inherited keys:\n"
                          "console.log('a' in d);             // true\n"
                          "\n"
                          "// Own keys only (recommended):\n"
                          "console.log(Object.hasOwn(d, 'a')); // true\n"
                          "console.log(d.hasOwnProperty('a')); // true (older)\n"
                          "\n"
                          "// Get with a default:\n"
                          "const value = d['z'] ?? 'default';\n"
                          "console.log(value);   // 'default'",
        },
    ),
    new_task(
        'number_commas',
        [r'\b(?:format|add|insert)\b.*\bcommas?\b.*\bnumber\b',
         r'\bnumber\b.*\bcommas?\b',
         r'\bthousands?\s+separator\b'],
        "Here's how to format a number with thousands separators in {lang}.",
        "The locale-based formatters handle grouping, decimals, and negative numbers correctly — don't hand-roll comma insertion. Python: f'{n:,}' or locale. JS: toLocaleString.",
        {
            'python': "n = 1234567.891\n"
                      "\n"
                      "# f-string grouping:\n"
                      "print(f'{n:,}')        # 1,234,567.891\n"
                      "\n"
                      "# Integer:\n"
                      "print(f'{1234567:,}')  # 1,234,567\n"
                      "\n"
                      "# locale-aware (grouping matches the user's locale):\n"
                      "import locale\n"
                      "locale.setlocale(locale.LC_ALL, '')\n"
                      "print(locale.format_string('%d', 1234567, grouping=True))\n"
                      "\n"
                      "# Formatting inside an f-string with decimals:\n"
                      "print(f'{n:,.2f}')     # 1,234,567.89",
            'javascript': "const n = 1234567.891;\n"
                          "\n"
                          "console.log(n.toLocaleString('en-US'));   // 1,234,567.891\n"
                          "\n"
                          "// Force grouping with a fixed style:\n"
                          "console.log(new Intl.NumberFormat('en-US', {\n"
                          "    maximumFractionDigits: 2\n"
                          "}).format(n));   // 1,234,567.89\n"
                          "\n"
                          "// Currency:\n"
                          "console.log(new Intl.NumberFormat('en-US', {\n"
                          "    style: 'currency', currency: 'USD'\n"
                          "}).format(n));   // $1,234,567.89",
        },
    ),
    new_task(
        'check_type',
        [r'\bcheck\b.*\btype\b.*\b(?:of\s+)?(?:variable|value|object)\b',
         r'\b(?:what\s+type|type\s+of)\b.*\b(?:variable|value|object)\b'],
        "Here's how to check the type of a variable in {lang}.",
        "Python's type() gives the exact class; isinstance() checks inheritance and is the right tool for branching. In JS, typeof is for primitives and Array.isArray for arrays.",
        {
            'python': "x = 42\n"
                      "\n"
                      "# Exact type:\n"
                      "print(type(x))            # <class 'int'>\n"
                      "\n"
                      "# For branching, use isinstance (handles subclasses):\n"
                      "if isinstance(x, int):\n"
                      "    print('integer')\n"
                      "elif isinstance(x, str):\n"
                      "    print('string')\n"
                      "\n"
                      "# Strings, lists, dicts:\n"
                      "print(isinstance('hi', str))     # True\n"
                      "print(isinstance([1], list))     # True\n"
                      "print(isinstance({'a': 1}, dict))  # True\n"
                      "\n"
                      "# Duck-typing alternative:\n"
                      "print(hasattr(x, '__iter__'))    # True for iterables",
            'javascript': "let x = 42;\n"
                          "\n"
                          "// typeof — primitives and functions:\n"
                          "console.log(typeof x);              // 'number'\n"
                          "console.log(typeof 'hi');           // 'string'\n"
                          "console.log(typeof true);           // 'boolean'\n"
                          "console.log(typeof undefined);      // 'undefined'\n"
                          "\n"
                          "// typeof [] is 'object' — use Array.isArray:\n"
                          "console.log(Array.isArray([1, 2]));  // true\n"
                          "console.log(Array.isArray({}));      // false\n"
                          "\n"
                          "// null check:\n"
                          "console.log(x === null);\n"
                          "\n"
                          "// Instance checks:\n"
                          "console.log(new Date() instanceof Date);  // true",
        },
    ),
    new_task(
        'remove_vowels',
        [r'\bremove\b.*\bvowels?\b.*\b(?:string|text|word)\b'],
        "Here's a {lang} function that removes vowels from a string.",
        "A translation table (Python) or regex (both languages) removes vowels in one pass. Remember that y is sometimes a vowel — this version keeps it.",
        {
            'python': "def remove_vowels(s: str) -> str:\n"
                      "    return ''.join(ch for ch in s if ch.lower() not in 'aeiou')\n"
                      "\n"
                      "# Fast version with a translation table:\n"
                      "def remove_vowels_fast(s: str) -> str:\n"
                      "    table = str.maketrans('', '', 'aeiouAEIOU')\n"
                      "    return s.translate(table)\n"
                      "\n"
                      "# Regex version:\n"
                      "import re\n"
                      "def remove_vowels_re(s: str) -> str:\n"
                      "    return re.sub(r'[aeiouAEIOU]', '', s)\n"
                      "\n"
                      "print(remove_vowels('hello world'))   # hll wrld",
            'javascript': "function removeVowels(s) {\n"
                          "    return s.replace(/[aeiouAEIOU]/g, '');\n"
                          "}\n"
                          "\n"
                          "// Case-insensitive:\n"
                          "function removeVowels2(s) {\n"
                          "    return s.replace(/[aeiou]/gi, '');\n"
                          "}\n"
                          "\n"
                          "console.log(removeVowels('hello world'));   // 'hll wrld'",
        },
    ),
    new_task(
        'sum_even',
        [r'\bsum\b.*\beven\b.*\b(?:numbers?|list|array)\b',
         r'\beven\s+numbers?\b.*\bsum\b'],
        "Here's a {lang} function that sums the even numbers in a list.",
        "Filter then sum — a comprehension with an if clause is the Pythonic one-liner; reduce or filter+sum work in JS.",
        {
            'python': "def sum_even(numbers: list) -> int:\n"
                      "    return sum(n for n in numbers if n % 2 == 0)\n"
                      "\n"
                      "# Examples:\n"
                      "print(sum_even([1, 2, 3, 4, 5, 6]))   # 12 (2+4+6)\n"
                      "print(sum_even([1, 3, 5]))           # 0",
            'javascript': "function sumEven(numbers) {\n"
                          "    return numbers\n"
                          "        .filter(n => n % 2 === 0)\n"
                          "        .reduce((acc, n) => acc + n, 0);\n"
                          "}\n"
                          "\n"
                          "console.log(sumEven([1, 2, 3, 4, 5, 6]));   // 12",
        },
    ),
    new_task(
        'dir_watcher',
        [r'\bwatch\b.*\b(?:directory|folder)\b.*\b(?:new\s+files?|changes?)\b',
         r'\bmonitor\b.*\b(?:directory|folder)\b.*\b(?:new\s+files?)\b'],
        "Here's a {lang} script that watches a directory for new files.",
        "Polling the directory listing is portable; watchdog (Python) uses OS events and scales better. The set-difference approach below reports only brand-new files.",
        {
            'python': "import os\n"
                      "import time\n"
                      "\n"
                      "def watch_directory(path: str, interval: float = 1.0):\n"
                      "    \"\"\"Print new files as they appear in a directory.\"\"\"\n"
                      "    seen = set(os.listdir(path))\n"
                      "    while True:\n"
                      "        time.sleep(interval)\n"
                      "        current = set(os.listdir(path))\n"
                      "        for name in current - seen:\n"
                      "            print('new file:', name)\n"
                      "        seen = current\n"
                      "\n"
                      "# Usage: watch_directory('./uploads')\n"
                      "\n"
                      "# Event-based alternative (pip install watchdog):\n"
                      "# from watchdog.observers import Observer\n"
                      "# from watchdog.events import FileSystemEventHandler\n"
                      "# class Handler(FileSystemEventHandler):\n"
                      "#     def on_created(self, event):\n"
                      "#         print('created', event.src_path)\n"
                      "# observer = Observer()\n"
                      "# observer.schedule(Handler(), path='.')\n"
                      "# observer.start()",
            'javascript': "const fs = require('fs');\n"
                          "\n"
                          "function watchDirectory(path, interval = 1000) {\n"
                          "    let seen = new Set(fs.readdirSync(path));\n"
                          "    setInterval(() => {\n"
                          "        const current = new Set(fs.readdirSync(path));\n"
                          "        for (const name of current) {\n"
                          "            if (!seen.has(name)) console.log('new file:', name);\n"
                          "        }\n"
                          "        seen = current;\n"
                          "    }, interval);\n"
                          "}\n"
                          "\n"
                          "// watchDirectory('./uploads');",
        },
    ),
    new_task(
        'luhn_check',
        [r'\bluhn\b',
         r'\b(?:validate|check)\b.*\bcredit\s+card\b'],
        "Here's a {lang} function that validates a credit card number using the Luhn algorithm.",
        "The Luhn checksum doubles every second digit from the right and subtracts 9 from results over 9; the total must be divisible by 10. Strip spaces/dashes before validating.",
        {
            'python': "def luhn_check(card_number: str) -> bool:\n"
                      "    \"\"\"True for a valid Luhn checksum (digits only).\"\"\"\n"
                      "    digits = [int(ch) for ch in card_number if ch.isdigit()]\n"
                      "    if len(digits) < 2:\n"
                      "        return False\n"
                      "    total = 0\n"
                      "    for i, d in enumerate(reversed(digits)):\n"
                      "        if i % 2 == 1:      # double every second digit from the right\n"
                      "            d *= 2\n"
                      "            if d > 9:\n"
                      "                d -= 9\n"
                      "        total += d\n"
                      "    return total % 10 == 0\n"
                      "\n"
                      "# Examples (test numbers):\n"
                      "print(luhn_check('4539 1488 0343 6467'))   # True\n"
                      "print(luhn_check('4539 1488 0343 6468'))   # False",
            'javascript': "function luhnCheck(cardNumber) {\n"
                          "    const digits = cardNumber.replace(/\\D/g, '').split('').map(Number);\n"
                          "    if (digits.length < 2) return false;\n"
                          "    let total = 0;\n"
                          "    for (let i = digits.length - 1, dbl = false; i >= 0; i--, dbl = !dbl) {\n"
                          "        let d = digits[i];\n"
                          "        if (dbl) {\n"
                          "            d *= 2;\n"
                          "            if (d > 9) d -= 9;\n"
                          "        }\n"
                          "        total += d;\n"
                          "    }\n"
                          "    return total % 10 === 0;\n"
                          "}\n"
                          "\n"
                          "console.log(luhnCheck('4539 1488 0343 6467'));  // true",
        },
    ),
    new_task(
        'permutations',
        [r'\bpermutations?\b'],
        "Here's how to generate all permutations of a string in {lang}.",
        "itertools.permutations is the stdlib answer for strings and lists. The recursive version is the classic interview implementation.",
        {
            'python': "from itertools import permutations\n"
                      "\n"
                      "# Stdlib (string):\n"
                      "s = 'abc'\n"
                      "perms = [''.join(p) for p in permutations(s)]\n"
                      "print(perms)   # ['abc', 'acb', 'bac', 'bca', 'cab', 'cba']\n"
                      "\n"
                      "# Recursive implementation:\n"
                      "def permute(s: str) -> list:\n"
                      "    if len(s) <= 1:\n"
                      "        return [s]\n"
                      "    out = []\n"
                      "    for i, ch in enumerate(s):\n"
                      "        for rest in permute(s[:i] + s[i+1:]):\n"
                      "            out.append(ch + rest)\n"
                      "    return out\n"
                      "\n"
                      "print(permute('abc'))",
            'javascript': "function permutations(s) {\n"
                          "    if (s.length <= 1) return [s];\n"
                          "    const out = [];\n"
                          "    for (let i = 0; i < s.length; i++) {\n"
                          "        const rest = s.slice(0, i) + s.slice(i + 1);\n"
                          "        for (const p of permutations(rest)) {\n"
                          "            out.push(s[i] + p);\n"
                          "        }\n"
                          "    }\n"
                          "    return out;\n"
                          "}\n"
                          "\n"
                          "console.log(permutations('abc'));\n"
                          "// ['abc', 'acb', 'bac', 'bca', 'cab', 'cba']",
        },
    ),
    new_task(
        'perfect_square',
        [r'\bperfect\s+square\b'],
        "Here's a {lang} function that checks whether a number is a perfect square.",
        "math.isqrt (Python 3.8+) computes the integer square root exactly; check whether its square equals the input. In JS use Math.sqrt and compare to Math.floor.",
        {
            'python': "import math\n"
                      "\n"
                      "def is_perfect_square(n: int) -> bool:\n"
                      "    if n < 0:\n"
                      "        return False\n"
                      "    root = math.isqrt(n)\n"
                      "    return root * root == n\n"
                      "\n"
                      "# Examples:\n"
                      "print(is_perfect_square(16))     # True\n"
                      "print(is_perfect_square(15))     # False\n"
                      "print(is_perfect_square(0))      # True\n"
                      "print(is_perfect_square(-4))     # False",
            'javascript': "function isPerfectSquare(n) {\n"
                          "    if (n < 0) return false;\n"
                          "    const root = Math.floor(Math.sqrt(n));\n"
                          "    return root * root === n;\n"
                          "}\n"
                          "\n"
                          "console.log(isPerfectSquare(16));   // true\n"
                          "console.log(isPerfectSquare(15));   // false",
        },
    ),
    new_task(
        'number_to_words',
        [r'\b(?:convert|write)\b.*\bnumber\b.*\b(?:to\s+)?(?:word|english|text)\s+form\b',
         r'\bnumbers?\s+to\s+words?\b'],
        "Here's a {lang} function that converts a number to its English word form.",
        "The classic implementation chunks the number into thousands groups and handles the teens separately. This version covers 0 to 999,999,999,999.",
        {
            'python': "ONES = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven',\n"
                      "        'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen',\n"
                      "        'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen']\n"
                      "TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy',\n"
                      "        'eighty', 'ninety']\n"
                      "SCALES = ['', 'thousand', 'million', 'billion']\n"
                      "\n"
                      "def _under_1000(n: int) -> str:\n"
                      "    out = []\n"
                      "    if n >= 100:\n"
                      "        out.append(f'{ONES[n // 100]} hundred')\n"
                      "        n %= 100\n"
                      "    if n >= 20:\n"
                      "        out.append(TENS[n // 10])\n"
                      "        n %= 10\n"
                      "        if n:\n"
                      "            out[-1] += '-' + ONES[n]\n"
                      "    elif n:\n"
                      "        out.append(ONES[n])\n"
                      "    return ' '.join(out)\n"
                      "\n"
                      "def number_to_words(n: int) -> str:\n"
                      "    if n == 0:\n"
                      "        return 'zero'\n"
                      "    if n < 0:\n"
                      "        return 'minus ' + number_to_words(-n)\n"
                      "    parts = []\n"
                      "    scale = 0\n"
                      "    while n:\n"
                      "        chunk = n % 1000\n"
                      "        if chunk:\n"
                      "            head = _under_1000(chunk)\n"
                      "            parts.append(f'{head} {SCALES[scale]}'.strip())\n"
                      "        n //= 1000\n"
                      "        scale += 1\n"
                      "    return ' '.join(reversed(parts)).strip()\n"
                      "\n"
                      "# Examples:\n"
                      "print(number_to_words(1234))        # one thousand two hundred thirty-four\n"
                      "print(number_to_words(1_000_001))   # one million one",
        },
    ),
    new_task(
        'calculator_app',
        [r'\b(?:simple\s+)?calculator\b'],
        "Here's a simple calculator in {lang}.",
        "A read-eval-print loop with arithmetic operations is the classic starting point. The dict-of-operations pattern avoids a long if/elif chain.",
        {
            'python': "def calculator():\n"
                      "    \"\"\"Simple REPL calculator: 3 + 4, 10 / 2, quit to exit.\"\"\"\n"
                      "    ops = {\n"
                      "        '+': lambda a, b: a + b,\n"
                      "        '-': lambda a, b: a - b,\n"
                      "        '*': lambda a, b: a * b,\n"
                      "        '/': lambda a, b: a / b if b else float('inf'),\n"
                      "    }\n"
                      "    print('Simple calculator — type \"3 + 4\", \"quit\" to exit')\n"
                      "    while True:\n"
                      "        line = input('> ').strip()\n"
                      "        if line.lower() in ('quit', 'exit', 'q'):\n"
                      "            break\n"
                      "        parts = line.split()\n"
                      "        if len(parts) != 3 or parts[1] not in ops:\n"
                      "            print('usage: <num> <op> <num>')\n"
                      "            continue\n"
                      "        try:\n"
                      "            a, b = float(parts[0]), float(parts[2])\n"
                      "        except ValueError:\n"
                      "            print('numbers only')\n"
                      "            continue\n"
                      "        print(ops[parts[1]](a, b))\n"
                      "\n"
                      "if __name__ == '__main__':\n"
                      "    calculator()",
        },
    ),
    new_task(
        'mask_credit_card',
        [r'\bmask\b.*\bcredit\s+card\b',
         r'\bmask\b.*\b(?:card\s+)?numbers?\b.*\bstring\b'],
        "Here's a {lang} function that masks credit card numbers in a string.",
        "A regex keeps the last four digits and replaces the rest. The callback form lets you preserve the digits-only check instead of matching raw text.",
        {
            'python': "import re\n"
                      "\n"
                      "def mask_credit_cards(text: str) -> str:\n"
                      "    \"\"\"Replace 12-19 digit card numbers with '************' + last 4.\"\"\"\n"
                      "    return re.sub(r'\\b(\\d{4}[ -]?\\d{4}[ -]?\\d{4}[ -]?(?:\\d{4})?)\\b',\n"
                      "                  lambda m: '*' * 12 + re.sub(r'\\D', '', m.group(1))[-4:],\n"
                      "                  text)\n"
                      "\n"
                      "# Simpler: mask a single card string:\n"
                      "def mask_card(card: str) -> str:\n"
                      "    digits = re.sub(r'\\D', '', card)\n"
                      "    return '**** **** **** ' + digits[-4:]\n"
                      "\n"
                      "print(mask_card('4539 1488 0343 6467'))  # **** **** **** 6467\n"
                      "print(mask_credit_cards('my card is 4539-1488-0343-6467 ok'))",
            'javascript': "function maskCreditCards(text) {\n"
                          "    return text.replace(/\\b\\d{4}[ -]?\\d{4}[ -]?\\d{4}[ -]?(?:\\d{4})?\\b/g,\n"
                          "        m => '*'.repeat(12) + m.replace(/\\D/g, '').slice(-4));\n"
                          "}\n"
                          "\n"
                          "function maskCard(card) {\n"
                          "    return '**** **** **** ' + card.replace(/\\D/g, '').slice(-4);\n"
                          "}\n"
                          "\n"
                          "console.log(maskCard('4539 1488 0343 6467'));  // **** **** **** 6467",
        },
    ),
    new_task(
        'extract_hashtags',
        [r'\bhashtags?\b',
         r'\bextract\b.*\b(?:tags?|hashtags?)\b.*\b(?:tweet|text|string)\b'],
        "Here's a {lang} function that extracts hashtags from a tweet.",
        "A regex matching # followed by word characters is the standard approach; the word-boundary lookahead avoids matching # inside URLs or trailing punctuation.",
        {
            'python': "import re\n"
                      "\n"
                      "def extract_hashtags(text: str) -> list:\n"
                      "    \"\"\"All #hashtags in a tweet, without the #.\"\"\"\n"
                      "    return re.findall(r'#(\\w+)', text)\n"
                      "\n"
                      "# Example:\n"
                      "tweet = 'Loving #python and #programming today! #100DaysOfCode'\n"
                      "print(extract_hashtags(tweet))\n"
                      "# ['python', 'programming', '100DaysOfCode']\n"
                      "\n"
                      "# With the # included:\n"
                      "print(re.findall(r'#\\w+', tweet))\n"
                      "\n"
                      "# Count hashtags:\n"
                      "print(len(extract_hashtags(tweet)))   # 3",
            'javascript': "function extractHashtags(text) {\n"
                          "    return (text.match(/#\\w+/g) || []).map(h => h.slice(1));\n"
                          "}\n"
                          "\n"
                          "const tweet = 'Loving #python and #programming today! #100DaysOfCode';\n"
                          "console.log(extractHashtags(tweet));\n"
                          "// ['python', 'programming', '100DaysOfCode']",
        },
    ),
    new_task(
        'tic_tac_toe',
        [r'\btic\s*tac\s*toe\b'],
        "Here's a text-based tic-tac-toe game in {lang}.",
        "A board of 9 cells, a turn loop, and a win check across rows/columns/diagonals. The winning lines are precomputed so the check stays short.",
        {
            'python': "def tic_tac_toe():\n"
                      "    board = [' '] * 9\n"
                      "    wins = [(0, 1, 2), (3, 4, 5), (6, 7, 8),\n"
                      "            (0, 3, 6), (1, 4, 7), (2, 5, 8),\n"
                      "            (0, 4, 8), (2, 4, 6)]\n"
                      "\n"
                      "    def show():\n"
                      "        for row in range(3):\n"
                      "            print(' | '.join(board[row*3:row*3+3]))\n"
                      "            if row < 2:\n"
                      "                print('-' * 9)\n"
                      "\n"
                      "    def winner():\n"
                      "        for a, b, c in wins:\n"
                      "            if board[a] != ' ' and board[a] == board[b] == board[c]:\n"
                      "                return board[a]\n"
                      "        return None\n"
                      "\n"
                      "    player = 'X'\n"
                      "    for turn in range(9):\n"
                      "        show()\n"
                      "        move = input(f'Player {player} (1-9): ')\n"
                      "        try:\n"
                      "            i = int(move) - 1\n"
                      "        except ValueError:\n"
                      "            print('enter 1-9')\n"
                      "            continue\n"
                      "        if i < 0 or i > 8 or board[i] != ' ':\n"
                      "            print('invalid move')\n"
                      "            continue\n"
                      "        board[i] = player\n"
                      "        if winner():\n"
                      "            show()\n"
                      "            print(f'Player {player} wins!')\n"
                      "            return\n"
                      "        player = 'O' if player == 'X' else 'X'\n"
                      "    show()\n"
                      "    print('Draw!')\n"
                      "\n"
                      "if __name__ == '__main__':\n"
                      "    tic_tac_toe()",
        },
    ),
    new_task(
        'level_order',
        [r'\blevel\s+order\b',
         r'\b(?:breadth[- ]first|bfs)\b.*\b(?:tree|binary\s+tree)\b'],
        "Here's a {lang} implementation of level-order (breadth-first) traversal of a binary tree.",
        "Use a queue: pop a node, visit it, push its children. Returning a list of levels (lists) is the common LeetCode format.",
        {
            'python': "from collections import deque\n"
                      "\n"
                      "class TreeNode:\n"
                      "    def __init__(self, val=0, left=None, right=None):\n"
                      "        self.val = val\n"
                      "        self.left = left\n"
                      "        self.right = right\n"
                      "\n"
                      "def level_order(root: TreeNode) -> list:\n"
                      "    \"\"\"Return node values grouped by level.\"\"\"\n"
                      "    if not root:\n"
                      "        return []\n"
                      "    result = []\n"
                      "    queue = deque([root])\n"
                      "    while queue:\n"
                      "        level = []\n"
                      "        for _ in range(len(queue)):\n"
                      "            node = queue.popleft()\n"
                      "            level.append(node.val)\n"
                      "            if node.left:\n"
                      "                queue.append(node.left)\n"
                      "            if node.right:\n"
                      "                queue.append(node.right)\n"
                      "        result.append(level)\n"
                      "    return result\n"
                      "\n"
                      "# Example:     1\n"
                      "#            / \\\n"
                      "#           2   3\n"
                      "root = TreeNode(1, TreeNode(2), TreeNode(3))\n"
                      "print(level_order(root))   # [[1], [2, 3]]",
            'javascript': "function levelOrder(root) {\n"
                          "    if (!root) return [];\n"
                          "    const result = [];\n"
                          "    const queue = [root];\n"
                          "    while (queue.length > 0) {\n"
                          "        const level = [];\n"
                          "        const n = queue.length;\n"
                          "        for (let i = 0; i < n; i++) {\n"
                          "            const node = queue.shift();\n"
                          "            level.push(node.val);\n"
                          "            if (node.left) queue.push(node.left);\n"
                          "            if (node.right) queue.push(node.right);\n"
                          "        }\n"
                          "        result.push(level);\n"
                          "    }\n"
                          "    return result;\n"
                          "}",
        },
    ),
]
# second_largest must sort BEFORE largest_number (same file, priority order)
largest_idx = next(i for i, t in enumerate(d13) if t['task'] == 'largest_number')
for t in reversed(new13):
    d13.insert(largest_idx, t)
save('13_python_utils.json', d13)

# ── 14_js_utils.json: new js tasks + pattern fixes ─────────────────────────
d14 = load('14_js_utils.json')
rde = task(d14, 'remove_dom_element')
rde['patterns'] = [
    r'^(?!.*\b(?:array|list)\b).*\bremove\b.*\b(?:element|dom\s+element)\b',
    r'\bdelete\b.*\b(?:dom\s+)?element\b',
]
sc = task(d14, 'string_contains')
sc['patterns'] = [
    r'^(?!.*\b(?:only\s+)?digits?\b).*\b(?:check\s+if\s+)?(?:a\s+|the\s+)?string\s+contains\b',
    r'^(?!.*\b(?:only\s+)?digits?\b).*\bcontains?\b.*\bsubstring\b',
]
d14.append(new_task(
    'array_unshift',
    [r'\b(?:add|insert|prepend)\b.*\b(?:item|element|value)\b.*\b(?:to\s+)?(?:the\s+)?(?:start|beginning)\b.*\b(?:array|list)\b',
     r'\b(?:add|insert)\b.*\bto\s+(?:the\s+)?start\b.*\barray\b'],
    "Here's how to add an item to the start of an array in {lang}.",
    "unshift is O(n) because every element shifts. Python's deque.appendleft is O(1) — use it for queues where you add to the front often.",
    {
        'javascript': "const arr = [2, 3, 4];\n"
                      "\n"
                      "// Add to the start:\n"
                      "arr.unshift(1);\n"
                      "console.log(arr);   // [1, 2, 3, 4]\n"
                      "\n"
                      "// Spread (non-mutating):\n"
                      "const arr2 = [1, ...arr];\n"
                      "\n"
                      "// Multiple items:\n"
                      "arr.unshift(-1, 0);  // [-1, 0, 1, 2, 3, 4]",
        'python': "from collections import deque\n"
                  "\n"
                  "# list.insert(0, x) is O(n):\n"
                  "lst = [2, 3, 4]\n"
                  "lst.insert(0, 1)\n"
                  "print(lst)   # [1, 2, 3, 4]\n"
                  "\n"
                  "# deque.appendleft is O(1):\n"
                  "d = deque([2, 3, 4])\n"
                  "d.appendleft(1)\n"
                  "print(list(d))   # [1, 2, 3, 4]\n"
                  "\n"
                  "# Non-mutating:\n"
                  "lst2 = [1] + lst",
    },
))
d14.append(new_task(
    'string_repeat',
    [r'\bstring\b.*\brepeat\b.*\bn\s+times\b',
     r'\brepeat\b.*\bstring\b.*\b(?:n\s+)?times\b'],
    "Here's how to repeat a string n times in {lang}.",
    "Python's 's' * n and JS's .repeat(n) both allocate the full result once. Beware: multiplication with a float or negative raises in Python.",
    {
        'javascript': "const s = 'ab';\n"
                      "\n"
                      "console.log(s.repeat(3));   // 'ababab'\n"
                      "console.log('='.repeat(20));  // '===================='\n"
                      "console.log('ha'.repeat(2));   // 'haha'\n"
                      "\n"
                      "// repeat(0) gives an empty string:\n"
                      "console.log(s.repeat(0));   // ''",
        'python': "s = 'ab'\n"
                  "\n"
                  "print(s * 3)          # 'ababab'\n"
                  "print('=' * 20)       # '===================='\n"
                  "print('ha' * 2)       # 'haha'\n"
                  "\n"
                  "# Only integers are allowed:\n"
                  "try:\n"
                  "    print(s * 2.5)\n"
                  "except TypeError as exc:\n"
                  "    print('need an integer:', exc)\n"
                  "\n"
                  "# Joining a list of the same string:\n"
                  "print('ab' * 3)",
    },
))
d14.append(new_task(
    'object_to_array',
    [r'\bobject\b.*\b(?:to\s+)?array\s+of\s+values\b',
     r'\b(?:get|convert|turn)\b.*\bvalues?\b.*\bobject\b.*\b(?:array|list)\b'],
    "Here's how to get an object's values as an array in {lang}.",
    "Object.values returns own enumerable values in insertion order. Object.entries gives [key, value] pairs; Object.keys the keys.",
    {
        'javascript': "const obj = { a: 1, b: 2, c: 3 };\n"
                      "\n"
                      "// Values:\n"
                      "console.log(Object.values(obj));   // [1, 2, 3]\n"
                      "\n"
                      "// Keys:\n"
                      "console.log(Object.keys(obj));     // ['a', 'b', 'c']\n"
                      "\n"
                      "// Entries (key-value pairs):\n"
                      "console.log(Object.entries(obj));  // [['a', 1], ['b', 2], ['c', 3]]\n"
                      "\n"
                      "// Sum the values:\n"
                      "console.log(Object.values(obj).reduce((a, b) => a + b, 0));  // 6",
        'python': "d = {'a': 1, 'b': 2, 'c': 3}\n"
                  "\n"
                  "print(list(d.values()))    # [1, 2, 3]\n"
                  "print(list(d.keys()))      # ['a', 'b', 'c']\n"
                  "print(list(d.items()))     # [('a', 1), ('b', 2), ('c', 3)]\n"
                  "\n"
                  "# Sum the values:\n"
                  "print(sum(d.values()))     # 6",
    },
))
# current_date also answers \"current year\"
cd = task(d14, 'current_date')
cd['patterns'].append(r'\bcurrent\s+year\b')
save('14_js_utils.json', d14)

# ── 18_devops.json: bash extract quotes / rename files ─────────────────────
d18 = load('18_devops.json')
d18.append(new_task(
    'bash_extract_quotes',
    [r'\bextract\b.*\b(?:text|string|content)\b.*\b(?:between|inside|within)\b.*\bquotes?\b',
     r'\bquoted\s+text\b'],
    "Here's how to extract text between quotes in {lang}.",
    "sed's capture group is the classic one-liner. grep -o prints only the matched part. In Python, a regex findall with a capture group returns just the quoted text.",
    {
        'bash': "# Extract the FIRST quoted string (sed):\n"
                "echo 'say \"hello world\" now' | sed -n 's/.*\"\\([^\"]*\\)\".*/\\1/p'\n"
                "# hello world\n"
                "\n"
                "# Extract ALL quoted strings (grep -o):\n"
                "echo 'a \"one\" b \"two\"' | grep -o '\"[^\"]*\"'\n"
                "# \"one\"\n"
                "# \"two\"\n"
                "\n"
                "# Single quotes:\n"
                "echo \"it's 'fine' really\" | grep -o \"'[^']*'\"\n"
                "\n"
                "# From a file:\n"
                "grep -o '\"[^\"]*\"' file.txt",
        'python': "import re\n"
                  "\n"
                  "text = 'say \"hello world\" now and \"bye\"'\n"
                  "\n"
                  "# All quoted strings (without the quotes):\n"
                  "print(re.findall(r'\"([^\"]*)\"', text))\n"
                  "# ['hello world', 'bye']\n"
                  "\n"
                  "# With the quotes:\n"
                  "print(re.findall(r'\"[^\"]*\"', text))\n"
                  "\n"
                  "# First match only:\n"
                  "m = re.search(r'\"([^\"]*)\"', text)\n"
                  "print(m.group(1) if m else None)   # hello world",
    },
    default_lang='bash',
))
d18.append(new_task(
    'bash_rename_files',
    [r'\brename\b.*\bfiles?\b.*\b(?:extension|\.\w+)\b',
     r'\brename\s+(?:all\s+)?\w+\s+files?\s+to\b'],
    "Here's how to rename files (e.g. .txt → .md) in {lang}.",
    "The for-loop with parameter expansion ${f%.txt} strips the extension cleanly. Use rename(1) (the Perl tool) for complex renames, or mv for single files.",
    {
        'bash': "# Rename all .txt files to .md (bash loop):\n"
                "for f in *.txt; do\n"
                "    mv -- \"$f\" \"${f%.txt}.md\"\n"
                "done\n"
                "\n"
                "# Dry run first (echo instead of mv):\n"
                "for f in *.txt; do echo \"$f -> ${f%.txt}.md\"; done\n"
                "\n"
                "# With the rename utility (Perl rename):\n"
                "rename 's/\\.txt$/.md/' *.txt\n"
                "\n"
                "# Prefix every file:\n"
                "for f in *.jpg; do mv -- \"$f\" \"backup-$f\"; done\n"
                "\n"
                "# Recursive:\n"
                "find . -name '*.txt' -exec bash -c 'mv \"$1\" \"${1%.txt}.md\"' _ {} \\;",
        'python': "from pathlib import Path\n"
                  "\n"
                  "# Rename every .txt file to .md in the current directory:\n"
                  "for path in Path('.').glob('*.txt'):\n"
                  "    path.rename(path.with_suffix('.md'))\n"
                  "\n"
                  "# With a log:\n"
                  "for path in Path('.').glob('*.txt'):\n"
                  "    new = path.with_suffix('.md')\n"
                  "    print(f'{path} -> {new}')\n"
                  "    path.rename(new)",
    },
    default_lang='bash',
))
save('18_devops.json', d18)

print('done')
