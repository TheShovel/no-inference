#!/usr/bin/env python3
"""Round 7: probe3 fixes — new tasks + hijack guards."""
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


# ── 02_algorithms: quicksort/merge-sort keep their algorithm meaning ────────
d02 = load('02_algorithms.json')
sl = task(d02, 'sort_list')
sl['patterns'] = [
    r'\bsort\s+(?:a\s+)?(?:list|array|slice|vector)\b',
    r'\bsort\s+(?:the\s+)?(?:list|array|slice)\s+(?:in|by)\b',
    r'\bsorting\s+(?:a\s+)?(?:list|array|slice)\b',
    r'^(?!.*\b(?:implement|write|code|build|create)\b).*\bquicksort\b',
    r'^(?!.*\b(?:implement|write|code|build|create)\b).*\bmerge\s+sort\b',
    r'\bbubble\s+sort\b',
    r'\bselection\s+sort\b',
    r'\binsertion\s+sort\b',
    r'\bsort\s+(?:a\s+|the\s+|this\s+)?(?:list|array|slice|vector)\s+(?:in\s+)?(?:descending|reverse)\b',
    r'\b(?:descending|reverse)\s+order\b.*\bsort\b',
]
save('02_algorithms.json', d02)

# ── 04_basics: env_vars must not swallow docker ENV questions ───────────────
d04 = load('04_basics.json')
ev = task(d04, 'env_vars')
ev['patterns'] = [
    r'^(?!.*\bdocker\b).*\benvironment\s+variable\b',
    r'^(?!.*\bdocker\b).*\benv\s+var\b',
    r'^(?!.*\bdocker\b).*\b(?:read|get|access|set)\b.*\b(?:env|environment)\b.*\b(?:var|variable)\b',
]
save('04_basics.json', d04)

# ── 05_sysadmin: pip version + thread pool ──────────────────────────────────
d05 = load('05_sysadmin.json')
pi = task(d05, 'pip_install')
if 'pip install package==1.2.3' not in pi['languages']['bash']:
    pi['languages']['bash'] += '''

# Install a specific version:
pip install requests==2.31.0

# Version range:
pip install 'requests>=2.28,<3'

# Upgrade an existing package:
pip install --upgrade requests'''
save('05_sysadmin.json', d05)

# ── 07_regex: ipv4 phrasing ────────────────────────────────────────────────
d07 = load('07_regex.json')
ri = task(d07, 'regex_ip')
ri['patterns'] = [
    r'\b(?:regex|regexp|regular\s+expression)\b.*\b(?:ip|ipv4|ip\s+address)\b',
    r'\b(?:validate|check|match|extract)\b.*\b(?:ipv4|ip)\s+address\b',
    r'\b(?:validate|check|match)\b.*\bvalid\s+(?:ipv4|ip)\s+address\b',
    r'\bip\s+(?:address\s+)?(?:regex|validation|validator)\b',
]
save('07_regex.json', d07)

# ── 08_file_io: read_json csv lookahead, list_files rglob ──────────────────
d08 = load('08_file_io.json')
rj = task(d08, 'read_json')
rj['patterns'] = [
    r'\b(?:read|parse|load)\s+(?:a\s+)?json\s+file\b',
    r'\bparse\s+json\b',
    r'\bjson\s+parser\b',
    r'\bconvert\s+json\s+to\b(?!\s+csv\b)',
]
lf = task(d08, 'list_files')
lf['languages']['python'] += '''

# Recursive search by extension (pathlib):
from pathlib import Path
for path in Path('.').rglob('*.txt'):
    print(path)'''
save('08_file_io.json', d08)

# ── 08 zip_folder: exclude gzip ────────────────────────────────────────────
zf = task(d08, 'zip_folder')
zf['patterns'] = [
    r'^(?!.*\b(?:extract|unzip|decompress|gzip)\b).*\b(?:zip|compress|archive)\b.*\b(?:folder|directory|files?)\b(?!.*\btar\b)',
    r'\b(?:create|make)\s+(?:a\s+)?zip\b',
]
save('08_file_io.json', d08)

# ── 13_python_utils: new tasks ─────────────────────────────────────────────
d13 = load('13_python_utils.json')
new13 = [
    new_task(
        'postgres_connect',
        [r'\bpostgres\b.*\b(?:connect|connection|database|python)\b',
         r'\b(?:connect|connection)\b.*\bpostgres\b'],
        "Here's how to connect to a PostgreSQL database in {lang}.",
        "psycopg2 (or psycopg 3) is the standard driver. Use a connection string or keyword args, always close the connection (context manager), and prefer parameterized queries.",
        {
            'python': "import psycopg2\n\n# Connect with keyword args:\nconn = psycopg2.connect(\n    host='localhost',\n    port=5432,\n    dbname='mydb',\n    user='app',\n    password='secret',\n)\n\n# Or with a connection string:\n# conn = psycopg2.connect('postgresql://app:secret@localhost:5432/mydb')\n\n# Query with a cursor:\nwith conn.cursor() as cur:\n    cur.execute('SELECT name FROM users WHERE id = %s', (1,))\n    row = cur.fetchone()\n    print(row)\n\n# Commit after writes:\nwith conn.cursor() as cur:\n    cur.execute(\"INSERT INTO users (name) VALUES (%s)\", ('alice',))\nconn.commit()\n\n# Close (or use 'with psycopg2.connect(...) as conn:')\nconn.close()",
            'javascript': "// node-postgres:\nconst { Client } = require('pg');\n\nconst client = new Client({\n    host: 'localhost',\n    port: 5432,\n    database: 'mydb',\n    user: 'app',\n    password: 'secret',\n});\n\nasync function main() {\n    await client.connect();\n    const res = await client.query('SELECT name FROM users WHERE id = $1', [1]);\n    console.log(res.rows);\n    await client.end();\n}\n\nmain().catch(console.error);",
        },
    ),
    new_task(
        'yaml_read',
        [r'\b(?:read|parse|load)\b.*\byaml\b',
         r'\byaml\b.*\b(?:file|parse|load|read)\b'],
        "Here's how to read a YAML file in {lang}.",
        "PyYAML's safe_load is the recommended entry point (yaml.load with a Loader is unsafe). For complex documents, yaml.safe_load_all handles multi-document files.",
        {
            'python': "# pip install pyyaml\nimport yaml\n\nwith open('config.yaml', encoding='utf-8') as f:\n    config = yaml.safe_load(f)\n\nprint(config.get('name'))\n\n# From a string:\nconfig2 = yaml.safe_load('name: demo\\nport: 8000')\n\n# Multi-document files:\nwith open('docs.yaml', encoding='utf-8') as f:\n    docs = list(yaml.safe_load_all(f))\n\n# Dump back to YAML:\nprint(yaml.safe_dump(config, sort_keys=False))",
            'javascript': "// npm install yaml\nconst YAML = require('yaml');\nconst fs = require('fs');\n\nconst text = fs.readFileSync('config.yaml', 'utf8');\nconst config = YAML.parse(text);\nconsole.log(config.name);\n\n// From a string:\nconst cfg2 = YAML.parse('name: demo\\nport: 8000');\n\n// Stringify:\nconsole.log(YAML.stringify(config));",
        },
    ),
    new_task(
        'excel_read',
        [r'\bexcel\b',
         r'\bxlsx\b'],
        "Here's how to read an Excel file in {lang}.",
        "openpyxl reads .xlsx (no Excel installed needed); pandas.read_excel is the quick path to a DataFrame. For legacy .xls files use xlrd.",
        {
            'python': "# pip install openpyxl\nfrom openpyxl import load_workbook\n\nwb = load_workbook('data.xlsx')\nws = wb.active            # or wb['Sheet1']\n\n# Iterate rows:\nfor row in ws.iter_rows(values_only=True):\n    print(row)\n\n# Cell access:\nprint(ws['A1'].value)\n\n# With pandas (pip install pandas openpyxl):\nimport pandas as pd\ndf = pd.read_excel('data.xlsx', sheet_name='Sheet1')\nprint(df.head())",
        },
    ),
    new_task(
        'json_to_csv',
        [r'\bjson\b.*\bcsv\b',
         r'\bconvert\b.*\b(?:json|data)\b.*\bto\b.*\bcsv\b'],
        "Here's how to convert JSON to CSV in {lang}.",
        "DictWriter with fieldnames handles the header row; flatten nested objects first since CSV is flat. For arrays of objects this is a clean one-pass write.",
        {
            'python': "import csv\nimport json\n\n# data.json: [{\"name\": \"alice\", \"age\": 30}, ...]\nwith open('data.json', encoding='utf-8') as f:\n    records = json.load(f)\n\nif records:\n    fieldnames = list(records[0].keys())\n    with open('out.csv', 'w', newline='', encoding='utf-8') as f:\n        writer = csv.DictWriter(f, fieldnames=fieldnames)\n        writer.writeheader()\n        writer.writerows(records)\n\n# From a JSON string:\nrecords = json.loads(json_text)\n\n# Nested objects need flattening first:\ndef flatten(record):\n    out = {}\n    for k, v in record.items():\n        if isinstance(v, dict):\n            for k2, v2 in v.items():\n                out[f'{k}_{k2}'] = v2\n        else:\n            out[k] = v\n    return out",
            'javascript': "const records = [\n    { name: 'alice', age: 30 },\n    { name: 'bob', age: 25 },\n];\n\nfunction toCsv(rows) {\n    if (rows.length === 0) return '';\n    const headers = Object.keys(rows[0]);\n    const escape = v => `\"${String(v).replace(/\"/g, '\"\"')}\"`;\n    return [\n        headers.join(','),\n        ...rows.map(r => headers.map(h => escape(r[h])).join(',')),\n    ].join('\\n');\n}\n\nconsole.log(toCsv(records));\n// name,age\n// \"alice\",30\n// \"bob\",25",
        },
    ),
    new_task(
        'merge_csv',
        [r'\bmerge\b.*\bcsv\b'],
        "Here's how to merge two CSV files in {lang}.",
        "If both files have the same columns, concatenate the rows. If they share a key column, join them. pandas makes both cases one-liners.",
        {
            'python': "import csv\n\n# Same columns — concatenate:\nwith open('a.csv', newline='', encoding='utf-8') as fa, \\\n     open('b.csv', newline='', encoding='utf-8') as fb, \\\n     open('merged.csv', 'w', newline='', encoding='utf-8') as out:\n    reader_a, reader_b = csv.reader(fa), csv.reader(fb)\n    header = next(reader_a)\n    next(reader_b)  # skip b's header\n    writer = csv.writer(out)\n    writer.writerow(header)\n    writer.writerows(reader_a)\n    writer.writerows(reader_b)\n\n# With pandas (pip install pandas):\nimport pandas as pd\n\ndf_a = pd.read_csv('a.csv')\ndf_b = pd.read_csv('b.csv')\n\n# Concatenate:\nmerged = pd.concat([df_a, df_b], ignore_index=True)\n\n# Join on a key column:\njoined = df_a.merge(df_b, on='user_id', how='left')\n\nmerged.to_csv('merged.csv', index=False)",
        },
    ),
    new_task(
        'gzip_compress',
        [r'\bgzip\b',
         r'\bcompress\b.*\b(?:file|string|data)\b.*\b(?:gzip|gz)\b'],
        "Here's how to compress a file with gzip in {lang}.",
        "gzip.open writes compressed data with the same file-like API as open. For a string, gzip.compress/decompress work on bytes.",
        {
            'python': "import gzip\nimport shutil\n\n# Compress a file:\nwith open('data.txt', 'rb') as f_in, gzip.open('data.txt.gz', 'wb') as f_out:\n    shutil.copyfileobj(f_in, f_out)\n\n# Decompress:\nwith gzip.open('data.txt.gz', 'rb') as f:\n    content = f.read()\n\n# Compress a string:\ntext = 'hello world' * 100\ntext_bytes = text.encode('utf-8')\ncompressed = gzip.compress(text_bytes)\nprint(len(compressed), 'vs', len(text_bytes))\nprint(gzip.decompress(compressed) == text_bytes)   # True",
            'javascript': "// Node.js zlib:\nconst zlib = require('zlib');\nconst fs = require('fs');\n\n// Compress a string:\nconst text = 'hello world'.repeat(100);\nconst compressed = zlib.gzipSync(text);\nconsole.log(compressed.length, 'vs', text.length);\nconsole.log(zlib.gunzipSync(compressed).toString() === text);\n\n// Compress a file:\nconst data = fs.readFileSync('data.txt');\nfs.writeFileSync('data.txt.gz', zlib.gzipSync(data));",
        },
    ),
    new_task(
        'copy_tree',
        [r'\bcopy\b.*\b(?:directory|folder|tree)\b',
         r'\b(?:recursive\w*)?\s*copy\b.*\b(?:dir|folder|directory)\b'],
        "Here's how to copy a directory tree in {lang}.",
        "shutil.copytree copies recursively and creates the destination. dirs_exist_ok=True (Python 3.8+) allows copying into an existing directory. Use ignore= to skip junk.",
        {
            'python': "import shutil\n\n# Copy a directory tree:\nshutil.copytree('src', 'dst')\n\n# Into an existing destination:\nshutil.copytree('src', 'dst', dirs_exist_ok=True)\n\n# Skip junk:\nshutil.copytree(\n    'src', 'dst',\n    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git'),\n)\n\n# Copy with symlinks preserved:\nshutil.copytree('src', 'dst', symlinks=True)",
        },
    ),
    new_task(
        'file_size',
        [r'\b(?:check|get|find|see)\b.*\b(?:size|how\\s+big)\\b.*\b(?:of\\s+)?(?:a\\s+)?file\\b',
         r'\bhow\\s+big\\s+is\\b.*\bfile\b'],
        "Here's how to check the size of a file in {lang}.",
        "os.path.getsize returns bytes; Path.stat().st_size is the pathlib equivalent. For human-readable output, divide by 1024 repeatedly or use a helper.",
        {
            'python': "import os\nfrom pathlib import Path\n\n# Bytes:\nsize = os.path.getsize('data.txt')\nprint(size)\n\n# pathlib:\nprint(Path('data.txt').stat().st_size)\n\n# Human readable:\ndef human_size(num_bytes: int) -> str:\n    for unit in ('B', 'KiB', 'MiB', 'GiB'):\n        if abs(num_bytes) < 1024 or unit == 'GiB':\n            return f'{num_bytes:.1f} {unit}'\n        num_bytes /= 1024\n\nprint(human_size(size))",
            'javascript': "const fs = require('fs');\n\nconst size = fs.statSync('data.txt').size;\nconsole.log(size);   // bytes\n\n// Human readable:\nfunction humanSize(bytes) {\n    const units = ['B', 'KiB', 'MiB', 'GiB'];\n    let i = 0;\n    while (bytes >= 1024 && i < units.length - 1) {\n        bytes /= 1024;\n        i++;\n    }\n    return `${bytes.toFixed(1)} ${units[i]}`;\n}\n\nconsole.log(humanSize(size));",
        },
    ),
    new_task(
        'prefix_rename',
        [r'\brename\b.*\bfiles?\b.*\b(?:prefix|add\\s+prefix)\\b'],
        "Here's how to rename files by adding a prefix in {lang}.",
        "A simple loop with os.rename (or Path.rename) prepends the prefix. Dry-run with print first to avoid surprises.",
        {
            'python': "from pathlib import Path\n\nprefix = 'backup-'\n\n# Add a prefix to every .jpg:\nfor path in Path('.').glob('*.jpg'):\n    new_name = path.with_name(prefix + path.name)\n    print(f'{path} -> {new_name}')\n    path.rename(new_name)\n\n# With os.rename:\nimport os\nfor name in os.listdir('.'):\n    if name.endswith('.jpg'):\n        os.rename(name, prefix + name)",
        },
    ),
    new_task(
        'quicksort',
        [r'\b(?:implement|write|code|build|create)\b.*\bquicksort\b',
         r'^(?!.*\\bsort\\s+(?:a\\s+)?(?:list|array)).*\\bquicksort\\s+function\\b'],
        "Here's a {lang} implementation of quicksort.",
        "Pick a pivot, partition into smaller/equal/larger, recurse. The in-place Lomuto partition is the classic interview version; the list-comprehension version is easiest to read.",
        {
            'python': "def quicksort(items: list) -> list:\n    \"\"\"Return a new sorted list (readable, not in-place).\"\"\"\n    if len(items) <= 1:\n        return items\n    pivot = items[len(items) // 2]\n    left = [x for x in items if x < pivot]\n    mid = [x for x in items if x == pivot]\n    right = [x for x in items if x > pivot]\n    return quicksort(left) + mid + quicksort(right)\n\n# In-place Lomuto partition:\ndef quicksort_inplace(items, lo=0, hi=None):\n    if hi is None:\n        hi = len(items) - 1\n    if lo >= hi:\n        return\n    pivot = items[hi]\n    i = lo\n    for j in range(lo, hi):\n        if items[j] <= pivot:\n            items[i], items[j] = items[j], items[i]\n            i += 1\n    items[i], items[hi] = items[hi], items[i]\n    quicksort_inplace(items, lo, i - 1)\n    quicksort_inplace(items, i + 1, hi)\n\nprint(quicksort([3, 1, 4, 1, 5, 9, 2]))   # [1, 1, 2, 3, 4, 5, 9]",
            'javascript': "function quicksort(items) {\n    if (items.length <= 1) return items;\n    const pivot = items[Math.floor(items.length / 2)];\n    const left = items.filter(x => x < pivot);\n    const mid = items.filter(x => x === pivot);\n    const right = items.filter(x => x > pivot);\n    return [...quicksort(left), ...mid, ...quicksort(right)];\n}\n\nconsole.log(quicksort([3, 1, 4, 1, 5, 9, 2]));  // [1, 1, 2, 3, 4, 5, 9]",
        },
    ),
    new_task(
        'merge_sort',
        [r'\b(?:implement|write|code|build|create)\b.*\bmerge\\s+sort\b',
         r'\bmerge\\s+sort\\s+(?:function|algorithm|implementation)\\b'],
        "Here's a {lang} implementation of merge sort.",
        "Divide the array in half, sort each half recursively, then merge the two sorted halves in O(n). Guaranteed O(n log n) and stable.",
        {
            'python': "def merge_sort(items: list) -> list:\n    if len(items) <= 1:\n        return items\n    mid = len(items) // 2\n    left = merge_sort(items[:mid])\n    right = merge_sort(items[mid:])\n    # merge two sorted halves\n    out = []\n    i = j = 0\n    while i < len(left) and j < len(right):\n        if left[i] <= right[j]:\n            out.append(left[i]); i += 1\n        else:\n            out.append(right[j]); j += 1\n    out.extend(left[i:])\n    out.extend(right[j:])\n    return out\n\nprint(merge_sort([3, 1, 4, 1, 5, 9, 2]))   # [1, 1, 2, 3, 4, 5, 9]",
            'javascript': "function mergeSort(items) {\n    if (items.length <= 1) return items;\n    const mid = Math.floor(items.length / 2);\n    const left = mergeSort(items.slice(0, mid));\n    const right = mergeSort(items.slice(mid));\n    const out = [];\n    let i = 0, j = 0;\n    while (i < left.length && j < right.length) {\n        if (left[i] <= right[j]) out.push(left[i++]);\n        else out.push(right[j++]);\n    }\n    return [...out, ...left.slice(i), ...right.slice(j)];\n}\n\nconsole.log(mergeSort([3, 1, 4, 1, 5, 9, 2]));  // [1, 1, 2, 3, 4, 5, 9]",
        },
    ),
    new_task(
        'pair_sum',
        [r'\bfind\b.*\ball\\s+pairs?\b.*\b(?:sum|add)\\b.*\btarget\b',
         r'\bpairs?\b.*\b(?:sum\\s+to|add\\s+up\\s+to)\\b.*\btarget\b'],
        "Here's a {lang} function that finds all pairs that sum to a target.",
        "The set-based approach tracks complements in one pass — O(n) time. The two-pointer version needs a sorted input and also runs in O(n).",
        {
            'python': "def pair_sum(numbers: list, target: int) -> list:\n    \"\"\"All unique pairs (a, b) with a + b == target.\"\"\"\n    seen = set()\n    pairs = set()\n    for n in numbers:\n        complement = target - n\n        if complement in seen:\n            pairs.add(tuple(sorted((n, complement))))\n        seen.add(n)\n    return [list(p) for p in pairs]\n\n# Two-pointer on a sorted list:\ndef pair_sum_sorted(numbers: list, target: int) -> list:\n    numbers = sorted(numbers)\n    out = []\n    lo, hi = 0, len(numbers) - 1\n    while lo < hi:\n        total = numbers[lo] + numbers[hi]\n        if total == target:\n            out.append([numbers[lo], numbers[hi]])\n            lo += 1\n            hi -= 1\n        elif total < target:\n            lo += 1\n        else:\n            hi -= 1\n    return out\n\nprint(pair_sum([1, 2, 3, 4, 5, 6], 7))   # [[2, 5], [3, 4], [1, 6]]",
            'javascript': "function pairSum(numbers, target) {\n    const seen = new Set();\n    const pairs = new Set();\n    for (const n of numbers) {\n        const complement = target - n;\n        if (seen.has(complement)) {\n            pairs.add(JSON.stringify([Math.min(n, complement), Math.max(n, complement)]));\n        }\n        seen.add(n);\n    }\n    return [...pairs].map(JSON.parse);\n}\n\nconsole.log(pairSum([1, 2, 3, 4, 5, 6], 7));  // [[2,5],[3,4],[1,6]]",
        },
    ),
    new_task(
        'sliding_window_max',
        [r'\bsliding\\s+window\\s+maximum\b',
         r'\b(?:max|maximum)\\s+in\\s+(?:a\\s+)?sliding\\s+window\b'],
        "Here's a {lang} function that computes the sliding window maximum.",
        "A monotonic deque keeps candidate maxima in decreasing order — each element is pushed and popped once, giving O(n) total. This is the classic hard-leetcode pattern.",
        {
            'python': "from collections import deque\n\n\ndef sliding_window_max(nums: list, k: int) -> list:\n    \"\"\"Max of every k-sized window, in O(n).\"\"\"\n    dq = deque()          # indices with decreasing values\n    out = []\n    for i, n in enumerate(nums):\n        while dq and nums[dq[-1]] <= n:\n            dq.pop()      # smaller values can never be the max again\n        dq.append(i)\n        if dq[0] <= i - k:\n            dq.popleft()  # index fell out of the window\n        if i >= k - 1:\n            out.append(nums[dq[0]])\n    return out\n\n# Example:\nprint(sliding_window_max([1, 3, -1, -3, 5, 3, 6, 7], 3))\n# [3, 3, 5, 5, 6, 7]",
            'javascript': "function slidingWindowMax(nums, k) {\n    const dq = [];          // indices with decreasing values\n    const out = [];\n    for (let i = 0; i < nums.length; i++) {\n        while (dq.length && nums[dq[dq.length - 1]] <= nums[i]) {\n            dq.pop();\n        }\n        dq.push(i);\n        if (dq[0] <= i - k) dq.shift();\n        if (i >= k - 1) out.push(nums[dq[0]]);\n    }\n    return out;\n}\n\nconsole.log(slidingWindowMax([1, 3, -1, -3, 5, 3, 6, 7], 3));\n// [3, 3, 5, 5, 6, 7]",
        },
    ),
    new_task(
        'edit_distance',
        [r'\bedit\\s+distance\b',
         r'\blevenshtein\b'],
        "Here's a {lang} function that computes the edit (Levenshtein) distance between two strings.",
        "Classic dynamic programming: dp[i][j] is the cost to transform s[:i] into t[:j]. O(m·n) time and space; the space can be reduced to one row.",
        {
            'python': "def edit_distance(a: str, b: str) -> int:\n    \"\"\"Minimum insertions/deletions/substitutions to turn a into b.\"\"\"\n    m, n = len(a), len(b)\n    dp = [[0] * (n + 1) for _ in range(m + 1)]\n    for i in range(m + 1):\n        dp[i][0] = i\n    for j in range(n + 1):\n        dp[0][j] = j\n    for i in range(1, m + 1):\n        for j in range(1, n + 1):\n            if a[i - 1] == b[j - 1]:\n                dp[i][j] = dp[i - 1][j - 1]\n            else:\n                dp[i][j] = 1 + min(dp[i - 1][j],      # delete\n                                   dp[i][j - 1],      # insert\n                                   dp[i - 1][j - 1])  # substitute\n    return dp[m][n]\n\nprint(edit_distance('kitten', 'sitting'))   # 3\nprint(edit_distance('flaw', 'lawn'))        # 2",
            'javascript': "function editDistance(a, b) {\n    const m = a.length, n = b.length;\n    const dp = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));\n    for (let i = 0; i <= m; i++) dp[i][0] = i;\n    for (let j = 0; j <= n; j++) dp[0][j] = j;\n    for (let i = 1; i <= m; i++) {\n        for (let j = 1; j <= n; j++) {\n            if (a[i - 1] === b[j - 1]) dp[i][j] = dp[i - 1][j - 1];\n            else dp[i][j] = 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);\n        }\n    }\n    return dp[m][n];\n}\n\nconsole.log(editDistance('kitten', 'sitting'));  // 3",
        },
    ),
    new_task(
        'bloom_filter',
        [r'\bbloom\\s+filter\b'],
        "Here's a {lang} bloom filter.",
        "A bloom filter answers 'definitely not present' vs 'maybe present' using k hash functions over a bit array. Python's built-in hash() is salted per process — use hashlib for stable hashes.",
        {
            'python': "import hashlib\n\n\nclass BloomFilter:\n    def __init__(self, size: int = 1024, num_hashes: int = 3):\n        self.size = size\n        self.num_hashes = num_hashes\n        self.bits = bytearray(size)\n\n    def _hashes(self, item: str):\n        out = []\n        for i in range(self.num_hashes):\n            digest = hashlib.sha256(f'{i}:{item}'.encode()).digest()\n            out.append(int.from_bytes(digest[:4], 'big') % self.size)\n        return out\n\n    def add(self, item: str) -> None:\n        for h in self._hashes(item):\n            self.bits[h] = 1\n\n    def __contains__(self, item: str) -> bool:\n        return all(self.bits[h] for h in self._hashes(item))\n\n# Example:\nbf = BloomFilter()\nbf.add('apple')\nprint('apple' in bf)      # True (maybe)\nprint('banana' in bf)     # False (definitely not)",
            'javascript': "// Node.js crypto for stable hashes:\nconst crypto = require('crypto');\n\nclass BloomFilter {\n    constructor(size = 1024, numHashes = 3) {\n        this.size = size;\n        this.numHashes = numHashes;\n        this.bits = new Uint8Array(size);\n    }\n\n    _hashes(item) {\n        const out = [];\n        for (let i = 0; i < this.numHashes; i++) {\n            const digest = crypto.createHash('sha256')\n                .update(`${i}:${item}`).digest();\n            out.push(digest.readUInt32BE(0) % this.size);\n        }\n        return out;\n    }\n\n    add(item) {\n        for (const h of this._hashes(item)) this.bits[h] = 1;\n    }\n\n    has(item) {\n        return this._hashes(item).every(h => this.bits[h] === 1);\n    }\n}",
        },
    ),
    new_task(
        'thread_pool',
        [r'\bthread\\s*pool\b',
         r'\b(?:concurrent|parallel)\\b.*\\b(?:tasks?|workers?|calls?)\\b.*\\b(?:python|thread)\\b'],
        "Here's how to use a thread pool in {lang}.",
        "ThreadPoolExecutor maps work across a pool of threads — great for I/O-bound tasks (network, disk). For CPU-bound work use ProcessPoolExecutor instead (GIL).",
        {
            'python': "from concurrent.futures import ThreadPoolExecutor\n\n\ndef fetch(url: str) -> str:\n    # I/O-bound work (network, disk) benefits from threads\n    return f'data from {url}'\n\nurls = ['https://a.com', 'https://b.com', 'https://c.com']\n\n# Map: run fetch on every url, results in order:\nwith ThreadPoolExecutor(max_workers=4) as pool:\n    results = list(pool.map(fetch, urls))\nprint(results)\n\n# Submit individual tasks:\nwith ThreadPoolExecutor(max_workers=4) as pool:\n    futures = [pool.submit(fetch, u) for u in urls]\n    for fut in futures:\n        print(fut.result())\n\n# CPU-bound work:\nfrom concurrent.futures import ProcessPoolExecutor\nwith ProcessPoolExecutor() as pool:\n    results = list(pool.map(sum, [[i] * 10_000 for i in range(4)]))",
        },
    ),
    new_task(
        'profile_code',
        [r'\bprofile\\b.*\\bpython\\s+code\\b',
         r'\bcProfile\\b',
         r'\b(?:find|measure)\\b.*\\b(?:slow|bottleneck)\\b.*\\b(?:code|function)\\b'],
        "Here's how to profile Python code.",
        "cProfile is the stdlib profiler; pstats summarizes the output. For a single function, timeit is simpler. Line-by-line detail needs the external line_profiler.",
        {
            'python': "import cProfile\nimport pstats\n\n# Profile a script:\ncProfile.run('my_function()', 'profile.out')\n\n# Or from the command line:\n#   python -m cProfile my_script.py\n\n# Summarize:\np = pstats.Stats('profile.out')\np.sort_stats('cumulative').print_stats(20)   # top 20 by cumulative time\n\n# Time a single function:\nimport timeit\nt = timeit.timeit('my_function()', globals=globals(), number=1000)\nprint(f'1 call: {t / 1000 * 1e6:.2f} us')\n\n# Timing helper:\nimport time\ndef timed(fn):\n    start = time.perf_counter()\n    result = fn()\n    print(f'{fn.__name__}: {time.perf_counter() - start:.4f}s')\n    return result",
        },
    ),
    new_task(
        'log_decorator',
        [r'\bdecorator\\b.*\\blog\\b',
         r'\b(?:log|logging)\\b.*\\bdecorator\\b'],
        "Here's a {lang} decorator that logs function calls.",
        "The decorator logs the function name, arguments, and return value (or exception). functools.wraps keeps the wrapped function's metadata for introspection.",
        {
            'python': "import functools\nimport logging\n\nlogging.basicConfig(level=logging.INFO)\nlog = logging.getLogger(__name__)\n\n\ndef logged(func):\n    @functools.wraps(func)\n    def wrapper(*args, **kwargs):\n        log.info('calling %s(%s, %s)', func.__name__, args, kwargs)\n        try:\n            result = func(*args, **kwargs)\n        except Exception as exc:\n            log.exception('%s raised %s', func.__name__, exc)\n            raise\n        log.info('%s returned %r', func.__name__, result)\n        return result\n    return wrapper\n\n\n@logged\ndef add(a, b):\n    return a + b\n\nadd(1, 2)\n# INFO:root:calling add((1, 2), {})\n# INFO:root:add returned 3",
        },
    ),
    new_task(
        'logging_setup',
        [r'\blogging\\b',
         r'\bset\\s+up\\s+logging\\b'],
        "Here's how to set up logging in {lang}.",
        "logging.basicConfig is the quick start; the module-level logger pattern (logger = logging.getLogger(__name__)) is the standard for libraries. Levels: DEBUG < INFO < WARNING < ERROR.",
        {
            'python': "import logging\n\n# Quick start — console output:\nlogging.basicConfig(\n    level=logging.INFO,\n    format='%(asctime)s %(levelname)s %(name)s: %(message)s',\n)\n\nlogger = logging.getLogger(__name__)\n\nlogger.debug('detail')        # hidden at INFO level\nlogger.info('started')\nlogger.warning('look out')\nlogger.error('something broke')\n\n# Log to a file too:\nlogging.basicConfig(\n    level=logging.INFO,\n    format='%(asctime)s %(levelname)s %(message)s',\n    handlers=[\n        logging.FileHandler('app.log'),\n        logging.StreamHandler(),\n    ],\n)\n\n# Exception tracebacks:\ntry:\n    1 / 0\nexcept ZeroDivisionError:\n    logger.exception('division failed')",
            'javascript': "// Node.js: console methods map to log levels; use a library (winston, pino)\n// for files/rotation.\nconsole.log('info');\nconsole.warn('warning');\nconsole.error('error');\n\n// Simple leveled logger:\nconst log = {\n    debug: (...a) => console.debug(new Date().toISOString(), ...a),\n    info: (...a) => console.log(new Date().toISOString(), ...a),\n    warn: (...a) => console.warn(new Date().toISOString(), ...a),\n    error: (...a) => console.error(new Date().toISOString(), ...a),\n};\n\nlog.info('started');\nlog.error('something broke');",
        },
    ),
    new_task(
        'chunk_file',
        [r'\bchunk\\b.*\\b(?:large\\s+)?file\\b',
         r'\bsplit\\b.*\\bfile\\b.*\\b(?:parts|chunks)\\b'],
        "Here's how to split a large file into smaller chunks in {lang}.",
        "Read fixed-size byte chunks with a loop (memory-friendly), or split by lines. shutil.copyfileobj accepts a length argument for the same effect.",
        {
            'python': "def split_file(filename: str, chunk_size: int = 1024 * 1024):\n    \"\"\"Split a file into chunk_size-byte parts.\"\"\"\n    with open(filename, 'rb') as f:\n        i = 0\n        while True:\n            chunk = f.read(chunk_size)\n            if not chunk:\n                break\n            with open(f'{filename}.part{i}', 'wb') as out:\n                out.write(chunk)\n            i += 1\n\n# Split by lines (readable chunks):\ndef split_by_lines(filename: str, lines_per_part: int = 1000):\n    with open(filename, encoding='utf-8') as f:\n        part = 0\n        lines = []\n        for line in f:\n            lines.append(line)\n            if len(lines) >= lines_per_part:\n                with open(f'{filename}.part{part}', 'w', encoding='utf-8') as out:\n                    out.writelines(lines)\n                lines = []\n                part += 1\n        if lines:\n            with open(f'{filename}.part{part}', 'w', encoding='utf-8') as out:\n                out.writelines(lines)",
        },
    ),
    new_task(
        'periodic_request',
        [r'\b(?:every|each)\\s+\\d+\\s+seconds?\\b.*\\b(?:request|api|call|fetch)\\b',
         r'\b(?:repeat|run)\\b.*\\b(?:every|each)\\s+\\d+\\s+seconds?\\b'],
        "Here's a {lang} script that calls an API every N seconds.",
        "A loop with time.sleep is the simplest scheduler. Python's schedule library reads nicer; for production batch jobs use cron or a task queue. Always wrap the call in try/except so one failure doesn't kill the loop.",
        {
            'python': "import time\nimport requests\n\nURL = 'https://api.example.com/status'\n\n# Simple loop:\nwhile True:\n    try:\n        resp = requests.get(URL, timeout=10)\n        print(resp.status_code)\n    except requests.RequestException as exc:\n        print('request failed:', exc)\n    time.sleep(10)\n\n# With the schedule library (pip install schedule):\n# import schedule\n# def job():\n#     requests.get(URL, timeout=10)\n# schedule.every(10).seconds.do(job)\n# while True:\n#     schedule.run_pending()\n#     time.sleep(1)",
        },
    ),
    new_task(
        'image_download',
        [r'\bdownload\\b.*\\bimage\\b',
         r'\bsave\\b.*\\bimage\\b.*\\b(?:url|from)\\b'],
        "Here's how to download an image from a URL and save it in {lang}.",
        "Download as bytes and write in binary mode. requests with stream=True avoids loading the whole image into memory; always check the status first.",
        {
            'python': "import requests\n\nurl = 'https://example.com/photo.jpg'\n\n# Simple version:\nresp = requests.get(url, timeout=30)\nresp.raise_for_status()\nwith open('photo.jpg', 'wb') as f:\n    f.write(resp.content)\n\n# Memory-friendly (streamed):\nwith requests.get(url, stream=True, timeout=30) as resp:\n    resp.raise_for_status()\n    with open('photo.jpg', 'wb') as f:\n        for chunk in resp.iter_content(chunk_size=8192):\n            f.write(chunk)\n\n# Verify it's actually an image:\nprint(resp.headers.get('Content-Type'))   # image/jpeg",
            'javascript': "const https = require('https');\nconst fs = require('fs');\n\nconst url = 'https://example.com/photo.jpg';\n\nhttps.get(url, (res) => {\n    if (res.statusCode !== 200) {\n        console.error('HTTP', res.statusCode);\n        res.resume();\n        return;\n    }\n    const file = fs.createWriteStream('photo.jpg');\n    res.pipe(file);\n    file.on('finish', () => file.close());\n}).on('error', err => console.error(err.message));",
        },
    ),
    new_task(
        'docker_env',
        [r'\benvironment\\s+variables?\\b.*\\bdocker\\b',
         r'\bdocker\\b.*\\benvironment\\s+variables?\\b'],
        "Here's how to use environment variables in a Docker container.",
        "ENV sets variables in the image; docker run -e overrides at runtime; --env-file reads many at once. Compose files use the environment: or env_file: keys. Never bake secrets into the image.",
        {
            'bash': "# Dockerfile:\nFROM python:3.12-slim\n# Default values baked into the image:\nENV APP_ENV=production \\\n    PORT=8000\n# Runtime values can override these with -e.\n\n# At runtime (docker run):\n#   docker run -e APP_ENV=development -e API_KEY=secret myapp\n#   docker run --env-file .env myapp\n\n# .env file format:\n#   APP_ENV=development\n#   API_KEY=secret\n\n# docker-compose.yml:\n# services:\n#   web:\n#     build: .\n#     environment:\n#       APP_ENV: development\n#     env_file:\n#       - .env\n\n# Secrets: use Docker secrets or your orchestration tool's secret store,\n# never ENV in a committed Dockerfile.\n\n# Read them from the app (Python):\n#   import os\n#   port = os.getenv('PORT', '8000')",
        },
        default_lang='bash',
    ),
]
for t in new13:
    d13.append(t)
save('13_python_utils.json', d13)

# ── 18_devops: nothing more needed here ─────────────────────────────────────

print('done')
