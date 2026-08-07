#!/usr/bin/env python3
"""Probe battery #8 — regex writers, API design, go idioms, python stdlib.

(query, expected_task_or_None, expected_lang_or_None, snippet)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from cos.engine import process_query, reset_conversation  # noqa: E402
from cos import code_gen  # noqa: E402

import cos.engine as _engine  # noqa: E402
import tempfile as _tempfile  # noqa: E402
_engine._WIKI_CACHE_FILE = _engine.Path(_tempfile.mktemp(suffix='.json'))
_engine._WIKI_CACHE.clear()

BATTERY = [
    # ── regex writers ──────────────────────────────────────────────────────
    ("write a regex to match a url", None, "python", "URL_RE"),
    ("write a regex for a valid ip address", None, "python", "ipv4"),
    ("write a regex to validate a date", None, "python", "DATE_RE"),
    ("write a regex for a hex color", None, "python", "HEX"),
    # ── api / systems design ───────────────────────────────────────────────
    ("how do i design a rate limiter", None, "python", "TokenBucket"),
    ("how do i design a url shortener", None, "python", "base62"),
    ("how do i implement a task queue", None, "python", "queue.Queue"),
    # ── python stdlib ──────────────────────────────────────────────────────
    ("how do i use sqlalchemy in python", None, "python", "create_engine"),
    ("how do i use argparse in python", None, "python", "add_argument"),
    ("how do i use pathlib in python", None, "python", "Path("),
    ("how do i use logging in python", None, "python", "getLogger"),
    # ── go idioms ──────────────────────────────────────────────────────────
    ("how do i use pointers in go", None, "go", "*int"),
    ("how do i handle errors in go", None, "go", "err != nil"),
    ("how do i use structs in go", None, "go", "type User struct"),
    # ── multi-language leetcode depth ──────────────────────────────────────
    ("implement the number of islands in java", None, "java", "int numIslands"),
    ("implement the number of islands in go", None, "go", "func numIslands"),
    ("implement two sum in c++", None, "c++", "vector"),
    ("write a valid parentheses checker in go", None, "go", "stack"),
    # ── js / testing ───────────────────────────────────────────────────────
    ("how do i mock a function in jest", None, "javascript", "jest.fn"),
    ("how do i use useEffect with cleanup in react", None, "javascript", "cleanup"),
]


def _fence_lang(answer: str):
    m = re.search(r'```([^\s`]+)', answer or '')
    if not m:
        return None
    lang = m.group(1).lower()
    return {'js': 'javascript', 'py': 'python', 'cpp': 'c++', 'cs': 'c#',
            'jsx': 'javascript', 'tsx': 'javascript', 'ts': 'typescript'}.get(lang, lang)


def _has_fence(answer: str) -> bool:
    return bool(re.search(r'```', answer or ''))


def main():
    results = []
    reset_conversation()
    for q, exp_task, exp_lang, snippet in BATTERY:
        reset_conversation()
        task = code_gen.detect_task(q)
        response = process_query(q)
        low = (response or '').lower()
        ok = True
        reasons = []
        if snippet is not None and snippet.lower() not in low:
            ok = False
            reasons.append(f"missing snippet {snippet!r}")
        if exp_task is not None and task != exp_task:
            ok = False
            reasons.append(f"task={task!r} want {exp_task!r}")
        if exp_lang is not None:
            fl = _fence_lang(response)
            if exp_lang == 'python' and fl is None and _has_fence(response):
                fl = 'python'
            if fl != exp_lang:
                ok = False
                reasons.append(f"fence lang={fl!r} want {exp_lang!r}")
        if not response or len(response) < 30:
            ok = False
            reasons.append('response too short')
        results.append((q, ok, reasons))
        if not ok:
            print(f"[FAIL] {', '.join(reasons)}")
            print(f"       {q}")
    passed = sum(1 for _, ok, *_ in results if ok)
    total = len(results)
    print(f"PROBE8: {passed}/{total} pass ({100.0 * passed / total:.1f}%)")
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
