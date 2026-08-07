#!/usr/bin/env python3
"""Probe battery #3 — the hardest tier: debugging, review, refactoring.

These are the requests that separate a coding tool from a chatbox.
(query, expected_task_or_None, expected_lang_or_None, snippet)
"""
import json
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
    # ── debugging / fixing pasted code ──────────────────────────────────────
    ("fix this code: def add(a, b)\n    return a + b  # missing colon", None, "python", "def add(a, b):"),
    ("why does this throw an error: print(undefined_variable)", None, None, "undefined"),
    ("debug this: for i in range(10)\n    print(i)", None, "python", ":"),
    ("this code has an off-by-one error, can you fix it: for i in range(len(arr)):\n    print(arr[i+1])", None, "python", "range"),
    ("add error handling to this: data = json.loads(text)", None, "python", "except"),
    ("refactor this code to use a function: x = [i*2 for i in range(5)]\nprint(x)", None, "python", "range(5)"),
    ("this function is slow, make it faster: def find_dups(lst):\n    return [x for x in lst if lst.count(x) > 1]", None, "python", "Counter"),
    # ── code review / explanation ───────────────────────────────────────────
    ("review this code for bugs: def divide(a, b):\n    return a / b", None, "python", "def divide"),
    ("explain this error: IndexError: list index out of range", None, None, "IndexError"),
    ("what does this line do: result = [x**2 for x in data if x > 0]", None, None, "Build a list"),
    ("explain the difference between == and is in python", None, None, "identity"),
    ("what is a memory leak and how do i avoid it in python", None, None, "memory"),
    ("explain what a closure is in javascript", None, None, "closure"),
    ("what is the difference between var let and const in javascript", None, None, "let"),
    # ── testing ─────────────────────────────────────────────────────────────
    ("write a unit test for this function: def add(a, b):\n    return a + b", None, "python", "def test"),
    ("write a test that checks this raises an error: def div(a, b):\n    if b == 0: raise ZeroDivisionError()", None, "python", "raises"),
    # ── config / integration ────────────────────────────────────────────────
    ("how do i connect to a postgres database in python", None, "python", "psycopg2"),
    ("how do i read a yaml file in python", None, "python", "yaml.safe_load"),
    ("write a python script that sends a request to an api every 10 seconds", None, "python", "schedule"),
    ("how do i use environment variables in a docker container", None, "bash", "ENV"),
    ("write a python function to download an image from a url and save it", None, "python", "requests"),
    ("how do i set up a virtual environment in python", None, "bash", "venv"),
    ("write a python script to parse command line arguments with flags", None, "python", "argparse"),
    # ── web / frontend ──────────────────────────────────────────────────────
    ("how do i make a post request with fetch in javascript", "http_post", "javascript", "fetch"),
    ("write a javascript function to validate a form email field", None, "javascript", "email"),
    ("how do i get data from an api in react", None, None, "useEffect"),
    ("write html to center a div", None, None, "flex"),
    ("how do i make a responsive navbar with css", None, "css", "media"),
    # ── data / files ────────────────────────────────────────────────────────
    ("how do i read an excel file in python", None, "python", "openpyxl"),
    ("write a python function to convert json to csv", None, "python", "csv"),
    ("how do i merge two csv files in python", None, "python", "csv"),
    ("write a python function to find files with a specific extension recursively", None, "python", "rglob"),
    ("how do i compress a file to gzip in python", None, "python", "gzip"),
    ("write a python function to copy a directory tree", None, "python", "copytree"),
    ("how do i check the size of a file in python", None, "python", "getsize"),
    ("write a python function that renames files by adding a prefix", None, "python", "rename"),
    # ── algorithms ──────────────────────────────────────────────────────────
    ("implement quicksort in python", None, "python", "def quicksort"),
    ("implement merge sort in python", None, "python", "def merge_sort"),
    ("write a python function to check if a string is a valid ipv4 address", None, "python", "ipv4"),
    ("implement a binary search tree with deletion in python", None, "python", "delete"),
    ("write a python function to find all pairs that sum to a target", None, "python", "def"),
    ("implement the sliding window maximum in python", None, "python", "deque"),
    ("write a python function to compute the edit distance between two strings", None, "python", "def"),
    ("implement a bloom filter in python", None, "python", "class BloomFilter"),
    # ── misc harder ─────────────────────────────────────────────────────────
    ("how do i create a thread pool in python", None, "python", "ThreadPoolExecutor"),
    ("write a python function that retries a function on failure", "retry_backoff", "python", "retry"),
    ("how do i profile python code", None, "python", "cProfile"),
    ("write a python decorator that logs function calls", None, "python", "def log"),
    ("how do i install a specific version of a pip package", None, "bash", "pip install"),
    ("write a bash script that downloads a file and checks its checksum", None, "bash", "sha256sum"),
    ("how do i set up logging in python", None, "python", "logging"),
    ("write a python function to chunk a large file into smaller parts", None, "python", "chunk"),
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
            reasons.append(f'missing snippet {snippet!r}')
        if exp_task is not None and task != exp_task:
            ok = False
            reasons.append(f'task={task!r} (want {exp_task!r})')
        if exp_lang is not None:
            fl = _fence_lang(response)
            if exp_lang == 'python' and fl is None and _has_fence(response):
                fl = 'python'
            if fl != exp_lang:
                ok = False
                reasons.append(f'fence lang={fl!r} (want {exp_lang!r})')
        if not response or len(response) < 30:
            ok = False
            reasons.append('too short')
        results.append({'q': q, 'ok': ok, 'reasons': reasons, 'response': response})

    passed = sum(1 for r in results if r['ok'])
    print(f'PROBE3: {passed}/{len(results)} pass ({100.0*passed/len(results):.1f}%)')
    for r in results:
        if not r['ok']:
            print(f"[{', '.join(r['reasons'])}] task={str(code_gen.detect_task(r['q']))!r}")
            print(f"    {r['q']}")
            print('    head:', (r['response'] or 'None')[:200].replace('\n', ' '))


if __name__ == '__main__':
    main()
