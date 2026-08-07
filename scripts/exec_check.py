#!/usr/bin/env python3
"""Execution check: run every self-contained Python template and report."""
import contextlib
import glob
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, 'src')

# Run in a scratch directory so templates that do file I/O (rename, delete,
# extract) can never touch the repository.
_HERE = os.path.dirname(os.path.abspath(__file__))
_TASKS_GLOB = os.path.join(_HERE, '..', 'data', 'knowledge', 'code_tasks', '*.json')
os.chdir(tempfile.mkdtemp(prefix='cos_exec_'))

SKIP_HINTS = ('input(', 'time.sleep', 'requests.', 'urllib', 'smtplib',
              'watch', 'monitor', 'mainloop', 'threading', 'tail_log',
              'tkinter', 'setinterval', 'sys.exit', 'sys.argv')

ran = ok = 0
errors = []
for f in sorted(glob.glob(_TASKS_GLOB)):
    if f.endswith('_web_types.json'):
        continue
    data = json.load(open(f))
    items = data.get('tasks', []) if isinstance(data, dict) else data
    for t in items:
        py = t.get('languages', {}).get('python')
        if not py or 'pytest is Python-only' in py:
            continue
        low = py.lower()
        if any(k in low for k in SKIP_HINTS):
            continue
        ran += 1
        try:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                exec(compile(py, '<tpl>', 'exec'), {'__name__': '__main__'})
            ok += 1
        except SystemExit:
            ok += 1  # template finished (exit is a graceful end)
        except Exception as e:  # noqa: BLE001
            errors.append((t['task'], type(e).__name__ + ': ' + str(e)[:90]))

print(f'runnable: {ok}/{ran} python templates executed without error')
for task, err in errors[:20]:
    print('  -', task, ':', err)
sys.exit(1 if errors else 0)
