#!/usr/bin/env python3
"""Iterative refinement: make -> edit -> refine loops (multi-turn).

These tests drive the full engine through the workflow that matters for
day-to-day use: generate an artifact, then follow up with edits that must
apply to *that artifact* — never fall into knowledge-article garbage.

Covers: website iteration (form, color, sections, menu items, rename,
dark mode, removal), wrong-kind artifact guarding, language conversion,
code edits (error handling, docstrings, appended functions), and honest
fallbacks for uneditable requests.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cos.engine import process_query, reset_conversation  # noqa: E402

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


def last_fence(answer: str) -> str:
    fences = re.findall(r'```\w*\n(.*?)```', answer, re.DOTALL)
    return fences[-1] if fences else ''


def run(turns, expect_fence=True):
    """Run turns, return the final answer."""
    out = None
    for t in turns:
        out = process_query(t)
        if expect_fence:
            check(f'turn: {t[:45]}', '```' in out)
    return out or ''


def test_website_iteration():
    print('\nSuite: website make->edit->refine loop')
    reset_conversation()
    run(['create a website for a taco shop',
         'add a contact form to the website',
         'change the accent color to green'])
    final = last_fence(process_query('make it dark'))
    check('contact form added', '<form' in final)
    check('accent is green', '--accent: #2ecc71' in final)
    check('dark mode applied', 'background: #121212' in final)
    check('taco menu preserved', 'Carnitas' in final)

    reset_conversation()
    run(['create a website for a pizza place',
         'add a section about catering',
         'add margherita to the menu',
         'change the name to Bella Napoli',
         'remove the hours section'])
    final = last_fence(process_query('make it dark'))
    check('section added', 'id="catering"' in final)
    check('menu item added', 'margherita' in final.lower())
    check('site renamed', '<title>Bella Napoli</title>' in final)
    check('hours removed', '<h2>Hours</h2>' not in final)


def test_artifact_kind_guard():
    print('\nSuite: wrong-kind artifact guard')
    reset_conversation()
    run(['create a website for a taco shop',
         'write a function that computes fibonacci numbers'])
    out = process_query('change the accent color to blue')
    check('website edited, not fibonacci',
          '```html' in out and '--accent: #3498db' in out)


def test_language_conversion():
    print('\nSuite: follow-up language conversion')
    reset_conversation()
    run(['write a function that reverses a string'])
    out = process_query('now do the same in rust')
    check('converted to rust', '```rust' in out and 'fn reverse_string' in out)
    check('no knowledge junk', 'swimmer' not in out.lower())


def test_code_refinement():
    print('\nSuite: function refinement')
    reset_conversation()
    run(['write a function that flattens a nested list'])
    out = process_query('add error handling to the function')
    final = last_fence(out)
    check('try/except added', 'try:' in final and 'except Exception' in final)
    check('flatten preserved', 'def flatten' in final)

    reset_conversation()
    run(['write a function that computes the factorial of a number'])
    out = process_query('add error handling')
    final = last_fence(out)
    check('bare add error handling works', 'try:' in final
          and 'def factorial' in final)

    reset_conversation()
    run(['write a function that computes the factorial of a number',
         'add a docstring'])
    out = process_query('add a function that validates an email address')
    final = last_fence(out)
    check('docstring added', '"""' in final)
    check('email function appended', 'def is_valid_email' in final)
    check('factorial preserved', 'def factorial' in final)


def test_script_refinement():
    print('\nSuite: script refinement')
    reset_conversation()
    run(['write a python script to back up a directory'])
    out = process_query('add compression to the backup script')
    final = last_fence(out)
    check('compression variant added',
          'backup_compressed' in final and 'make_archive' in final)


def test_honest_fallback():
    print('\nSuite: honest fallback for uneditable requests')
    reset_conversation()
    run(['create a website for a taco shop'])
    out = process_query('add a swimming pool section')
    final = last_fence(out)
    check('noun-first section added', 'id="swimming-pool"' in final
          and 'Swimming Pool' in final)
    reset_conversation()
    run(['create a website for a taco shop'])
    out = process_query('add a swimming pool to the parking lot')
    check('no artifact ref -> real info, not hijacked', '```' not in out
          and len(out) > 40)
    check('no knowledge article hijack', 'Caesarean' not in out
          and 'ADHD' not in out)


def test_refine_first_turn_noop():
    print('\nSuite: refinement without a prior artifact')
    reset_conversation()
    out = process_query('add a contact form to the website')
    check('no artifact -> normal flow, not garbage', '```' not in out
          or 'contact form' in out.lower())
    check('still informative', len(out) > 40)


def main():
    test_website_iteration()
    test_artifact_kind_guard()
    test_language_conversion()
    test_code_refinement()
    test_script_refinement()
    test_honest_fallback()
    test_refine_first_turn_noop()
    print(f'\nResults: {PASS}/{PASS + FAIL} passed')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
