#!/usr/bin/env python3
"""Probe battery #4 — new territory: multi-language, data, web, ops, security.

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
    # ── multi-language asks for classic tasks ───────────────────────────────
    ("implement a stack in go", None, "go", "func"),
    ("implement a queue in rust", None, "rust", "VecDeque"),
    ("implement a trie in java", None, "java", "class Trie"),
    ("implement a min heap in go", None, "go", "heap."),
    ("implement dijkstra in rust", None, "rust", "BinaryHeap"),
    ("implement an lru cache in go", None, "go", "container/list"),
    ("merge intervals in java", None, "java", "int[][]"),
    ("find the longest common prefix in go", None, "go", "strings.HasPrefix"),
    ("compute the edit distance in rust", None, "rust", "fn edit_distance"),
    ("implement quicksort in go", None, "go", "func quicksort"),
    ("sliding window maximum in c++", None, "c++", "deque"),
    ("find the first non-repeating character in java", None, "java", "LinkedHashMap"),
    ("reverse words in a sentence in go", None, "go", "strings.Fields"),
    ("count vowels in a string in rust", None, "rust", "fn count_vowels"),
    ("implement a queue using two stacks in java", None, "java", "Deque"),
    ("find duplicate elements in a list in go", None, "go", "map["),
    # ── data science ────────────────────────────────────────────────────────
    ("how do i read a csv and filter rows with pandas", None, "python", "pandas"),
    ("how do i group by a column and compute the mean with pandas", None, "python", "groupby"),
    ("how do i create a numpy array", None, "python", "np.array"),
    ("how do i plot a line chart with matplotlib", None, "python", "plt.plot"),
    ("how do i merge two dataframes in pandas", None, "python", "pd.merge"),
    # ── web frameworks ──────────────────────────────────────────────────────
    ("how do i create a flask route that returns json", "flask_api", "python", "jsonify"),
    ("how do i add middleware to an express app", None, "javascript", "app.use"),
    ("how do i read the request body in express", None, "javascript", "express.json"),
    ("how do i define a model in django", None, "python", "class "),
    ("how do i make a fastapi endpoint", None, "python", "FastAPI"),
    # ── sql beyond basics ───────────────────────────────────────────────────
    ("write a sql query to create a view", None, "sql", "CREATE VIEW"),
    ("write sql to update rows using a join", None, "sql", "UPDATE"),
    ("write sql to delete rows with a join", None, "sql", "DELETE"),
    ("write a sql query using lag or lead", None, "sql", "LAG"),
    ("how do i add a foreign key constraint in sql", None, "sql", "FOREIGN KEY"),
    ("write a sql query to find the top 3 salaries per department", None, "sql", "DENSE_RANK"),
    ("write sql to get the difference between two dates", None, "sql", "DATEDIFF"),
    # ── git / ops ───────────────────────────────────────────────────────────
    ("how do i rebase my branch onto main", None, "bash", "git rebase"),
    ("how do i cherry-pick a commit", None, "bash", "git cherry-pick"),
    ("how do i resolve a merge conflict in git", None, "bash", "merge"),
    ("how do i amend the last commit message", None, "bash", "git commit --amend"),
    ("how do i undo a pushed commit", None, "bash", "git revert"),
    ("write a kubernetes deployment yaml", None, None, "kind: Deployment"),
    ("how do i check kubectl pods in a namespace", None, "bash", "kubectl get pods"),
    ("write an nginx config to serve a static site", None, None, "server {"),
    ("how do i create a docker multi-stage build", None, "bash", "AS "),
    # ── config / formats ────────────────────────────────────────────────────
    ("how do i read a toml file in python", None, "python", "tomllib"),
    ("how do i parse xml in python", None, "python", "ElementTree"),
    ("how do i read an ini file in python", "read_config", "python", "configparser"),
    ("how do i use sqlite in python", None, "python", "sqlite3"),
    ("how do i store data in redis from python", None, "python", "redis.Redis"),
    # ── security ────────────────────────────────────────────────────────────
    ("how do i hash a password safely in python", None, "python", "bcrypt"),
    ("how do i prevent sql injection in python", None, "python", "parameterized"),
    ("how do i encrypt a string in python", None, "python", "Fernet"),
    ("how do i generate a jwt in python", None, "python", "jwt.encode"),
    # ── leetcode-style ──────────────────────────────────────────────────────
    ("write a python function to check if a list contains duplicates", "any_duplicates", "python", "set"),
    ("write a python function for the best time to buy and sell stock", None, "python", "max_profit"),
    ("write a python function for product of array except self", None, "python", "prefix"),
    ("write a python function to group anagrams", None, "python", "def group_anagrams"),
    ("write a python function to find the kth largest element", None, "python", "nlargest"),
    ("write a python function for plus one", None, "python", "def plus_one"),
    ("write a python function to move zeroes to the end", None, "python", "move_zeroes"),
    ("write a python function for valid sudoku", None, "python", "def is_valid_sudoku"),
    # ── text tools ──────────────────────────────────────────────────────────
    ("how do i extract the second column of a csv with awk", None, "bash", "awk"),
    ("how do i parse json in bash with jq", None, "bash", "jq"),
    ("how do i run commands in parallel with xargs", None, "bash", "xargs"),
    ("how do i replace text in a file with sed", None, "bash", "sed -i"),
    ("how do i sort a file by column with sort", None, "bash", "sort -k"),
    ("how do i find duplicate lines in a file", None, "bash", "sort"),
    # ── advanced language features ──────────────────────────────────────────
    ("how do i write a generator in python", None, "python", "yield"),
    ("how do i define a dataclass in python", None, "python", "@dataclass"),
    ("how do i write a context manager in python", None, "python", "__enter__"),
    ("how do i use f-strings for padding in python", None, "python", "f'{"),
    ("how do i use destructuring in javascript", None, "javascript", "const {"),
    ("how do i use optional chaining in javascript", None, "javascript", "?."),
    ("how do i use template literals in javascript", None, "javascript", "`"),
    ("how do i define a class with getters in javascript", None, "javascript", "get "),
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
    print(f'PROBE4: {passed}/{len(results)} pass ({100.0*passed/len(results):.1f}%)')
    for r in results:
        if not r['ok']:
            print(f"[{', '.join(r['reasons'])}] task={str(code_gen.detect_task(r['q']))!r}")
            print(f"    {r['q']}")
            print('    head:', (r['response'] or 'None')[:180].replace('\n', ' '))


if __name__ == '__main__':
    main()
