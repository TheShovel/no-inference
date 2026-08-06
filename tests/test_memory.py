#!/usr/bin/env python3
"""Load-on-demand memory machinery: cheap KB counting, cache release and
TTL auto-unload, bounded conversation history, and the API server not
preloading the full KB at startup.
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cos import knowledge as kb  # noqa: E402
from cos.state import conversation_history, trim_conversation  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  ✓ {name}')
    else:
        FAIL += 1
        print(f'  ✗ {name}')


def test_cheap_count():
    print('\nSuite: cheap KB count (no full load)')
    kb._KNOWLEDGE_CACHE = None
    cheap = kb.count_knowledge_entries()
    check('count parses without loading', cheap > 10000)
    check('cache still unloaded', kb._KNOWLEDGE_CACHE is None)
    entries = kb.get_all_knowledge()
    try:
        check('cheap count == loaded count', cheap == len(entries))
    finally:
        kb.release_knowledge()


def test_release_and_reload():
    print('\nSuite: release + on-demand reload')
    real_load = kb._load_knowledge
    calls = []

    def fake_load(*a, **kw):
        calls.append(1)
        return [(re.compile('^paris$', re.I), 'Paris is the capital of France.')]

    kb._load_knowledge = fake_load
    kb._KNOWLEDGE_CACHE = None
    try:
        kb.get_all_knowledge()
        check('first load happens', len(calls) == 1)
        kb.get_all_knowledge()
        check('cached (no second load)', len(calls) == 1)
        kb.release_knowledge()
        check('release clears cache', kb._KNOWLEDGE_CACHE is None)
        kb.get_all_knowledge()
        check('reloads on demand', len(calls) == 2)
    finally:
        kb._load_knowledge = real_load
        kb.release_knowledge()


def test_ttl_unload():
    print('\nSuite: TTL auto-unload')
    real_load = kb._load_knowledge
    calls = []

    def fake_load(*a, **kw):
        calls.append(1)
        return [(re.compile('^x$', re.I), 'y')]

    old_ttl = kb._KB_TTL
    kb._load_knowledge = fake_load
    kb._KNOWLEDGE_CACHE = None
    try:
        kb._KB_TTL = 0.05
        kb.get_all_knowledge()
        check('loaded once', len(calls) == 1)
        # simulate an idle gap, then touch the cache again
        kb._KNOWLEDGE_LOADED_AT = time.monotonic() - 1.0
        kb.get_all_knowledge()
        check('idle cache unloaded + reloaded', len(calls) == 2)
    finally:
        kb._KB_TTL = old_ttl
        kb._load_knowledge = real_load
        kb.release_knowledge()


def test_history_cap():
    print('\nSuite: bounded conversation history')
    conversation_history.clear()
    conversation_history.extend([(f'q{i}', f'a{i}') for i in range(250)])
    trim_conversation(200)
    check('history trimmed to 200', len(conversation_history) == 200)
    check('oldest kept is q50', conversation_history[0][0] == 'q50')
    check('latest kept is q249', conversation_history[-1][0] == 'q249')
    conversation_history.clear()


def test_server_does_not_preload():
    print('\nSuite: API server startup is cheap')
    kb._KNOWLEDGE_CACHE = None
    try:
        from api import server
        server._load_kb_size()
        check('status count populated', server._KB_SIZE > 10000)
        check('full KB not loaded just to count',
              kb._KNOWLEDGE_CACHE is None)
    finally:
        kb.release_knowledge()


def main():
    test_cheap_count()
    test_release_and_reload()
    test_ttl_unload()
    test_history_cap()
    test_server_does_not_preload()
    print(f'\nResults: {PASS}/{PASS + FAIL} passed')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
