#!/usr/bin/env python3
"""API server: the JSON API the gh-pages website talks to.

Starts the real stdlib server on an ephemeral port and exercises the
endpoints the website's chat.html and editor.html pages call: /health,
/api/query (plus the legacy /query alias), conversations, and the
/api/editor/* buffer-aware coding endpoints. Also checks the JSON index
and the CORS headers that make the cross-origin site work.
"""
import json
import os
import sys
import threading
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

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


def _start():
    from http.server import HTTPServer
    from api.server import COSAPIHandler
    srv = HTTPServer(('127.0.0.1', 0), COSAPIHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, f'http://127.0.0.1:{srv.server_port}'


def _get_json(base: str, path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(base + path, timeout=60) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


def _get_headers(base: str, path: str) -> tuple[int, dict]:
    req = urllib.request.Request(base + path, method='GET')
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, dict(r.headers)


def _post(base: str, path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


def test_index_and_cors(base):
    print('\nSuite: index + CORS')
    s, d = _get_json(base, '/')
    check('index serves 200', s == 200)
    check('index lists endpoints', isinstance(d, dict)
          and 'endpoints' in d and '/api/editor/fill' in ' '.join(d['endpoints']))
    check('index names the frontend', isinstance(d, dict) and 'frontend' in d)

    s, _ = _get_json(base, '/chat')
    check('chat page not served by API (lives on gh-pages)', s == 404)
    s, _ = _get_json(base, '/editor')
    check('editor page not served by API (lives on gh-pages)', s == 404)

    s, h = _get_headers(base, '/api/status')
    check('status serves 200', s == 200)
    check('CORS header present for the website', h.get('Access-Control-Allow-Origin') == '*')

    s, _ = _get_json(base, '/nope')
    check('unknown route 404s', s == 404)


def test_editor_fill(base):
    print('\nSuite: /api/editor/fill')
    code = 'def reverse_string(s: str) -> str:\n    ...\n'
    s, d = _post(base, '/api/editor/fill',
                 {'code': code, 'instruction': '', 'filename': 'tool.py'})
    check('fill returns 200', s == 200)
    check('fill ok', d.get('ok') is True)
    check('fill produced text', 's[::-1]' in d.get('text', ''))
    check('fill edited buffer preview', bool(d.get('edited'))
          and 's[::-1]' in d['edited'])
    check('fill replace_line is marker line', d.get('replace_line') == 1)
    check('fill context has language',
          bool(d.get('context', {}).get('language') == 'python'))

    s, d = _post(base, '/api/editor/fill',
                 {'code': 'x = 1\n', 'instruction': '', 'filename': 'x.py'})
    check('no-marker fill reports ok=False', d.get('ok') is False)

    s, d = _post(base, '/api/editor/fill',
                 {'code': '  ', 'instruction': '', 'filename': 'x.py'})
    check('empty buffer rejected', s == 400)


def test_editor_generate(base):
    print('\nSuite: /api/editor/generate')
    s, d = _post(base, '/api/editor/generate',
                 {'query': 'write a python function that flattens a nested list'})
    check('generate returns 200', s == 200)
    check('generate ok', d.get('ok') is True)
    check('generate has code', 'def flatten' in d.get('code', ''))
    check('generate has markdown', '```' in d.get('markdown', ''))
    check('generate lang python', d.get('lang') == 'python')

    s, d = _post(base, '/api/editor/generate', {'query': 'purple elephant'})
    check('unmapped task reports ok=False', d.get('ok') is False)

    s, _ = _post(base, '/api/editor/generate', {'query': ''})
    check('empty query rejected', s == 400)


def test_editor_transform(base):
    print('\nSuite: /api/editor/transform')
    code = 'def count_words(text):\n    return len(text.split())\n'
    s, d = _post(base, '/api/editor/transform',
                 {'query': 'convert this to javascript', 'code': code,
                  'filename': 'tool.py'})
    check('transform returns 200', s == 200)
    check('transform ok', d.get('ok') is True)
    check('transform op is convert_lang', d.get('op') == 'convert_lang')
    check('transform produced javascript',
          'function' in d.get('edited', '') or '=>' in d.get('edited', ''))

    code2 = ('import os\n\n'
             'def load(path):\n'
             '    with open(path) as f:\n'
             '        return f.read()\n')
    s, d = _post(base, '/api/editor/transform',
                 {'query': 'add error handling', 'code': code2,
                  'filename': 'io.py'})
    check('add_errors detected', d.get('ok') is True and d.get('op') == 'add_errors')
    check('add_errors wrapped in try', 'try:' in d.get('edited', ''))

    s, d = _post(base, '/api/editor/transform',
                 {'query': 'rename total to sum', 'code': 'total = 1 + 2\n',
                  'filename': 't.py'})
    check('rename detected', d.get('ok') is True and d.get('op') == 'rename')
    check('rename applied', 'sum = 1 + 2' in d.get('edited', ''))

    # code pasted into the query still edits the buffer
    s, d = _post(base, '/api/editor/transform',
                 {'query': 'add error handling: ' + code2, 'code': code2,
                  'filename': 'io.py'})
    check('pasted-code query handled', d.get('ok') is True
          and d.get('op') == 'add_errors')

    s, d = _post(base, '/api/editor/transform',
                 {'query': 'make it spicy', 'code': code, 'filename': 'tool.py'})
    check('unknown transform rejected', d.get('ok') is False)

    s, _ = _post(base, '/api/editor/transform',
                 {'query': 'convert this to javascript', 'code': '', 'filename': 'x.py'})
    check('empty buffer rejected', s == 400)


def test_editor_analyze(base):
    print('\nSuite: /api/editor/analyze')
    code = ('import json\n\n'
            'def load(path):\n'
            '    with open(path) as f:\n'
            '        return json.load(f)\n')
    s, d = _post(base, '/api/editor/analyze', {'code': code, 'filename': 'c.py'})
    check('analyze returns 200', s == 200)
    check('analyze ok', d.get('ok') is True)
    check('analyze language python', d.get('language') == 'python')
    check('analyze imports json', 'json' in d.get('imports', []))
    check('analyze found load def',
          ('function', 'load') in [tuple(x) for x in d.get('definitions', [])])
    check('analyze indent kind', d.get('indent', {}).get('kind') == 'spaces')
    check('analyze line count', d.get('line_count') == 6)


def test_api_unchanged(base):
    print('\nSuite: chat + conversations API still works')
    s, d = _get_json(base, '/api/status')
    check('status has kb_entries', s == 200 and 'kb_entries' in d)

    s, d = _post(base, '/api/query', {'query': 'what is 2+2?'})
    check('single query works', s == 200 and bool(d.get('response')))

    s, d = _post(base, '/query', {'query': 'what is 2+2?'})
    check('legacy /query alias works', s == 200 and bool(d.get('response')))

    s, d = _post(base, '/api/conversations', {})
    cid = d.get('id')
    check('conversation created', s == 201 and bool(cid))
    if cid:
        s, d = _post(base, f'/api/conversations/{cid}/query', {'query': 'hello'})
        check('conversation query works', s == 200 and bool(d.get('response')))
        s, d = _get_json(base, f'/api/conversations/{cid}')
        check('conversation history works', s == 200
              and len(d.get('turns', [])) == 1)
        s, _ = _get_json(base, '/api/conversations')
        check('conversation list works', s == 200)


def main():
    srv, base = _start()
    try:
        test_index_and_cors(base)
        test_editor_fill(base)
        test_editor_generate(base)
        test_editor_transform(base)
        test_editor_analyze(base)
        test_api_unchanged(base)
    finally:
        srv.shutdown()
        srv.server_close()
    print(f'\nResults: {PASS}/{PASS + FAIL} passed')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
