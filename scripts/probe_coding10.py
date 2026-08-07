#!/usr/bin/env python3
"""Probe battery #10 — SQL deep drills, CSS recipes, Rust ownership, error patterns.

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
    # ── sql deep drills ────────────────────────────────────────────────────
    ("how do i pivot rows to columns in sql", None, "sql", "PIVOT"),
    ("how do i write a self join in sql", None, "sql", "LEFT JOIN"),
    ("what is the difference between exists and in in sql", None, "sql", "EXISTS"),
    ("how do i use coalesce in sql", None, "sql", "COALESCE"),
    ("how do i use union vs union all in sql", None, "sql", "UNION ALL"),
    ("how do i use having in sql", None, "sql", "HAVING"),
    # ── css recipes ────────────────────────────────────────────────────────
    ("how do i center a div with flexbox", None, "css", "flex"),
    ("how do i make a responsive grid with css", None, "css", "grid"),
    ("how do i use media queries in css", None, "css", "@media"),
    ("how do i make a sticky footer in css", None, "css", "margin-top: auto"),
    ("how do i add a gradient background in css", None, "css", "linear-gradient"),
    ("how do i animate a button on hover in css", None, "css", "transition"),
    # ── rust ownership ─────────────────────────────────────────────────────
    ("how do i understand ownership in rust", None, None, "ownership"),
    ("how do i use borrowing in rust", None, "rust", "&"),
    ("how do i use lifetimes in rust", None, "rust", "'a"),
    ("how do i use match in rust", None, "rust", "match"),
    ("how do i use iterators in rust", None, "rust", "iter()"),
    # ── error-handling patterns ────────────────────────────────────────────
    ("how do i raise an exception from another in python", None, "python", "raise"),
    ("how do i use try with resources in java", None, "java", "try ("),
    ("how do i use panic and recover in go", None, "go", "recover"),
    # ── git / testing / packaging ──────────────────────────────────────────
    ("how do i use git bisect", None, "bash", "git bisect"),
    ("how do i use git worktree", None, "bash", "git worktree"),
    ("how do i use pytest fixtures", None, "python", "@pytest.fixture"),
    ("how do i mock requests in pytest", None, "python", "monkeypatch"),
    ("how do i write async tests in pytest", None, "python", "asyncio"),
    ("how do i pin dependencies in requirements.txt", None, "bash", "=="),
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
    print(f"PROBE10: {passed}/{total} pass ({100.0 * passed / total:.1f}%)")
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
