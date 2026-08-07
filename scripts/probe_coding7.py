#!/usr/bin/env python3
"""Probe battery #7 — language idioms, framework error handling, multi-lang leetcode.

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
    # ── python idioms ──────────────────────────────────────────────────────
    ("how do i use defaultdict in python", None, "python", "defaultdict"),
    ("how do i catch all exceptions in python", None, "python", "except"),
    ("how do i use a singleton in python", None, "python", "__new__"),
    ("how do i use property decorators in python", None, "python", "@property"),
    ("how do i use @property in python", None, "python", "@property"),
    ("how do i retry a failed request in python", None, "python", "retry"),
    ("how do i handle errors in flask", None, "python", "errorhandler"),
    # ── go / rust idioms ───────────────────────────────────────────────────
    ("how do i define an interface in go", None, "go", "type Speaker"),
    ("write a go function that takes a channel", None, "go", "chan"),
    ("how do i use traits in rust", None, "rust", "trait Speaker"),
    ("implement the number of islands in go", None, "go", "func numIslands"),
    ("write a two sum function in go", None, "go", "func TwoSum"),
    ("implement a binary search in go", None, "go", "func BinarySearch"),
    ("write a debounce function in typescript", None, "typescript", "debounce"),
    # ── javascript idioms / web ────────────────────────────────────────────
    ("how do i use closures in javascript", None, "javascript", "closure"),
    ("how do i add a custom error handler in express", None, "javascript", "next(err)"),
    # ── already-good multi-language leetcode (regression pins) ─────────────
    ("implement two sum in rust", None, "rust", "fn two_sum"),
    ("implement two sum in java", None, "java", "int[]"),
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
    print(f"PROBE7: {passed}/{total} pass ({100.0 * passed / total:.1f}%)")
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
