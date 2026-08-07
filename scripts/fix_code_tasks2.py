#!/usr/bin/env python3
"""Round 2 data fixes: tighten hijacking patterns, add default_lang, new tasks.

All edits go through json round-tripping (see add_code_tasks.py).
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


def task(data, tid):
    items = data.get('tasks', []) if isinstance(data, dict) else data
    for t in items:
        if t['task'] == tid:
            return t
    raise KeyError(tid)


def add_lang(data, tid, lang, code):
    task(data, tid)['languages'][lang] = code


# ── 03_strings.json ────────────────────────────────────────────────────────
d03 = load('03_strings.json')
sl = task(d03, 'string_length')
sl['patterns'] = [
    r'\b(?:count|get|find|calculate|compute|return)\b.*\b(?:number\s+of\s+)?(?:characters?|letters?)\b.*\b(?:in\s+a\s+|of\s+a\s+|in\s+the\s+|of\s+the\s+)?(?:string|text|word|sentence|phrase)\b(?!.*\b(?:unique|distinct|non-?repeating|first)\b)',
    r'\blength\s+of\s+(?:a\s+|the\s+)?(?:string|text|word|sentence)\b',
    r'\b(?:string|text)\s+length\b',
    r'\bhow\s+long\s+is\s+(?:a\s+|the\s+)?(?:string|word|text)\b',
    r'\blen\s+of\s+(?:a\s+|the\s+)?(?:string|text|word)\b',
]
save('03_strings.json', d03)

# ── 06_data_structures.json: linked_list js uses ListNode class ────────────
# (fine as-is; probe snippet relaxed to ListNode)

# ── 08_file_io.json ────────────────────────────────────────────────────────
d08 = load('08_file_io.json')
wf = task(d08, 'write_file')
wf['patterns'] = [
    r'\bwrite\s+(?:to\s+)?(?:a\s+)?file\b',
    r'\bwrite\s+(?:a\s+|the\s+)?(?:string|text|content|line|data|message|value)\s+(?:to\s+)?(?:a\s+|the\s+)?file\b',
    r'\bappend\s+to\s+(?:a\s+)?file\b',
    r'\bcreate\s+(?:a\s+)?file\b',
]
df = task(d08, 'delete_file')
df['patterns'] = [
    r'\b(?:delete|remove|unlink)\s+(?:a\s+|the\s+|this\s+)?files?\b(?!.*\b(?:older\s+than|mtime|days?\s+old|find\s+and)\b)',
    r'\b(?:delete|remove)\s+(?:a\s+|the\s+)?(?:file|directory)\s+(?:in|with|using)\s+python\b',
    r'\brm\s+file\b',
]
rc = task(d08, 'read_csv')
rc['patterns'] = [
    r'\breads?\s+(?:a\s+)?csv\b',
    r'\bread\s+csv\s+file\b',
    r'\bparse\s+(?:a\s+)?csv\b',
    r'\bcsv\s+file\b',
    r'\bcsv\s+reader\b',
    r'\bcsv\s+parser\b',
]
zf = task(d08, 'zip_folder')
zf['patterns'] = [
    r'\b(?:zip|compress|archive)\b.*\b(?:folder|directory|files?)\b(?!.*\btar\b)',
    r'\b(?:create|make)\s+(?:a\s+)?zip\b',
]
save('08_file_io.json', d08)

# ── 09_http.json ───────────────────────────────────────────────────────────
d09 = load('09_http.json')
fa = task(d09, 'flask_api')
fa['patterns'] = [
    r'\bflask\s+(?:api|app|server|endpoint|route)\b(?!.*\bdocker\b)',
]
hp = task(d09, 'http_post')
hp['patterns'] = [
    r'\bpost\s+(?:data|json|a\s+request)\b(?!.*\bcurl\b)',
    r'\bpost\s+request\b(?!.*\bcurl\b)',
    r'\b(?:make|send|do)\s+(?:a\s+)?post\s+request\b(?!.*\bcurl\b)',
    r'\bhttp\s+post\b',
    r'\bsend\s+(?:a\s+)?post\b',
    r'\bsubmit\s+(?:a\s+)?form\b',
]
hg = task(d09, 'http_get')
hg['languages']['python'] = (
    "import requests\n\n"
    "def http_get(url: str, timeout: int = 10) -> dict:\n"
    "    \"\"\"GET a URL and return the parsed JSON (or raise).\"\"\"\n"
    "    resp = requests.get(url, timeout=timeout)\n"
    "    resp.raise_for_status()          # raises for 4xx/5xx\n"
    "    return resp.json()\n"
    "\n"
    "# Example:\n"
    "data = http_get('https://api.example.com/data')\n"
    "print(data)\n"
    "\n"
    "# Download a file to disk:\n"
    "url = 'https://example.com/file.zip'\n"
    "resp = requests.get(url, stream=True, timeout=30)\n"
    "resp.raise_for_status()\n"
    "with open('file.zip', 'wb') as f:\n"
    "    for chunk in resp.iter_content(chunk_size=8192):\n"
    "        f.write(chunk)\n"
    "\n"
    "# Standard library alternative (no pip install):\n"
    "import urllib.request\n"
    "with urllib.request.urlopen(url, timeout=10) as r:\n"
    "    print(r.read().decode())\n"
    "\n"
    "# Headers / query params:\n"
    "resp = requests.get(url, params={'page': 1},\n"
    "                    headers={'Authorization': 'Bearer TOKEN'},\n"
    "                    timeout=10)"
)
save('09_http.json', d09)

# ── 10_sql.json ────────────────────────────────────────────────────────────
d10 = load('10_sql.json')
si = task(d10, 'sql_insert')
si['patterns'] = [
    r'\binsert\s+(?:into|new\s+rows?)\b',
    r'\binsert\s+(?:a\s+|the\s+)?(?:row|record)\b',
]
sg = task(d10, 'sql_group_by')
sg['patterns'] = [
    r'\bgroup\s+by\b',
    r'\bgrouped\s+by\b',
    r'\b(?:sum|average|count)\s+.*\bper\b',
    r'\bcount\s+rows\b',
    r'\bcount\s+records\b',
    r'\bgroup\s+(?:rows|records)\b.*\bcount\b',
    r'\bcount\s+(?:them|rows?|records?)\s+per\s+(?:group|category)\b',
]
save('10_sql.json', d10)

# ── 11_git_bash.json ───────────────────────────────────────────────────────
d11 = load('11_git_bash.json')
gu = task(d11, 'git_undo')
gu['patterns'] = [
    r'\bundo\s+(?:a\s+)?commit\b',
    r'\bundo\s+(?:the\s+)?last\s+commit\b',
    r'\brevert\s+(?:a\s+)?commit\b',
    r'\breset\s+(?:a\s+)?commit\b',
    r'\buncommit\b',
]
save('11_git_bash.json', d11)

# ── 13_python_utils.json: new tasks + tweaks ───────────────────────────────
d13 = load('13_python_utils.json')

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
    d13.append(t)

new_task(
    'group_dicts',
    [r'\bgroup\b.*\b(?:list|dict(?:s)?|dictionaries|records?|items?)\b.*\b(?:by|according\s+to)\b.*\b(?:field|key|property|column)\b',
     r'\bgroup\s+by\s+(?:a\s+)?(?:field|key|property)\b'],
    "Here's how to group a list of dictionaries by a field in {lang}.",
    "itertools.groupby requires the input to be SORTED by the grouping key first. For unsorted input, a plain dict-of-lists loop is simpler and O(n).",
    {
        'python': "from itertools import groupby\n\npeople = [\n    {'name': 'alice', 'dept': 'eng'},\n    {'name': 'bob', 'dept': 'sales'},\n    {'name': 'carol', 'dept': 'eng'},\n    {'name': 'dave', 'dept': 'sales'},\n]\n\n# groupby needs sorted input:\npeople.sort(key=lambda p: p['dept'])\ngroups = {dept: list(members)\n          for dept, members in groupby(people, key=lambda p: p['dept'])}\nprint(groups)\n# {'eng': [...alice, carol...], 'sales': [...bob, dave...]}\n\n# Simpler O(n) approach that works on any input:\ndef group_by(items, key):\n    out = {}\n    for item in items:\n        out.setdefault(key(item), []).append(item)\n    return out\n\nprint(group_by(people, lambda p: p['dept']))",
        'javascript': "const people = [\n    { name: 'alice', dept: 'eng' },\n    { name: 'bob', dept: 'sales' },\n    { name: 'carol', dept: 'eng' },\n    { name: 'dave', dept: 'sales' },\n];\n\nfunction groupBy(items, keyFn) {\n    const out = {};\n    for (const item of items) {\n        const key = keyFn(item);\n        (out[key] ||= []).push(item);\n    }\n    return out;\n}\n\nconsole.log(groupBy(people, p => p.dept));",
    },
)
new_task(
    'download_unzip',
    [r'\bdownload\b.*\bunzip\b',
     r'\b(?:download|fetch)\b.*\bzip\s+file\b.*\b(?:extract|unzip)\b'],
    "Here's a {lang} script that downloads and unzips a file.",
    "Use io.BytesIO to unzip from memory, or save to disk first when the archive is large. Always check the download status and close the zipfile.",
    {
        'python': "import io\nimport zipfile\nimport requests\n\n\ndef download_and_unzip(url: str, dest_dir: str = '.') -> None:\n    \"\"\"Download a zip and extract it into dest_dir.\"\"\"\n    resp = requests.get(url, timeout=60)\n    resp.raise_for_status()\n    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:\n        zf.extractall(dest_dir)\n        print('extracted:', zf.namelist())\n\n# Example:\n# download_and_unzip('https://example.com/data.zip', 'data')\n\n# Save-then-extract version (better for large archives):\nimport os\nfrom urllib.request import urlretrieve\n\ndef download_unzip_disk(url: str, dest_dir: str = '.') -> None:\n    tmp = 'downloaded.zip'\n    urlretrieve(url, tmp)\n    with zipfile.ZipFile(tmp) as zf:\n        zf.extractall(dest_dir)\n    os.remove(tmp)",
    },
)
# set_timeout lives in 14; add pattern here is fine since files are separate.
save('13_python_utils.json', d13)

# ── 14_js_utils.json ───────────────────────────────────────────────────────
d14 = load('14_js_utils.json')
st = task(d14, 'set_timeout')
st['patterns'] = [
    r'\bsetTimeout\b',
    r'\bset\s+(?:a\s+)?timeout\b',
    r'\b(?:delay|wait)\b.*\b(?:ms|milliseconds?|seconds?)\b.*\b(?:javascript|js|node)\b',
]
save('14_js_utils.json', d14)

# ── 15_ds_advanced.json: min_heap already fixed; nothing more needed ───────

# ── 18_devops.json: default_lang=bash + plural loop pattern ────────────────
d18 = load('18_devops.json')
for t in d18:
    if t['task'] in ('dockerfile', 'docker_compose', 'github_actions',
                     'gitignore', 'setup_py', 'cron_job', 'systemd_service',
                     'inotify_watch', 'tar_compress', 'grep_recursive',
                     'tail_follow', 'ffmpeg_mp4_gif', 'find_delete_old',
                     'rsync_sync', 'bash_loop_files'):
        t['default_lang'] = 'bash'
blf = task(d18, 'bash_loop_files')
blf['patterns'] = [
    r'\b(?:loop\w*|iterat\w*|for\s+loop)\b.*\bfiles?\b.*\b(?:directory|folder)\b',
    r'\b(?:loop\w*|iterat\w*)\b.*\b(?:directory|folder)\b.*\bfiles?\b',
]
save('18_devops.json', d18)

# ── 20_react.json: default_lang=javascript ────────────────────────────────
d20 = load('20_react.json')
for t in d20:
    if t['task'] == 'react_component':
        t['default_lang'] = 'javascript'
save('20_react.json', d20)

# ── 08 read_file: kotlin gets the idiomatic readText variant ──────────────
d08b = load('08_file_io.json')
rf = task(d08b, 'read_file')
rf['languages']['kotlin'] = (
    "import java.io.File\n"
    "\n"
    "// Idiomatic Kotlin (stdlib extension):\n"
    "val content = File(\"data.txt\").readText()\n"
    "\n"
    "// Read lines:\n"
    "val lines = File(\"data.txt\").readLines()\n"
    "lines.forEach { println(it) }\n"
    "\n"
    "// Large files: read line by line\n"
    "File(\"data.txt\").useLines { sequence ->\n"
    "    sequence.forEach { println(it) }\n"
    "}"
)
save('08_file_io.json', d08b)

print('done')
