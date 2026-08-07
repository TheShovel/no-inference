#!/usr/bin/env python3
"""Round 3 data fixes: start-anchored exclusions, tighter patterns."""
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


# 03_strings: string_length must not swallow "first non-repeating"/"unique"
d03 = load('03_strings.json')
sl = task(d03, 'string_length')
sl['patterns'] = [
    r'^(?!.*\b(?:unique|distinct|non-?repeating|first)\b).*\b(?:count|get|find|calculate|compute|return)\b.*\b(?:number\s+of\s+)?(?:characters?|letters?)\b.*\b(?:in\s+a\s+|of\s+a\s+|in\s+the\s+|of\s+the\s+)?(?:string|text|word|sentence|phrase)\b',
    r'\blength\s+of\s+(?:a\s+|the\s+)?(?:string|text|word|sentence)\b',
    r'\b(?:string|text)\s+length\b',
    r'\bhow\s+long\s+is\s+(?:a\s+|the\s+)?(?:string|word|text)\b',
    r'\blen\s+of\s+(?:a\s+|the\s+)?(?:string|text|word)\b',
]
save('03_strings.json', d03)

# 08_file_io: write_csv catches "write data to a csv file"; read_csv loses
# the too-loose "csv file" pattern; zip_folder excludes extract/unzip.
d08 = load('08_file_io.json')
rc = task(d08, 'read_csv')
rc['patterns'] = [
    r'\breads?\s+(?:a\s+)?csv\b',
    r'\bread\s+csv\s+file\b',
    r'\bparse\s+(?:a\s+)?csv\b',
    r'\bcsv\s+reader\b',
    r'\bcsv\s+parser\b',
]
wc = task(d08, 'write_csv')
wc['patterns'] = [
    r'\bwrite\s+(?:a\s+)?csv\b',
    r'\bwrite\b.*\bcsv\b',
    r'\bexport\s+.*csv\b',
    r'\bsave\s+.*\bcsv\b',
]
zf = task(d08, 'zip_folder')
zf['patterns'] = [
    r'^(?!.*\b(?:extract|unzip|decompress)\b).*\b(?:zip|compress|archive)\b.*\b(?:folder|directory|files?)\b(?!.*\btar\b)',
    r'\b(?:create|make)\s+(?:a\s+)?zip\b',
]
save('08_file_io.json', d08)

# 09_http: flask_api excludes docker; http_post excludes curl; web_scrape
# excludes table parsing.
d09 = load('09_http.json')
fa = task(d09, 'flask_api')
fa['patterns'] = [
    r'^(?!.*\bdocker\b).*\bflask\s+(?:api|app|server|endpoint|route)\b',
]
hp = task(d09, 'http_post')
hp['patterns'] = [
    r'^(?!.*\bcurl\b).*\bpost\s+(?:data|json|a\s+request)\b',
    r'^(?!.*\bcurl\b).*\bpost\s+request\b',
    r'^(?!.*\bcurl\b).*\b(?:make|send|do)\s+(?:a\s+)?post\s+request\b',
    r'\bhttp\s+post\b',
    r'\bsend\s+(?:a\s+)?post\b',
    r'\bsubmit\s+(?:a\s+)?form\b',
]
ws = task(d09, 'web_scrape')
ws['patterns'] = [
    r'\b(?:web\s+)?scrap(?:e|ing)\b',
    r'\bscrape\b',
    r'\bextract\s+(?:all\s+)?links?\b',
    r'\bextract\s+(?:the\s+)?(?:title|headings?|text)\s+from\b',
    r'\bparse\s+(?:an?\s+)?html\b(?!.*\btable\b)',
]
save('09_http.json', d09)

# 10_sql: sql_duplicates gains the DELETE variant.
d10 = load('10_sql.json')
sd = task(d10, 'sql_duplicates')
sd['languages']['sql'] = (
    "-- Find duplicate rows (same key, multiple entries):\n"
    "SELECT email, COUNT(*) AS n\n"
    "FROM customers\n"
    "GROUP BY email\n"
    "HAVING COUNT(*) > 1;\n"
    "\n"
    "-- Delete duplicates, keeping one row per key (MySQL/PostgreSQL):\n"
    "DELETE FROM customers\n"
    "WHERE id NOT IN (\n"
    "    SELECT MIN(id)\n"
    "    FROM customers\n"
    "    GROUP BY email\n"
    ");\n"
    "\n"
    "-- Same idea with a self-join (keeps the smallest id per key):\n"
    "DELETE a\n"
    "FROM customers a\n"
    "JOIN customers b ON a.email = b.email AND a.id > b.id;\n"
    "\n"
    "-- PostgreSQL row_number approach (keeps one per key):\n"
    "DELETE FROM customers\n"
    "WHERE id IN (\n"
    "    SELECT id FROM (\n"
    "        SELECT id, ROW_NUMBER() OVER (PARTITION BY email ORDER BY id) AS rn\n"
    "        FROM customers\n"
    "    ) ranked\n"
    "    WHERE rn > 1\n"
    ");"
)
save('10_sql.json', d10)

# 11_git_bash: bash_file_ops must not swallow "count lines in a file".
d11 = load('11_git_bash.json')
bf = task(d11, 'bash_file_ops')
bf['patterns'] = [
    r'^(?!.*\blines?\b).*\b(?:list|find|count)\s+(?:all\s+|the\s+)?(?:[a-z0-9_.-]+\s+)*(?:files?|directories?)\b',
    r'\b(?:copy|move|rename|delete)\s+(?:a\s+)?file\b',
    r'\bpermissions?\s+(?:on\s+)?(?:a\s+)?file\b',
]
save('11_git_bash.json', d11)

# 12_more: count_words catches "count the number of words in a string".
d12 = load('12_more.json')
cw = task(d12, 'count_words')
cw['patterns'] = cw['patterns'] + [
    r'\bcount\b.*\b(?:the\s+)?(?:number\s+of\s+)?words?\b.*\b(?:in\s+(?:a\s+|the\s+)?(?:string|text|sentence|phrase))\b',
]
save('12_more.json', d12)

print('done')
