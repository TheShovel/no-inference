#!/usr/bin/env python3
"""Probe battery #6 — leetcode classics, React hooks, JS idioms, embedded code.

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
    # ── leetcode classics ───────────────────────────────────────────────────
    ("write a python function for two sum", None, "python", "def two_sum"),
    ("write a python function to check valid parentheses", None, "python", "stack"),
    ("write a function to reverse a linked list in python", None, "python", "def reverse_list"),
    ("write a python function for longest substring without repeating characters", None, "python", "def length"),
    ("write a python function for binary search", None, "python", "def binary_search"),
    ("write a python function to merge two sorted lists", None, "python", "def merge"),
    ("write a python function for the number of islands", None, "python", "def num_islands"),
    # ── React hooks / web ───────────────────────────────────────────────────
    ("how do i use useState in react", None, "javascript", "useState"),
    ("how do i use useEffect in react", None, "javascript", "useEffect"),
    ("how do i make a custom hook in react", None, "javascript", "function use"),
    ("how do i add jwt auth middleware to an express app", None, "javascript", "jwt.verify"),
    # ── JS idioms ───────────────────────────────────────────────────────────
    ("how do i debounce a function in javascript", None, "javascript", "setTimeout"),
    ("how do i deep copy an object in javascript", None, "javascript", "structuredClone"),
    ("how do i use promise.all in javascript", None, "javascript", "Promise.all"),
    # ── python data munging ─────────────────────────────────────────────────
    ("how do i flatten a nested list in python", None, "python", "def flatten"),
    ("how do i transpose a matrix in python", None, "python", "zip(*"),
    ("how do i read a file line by line in python", None, "python", "for line in"),
    ("how do i check if a file exists in python", None, "python", "os.path.exists"),
    ("how do i get the current date in python", None, "python", "datetime"),
    ("how do i write json to a file in python", None, "python", "json.dump"),
    # ── embedded code in the prompt ─────────────────────────────────────────
    ("convert this python to javascript: def square(x): return x * x", None, "javascript", "function square"),
    ("convert this code from python to javascript: def square(x): return x * x", None, "javascript", "function square"),
    ("why does this code fail: def add(a, b): return a + b  print(add('1', 2))", None, None, "TypeError"),
]

# Multi-turn: write in python, follow up to convert to rust (shares context).
FOLLOWUP_PAIR = ("write a function to reverse a string in python",
                 "now do it in rust",
                 "fn reverse_string")


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
    # follow-up pair shares one conversation
    first, follow, snip = FOLLOWUP_PAIR
    reset_conversation()
    process_query(first)
    response = process_query(follow)
    ok = snip in (response or '').lower()
    results.append((follow, ok, [] if ok else ['follow-up missed snippet']))
    if not ok:
        print(f"[FAIL] follow-up: {follow}  missing {snip!r}")
    passed = sum(1 for _, ok, *_ in results if ok)
    total = len(results)
    print(f"PROBE6: {passed}/{total} pass ({100.0 * passed / total:.1f}%)")
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
