#!/usr/bin/env python3
"""Probe battery #5 — dev tools, infra, profiling, git workflows, data munging.

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
    # ── tool-specific config / infra ───────────────────────────────────────
    ("how do i use environment variables in node.js", None, "javascript", "process.env"),
    ("write a terraform config for an aws ec2 instance", "terraform_ec2", None, "aws_instance"),
    ("write a docker-compose file for a postgres database", None, "bash", "postgres:16"),
    ("how do i make a get request with axios", None, "javascript", "axios.get"),
    ("how do i check how much disk space is left", None, "bash", "df -h"),
    ("how do i check listening ports in linux", None, "bash", "ss -tulpn"),
    ("how do i set up a crontab job", None, "bash", "crontab -e"),
    ("how do i create a symlink in linux", None, "bash", "ln -s"),
    ("how do i extract a tar.gz file", None, "bash", "tar -xzf"),
    # ── git workflows ──────────────────────────────────────────────────────
    ("how do i format a git log to show one line per commit", None, "bash", "git log --oneline"),
    ("git: how do i squash my last 3 commits", "git_squash", "bash", "git rebase -i"),
    # ── data munging / science ─────────────────────────────────────────────
    ("how do i filter a pandas dataframe by a column value", None, "python", "df["),
    ("how do i remove duplicate lines from a file in linux", None, "bash", "sort"),
    ("how do i iterate over a dict in python", None, "python", "items()"),
    ("write sql to get the highest paid employee in each department", None, "sql", "DENSE_RANK"),
    # ── language idioms ────────────────────────────────────────────────────
    ("how do i use a map in golang", None, "go", "make(map"),
    ("how do i use goroutines in go", None, "go", "goroutine"),
    ("how do i make a rest api with go", None, "go", "net/http"),
    ("how do i make an http request in go", None, "go", "http.Get"),
    ("how do i use async/await in javascript", None, "javascript", "async"),
    ("how do i use pydantic in fastapi", None, "python", "BaseModel"),
    ("write a memoized fibonacci in javascript", None, "javascript", "memo"),
    # ── profiling / testing / ops ──────────────────────────────────────────
    ("how do i profile a python script", "profile_python", "python", "cProfile"),
    ("write a unit test with pytest", None, "python", "def test_"),
    ("how do i do multiprocessing in python", None, "python", "multiprocessing"),
    ("write a bash one-liner to kill processes on port 8080", None, "bash", "lsof"),
    ("how do i list all pods in all namespaces", None, "bash", "kubectl get pods"),
    ("how do i read a query parameter in express", None, "javascript", "req.query"),
    ("write a bash script that backs up a directory with timestamps", None, "bash", "tar"),
    ("how do i validate an email with a regex in javascript", None, "javascript", "test("),
]


def _fence_lang(answer: str):
    m = re.search(r'```([^\s`]+)', answer or '')
    if not m:
        return None
    lang = m.group(1).lower()
    return {'js': 'javascript', 'py': 'python', 'cpp': 'c++', 'cs': 'c#', 'jsx': 'javascript', 'tsx': 'javascript', 'ts': 'typescript'}.get(lang, lang)


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
        results.append((q, ok, reasons, task, _fence_lang(response)))
        if not ok:
            print(f"[FAIL] task={task!r} lang={_fence_lang(response)!r} {', '.join(reasons)}")
            print(f"       {q}")
    passed = sum(1 for _, ok, *_ in results if ok)
    total = len(results)
    print(f"PROBE5: {passed}/{total} pass ({100.0 * passed / total:.1f}%)")
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
