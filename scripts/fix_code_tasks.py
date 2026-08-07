#!/usr/bin/env python3
"""Re-apply pattern edits to code_tasks JSON files with correct escaping.

The interactive edit tool mangles backslashes in JSON string values, so
these edits are applied programmatically with json round-tripping (the only
way to guarantee the file stays valid JSON with exactly the right escapes).

Usage: python3 scripts/fix_code_tasks.py
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


# ── 02_algorithms.json: power patterns ────────────────────────────────────
d02 = load('02_algorithms.json')
power = task(d02, 'power')
power['patterns'] = [
    r'\b(?:calculate|compute|find|get)\b.*\bpower\b.*\b(?:number|base)\b',
    r'\b(?:raise|calculate)\s+(?:a\s+)?(?:number|base)\s+to\s+(?:the\s+)?(?:power|exponent)\b',
    r'\b(?:x|n|number|base|a|value)\s+raised\s+to\s+(?:the\s+)?(?:power|exponent)(?:\s+of\s+(?:n|y|an?\s+exponent))?\b',
    r'\b(?:compute|calculate|find|get)\b.*\brais(?:e|ed)\s+(?:a\s+|the\s+)?(?:number|base|value|x|n)\b',
    r'\bexponentiation\b',
    r'\bpower\s+of\s+(?:a\s+)?(?:number|base)\b',
    r'\bpower\s+function\b',
]
save('02_algorithms.json', d02)

# ── 03_strings.json: widened patterns + missing languages ────────────────
d03 = load('03_strings.json')

mf = task(d03, 'most_frequent')
mf['patterns'] = [
    r'\bmost\s+(?:frequently\s+)?occurring\s+(?:character|element|word)\b',
    r'\bfind\s+the\s+most\s+common\b',
    r'\bmost\s+common\s+(?:character|element|word)\b',
    r'\bmost\s+frequent\s+(?:character|element|word|item)\b',
    r'\bmode\s+of\s+(?:a\s+)?(?:list|array)\b',
]

co = task(d03, 'count_occurrences')
co['patterns'] = [
    r'\bcount\s+(?:the\s+)?(?:number\s+of\s+)?(?:occurrences|frequency)\s+of\b',
    r'\bcount\s+how\s+many\s+times\b.*\b(?:appears?|occurs?|shows?\s+up)\b',
    r'\bhow\s+many\s+times\b.*\b(?:appears?|occurs?)\b',
    r'\bfrequency\s+of\s+(?:each|every|characters?|elements?|words?)\b',
    r'\bcharacter\s+counter\b',
    r'\bword\s+count(?:er)?\b',
]

bp = task(d03, 'balanced_parens')
bp['patterns'] = [
    r'\b(?:check|test|validate)\b.*\bbalanced\b.*\b(?:parentheses?|brackets?|braces?|parens?)\b',
    r'\b(?:check|test|validate)\s+(?:if\s+|whether\s+)?(?:parentheses?|brackets?|braces?|parens?)\s+(?:are|is)\s+balanced\b',
    r'\bbalanced\s+(?:parentheses?|brackets?|braces?|parens?)\b',
    r'\bvalid\s+parentheses?\b',
    r'\b(?:parentheses?|brackets?)\s+match(?:ing|ed)?\b',
]

lts = task(d03, 'list_to_string')
lts['patterns'] = [
    r'\b(?:convert|turn|transform)\s+(?:a\s+|the\s+)?list\s+(?:to|into)\s+(?:a\s+|the\s+)?string\b',
    r'\b(?:convert|turn|transform)\s+(?:a\s+|the\s+)?list\s+(?:to|into)\s+(?:a\s+|the\s+)?(?:comma\s+separated\s+)?string\b',
    r'\bjoin\s+(?:a\s+|the\s+)?list\s+(?:into|to)\s+(?:a\s+)?string\b',
    r'\bjoin\s+(?:a\s+)?list\s+of\s+strings\b',
    r'\b(?:comma\s+)?separated\s+string\b',
]

rs = task(d03, 'reverse_string')
rs['languages']['swift'] = (
    'func reverseString(_ s: String) -> String {\n'
    '    return String(s.reversed())\n'
    '}\n\n'
    '// Example:\n'
    'print(reverseString("hello"))  // "olleh"'
)
rs['languages']['kotlin'] = (
    'fun reverseString(s: String): String = s.reversed()\n\n'
    '// Example:\n'
    'println(reverseString("hello"))  // olleh'
)
rs['languages']['ruby'] = (
    "def reverse_string(s)\n"
    "  s.reverse\n"
    "end\n\n"
    "# Example:\n"
    "puts reverse_string('hello')  # olleh"
)
rs['languages']['php'] = (
    "<?php\n"
    "function reverseString(string $s): string {\n"
    "    return strrev($s);\n"
    "}\n\n"
    "// Example:\n"
    "echo reverseString('hello');  // olleh"
)
save('03_strings.json', d03)

print('done')
