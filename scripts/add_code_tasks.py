#!/usr/bin/env python3
"""Add new code tasks (data-driven) + fix conflicting patterns.

All edits go through json round-tripping so escaping stays valid. New task
files load after the existing 01-12 files, so they never outrank a matching
existing task; conflicts are resolved by tightening the earlier files'
patterns here (exclude lookaheads, extra phrasings).

Usage: python3 scripts/add_code_tasks.py
"""
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


def task(data, task_id):
    for t in data['tasks']:
        if t['task'] == task_id:
            return t
    raise KeyError(task_id)


# ── 1. Fix conflicting patterns in existing files ─────────────────────────

d03 = load('03_strings.json')
# "reverse a linked list" is a linked-list task, not an array reversal.
ra = task(d03, 'reverse_array')
ra['patterns'] = [
    r'\brevers(?:e|es|ing)\s+(?:an?\s+)?(?:array|slice|vector)\b',
    r'\brevers(?:e|es|ing)\s+(?:the\s+)?(?:array|slice|vector)\b',
    r'\brevers(?:e|es|ing)\s+(?:an?\s+|the\s+)?list\b(?!\s+linked\s+list)',
]
# "reverse words in a sentence" reverses word ORDER, not characters.
rs = task(d03, 'reverse_string')
rs['patterns'] = [
    r'\brevers(?:e|es|ing)\s+(?:a\s+|the\s+)?string\b',
    r'\brevers(?:e|es|ing)\s+(?:the\s+)?(?:characters\s+of\s+)?(?:a\s+)?string\b',
    r'\brevers(?:e|es|ing)\s+word(?:s)?\b(?!\s+in\s+(?:a\s+)?sentence)',
]
save('03_strings.json', d03)

d06 = load('06_data_structures.json')
ll = task(d06, 'linked_list')
ll['patterns'] = [
    r'\breverse\s+(?:a\s+)?linked\s+list\b',
    r'^(?!.*\b(?:cycle|loop|circular)\b).*\blinked\s+list\b',
]
save('06_data_structures.json', d06)

d07 = load('07_regex.json')
re_ = task(d07, 'regex_email')
re_['patterns'] = [
    r'\b(?:validat|check|verif|test)\w*\s+(?:if\s+)?(?:a\s+|an?\s+|the\s+)?(?:string\s+is\s+)?(?:a\s+|an?\s+)?(?:valid\s+)?email(?:\.?\s+address)?\b',
    r'\b(?:check|validate|test)\b.*\bstring\s+is\s+(?:a\s+|an?\s+)?valid\s+email\b',
    r'\bemail\s+(?:validation|validator|regex|regexp)\b',
    r'\bregex\s+(?:to|for)\s+.*\bemail\b',
]
rp = task(d07, 'regex_phone')
rp['patterns'] = [
    r'\b(?:validate|check|verify)\s+(?:a\s+)?phone\s+number\b',
    r'\bregex\b.*\bphone\s+number\b',
    r'\bphone\s+(?:validation|validator|regex|regexp)\b',
    r'\b(?:extract|find|match|pull|grab)\s+(?:all\s+|the\s+)?(?:phone|telephone)\s+numbers?\s+(?:from|in)\b',
    r'\bphone\s+numbers?\s+from\s+text\b',
]
save('07_regex.json', d07)

d08 = load('08_file_io.json')
lf = task(d08, 'list_files')
lf['patterns'] = [
    r'^(?!.*\b(?:bash|shell|zsh)\b).*\b(?:list|get|show)\b.*\b(?:files|directories?|folders?|directory\s+contents)\b',
    r'^(?!.*\b(?:bash|shell|zsh)\b).*\b(?:find|search)\s+(?:all\s+|for\s+)?.*\bfiles?\s+(?:in|with|matching|named)\b',
    r'^(?!.*\b(?:bash|shell|zsh|loop\w*|iterat\w*)\b).*\bfiles?\s+in\s+(?:a\s+|the\s+)?(?:directory|folder)\b',
]
wf = task(d08, 'write_file')
wf['patterns'] = [
    r'\bwrite\s+(?:to\s+)?(?:a\s+)?file\b',
    r'\bwrite\s+(?:a\s+|the\s+)?[a-z\s]*?(?:to\s+)?(?:a\s+|the\s+)?file\b',
    r'\bappend\s+to\s+(?:a\s+)?file\b',
    r'\bcreate\s+(?:a\s+)?file\b',
]
save('08_file_io.json', d08)

d09 = load('09_http.json')
hp = task(d09, 'http_post')
hp['patterns'] = [
    r'\bpost\s+(?:data|json|a\s+request)\b',
    r'\bpost\s+request\b',
    r'\b(?:make|send|do)\s+(?:a\s+)?post\s+request\b',
    r'\bhttp\s+post\b',
    r'\bsend\s+(?:a\s+)?post\b',
    r'\bsubmit\s+(?:a\s+)?form\b',
]
save('09_http.json', d09)

# ── 2. New task files ─────────────────────────────────────────────────────

# Each dict: task, patterns (regex), intro ({lang} placeholder allowed),
# notes (plain text), languages {canonical lang: raw code}.


def task_dict(tid, patterns, intro, notes, languages):
    return {
        'task': tid,
        'patterns': patterns,
        'intro': intro,
        'notes': notes,
        'languages': languages,
    }


# ── 13_python_utils.json ──────────────────────────────────────────────────
d13 = []
d13.append(task_dict(
    'uuid_gen',
    [r'\buuid\b', r'\bguid\b'],
    "Here's how to generate a UUID in {lang}.",
    "uuid4() is the right choice for almost everything: it's random and unique. uuid1() encodes the MAC address and time — don't use it when privacy matters.",
    {
        'python': "import uuid\n\n# Random UUID (v4) — the default choice:\nuid = uuid.uuid4()\nprint(uid)                 # 8f8e... (hex string)\nprint(str(uid))\n\n# UUID from a string:\nparsed = uuid.UUID('12345678-1234-5678-1234-567812345678')\n\n# Short unique id (not a UUID, but handy for filenames):\nimport secrets\nprint(secrets.token_hex(8))",
        'javascript': "// Browser: crypto.randomUUID()\nconst uid = crypto.randomUUID();\nconsole.log(uid);\n\n// Node.js:\nconst { randomUUID } = require('crypto');\nconsole.log(randomUUID());\n\n// Short random id:\nconsole.log(Math.random().toString(36).slice(2));",
    },
))
d13.append(task_dict(
    'hash_string',
    [r'\b(?:md5|sha-?1|sha-?256|sha-?512)\b',
     r'\bhash\b.*\b(?:string|password|text|file|password)\b(?!\s+(?:map|set|table))'],
    "Here's how to hash a string in {lang}.",
    "Use SHA-256 or stronger for checksums. MD5 and SHA-1 are cryptographically broken — never use them for passwords; use a key-derivation function like bcrypt, argon2, or PBKDF2 instead.",
    {
        'python': "import hashlib\n\n# SHA-256 (recommended for checksums):\ntext = 'hello world'\ndigest = hashlib.sha256(text.encode('utf-8')).hexdigest()\nprint(digest)\n\n# MD5 (broken — checksums only):\nprint(hashlib.md5(text.encode()).hexdigest())\n\n# SHA-1 (broken — checksums only):\nprint(hashlib.sha1(text.encode()).hexdigest())\n\n# With a salt, for password storage:\nimport hashlib, os\nsalt = os.urandom(16)\nhashed = hashlib.pbkdf2_hmac('sha256', b'password', salt, 100_000)",
        'javascript': "const crypto = require('crypto');\n\n// SHA-256 (recommended for checksums):\nconst digest = crypto.createHash('sha256')\n    .update('hello world')\n    .digest('hex');\nconsole.log(digest);\n\n// MD5 (broken — checksums only):\nconsole.log(crypto.createHash('md5').update('hello world').digest('hex'));\n\n// Browser:\n// const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode('hello world'));",
    },
))
d13.append(task_dict(
    'base64_codec',
    [r'\bbase64\b', r'\b(?:encode|decode)\b.*\b(?:base64|to\s+base64|from\s+base64)\b'],
    "Here's how to encode and decode base64 in {lang}.",
    "Base64 is an encoding, not encryption — anyone can decode it. It's for putting binary data in text (JSON, emails, URLs). For secrets, use real encryption.",
    {
        'python': "import base64\n\n# Encode:\ntext = 'hello world'\nencoded = base64.b64encode(text.encode('utf-8')).decode('utf-8')\nprint(encoded)   # aGVsbG8gd29ybGQ=\n\n# Decode:\ndecoded = base64.b64decode(encoded).decode('utf-8')\nprint(decoded)   # hello world\n\n# URL-safe variant (no + or /):\nurlsafe = base64.urlsafe_b64encode(text.encode()).decode()\n\n# Binary data:\nimg_b64 = base64.b64encode(open('img.png', 'rb').read())",
        'javascript': "// Encode:\nconst text = 'hello world';\nconst encoded = Buffer.from(text, 'utf8').toString('base64');\nconsole.log(encoded);  // aGVsbG8gd29ybGQ=\n\n// Decode:\nconsole.log(Buffer.from(encoded, 'base64').toString('utf8'));  // hello world\n\n// Browser:\n// const encoded = btoa(text);\n// const decoded = atob(encoded);",
    },
))
d13.append(task_dict(
    'timestamp_to_date',
    [r'\b(?:unix\s+)?timestamp\b.*\b(?:to|convert|readable|date|human)\b',
     r'\b(?:convert|format)\b.*\b(?:unix\s+)?timestamp\b'],
    "Here's how to convert a Unix timestamp to a readable date in {lang}.",
    "A Unix timestamp is seconds since 1970-01-01 UTC. Python's datetime.fromtimestamp() converts to local time; use utcfromtimestamp()/datetime.fromtimestamp(ts, tz=timezone.utc) for UTC.",
    {
        'python': "from datetime import datetime, timezone\n\n# Timestamp (seconds since epoch):\nts = 1710000000\n\n# To local time:\ndt = datetime.fromtimestamp(ts)\nprint(dt)                    # 2024-03-09 16:00:00\n\n# To UTC explicitly:\ndt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)\nprint(dt_utc.isoformat())    # 2024-03-09T16:00:00+00:00\n\n# Format it:\nprint(dt.strftime('%Y-%m-%d %H:%M:%S'))\n\n# Milliseconds (JS-style) -> divide by 1000 first:\ndt_ms = datetime.fromtimestamp(1710000000000 / 1000)",
        'javascript': "// Timestamp (milliseconds in JS!):\nconst ts = 1710000000000;\n\nconst date = new Date(ts);\nconsole.log(date.toISOString());          // 2024-03-09T16:00:00.000Z\nconsole.log(date.toLocaleString());       // local time\nconsole.log(date.toLocaleDateString());   // 3/9/2024\n\n// Seconds (Python-style) -> multiply by 1000:\nconst fromSeconds = new Date(1710000000 * 1000);",
    },
))
d13.append(task_dict(
    'format_date',
    [r'\b(?:format|convert)\b.*\bdate\b.*\b(?:yyyy[-/]?mm[-/]?dd|iso|format|string)\b',
     r'\bdate\b.*\b(?:formatted|formatting)\b'],
    "Here's how to format a date as YYYY-MM-DD in {lang}.",
    "ISO 8601 (YYYY-MM-DD) sorts correctly as a string and is unambiguous across locales — prefer it for storage and APIs.",
    {
        'python': "from datetime import datetime, date\n\n# From a datetime:\nnow = datetime.now()\nprint(now.strftime('%Y-%m-%d'))            # 2026-04-03\n\n# From a date:\ntoday = date.today()\nprint(today.isoformat())                   # 2026-04-03\n\n# With time:\nprint(now.strftime('%Y-%m-%d %H:%M:%S'))   # 2026-04-03 15:30:00\n\n# Parse an ISO string back:\nparsed = datetime.strptime('2026-04-03', '%Y-%m-%d')",
        'javascript': "// Manual zero-padding (most reliable):\nconst d = new Date();\nconst iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;\nconsole.log(iso);\n\n// One-liner via toISOString (UTC, not local):\nconsole.log(new Date().toISOString().slice(0, 10));\n\n// Intl with explicit parts:\nconst parts = new Intl.DateTimeFormat('en-CA', {\n    year: 'numeric', month: '2-digit', day: '2-digit'\n}).formatToParts(d).reduce((acc, p) => (acc[p.type] = p.value, acc), {});\nconsole.log(`${parts.year}-${parts.month}-${parts.day}`);",
    },
))
d13.append(task_dict(
    'timezone_now',
    [r'\btimezone\b', r'\btime\s+zone\b'],
    "Here's how to work with timezones in {lang}.",
    "Store times in UTC and convert to local timezones only when displaying. Python needs zoneinfo (stdlib, 3.9+) — avoid pytz for new code. JS uses IANA names via Intl.",
    {
        'python': "from datetime import datetime, timezone, timedelta\nfrom zoneinfo import ZoneInfo\n\n# Current time in a specific timezone:\nnow_tokyo = datetime.now(ZoneInfo('Asia/Tokyo'))\nprint(now_tokyo)\n\n# Fixed offset:\nutc_plus_5 = datetime.now(timezone(timedelta(hours=5)))\n\n# Convert between zones:\nnow_utc = datetime.now(timezone.utc)\nprint(now_utc.astimezone(ZoneInfo('America/New_York')))\n\n# List all zones:\nimport zoneinfo\nprint(zoneinfo.available_timezones())",
        'javascript': "// Local timezone name and offset:\nconst tz = Intl.DateTimeFormat().resolvedOptions().timeZone;\nconsole.log(tz);                    // e.g. 'America/New_York'\n\n// Time in a specific timezone:\nconsole.log(new Intl.DateTimeFormat('en-US', {\n    timeZone: 'Asia/Tokyo',\n    dateStyle: 'full', timeStyle: 'long'\n}).format(new Date()));\n\n// Offset (minutes) of a zone at a given instant:\nfunction tzOffsetMs(zone, date = new Date()) {\n    const dtf = new Intl.DateTimeFormat('en-US', {\n        timeZone: zone, hour12: false,\n        year: 'numeric', month: '2-digit', day: '2-digit',\n        hour: '2-digit', minute: '2-digit', second: '2-digit',\n    });\n    const parts = Object.fromEntries(dtf.formatToParts(date)\n        .filter(p => p.type !== 'literal').map(p => [p.type, p.value]));\n    const asUTC = Date.UTC(parts.year, parts.month - 1, parts.day,\n                           parts.hour, parts.minute, parts.second);\n    return asUTC - date.getTime();\n}\nconsole.log(tzOffsetMs('Asia/Tokyo'));",
    },
))
d13.append(task_dict(
    'human_file_size',
    [r'\b(?:human\s+readable|humanize|human)\b.*\b(?:file\s+)?size\b',
     r'\b(?:file\s+)?size\b.*\b(?:human|readable)\b'],
    "Here's a {lang} function that formats a byte count as a human-readable size.",
    "Use powers of 1024 (KiB/MiB/GiB) for file sizes on disk; powers of 1000 (KB/MB/GB) for marketing-style numbers. The function below rounds to two decimals and keeps units sensible.",
    {
        'python': "def human_file_size(num_bytes: int) -> str:\n    size = float(num_bytes)\n    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'):\n        if abs(size) < 1024.0 or unit == 'PiB':\n            if unit == 'B':\n                return f'{int(size)} {unit}'\n            return f'{size:.2f} {unit}'\n        size /= 1024.0\n\n# Example:\nprint(human_file_size(0))        # 0 B\nprint(human_file_size(1536))     # 1.50 KiB\nprint(human_file_size(536870912))  # 512.00 MiB",
        'javascript': "function humanFileSize(numBytes) {\n    const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];\n    let size = Math.abs(numBytes);\n    let i = 0;\n    while (size >= 1024 && i < units.length - 1) {\n        size /= 1024;\n        i++;\n    }\n    return `${numBytes < 0 ? '-' : ''}${i === 0 ? size : size.toFixed(2)} ${units[i]}`;\n}\n\nconsole.log(humanFileSize(1536));        // 1.50 KiB\nconsole.log(humanFileSize(536870912));   // 512.00 MiB",
    },
))
d13.append(task_dict(
    'deep_copy',
    [r'\bdeep\s*copy\b'],
    "Here's how to deep-copy an object in {lang}.",
    "A shallow copy shares nested objects; a deep copy duplicates everything. Python's copy.deepcopy handles arbitrary object graphs; JSON round-tripping works only for JSON-safe data.",
    {
        'python': "import copy\n\n# Deep copy (handles nested lists/dicts/objects):\noriginal = {'items': [1, 2, {'x': 3}]}\ndeep = copy.deepcopy(original)\ndeep['items'][2]['x'] = 99\nprint(original['items'][2]['x'])   # 3 (unchanged)\n\n# Shallow copy (nested objects are SHARED):\nshallow = original.copy()\nshallow['items'][2]['x'] = 99\nprint(original['items'][2]['x'])   # 99 (shared!)\n\n# JSON round-trip (only for JSON-safe data):\nimport json\nclone = json.loads(json.dumps(original))",
        'javascript': "// Deep clone (modern, handles most types):\nconst original = { items: [1, 2, { x: 3 }] };\nconst deep = structuredClone(original);\ndeep.items[2].x = 99;\nconsole.log(original.items[2].x);   // 3 (unchanged)\n\n// JSON round-trip (JSON-safe data only):\nconst clone = JSON.parse(JSON.stringify(original));\n\n// Shallow copy (nested objects are SHARED):\nconst shallow = { ...original };\nshallow.items[2].x = 99;\nconsole.log(original.items[2].x);   // 99 (shared!)",
    },
))
d13.append(task_dict(
    'dict_merge',
    [r'\bmerge\b.*\b(?:dict|dictionary|dicts|dictionaries|maps?)\b(?!\s+sort)',
     r'\bcombine\b.*\b(?:dict|dictionary|dictionaries)\b'],
    "Here's how to merge two dictionaries in {lang}.",
    "Later values win on key conflicts. Python 3.9+ has the | operator; the |=.update() version also works on older versions and mutates the first dict.",
    {
        'python': "# Python 3.9+:\na = {'x': 1, 'y': 2}\nb = {'y': 3, 'z': 4}\nmerged = a | b\nprint(merged)   # {'x': 1, 'y': 3, 'z': 4}\n\n# a is unchanged; to merge into a, use a |= b (or a.update(b)).\n\n# Older versions:\nmerged2 = {**a, **b}\n\n# Or in place:\na.update(b)\nprint(a)        # {'x': 1, 'y': 3, 'z': 4}",
        'javascript': "const a = { x: 1, y: 2 };\nconst b = { y: 3, z: 4 };\n\n// Spread (later values win):\nconst merged = { ...a, ...b };\nconsole.log(merged);   // { x: 1, y: 3, z: 4 }\n\n// Object.assign (mutates the first argument):\nconst merged2 = Object.assign({}, a, b);\n\n// Same keys, last one wins:\nconsole.log({ ...a, ...b }.y);  // 3",
    },
))
d13.append(task_dict(
    'dict_keys',
    [r'\b(?:all\s+)?keys?\s+of\s+(?:a\s+|the\s+)?(?:dict|dictionary)\b',
     r'\b(?:get|return|list)\b.*\bkeys?\b.*\b(?:dict|dictionary)\b'],
    "Here's how to get the keys of a dictionary in {lang}.",
    "Python's .keys() is a live view — it reflects later mutations of the dict. Convert to list() if you need a snapshot or an indexable object.",
    {
        'python': "d = {'a': 1, 'b': 2, 'c': 3}\n\n# View object (live, cheap):\nkeys = d.keys()\nprint(keys)              # dict_keys(['a', 'b', 'c'])\n\n# As a list:\nprint(list(d.keys()))    # ['a', 'b', 'c']\n\n# Iterate keys directly:\nfor k in d:\n    print(k)\n\n# Check membership:\nprint('a' in d)          # True",
        'javascript': "const d = { a: 1, b: 2, c: 3 };\n\nconst keys = Object.keys(d);\nconsole.log(keys);          // ['a', 'b', 'c']\n\n// Iterate:\nfor (const k of Object.keys(d)) {\n    console.log(k);\n}\n\n// Check membership:\nconsole.log('a' in d);      // true (includes inherited keys)\nconsole.log(Object.hasOwn(d, 'a'));  // true (own keys only)",
    },
))
d13.append(task_dict(
    'sort_dict_by_value',
    [r'\bsort\b.*\b(?:dict|dictionary)\b.*\b(?:by\s+)?value\b'],
    "Here's how to sort a dictionary by its values in {lang}.",
    "Python dicts keep insertion order (3.7+), so sorting the items and rebuilding the dict gives a sorted dict. Use reverse=True for descending.",
    {
        'python': "d = {'alice': 30, 'bob': 25, 'carol': 35}\n\n# Ascending by value:\nsorted_d = dict(sorted(d.items(), key=lambda item: item[1]))\nprint(sorted_d)   # {'bob': 25, 'alice': 30, 'carol': 35}\n\n# Descending:\nsorted_d_desc = dict(sorted(d.items(), key=lambda item: item[1], reverse=True))\n\n# operator.itemgetter is faster for big dicts:\nfrom operator import itemgetter\nsorted_d2 = dict(sorted(d.items(), key=itemgetter(1)))\n\n# Just the sorted values:\nprint(sorted(d.values()))",
        'javascript': "const d = { alice: 30, bob: 25, carol: 35 };\n\n// Sort entries by value, rebuild the object:\nconst sorted = Object.fromEntries(\n    Object.entries(d).sort((a, b) => a[1] - b[1])\n);\nconsole.log(sorted);   // { bob: 25, alice: 30, carol: 35 }\n\n// Descending:\nconst desc = Object.fromEntries(\n    Object.entries(d).sort((a, b) => b[1] - a[1])\n);",
    },
))
d13.append(task_dict(
    'dict_intersection',
    [r'\bintersection\b.*\b(?:dict|dictionary|dictionaries)\b',
     r'\b(?:common|shared)\s+keys?\b.*\b(?:dict|dictionary)\b'],
    "Here's how to find the intersection of two dictionaries in {lang}.",
    "Set operations on .keys()/.items() are the idiomatic way: & for intersection, | for union, - for difference.",
    {
        'python': "a = {'x': 1, 'y': 2, 'z': 3}\nb = {'y': 20, 'z': 30, 'w': 40}\n\n# Keys in both:\ncommon_keys = a.keys() & b.keys()\nprint(common_keys)            # {'y', 'z'}\n\n# Key-value pairs in both:\ncommon_items = a.items() & b.items()\nprint(common_items)           # set() — values differ\n\n# Keys in a but not b:\nprint(a.keys() - b.keys())    # {'x'}\n\n# New dict with only the common keys (from a):\nintersection = {k: a[k] for k in (a.keys() & b.keys())}\nprint(intersection)           # {'y': 2, 'z': 3}",
        'javascript': "const a = { x: 1, y: 2, z: 3 };\nconst b = { y: 20, z: 30, w: 40 };\n\n// Keys in both:\nconst commonKeys = Object.keys(a).filter(k => k in b);\nconsole.log(commonKeys);        // ['y', 'z']\n\n// New object with common keys (from a):\nconst intersection = Object.fromEntries(\n    Object.entries(a).filter(([k]) => k in b)\n);\nconsole.log(intersection);      // { y: 2, z: 3 }",
    },
))
d13.append(task_dict(
    'read_config',
    [r'\b(?:read|parse|load)\b.*\bconfig(?:uration)?\s+file\b',
     r'\bconfigparser\b'],
    "Here's how to read a config file in {lang}.",
    "INI files: Python's configparser is in the stdlib. For JSON configs, just json.load. Environment variables are often the simplest config mechanism for deployment.",
    {
        'python': "import configparser\n\n# config.ini:\n#   [database]\n#   host = localhost\n#   port = 5432\n\nconfig = configparser.ConfigParser()\nconfig.read('config.ini')\n\nhost = config['database']['host']\nport = config.getint('database', 'port')\nprint(host, port)\n\n# With defaults:\nconfig = configparser.ConfigParser(defaults={'host': 'localhost'})\nconfig.read('config.ini')\n\n# JSON config:\nimport json\ncfg = json.load(open('config.json'))\n\n# env-based config:\nimport os\nhost = os.getenv('DB_HOST', 'localhost')",
        'javascript': "// INI parsing needs a library; JSON and env vars are the common paths.\n\n// JSON config:\nconst fs = require('fs');\nconst config = JSON.parse(fs.readFileSync('config.json', 'utf8'));\nconsole.log(config.database.host);\n\n// Environment-based config (recommended for deployment):\nconst host = process.env.DB_HOST || 'localhost';\nconst port = Number(process.env.DB_PORT || 5432);",
    },
))
d13.append(task_dict(
    'current_timestamp',
    [r'\bcurrent\s+timestamp\b',
     r'\btime\s+since\s+epoch\b',
     r'\bunix\s+time\s+(?:now|current)\b',
     r'\bepoch\s+seconds?\s+now\b'],
    "Here's how to get the current Unix timestamp in {lang}.",
    "Python time.time() returns seconds as a float; JS Date.now() returns MILLISECONDS — the classic bug when porting between the two. JS: Math.floor(Date.now() / 1000) for seconds.",
    {
        'python': "import time\nimport datetime\n\n# Seconds since epoch (float):\nnow = time.time()\nprint(now)                    # 1775250000.123456\n\n# As an integer:\nprint(int(time.time()))\n\n# Milliseconds (JS-compatible):\nprint(int(time.time() * 1000))\n\n# Via datetime:\nprint(datetime.datetime.now().timestamp())",
        'javascript': "// Milliseconds since epoch:\nconsole.log(Date.now());\n\n// Seconds since epoch (Python-style):\nconsole.log(Math.floor(Date.now() / 1000));\n\n// ISO string:\nconsole.log(new Date().toISOString());",
    },
))
d13.append(task_dict(
    'file_extension',
    [r'\b(?:file\s+)?extension\b.*\b(?:file|filename|path)\b'],
    "Here's how to get a file's extension in {lang}.",
    "os.path.splitext returns (name, extension) — the extension includes the dot. Path('x').suffix is the pathlib equivalent.",
    {
        'python': "import os\nfrom pathlib import Path\n\nfilename = 'report.tar.gz'\n\n# os.path.splitext — splits on the LAST dot:\nname, ext = os.path.splitext(filename)\nprint(name, ext)     # report.tar .gz\n\n# pathlib:\nprint(Path(filename).suffix)      # .gz\nprint(Path(filename).suffixes)    # ['.tar', '.gz']\nprint(Path(filename).stem)        # report.tar\n\n# No extension:\nprint(os.path.splitext('README')[1])   # ''",
        'javascript': "const filename = 'report.tar.gz';\n\n// Last dot:\nconst ext = filename.slice(filename.lastIndexOf('.'));\nconsole.log(ext);                    // .gz\n\n// Regex alternative:\nconst m = filename.match(/\\.([^.]+)$/);\nconsole.log(m ? m[1] : '');          // gz\n\n// Node.js path module:\nconst path = require('path');\nconsole.log(path.extname(filename)); // .gz\nconsole.log(path.basename(filename, path.extname(filename)));  // report.tar",
    },
))
d13.append(task_dict(
    'startswith',
    [r'\b(?:starts?\s+with|prefix)\b.*\b(?:string|text|word)\b',
     r'\bcheck\s+if\s+(?:a\s+)?(?:string|text)\s+(?:starts|ends|begins)\b'],
    "Here's how to check whether a string starts with a prefix in {lang}.",
    "str.startswith also accepts a tuple of prefixes. Use .endswith() for suffixes and .casefold() when you need case-insensitive comparison.",
    {
        'python': "text = 'hello world'\n\nprint(text.startswith('hello'))    # True\nprint(text.startswith('world'))    # False\nprint(text.endswith('world'))      # True\n\n# Multiple prefixes:\nprint(text.startswith(('hello', 'hi')))   # True\n\n# Slice within the string:\nprint(text.startswith('lo', 3))    # True (starts at index 3)\n\n# Case-insensitive:\nprint(text.lower().startswith('HELLO'.lower()))",
        'javascript': "const text = 'hello world';\n\nconsole.log(text.startsWith('hello'));    // true\nconsole.log(text.startsWith('world'));    // false\nconsole.log(text.endsWith('world'));      // true\n\n// Multiple prefixes:\nconsole.log(['hello', 'hi'].some(p => text.startsWith(p)));  // true\n\n// From an index:\nconsole.log(text.startsWith('lo', 3));    // true\n\n// Case-insensitive:\nconsole.log(text.toLowerCase().startsWith('HELLO'.toLowerCase()));",
    },
))
d13.append(task_dict(
    'replace_all',
    [r'\breplace\b.*\b(?:all\s+)?occurrences\b',
     r'\breplace\b.*\bword\b.*\b(?:string|text)\b',
     r'\b(?:replace|substitute)\b.*\b(?:every|all)\b.*\b(?:instance|occurrence)\b'],
    "Here's how to replace all occurrences of a string in {lang}.",
    "Python str.replace replaces all occurrences by default (str.replace(s, old, 1) for one). JS: String.replace with a string only replaces the FIRST — use a global regex or replaceAll.",
    {
        'python': "text = 'the cat sat on the mat'\n\n# Replace all:\nprint(text.replace('the', 'a'))     # a cat sat on a mat\n\n# Replace only the first:\nprint(text.replace('the', 'a', 1))  # a cat sat on the mat\n\n# Case-insensitive:\nimport re\nprint(re.sub(r'the', 'a', text, flags=re.IGNORECASE))\n\n# Word-boundary aware:\nprint(re.sub(r'\\bthe\\b', 'a', text))",
        'javascript': "const text = 'the cat sat on the mat';\n\n// replaceAll (modern):\nconsole.log(text.replaceAll('the', 'a'));  // a cat sat on a mat\n\n// String.replace with a string replaces only the FIRST:\nconsole.log(text.replace('the', 'a'));     // a cat sat on the mat\n\n// Global regex replaces all:\nconsole.log(text.replace(/the/g, 'a'));\n\n// Case-insensitive:\nconsole.log(text.replace(/the/gi, 'a'));\n\n// Word-boundary aware:\nconsole.log(text.replace(/\\bthe\\b/g, 'a'));",
    },
))
d13.append(task_dict(
    'count_lines',
    [r'\bcount\b.*\b(?:the\s+)?(?:number\s+of\s+)?lines?\s+in\s+(?:a\s+|the\s+)?file\b',
     r'\b(?:how\s+many|number\s+of)\s+lines?\s+(?:are\s+there\s+)?in\s+(?:a\s+|the\s+)?file\b'],
    "Here's how to count the lines in a file in {lang}.",
    "Iterating the file object is memory-friendly — it never loads the whole file. Note that a final line without a trailing newline is still counted.",
    {
        'python': "def count_lines(filename: str) -> int:\n    with open(filename, encoding='utf-8') as f:\n        return sum(1 for _ in f)\n\n# Example:\nprint(count_lines('data.txt'))\n\n# Without a helper:\nwith open('data.txt', encoding='utf-8') as f:\n    line_count = sum(1 for _ in f)\n\n# Excluding blank lines:\nwith open('data.txt', encoding='utf-8') as f:\n    non_blank = sum(1 for line in f if line.strip())",
        'javascript': "const fs = require('fs');\n\nfunction countLines(filename) {\n    const content = fs.readFileSync(filename, 'utf8');\n    if (content === '') return 0;\n    return content.split('\\n').length - (content.endsWith('\\n') ? 1 : 0);\n}\n\nconsole.log(countLines('data.txt'));\n\n// Memory-friendly for large files:\nconst readline = require('readline');\nconst rl = readline.createInterface({\n    input: fs.createReadStream('data.txt'),\n});\nlet n = 0;\nrl.on('line', () => n++);\nrl.on('close', () => console.log(n));",
    },
))
d13.append(task_dict(
    'remove_empty_strings',
    [r'\bremove\b.*\bempty\s+strings?\b',
     r'\bfilter\b.*\bempty\s+strings?\b'],
    "Here's how to remove empty strings from a list in {lang}.",
    "In Python, filter(None, items) removes empty strings, None, and 0 — use a lambda when you only want to drop ''.",
    {
        'python': "items = ['a', '', 'b', '  ', 'c', '']\n\n# Remove '' only:\nclean = [x for x in items if x != '']\nprint(clean)     # ['a', 'b', '  ', 'c']\n\n# Remove empty AND whitespace-only:\nclean2 = [x for x in items if x.strip()]\nprint(clean2)    # ['a', 'b', 'c']\n\n# filter(None, ...) also drops None and 0:\nprint(list(filter(None, items)))",
        'javascript': "const items = ['a', '', 'b', '  ', 'c', ''];\n\n// Remove '' only:\nconst clean = items.filter(x => x !== '');\nconsole.log(clean);     // ['a', 'b', '  ', 'c']\n\n// Remove empty AND whitespace-only:\nconst clean2 = items.filter(x => x.trim() !== '');\nconsole.log(clean2);    // ['a', 'b', 'c']\n\n// Truthiness also drops null/undefined/0:\nconst clean3 = items.filter(Boolean);",
    },
))
d13.append(task_dict(
    'largest_number',
    [r'\blargest\b.*\b(?:number|element|item|value)\b.*\b(?:list|array)\b',
     r'\b(?:find|get|return)\b.*\b(?:max|maximum)\b.*\b(?:list|array)\b'],
    "Here's how to find the largest number in a list in {lang}.",
    "max() is O(n) and handles any iterable. Use max(items, key=...) for the largest object by an attribute, and heapq.nlargest for the top k.",
    {
        'python': "numbers = [3, 7, 2, 9, 5]\n\nlargest = max(numbers)\nprint(largest)     # 9\n\n# Smallest:\nprint(min(numbers))  # 2\n\n# Largest by a key (dicts/objects):\npeople = [{'name': 'a', 'age': 30}, {'name': 'b', 'age': 40}]\noldest = max(people, key=lambda p: p['age'])\nprint(oldest['name'])  # b\n\n# Empty-list safety:\nprint(max(numbers, default=None))",
        'javascript': "const numbers = [3, 7, 2, 9, 5];\n\nconst largest = Math.max(...numbers);\nconsole.log(largest);   // 9\n\n// Smallest:\nconsole.log(Math.min(...numbers));  // 2\n\n// Large arrays: spread can overflow the stack — use reduce:\nconst max = numbers.reduce((a, b) => Math.max(a, b));\n\n// Largest by a key:\nconst people = [{ name: 'a', age: 30 }, { name: 'b', age: 40 }];\nconst oldest = people.reduce((a, b) => (a.age > b.age ? a : b));",
    },
))
d13.append(task_dict(
    'average_list',
    [r'\baverage\b.*\b(?:list|array|numbers?|values?)\b',
     r'\b(?:mean|arithmetic\s+mean)\b.*\b(?:list|array)\b'],
    "Here's how to compute the average of a list in {lang}.",
    "Watch for integer division: Python 3's / always returns a float. Guard against empty input to avoid ZeroDivisionError / NaN.",
    {
        'python': "def average(numbers: list) -> float:\n    if not numbers:\n        return 0.0\n    return sum(numbers) / len(numbers)\n\n# Example:\nprint(average([1, 2, 3, 4]))   # 2.5\n\n# With statistics (more helpers: median, stdev):\nimport statistics\nprint(statistics.mean([1, 2, 3, 4]))    # 2.5\nprint(statistics.median([1, 2, 3, 4]))  # 2.5",
        'javascript': "function average(numbers) {\n    if (numbers.length === 0) return 0;\n    return numbers.reduce((a, b) => a + b, 0) / numbers.length;\n}\n\nconsole.log(average([1, 2, 3, 4]));   // 2.5\n\n// Integer arrays with a large sum: watch floating point —\n// sort and add pairwise, or use a library for exact rationals.",
    },
))
d13.append(task_dict(
    'unique_chars',
    [r'\bunique\s+characters?\b',
     r'\bdistinct\s+characters?\b',
     r'\b(?:all\s+)?different\s+characters?\b'],
    "Here's how to get the unique characters in a string in {lang}.",
    "set() removes duplicates but loses order; dict.fromkeys preserves first-seen order (Python 3.7+). For JS, use Set.",
    {
        'python': "text = 'banana'\n\n# Unique characters (order NOT preserved):\nuniq = set(text)\nprint(uniq)               # {'a', 'b', 'n'}\n\n# Unique characters in first-seen order:\nordered = ''.join(dict.fromkeys(text))\nprint(ordered)            # 'ban'\n\n# Check whether all characters are unique:\ndef all_unique(s: str) -> bool:\n    return len(s) == len(set(s))\n\nprint(all_unique('abc'))  # True\nprint(all_unique('aba'))  # False",
        'javascript': "const text = 'banana';\n\n// Unique characters (insertion order preserved by Set):\nconst uniq = [...new Set(text)];\nconsole.log(uniq);            // ['b', 'a', 'n']\n\n// As a string:\nconsole.log([...new Set(text)].join(''));  // 'ban'\n\n// Check whether all characters are unique:\nfunction allUnique(s) {\n    return new Set(s).size === s.length;\n}\nconsole.log(allUnique('abc'));  // true\nconsole.log(allUnique('aba'));  // false",
    },
))
d13.append(task_dict(
    'valid_email_check',
    [r'\b(?:check|validate|verify)\b.*\b(?:string\s+is\s+(?:a\s+|an?\s+)?)?valid\s+email\s+address\b',
     r'\b(?:is\s+valid|validate)\s+email\b(?!\s+regex)'],
    "Here's a {lang} function that checks whether a string is a valid email address.",
    "A pragmatic validator checks for a single @, a non-empty local part, a dot in the domain, and reasonable lengths — full RFC 5322 regexes are huge and still reject many real addresses.",
    {
        'python': "import re\n\n_EMAIL_RE = re.compile(\n    r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'\n)\n\n\ndef is_valid_email(email: str) -> bool:\n    return bool(_EMAIL_RE.fullmatch(email.strip()))\n\n# Examples:\nprint(is_valid_email('alice@example.com'))     # True\nprint(is_valid_email('alice@example'))         # False (no TLD)\nprint(is_valid_email('alice@example.c'))       # False (TLD too short)\nprint(is_valid_email('not an email'))          # False",
        'javascript': "const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$/;\n\nfunction isValidEmail(email) {\n    return EMAIL_RE.test(email.trim());\n}\n\nconsole.log(isValidEmail('alice@example.com'));  // true\nconsole.log(isValidEmail('alice@example'));      // false\nconsole.log(isValidEmail('not an email'));       // false",
    },
))
d13.append(task_dict(
    'timeit_decorator',
    [r'\b(?:tim\w*|timeit)\b.*\bdecorator\b',
     r'\bdecorator\b.*\b(?:tim\w*|timeit)\b'],
    "Here's a {lang} decorator that times a function's execution.",
    "time.perf_counter() is the right clock for measuring code — it's monotonic and high-resolution. functools.wraps preserves the wrapped function's name and docstring.",
    {
        'python': "import time\nimport functools\n\n\ndef timed(func):\n    \"\"\"Decorator: print how long the wrapped function takes.\"\"\"\n    @functools.wraps(func)\n    def wrapper(*args, **kwargs):\n        start = time.perf_counter()\n        result = func(*args, **kwargs)\n        elapsed = time.perf_counter() - start\n        print(f'{func.__name__} took {elapsed * 1000:.2f} ms')\n        return result\n    return wrapper\n\n\n@timed\ndef slow_add(a, b):\n    time.sleep(0.1)\n    return a + b\n\nprint(slow_add(1, 2))\n# slow_add took 100.12 ms\n# 3",
        'javascript': "function timed(fn) {\n    return function (...args) {\n        const start = performance.now();\n        const result = fn.apply(this, args);\n        const elapsed = performance.now() - start;\n        console.log(`${fn.name} took ${elapsed.toFixed(2)} ms`);\n        return result;\n    };\n}\n\nconst slowAdd = timed((a, b) => {\n    const t = Date.now();\n    while (Date.now() - t < 100);  // busy-wait\n    return a + b;\n});\n\nconsole.log(slowAdd(1, 2));\n// slowAdd took ~100 ms\n// 3",
    },
))
d13.append(task_dict(
    'any_duplicates',
    [r'\b(?:any|has|have|contains?|check\s+for)\b.*\bduplicates?\b.*\b(?:list|array)\b',
     r'\b(?:list|array)\b.*\b(?:has|have|contain\w*)\b.*\bduplicates?\b',
     r'\bduplicates?\s+in\s+(?:a\s+|the\s+)?(?:list|array)\b(?!.*\bsql)'],
    "Here's a {lang} function that checks whether a list contains duplicates.",
    "Comparing len(items) to len(set(items)) is O(n) and simple. For big data, stop early by tracking seen items in a set.",
    {
        'python': "def has_duplicates(items: list) -> bool:\n    return len(items) != len(set(items))\n\n# Examples:\nprint(has_duplicates([1, 2, 3]))        # False\nprint(has_duplicates([1, 2, 2]))        # True\n\n# Early-exit version (stops at the first duplicate):\ndef has_duplicates_fast(items):\n    seen = set()\n    for item in items:\n        if item in seen:\n            return True\n        seen.add(item)\n    return False\n\n# Which items are duplicated:\nfrom collections import Counter\ncounts = Counter([1, 2, 2, 3, 3, 3])\nprint([k for k, v in counts.items() if v > 1])   # [2, 3]",
        'javascript': "function hasDuplicates(items) {\n    return new Set(items).size !== items.length;\n}\n\nconsole.log(hasDuplicates([1, 2, 3]));   // false\nconsole.log(hasDuplicates([1, 2, 2]));   // true\n\n// Early-exit version:\nfunction hasDuplicatesFast(items) {\n    const seen = new Set();\n    for (const item of items) {\n        if (seen.has(item)) return true;\n        seen.add(item);\n    }\n    return false;\n}",
    },
))
d13.append(task_dict(
    'zip_lists',
    [r'\bzip\b.*\blists?\b(?!\s+(?:file|folder|directory|archive))',
     r'\b(?:pair|combine)\b.*\btwo\s+lists\b'],
    "Here's how to zip two lists together in {lang}.",
    "Python's zip() stops at the shortest input; zip_longest pads with a fill value. In JS, use a map over Math.min lengths, or Object.fromEntries for key-value pairs.",
    {
        'python': "names = ['alice', 'bob', 'carol']\nages = [30, 25, 35]\n\n# Pairs (stops at the shortest):\npairs = list(zip(names, ages))\nprint(pairs)   # [('alice', 30), ('bob', 25), ('carol', 35)]\n\n# Dict from two lists:\npeople = dict(zip(names, ages))\nprint(people)  # {'alice': 30, 'bob': 25, 'carol': 35}\n\n# Unpack back:\nnames2, ages2 = zip(*pairs)\n\n# Unequal lengths -> pad:\nfrom itertools import zip_longest\nprint(list(zip_longest([1, 2], ['a'], fillvalue=None)))  # [(1, 'a'), (2, None)]",
        'javascript': "const names = ['alice', 'bob', 'carol'];\nconst ages = [30, 25, 35];\n\n// Pairs (stops at the shortest):\nconst pairs = names.map((name, i) => [name, ages[i]]);\nconsole.log(pairs);   // [['alice', 30], ['bob', 25], ['carol', 35]]\n\n// Object from two arrays:\nconst people = Object.fromEntries(pairs);\nconsole.log(people);  // { alice: 30, bob: 25, carol: 35 }",
    },
))
d13.append(task_dict(
    'log_monitor',
    [r'^(?!.*\blast\s+\d+\s+lines?).*\b(?:monitor|tail|follow)\b.*\blog\b',
     r'^.*\bwatch\b.*\blog\b'],
    "Here's a {lang} script that monitors a log file as it grows.",
    "Seeking to the end on startup avoids replaying the whole file. In bash, tail -F (capital F) retries when the file is rotated; tail -f does not.",
    {
        'python': "import time\n\n\ndef tail_log(filename: str, interval: float = 0.5):\n    \"\"\"Print new lines appended to a log file forever.\"\"\"\n    with open(filename, encoding='utf-8') as f:\n        f.seek(0, 2)          # start at the end\n        while True:\n            line = f.readline()\n            if line:\n                print(line.rstrip())\n            else:\n                time.sleep(interval)\n\n\nif __name__ == '__main__':\n    tail_log('app.log')",
        'javascript': "// Node.js: follow a file like tail -f\nconst fs = require('fs');\n\nfunction tailLog(filename, interval = 500) {\n    // Poll the file size and read newly appended bytes:\n    let pos = fs.statSync(filename).size;\n    setInterval(() => {\n        const size = fs.statSync(filename).size;\n        if (size > pos) {\n            const fd = fs.openSync(filename, 'r');\n            const buf = Buffer.alloc(size - pos);\n            fs.readSync(fd, buf, 0, buf.length, pos);\n            fs.closeSync(fd);\n            process.stdout.write(buf.toString());\n            pos = size;\n        }\n    }, interval);\n}",
    },
))
save('13_python_utils.json', d13)
print('13_python_utils.json:', len(d13), 'tasks')

# ── 14_js_utils.json ──────────────────────────────────────────────────────
d14 = []
d14.append(task_dict(
    'fetch_with_errors',
    [r'\bfetch\b.*\b(?:error|errors?|try|catch|handle|handling)\b'],
    "Here's how to make a fetch request with error handling in {lang}.",
    "fetch only rejects on network failure — HTTP errors (404, 500) resolve normally, so check response.ok. A timeout also needs explicit handling: AbortSignal.timeout is the modern way.",
    {
        'python': "import requests\nfrom requests.exceptions import RequestException, Timeout\n\ntry:\n    resp = requests.get('https://api.example.com/data', timeout=10)\n    resp.raise_for_status()          # raises for 4xx/5xx\n    data = resp.json()\nexcept Timeout:\n    print('request timed out')\nexcept RequestException as exc:\n    print(f'request failed: {exc}')\nelse:\n    print(data)",
        'javascript': "async function fetchWithErrors(url) {\n    try {\n        const resp = await fetch(url, {\n            signal: AbortSignal.timeout(10_000),  // abort after 10s\n        });\n        if (!resp.ok) {\n            throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);\n        }\n        return await resp.json();\n    } catch (err) {\n        if (err.name === 'TimeoutError') {\n            console.error('request timed out');\n        } else {\n            console.error('request failed:', err.message);\n        }\n        throw err;\n    }\n}\n\nfetchWithErrors('https://api.example.com/data')\n    .then(data => console.log(data))\n    .catch(() => console.log('handled'));",
    },
))
d14.append(task_dict(
    'debounce',
    [r'\bdebounce\b'],
    "Here's how to debounce a function in {lang}.",
    "Debouncing delays the call until the input stops changing — right for search-as-you-type and resize handlers. The trailing call runs after the delay; leading:true runs immediately and cancels the rest.",
    {
        'python': "import time\nimport threading\n\n\ndef debounce(wait: float):\n    \"\"\"Decorator: call fn at most once per `wait` seconds of quiet.\"\"\"\n    def decorator(fn):\n        timer = None\n        def wrapped(*args, **kwargs):\n            nonlocal timer\n            def call():\n                fn(*args, **kwargs)\n            if timer is not None:\n                timer.cancel()\n            timer = threading.Timer(wait, call)\n            timer.start()\n        return wrapped\n    return decorator\n\n\n@debounce(0.3)\ndef on_type(text):\n    print('searched:', text)\n\n# Call rapidly; on_type runs once, 0.3s after the last call.",
        'javascript': "function debounce(fn, wait = 300) {\n    let timer;\n    return function (...args) {\n        clearTimeout(timer);\n        timer = setTimeout(() => fn.apply(this, args), wait);\n    };\n}\n\n// Example: search box\nconst onType = debounce(text => console.log('searched:', text), 300);\ninput.addEventListener('input', e => onType(e.target.value));\n\n// Leading edge (run immediately, then wait):\nfunction debounceLeading(fn, wait = 300) {\n    let timer, lastRan;\n    return function (...args) {\n        const now = Date.now();\n        if (lastRan && now - lastRan < wait) {\n            clearTimeout(timer);\n            timer = setTimeout(() => {\n                lastRan = Date.now();\n                fn.apply(this, args);\n            }, wait - (now - lastRan));\n            return;\n        }\n        lastRan = now;\n        fn.apply(this, args);\n    };\n}",
    },
))
d14.append(task_dict(
    'throttle',
    [r'\bthrottle\b'],
    "Here's how to throttle a function in {lang}.",
    "Throttling limits calls to at most once per interval — right for scroll and mousemove handlers. Debounce waits for quiet; throttle guarantees a minimum spacing.",
    {
        'python': "import time\nimport threading\n\n\ndef throttle(interval: float):\n    \"\"\"Decorator: run fn at most once per `interval` seconds.\"\"\"\n    def decorator(fn):\n        last_run = 0.0\n        lock = threading.Lock()\n        def wrapped(*args, **kwargs):\n            nonlocal last_run\n            with lock:\n                now = time.monotonic()\n                if now - last_run < interval:\n                    return\n                last_run = now\n            return fn(*args, **kwargs)\n        return wrapped\n    return decorator\n\n\n@throttle(1.0)\ndef on_scroll():\n    print('scrolled')\n\n# Called 100 times in a second, on_scroll runs ~once.",
        'javascript': "function throttle(fn, limit = 1000) {\n    let lastRun = 0;\n    return function (...args) {\n        const now = Date.now();\n        if (now - lastRun >= limit) {\n            lastRun = now;\n            fn.apply(this, args);\n        }\n    };\n}\n\n// Trailing edge (guarantee the final call runs):\nfunction throttleTrailing(fn, limit = 1000) {\n    let lastRun = 0, timer;\n    return function (...args) {\n        const now = Date.now();\n        const remaining = limit - (now - lastRun);\n        if (remaining <= 0) {\n            clearTimeout(timer);\n            lastRun = now;\n            fn.apply(this, args);\n        } else if (!timer) {\n            timer = setTimeout(() => {\n                lastRun = Date.now();\n                timer = null;\n                fn.apply(this, args);\n            }, remaining);\n        }\n    };\n}\n\n// Example: window.addEventListener('scroll', throttle(onScroll, 200));",
    },
))
d14.append(task_dict(
    'shallow_copy',
    [r'\bshallow\s*copy\b'],
    "Here's how to shallow-copy an object in {lang}.",
    "A shallow copy duplicates the top level; nested objects are still shared. For a full clone use structuredClone (JS) or copy.deepcopy (Python).",
    {
        'python': "import copy\n\noriginal = {'items': [1, 2, 3]}\n\n# Shallow copies (dict copy, dict(), or copy.copy):\nshallow = original.copy()\nshallow['items'].append(4)\nprint(original['items'])   # [1, 2, 3, 4]  (SHARED!)\n\nshallow2 = copy.copy(original)\n\n# Lists:\nnums = [1, 2, [3]]\nnums_shallow = nums.copy()   # or list(nums), nums[:]",
        'javascript': "const original = { items: [1, 2, 3], name: 'x' };\n\n// Shallow copies:\nconst shallow = { ...original };\nconst shallow2 = Object.assign({}, original);\n\n// Nested objects are shared:\nshallow.items.push(4);\nconsole.log(original.items);   // [1, 2, 3, 4]  (SHARED!)\n\n// Arrays:\nconst arr = [1, 2, [3]];\nconst arrCopy = [...arr];\nconst arrCopy2 = arr.slice();",
    },
))
d14.append(task_dict(
    'deep_clone',
    [r'\bdeep\s*(?:clone|copy)\b'],
    "Here's how to deep-clone an object in {lang}.",
    "structuredClone (JS) handles dates, Maps, Sets, and circular references — JSON round-trips do not. Python's copy.deepcopy is the equivalent.",
    {
        'python': "import copy\n\nclass Point:\n    def __init__(self, x, y):\n        self.x, self.y = x, y\n\noriginal = {'point': Point(1, 2), 'tags': ['a', 'b']}\n\n# Deep copy:\ndeep = copy.deepcopy(original)\ndeep['point'].x = 99\nprint(original['point'].x)   # 1 (unchanged)\ndeep['tags'].append('c')\nprint(original['tags'])      # ['a', 'b'] (unchanged)\n\n# JSON round-trip (only JSON-safe data):\nimport json\nclone = json.loads(json.dumps({'tags': ['a', 'b']}))",
        'javascript': "const original = { date: new Date(), tags: ['a', 'b'], nested: { x: 1 } };\n\n// structuredClone — deep, handles Date/Map/Set/circular refs:\nconst deep = structuredClone(original);\ndeep.tags.push('c');\ndeep.nested.x = 99;\nconsole.log(original.tags);       // ['a', 'b'] (unchanged)\nconsole.log(original.nested.x);   // 1 (unchanged)\n\n// JSON round-trip — loses Dates (becomes string) and functions:\nconst clone = JSON.parse(JSON.stringify(original));",
    },
))
d14.append(task_dict(
    'currency_format',
    [r'\b(?:format|convert)\b.*\b(?:number|amount|value)\b.*\bcurrency\b',
     r'\bcurrency\s+format\w*\b',
     r'\b(?:money|price|dollars?)\s+format\w*\b'],
    "Here's how to format a number as currency in {lang}.",
    "Intl.NumberFormat (JS) and the locale module (Python) handle grouping, decimal separators, and currency symbols per locale — don't hand-roll comma insertion.",
    {
        'python': "import locale\n\n# The locale module follows your system locale:\nlocale.setlocale(locale.LC_ALL, '')\nprint(locale.currency(1234.5, grouping=True))   # $1,234.50 (en_US)\n\n# Explicit formatting without locale:\nprint(f'${1234.5:,.2f}')   # $1,234.50\n\n# Euro / other symbols are just strings:\nprint(f'\\u20ac{1234.5:,.2f}')  # €1,234.50\n\n# babel (pip install babel) for full i18n:\n# from babel.numbers import format_currency\n# format_currency(1234.5, 'EUR', locale='de_DE')  # 1.234,50 €",
        'javascript': "const amount = 1234.5;\n\n// Locale-aware (recommended):\nconsole.log(new Intl.NumberFormat('en-US', {\n    style: 'currency', currency: 'USD'\n}).format(amount));   // $1,234.50\n\nconsole.log(new Intl.NumberFormat('de-DE', {\n    style: 'currency', currency: 'EUR'\n}).format(amount));   // 1.234,50 €\n\n// Just the number with grouping:\nconsole.log(amount.toLocaleString('en-US'));   // 1,234.5\n\n// Hand-rolled (no decimals):\nfunction formatMoney(n) {\n    return '$' + n.toFixed(2).replace(/\\B(?=(\\d{3})+(?!\\d))/g, ',');\n}",
    },
))
d14.append(task_dict(
    'current_date',
    [r"\b(?:current|today'?s?|now)\b.*\bdate\b(?!\s+timezone)",
     r'\bget\b.*\b(?:today|current)\s+date\b'],
    "Here's how to get the current date in {lang}.",
    "JS Date is a timestamp + timezone display — getDate() is LOCAL; use getUTCDate()/toISOString() for UTC. Python's date.today() is local; date.today() from datetime is the stdlib way.",
    {
        'python': "from datetime import date, datetime\n\n# Today's date (local):\ntoday = date.today()\nprint(today)                  # 2026-04-03\n\n# Current date and time:\nnow = datetime.now()\nprint(now)\n\n# Current date in UTC:\nfrom datetime import timezone\nprint(datetime.now(timezone.utc).date())\n\n# Individual fields:\nprint(today.year, today.month, today.day)",
        'javascript': "// Now:\nconst now = new Date();\n\n// Local date parts:\nconsole.log(now.getFullYear(), now.getMonth() + 1, now.getDate());\n\n// UTC date parts:\nconsole.log(now.getUTCFullYear(), now.getUTCMonth() + 1, now.getUTCDate());\n\n// ISO string (UTC):\nconsole.log(now.toISOString());            // 2026-04-03T15:30:00.000Z\nconsole.log(now.toISOString().slice(0, 10));  // 2026-04-03\n\n// Locale date:\nconsole.log(now.toLocaleDateString());     // 4/3/2026",
    },
))
d14.append(task_dict(
    'set_timeout',
    [r'\bsetTimeout\b',
     r'\b(?:delay|wait)\b.*\b(?:ms|milliseconds?|seconds?)\b.*\b(?:javascript|js|node)\b'],
    "Here's how to delay code with setTimeout in {lang}.",
    "setTimeout runs once after the delay; setInterval repeats. The delay is a minimum, not exact — the event loop may be busy. Use AbortController or clearTimeout to cancel.",
    {
        'python': "import time\nimport threading\n\n# Blocking delay (simple scripts):\ntime.sleep(1.5)          # 1.5 seconds\nprint('after sleep')\n\n# Non-blocking delay (run a function later):\nthreading.Timer(1.5, lambda: print('after timer')).start()\nprint('immediately')\n\n# Asyncio:\nimport asyncio\n\nasync def main():\n    await asyncio.sleep(1.5)\n    print('after await')\n\nasyncio.run(main())",
        'javascript': "// Run once after 1.5s:\nconst timer = setTimeout(() => {\n    console.log('after 1.5s');\n}, 1500);\n\n// Cancel it:\nclearTimeout(timer);\n\n// Repeat every 2s:\nconst interval = setInterval(() => {\n    console.log('tick');\n}, 2000);\nclearInterval(interval);\n\n// Inside async code:\nawait new Promise(resolve => setTimeout(resolve, 1500));\nconsole.log('after await');",
    },
))
d14.append(task_dict(
    'add_event_listener',
    [r'\b(?:add\s+(?:an?\s+)?)?event\s+listener\b',
     r'\b(?:attach|bind|register)\b.*\b(?:event|handler|listener)\b'],
    "Here's how to attach an event listener in {lang}.",
    "addEventListener is the modern way — it supports multiple handlers and options like { once: true }. Inline onclick= attributes are discouraged (mixes markup and logic).",
    {
        'javascript': "// Basic click listener:\nconst button = document.querySelector('#my-button');\nbutton.addEventListener('click', () => {\n    console.log('clicked');\n});\n\n// With event object:\nbutton.addEventListener('click', (event) => {\n    console.log(event.target, event.clientX, event.clientY);\n});\n\n// Run once:\nbutton.addEventListener('click', handler, { once: true });\n\n// Remove a listener (needs the same function reference):\nfunction handler() {}\nbutton.addEventListener('click', handler);\nbutton.removeEventListener('click', handler);\n\n// Keyboard / document events:\ndocument.addEventListener('keydown', (e) => {\n    if (e.key === 'Escape') console.log('escaped');\n});",
        'python': "import tkinter as tk\n\n# Tkinter: the stdlib GUI toolkit\nroot = tk.Tk()\n\n\ndef on_click(event):\n    print('clicked at', event.x, event.y)\n\n\nbutton = tk.Button(root, text='Click me')\nbutton.pack()\nbutton.bind('<Button-1>', on_click)   # left click\nroot.bind('<Escape>', lambda e: root.quit())\nroot.mainloop()",
    },
))
d14.append(task_dict(
    'remove_dom_element',
    [r'\bremove\b.*\b(?:element|dom\s+element)\b',
     r'\bdelete\b.*\b(?:dom\s+)?element\b'],
    "Here's how to remove an element from the DOM in {lang}.",
    "element.remove() is the clean modern way. removeChild is the older API. To hide without removing (keep state), use style.display='none'.",
    {
        'javascript': "// Remove the element itself (modern):\nconst el = document.querySelector('#toast');\nel.remove();\n\n// Remove a child from its parent (older API):\nel.parentNode.removeChild(el);\n\n// Remove all children (clear a container):\nconst container = document.querySelector('#list');\ncontainer.replaceChildren();\n\n// Hide instead of remove:\nel.style.display = 'none';",
        'python': "import tkinter as tk\n\nroot = tk.Tk()\nlabel = tk.Label(root, text='bye')\nlabel.pack()\n\n# Remove from the layout:\nlabel.pack_forget()\n\n# Or destroy it entirely:\nlabel.destroy()\n\nroot.mainloop()",
    },
))
d14.append(task_dict(
    'js_map',
    [r'\bmap\b.*\b(?:an?\s+|the\s+)?array\b',
     r'\b(?:transform|convert)\b.*\b(?:each\s+)?(?:element|item)\b.*\barray\b'],
    "Here's how to map an array to new values in {lang}.",
    "Array.map returns a NEW array of the same length — use it for transforms, not side effects (that's forEach). The index is the second callback argument.",
    {
        'python': "numbers = [1, 2, 3, 4]\n\n# List comprehension (the Pythonic map):\nsquares = [x * x for x in numbers]\nprint(squares)   # [1, 4, 9, 16]\n\n# Functional map():\nprint(list(map(lambda x: x * x, numbers)))\n\n# With index (enumerate):\nwith_index = [f'{i}: {x}' for i, x in enumerate(numbers)]\n\n# Strings:\nnames = ['alice', 'bob']\nuppercased = [n.upper() for n in names]",
        'javascript': "const numbers = [1, 2, 3, 4];\n\n// .map returns a new array:\nconst squares = numbers.map(x => x * x);\nconsole.log(squares);   // [1, 4, 9, 16]\n\n// With index:\nconst labeled = numbers.map((x, i) => `${i}: ${x}`);\n\n// Objects:\nconst people = [{ name: 'alice' }, { name: 'bob' }];\nconst names = people.map(p => p.name);   // ['alice', 'bob']",
    },
))
d14.append(task_dict(
    'js_filter',
    [r'\bfilter\b.*\b(?:an?\s+|the\s+)?array\b',
     r'\b(?:keep|select)\b.*\b(?:items?|elements?)\b.*\b(?:matching|where|that)\b'],
    "Here's how to filter an array in {lang}.",
    "Array.filter keeps elements where the callback returns true and returns a new array. Python's list comprehension with an if clause is the equivalent.",
    {
        'python': "numbers = [1, 2, 3, 4, 5]\n\n# Keep even numbers:\nevens = [x for x in numbers if x % 2 == 0]\nprint(evens)   # [2, 4]\n\n# Functional filter():\nprint(list(filter(lambda x: x % 2 == 0, numbers)))\n\n# Filter objects:\npeople = [{'name': 'a', 'age': 30}, {'name': 'b', 'age': 20}]\nadults = [p for p in people if p['age'] >= 21]\n\n# Filter + transform in one pass:\nsquares_of_evens = [x * x for x in numbers if x % 2 == 0]",
        'javascript': "const numbers = [1, 2, 3, 4, 5];\n\n// Keep even numbers:\nconst evens = numbers.filter(x => x % 2 === 0);\nconsole.log(evens);   // [2, 4]\n\n// With index:\nconst firstTwo = numbers.filter((x, i) => i < 2);\n\n// Filter objects:\nconst people = [{ name: 'a', age: 30 }, { name: 'b', age: 20 }];\nconst adults = people.filter(p => p.age >= 21);\n\n// Chain with map:\nconst evensSquared = numbers.filter(x => x % 2 === 0).map(x => x * x);",
    },
))
d14.append(task_dict(
    'js_reduce',
    [r'\breduce\b.*\b(?:an?\s+|the\s+)?array\b',
     r'\b(?:fold|aggregate)\b.*\b(?:array|list)\b.*\b(?:single|sum|total)\b'],
    "Here's how to reduce an array to a single value in {lang}.",
    "Array.reduce folds the array with an accumulator. For sums use the built-in (Python sum, JS reduce). Always pass the initial value to avoid surprises on empty arrays.",
    {
        'python': "from functools import reduce\n\nnumbers = [1, 2, 3, 4]\n\n# Built-in for sums:\ntotal = sum(numbers)\nprint(total)   # 10\n\n# reduce for custom folds:\nproduct = reduce(lambda acc, x: acc * x, numbers, 1)\nprint(product)   # 24\n\n# Max via reduce:\nmaximum = reduce(max, numbers)\n\n# Custom:\njoined = reduce(lambda acc, x: f'{acc}-{x}', numbers)\nprint(joined)   # 1-2-3-4",
        'javascript': "const numbers = [1, 2, 3, 4];\n\n// Sum with reduce (always pass the initial value):\nconst total = numbers.reduce((acc, x) => acc + x, 0);\nconsole.log(total);   // 10\n\n// Product:\nconst product = numbers.reduce((acc, x) => acc * x, 1);   // 24\n\n// Max:\nconst max = numbers.reduce((acc, x) => Math.max(acc, x), -Infinity);\n\n// Build an object:\nconst counts = ['a', 'b', 'a'].reduce((acc, x) => {\n    acc[x] = (acc[x] || 0) + 1;\n    return acc;\n}, {});\nconsole.log(counts);   // { a: 2, b: 1 }",
    },
))
d14.append(task_dict(
    'array_last',
    [r'\blast\s+(?:element|item|value)\s+of\s+(?:an?\s+|the\s+)?array\b',
     r'\b(?:get|access|return)\b.*\blast\b.*\b(?:element|item)\b.*\barray\b'],
    "Here's how to get the last element of an array in {lang}.",
    "Python: arr[-1] is the idiomatic way. JS: arr[arr.length - 1], or arr.at(-1) (ES2022). Be careful with negative-index slicing — arr[-1] in JS is undefined.",
    {
        'python': "arr = [1, 2, 3, 4]\n\nlast = arr[-1]\nprint(last)   # 4\n\n# Second-to-last:\nprint(arr[-2])   # 3\n\n# Safe version:\ndef last_item(items):\n    return items[-1] if items else None\n\n# Pop removes AND returns the last element:\nprint(arr.pop())   # 4\nprint(arr)         # [1, 2, 3]",
        'javascript': "const arr = [1, 2, 3, 4];\n\nconst last = arr[arr.length - 1];\nconsole.log(last);   // 4\n\n// ES2022 .at():\nconsole.log(arr.at(-1));   // 4\nconsole.log(arr.at(-2));   // 3\n\n// .pop() removes and returns:\nconsole.log(arr.pop());    // 4\nconsole.log(arr);          // [1, 2, 3]\n\n// Safe version:\nfunction lastItem(items) {\n    return items.length ? items[items.length - 1] : undefined;\n}",
    },
))
d14.append(task_dict(
    'merge_arrays',
    [r'\bmerge\b.*\barrays?\b(?!.*\bsorted\b)',
     r'\bconcat(?:enate)?\b.*\barrays?\b'],
    "Here's how to merge two arrays in {lang}.",
    "Python: list + list (or extend for in-place). JS: spread [...a, ...b] or .concat(). Neither deduplicates — use a Set for that.",
    {
        'python': "a = [1, 2, 3]\nb = [4, 5, 6]\n\n# New merged list:\nmerged = a + b\nprint(merged)   # [1, 2, 3, 4, 5, 6]\n\n# In place (a is extended):\na.extend(b)\nprint(a)\n\n# Without duplicates (order-preserving):\nmerged_uniq = list(dict.fromkeys(a + b))\n\n# Repeated / interleaved: itertools.chain\nfrom itertools import chain\nprint(list(chain([1, 2], [3, 4])))",
        'javascript': "const a = [1, 2, 3];\nconst b = [4, 5, 6];\n\n// Spread:\nconst merged = [...a, ...b];\nconsole.log(merged);   // [1, 2, 3, 4, 5, 6]\n\n// concat:\nconst merged2 = a.concat(b);\n\n// In place (mutates a):\na.push(...b);\n\n// Without duplicates:\nconst unique = [...new Set([...a, ...b])];",
    },
))
d14.append(task_dict(
    'string_contains',
    [r'\b(?:check\s+if\s+)?(?:a\s+|the\s+)?string\s+contains\b',
     r'\bcontains?\b.*\bsubstring\b'],
    "Here's how to check whether a string contains a substring in {lang}.",
    "Python: 'sub' in s. JS: s.includes('sub') (ES2016) — indexOf for older environments. Both are case-sensitive; lowercase both sides for case-insensitive matching.",
    {
        'python': "text = 'hello world'\n\nprint('world' in text)        # True\nprint('xyz' in text)          # False\n\n# Case-insensitive:\nprint('WORLD' in text.upper())  # True\n\n# Position (index of first occurrence, -1 if absent):\nprint(text.find('world'))     # 6\nprint(text.index('world'))    # 6 (raises ValueError if absent)\n\n# Count occurrences:\nprint(text.count('o'))        # 2",
        'javascript': "const text = 'hello world';\n\nconsole.log(text.includes('world'));     // true\nconsole.log(text.includes('xyz'));       // false\n\n// Case-insensitive:\nconsole.log(text.toUpperCase().includes('WORLD'));  // true\n\n// Position (ES2015, -1 if absent):\nconsole.log(text.indexOf('world'));      // 6\nconsole.log(text.indexOf('xyz'));        // -1\n\n// Starts/ends:\nconsole.log(text.startsWith('hello'));   // true\nconsole.log(text.endsWith('world'));     // true",
    },
))
d14.append(task_dict(
    'array_find',
    [r'\bfind\b.*\b(?:an?\s+|the\s+)?(?:element|item|value)\s+in\b.*\barray\b'],
    "Here's how to find an element in an array in {lang}.",
    "JS .find returns the first match or undefined; .findIndex returns its index. Python uses a loop, next() with a generator, or index() for exact values.",
    {
        'python': "numbers = [1, 2, 3, 4]\n\n# First element matching a condition:\ndef find_first(items, predicate):\n    return next((x for x in items if predicate(x)), None)\n\nprint(find_first(numbers, lambda x: x > 2))    # 3\n\n# Exact value -> index (raises ValueError if absent):\nprint(numbers.index(3))    # 2\n\n# Safe index:\ndef safe_index(items, value):\n    return items.index(value) if value in items else -1\n\n# Boolean check:\nprint(2 in numbers)        # True",
        'javascript': "const numbers = [1, 2, 3, 4];\n\n// First element matching a condition (or undefined):\nconst found = numbers.find(x => x > 2);\nconsole.log(found);            // 3\n\n// Its index (or -1):\nconsole.log(numbers.findIndex(x => x > 2));   // 2\n\n// Exact value -> index:\nconsole.log(numbers.indexOf(3));   // 2\n\n// Boolean check:\nconsole.log(numbers.includes(2));  // true\n\n// Find in objects:\nconst people = [{ id: 1, name: 'a' }, { id: 2, name: 'b' }];\nconsole.log(people.find(p => p.id === 2));   // { id: 2, name: 'b' }",
    },
))
d14.append(task_dict(
    'round_decimal',
    [r'\bround\b.*\b(?:decimal\s+places?|to\s+\d+\s+decimals?|2\s+decimals?)\b',
     r'\b(?:to\s+)?2\s+decimal\s+places?\b'],
    "Here's how to round a number to 2 decimal places in {lang}.",
    "JS toFixed returns a STRING — wrap in Number() for arithmetic. Python's round() uses banker's rounding (round-half-to-even); use Decimal for strict financial rounding.",
    {
        'python': "x = 3.14159\n\nprint(round(x, 2))      # 3.14\nprint(round(2.675, 2))  # 2.67 (banker's rounding!)\n\n# Formatting (returns a string):\nprint(f'{x:.2f}')       # 3.14\nprint('%.2f' % x)       # 3.14\n\n# Strict decimal arithmetic (finance):\nfrom decimal import Decimal, ROUND_HALF_UP\nmoney = Decimal('2.675').quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)\nprint(money)            # 2.68",
        'javascript': "const x = 3.14159;\n\n// toFixed returns a STRING:\nconsole.log(x.toFixed(2));            // '3.14'\nconsole.log(Number(x.toFixed(2)));    // 3.14\n\n// Round-then-keep-number (multiply trick):\nconsole.log(Math.round(x * 100) / 100);   // 3.14\n\n// toFixed quirks: (2.675).toFixed(2) === '2.67'\n// For strict finance use a decimal library (decimal.js).\n\n// Round to nearest integer:\nconsole.log(Math.round(3.5));   // 4\nconsole.log(Math.ceil(3.1));    // 4\nconsole.log(Math.floor(3.9));   // 3",
    },
))
d14.append(task_dict(
    'object_length',
    [r'\b(?:length|size)\b.*\bobject\b',
     r'\b(?:number|count)\s+of\s+(?:keys|properties)\b.*\bobject\b',
     r'\bhow\s+many\s+(?:keys|properties)\b'],
    "Here's how to get the number of keys in an object in {lang}.",
    "JS objects don't have a .length — use Object.keys(obj).length. Python's len(dict) counts keys directly.",
    {
        'python': "d = {'a': 1, 'b': 2, 'c': 3}\n\nprint(len(d))      # 3\n\n# Count of values matching a condition:\nprint(sum(1 for v in d.values() if v > 1))   # 2\n\n# Count nested dicts:\nnested = {'x': {'a': 1}, 'y': {'b': 2}}\nprint(len(nested))   # 2 (top level only)",
        'javascript': "const obj = { a: 1, b: 2, c: 3 };\n\nconsole.log(Object.keys(obj).length);    // 3\n\n// Own enumerable string keys only — inherited ones excluded:\nconsole.log(Object.keys({}).length);     // 0\n\n// All keys including non-enumerable (rarely needed):\nconsole.log(Reflect.ownKeys(obj).length);\n\n// Array .length works normally:\nconsole.log([1, 2, 3].length);           // 3",
    },
))
d14.append(task_dict(
    'object_values_loop',
    [r'\bloop\b.*\b(?:object|dictionary|dict)\b.*\bvalues?\b',
     r'\biterate\b.*\b(?:over\s+)?(?:object|dict)\b.*\bvalues?\b'],
    "Here's how to loop over an object's values in {lang}.",
    "JS: Object.values(obj) gives the values; for-in iterates keys (with inherited keys — guard with hasOwnProperty). Python iterates a dict's keys by default; .values() for values.",
    {
        'python': "d = {'a': 1, 'b': 2, 'c': 3}\n\n# Values:\nfor v in d.values():\n    print(v)\n\n# Keys (default iteration):\nfor k in d:\n    print(k)\n\n# Key + value pairs:\nfor k, v in d.items():\n    print(f'{k}: {v}')\n\n# Sum of values:\nprint(sum(d.values()))   # 6",
        'javascript': "const obj = { a: 1, b: 2, c: 3 };\n\n// Values:\nfor (const value of Object.values(obj)) {\n    console.log(value);\n}\n\n// Keys:\nfor (const key of Object.keys(obj)) {\n    console.log(key);\n}\n\n// Entries (key + value):\nfor (const [key, value] of Object.entries(obj)) {\n    console.log(key, value);\n}\n\n// for...in includes inherited keys — usually avoid:\nfor (const key in obj) {\n    if (Object.hasOwn(obj, key)) console.log(key);\n}",
    },
))
d14.append(task_dict(
    'json_stringify',
    [r'\bstringify\b',
     r'\bserialize\b.*\b(?:object|data)\b.*\bjson\b'],
    "Here's how to convert an object to a JSON string in {lang}.",
    "JSON.stringify(obj, null, 2) pretty-prints. It skips functions and undefined, and turns Dates into ISO strings — pass a replacer to customize.",
    {
        'python': "import json\n\ndata = {'name': 'alice', 'age': 30, 'tags': ['a', 'b']}\n\n# Compact:\ns = json.dumps(data)\nprint(s)   # {\"name\": \"alice\", \"age\": 30, \"tags\": [\"a\", \"b\"]}\n\n# Pretty-printed:\nprint(json.dumps(data, indent=2))\n\n# Sort keys:\nprint(json.dumps(data, sort_keys=True))\n\n# Non-ASCII escaped by default; keep unicode with ensure_ascii=False:\nprint(json.dumps({'caf\\u00e9': 1}, ensure_ascii=False))",
        'javascript': "const data = { name: 'alice', age: 30, tags: ['a', 'b'] };\n\n// Compact:\nconst s = JSON.stringify(data);\nconsole.log(s);\n\n// Pretty-printed:\nconsole.log(JSON.stringify(data, null, 2));\n\n// Replacer (pick keys):\nconsole.log(JSON.stringify(data, ['name', 'age']));\n\n// Dates become ISO strings:\nconsole.log(JSON.stringify({ when: new Date() }));\n// {\"when\":\"2026-04-03T15:30:00.000Z\"}",
    },
))
d14.append(task_dict(
    'async_await',
    [r'\basync\s*await\b',
     r'\b(?:async\s+)?function\b.*\b(?:await|asynchronous)\b'],
    "Here's how to use async/await in {lang}.",
    "async functions always return a Promise; await unwraps it. Errors inside async code reject the promise — always handle with try/catch or .catch().",
    {
        'python': "import asyncio\n\nasync def fetch_data(url: str) -> str:\n    # Simulate an async call (real code would use aiohttp/httpx):\n    await asyncio.sleep(0.1)\n    return f'data from {url}'\n\n\nasync def main():\n    try:\n        result = await fetch_data('https://example.com')\n        print(result)\n    except Exception as exc:\n        print(f'failed: {exc}')\n\n\nasyncio.run(main())",
        'javascript': "async function fetchData(url) {\n    // await unwraps the promise:\n    const resp = await fetch(url);\n    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);\n    return resp.json();\n}\n\nasync function main() {\n    try {\n        const data = await fetchData('https://api.example.com');\n        console.log(data);\n    } catch (err) {\n        console.error('failed:', err.message);\n    }\n}\n\nmain();\n\n// async functions always return a Promise:\n// const p = main();  p.catch(...)\n\n// Run several in parallel:\nconst [a, b] = await Promise.all([\n    fetchData('/a'),\n    fetchData('/b'),\n]);",
    },
))
d14.append(task_dict(
    'promise_all',
    [r'\bpromise\.all\b',
     r'\b(?:run|execute|wait\s+for)\b.*\b(?:multiple|several|all)\b.*\b(?:promises?|requests?|calls?)\b'],
    "Here's how to use Promise.all in {lang}.",
    "Promise.all resolves when EVERY promise resolves and rejects fast on the first rejection — use Promise.allSettled when you want results regardless of failures.",
    {
        'python': "import asyncio\n\nasync def fetch(id: int) -> str:\n    await asyncio.sleep(0.1)\n    return f'item {id}'\n\n\nasync def main():\n    # Run concurrently and collect results in order:\n    results = await asyncio.gather(fetch(1), fetch(2), fetch(3))\n    print(results)   # ['item 1', 'item 2', 'item 3']\n\n    # With error handling (return_exceptions=True keeps partial results):\n    results = await asyncio.gather(fetch(1), fetch(2), return_exceptions=True)\n\n\nasyncio.run(main())",
        'javascript': "// Promise.all — resolves when ALL resolve, rejects on the first rejection:\nconst results = await Promise.all([\n    fetch('/a').then(r => r.json()),\n    fetch('/b').then(r => r.json()),\n]);\nconsole.log(results);   // [dataA, dataB] — in order\n\n// With .then():\nPromise.all([p1, p2]).then(\n    ([r1, r2]) => console.log(r1, r2),\n    err => console.error('one failed:', err),\n);\n\n// Promise.allSettled — wait for all, keep failures:\nconst settled = await Promise.allSettled([p1, p2]);\n// [{status: 'fulfilled', value}, {status: 'rejected', reason}]\n\n// Promise.race — first to settle wins:\nconst first = await Promise.race([p1, p2]);",
    },
))
save('14_js_utils.json', d14)
print('14_js_utils.json:', len(d14), 'tasks')

# ── 15_ds_advanced.json ───────────────────────────────────────────────────
d15 = []
d15.append(task_dict(
    'queue_two_stacks',
    [r'\bqueue\b.*\b(?:using|with)\s+two\s+stacks\b',
     r'\btwo\s+stacks\b.*\bqueue\b'],
    "Here's a {lang} queue implemented with two stacks.",
    "Push into stack_in; to pop, if stack_out is empty, drain stack_in into it (reversing order), then pop from stack_out. Amortized O(1) per operation.",
    {
        'python': "class QueueWithStacks:\n    \"\"\"FIFO queue using two stacks (amortized O(1)).\"\"\"\n    def __init__(self):\n        self.stack_in = []\n        self.stack_out = []\n\n    def enqueue(self, item):\n        self.stack_in.append(item)\n\n    def dequeue(self):\n        if not self.stack_out:\n            while self.stack_in:\n                self.stack_out.append(self.stack_in.pop())\n        if not self.stack_out:\n            raise IndexError('dequeue from empty queue')\n        return self.stack_out.pop()\n\n    def peek(self):\n        if not self.stack_out:\n            while self.stack_in:\n                self.stack_out.append(self.stack_in.pop())\n        return self.stack_out[-1]\n\n    def is_empty(self):\n        return not self.stack_in and not self.stack_out\n\n    def __len__(self):\n        return len(self.stack_in) + len(self.stack_out)\n\n# Example:\nq = QueueWithStacks()\nq.enqueue(1); q.enqueue(2); q.enqueue(3)\nprint(q.dequeue())  # 1\nprint(q.dequeue())  # 2",
        'javascript': "class QueueWithStacks {\n    constructor() {\n        this.stackIn = [];\n        this.stackOut = [];\n    }\n\n    enqueue(item) {\n        this.stackIn.push(item);\n    }\n\n    dequeue() {\n        if (this.stackOut.length === 0) {\n            while (this.stackIn.length > 0) {\n                this.stackOut.push(this.stackIn.pop());\n            }\n        }\n        if (this.stackOut.length === 0) throw new Error('empty queue');\n        return this.stackOut.pop();\n    }\n\n    peek() {\n        if (this.stackOut.length === 0) {\n            while (this.stackIn.length > 0) {\n                this.stackOut.push(this.stackIn.pop());\n            }\n        }\n        return this.stackOut[this.stackOut.length - 1];\n    }\n\n    get isEmpty() {\n        return this.stackIn.length === 0 && this.stackOut.length === 0;\n    }\n}\n\nconst q = new QueueWithStacks();\nq.enqueue(1); q.enqueue(2); q.enqueue(3);\nconsole.log(q.dequeue());  // 1\nconsole.log(q.dequeue());  // 2",
    },
))
d15.append(task_dict(
    'stack',
    [r'\b(?:implement|create|build|write|make)\b.*\bstack\b(?!\s+of\s+(?:books|papers?|pancakes?|cards?))',
     r'\bstack\b.*\b(?:push|pop|peek)\b'],
    "Here's a {lang} stack (LIFO) with push, pop, and peek.",
    "A stack is last-in-first-out. Python lists ARE stacks (append/pop). The class version makes the operations explicit and can enforce a max size.",
    {
        'python': "# Python lists are already stacks:\nstack = []\nstack.append(1)      # push\nstack.append(2)\ntop = stack[-1]      # peek\nprint(top)           # 2\npopped = stack.pop() # pop\nprint(popped)        # 2\n\n# Class with a size limit:\nclass Stack:\n    def __init__(self, max_size=None):\n        self._items = []\n        self._max = max_size\n\n    def push(self, item):\n        if self._max is not None and len(self._items) >= self._max:\n            raise OverflowError('stack full')\n        self._items.append(item)\n\n    def pop(self):\n        if not self._items:\n            raise IndexError('pop from empty stack')\n        return self._items.pop()\n\n    def peek(self):\n        return self._items[-1]\n\n    def is_empty(self):\n        return not self._items\n\n    def __len__(self):\n        return len(self._items)",
        'javascript': "class Stack {\n    constructor(maxSize) {\n        this.items = [];\n        this.maxSize = maxSize ?? Infinity;\n    }\n\n    push(item) {\n        if (this.items.length >= this.maxSize) throw new Error('stack full');\n        this.items.push(item);\n    }\n\n    pop() {\n        if (this.items.length === 0) throw new Error('pop from empty stack');\n        return this.items.pop();\n    }\n\n    peek() {\n        return this.items[this.items.length - 1];\n    }\n\n    get isEmpty() {\n        return this.items.length === 0;\n    }\n\n    get size() {\n        return this.items.length;\n    }\n}\n\n// Arrays are stacks too:\nconst s = [];\ns.push(1); s.push(2);\nconsole.log(s.pop());  // 2",
    },
))
d15.append(task_dict(
    'queue',
    [r'\b(?:implement|create|build|write|make)\b.*\bqueue\b(?!.*\btwo\s+stacks\b)',
     r'\bqueue\b.*\b(?:enqueue|dequeue|fifo)\b'],
    "Here's a {lang} queue (FIFO) with enqueue and dequeue.",
    "collections.deque is the right Python tool — appends and popleft are O(1), while list.pop(0) is O(n). JS arrays work with push + shift (O(n) shift) or an index-based queue.",
    {
        'python': "from collections import deque\n\n# deque — O(1) append and popleft:\nq = deque()\nq.append('a')          # enqueue\nq.append('b')\nfirst = q.popleft()    # dequeue\nprint(first)           # 'a'\n\n# Use as a class:\nclass Queue:\n    def __init__(self):\n        self._items = deque()\n\n    def enqueue(self, item):\n        self._items.append(item)\n\n    def dequeue(self):\n        if not self._items:\n            raise IndexError('dequeue from empty queue')\n        return self._items.popleft()\n\n    def peek(self):\n        return self._items[0]\n\n    def is_empty(self):\n        return not self._items\n\n    def __len__(self):\n        return len(self._items)\n\n# Bounded queue: collections.deque(maxlen=n) drops the oldest item.",
        'javascript': "class Queue {\n    constructor() {\n        this.items = [];\n    }\n\n    enqueue(item) {\n        this.items.push(item);\n    }\n\n    dequeue() {\n        if (this.items.length === 0) throw new Error('empty queue');\n        return this.items.shift();   // O(n) — fine for small queues\n    }\n\n    peek() {\n        return this.items[0];\n    }\n\n    get isEmpty() {\n        return this.items.length === 0;\n    }\n\n    get size() {\n        return this.items.length;\n    }\n}\n\n// O(1) alternative: index-based queue\nclass FastQueue {\n    constructor() {\n        this.items = [];\n        this.head = 0;\n    }\n    enqueue(item) { this.items.push(item); }\n    dequeue() {\n        if (this.head >= this.items.length) throw new Error('empty');\n        const item = this.items[this.head++];\n        if (this.head > 1000 && this.head * 2 > this.items.length) {\n            this.items = this.items.slice(this.head);\n            this.head = 0;\n        }\n        return item;\n    }\n}",
    },
))
d15.append(task_dict(
    'trie',
    [r'\btrie\b'],
    "Here's a {lang} trie (prefix tree) with insert, search, and prefix lookup.",
    "A trie stores strings by their prefixes — ideal for autocomplete, spell-check, and prefix matching. Insert/search are O(length of the word), independent of the number of stored words.",
    {
        'python': "class TrieNode:\n    def __init__(self):\n        self.children = {}\n        self.is_end = False\n\n\nclass Trie:\n    def __init__(self):\n        self.root = TrieNode()\n\n    def insert(self, word: str) -> None:\n        node = self.root\n        for ch in word:\n            node = node.children.setdefault(ch, TrieNode())\n        node.is_end = True\n\n    def search(self, word: str) -> bool:\n        node = self._find(word)\n        return node is not None and node.is_end\n\n    def starts_with(self, prefix: str) -> bool:\n        return self._find(prefix) is not None\n\n    def _find(self, prefix: str):\n        node = self.root\n        for ch in prefix:\n            if ch not in node.children:\n                return None\n            node = node.children[ch]\n        return node\n\n# Example:\ntrie = Trie()\ntrie.insert('apple')\nprint(trie.search('apple'))       # True\nprint(trie.search('app'))         # False\nprint(trie.starts_with('app'))    # True",
        'javascript': "class TrieNode {\n    constructor() {\n        this.children = {};\n        this.isEnd = false;\n    }\n}\n\nclass Trie {\n    constructor() {\n        this.root = new TrieNode();\n    }\n\n    insert(word) {\n        let node = this.root;\n        for (const ch of word) {\n            node = node.children[ch] ??= new TrieNode();\n        }\n        node.isEnd = true;\n    }\n\n    search(word) {\n        const node = this._find(word);\n        return !!node && node.isEnd;\n    }\n\n    startsWith(prefix) {\n        return this._find(prefix) !== null;\n    }\n\n    _find(prefix) {\n        let node = this.root;\n        for (const ch of prefix) {\n            if (!(ch in node.children)) return null;\n            node = node.children[ch];\n        }\n        return node;\n    }\n}\n\nconst trie = new Trie();\ntrie.insert('apple');\nconsole.log(trie.search('apple'));    // true\nconsole.log(trie.startsWith('app'));  // true",
    },
))
d15.append(task_dict(
    'min_heap',
    [r'\b(?:min\s+heap|heapify|max\s+heap|heap\s+sort)\b',
     r'\bpriority\s+queue\b(?!.*\\b(?:message|job)\\b)'],
    "Here's how to use a min-heap in {lang}.",
    "heapq gives O(log n) push/pop and O(1) min access. Python heaps are min-heaps by default; negate values for a max-heap. heapq.nlargest/nsmallest are the clean way to get top-k.",
    {
        'python': "import heapq\n\nheap = []\n\n# Push:\nheapq.heappush(heap, 5)\nheapq.heappush(heap, 1)\nheapq.heappush(heap, 3)\n\n# Peek at the min:\nprint(heap[0])        # 1\n\n# Pop the min:\nprint(heapq.heappop(heap))   # 1\n\n# Build a heap from a list in place (O(n)):\nnums = [5, 1, 3, 8, 2]\nheapq.heapify(nums)\n\n# Top-k:\nprint(heapq.nlargest(2, nums))   # [8, 5]\nprint(heapq.nsmallest(2, nums))  # [1, 2]\n\n# Max-heap via negation:\nmaxheap = []\nheapq.heappush(maxheap, -x for x in [5, 1, 3])\nprint(-heapq.heappop(maxheap))   # 5",
        'javascript': "// JS has no built-in heap — this is the classic array-based min-heap:\nclass MinHeap {\n    constructor() {\n        this.heap = [];\n    }\n\n    push(val) {\n        this.heap.push(val);\n        this._siftUp(this.heap.length - 1);\n    }\n\n    pop() {\n        const top = this.heap[0];\n        const last = this.heap.pop();\n        if (this.heap.length > 0) {\n            this.heap[0] = last;\n            this._siftDown(0);\n        }\n        return top;\n    }\n\n    peek() {\n        return this.heap[0];\n    }\n\n    get size() {\n        return this.heap.length;\n    }\n\n    _siftUp(i) {\n        while (i > 0) {\n            const parent = (i - 1) >> 1;\n            if (this.heap[parent] <= this.heap[i]) break;\n            [this.heap[parent], this.heap[i]] = [this.heap[i], this.heap[parent]];\n            i = parent;\n        }\n    }\n\n    _siftDown(i) {\n        const n = this.heap.length;\n        while (true) {\n            let smallest = i;\n            const l = 2 * i + 1, r = 2 * i + 2;\n            if (l < n && this.heap[l] < this.heap[smallest]) smallest = l;\n            if (r < n && this.heap[r] < this.heap[smallest]) smallest = r;\n            if (smallest === i) break;\n            [this.heap[i], this.heap[smallest]] = [this.heap[smallest], this.heap[i]];\n            i = smallest;\n        }\n    }\n}\n\nconst h = new MinHeap();\nh.push(5); h.push(1); h.push(3);\nconsole.log(h.pop());   // 1",
    },
))
d15.append(task_dict(
    'top_k_frequent',
    [r'\btop\s+k\b.*\bfrequent\b',
     r'\bk\s+most\s+frequent\b',
     r'\b(?:most\s+)?frequent\s+(?:elements?|items?|numbers?)\b.*\b(?:top\s+k|k\b)\b'],
    "Here's how to find the k most frequent elements in {lang}.",
    "Counter.most_common(k) is the clean O(n log n) answer. For huge inputs use heapq.nlargest or a heap of size k for O(n log k).",
    {
        'python': "from collections import Counter\n\nnums = [1, 1, 1, 2, 2, 3]\n\n# One-liner:\ntop = [x for x, _ in Counter(nums).most_common(2)]\nprint(top)   # [1, 2]\n\n# Step by step:\ncounts = Counter(nums)\nprint(counts.most_common(2))   # [(1, 3), (2, 2)]\n\n# For very large inputs (heap of size k):\nimport heapq\nitems = counts.items()\nheapq.nlargest(2, items, key=lambda kv: kv[1])\n\n# Words in text:\nwords = 'the cat and the dog and the bird'.split()\nprint([w for w, _ in Counter(words).most_common(3)])",
        'javascript': "const nums = [1, 1, 1, 2, 2, 3];\n\nfunction topKFrequent(nums, k) {\n    const counts = new Map();\n    for (const n of nums) counts.set(n, (counts.get(n) || 0) + 1);\n    return [...counts.entries()]\n        .sort((a, b) => b[1] - a[1])\n        .slice(0, k)\n        .map(([n]) => n);\n}\n\nconsole.log(topKFrequent(nums, 2));   // [1, 2]\n\n// Words in text:\nconst words = 'the cat and the dog and the bird'.split(' ');\nconsole.log(topKFrequent(words, 3));  // ['the', 'and', ...]",
    },
))
d15.append(task_dict(
    'merge_intervals',
    [r'\bmerge\s+intervals\b',
     r'\b(?:overlapping|overlap)\s+intervals\b'],
    "Here's a {lang} function that merges overlapping intervals.",
    "Sort by start, then greedily extend the current interval when the next start is within it. O(n log n) from the sort.",
    {
        'python': "def merge_intervals(intervals: list) -> list:\n    \"\"\"Merge overlapping intervals. Each interval is [start, end].\"\"\"\n    if not intervals:\n        return []\n    intervals.sort(key=lambda x: x[0])\n    merged = [intervals[0]]\n    for start, end in intervals[1:]:\n        last_start, last_end = merged[-1]\n        if start <= last_end:\n            merged[-1] = [last_start, max(last_end, end)]\n        else:\n            merged.append([start, end])\n    return merged\n\n# Example:\nprint(merge_intervals([[1, 3], [2, 6], [8, 10], [15, 18]]))\n# [[1, 6], [8, 10], [15, 18]]",
        'javascript': "function mergeIntervals(intervals) {\n    if (intervals.length === 0) return [];\n    intervals.sort((a, b) => a[0] - b[0]);\n    const merged = [intervals[0]];\n    for (const [start, end] of intervals.slice(1)) {\n        const last = merged[merged.length - 1];\n        if (start <= last[1]) {\n            last[1] = Math.max(last[1], end);\n        } else {\n            merged.push([start, end]);\n        }\n    }\n    return merged;\n}\n\nconsole.log(mergeIntervals([[1, 3], [2, 6], [8, 10], [15, 18]]));\n// [[1, 6], [8, 10], [15, 18]]",
    },
))
d15.append(task_dict(
    'lru_cache',
    [r'\blru\s+cache\b'],
    "Here's an LRU cache in {lang}.",
    "functools.lru_cache is the stdlib solution for memoizing functions. The manual OrderedDict version is what interview questions want: move-to-end on access, evict the front when full.",
    {
        'python': "from functools import lru_cache\nfrom collections import OrderedDict\n\n# 1) Stdlib for memoizing a function:\n@lru_cache(maxsize=128)\ndef expensive(n):\n    return n * n\n\n# 2) Manual LRU cache class (move-to-end on access):\nclass LRUCache:\n    def __init__(self, capacity: int):\n        self.capacity = capacity\n        self.data = OrderedDict()\n\n    def get(self, key: int) -> int:\n        if key not in self.data:\n            return -1\n        self.data.move_to_end(key)      # mark as recently used\n        return self.data[key]\n\n    def put(self, key: int, value: int) -> None:\n        if key in self.data:\n            self.data.move_to_end(key)\n        self.data[key] = value\n        if len(self.data) > self.capacity:\n            self.data.popitem(last=False)  # evict least recently used\n\n# Example:\ncache = LRUCache(2)\ncache.put(1, 1); cache.put(2, 2)\nprint(cache.get(1))      # 1\ncache.put(3, 3)          # evicts key 2\nprint(cache.get(2))      # -1",
        'javascript': "class LRUCache {\n    constructor(capacity) {\n        this.capacity = capacity;\n        this.map = new Map();   // Map preserves insertion order\n    }\n\n    get(key) {\n        if (!this.map.has(key)) return -1;\n        const value = this.map.get(key);\n        this.map.delete(key);       // re-insert to mark as recent\n        this.map.set(key, value);\n        return value;\n    }\n\n    put(key, value) {\n        if (this.map.has(key)) this.map.delete(key);\n        this.map.set(key, value);\n        if (this.map.size > this.capacity) {\n            const oldest = this.map.keys().next().value;\n            this.map.delete(oldest);\n        }\n    }\n}\n\nconst cache = new LRUCache(2);\ncache.put(1, 1); cache.put(2, 2);\nconsole.log(cache.get(1));  // 1\ncache.put(3, 3);            // evicts key 2\nconsole.log(cache.get(2));  // -1",
    },
))
d15.append(task_dict(
    'reverse_linked_list',
    [r'\brevers\w*\b.*\blinked\s+list\b'],
    "Here's a {lang} function that reverses a singly linked list in place.",
    "Iterate with prev/curr/next: save the next node, rewire curr.next to prev, advance. O(n) time, O(1) space — no recursion stack, so it's safe for long lists.",
    {
        'python': "class ListNode:\n    def __init__(self, val=0, next=None):\n        self.val = val\n        self.next = next\n\n\ndef reverse_linked_list(head: ListNode) -> ListNode:\n    prev = None\n    curr = head\n    while curr:\n        nxt = curr.next     # save before rewiring\n        curr.next = prev\n        prev, curr = curr, nxt\n    return prev\n\n# Helper to build + print:\ndef to_list(head):\n    out = []\n    while head:\n        out.append(head.val)\n        head = head.next\n    return out\n\nhead = ListNode(1, ListNode(2, ListNode(3)))\nprint(to_list(reverse_linked_list(head)))  # [3, 2, 1]",
        'javascript': "function reverseLinkedList(head) {\n    let prev = null;\n    let curr = head;\n    while (curr) {\n        const next = curr.next;   // save before rewiring\n        curr.next = prev;\n        prev = curr;\n        curr = next;\n    }\n    return prev;\n}\n\n// Example:\nconst head = { val: 1, next: { val: 2, next: { val: 3, next: null } } };\nfunction toArray(node) {\n    const out = [];\n    while (node) { out.push(node.val); node = node.next; }\n    return out;\n}\nconsole.log(toArray(reverseLinkedList(head)));  // [3, 2, 1]",
    },
))
d15.append(task_dict(
    'linked_list_cycle',
    [r'\b(?:cycle|loop|circular)\b.*\blinked\s+list\b',
     r'\bdetect\b.*\b(?:cycle|loop)\b'],
    "Here's a {lang} function that detects a cycle in a linked list.",
    "Floyd's tortoise-and-hare: the slow pointer moves one step, the fast pointer two. If they meet, there's a cycle. O(n) time, O(1) space.",
    {
        'python': "class ListNode:\n    def __init__(self, val=0, next=None):\n        self.val = val\n        self.next = next\n\n\ndef has_cycle(head: ListNode) -> bool:\n    \"\"\"Floyd's cycle detection (tortoise and hare).\"\"\"\n    slow = fast = head\n    while fast and fast.next:\n        slow = slow.next        # one step\n        fast = fast.next.next   # two steps\n        if slow is fast:\n            return True\n    return False\n\n# Example: build 1 -> 2 -> 3 -> 2 (cycle)\nn3 = ListNode(3)\nn2 = ListNode(2, n3)\nn1 = ListNode(1, n2)\nn3.next = n2\nprint(has_cycle(n1))   # True\nprint(has_cycle(ListNode(1)))  # False",
        'javascript': "function hasCycle(head) {\n    // Floyd's tortoise and hare\n    let slow = head;\n    let fast = head;\n    while (fast && fast.next) {\n        slow = slow.next;\n        fast = fast.next.next;\n        if (slow === fast) return true;\n    }\n    return false;\n}\n\n// Example:\nconst n3 = { val: 3, next: null };\nconst n2 = { val: 2, next: n3 };\nconst n1 = { val: 1, next: n2 };\nn3.next = n2;   // cycle\nconsole.log(hasCycle(n1));  // true",
    },
))
d15.append(task_dict(
    'dijkstra',
    [r"\bdijkstra'?s?\b",
     r'\bshortest\s+path\b(?!.*\\b(?:bfs|unweighted)\\b)'],
    "Here's a {lang} implementation of Dijkstra's shortest-path algorithm.",
    "Dijkstra finds shortest paths in graphs with non-negative edge weights. A priority queue gives O((V + E) log V). For unweighted graphs BFS is faster; for negative weights use Bellman-Ford.",
    {
        'python': "import heapq\n\n\ndef dijkstra(graph: dict, start: str) -> dict:\n    \"\"\"graph: {node: [(neighbor, weight), ...]}. Returns {node: distance}.\"\"\"\n    distances = {node: float('inf') for node in graph}\n    distances[start] = 0\n    pq = [(0, start)]\n    while pq:\n        dist, node = heapq.heappop(pq)\n        if dist > distances[node]:\n            continue\n        for neighbor, weight in graph[node]:\n            new_dist = dist + weight\n            if new_dist < distances[neighbor]:\n                distances[neighbor] = new_dist\n                heapq.heappush(pq, (new_dist, neighbor))\n    return distances\n\n# Example:\ngraph = {\n    'A': [('B', 1), ('C', 4)],\n    'B': [('A', 1), ('C', 2), ('D', 5)],\n    'C': [('A', 4), ('B', 2), ('D', 1)],\n    'D': [('B', 5), ('C', 1)],\n}\nprint(dijkstra(graph, 'A'))   # {'A': 0, 'B': 1, 'C': 3, 'D': 4}",
        'javascript': "function dijkstra(graph, start) {\n    // graph: {node: [[neighbor, weight], ...]}\n    const distances = {};\n    for (const node in graph) distances[node] = Infinity;\n    distances[start] = 0;\n\n    // Simple priority queue via array (use a real heap for big graphs):\n    const pq = [[0, start]];\n    while (pq.length > 0) {\n        pq.sort((a, b) => a[0] - b[0]);\n        const [dist, node] = pq.shift();\n        if (dist > distances[node]) continue;\n        for (const [neighbor, weight] of graph[node]) {\n            const newDist = dist + weight;\n            if (newDist < distances[neighbor]) {\n                distances[neighbor] = newDist;\n                pq.push([newDist, neighbor]);\n            }\n        }\n    }\n    return distances;\n}\n\nconst graph = {\n    A: [['B', 1], ['C', 4]],\n    B: [['A', 1], ['C', 2], ['D', 5]],\n    C: [['A', 4], ['B', 2], ['D', 1]],\n    D: [['B', 5], ['C', 1]],\n};\nconsole.log(dijkstra(graph, 'A'));  // {A: 0, B: 1, C: 3, D: 4}",
    },
))
d15.append(task_dict(
    'bfs_graph',
    [r'\b(?:breadth[- ]first(?:\s+search)?|bfs)\b'],
    "Here's a {lang} implementation of breadth-first search on a graph.",
    "BFS visits nodes in order of distance from the start, using a queue. Track visited to avoid revisiting (and infinite loops in cyclic graphs). For shortest hops in an unweighted graph, BFS is optimal.",
    {
        'python': "from collections import deque\n\n\ndef bfs(graph: dict, start) -> list:\n    \"\"\"graph: {node: [neighbors]}. Returns nodes in BFS order.\"\"\"\n    visited = {start}\n    queue = deque([start])\n    order = []\n    while queue:\n        node = queue.popleft()\n        order.append(node)\n        for neighbor in graph.get(node, []):\n            if neighbor not in visited:\n                visited.add(neighbor)\n                queue.append(neighbor)\n    return order\n\n# Shortest path (number of hops) from start to target:\ndef bfs_shortest_path(graph, start, target):\n    queue = deque([(start, [start])])\n    visited = {start}\n    while queue:\n        node, path = queue.popleft()\n        if node == target:\n            return path\n        for neighbor in graph.get(node, []):\n            if neighbor not in visited:\n                visited.add(neighbor)\n                queue.append((neighbor, path + [neighbor]))\n    return None\n\n# Example:\ngraph = {'A': ['B', 'C'], 'B': ['A', 'D'], 'C': ['A', 'D'], 'D': ['B', 'C']}\nprint(bfs(graph, 'A'))        # ['A', 'B', 'C', 'D']\nprint(bfs_shortest_path(graph, 'A', 'D'))  # ['A', 'B', 'D']",
        'javascript': "function bfs(graph, start) {\n    // graph: {node: [neighbors]}\n    const visited = new Set([start]);\n    const queue = [start];\n    const order = [];\n    while (queue.length > 0) {\n        const node = queue.shift();\n        order.push(node);\n        for (const neighbor of graph[node] || []) {\n            if (!visited.has(neighbor)) {\n                visited.add(neighbor);\n                queue.push(neighbor);\n            }\n        }\n    }\n    return order;\n}\n\nconst graph = {\n    A: ['B', 'C'],\n    B: ['A', 'D'],\n    C: ['A', 'D'],\n    D: ['B', 'C'],\n};\nconsole.log(bfs(graph, 'A'));  // ['A', 'B', 'C', 'D']",
    },
))
d15.append(task_dict(
    'longest_substring_no_repeat',
    [r'\blongest\s+substring\b'],
    "Here's a {lang} function that finds the longest substring without repeating characters.",
    "Sliding window with a set (or a char->index map to jump the left pointer). O(n) time. The map version also gives the window length without clearing.",
    {
        'python': "def length_of_longest_substring(s: str) -> int:\n    \"\"\"Longest substring without repeating characters (sliding window).\"\"\"\n    seen = set()\n    left = 0\n    longest = 0\n    for right, ch in enumerate(s):\n        while ch in seen:\n            seen.remove(s[left])\n            left += 1\n        seen.add(ch)\n        longest = max(longest, right - left + 1)\n    return longest\n\n# Examples:\nprint(length_of_longest_substring('abcabcbb'))  # 3  ('abc')\nprint(length_of_longest_substring('bbbbb'))     # 1  ('b')\nprint(length_of_longest_substring('pwwkew'))    # 3  ('wke')",
        'javascript': "function lengthOfLongestSubstring(s) {\n    const seen = new Set();\n    let left = 0;\n    let longest = 0;\n    for (let right = 0; right < s.length; right++) {\n        const ch = s[right];\n        while (seen.has(ch)) {\n            seen.delete(s[left]);\n            left++;\n        }\n        seen.add(ch);\n        longest = Math.max(longest, right - left + 1);\n    }\n    return longest;\n}\n\nconsole.log(lengthOfLongestSubstring('abcabcbb'));  // 3\nconsole.log(lengthOfLongestSubstring('bbbbb'));     // 1\nconsole.log(lengthOfLongestSubstring('pwwkew'));    // 3",
    },
))
d15.append(task_dict(
    'first_unique_char',
    [r'\bfirst\s+(?:non-?repeating|unique|non-repeated)\s+character\b',
     r'\b(?:first\s+)?non-?repeating\s+character\b'],
    "Here's a {lang} function that finds the first non-repeating character in a string.",
    "Two passes: count with a Counter/Map, then scan for the first character with count 1. O(n) time, O(1) space for fixed alphabets.",
    {
        'python': "from collections import Counter\n\n\ndef first_unique_char(s: str):\n    \"\"\"Return the first non-repeating character, or None.\"\"\"\n    counts = Counter(s)\n    for ch in s:\n        if counts[ch] == 1:\n            return ch\n    return None\n\n# Its index instead:\ndef first_unique_index(s: str) -> int:\n    counts = Counter(s)\n    for i, ch in enumerate(s):\n        if counts[ch] == 1:\n            return i\n    return -1\n\n# Examples:\nprint(first_unique_char('leetcode'))    # 'l'\nprint(first_unique_char('loveleetcode'))  # 'v'\nprint(first_unique_char('aabb'))        # None",
        'javascript': "function firstUniqueChar(s) {\n    const counts = new Map();\n    for (const ch of s) counts.set(ch, (counts.get(ch) || 0) + 1);\n    for (const ch of s) {\n        if (counts.get(ch) === 1) return ch;\n    }\n    return null;\n}\n\nfunction firstUniqueIndex(s) {\n    const counts = new Map();\n    for (const ch of s) counts.set(ch, (counts.get(ch) || 0) + 1);\n    for (let i = 0; i < s.length; i++) {\n        if (counts.get(s[i]) === 1) return i;\n    }\n    return -1;\n}\n\nconsole.log(firstUniqueChar('leetcode'));    // 'l'\nconsole.log(firstUniqueChar('aabb'));        // null",
    },
))
save('15_ds_advanced.json', d15)
print('15_ds_advanced.json:', len(d15), 'tasks')

# ── 16_strings_adv.json ───────────────────────────────────────────────────
d16 = []
d16.append(task_dict(
    'longest_common_prefix',
    [r'\blongest\s+common\s+prefix\b'],
    "Here's a {lang} function that finds the longest common prefix of a list of strings.",
    "Compare character by character across all strings, or sort and compare the first and last strings. Empty input returns an empty string.",
    {
        'python': "def longest_common_prefix(strings: list) -> str:\n    \"\"\"Longest common prefix of a list of strings.\"\"\"\n    if not strings:\n        return ''\n    prefix = strings[0]\n    for s in strings[1:]:\n        while not s.startswith(prefix):\n            prefix = prefix[:-1]\n            if not prefix:\n                return ''\n    return prefix\n\n# Examples:\nprint(longest_common_prefix(['flower', 'flow', 'flight']))  # 'fl'\nprint(longest_common_prefix(['dog', 'racecar', 'car']))     # ''",
        'javascript': "function longestCommonPrefix(strings) {\n    if (strings.length === 0) return '';\n    let prefix = strings[0];\n    for (let i = 1; i < strings.length; i++) {\n        while (!strings[i].startsWith(prefix)) {\n            prefix = prefix.slice(0, -1);\n            if (prefix === '') return '';\n        }\n    }\n    return prefix;\n}\n\nconsole.log(longestCommonPrefix(['flower', 'flow', 'flight']));  // 'fl'\nconsole.log(longestCommonPrefix(['dog', 'racecar', 'car']));     // ''",
    },
))
d16.append(task_dict(
    'run_length_encode',
    [r'\brun[- ]length\b',
     r'\brle\b.*\b(?:encode|decode)\b'],
    "Here's a {lang} run-length encoder.",
    "Run-length encoding compresses runs of repeated characters ('aaabbc' -> 'a3b2c1'). It shines on data with long runs; random data gets bigger.",
    {
        'python': "def run_length_encode(s: str) -> str:\n    \"\"\"'aaabbc' -> 'a3b2c1'\"\"\"\n    if not s:\n        return ''\n    out = []\n    count = 1\n    for i in range(1, len(s)):\n        if s[i] == s[i - 1]:\n            count += 1\n        else:\n            out.append(f'{s[i - 1]}{count}')\n            count = 1\n    out.append(f'{s[-1]}{count}')\n    return ''.join(out)\n\n\ndef run_length_decode(s: str) -> str:\n    \"\"\"'a3b2c1' -> 'aaabbc'\"\"\"\n    import re\n    return ''.join(ch * int(n) for ch, n in re.findall(r'(\\w)(\\d+)', s))\n\n# Examples:\nprint(run_length_encode('aaabbc'))   # a3b2c1\nprint(run_length_decode('a3b2c1'))   # aaabbc\n\n# With itertools:\nfrom itertools import groupby\nprint(''.join(f'{ch}{len(list(g))}' for ch, g in groupby('aaabbc')))",
        'javascript': "function runLengthEncode(s) {\n    let out = '';\n    let count = 1;\n    for (let i = 1; i <= s.length; i++) {\n        if (s[i] === s[i - 1]) {\n            count++;\n        } else {\n            out += s[i - 1] + count;\n            count = 1;\n        }\n    }\n    return out;\n}\n\nfunction runLengthDecode(s) {\n    return s.replace(/(\\w)(\\d+)/g, (_, ch, n) => ch.repeat(Number(n)));\n}\n\nconsole.log(runLengthEncode('aaabbc'));   // a3b2c1\nconsole.log(runLengthDecode('a3b2c1'));   // aaabbc",
    },
))
d16.append(task_dict(
    'reverse_words',
    [r'\brevers\w*\b.*\bwords?\b.*\b(?:sentence|order|phrase)\b'],
    "Here's a {lang} function that reverses the order of words in a sentence.",
    "Split on whitespace, reverse the list, join back. 'the sky is blue' -> 'blue is sky the'. Handle multiple spaces with a regex split.",
    {
        'python': "def reverse_words(sentence: str) -> str:\n    \"\"\"Reverse the ORDER of words, keeping their internal letters.\"\"\"\n    return ' '.join(sentence.split()[::-1])\n\n# Examples:\nprint(reverse_words('the sky is blue'))    # blue is sky the\nprint(reverse_words('  hello   world  '))  # world hello\n\n# Reverse each word but keep the order:\ndef reverse_each_word(sentence: str) -> str:\n    return ' '.join(w[::-1] for w in sentence.split())\n\nprint(reverse_each_word('the sky is blue'))  # eht yks si eulb\n\n# Keep internal spacing (preserve multiple spaces):\nimport re\nprint(' '.join(re.split(r'\\s+', sentence.strip())[::-1]))",
        'javascript': "function reverseWords(sentence) {\n    return sentence.trim().split(/\\s+/).reverse().join(' ');\n}\n\nconsole.log(reverseWords('the sky is blue'));    // 'blue is sky the'\nconsole.log(reverseWords('  hello   world  '));  // 'world hello'\n\n// Reverse each word but keep the order:\nfunction reverseEachWord(sentence) {\n    return sentence.split(/\\s+/).map(w => [...w].reverse().join('')).join(' ');\n}\nconsole.log(reverseEachWord('the sky is blue'));  // 'eht yks si eulb'",
    },
))
d16.append(task_dict(
    'title_case',
    [r'\bconverts?\b.*\bstring\b.*\btitle\s*case\b',
     r'\b(?:convert|change|transform)\b.*\b(?:string|text)\b.*\btitle\s*case\b(?!.*\b(?:lowercase|uppercase)\b)',
     r'\btitle\s*case\b.*\b(?:string|text|word)\b',
     r'\b(?:capitalize|capitalise)\b.*\b(?:each\s+)?word\b.*\b(?:string|text)\b'],
    "Here's how to convert a string to title case in {lang}.",
    "Python's str.title() uppercases after any non-letter (so 'don't' -> 'Don'T'); use a regex or a library for smarter casing. JS has no built-in — split and map.",
    {
        'python': "text = 'hello world, welcome to python'\n\n# Built-in (note the apostrophe quirk):\nprint(text.title())   # Hello World, Welcome To Python\nprint(\"don't stop\".title())   # Don'T Stop  (apostrophe quirk!)\n\n# Word-aware capitalization:\ndef title_case(s: str) -> str:\n    return ' '.join(w.capitalize() for w in s.split())\n\nprint(title_case(text))            # Hello World, Welcome To Python\nprint(title_case(\"don't stop\"))   # Don't Stop\n\n# str.capwords does the same:\nimport string\nprint(string.capwords(text))",
        'javascript': "const text = 'hello world, welcome to python';\n\nfunction titleCase(s) {\n    return s.toLowerCase().split(/\\s+/)\n        .map(w => w.charAt(0).toUpperCase() + w.slice(1))\n        .join(' ');\n}\n\nconsole.log(titleCase(text));   // 'Hello World, Welcome To Python'\n\n// One-liner with a regex:\nconsole.log(text.replace(/\\w\\S*/g, w => w.charAt(0).toUpperCase() + w.slice(1)));",
    },
))
d16.append(task_dict(
    'extract_numbers',
    [r'\bextract\b.*\bnumbers?\b.*\b(?:string|text|sentence)\b',
     r'\bfind\b.*\b(?:all\s+)?numbers?\s+in\b.*\b(?:string|text)\b'],
    "Here's how to extract all numbers from a string in {lang}.",
    "re.findall(r'\\d+', s) grabs digit runs. Include decimals/negatives with a richer pattern like -?\\d+(\\.\\d+)?.",
    {
        'python': "import re\n\ntext = 'Order 42 costs 19.99 dollars, -3 in stock, id: 007'\n\n# Integer runs:\nprint(re.findall(r'\\d+', text))\n# ['42', '19', '99', '3', '007']\n\n# Decimals and negatives:\nprint(re.findall(r'-?\\d+\\.?\\d*', text))\n# ['42', '19.99', '-3', '007']\n\n# As floats:\nprint([float(x) for x in re.findall(r'-?\\d+\\.?\\d*', text)])\n\n# Whole numbers only (not part of a larger number):\nprint(re.findall(r'\\b\\d+\\b', text))\n\n# Numbers >= some threshold:\nprint([int(x) for x in re.findall(r'\\d+', text) if int(x) > 10])",
        'javascript': "const text = 'Order 42 costs 19.99 dollars, -3 in stock, id: 007';\n\n// Integer runs:\nconsole.log(text.match(/\\d+/g));   // ['42', '19', '99', '3', '007']\n\n// Decimals and negatives:\nconsole.log(text.match(/-?\\d+\\.?\\d*/g));\n// ['42', '19.99', '-3', '007']\n\n// As numbers:\nconsole.log(text.match(/-?\\d+\\.?\\d*/g).map(Number));\n\n// Whole numbers only:\nconsole.log(text.match(/\\b\\d+\\b/g));\n\n// Unique sorted:\nconsole.log([...new Set(text.match(/\\d+/g))].sort((a, b) => a - b));",
    },
))
d16.append(task_dict(
    'hex_color_regex',
    [r'\bhex\s+color\b.*\bregex\b',
     r'\bregex\b.*\bhex\s+color\b',
     r'\b(?:match|validate|extract)\b.*\b(?:hex\s+)?colors?\b.*\b(?:regex|from)\b'],
    "Here's a regex for matching hex color codes in {lang}.",
    "#RGB (3 digits) and #RRGGBB (6 digits) are both valid CSS hex colors — optionally with a trailing alpha (#RRGGBBAA). The boundary check avoids matching hex digits inside larger tokens.",
    {
        'python': "import re\n\n# 3 or 6 digits, case-insensitive:\nHEX_COLOR = re.compile(r'#[0-9a-fA-F]{6}\\b|#[0-9a-fA-F]{3}\\b')\n\n# Validate a single color:\ndef is_hex_color(s: str) -> bool:\n    return bool(HEX_COLOR.fullmatch(s.strip()))\n\n# Extract from text:\ntext = 'Use #ff0000 or #F00, and also #1a2b3c, but not #12345'\nprint(HEX_COLOR.findall(text))   # ['#ff0000', '#F00', '#1a2b3c']\n\nprint(is_hex_color('#fff'))      # True\nprint(is_hex_color('#ff0000'))   # True\nprint(is_hex_color('#ff00001'))  # False\n\n# With optional alpha (#RRGGBBAA):\nHEX_WITH_ALPHA = re.compile(r'#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?:[0-9a-fA-F]{2})?\\b')",
        'javascript': "const hexColor = /#[0-9a-fA-F]{6}\\b|#[0-9a-fA-F]{3}\\b/;\n\n// Extract from text:\nconst text = 'Use #ff0000 or #F00, and also #1a2b3c, but not #12345';\nconsole.log(text.match(hexColor));        // first match\nconsole.log(text.match(new RegExp(hexColor.source, 'g')));  // all\n\n// Validate a single color:\nfunction isHexColor(s) {\n    return /^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{3}$/.test(s.trim());\n}\nconsole.log(isHexColor('#fff'));     // true\nconsole.log(isHexColor('#ff0000'));  // true\n\n// With optional alpha:\nconst hexAlpha = /#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?:[0-9a-fA-F]{2})?\\b/;",
    },
))
d16.append(task_dict(
    'validate_date_iso',
    [r'\bvalidate\b.*\bdate\b.*\b(?:yyyy[-/]?mm[-/]?dd|iso|format)\b',
     r'\b(?:check|validate)\b.*\bdate\s+string\b',
     r'\bdate\b.*\b(?:yyyy-mm-dd|YYYY-MM-DD)\b'],
    "Here's how to validate a YYYY-MM-DD date string in {lang}.",
    "Regex only checks the SHAPE — '2023-02-31' passes. Use a real date parser to validate calendar correctness (leap years, month lengths).",
    {
        'python': "from datetime import datetime\n\n\ndef is_valid_date(date_str: str) -> bool:\n    \"\"\"True for real calendar dates in YYYY-MM-DD form.\"\"\"\n    try:\n        datetime.strptime(date_str, '%Y-%m-%d')\n        return True\n    except ValueError:\n        return False\n\n# Shape check first (regex):\nimport re\nshape_ok = re.fullmatch(r'\\d{4}-\\d{2}-\\d{2}', date_str) is not None\n\n# Examples:\nprint(is_valid_date('2023-02-28'))   # True\nprint(is_valid_date('2023-02-31'))   # False (Feb has 28/29 days)\nprint(is_valid_date('2023-13-01'))   # False (month 13)\nprint(is_valid_date('23-02-28'))     # False (wrong shape)\n\n# Range-aware alternative:\ndef is_valid_iso(s: str) -> bool:\n    import re as _re\n    if not _re.fullmatch(r'\\d{4}-\\d{2}-\\d{2}', s):\n        return False\n    y, m, d = map(int, s.split('-'))\n    return 1 <= m <= 12 and 1 <= d <= 31\n\n# Note: is_valid_iso('2023-02-31') is True — use strptime for full checks.",
        "javascript": "function isValidDate(dateStr) {\n    // Shape check first:\n    if (!/^\\d{4}-\\d{2}-\\d{2}$/.test(dateStr)) return false;\n\n    const [y, m, d] = dateStr.split('-').map(Number);\n    const date = new Date(Date.UTC(y, m - 1, d));\n    // Date.UTC rolls over invalid values — compare back:\n    return date.getUTCFullYear() === y &&\n           date.getUTCMonth() === m - 1 &&\n           date.getUTCDate() === d;\n}\n\nconsole.log(isValidDate('2023-02-28'));  // true\nconsole.log(isValidDate('2023-02-31'));  // false\nconsole.log(isValidDate('2023-13-01'));  // false\n\n// Note: new Date('2023-02-31') would roll over to Mar 3 —\n// that's why the round-trip comparison above is needed.",
    },
))
d16.append(task_dict(
    'substring_search',
    [r'\bfind\b.*\bsubstring\b',
     r'\bsubstring\s+(?:search|find|index)\b',
     r'\b(?:index|position)\s+of\s+(?:a\s+)?substring\b'],
    "Here's how to find a substring's position in {lang}.",
    "Python str.find returns -1 when absent; str.index raises ValueError. JS indexOf returns -1; use .search() with regexes. For repeated matches, use finditer (Python) or matchAll (JS).",
    {
        'python': "text = 'the quick brown fox'\n\nprint(text.find('quick'))      # 4\nprint(text.find('zzz'))        # -1\n\n# index() raises when absent:\ntry:\n    print(text.index('quick'))\nexcept ValueError:\n    print('not found')\n\n# Last occurrence:\nprint(text.rfind('o'))         # 15\n\n# All occurrences:\ndef all_indexes(text: str, sub: str):\n    start = 0\n    while True:\n        i = text.find(sub, start)\n        if i == -1:\n            return\n        yield i\n        start = i + 1\n\nprint(list(all_indexes('banana', 'na')))   # [2, 4]\n\n# Case-insensitive:\nprint(text.lower().find('QUICK'.lower()))",
        'javascript': "const text = 'the quick brown fox';\n\nconsole.log(text.indexOf('quick'));   // 4\nconsole.log(text.indexOf('zzz'));     // -1\n\n// Last occurrence:\nconsole.log(text.lastIndexOf('o'));   // 15\n\n// All occurrences:\nfunction allIndexes(text, sub) {\n    const indexes = [];\n    let i = text.indexOf(sub);\n    while (i !== -1) {\n        indexes.push(i);\n        i = text.indexOf(sub, i + 1);\n    }\n    return indexes;\n}\nconsole.log(allIndexes('banana', 'na'));   // [2, 4]\n\n// Case-insensitive:\nconsole.log(text.toLowerCase().indexOf('QUICK'.toLowerCase()));",
    },
))
save('16_strings_adv.json', d16)
print('16_strings_adv.json:', len(d16), 'tasks')

# ── 17_sql_adv.json ───────────────────────────────────────────────────────
d17 = []
d17.append(task_dict(
    'sql_window_rank',
    [r'\bwindow\s+function\b',
     r'\brank\w*\b.*\brows?\b',
     r'\brow_number\b'],
    "Here's a SQL query using a window function to rank rows.",
    "RANK() leaves gaps (1, 1, 3); DENSE_RANK() does not (1, 1, 2); ROW_NUMBER() is unique per row. The OVER clause defines the partition and ordering.",
    {
        'sql': "-- Rank employees by salary within each department:\nSELECT\n    name,\n    department,\n    salary,\n    RANK() OVER (PARTITION BY department ORDER BY salary DESC) AS rank\nFROM employees;\n\n-- DENSE_RANK (no gaps):\nSELECT\n    name,\n    department,\n    salary,\n    DENSE_RANK() OVER (PARTITION BY department ORDER BY salary DESC) AS dense_rank\nFROM employees;\n\n-- ROW_NUMBER (unique per row):\nSELECT\n    name,\n    department,\n    salary,\n    ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC) AS row_num\nFROM employees;\n\n-- Top 2 per department (filter on the window result):\nSELECT * FROM (\n    SELECT\n        name,\n        department,\n        salary,\n        RANK() OVER (PARTITION BY department ORDER BY salary DESC) AS rnk\n    FROM employees\n) ranked\nWHERE rnk <= 2;\n\n-- Running total (another window function):\nSELECT\n    date,\n    amount,\n    SUM(amount) OVER (ORDER BY date) AS running_total\nFROM sales;"
    },
))
d17.append(task_dict(
    'sql_cte',
    [r'\bcommon\s+table\s+expression\b',
     r'\b(?:cte|ctes)\b',
     r'\bwith\s+(?:a\s+)?cte\b'],
    "Here's a SQL query using a common table expression (CTE).",
    "CTEs (WITH clauses) name a subquery you can reference multiple times — the cleanest way to write multi-step queries. Unlike subqueries they can be recursive.",
    {
        'sql': "-- Name a subquery and reuse it:\nWITH high_earners AS (\n    SELECT department, AVG(salary) AS avg_salary\n    FROM employees\n    GROUP BY department\n    HAVING AVG(salary) > 80000\n)\nSELECT e.name, e.salary, h.avg_salary\nFROM employees e\nJOIN high_earners h ON e.department = h.department;\n\n-- Multiple CTEs, comma-separated:\nWITH dept_counts AS (\n    SELECT department, COUNT(*) AS emp_count\n    FROM employees\n    GROUP BY department\n),\ntop_depts AS (\n    SELECT department\n    FROM dept_counts\n    ORDER BY emp_count DESC\n    LIMIT 3\n)\nSELECT * FROM top_depts;\n\n-- Recursive CTE (numbers 1..10):\nWITH RECURSIVE nums(n) AS (\n    SELECT 1\n    UNION ALL\n    SELECT n + 1 FROM nums WHERE n < 10\n)\nSELECT * FROM nums;"
    },
))
d17.append(task_dict(
    'sql_create_index',
    [r'\bcreate\s+(?:an?\s+)?index\b',
     r'\badd\s+(?:an?\s+)?index\b',
     r'\bindex\b.*\b(?:column|table)\b.*\bsql\b'],
    "Here's how to create an index in SQL.",
    "Indexes speed up lookups at the cost of write speed and disk. Index columns used in WHERE/JOIN/ORDER BY. Unique indexes also enforce uniqueness. Only create what queries actually need.",
    {
        'sql': "-- Basic index:\nCREATE INDEX idx_employees_last_name ON employees (last_name);\n\n-- Composite (multi-column) index — leftmost-prefix rules apply:\nCREATE INDEX idx_orders_customer_date\n    ON orders (customer_id, order_date);\n\n-- Unique index (also enforces uniqueness):\nCREATE UNIQUE INDEX idx_users_email ON users (email);\n\n-- Partial index (PostgreSQL — only matching rows):\nCREATE INDEX idx_orders_pending ON orders (created_at)\n    WHERE status = 'pending';\n\n-- Check which indexes exist (PostgreSQL):\nSELECT indexname, tablename FROM pg_indexes\nWHERE tablename = 'employees';\n\n-- Drop an index:\nDROP INDEX idx_employees_last_name;\n\n-- Note: PRIMARY KEY and UNIQUE constraints already create indexes."
    },
))
d17.append(task_dict(
    'sql_case',
    [r'\bcase\s+(?:statement|when|expression)\b',
     r'\bcase\s+when\b',
     r'\bif[- ]then[- ]else\b.*\bsql\b'],
    "Here's how to write a CASE statement in SQL.",
    "CASE is SQL's if/else: a searched form (CASE WHEN cond THEN ...) and a simple form (CASE expr WHEN value THEN ...). ELSE is optional and defaults to NULL.",
    {
        'sql': "-- Searched CASE (conditions):\nSELECT\n    name,\n    salary,\n    CASE\n        WHEN salary > 100000 THEN 'high'\n        WHEN salary > 60000  THEN 'mid'\n        ELSE 'low'\n    END AS salary_band\nFROM employees;\n\n-- Simple CASE (equality):\nSELECT\n    order_id,\n    CASE status\n        WHEN 'pending'  THEN 'awaiting payment'\n        WHEN 'shipped'  THEN 'on its way'\n        WHEN 'delivered' THEN 'complete'\n        ELSE 'unknown'\n    END AS status_label\nFROM orders;\n\n-- CASE in aggregation (conditional count):\nSELECT\n    department,\n    COUNT(CASE WHEN salary > 80000 THEN 1 END) AS high_earners\nFROM employees\nGROUP BY department;\n\n-- CASE in ORDER BY (custom sort order):\nSELECT * FROM tasks\nORDER BY CASE priority\n    WHEN 'urgent' THEN 1\n    WHEN 'high'   THEN 2\n    WHEN 'normal' THEN 3\n    ELSE 4\nEND;"
    },
))
d17.append(task_dict(
    'sql_subquery',
    [r'\bsubquery\b',
     r'\bsub[- ]?query\b',
     r'\bnested\s+query\b'],
    "Here's how to write a SQL query with a subquery.",
    "A subquery is a SELECT inside another query — in WHERE (scalar or IN), FROM (derived table), or SELECT (scalar). Correlated subqueries reference the outer row.",
    {
        'sql': "-- Subquery in WHERE (IN):\nSELECT name, department\nFROM employees\nWHERE department_id IN (\n    SELECT id FROM departments WHERE location = 'Berlin'\n);\n\n-- Scalar subquery (returns one value):\nSELECT\n    name,\n    salary,\n    (SELECT AVG(salary) FROM employees) AS company_avg\nFROM employees;\n\n-- Subquery in FROM (derived table):\nSELECT dept, avg_salary\nFROM (\n    SELECT department AS dept, AVG(salary) AS avg_salary\n    FROM employees\n    GROUP BY department\n) dept_stats\nWHERE avg_salary > 75000;\n\n-- Correlated subquery (per outer row):\nSELECT e1.name, e1.salary\nFROM employees e1\nWHERE e1.salary = (\n    SELECT MAX(e2.salary)\n    FROM employees e2\n    WHERE e2.department = e1.department\n);"
    },
))
d17.append(task_dict(
    'sql_second_highest',
    [r'\bsecond\s+(?:highest|largest|maximum|biggest)\b'],
    "Here's how to find the second-highest value in SQL.",
    "ORDER BY + LIMIT/OFFSET is the direct way. The correlated COUNT version is more portable (works where LIMIT isn't available) and handles ties explicitly.",
    {
        'sql': "-- Second highest salary (SQLite/PostgreSQL/MySQL):\nSELECT salary\nFROM employees\nORDER BY salary DESC\nLIMIT 1 OFFSET 1;\n\n-- Same with a subquery (avoids the highest row):\nSELECT MAX(salary)\nFROM employees\nWHERE salary < (SELECT MAX(salary) FROM employees);\n\n-- Nth highest generically (OFFSET n-1):\nSELECT salary\nFROM employees\nORDER BY salary DESC\nLIMIT 1 OFFSET 3;   -- 4th highest\n\n-- NULL-safe: if fewer than 2 employees, returns no row."
    },
))
d17.append(task_dict(
    'sql_top_n',
    [r'\btop\s+(?:\d+|n)\b.*\b(?:rows?|records?|salaries?)\b',
     r'\b(?:first|top)\s+\d+\s+records?\b'],
    "Here's how to get the top N rows in SQL.",
    "LIMIT n (SQLite/PostgreSQL/MySQL) truncates the result; FETCH FIRST n ROWS ONLY is the standard SQL way. Always pair with ORDER BY or the 'top N' is arbitrary.",
    {
        'sql': "-- Top 10 by salary (SQLite / PostgreSQL / MySQL):\nSELECT *\nFROM employees\nORDER BY salary DESC\nLIMIT 10;\n\n-- Standard SQL:\nSELECT *\nFROM employees\nORDER BY salary DESC\nFETCH FIRST 10 ROWS ONLY;\n\n-- With ties (keeps rows equal to the 10th value):\nSELECT *\nFROM employees\nORDER BY salary DESC\nFETCH FIRST 10 ROWS WITH TIES;\n\n-- Top N per group (window function):\nSELECT * FROM (\n    SELECT *,\n           ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC) AS rn\n    FROM employees\n) t\nWHERE rn <= 3;"
    },
))
d17.append(task_dict(
    'sql_join_three',
    [r'\bjoin\s+(?:three|3)\s+tables\b'],
    "Here's how to join three tables in SQL.",
    "Chain joins with ON conditions — each ON pairs the two tables being joined at that step. Use LEFT JOIN when a table may have no matching rows.",
    {
        'sql': "-- orders -> customers -> products:\nSELECT\n    o.id AS order_id,\n    c.name AS customer,\n    p.name AS product,\n    o.quantity\nFROM orders o\nJOIN customers c ON o.customer_id = c.id\nJOIN products  p ON o.product_id = p.id;\n\n-- With LEFT JOINs (keep orders even without a product):\nSELECT\n    o.id AS order_id,\n    c.name AS customer,\n    COALESCE(p.name, 'deleted product') AS product\nFROM orders o\nJOIN customers c ON o.customer_id = c.id\nLEFT JOIN products p ON o.product_id = p.id;\n\n-- Join order matters for performance, not the result (query planner):\nSELECT e.name, d.name AS dept, r.role\nFROM employees e\nJOIN departments d ON e.department_id = d.id\nJOIN roles r ON e.role_id = r.id;"
    },
))
d17.append(task_dict(
    'sql_left_join',
    [r'\bleft\s+(?:outer\s+)?join\b'],
    "Here's how to use a LEFT JOIN in SQL.",
    "LEFT JOIN keeps every row from the left table; unmatched right-side rows get NULLs. Use it to find missing matches (WHERE right.id IS NULL).",
    {
        'sql': "-- All customers with their orders (NULL when none):\nSELECT c.name, o.id AS order_id, o.total\nFROM customers c\nLEFT JOIN orders o ON c.id = o.customer_id;\n\n-- Customers with NO orders:\nSELECT c.name\nFROM customers c\nLEFT JOIN orders o ON c.id = o.customer_id\nWHERE o.id IS NULL;\n\n-- Count orders per customer (0 for none — LEFT JOIN + GROUP BY):\nSELECT\n    c.name,\n    COUNT(o.id) AS order_count\nFROM customers c\nLEFT JOIN orders o ON c.id = o.customer_id\nGROUP BY c.id, c.name;\n\n-- RIGHT JOIN is the mirror image; many teams avoid it for readability.\n-- FULL OUTER JOIN keeps both sides (SQLite/PostgreSQL support it)."
    },
))
save('17_sql_adv.json', d17)
print('17_sql_adv.json:', len(d17), 'tasks')

# ── 18_devops.json ────────────────────────────────────────────────────────
d18 = []
d18.append(task_dict(
    'dockerfile',
    [r'\bdockerfile\b'],
    "Here's a Dockerfile for a Python application.",
    "Use a slim base, install dependencies via requirements.txt (or pip install -e . for an editable package), and prefer COPY over ADD. Multi-stage builds shrink the final image.",
    {
        'bash': "FROM python:3.12-slim\n\n# Set the working directory\nWORKDIR /app\n\n# Install dependencies first (caches the layer when requirements.txt changes)\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\n\n# Copy the application code\nCOPY . .\n\n# Non-root user (security)\nRUN useradd --create-home appuser\nUSER appuser\n\n# Expose the port your app listens on\nEXPOSE 8000\n\n# Run the app\nCMD [\"uvicorn\", \"app.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]\n\n# Build:   docker build -t myapp .\n# Run:     docker run -p 8000:8000 myapp"
    },
))
d18.append(task_dict(
    'docker_compose',
    [r'\bdocker[- ]compose\b'],
    "Here's a docker-compose.yml for a web app with a database.",
    "Compose orchestrates multi-container apps. Services get their own network; the app reaches the db at the service name (db:5432). Volumes persist data across restarts.",
    {
        'bash': "version: '3.9'\n\nservices:\n  db:\n    image: postgres:16\n    environment:\n      POSTGRES_USER: app\n      POSTGRES_PASSWORD: secret\n      POSTGRES_DB: myapp\n    volumes:\n      - db_data:/var/lib/postgresql/data\n    healthcheck:\n      test: ['CMD-SHELL', 'pg_isready -U app']\n      interval: 5s\n      timeout: 3s\n      retries: 5\n\n  web:\n    build: .\n    ports:\n      - '8000:8000'\n    environment:\n      DATABASE_URL: postgresql://app:secret@db:5432/myapp\n    depends_on:\n      db:\n        condition: service_healthy\n    volumes:\n      - .:/app          # live-reload during development\n\nvolumes:\n  db_data:\n\n# Up:      docker compose up\n# Build:   docker compose up --build\n# Logs:    docker compose logs -f web"
    },
))
d18.append(task_dict(
    'github_actions',
    [r'\bgithub\s+actions\b',
     r'\b(?:ci\s+)?(?:workflow|pipeline)\b.*\b(?:tests?|build|deploy)\b'],
    "Here's a GitHub Actions workflow that runs tests on push.",
    "Workflows live in .github/workflows/*.yml. on: triggers (push, pull_request); jobs run in parallel by default — use needs: to chain them. setup-python caches dependencies for you.",
    {
        'bash': "name: CI\n\non:\n  push:\n    branches: [main]\n  pull_request:\n\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n\n      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.12'\n          cache: 'pip'\n\n      - name: Install dependencies\n        run: |\n          pip install -r requirements-dev.txt\n\n      - name: Run tests\n        run: pytest\n\n      - name: Lint\n        run: ruff check .\n\n  deploy:\n    needs: test            # only after tests pass\n    runs-on: ubuntu-latest\n    if: github.ref == 'refs/heads/main'\n    steps:\n      - uses: actions/checkout@v4\n      - name: Deploy\n        run: ./deploy.sh\n        env:\n          API_TOKEN: ${{ secrets.API_TOKEN }}"
    },
))
d18.append(task_dict(
    'gitignore',
    [r'\bgitignore\b',
     r'\bgit\s+ignore\s+file\b'],
    "Here's a .gitignore for a Python project.",
    "Ignore generated files, caches, virtualenvs, and secrets — never commit credentials. Patterns are relative to the .gitignore's directory; ! re-includes.",
    {
        'bash': "# Byte-compiled / cache\n__pycache__/\n*.py[cod]\n*.egg-info/\n.pytest_cache/\n.ruff_cache/\n.mypy_cache/\n\n# Virtual environments\nvenv/\n.venv/\nenv/\n\n# Build artifacts\ndist/\nbuild/\n*.egg\n\n# IDE / editor\n.vscode/\n.idea/\n*.swp\n.DS_Store\n\n# Logs / runtime\ndata/cache/\n*.log\n.env\n*.pid\n\n# Keep the .env.example template if you commit one:\n!.env.example"
    },
))
d18.append(task_dict(
    'setup_py',
    [r'\bsetup\.py\b',
     r'\b(?:create|write|generate)\b.*\b(?:package|packaging)\b.*\b(?:setup|pyproject)\b'],
    "Here's a setup.py for a Python package.",
    "Modern projects prefer pyproject.toml (PEP 621) — setup.py still works but is legacy. For a simple package, setuptools with find_packages() is the standard layout.",
    {
        'bash': "from setuptools import setup, find_packages\n\nsetup(\n    name='my-package',\n    version='0.1.0',\n    description='A short description',\n    packages=find_packages(exclude=['tests*']),\n    python_requires='>=3.10',\n    install_requires=[\n        'requests>=2.31',\n    ],\n    extras_require={\n        'dev': ['pytest', 'ruff'],\n    },\n    entry_points={\n        'console_scripts': [\n            'mycli=my_package.cli:main',\n        ],\n    },\n)\n\n# Modern equivalent: pyproject.toml\n# [build-system]\n# requires = ['setuptools>=61']\n# build-backend = 'setuptools.build_meta'\n#\n# [project]\n# name = 'my-package'\n# version = '0.1.0'\n# requires-python = '>=3.10'\n# dependencies = ['requests>=2.31']"
    },
))
d18.append(task_dict(
    'cron_job',
    [r'\bcron\b'],
    "Here's how to schedule a cron job that runs a script daily.",
    "crontab -e edits your user's schedule. The five fields are minute hour day-of-month month day-of-week. Redirect output (>> log 2>&1) so cron errors are visible, and use absolute paths.",
    {
        'bash': "# Edit your crontab:\n#   crontab -e\n\n# Run every day at 2:30am:\n30 2 * * * /usr/bin/python3 /home/me/scripts/backup.py >> /home/me/backup.log 2>&1\n\n# Every hour:\n0 * * * * /home/me/scripts/hourly.sh\n\n# Every Monday at 9am:\n0 9 * * 1 /home/me/scripts/weekly_report.sh\n\n# Every 15 minutes:\n*/15 * * * * /home/me/scripts/ping.sh\n\n# Field order: minute(0-59) hour(0-23) dom(1-31) month(1-12) dow(0-7, 0/7=Sun)\n\n# List your jobs:\n#   crontab -l\n\n# Remove all your jobs:\n#   crontab -r\n\n# Scripts should use absolute paths and set their own PATH:\n#!/bin/bash\ncd /home/me && ./scripts/backup.py >> /home/me/backup.log 2>&1"
    },
))
d18.append(task_dict(
    'systemd_service',
    [r'\bsystemd\b',
     r'\b(?:create|write|make)\b.*\bservice\s+file\b'],
    "Here's a systemd service unit for a Python app.",
    "Units live in /etc/systemd/system/ (root) or ~/.config/systemd/user/. After writing one: systemctl daemon-reload, then enable --now. Restart=on-failure brings the app back automatically.",
    {
        'bash': "# /etc/systemd/system/myapp.service\n[Unit]\nDescription=My Python application\nAfter=network.target\n\n[Service]\nType=simple\nUser=www-data\nWorkingDirectory=/opt/myapp\nEnvironmentFile=/etc/myapp.env\nExecStart=/opt/myapp/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000\nRestart=on-failure\nRestartSec=5\n\n# Hardening (optional but recommended):\nNoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=full\n\n[Install]\nWantedBy=multi-user.target\n\n# Commands:\n#   sudo systemctl daemon-reload\n#   sudo systemctl enable --now myapp\n#   sudo systemctl status myapp\n#   sudo journalctl -u myapp -f      # logs\n#   sudo systemctl restart myapp"
    },
))
d18.append(task_dict(
    'inotify_watch',
    [r'\bwatch\b.*\b(?:file|directory|folder)\b.*\b(?:changes?|inotify)\b',
     r'\binotify(?:wait)?\b'],
    "Here's how to watch a file for changes in {lang}.",
    "inotifywait (inotify-tools) is the classic CLI watcher. For scripts, a polling loop with stat is portable; Python's watchdog library is the batteries-included option.",
    {
        'bash': "# inotify-tools (apt install inotify-tools):\n# Run a command every time a file in the directory changes:\ninotifywait -m -r -e modify,create,delete /path/to/dir |\nwhile read path event file; do\n    echo \"$event: $path$file\"\n    ./your-handler.sh \"$path$file\"\ndone\n\n# Watch a single file:\ninotifywait -m -e modify /var/log/app.log\n\n# One-shot (exit after the first event):\ninotifywait -e modify /var/log/app.log && echo changed\n\n# Portable fallback: poll mtime every second\n#!/bin/bash\nLAST=$(stat -c %Y /path/to/file)\nwhile true; do\n    NOW=$(stat -c %Y /path/to/file)\n    if [ \"$NOW\" != \"$LAST\" ]; then\n        echo \"file changed\"\n        LAST=$NOW\n    fi\n    sleep 1\ndone"
    },
))
d18.append(task_dict(
    'tar_compress',
    [r'\b(?:compress|archive)\b.*\btar\b',
     r'\btar\b.*\b(?:compress|archive|extract|backup)\b'],
    "Here's how to compress a directory with tar in {lang}.",
    "tar -czf creates a gzipped archive; -xzf extracts. Always test with -tzf (list). Use -C to avoid storing absolute paths, and -z for gzip vs -j for bzip2.",
    {
        'bash': "# Create a gzipped archive of a directory:\ntar -czf myproject.tar.gz myproject/\n\n# Extract it:\ntar -xzf myproject.tar.gz\n\n# List contents (verify before extracting):\ntar -tzf myproject.tar.gz\n\n# Compress from the parent dir so paths stay relative:\ncd /home/me && tar -czf myproject.tar.gz myproject\n\n# Exclude files:\ntar -czf myproject.tar.gz --exclude='*.log' --exclude='node_modules' myproject\n\n# bzip2 (smaller, slower):\ntar -cjf myproject.tar.bz2 myproject\n\n# Extract to a specific directory:\ntar -xzf myproject.tar.gz -C /tmp"
    },
))
d18.append(task_dict(
    'grep_recursive',
    [r'\bgrep\b.*\brecursi\w+\b',
     r'\bgrep\s+-r\b',
     r'\bsearch\b.*\b(?:all\s+)?files\b.*\b(?:recursive|for\s+a\s+pattern|grep)\b'],
    "Here's how to grep recursively for a pattern in {lang}.",
    "grep -r searches recursively; -n shows line numbers, -i ignores case, -l lists only filenames. Use rg (ripgrep) for speed — it respects .gitignore.",
    {
        'bash': "# Recursive search in the current directory:\ngrep -rn \"TODO\" .\n\n# Case-insensitive, with line numbers:\ngrep -rni \"error\" src/\n\n# Only filenames containing the match:\ngrep -rl \"FIXME\" .\n\n# Whole-word matches only:\ngrep -rnw \"class\" src/\n\n# Extended regex (-E) or fixed strings (-F):\ngrep -rnE \"error|fail\" logs/\ngrep -rnF \"literal.dots\" .\n\n# Exclude directories:\ngrep -rn \"TODO\" . --exclude-dir=node_modules --exclude-dir=.git\n\n# Count matches per file:\ngrep -rc \"error\" logs/\n\n# Ripgrep (faster, respects .gitignore):\nrg -n \"TODO\" src/"
    },
))
d18.append(task_dict(
    'tail_follow',
    [r'\b(?:last\s+\d+\s+lines?|tail)\b.*\b(?:log\s+)?file\b.*\bfollow\b',
     r'\btail\s+-f\b'],
    "Here's how to show the last N lines of a log and follow new ones in {lang}.",
    "tail -n 50 shows the last 50 lines; tail -f (or -F — handles log rotation) follows new appends. Combine: tail -n 50 -f. head -n 50 shows the first lines.",
    {
        'bash': "# Last 50 lines, then follow new output:\ntail -n 50 -f app.log\n\n# Just the last 50 lines (no follow):\ntail -n 50 app.log\n\n# Follow only (defaults to last 10 lines):\ntail -f app.log\n\n# Follow with retries — survives log rotation (-F):\ntail -F app.log\n\n# First 50 lines:\nhead -n 50 app.log\n\n# Follow multiple files:\ntail -f app.log web.log\n\n# Filter what you follow:\ntail -f app.log | grep --line-buffered ERROR"
    },
))
d18.append(task_dict(
    'ffmpeg_mp4_gif',
    [r'\bffmpeg\b',
     r'\b(?:mp4|webm|video)\b.*\bgif\b'],
    "Here's how to convert an MP4 to a GIF with ffmpeg in {lang}.",
    "GIFs are huge — keep the source short, scale it down, and drop the framerate. A palette-based conversion (two-pass) gives the best quality for the size.",
    {
        'bash': "# Simple conversion:\nffmpeg -i input.mp4 output.gif\n\n# Smaller, smoother (scale + framerate):\nffmpeg -i input.mp4 -vf \"fps=10,scale=480:-1:flags=lanczos\" output.gif\n\n# Best quality per byte (palette method):\nffmpeg -i input.mp4 -vf \"fps=10,scale=480:-1:flags=lanczos,palettegen\" palette.png\nffmpeg -i input.mp4 -i palette.png -lavfi \"fps=10,scale=480:-1:flags=lanczos[x];[x][1:v]paletteuse\" output.gif\n\n# Loop only once (default is infinite):\nffmpeg -i input.mp4 -loop 1 output.gif\n\n# First 5 seconds only:\nffmpeg -ss 0 -t 5 -i input.mp4 output.gif\n\n# Audio extraction:\nffmpeg -i input.mp4 -q:a 0 -map a audio.mp3"
    },
))
d18.append(task_dict(
    'find_delete_old',
    [r'\bfind\b.*\bdelete\b.*\b(?:older|days|mtime)\b',
     r'\bdelete\b.*\bfiles?\b.*\b(?:older|mtime|days)\b'],
    "Here's how to find and delete files older than N days in {lang}.",
    "find -mtime +30 matches files modified more than 30 days ago. Test with -print first, then swap in -delete (or -exec rm {} +). -mtime counts 24h periods; -mmin works in minutes.",
    {
        'bash': "# List files modified more than 30 days ago (dry run):\nfind /var/log -type f -mtime +30 -print\n\n# Delete them:\nfind /var/log -type f -mtime +30 -delete\n\n# Delete via exec (more portable, verbose):\nfind /var/log -type f -mtime +30 -exec rm {} \\;\n\n# Also remove now-empty directories:\nfind /var/log -type d -empty -delete\n\n# Minutes instead of days:\nfind /tmp -type f -mmin +120 -delete\n\n# Exclude a path:\nfind /var/log -type f -mtime +30 -not -path '*/important/*' -delete\n\n# Combine with a file-size floor:\nfind . -type f -size +100M -mtime +30 -delete"
    },
))
d18.append(task_dict(
    'rsync_sync',
    [r'\brsync\b(?!.*\bbackup\b)',
     r'\bsync\b.*\b(?:remote\s+)?(?:server|host)\b.*\brsync\b'],
    "Here's how to sync a directory to a remote server with rsync in {lang}.",
    "rsync copies only changed files (delta transfer). Trailing slashes matter: src/ copies CONTENTS into dst; src copies the directory itself. -a preserves permissions and timestamps.",
    {
        'bash': "# Push to a remote server:\nrsync -avz ./project/ user@server:/srv/project/\n\n# Pull from remote:\nrsync -avz user@server:/srv/project/ ./project/\n\n# -a archive (recursive + permissions), -v verbose, -z compress\n\n# Dry run (see what WOULD transfer):\nrsync -avzn ./project/ user@server:/srv/project/\n\n# Delete files on the destination that no longer exist locally:\nrsync -avz --delete ./project/ user@server:/srv/project/\n\n# Exclude junk:\nrsync -avz --exclude node_modules --exclude .git ./project/ user@server:/srv/project/\n\n# Over SSH with a custom port:\nrsync -avz -e 'ssh -p 2222' ./project/ user@server:/srv/project/\n\n# Local mirror (e.g. backup to an external drive):\nrsync -av --delete ~/Documents/ /mnt/backup/Documents/"
    },
))
d18.append(task_dict(
    'bash_loop_files',
    [r'\b(?:loop|iterate|for\s+loop)\b.*\bfiles?\b.*\b(?:directory|folder)\b',
     r'\b(?:loop|iterate)\b.*\b(?:directory|folder)\b.*\bfiles?\b'],
    "Here's how to loop over files in a directory in {lang}.",
    "The glob pattern approach handles spaces in filenames safely (quote \"$f\"). For recursive iteration use find ... | while read or ** globbing.",
    {
        'bash': "#!/bin/bash\n# Loop over every .txt file in the current directory:\nfor f in *.txt; do\n    echo \"processing $f\"\n    # wc -l \"$f\"   # quote \"$f\" — filenames may contain spaces!\ndone\n\n# Loop over ALL files (not just a pattern):\nfor f in *; do\n    [ -f \"$f\" ] || continue    # skip directories\n    echo \"$f\"\ndone\n\n# Recursive (find + while read):\nfind . -name '*.py' -print0 | while IFS= read -r -d '' f; do\n    echo \"$f\"\ndone\n\n# With a counter:\ni=0\nfor f in *.log; do\n    (( i++ ))\n    echo \"[$i] $f\"\ndone\n\n# Python version:\n# import glob\n# for path in glob.glob('*.txt'):\n#     print(path)"
    },
))
save('18_devops.json', d18)
print('18_devops.json:', len(d18), 'tasks')

# ── 19_testing.json ───────────────────────────────────────────────────────
d19 = []
d19.append(task_dict(
    'pytest_test',
    [r'\bpytest\b'],
    "Here's how to write a pytest test for a Python function.",
    "Test functions start with test_; assert raises/fixtures are the pytest way. Run with `pytest` or `pytest -k name`. Parametrize covers multiple inputs in one test.",
    {
        'python': "# app.py (the code under test):\ndef add(a, b):\n    return a + b\n\n# test_app.py:\nimport pytest\nfrom app import add\n\n\ndef test_add_positive_numbers():\n    assert add(2, 3) == 5\n\n\ndef test_add_negative_numbers():\n    assert add(-1, 1) == 0\n\n\n# Parametrize — one test, many cases:\n@pytest.mark.parametrize('a,b,expected', [\n    (2, 3, 5),\n    (0, 0, 0),\n    (-1, -1, -2),\n])\ndef test_add_cases(a, b, expected):\n    assert add(a, b) == expected\n\n\n# Testing that an error is raised:\ndef divide(a, b):\n    if b == 0:\n        raise ZeroDivisionError('cannot divide by zero')\n    return a / b\n\n\ndef test_divide_by_zero_raises():\n    with pytest.raises(ZeroDivisionError):\n        divide(1, 0)\n\n# Run:  pytest test_app.py -v",
        'javascript': "// Jest equivalent (see the jest task) — pytest is Python-only.",
    },
))
d19.append(task_dict(
    'jest_test',
    [r'\bjest\b'],
    "Here's how to write a unit test in JavaScript with Jest.",
    "describe/test/it structure the suite; expect(...).toBe(...) asserts. jest.fn() creates mocks; jest.mock replaces modules. Run with `npm test` (configured to use jest).",
    {
        'javascript': "// utils.js (code under test):\nfunction add(a, b) {\n    return a + b;\n}\nmodule.exports = { add };\n\n// utils.test.js:\nconst { add } = require('./utils');\n\ndescribe('add', () => {\n    it('adds positive numbers', () => {\n        expect(add(2, 3)).toBe(5);\n    });\n\n    it('adds negatives', () => {\n        expect(add(-1, 1)).toBe(0);\n    });\n\n    it.each([\n        [2, 3, 5],\n        [0, 0, 0],\n        [-1, -1, -2],\n    ])('adds %i + %i = %i', (a, b, expected) => {\n        expect(add(a, b)).toBe(expected);\n    });\n});\n\n// package.json needs:\n// {\"scripts\": {\"test\": \"jest\"}, \"devDependencies\": {\"jest\": \"^29\"}}\n\n// Async tests:\nit('fetches data', async () => {\n    const data = await fetchData();\n    expect(data).toHaveProperty('ok', true);\n});\n\n// Mocks:\nconst fn = jest.fn();\nfn.mockReturnValue(42);\n// expect(fn).toHaveBeenCalledWith(...)",
        'python': "# Pytest equivalent (see the pytest task) — Jest is JavaScript-only.",
    },
))
save('19_testing.json', d19)
print('19_testing.json:', len(d19), 'tasks')

# ── 20_react.json ─────────────────────────────────────────────────────────
d20 = []
d20.append(task_dict(
    'react_component',
    [r'\breact\b.*\b(?:todo|component|app)\b',
     r'\b(?:create|build|write|make)\b.*\breact\b'],
    "Here's a React component with hooks.",
    "useState holds local state; useEffect runs side effects (fetch, subscriptions) after render. Components re-render when state/props change — keep side effects out of the render body.",
    {
        'javascript': "import { useState } from 'react';\n\n// A todo list component with hooks:\nfunction TodoList() {\n    const [todos, setTodos] = useState([]);\n    const [text, setText] = useState('');\n\n    function addTodo(e) {\n        e.preventDefault();\n        if (!text.trim()) return;\n        setTodos([...todos, { id: Date.now(), text: text.trim() }]);\n        setText('');\n    }\n\n    function removeTodo(id) {\n        setTodos(todos.filter(t => t.id !== id));\n    }\n\n    return (\n        <div>\n            <h1>Todo</h1>\n            <form onSubmit={addTodo}>\n                <input\n                    value={text}\n                    onChange={e => setText(e.target.value)}\n                    placeholder=\"What needs doing?\"\n                />\n                <button type=\"submit\">Add</button>\n            </form>\n            <ul>\n                {todos.map(t => (\n                    <li key={t.id}>\n                        {t.text}\n                        <button onClick={() => removeTodo(t.id)}>x</button>\n                    </li>\n                ))}\n            </ul>\n        </div>\n    );\n}\n\nexport default TodoList;",
        'typescript': "import { useState } from 'react';\n\ntype Todo = { id: number; text: string };\n\nfunction TodoList() {\n    const [todos, setTodos] = useState<Todo[]>([]);\n    const [text, setText] = useState('');\n\n    function addTodo(e: React.FormEvent) {\n        e.preventDefault();\n        if (!text.trim()) return;\n        setTodos([...todos, { id: Date.now(), text: text.trim() }]);\n        setText('');\n    }\n\n    function removeTodo(id: number) {\n        setTodos(todos.filter(t => t.id !== id));\n    }\n\n    return (\n        <div>\n            <h1>Todo</h1>\n            <form onSubmit={addTodo}>\n                <input value={text} onChange={e => setText(e.target.value)} />\n                <button type=\"submit\">Add</button>\n            </form>\n            <ul>\n                {todos.map(t => (\n                    <li key={t.id}>\n                        {t.text}\n                        <button onClick={() => removeTodo(t.id)}>x</button>\n                    </li>\n                ))}\n            </ul>\n        </div>\n    );\n}\n\nexport default TodoList;",
    },
))
save('20_react.json', d20)
print('20_react.json:', len(d20), 'tasks')
