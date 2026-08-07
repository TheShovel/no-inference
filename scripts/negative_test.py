#!/usr/bin/env python3
"""NEGATIVE test: out-of-distribution prompts to find the real ceiling.

Deliberately NOT covered by the probe batteries. No fixes applied — this is
a measurement pass. Each query is judged on CONTENT relevance:
  GOOD   = answer is on-topic and gives correct, usable content
  PARTIAL = right topic but generic/missing the specific ask
  BAD    = wrong topic, Wikipedia garbage, or the generic fallback
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import cos.engine as _engine
import tempfile as _tempfile
_engine._WIKI_CACHE_FILE = _engine.Path(_tempfile.mktemp(suffix='.json'))
_engine._WIKI_CACHE.clear()

from cos.engine import process_query, reset_conversation  # noqa: E402

BATCHES = {
    'A. novel phrasings': [
        "i need something that walks a directory tree and renames all .tmp files to .bak",
        "gimme a function that tells me if two strings are rotations of each other",
        "how do i check whether a number is a power of two",
        "sort this list but keep the zeros at the end",
        "what's the cleanest way to read a big file in chunks in python",
        "write me a script that watches a folder and zips anything new",
        "how would i count how many times each word appears in a text file",
        "i need to extract every link from an html page in python",
        "make a timer that runs a task every 10 seconds in bash",
        "convert temperatures between celsius and fahrenheit in go",
    ],
    'B. genuinely new tasks': [
        "write a websocket echo server in python",
        "implement a bloom filter in python",
        "write a binary tree from preorder and inorder traversal in java",
        "implement a debounce function in go",
        "write a promise-based retry wrapper in javascript",
        "how do i do a left outer join with pandas merge",
        "implement a lock-free queue in go",
        "write a crc32 checksum function in rust",
        "how do i build a collaborative filtering recommender",
        "implement a trie with wildcard search in python",
    ],
    'C. bug reports / debugging': [
        "why does this crash: x = [1, 2, 3]; print(x[5])",
        "this code prints None, why: def f(): print('hi'); print(f())",
        "my regex matches too much: re.findall(r'<.+>', '<a>x</a><b>y</b>')",
        "this js gives NaN: parseInt('12px') * '3'",
        "race condition in this go code: var c int; go func(){c++}(); go func(){c++}(); fmt.Println(c)",
        "my python script pegs the cpu at 100%",
        "File \"app.py\", line 5, in <module>  user[\"name\"]  KeyError: 'name'",
        "the button in my react component doesn't fire the handler",
        "it works on my machine but the docker container crashes on startup",
        "why is my sql query so slow: SELECT * FROM orders WHERE customer_id IN (SELECT id FROM customers WHERE active = 1)",
    ],
    'D. multi-step builds': [
        ("write a todo list cli in python", "add a deadline field and sort by it", "make it store todos in sqlite"),
        ("write a function that finds primes up to n", "now make it a generator", "now parallelize it"),
        ("build a chat server with node", "add authentication", "persist messages to a file"),
    ],
    'E. vague / garbled': [
        "code for sum thing with list",
        "python read json and do stuff",
        "make it fast",
        "fix my code pls: def f(x): return x*x  print(f(4))",
        "how 2 sort in py",
        "give me a regex",
    ],
}


def _head(r, n=220):
    return (r or '').replace('\n', ' | ')[:n]


def main():
    results = []
    reset_conversation()
    for batch, items in BATCHES.items():
        print('=' * 90)
        print(f'## {batch}')
        print('=' * 90)
        for it in items:
            if isinstance(it, tuple):
                # multi-step: run the chain in one conversation
                reset_conversation()
                responses = []
                for q in it:
                    responses.append(process_query(q))
                verdicts = _judge_multi(it, responses)
                for q, v, r in zip(it, verdicts, responses):
                    results.append((batch, q, v))
                    print(f'  [{v}] {q}')
                    print(f'        {_head(r)}')
                continue
            q = it
            reset_conversation()
            r = process_query(q)
            v = _judge(q, r)
            results.append((batch, q, v))
            print(f'  [{v}] {q}')
            print(f'        {_head(r)}')

    print()
    print('=' * 90)
    print('SUMMARY')
    print('=' * 90)
    from collections import Counter
    total = len(results)
    counts = Counter(v for _, _, v in results)
    good = counts['GOOD']
    print(f'total: {total}  GOOD: {good} ({100.0*good/total:.0f}%)  '
          f'PARTIAL: {counts["PARTIAL"]}  BAD: {counts["BAD"]}')
    for batch in BATCHES:
        sub = [v for b, _, v in results if b == batch]
        g = sum(1 for v in sub if v == 'GOOD')
        print(f'  {batch}: {g}/{len(sub)} good')
    return 0


def _judge(q, r):
    low = (r or '').lower()
    fallback = ('exact recipe' in low or "couldn't find solid information" in low
                or "don't have a ready-made answer" in low)
    if fallback:
        return 'BAD'
    has_fence = '```' in low
    # Wikipedia-ish generic prose (long flat paragraphs, no code) for a
    # code request:
    if not has_fence and (' is a ' in low or ' refers to ' in low or ' wikipedia ' in low):
        return 'BAD' if _wants_code(q) else 'GOOD'
    # check relevance: at least one content word from the query appears
    content = _content_words(q)
    hit = sum(1 for w in content if w in low)
    if has_fence:
        return 'GOOD' if hit >= 1 else 'PARTIAL'
    return 'PARTIAL' if hit >= 1 else 'BAD'


def _judge_multi(chain, responses):
    verdicts = []
    for i, (q, r) in enumerate(zip(chain, responses)):
        v = _judge(q, r)
        if i > 0:
            # follow-ups must reference the prior topic
            prior_words = _content_words(chain[i - 1])
            if not any(w in (r or '').lower() for w in prior_words[:3]):
                v = 'BAD' if v == 'PARTIAL' else v
        verdicts.append(v)
    return verdicts


def _content_words(q):
    stop = {'the', 'a', 'an', 'and', 'or', 'in', 'on', 'of', 'to', 'for', 'with',
            'how', 'do', 'i', 'my', 'me', 'this', 'that', 'it', 'why', 'does',
            'code', 'write', 'make', 'implement', 'now', 'add', 'is', 'pls'}
    return [w for w in re.findall(r'[a-z0-9]+', q.lower()) if w not in stop and len(w) > 2]


def _wants_code(q):
    return bool(re.search(r'\b(write|implement|make|build|fix|code|function|script)\b', q.lower()))


if __name__ == '__main__':
    sys.exit(main())
