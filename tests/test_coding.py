#!/usr/bin/env python3
"""Regression battery for coding capabilities.

Each case is (query, [required_substrings], [forbidden_substrings]).
The response must contain every required substring (case-insensitive) and
none of the forbidden ones. Runs offline: the Stack dataset API fallback is
patched so results are deterministic and don't depend on the network.

Run with:  python3 tests/test_coding.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import cos.code_knowledge as code_knowledge
from cos.engine import process_query, reset_conversation

# Offline: no Stack API calls (60s timeouts would hang the battery)
code_knowledge._search_stack = lambda query, max_files=2: []

FALLBACK_PHRASES = [
    "i do not have enough specific information",
    "i'm not sure about that",
]

# (query, [required], [forbidden])
CASES = [
    # ── Python ────────────────────────────────────────────────────────────
    ("write a python function to check if a number is prime", ["prime", "def"]),
    ("how do i check if a number is prime in python", ["prime"]),
    ("python function to compute the factorial of a number", ["factorial"]),
    ("write a fizzbuzz program in python", ["fizz"]),
    ("python function to check if a string is a palindrome", ["palindrome"]),
    ("how to reverse a string in python", ["reverse"]),
    ("python list comprehension example", ["comprehension"]),
    ("what is a lambda function in python", ["lambda"]),
    ("what is a decorator in python", ["decorator"]),
    ("how do generators work in python", ["generator", "yield"]),
    ("what is the difference between a list and a tuple in python", ["list", "tuple"]),
    ("how do i handle exceptions in python", ["try", "except"]),
    ("python read a file line by line", ["open", "read"]),
    ("how to use the requests library in python", ["requests"]),
    ("python datetime current date and time", ["datetime"]),
    ("what are args and kwargs in python", ["args", "kwargs"]),
    ("what is a class in python oop", ["class"]),
    ("python dictionary get vs setdefault", ["dict", "get"]),
    ("python check if key exists in dict", ["key", "dict"]),
    ("how to merge two dictionaries in python", ["merge", "dict"]),
    ("python sort a list of dictionaries by a key", ["sort", "key"]),
    ("what is a set in python", ["set", "unique"]),
    ("python how to use enumerate", ["enumerate"]),
    ("python zip two lists", ["zip"]),

    # ── JavaScript ────────────────────────────────────────────────────────
    ("what is the difference between var let and const in javascript", ["let", "const"]),
    ("what is hoisting in javascript", ["hoist"]),
    ("what is a closure in javascript", ["closure"]),
    ("how do arrow functions work in javascript", ["arrow"]),
    ("what is the this keyword in javascript", ["this"]),
    ("javascript spread operator example", ["spread"]),
    ("javascript destructuring assignment", ["destructur"]),
    ("how do promises work in javascript", ["promise"]),
    ("how does async await work in javascript", ["async", "await"]),
    ("javascript map filter reduce", ["map", "filter", "reduce"]),
    ("how to fetch data from an api in javascript", ["fetch"]),
    ("javascript template literals", ["template"]),
    ("what is the event loop in javascript", ["event loop"]),
    ("javascript ternary operator", ["ternary"]),

    # ── General CS / data structures ──────────────────────────────────────
    ("what is the difference between a stack and a queue", ["stack", "queue"]),
    ("explain how a hash map works", ["hash"]),
    ("what is a linked list", ["linked list"]),
    ("what is big o notation", ["big o"]),
    ("what is recursion in programming", ["recursion"]),
    ("explain time complexity vs space complexity", ["time complexity"]),
    ("how does quicksort work", ["quicksort"]),
    ("what is a binary search tree", ["binary search tree"]),
    ("breadth first search vs depth first search", ["breadth", "depth"]),
    ("what is an algorithm", ["algorithm"]),

    # ── SQL ───────────────────────────────────────────────────────────────
    ("write a sql query to join two tables", ["join"]),
    ("what is the difference between inner join and left join", ["inner join", "left join"]),
    ("sql group by example", ["group by"]),
    ("what is the difference between where and having in sql", ["where", "having"]),
    ("how do sql indexes work", ["index"]),
    ("sql select distinct example", ["distinct"]),

    # ── Web / other ───────────────────────────────────────────────────────
    ("how to center a div in css", ["center"]),
    ("what is the difference between html and css", ["html", "css"]),
    ("how does the http request response cycle work", ["http"]),
    ("what is rest api", ["rest"]),
    ("what is the difference between git merge and rebase", ["merge", "rebase"]),
    ("what is docker", ["docker"]),
    ("what is a virtual environment in python", ["virtual"]),

    # ── Wave 2: harder topics ─────────────────────────────────────────────
    ("what are the http status codes and what do they mean", ["404", "500"]),
    ("what is the difference between get and post requests", ["get", "post"]),
    ("python dataclass example", ["dataclass"]),
    ("what are type hints in python", ["type hint"]),
    ("python how to use try except finally", ["finally"]),
    ("how do i read a csv file in python", ["csv"]),
    ("javascript array methods push pop shift unshift", ["shift", "unshift"]),
    ("javascript how to select an element with queryselector", ["queryselector"]),
    ("javascript add event listener click", ["eventlistener"]),
    ("how does json stringify and parse work in javascript", ["json"]),
    ("what is object oriented programming", ["object", "class"]),
    ("what are the four pillars of oop", ["inheritance", "polymorphism"]),
    ("what is the difference between an interface and an abstract class", ["interface", "abstract"]),
    ("what is a deadlock in concurrency", ["deadlock"]),
    ("python multithreading vs multiprocessing", ["thread"]),
    ("what is a sql transaction", ["transaction"]),
    ("what is the difference between primary key and foreign key", ["primary key", "foreign key"]),
    ("sql what is a subquery", ["subquery"]),
    ("what is database normalization", ["normaliz"]),
    ("what is the difference between an array and a linked list", ["array", "linked list"]),
    ("what is the two sum problem", ["two sum"]),
    ("how do you reverse a linked list", ["linked list", "reverse"]),
    ("what is dynamic programming", ["dynamic programming"]),
    ("what is the difference between http and https", ["https"]),
    ("what is a cookie vs a session", ["cookie", "session"]),
    ("what is jwt authentication", ["jwt"]),
    ("what is the difference between a process and a thread", ["process", "thread"]),
    ("python how to use pathlib to read files", ["pathlib"]),
    ("what is a unit test and why write them", ["unit test"]),
    ("python how to write a unit test with pytest", ["pytest"]),
]


def main():
    reset_conversation()
    passed = failed = 0
    failures = []
    for query, required, *rest in CASES:
        forbidden = rest[0] if rest else FALLBACK_PHRASES
        response = process_query(query)
        low = response.lower()
        missing = [k for k in required if k.lower() not in low]
        bad = [f for f in forbidden if f.lower() in low]
        if missing or bad:
            failed += 1
            failures.append((query, missing, bad, response[:260]))
        else:
            passed += 1

    print(f"Results: {passed}/{passed + failed} passed")
    if failures:
        print("\nFAILURES:")
        for query, missing, bad, snippet in failures:
            print(f"  Q: {query}")
            if missing:
                print(f"     missing: {missing}")
            if bad:
                print(f"     forbidden hit: {bad}")
            print(f"     response: {snippet}")
        sys.exit(1)


if __name__ == '__main__':
    main()
