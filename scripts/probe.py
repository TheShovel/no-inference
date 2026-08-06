#!/usr/bin/env python3
"""Gap probe: run a batch of queries, flag weak responses (fallbacks / too short).

Usage: python3 scripts/probe.py  (edit the QUERIES list below per round)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cos.engine import process_query

QUERIES = [
    # coding
    "how do i merge two dictionaries in python",
    "how to sort a list of dictionaries by a key in python",
    "how to read a json file in javascript",
    "what does the map function do in javascript",
    "how to check if a string contains a substring in python",
    "how to remove duplicates from a list in python",
    "how to reverse a string in java",
    "how to concatenate strings in golang",
    "how to write a function in rust",
    "how to left join two tables in sql",
    "how to rename a column in sql",
    "how to convert a string to an integer in python",
    "how to check if a file exists in python",
    "how to read a csv file in pandas",
    "what is a lambda function in python",
    "how to catch an exception in python",
    "how to check if a number is prime in python",
    "how to reverse a linked list",
    "what is big o notation",
    "how to write a unit test in python",
    "how to squash commits in git",
    "how to write a dockerfile",
    "what is the difference between a list and a tuple in python",
    "what is the difference between an array and a linked list",
    "what is recursion",
    "what is a hash table",
    "what is a deadlock",
    "what is a rest api",
    "what is the difference between http and https",
    "what is a database index",
    "what is sql injection",
    "what is the difference between a compiler and an interpreter",
    "what is the difference between a framework and a library",
    "what is the singleton pattern",
    "what is a microservice",
    "what is the difference between docker and kubernetes",
    "what is the difference between a process and a thread",
    "what is a firewall",
    "what is the difference between encryption and hashing",
    "what is the difference between a stack and a queue",
    "what is a binary search",
    "what is time complexity",
    "what is a palindrome",
    "what is inheritance",
    "what is polymorphism",
    "what is a promise",
    "what is a race condition",
    "what is the difference between a monolith and microservices",
    "what is a 404",
    "what is a join",
    "what is a group by",
    "what is a stored procedure",
    "what is normalization",
    "what is an orm",
    "what is a unit test",
    "what is a pull request",
    "what is a sprint",
    "what is agile",
    "what is a kpi",
    "what is a heuristic",
    "what is a genetic algorithm",
    # everyday
    "how to get rid of a cold fast",
    "how to soothe a sore throat",
    "how to reduce a fever",
    "how to stop coughing at night",
    "how to unclog a stuffy nose",
    "how to get rid of heartburn fast",
    "how to get rid of a wart",
    "how to treat sunburn",
    "how to treat a bee sting",
    "how to remove a tick safely",
    "how to stop mosquito bites from itching",
]

weak = 0
for t in QUERIES:
    r = process_query(t)
    fb = any(f in r.lower() for f in [
        'i could not find', 'i couldn\'t find solid', 'not sure about that',
        'fallback', 'i do not have enough'])
    if fb or len(r) < 60:
        weak += 1
        print(f'[WEAK] {t} -> {r[:120]}')
    else:
        print(f'[OK] {t} ({len(r)} chars)')
print(f'{len(QUERIES)-weak}/{len(QUERIES)} solid, {weak} weak')
