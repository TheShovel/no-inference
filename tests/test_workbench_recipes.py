#!/usr/bin/env python3
"""Workbench recipes: end-to-end fill-in quality on realistic scripts.

These tests read the fixture scripts under examples/workbench/ (fresh from
disk), fill every marker via complete_buffer exactly like the agent CLI
would, and assert the bodies are the *correct implementations* — not
scaffolding. They lock in the buffer-aware recipes: module-level state,
instruction/docstring-driven bodies, name-verb recipes, TS/JS export +
generics parsing, and indentation inference.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cos.code_editor import _apply_insertion, _marker_lines, complete_buffer, detect_indent

HERE = os.path.dirname(os.path.abspath(__file__))
WB = os.path.join(os.path.dirname(HERE), 'examples', 'workbench')

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


def fill_all(rel: str):
    """Fill every marker in the fixture; returns the fully edited code."""
    with open(os.path.join(WB, rel), encoding='utf-8') as fh:
        code = fh.read()
    for _ in range(20):
        r = complete_buffer(code, instruction='', filename=rel)
        if not r['changed']:
            break
        code = _apply_insertion(code, r['text'], r['replace_line'])
    return code


def test_todo_app():
    print('\nSuite: workbench todo_app.py (module-state recipes, Python)')
    out = fill_all('todo_app.py')
    check('add_task appends to TODO', 'TODO.append(text)' in out)
    check('list_tasks iterates TODO', 'for item in TODO:' in out
          and 'print(item)' in out)
    check('mark_done moves TODO->DONE',
          'task = TODO.pop(index)' in out and 'DONE.append(task)' in out)
    check('count_remaining counts TODO', 'return len(TODO)' in out)
    check('clear_finished clears DONE', 'DONE.clear()' in out)
    check('no scaffolding left', 'TODO: implement' not in out)
    check('no markers left', _marker_lines(out) == [])


def test_cart_js():
    print('\nSuite: workbench cart.js (module-state recipes, JavaScript)')
    out = fill_all('cart.js')
    check('addItem pushes object', 'cart.push({ name, price, qty });' in out)
    check('total reduces item.price',
          'cart.reduce((acc, item) => acc + item.price, 0);' in out)
    check('applyDiscount reuses total()',
          'return total() * (1 - percent / 100);' in out)
    check('itemCount counts cart', 'return cart.length;' in out)
    check('no scaffolding left', 'TODO: implement' not in out)


def test_utils_ts():
    print('\nSuite: workbench utils.ts (TS export + generics + groupBy)')
    out = fill_all('utils.ts')
    check('unique dedups via Set', 'return [...new Set(items)];' in out)
    check('chunk slices by size',
          'items.slice(i, i + size)' in out and 'throw new Error' in out)
    check('groupBy buckets by key fn',
          'const g = key(item);' in out and '(out[g] = out[g] || []).push(item);' in out)
    check('no markers left', _marker_lines(out) == [])


def test_data_processor():
    print('\nSuite: workbench data_processor.py (docstring + instruction recipes)')
    out = fill_all('data_processor.py')
    check('read_csv_rows uses DictReader',
          'return list(csv.DictReader(f))' in out)
    check('average_by comprehension',
          'sum(r[key] for r in rows) / len(rows)' in out)
    check('totals_by grouped sum',
          'out[r[group_key]] = out.get(r[group_key], 0) + r[value_key]' in out)
    check('top_n sorted desc',
          'sorted(rows, key=lambda r: r[key], reverse=True)[:n]' in out)
    check('no scaffolding left', 'TODO: implement' not in out)


def test_indent_inference():
    print('\nSuite: indentation inference (deep nesting must not inflate the unit)')
    deep = ('def main():\n    while True:\n        try:\n            cmd = '
            "input('> ')\n        except Exception:\n            break\n")
    check('4-space unit with 8/12-deep blocks', detect_indent(deep) == ('spaces', 4))
    tabbed = 'def f():\n\tx = 1\n\tif x:\n\t\ty = 2\n'
    check('tabs detected', detect_indent(tabbed) == ('tabs', 1))
    two = 'def f():\n  a = 1\n  if a:\n    b = 2\n'
    check('2-space unit', detect_indent(two) == ('spaces', 2))
    none = 'x = 1\ny = 2\n'
    check('no indentation defaults to 4', detect_indent(none) == ('spaces', 4))


def test_instruction_variants():
    print('\nSuite: instruction-driven recipes (direct API)')
    code = ('items = []\n\ndef add_item(name):\n    ...\n')
    r = complete_buffer(code, instruction='', filename='x.py')
    check('single-container add -> append', r['changed']
          and 'items.append(name)' in r['text'])

    code = ('def find_avg(rows, key):\n'
            '    # TODO: average of rows[*][key]\n'
            '    ...\n')
    r = complete_buffer(code, instruction='', filename='x.py')
    check('average-of recipe', r['changed']
          and 'sum(r[key] for r in rows) / len(rows)' in r['text'])

    code = ('def apply_discount(percent):\n'
            '    // TODO: reduce the total by the given percent\n'
            '    ...\n')
    code = code.replace('//', '#')
    r = complete_buffer(code, instruction='', filename='x.py')
    check('percent discount falls back to a note', not r['changed']
          or 'total' in r['text'] or r['notes'])

    code = 'def total():  # noqa\n    """Return the total number of entries."""\n    ...\n'
    r = complete_buffer(code, instruction='', filename='x.py')
    check('docstring not required for total()', r['changed'])


def test_generic_instruction_does_not_override_spec():
    print('\nSuite: generic instruction vs embedded spec')
    code = ('def read_rows(path):\n'
            '    """Read a CSV file into a list of dicts keyed by header row."""\n'
            '    ...\n')
    for generic in ('complete the function', 'fill this in',
                    'please finish the body'):
        r = complete_buffer(code, instruction=generic, filename='x.py')
        check(f'generic {generic!r} -> docstring spec wins',
              r['changed'] and 'csv.DictReader(f)' in r['text'])
    r = complete_buffer(code, instruction='read it as plain text lines',
                        filename='x.py')
    check('specific instruction still wins over docstring',
          r['changed'] and 'DictReader' not in r['text'])
    from cos.code_editor import _is_generic_instruction
    check('generic detector: complete the function',
          _is_generic_instruction('complete the function'))
    check('generic detector: implement a binary search',
          not _is_generic_instruction('implement a binary search'))
    check('generic detector: sum the two numbers',
          not _is_generic_instruction('sum the two numbers'))


def test_ts_signature_forms():
    print('\nSuite: TypeScript signature forms')
    from cos.code_editor import _parse_signature
    s = _parse_signature(
        'export function groupBy<T>(items: T[], key: (item: T) => string): '
        'Record<string, T[]> {', 'typescript')
    check('function-typed param parses', s is not None
          and s['name'] == 'groupBy' and s['params'][0][0] == 'items')
    s = _parse_signature(
        'export const chunk = <T,>(items: T[], size: number): T[][] => {',
        'typescript')
    check('generic arrow parses', s is not None and s['name'] == 'chunk'
          and len(s['params']) == 2)
    s = _parse_signature(
        'function addItem(name, price, qty) {', 'javascript')
    check('plain JS function parses', s is not None
          and len(s['params']) == 3)


def main():
    test_todo_app()
    test_cart_js()
    test_utils_ts()
    test_data_processor()
    test_indent_inference()
    test_instruction_variants()
    test_generic_instruction_does_not_override_spec()
    test_ts_signature_forms()
    print(f'\nResults: {PASS}/{PASS + FAIL} passed')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
