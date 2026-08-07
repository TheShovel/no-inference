#!/usr/bin/env python3
"""Probe battery #9 — bash scripting, framework depth, SQL window drills.

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
    # ── bash scripting patterns ────────────────────────────────────────────
    ("how do i run a command on every file in a directory", None, "bash", "for f in"),
    ("how do i loop over lines in a file in bash", None, "bash", "while IFS= read"),
    ("how do i pass arguments to a bash function", None, "bash", "$1"),
    ("how do i use arrays in bash", None, "bash", "${files[@]}"),
    ("how do i check if a file exists in bash", None, "bash", "-f"),
    ("how do i use a here document in bash", None, "bash", "<<"),
    ("how do i split a string in bash", None, "bash", "IFS="),
    ("how do i get the current date in bash", None, "bash", "date +"),
    ("how do i use sed to delete lines matching a pattern", None, "bash", "sed"),
    ("how do i use grep to find files containing text", None, "bash", "grep -rl"),
    # ── framework depth ────────────────────────────────────────────────────
    ("how do i query a django model", None, "python", "objects.filter"),
    ("how do i create a spring boot controller", None, "java", "@RestController"),
    ("how do i use linq in c#", None, "c#", "Where("),
    # ── sql window drills ──────────────────────────────────────────────────
    ("how do i use row_number in sql", None, "sql", "ROW_NUMBER"),
    ("how do i use rank vs dense_rank in sql", None, "sql", "DENSE_RANK"),
    ("how do i write a recursive cte in sql", None, "sql", "WITH RECURSIVE"),
    # ── docker / ci ────────────────────────────────────────────────────────
    ("how do i check docker container logs", None, "bash", "docker logs"),
    ("how do i exec into a running docker container", None, "bash", "docker exec"),
    ("how do i use github actions for ci", None, "bash", "on:"),
    # ── data science depth ─────────────────────────────────────────────────
    ("how do i use seaborn in python", None, "python", "sns."),
    ("how do i train a model with scikit-learn", None, "python", "fit("),
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
    print(f"PROBE9: {passed}/{total} pass ({100.0 * passed / total:.1f}%)")
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
