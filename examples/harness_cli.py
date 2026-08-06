#!/usr/bin/env python3
"""Reference editor harness for COS fill-in.

A tiny, scriptable stand-in for an editor plugin: it reads a buffer (a file
or stdin), finds the fill-in marker (or uses --cursor), asks
cos.code_editor.complete_buffer to fill it, and either prints the insertion,
prints machine-readable JSON (for real plugins), or --apply writes the edit
back to the file.

Usage::

    # fill the first '...' marker in a file, show the insertion
    python3 examples/harness_cli.py tool.py

    # fill at a specific line (editor-style 1-based), with an instruction
    python3 examples/harness_cli.py tool.py --cursor 7 \\
        --instruction "return the sum of the two numbers"

    # machine-readable output for a plugin
    python3 examples/harness_cli.py tool.py --json

    # feed the buffer on stdin (no temp file needed from an editor)
    cat tool.py | python3 examples/harness_cli.py - --filename tool.py --json

    # apply the edit in place (demo of an editor applying the insertion)
    python3 examples/harness_cli.py tool.py --apply

Exit codes: 0 = filled, 1 = nothing to fill, 2 = usage error.

See docs/editor-harness.md for the full API and the agent CLI example.
"""
import argparse
import json
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from cos.code_editor import analyze_buffer, complete_buffer  # noqa: E402


def _read_source(args: argparse.Namespace) -> str:
    if args.file == '-':
        return sys.stdin.read()
    with open(args.file, 'r', encoding='utf-8') as fh:
        return fh.read()


def main() -> int:
    parser = argparse.ArgumentParser(
        prog='harness_cli.py',
        description='Reference COS fill-in harness (editor integration demo).')
    parser.add_argument('file', nargs='?', default='-',
                        help='source file to fill in, or "-" for stdin')
    parser.add_argument('--cursor', type=int, default=None, metavar='N',
                        help='1-based line of the fill-in point '
                             '(default: first "..." / "pass" marker)')
    parser.add_argument('--instruction', default='', metavar='TEXT',
                        help='what the code should do (also honored from a '
                             '"# TODO:" comment on/above the marker)')
    parser.add_argument('--filename', default=None, metavar='NAME',
                        help='filename to use for language detection '
                             '(with stdin; defaults to the file argument)')
    parser.add_argument('--apply', action='store_true',
                        help='write the edited buffer back to the file')
    parser.add_argument('--json', action='store_true',
                        help='print machine-readable JSON instead of prose')
    parser.add_argument('--context', action='store_true',
                        help='also print the buffer analysis')
    args = parser.parse_args()

    try:
        code = _read_source(args)
    except OSError as exc:
        print(f'harness: cannot read {args.file!r}: {exc}', file=sys.stderr)
        return 2

    filename = args.filename or (None if args.file == '-' else args.file)
    cursor = None if args.cursor is None else args.cursor - 1  # 1-based -> 0-based

    result = complete_buffer(code, instruction=args.instruction,
                             cursor_pos=cursor, filename=filename or '')
    ctx = analyze_buffer(code, filename or '')

    if args.json:
        payload = {
            'ok': result['changed'],
            'language': result['lang'],
            'text': result['text'],
            'notes': result['notes'],
            'replace_line': result['replace_line'],
            'context': result['context'] if args.context else None,
        }
        if result['changed']:
            payload['edited'] = _apply(code, result)
        print(json.dumps(payload, indent=2))
        return 0 if result['changed'] else 1

    if args.context:
        print('buffer analysis:')
        print(json.dumps(ctx, indent=2))
        print()

    if not result['changed']:
        notes = result['notes']
        print('nothing filled in.' + (f' {" ".join(notes)}' if notes else ''))
        return 1

    print(f'language: {result["lang"]}')
    if result['notes']:
        print('notes:')
        for note in result['notes']:
            print(f'  - {note}')
    print()
    print(f'insertion (replaces line {result["replace_line"] + 1}):')
    print(result['text'])

    if args.apply:
        if args.file == '-':
            print('\n--apply is not supported with stdin (nothing to write to).',
                  file=sys.stderr)
            return 2
        edited = _apply(code, result)
        with open(args.file, 'w', encoding='utf-8') as fh:
            fh.write(edited)
        print(f'\nwrote edited buffer back to {args.file}')
    return 0


def _apply(code: str, result: dict) -> str:
    lines = code.split('\n')
    idx = result['replace_line']
    if idx is not None and 0 <= idx < len(lines):
        lines[idx] = result['text']
    return '\n'.join(lines)


if __name__ == '__main__':
    sys.exit(main())
