#!/usr/bin/env python3
"""Battery for text/code transformation of pasted content.

Covers the deterministic transformer pipeline:
  - code: add error handling, convert python<->javascript, rename identifiers,
    add comments, make faster, explain, loop conversion
  - text: politeness, extractive summarization, phrasebook translation
  - routing: each request must go to the transformer, never Wikipedia/the
    generic fallback

Run with:  python3 tests/test_code_transformer.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import cos.code_knowledge as code_knowledge
import cos.nlg.fallback as _nf
import cos.engine as engine
from cos.code_transformer import detect_code_transform, transform_code
from cos.engine import process_query, reset_conversation

# Offline: no network anywhere
code_knowledge._search_stack = lambda query, max_files=2: []
_nf.fallback_response = lambda q, c: 'FALLBACK-NETWORK'
engine._search_wikipedia = lambda query: (None, None)
engine._search_wikipedia_full = lambda query: (None, None)

FALLBACK_PHRASES = [
    "i do not have enough specific information",
    "i'm not sure about that",
    "i could not find enough",
    "fallback-network",
    "here's a {lang}",
]

# ── 1. unit checks on the transformer ───────────────────────────────────────
# (query, expected_op, [required-in-output], [forbidden-in-output])
UNIT = [
    ("add error handling to this code: def divide(a, b):\n    return a / b",
     "add_errors", ["try:", "except Exception"], []),
    ("make this code more robust: def f(x):\n    return x",
     "add_errors", ["try:", "except"], []),
    ("convert this code from python to javascript: def double(x):\n    return x * 2",
     "convert_lang", ["function double(x)", "return x * 2;"], ["def double"]),
    ("convert this code from javascript to python: function add(a, b) {\n  return a + b;\n}",
     "convert_lang", ["def add(a, b):", "return a + b"], ["function add"]),
    ("convert this code to javascript: def double(x):\n    return x * 2",
     "convert_lang", ["function double(x)"], ["def double"]),
    ("convert this python code to javascript: def double(x):\n    return x * 2",
     "convert_lang", ["function double(x)"], ["def double"]),
    ("rename the variable x to y in this code: x = 5\nprint(x)",
     "rename", ["y = 5", "print(y)"], ["print(x)"]),
    ("add comments to this code: def add(a, b):\n    return a + b",
     "add_comments", ["# Define the function add"], []),
    ("make this code faster: result = []\nfor i in range(100):\n    result.append(i*2)",
     "make_faster", ["[i*2 for i in range(100)]"], ["result.append"]),
    ("explain this code: for i in range(10):\n    print(i)",
     "explain", ["Loop over", "Print"], []),
    ("convert the for loop to a while loop in this code: for i in range(5):\n    print(i)",
     "loop_convert", ["while i < 5", "i += 1"], ["for i in range"]),
    ("convert the while loop to a for loop in this code: i = 0\nwhile i < 5:\n    print(i)\n    i += 1",
     "loop_convert", ["for i in range(0, 5)"], ["while"]),
]

# ── 2. end-to-end routing through the engine ────────────────────────────────
# (query, [required], [forbidden])
E2E = [
    ("add error handling to this code: def divide(a, b):\n    return a / b",
     ["try:", "except"], ["wikipedia"]),
    ("convert this code from python to javascript: def double(x):\n    return x * 2",
     ["function double"], ["def double"]),
    ("rename the variable x to y in this code: x = 5\nprint(x)",
     ["y = 5", "print(y)"], []),
    ("add comments to this code: def add(a, b):\n    return a + b",
     ["Define the function add"], []),
    ("explain this code: for i in range(10):\n    print(i)",
     ["Loop over", "Print"], []),
    ("make this code faster: result = []\nfor i in range(100):\n    result.append(i*2)",
     ["list comprehension", "for i in range(100)]"], []),
    ("make this text more polite: give me the report by friday or else",
     ["could you please", "thank you"], ["or else"]),
    ("summarize this text: The Industrial Revolution was a period of major industrialization that took place during the late 1700s and early 1800s. It began in Great Britain and quickly spread across the world. The textile industry was the first to be transformed, using new machines and factories. Steam power became the primary source of energy for factories and transportation.",
     ["Industrial Revolution", "textile"], []),
    ("translate this to spanish: hello. how are you?",
     ["Hola", "Cómo estás"], []),
    ("translate this to french: i like pizza",
     ["J'aime"], []),
    # these must NOT be hijacked by the transformer
    ("make this text more formal: give me the report by friday or else",
     ["formal"], []),
    ("summarize the plot of the odyssey",
     ["odyssey", "homer"], ["Summary"]),
    ("what is the capital of france",
     ["paris"], []),
]

# ── 3. multi-turn: transformations applied to the previous edit ────────────
# (first query, follow-up, [required in follow-up response])
MULTITURN = [
    ("fix this code: def factorial(n):\n    if n == 0:\n        retrun 1\n    return n * factorial(n-1)",
     "add comments to the last code", ["Define the function factorial"]),
    ("fix this code: def factorial(n):\n    if n == 0:\n        retrun 1\n    return n * factorial(n-1)",
     "convert it to javascript", ["function factorial(n)", "return n * factorial(n-1);"]),
    ("fix this code: def greet(name):\n    print(\"hello \" + name)",
     "rename name to person in the last code", ["def greet(person)", "print(\"hello \" + person)"]),
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

    # 1. transformer unit checks
    check("convert to french not a code convert",
          detect_code_transform("convert this code to french: def f():\n    pass")
          is None,
          "was detected as a code convert")
    for query, op, required, forbidden in UNIT:
        det = detect_code_transform(query)
        if det is None:
            check(f"detect {query[:40]!r}", False, "not detected")
            continue
        got_op, params, code, lang = det
        edited, notes = transform_code(got_op, params, code, lang)
        low = edited.lower()
        missing = [k for k in required if k.lower() not in low]
        bad = [f for f in forbidden if f.lower() in low]
        check(f"transform {query[:40]!r}",
              got_op == op and not missing and not bad,
              f"op={got_op} (want {op}) missing={missing} bad={bad} | {edited[:200]!r}")

    # 2. end-to-end routing
    for query, required, forbidden in E2E:
        response = process_query(query)
        low = response.lower()
        missing = [k for k in required if k.lower() not in low]
        bad = [f for f in (forbidden + FALLBACK_PHRASES) if f.lower() in low]
        check(f"e2e {query[:45]!r}",
              not missing and not bad,
              f"missing={missing} forbidden={bad} | {response[:220]}")

    # 3. multi-turn follow-ups on the previous edit
    reset_conversation()
    for first, follow, required in MULTITURN:
        process_query(first)
        response = process_query(follow)
        low = response.lower()
        missing = [k for k in required if k.lower() not in low]
        bad = [f for f in FALLBACK_PHRASES if f.lower() in low]
        check(f"multiturn {follow!r}",
              not missing and not bad,
              f"missing={missing} forbidden={bad} | {response[:220]}")

    # 4. typed-signature error handling: the def must be wrapped, not dropped
    typed = 'def factorial(n: int) -> int:\n    result = 1\n    return result\n'
    edited, _ = transform_code('add_errors', {}, typed, 'python')
    check('typed sig wrapped (not dropped)',
          'try:' in edited and 'except Exception' in edited
          and 'def factorial(n: int) -> int:' in edited,
          f'got: {edited[:160]!r}')

    total = len(UNIT) + len(E2E) + len(MULTITURN) + 1
    print(f"Results: {total - failed}/{total} passed")
    if failures:
        print("\nFAILURES:")
        for name, detail in failures:
            print(f"  ✗ {name}\n    {detail}")
        sys.exit(1)


if __name__ == '__main__':
    main()
