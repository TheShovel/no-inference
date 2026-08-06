#!/usr/bin/env python3
"""Battery for the deterministic code generator and coding routing fixes.

Covers:
  1. Unit checks on cos.code_gen (language + task detection, generation).
  2. End-to-end routing through process_query: code questions must produce
     real code in the requested language and must NEVER fall back to
     Wikipedia (the old "read a csv with pandas -> giant panda" bug) or to
     the generic "I do not have enough information" fallback.

Runs fully offline: the Stack dataset API fallback is patched away.

Run with:  python3 tests/test_code_gen.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import cos.code_knowledge as code_knowledge
from cos.code_gen import generate_code, detect_language, detect_task
from cos.engine import process_query, reset_conversation

# Offline: no Stack API calls
code_knowledge._search_stack = lambda query, max_files=2: []

FALLBACK_PHRASES = [
    "i do not have enough specific information",
    "i'm not sure about that",
    "i could not find enough",
    "fallback-network",
]

# ── 1. Unit checks: (query, expected_lang, expected_task) ──────────────────
LANG_TASK_CASES = [
    ("write a python function to check if a number is prime", 'python', 'prime'),
    ("how to check if a number is prime in javascript", 'javascript', 'prime'),
    ("implement isPrime in java", 'java', 'prime'),
    ("write a prime checker in c++", 'c++', 'prime'),
    ("golang function to test primality", 'go', 'prime'),
    ("rust prime number function", 'rust', 'prime'),
    ("fizzbuzz in c#", 'c#', 'fizzbuzz'),
    ("typescript fibonacci sequence", 'typescript', 'fibonacci'),
    ("write a factorial program in kotlin", 'kotlin', 'factorial'),  # no kotlin template -> None
    ("how to read a csv file with pandas", 'python', 'read_csv'),
    ("read csv in go", 'go', 'read_csv'),
    ("how to make a http request in node.js", 'javascript', 'http_get'),
    ("make a GET request with curl", 'bash', 'http_get'),
    ("write sql to find duplicate rows in a table", 'sql', 'sql_duplicates'),
    ("how do i use git to undo a commit", None, 'git_undo'),
    ("bash script to list all python files", 'bash', 'bash_file_ops'),
    ("how to validate an email address with regex in python", 'python', 'regex_email'),
    ("implement a binary search tree in python", 'python', 'bst'),
    ("how to reverse a linked list in c++", 'c++', 'linked_list'),
    ("write a binary search in typescript", 'typescript', 'binary_search'),
    ("how to flatten a nested list in rust", 'rust', 'flatten'),
    ("how to split a list into chunks in javascript", 'javascript', 'chunk_list'),
    ("remove duplicates from a list in go", 'go', 'dedup'),
    ("get the unique values from a list in python", 'python', 'dedup'),
    ("transpose a matrix in rust", 'rust', 'transpose_matrix'),
    ("count word frequency in a text in python", 'python', 'count_words'),
    ("make a slugify function in javascript", 'javascript', 'slugify'),
    ("implement a caesar cipher in go", 'go', 'caesar_cipher'),
    ("generate a random password in python", 'python', 'password_gen'),
    ("shuffle a list in rust", 'rust', 'shuffle_list'),
    ("memoize a function in javascript", 'javascript', 'memoize'),
    ("retry a function with exponential backoff in python", 'python', 'retry_backoff'),
    ("pretty print json in javascript", 'javascript', 'json_pretty'),
    ("write a python decorator", 'python', None),  # concept, not a generation task
    ("what is the capital of france", None, None),  # not a code query at all
]

# Queries that must generate (task + language both resolvable).
MUST_GENERATE = [
    "write a python function to check if a number is prime",
    "how to read a csv file with pandas",
    "write sql to find duplicate rows in a table",
    "how do i use git to undo a commit",
    "how to make a http request in node.js",
    "how to reverse a linked list in c++",
    "implement a binary search tree in python",
    "how to validate an email address with regex in python",
    "write a fizzbuzz program in java",
    "how to flatten a nested list in rust",
    "how to write a for loop in javascript",
    "how to convert a string to a number in javascript",
    "how to check if an array contains a value in javascript",
    "how to rename a file in python",
    "how to install a package with pip",
    "how to install a package with npm",
    "how to check disk space in linux",
    "how to kill a process in linux",
    "how to find what is using a port in linux",
    "how to comment in python",
    "how to check memory usage in linux",
    "how to split a list into chunks in javascript",
    "get the unique values from a list in python",
    "transpose a matrix in rust",
    "count word frequency in a text in python",
    "make a slugify function in javascript",
    "implement a caesar cipher in go",
    "generate a random password in python",
    "shuffle a list in rust",
    "memoize a function in javascript",
    "retry a function with exponential backoff in python",
    "pretty print json in javascript",
]

# Queries where the generated code must be in a specific language family.
LANG_CHECK = [
    ("how to reverse a string in c++", "c++", ["::", "std::reverse"]),
    ("how to write a for loop in javascript", "javascript", ["for (", "console.log"]),
    ("how to read a file line by line in go", "go", ["bufio", "os.Open"]),
    ("how to check if a number is prime in rust", "rust", ["fn is_prime"]),
    ("write a fizzbuzz program in java", "java", ["System.out.println"]),
    ("write sql to find duplicate rows in a table", "sql", ["HAVING"]),
    ("how do i use git to undo a commit", "bash", ["git reset", "git revert"]),
    ("how to check disk space in linux", "bash", ["df -h"]),
    ("how to install a package with npm", "bash", ["npm install"]),
]

# Queries that must generate: (task + language both resolvable).

# ── 2. End-to-end routing: (query, [required], [forbidden]) ────────────────
E2E_CASES = [
    # pandas must NOT return the giant panda bear article
    ("how to read a csv file with pandas", ["read_csv", "pandas"],
     ["panda bear", "ailuropoda"]),
    # git undo must return git commands, not the Wikipedia "Undo" article
    ("how do i use git to undo a commit", ["git", "reset", "revert"], []),
    # SQL duplicates -> real HAVING query
    ("write sql to find duplicate rows in a table", ["having", "count"], []),
    # node.js HTTP -> fetch/async code, not the HTTP protocol article
    ("how to make a http request in node.js", ["fetch", "async"], []),
    # C++ request must return C++, not Python
    ("how to reverse a linked list in c++", ["ListNode", "->"], ["def "]),
    ("how to reverse a string in rust", ["fn", "chars"], ["def "]),
    ("write a function to check if a number is prime in java",
     ["isPrime", "boolean"], ["def "]),
    # lambda concept must return the concept, not the map() entry
    ("what is a lambda function in python", ["anonymous", "lambda"],
     ["applies a given function to every item"]),
    # deploy answers must be about deployment, not creating an endpoint
    ("how to deploy a flask app to production", ["gunicorn", "proxy"], []),
    # sql counting
    ("sql how to count rows in a table", ["count"], []),
    # code generation with no language defaults sensibly
    ("write a function to check if a number is prime", ["prime", "def"], []),
    # binary search tree must not match binary search
    ("implement a binary search tree in python", ["binary search tree", "insert"], []),
    # concept entries from the curated code KB
    ("what is a database index", ["index", "speed"], []),
    ("what is the difference between http and https", ["encrypted", "tls"], []),
    # sysadmin questions must not return Wikipedia movie/Tiny-Core articles
    ("how to kill a process in linux", ["kill", "pid"], ["film", "science fiction"]),
    ("how to check disk space in linux", ["df", "du"], []),
    ("how to find what is using a port in linux", ["lsof", "port"], []),
    ("how to install a package with pip", ["pip install"], []),
    ("how to write a for loop in javascript", ["for", "loop"], ["event loop"]),
    ("how to convert a string to a number in javascript", ["Number", "parseInt"], ["Math.random"]),
    ("how to check if an array contains a value in javascript", ["includes"], ["password"]),
    ("how to rename a file in python", ["os.rename"], []),
    ("explain what a decorator does", ["decorator"], []),
    # code pasted in the query is the subject — must not be hijacked by the
    # previous conversation topic (regression: stress suite order)
    ("what does this do in python: [x*2 for x in range(5)]", ["comprehension"], []),
]

# ── 3. Multi-turn language-switch follow-ups ───────────────────────────────
# The first query establishes a code task; the follow-up must redo it in a
# different language (not fall into Wikipedia).
FOLLOWUP_PAIRS = [
    ("write a python function to check if a number is prime",
     "now do the same in rust", ["fn is_prime"]),
    ("write a function to reverse a string",
     "do that in go", ["func ReverseString"]),
    ("how to reverse a linked list in c++",
     "do the same in python", ["def reverse_list"]),
]


def main():
    reset_conversation()
    failed = 0
    failures = []

    def check(name, ok, detail):
        nonlocal failed
        if not ok:
            failed += 1
            failures.append((name, detail))

    # 1. language + task detection
    for query, exp_lang, exp_task in LANG_TASK_CASES:
        lang = detect_language(query)
        task = detect_task(query)
        check(f"detect {query!r}",
              lang == exp_lang and task == exp_task,
              f"lang={lang} (want {exp_lang}), task={task} (want {exp_task})")

    # 2. generation happens for the expected queries
    for query in MUST_GENERATE:
        out = generate_code(query)
        check(f"generate {query!r}", bool(out),
              f"generate_code returned None: {out!r}")

    # 3. generated code always contains a fenced code block
    for query in MUST_GENERATE[:5]:
        out = generate_code(query)
        check(f"fence {query!r}", out and '```' in out,
              "no code fence in generated output")

    # 3b. generated code is in the requested language
    for query, exp_lang, snippets in LANG_CHECK:
        out = generate_code(query)
        low = (out or '').lower()
        ok = out is not None and f'```{exp_lang}' in low and all(
            s.lower() in low for s in snippets)
        check(f"lang {query!r}", ok,
              f"want lang={exp_lang} + {snippets}, got: {(out or 'None')[:140]!r}")

    # 4. end-to-end routing through the engine
    for query, required, forbidden in E2E_CASES:
        response = process_query(query)
        low = response.lower()
        missing = [k for k in required if k.lower() not in low]
        bad = [f for f in (forbidden + FALLBACK_PHRASES) if f.lower() in low]
        check(f"e2e {query!r}",
              not missing and not bad,
              f"missing={missing} forbidden={bad} | {response[:240]}")

    # 4b. website generation (HTML/CSS, topic-aware, no knowledge hijack)
    WEB_CASES = [
        ('create a simple website for a taco shop', 'Taco Shop', 'Carnitas'),
        ('make me a landing page for my startup', 'Startup', '<!DOCTYPE html>'),
        ('build a portfolio website', 'Portfolio', '<!DOCTYPE html>'),
        ('create a website for a pizza place', 'Pizza', 'Margherita'),
        ('design a website for a coffee shop', 'Coffee', 'Espresso'),
        ('taco shop website', 'Taco Shop', '<!DOCTYPE html>'),
    ]
    for query, name, snippet in WEB_CASES:
        out = generate_code(query)
        low = (out or '').lower()
        ok = (out is not None and '```html' in low
              and name.lower() in low and snippet.lower() in low
              and 'tim berners-lee' not in low)
        check(f"website {query!r}", ok,
              f"want {name} + {snippet}, got: {(out or 'None')[:160]!r}")
    for query in ('what is a website', 'visit the website',
                  'that website is slow'):
        check(f"website not hijacked {query!r}",
              detect_task(query) is None
              and '```html' not in (generate_code(query) or ''),
              'bare website mentions must not synthesize a page')
    check("website via engine (no file needed)",
          '```html' in process_query('create a simple website for a taco shop'),
          'engine should synthesize the page, not answer with a definition')

    # 5. multi-turn language-switch follow-ups
    reset_conversation()
    for first, follow, snippets in FOLLOWUP_PAIRS:
        process_query(first)
        response = process_query(follow)
        low = response.lower()
        missing = [k for k in snippets if k.lower() not in low]
        bad = [f for f in FALLBACK_PHRASES if f.lower() in low]
        check(f"followup {follow!r}",
              not missing and not bad,
              f"missing={missing} forbidden={bad} | {response[:240]}")

    total = (len(LANG_TASK_CASES) + len(MUST_GENERATE) * 2 + len(LANG_CHECK)
             + len(E2E_CASES) + len(WEB_CASES) + 4 + len(FOLLOWUP_PAIRS))
    print(f"Results: {total - failed}/{total} passed")
    if failures:
        print("\nFAILURES:")
        for name, detail in failures:
            print(f"  ✗ {name}\n    {detail}")
        sys.exit(1)


if __name__ == '__main__':
    main()
