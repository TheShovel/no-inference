#!/usr/bin/env python3
"""Probe batteries as a permanent regression suite.

Runs the full developer-prompt batteries from scripts/probe_coding.py and
scripts/probe_coding2.py through the real engine and asserts every probe
passes. This locks in the coding-routing and task-coverage improvements:
any future edit that regresses a covered phrasing fails here.

Run with:  python3 tests/test_probe_coding.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

# Route Wikipedia cache writes to a scratch file — never pollute the repo.
import tempfile
import cos.engine as engine
engine._WIKI_CACHE_FILE = engine.Path(tempfile.mktemp(suffix='.json'))
engine._WIKI_CACHE.clear()

from cos.engine import process_query, reset_conversation  # noqa: E402
from cos import code_gen  # noqa: E402

from probe_coding import BATTERY as BATTERY_1  # noqa: E402
from probe_coding2 import BATTERY as BATTERY_2  # noqa: E402
from probe_coding2 import FOLLOWUP_PAIR  # noqa: E402
from probe_coding3 import BATTERY as BATTERY_3  # noqa: E402
from probe_coding4 import BATTERY as BATTERY_4  # noqa: E402
from probe_coding5 import BATTERY as BATTERY_5  # noqa: E402
from probe_coding6 import BATTERY as BATTERY_6  # noqa: E402
from probe_coding6 import FOLLOWUP_PAIR as FOLLOWUP_PAIR_6  # noqa: E402
from probe_coding7 import BATTERY as BATTERY_7  # noqa: E402
from probe_coding8 import BATTERY as BATTERY_8  # noqa: E402
from probe_coding9 import BATTERY as BATTERY_9  # noqa: E402
from probe_coding10 import BATTERY as BATTERY_10  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


def check(name: str, cond: bool):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name)


def _fence_lang(answer: str):
    m = re.search(r'```([^\s`]+)', answer or '')
    if not m:
        return None
    lang = m.group(1).lower()
    return {'js': 'javascript', 'py': 'python', 'cpp': 'c++', 'cs': 'c#', 'jsx': 'javascript', 'tsx': 'javascript', 'ts': 'typescript'}.get(lang, lang)


def _has_fence(answer: str) -> bool:
    return bool(re.search(r'```', answer or ''))


def run_battery(name, battery):
    global PASS, FAIL
    for q, exp_task, exp_lang, snippet in battery:
        reset_conversation()
        task = code_gen.detect_task(q)
        response = process_query(q)
        low = (response or '').lower()
        ok = True
        detail = []
        if snippet is not None and snippet.lower() not in low:
            ok = False
            detail.append(f'missing snippet {snippet!r}')
        if exp_task is not None and task != exp_task:
            ok = False
            detail.append(f'task={task!r} want {exp_task!r}')
        if exp_lang is not None:
            fl = _fence_lang(response)
            if exp_lang == 'python' and fl is None and _has_fence(response):
                fl = 'python'
            if fl != exp_lang:
                ok = False
                detail.append(f'fence={fl!r} want {exp_lang!r}')
        if not response or len(response) < 30:
            ok = False
            detail.append('response too short')
        check(f'{name}: {q}', ok and not detail)
        if not ok:
            print(f'  ✗ {name}: {q}  {", ".join(detail)}')


def main():
    run_battery('probe1', BATTERY_1)
    run_battery('probe2', BATTERY_2)
    run_battery('probe3', BATTERY_3)
    run_battery('probe4', BATTERY_4)
    run_battery('probe5', BATTERY_5)
    run_battery('probe6', BATTERY_6)
    run_battery('probe7', BATTERY_7)
    run_battery('probe8', BATTERY_8)
    run_battery('probe9', BATTERY_9)
    run_battery('probe10', BATTERY_10)
    # battery-6 follow-up pair shares one conversation
    first, follow, snip = FOLLOWUP_PAIR_6
    reset_conversation()
    process_query(first)
    response = process_query(follow)
    check(f'followup6: {follow}', snip in (response or '').lower())
    if snip not in (response or '').lower():
        print(f'  ✗ followup6: {follow}  missing {snip!r}')
    # follow-up pair shares one conversation
    first, follow, snip = FOLLOWUP_PAIR
    reset_conversation()
    process_query(first)
    response = process_query(follow)
    check(f'followup: {follow}', snip in (response or '').lower())
    if snip not in (response or '').lower():
        print(f'  ✗ followup: {follow}  missing {snip!r}')

    total = PASS + FAIL
    print(f'Results: {PASS}/{total} passed')
    if FAILURES:
        print('\nFAILURES:')
        for f in FAILURES:
            print(f'  ✗ {f}')
        sys.exit(1)


if __name__ == '__main__':
    main()
