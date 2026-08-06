#!/usr/bin/env python3
"""Battery for the code editor harness (cos.code_editor) + engine fill-in.

Covers:
  1. Buffer analysis: language, imports, definitions, indent style.
  2. complete_buffer: task-by-name, instruction-driven, scaffold fallback,
     JS extraction (no duplicate braces), tabs, TODO-comment instructions,
     marker variants ('...', 'pass').
  3. fill_in chat form + honest failure.
  4. detect_fill_request must NOT hijack transforms/explains.
  5. End-to-end through process_query.

Run with:  python3 tests/test_code_editor.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cos.code_editor import (analyze_buffer, complete_buffer, fill_in,
                             detect_fill_request)
from cos.engine import process_query, reset_conversation

_p = _f = 0


def check(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  \u2713 {name}")
    else:
        _f += 1
        print(f"  \u2717 {name}" + (f"  -- {detail}" if detail else ""))


# ── 1. buffer analysis ──────────────────────────────────────────────────────
def test_analyze():
    print("\nSuite: analyze_buffer")
    ctx = analyze_buffer('import os\nimport json\n\ndef unique(items):\n    ...\n',
                         filename='tool.py')
    check("language python", ctx['language'] == 'python')
    check("imports found", ctx['imports'] == ['os', 'json'])
    check("defs found", ('function', 'unique') in ctx['definitions'])
    check("indent 4 spaces", ctx['indent'] == {'kind': 'spaces', 'unit': 4})
    check("js from filename", analyze_buffer('x = 1', 'a.js')['language'] == 'javascript')
    check("go from filename", analyze_buffer('package main', 'a.go')['language'] == 'go')
    ctx2 = analyze_buffer('function a() {}\n\tfunction b() {}', 'x.js')
    check("tab indent detected", ctx2['indent']['kind'] == 'tabs')


# ── 2. complete_buffer ──────────────────────────────────────────────────────
def test_complete():
    print("\nSuite: complete_buffer")
    r = complete_buffer('def reverse_string(s: str) -> str:\n    ...\n')
    check("task-by-name body", r['changed'] and 's[::-1]' in r['text'])
    check("body indented 4", r['text'].startswith('    return s[::-1]'))

    r = complete_buffer('def solve(a, b):\n    ...\n',
                        instruction='find the greatest common divisor of a and b')
    check("instruction->gcd", r['changed'] and 'a % b' in r['text'])
    # relative indentation inside the while loop is preserved
    check("relative indent kept", 'while b:\n        a, b' in r['text'])

    r = complete_buffer('def frobnicate(x: int) -> bool:\n    pass\n')
    check("scaffold honest", r['changed'] and 'return False' in r['text'])
    check("scaffold note", any('scaffold' in n for n in r['notes']))

    r = complete_buffer('function dedupe(arr) {\n  // ...\n}\n')
    check("js unique body", r['changed'] and 'Set(' in r['text'])
    check("js no duplicate brace", r['text'].count('}') == 0)

    r = complete_buffer('def chunk(items, size):\n\t...\n')
    check("tabs preserved", '\t' in r['text'] and 'raise ValueError' in r['text'])

    r = complete_buffer('def greet(name):\n    # TODO: return a greeting\n    ...\n')
    check("TODO instruction", r['changed'] and 'Hello' in r['text'])

    r = complete_buffer('def f(x):\n    ...\n')
    check("unknown name -> scaffold not empty", r['changed'])
    check("scaffold note honest", any("couldn't infer" in n or 'scaffold' in n
                                      for n in r['notes']))

    r = complete_buffer('def add(a, b):\n    ...\n', instruction='sum of a and b')
    check("little recipe add", r['changed'] and 'a + b' in r['text'])

    # imports note only when body actually uses the module
    r = complete_buffer('def unique_items(items):\n    ...\n', filename='x.py')
    check("no bogus import note", not any('import' in n for n in r['notes']))
    r = complete_buffer('def slugify(s):\n    ...\n', filename='x.py')
    check("import note for re", any('`re`' in n for n in r['notes']))

    # cursor_pos points at a specific marker
    code = 'def a():\n    ...\n\ndef b():\n    ...\n'
    r = complete_buffer(code, cursor_pos=4)
    check("cursor_pos honored", r['replace_line'] == 4)

    # no marker -> unchanged
    r = complete_buffer('def done():\n    return 1\n')
    check("no marker unchanged", not r['changed'])

    # parameter alignment: signature param names replace the template's
    r = complete_buffer('def slugify(title):\n    ...\n')
    check("param alignment (title)", r['changed'] and 'title.lower()' in r['text']
          and 'text.lower()' not in r['text'])

    # name-prefix recipes: total/sum/count/avg/max/min + collection
    r = complete_buffer('def total_revenue(orders):\n    ...\n')
    check("total_ recipe", r['changed'] and 'sum(orders)' in r['text'])
    check("total_ note honest", 'list of numbers' in r['text'] + ' '.join(r['notes']))
    r = complete_buffer('def count_items(items):\n    ...\n')
    check("count_ recipe", r['changed'] and 'len(items)' in r['text'])
    r = complete_buffer('function average(nums) {\n  // ...\n}\n')
    check("avg js recipe", r['changed'] and 'reduce' in r['text'])


# ── 3. fill_in ──────────────────────────────────────────────────────────────
def test_fill_in():
    print("\nSuite: fill_in")
    ans = fill_in('complete this function: def is_prime(n):\n    ...')
    check("chat answer has fence", '```python' in ans)
    check("chat answer has body", 'if n < 2' in ans)
    check("marker replaced", '    ...' not in ans.split('```')[1])
    ans = fill_in('complete this: def whatever(x):\n    ...')
    check("no marker-ish answer", 'completed code' in ans or "couldn't" in ans)


# ── 4. detection safety ─────────────────────────────────────────────────────
def test_detect():
    print("\nSuite: detect_fill_request")
    check("transform not hijacked",
          not detect_fill_request('convert this code from python to javascript: '
                                  'def double(x):\n    return x * 2'))
    check("explain not hijacked",
          not detect_fill_request('explain this code: def foo(x):\n    return x'))
    check("plain fill detected",
          detect_fill_request('complete this function: def add(a, b):\n    ...'))
    check("fenced fill detected",
          detect_fill_request('fill in the body: ```python\ndef fib(n):\n    pass\n```'))
    check("real body not fill",
          not detect_fill_request('write a function that sums a list: '
                                  'def total(xs):\n    return sum(xs)'))


# ── 5. engine integration ───────────────────────────────────────────────────
def test_engine():
    print("\nSuite: engine fill-in")
    reset_conversation()
    r = process_query('complete this function: def is_prime(n):\n    ...')
    check("engine returns filled code", '```python' in r and 'if n < 2' in r)
    check("engine not fallback", 'could not find' not in r.lower())
    reset_conversation()
    r = process_query('complete the last code')
    check("no-last-edit guard", 'previous code' in r)
    reset_conversation()
    r = process_query('convert this code from python to javascript: '
                      'def double(x):\n    return x * 2')
    check("transform still works", 'function double' in r and 'javascript' in r)


# ── 6. reference CLI harness (examples/harness_cli.py) ──────────────────────
def test_cli():
    import json as _json
    import subprocess
    import tempfile

    print("\nSuite: example harness CLI")
    cli = os.path.join(os.path.dirname(__file__), '..', 'examples', 'harness_cli.py')
    cli = os.path.abspath(cli)
    code = ('import json\n\n\ndef load(path):\n    with open(path) as f:\n'
            '        return json.load(f)\n\n\ndef total(items):\n    ...\n')
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as fh:
        fh.write(code)
        path = fh.name
    try:
        # --json mode: filled + correct language + insertion + edited buffer
        proc = subprocess.run(
            [sys.executable, cli, path, '--json'],
            capture_output=True, text=True, timeout=60)
        check("cli exit 0 on fill", proc.returncode == 0)
        out = _json.loads(proc.stdout)
        check("cli ok flag", out['ok'] is True)
        check("cli language", out['language'] == 'python')
        check("cli insertion", 'sum(items)' in out['text'])
        check("cli edited buffer", 'sum(items)' in out['edited']
              and '...' not in out['edited'])
        # exit 1 when there is nothing to fill
        proc2 = subprocess.run(
            [sys.executable, cli, path, '--json', '--cursor', '1'],
            capture_output=True, text=True, timeout=60)
        check("cli exit 1 on no-fill", proc2.returncode == 1)
    finally:
        os.unlink(path)


# ── 7. opencode-style agent CLI (src/cos/cli.py) ────────────────────────────
def test_agent_cli():
    import json as _json
    import subprocess
    import tempfile

    print("\nSuite: agent CLI (opencode-style)")
    cli = os.path.abspath(os.path.join(
        os.path.dirname(__file__), '..', 'src', 'cos', 'cli.py'))
    code = ('import json\n\n\ndef load(path):\n    with open(path) as f:\n'
            '        return json.load(f)\n\n\ndef total(items):\n    ...\n')

    # 1. fill-in task, applied with --yes
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as fh:
        fh.write(code)
        path = fh.name
    try:
        proc = subprocess.run(
            [sys.executable, cli, 'complete the function', '--file', path, '--yes'],
            capture_output=True, text=True, timeout=60)
        check("agent fill exit 0", proc.returncode == 0)
        check("agent fill applied", 'sum(items)' in open(path).read())
        check("agent fill showed diff", '--- before' in proc.stdout)
    finally:
        os.unlink(path)

    # 2. convert task on the open buffer, applied
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as fh:
        fh.write('def double(x):\n    return x * 2\n')
        path = fh.name
    try:
        proc = subprocess.run(
            [sys.executable, cli, 'convert this code to javascript',
             '--file', path, '--yes'],
            capture_output=True, text=True, timeout=60)
        check("agent convert exit 0", proc.returncode == 0)
        content = open(path).read()
        check("agent convert applied", 'function double' in content
              and 'def double' not in content)
    finally:
        os.unlink(path)

    # 3. generate task -> appended to the open file
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as fh:
        fh.write('\n')
        path = fh.name
    try:
        proc = subprocess.run(
            [sys.executable, cli, 'write a function that flattens a nested list',
             '--file', path, '--yes'],
            capture_output=True, text=True, timeout=60)
        content = open(path).read()
        check("agent generate appended", 'def flatten' in content)
    finally:
        os.unlink(path)

    # 4. chat fallback when no file/code task
    proc = subprocess.run(
        [sys.executable, cli, 'what is a binary search'],
        capture_output=True, text=True, timeout=60)
    check("agent chat fallback", proc.returncode == 0
          and len(proc.stdout) > 60)

    # 5. no file open + generated artifact -> new-file creation
    workdir = tempfile.mkdtemp()
    try:
        proc = subprocess.run(
            [sys.executable, cli, 'create a simple website for a taco shop',
             '--yes', '--cwd', workdir],
            capture_output=True, text=True, timeout=60)
        check("agent new-file exit 0", proc.returncode == 0)
        html = os.path.join(workdir, 'taco-shop.html')
        check("agent new-file created", os.path.isfile(html)
              and '<title>Taco Shop</title>' in open(html).read())
        check("agent new-file diff shown",
              'new file' in proc.stdout or 'dev/null' in proc.stdout)
        # overwrite protection: existing file is left untouched
        before = open(html).read()
        proc = subprocess.run(
            [sys.executable, cli, 'create a simple website for a taco shop',
             '--yes', '--cwd', workdir],
            capture_output=True, text=True, timeout=60)
        check("agent new-file no overwrite", open(html).read() == before
              and 'already exists' in proc.stdout)
        # knowledge questions with example blocks never become files
        subprocess.run(
            [sys.executable, cli, 'explain what a hashmap is', '--cwd', workdir],
            capture_output=True, text=True, timeout=60)
        check("agent KB answer no file",
              sorted(os.listdir(workdir)) == ['taco-shop.html'])
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == '__main__':
    test_analyze()
    test_complete()
    test_fill_in()
    test_detect()
    test_engine()
    test_cli()
    test_agent_cli()
    print(f"\nResults: {_p}/{_p + _f} passed")
    sys.exit(1 if _f else 0)
