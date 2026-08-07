#!/usr/bin/env python3
"""Repair doubled backslashes in code_tasks patterns (write_file artifact).

Correct patterns use single backslashes (\\b, \\s, \\d). Any literal `\\`
(two backslashes) inside a pattern string is an escaping artifact and is
reduced to one. Idempotent: patterns that are already correct are untouched.
"""
import glob
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / 'data' / 'knowledge' / 'code_tasks'

fixed_any = False
for f in sorted(glob.glob(str(BASE / '*.json'))):
    if f.endswith('_web_types.json'):
        continue
    data = json.load(open(f, encoding='utf-8'))
    items = data.get('tasks', []) if isinstance(data, dict) else data
    changed = False
    for t in items:
        for i, p in enumerate(t.get('patterns', [])):
            if '\\\\' in p:
                t['patterns'][i] = p.replace('\\\\', '\\')
                changed = True
    if changed:
        with open(f, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write('\n')
        fixed_any = True
        print('repaired', Path(f).name)
print('done' if fixed_any else 'nothing to repair')
