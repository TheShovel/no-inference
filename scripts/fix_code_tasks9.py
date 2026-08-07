#!/usr/bin/env python3
"""Round 9: final probe3 data fixes."""
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


# 13_python_utils: prefix_rename plural, retry pattern, checksum task
d13 = load('13_python_utils.json')
pr = task(d13, 'prefix_rename')
pr['patterns'] = [
    r'\brenames?\b.*\bfiles?\b.*\b(?:prefix|add\s+prefix)\b',
    r'\b(?:add|prepend)\b.*\bprefix\b.*\bfiles?\b',
]
rb = task(load('12_more.json'), 'retry_backoff')
rb['patterns'] = rb['patterns'] + [
    r'\bretr\w+\b.*\b(?:function|request|call|operation)\b.*\b(?:fail\w*|error|exception)\b',
]
d12 = load('12_more.json')
save('12_more.json', d12)
d13.append({
    'task': 'download_checksum',
    'patterns': [
        r'\b(?:download|verify|check)\b.*\bchecksum\b',
        r'\bchecksum\b.*\b(?:download|file|verify)\b',
    ],
    'intro': "Here's how to download a file and verify its checksum in {lang}.",
    'notes': "Always compare against the official checksum published by the project. sha256sum is the current standard — md5 and sha1 are broken for security purposes.",
    'languages': {
        'bash': "# Download:\ncurl -fL -o file.tar.gz https://example.com/file.tar.gz\n\n# Verify SHA-256:\necho 'expected-sha256  file.tar.gz' | sha256sum -c -\n# file.tar.gz: OK\n\n# Or print and compare manually:\nsha256sum file.tar.gz\n\n# Compute without a file:\ncurl -fsL https://example.com/file.tar.gz | sha256sum\n\n# GPG-style alternatives: sha1sum, md5sum (both weaker)\n# If the project publishes a .sha256 file:\ncurl -fsL -O https://example.com/file.tar.gz.sha256\nsha256sum -c file.tar.gz.sha256",
        'python': "import hashlib\nimport requests\n\nurl = 'https://example.com/file.tar.gz'\nexpected = 'expected-sha256-hex'\n\nresp = requests.get(url, timeout=60)\nresp.raise_for_status()\n\ndigest = hashlib.sha256(resp.content).hexdigest()\nprint(digest)\nif digest == expected:\n    print('checksum OK')\nelse:\n    print('checksum MISMATCH — do not use this file')\n\n# Streaming for large files:\ndef sha256_file(path: str, chunk: int = 8192) -> str:\n    h = hashlib.sha256()\n    with open(path, 'rb') as f:\n        while True:\n            block = f.read(chunk)\n            if not block:\n                break\n            h.update(block)\n    return h.hexdigest()",
    },
    'default_lang': 'bash',
})
save('13_python_utils.json', d13)

print('done')
