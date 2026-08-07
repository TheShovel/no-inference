#!/usr/bin/env python3
"""Probe battery #2 — harder, more varied developer requests.

A second wave of realistic prompts with trickier phrasings, compound
requests, and less common tasks, to find blind spots the first battery
missed. (query, expected_task_or_None, expected_lang_or_None, snippet)
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from cos.engine import process_query, reset_conversation  # noqa: E402
from cos import code_gen  # noqa: E402

# Probes must not pollute the repo's persistent Wikipedia cache.
import cos.engine as _engine  # noqa: E402
import tempfile as _tempfile  # noqa: E402
_engine._WIKI_CACHE_FILE = _engine.Path(_tempfile.mktemp(suffix='.json'))
_engine._WIKI_CACHE.clear()

BATTERY = [
    # ── alternative phrasings of covered tasks ──────────────────────────────
    ("how do i check whether a number is prime in python", "prime", "python", "def is_prime"),
    ("javascript function to find prime numbers up to 100", "prime", "javascript", "isPrime"),
    ("calculate the factorial of 10 in python", "factorial", "python", "factorial"),
    ("fibonacci sequence in java", "fibonacci", "java", "fibonacci"),
    ("is this number even or odd in python", "is_even", "python", "% 2"),
    ("how to get the last item of a python list", None, "python", "[-1]"),
    ("split a sentence into words in python", "string_to_list", "python", "split"),
    ("check if a word is a palindrome", "palindrome_string", "python", "def is_palindrome"),
    ("how do i count vowels in a string in python", None, "python", "vowel"),
    ("find the duplicate elements in a list python", None, "python", "Counter"),
    ("sort this list in descending order python", "sort_list", "python", "reverse=True"),
    ("python read file and count words", None, "python", "Counter"),
    ("how to convert a list of strings to integers in python", None, "python", "map"),
    ("python dictionary get value by key", None, "python", "get"),
    ("how to check if a key exists in a python dict", None, "python", "exists"),
    ("iterate over two lists at the same time in python", "zip_lists", "python", "zip("),
    ("python how to make a deep copy of a list", "deep_copy", "python", "copy.deepcopy"),
    ("append to a list in python", None, "python", "append"),
    ("remove an item from a list in python", None, "python", "remove"),
    ("python sort dictionary by key", None, "python", "sorted"),
    ("find the index of an element in a python list", None, "python", "index"),
    ("how to generate random numbers in python", "random_number", "python", "random"),
    ("get today's date as a string in python", None, "python", "date.today"),
    ("python format number with commas", None, "python", "f'{"),
    ("how to check the type of a variable in python", None, "python", "type("),
    ("convert string to datetime in python", None, "python", "strptime"),
    ("python how to round to 2 decimal places", "round_decimal", "python", "round"),
    ("javascript get current year", None, "javascript", "getFullYear"),
    ("javascript uppercase first letter", None, "javascript", "toUpperCase"),
    ("javascript check if array is empty", "list_empty", "javascript", ".length"),
    ("javascript remove first element of array", None, "javascript", "shift"),
    ("javascript add item to start of array", None, "javascript", "unshift"),
    ("javascript object to array of values", None, None, None),
    ("javascript loop through array with index", None, "javascript", "forEach"),
    ("javascript find max value in array", "largest_number", "javascript", "Math.max"),
    ("javascript string repeat n times", None, "javascript", "repeat"),
    ("javascript replace spaces with dashes", "slugify", "javascript", "replace"),
    ("how to write a sql join between users and orders", "sql_join", "sql", "JOIN"),
    ("sql count of orders per customer", "sql_group_by", "sql", "COUNT"),
    ("sql sum of a column grouped by month", None, "sql", "GROUP BY"),
    ("sql query for customers who made no orders", "sql_left_join", "sql", "LEFT JOIN"),
    ("bash script to find files larger than 1GB", "sys_large_files", "bash", "find"),
    ("bash how to check if a command exists", None, "bash", "command -v"),
    ("bash extract text between quotes", None, "bash", "sed"),
    ("bash rename all .txt files to .md", None, "bash", "rename"),
    ("linux find process by name", "sys_kill", "bash", "pgrep"),
    ("how to see open ports in linux", "sys_port", "bash", "ss -tulpn"),
    ("git commit message conventions", None, "bash", "commit"),
    ("how to discard unstaged changes in git", "git_undo", "bash", "git checkout"),
    # ── compound / multi-step ───────────────────────────────────────────────
    ("write a python function that reads a csv and returns the sum of a column", None, "python", "csv"),
    ("python script to download a file and save it to disk", "http_get", "python", "requests.get"),
    ("write a python function to check if a string contains only digits", None, "python", "isdigit"),
    ("python program to find prime numbers between 1 and 100", "prime", "python", "range"),
    ("write a function to count the frequency of each character in a string", "count_occurrences", "python", "Counter"),
    ("python function to remove vowels from a string", None, "python", "re.sub"),
    ("write a python function that takes a list and returns the sum of even numbers", None, "python", "sum"),
    ("implement a function that checks if two strings are anagrams case-insensitively", "anagram", "python", "anagram"),
    ("write a python script that watches a directory for new files", None, "python", "watch"),
    ("python function to get the nth largest element in a list", None, "python", "nlargest"),
    ("create a python function that converts a dictionary to a list of tuples", None, "python", "items"),
    # ── harder / less common tasks ──────────────────────────────────────────
    ("write a python function that validates a credit card number using luhn", None, "python", "luhn"),
    ("python function to find all permutations of a string", None, "python", "permutations"),
    ("implement binary search recursively in python", "binary_search", "python", "def binary_search"),
    ("python function to check if a number is a perfect square", None, "python", "math.isqrt"),
    ("write a function to compute the nth prime number in python", "nth_prime", "python", "def nth_prime"),
    ("python function to convert a number to its word form", None, "python", "words"),
    ("implement a simple calculator in python", None, "python", "def"),
    ("python function to find the mode of a list", "most_frequent", "python", "Counter"),
    ("write a python function that returns the intersection of two lists", "list_intersection", "python", "&"),
    ("python function to check if a string is a valid phone number", "regex_phone", "python", "re."),
    ("write a python function to mask credit card numbers in a string", None, "python", "re.sub"),
    ("python function to extract hashtags from a tweet", None, "python", "findall"),
    ("implement a simple text-based tic tac toe game in python", None, "python", "def"),
    ("python function to rotate a matrix 90 degrees", "transpose_matrix", "python", "zip"),
    ("write a python function to check if a number is a palindrome", None, "python", "str"),
    ("python function to find the second largest number in a list", None, "python", "sorted"),
    ("implement a binary tree level order traversal in python", None, "python", "deque"),
    ("python function to invert a dictionary", "reverse_dict", "python", "items"),
    ("write a python function to shuffle a string", "shuffle_list", "python", "random"),
    # ── concept-style but code-adjacent ─────────────────────────────────────
    ("what is the difference between a list and a tuple in python", None, None, "immutable"),
    ("explain how python decorators work", None, "python", "decorator"),
    ("how does garbage collection work in python", None, None, None),
    ("what is the time complexity of binary search", None, None, "log"),
    ("explain what a rest api is", None, None, None),
    ("how do i choose between a list and a set in python", None, "python", "set"),
    # ── transforms / pasted code ────────────────────────────────────────────
    ("convert this code to javascript: def add(a, b):\n    return a + b", None, "javascript", "function add"),
    ("add error handling to this code: x = int(input())", None, "python", "try"),
    ("explain this code: def fib(n):\n    return n if n < 2 else fib(n-1) + fib(n-2)", None, None, "fib"),
    ("rename the variable x to total in this code: total = x + 1", None, "python", "total"),
    ("make this code faster: result = []\nfor i in range(1000):\n    result.append(i * 2)", None, "python", "comprehension"),
    # ── editor fill-ins (chat path) ─────────────────────────────────────────
    ("complete this function: def is_even(n):\n    ...", None, "python", "% 2"),
    ("fill in the missing code: def square(x):\n    return ...", None, None, None),
    # ── follow-ups (need conversation state) ────────────────────────────────
    ("write a python function to reverse a string", "reverse_string", "python", "def reverse_string"),
]

# The follow-up pair shares one conversation (no reset between them):
FOLLOWUP_PAIR = (
    "write a python function to reverse a string",
    "now do the same in rust",
    "fn reverse_string",
)


def _fence_lang(answer: str):
    m = re.search(r'```([^\s`]+)', answer or '')
    if not m:
        return None
    lang = m.group(1).lower()
    return {'js': 'javascript', 'py': 'python', 'cpp': 'c++', 'cs': 'c#', 'jsx': 'javascript', 'tsx': 'javascript', 'ts': 'typescript'}.get(lang, lang)


def _has_fence(answer: str) -> bool:
    return bool(re.search(r'```', answer or ''))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    results = []
    reset_conversation()
    for q, exp_task, exp_lang, snippet in BATTERY:
        reset_conversation()
        task = code_gen.detect_task(q)
        lang = code_gen.detect_language(q)
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

    # Follow-up pair: same conversation, second query must redo the task.
    first, follow, snip = FOLLOWUP_PAIR
    reset_conversation()
    process_query(first)
    response = process_query(follow)
    ok = snip in (response or '').lower()
    results.append({'q': follow, 'ok': ok,
                    'reasons': [] if ok else [f'missing {snip!r}'],
                    'response': response})

    passed = sum(1 for r in results if r['ok'])
    print(f'PROBE2: {passed}/{len(results)} pass ({100.0*passed/len(results):.1f}%)')
    if args.json:
        print(json.dumps([{k: r[k] for k in ('q', 'ok', 'reasons')} for r in results], indent=1))
        return
    for r in results:
        if not r['ok']:
            print(f"[{', '.join(r['reasons'])}] {r['q']}")
            print('   head:', (r['response'] or 'None')[:220].replace('\n', ' '))


if __name__ == '__main__':
    main()
