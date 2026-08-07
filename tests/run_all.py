#!/usr/bin/env python3
"""Run every test suite and print a summary.

Usage:  python3 tests/run_all.py   (or:  ./tests/run_all.py)
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = [
    ('regression',        'test_regression.py'),
    ('coding',            'test_coding.py'),
    ('code gen + routing', 'test_code_gen.py'),
    ('code/text transform', 'test_code_transformer.py'),
    ('practical knowledge', 'test_practical_knowledge.py'),
    ('editor (e2e)',      'test_editor.py'),
    ('editor changes',    'test_editor_changes.py'),
    ('editor benchmark',  'test_editor_bench.py'),
    ('stress',            'test_stress.py'),
    ('essay',             'test_essay.py'),
    ('nlg package',       'test_nlg_package.py'),
    ('context extraction', 'test_context_extraction.py'),
    ('code editor harness', 'test_code_editor.py'),
    ('workbench recipes', 'test_workbench_recipes.py'),
    ('tui + launcher', 'test_tui.py'),
    ('iterative refine', 'test_refine.py'),
    ('load-on-demand memory', 'test_memory.py'),
    ('freeform discovered', 'test_freeform_discovered.py'),
    ('coding probe batteries', 'test_probe_coding.py'),
    ('api server', 'test_api_server.py'),
]



def main():
    results = []
    for name, file in SUITES:
        print(f'\n── {name} ({file}) ' + '─' * max(0, 40 - len(name)))
        try:
            proc = subprocess.run(
                [sys.executable, os.path.join(HERE, file)],
                capture_output=True, text=True, timeout=900, check=False,
            )
            out = (proc.stdout or '') + (proc.stderr or '')
            # find the results line
            line = ''
            for ln in out.splitlines():
                if 'passed' in ln.lower() or 'total:' in ln:
                    line = ln.strip()
            ok = proc.returncode == 0
            results.append((name, ok, line or f'exit {proc.returncode}'))
        except subprocess.TimeoutExpired:
            results.append((name, False, 'TIMEOUT'))

    print('\n' + '=' * 60)
    print('SUMMARY')
    print('=' * 60)
    all_ok = True
    for name, ok, line in results:
        mark = 'PASS' if ok else 'FAIL'
        all_ok = all_ok and ok
        print(f'  [{mark}] {name:22s} {line}')
    print('=' * 60)
    print('ALL PASS' if all_ok else 'SOME SUITES FAILED')
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
