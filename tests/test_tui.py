#!/usr/bin/env python3
"""TUI + launcher tests: the full-screen agent UI (cos) and bin/cos.

Tests the dependency-free TUI's pure pieces (history buffer, input editor,
file picker, wrapping, diff coloring), the shared command dispatch, a
pty-based end-to-end fill-and-apply through the TUI, and the ``bin/cos``
launcher running from an arbitrary working directory.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CLI = os.path.join(ROOT, 'src', 'cos', 'cli.py')
LAUNCHER = os.path.join(ROOT, 'bin', 'cos')

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


def test_wrap():
    print('\nSuite: line wrapping')
    from cos.tui import wrap
    check('short line passes through', wrap('hello', 80) == ['hello'])
    check('long line wraps at width', len(wrap('x' * 100, 40)[0]) <= 40)
    check('word boundary preferred', wrap('abc def ghi', 7)[0].endswith('abc'))
    check('multiline splits', wrap('a\nb', 80) == ['a', 'b'])


def test_colorize():
    print('\nSuite: diff coloring')
    from cos.tui import colorize
    check('added line green', '\x1b[32m' in colorize('+ return 1'))
    check('removed line red', '\x1b[31m' in colorize('- old'))
    check('hunk header cyan', '\x1b[36m' in colorize('@@ -1,2 +1,2 @@'))
    check('file header bold', '\x1b[1m' in colorize('--- before'))
    check('notes dim', '\x1b[2m' in colorize('notes:'))
    check('plain line untouched', colorize('just text') == 'just text')


def test_history():
    print('\nSuite: history viewport')
    from cos.tui import History
    h = History()
    h.append('a\nb\nc')
    check('follows tail by default', h.view(2, 80) == ['b', 'c'])
    h.scroll(1, 2)                     # one visual row up
    check('scrolled view shows older', h.view(2, 80) == ['a', 'b'])
    h.page(1, 2)                       # PageUp -> even older (clamped)
    check('page clamp at top', h.view(2, 80) == ['a', 'b'])
    h.to_tail(2)
    check('back to tail', h.view(2, 80) == ['b', 'c'])


def test_editor():
    print('\nSuite: input line editor')
    from cos.tui import Editor
    e = Editor('cos> ')
    for ch in 'abc':
        e.insert(ch)
    e.move(-1)
    e.insert('X')
    check('insert at cursor', e.text() == 'abXc')
    e.home(); e.backspace()
    check('backspace at home noop', e.text() == 'abXc')
    e.end(); e.backspace()
    check('backspace deletes before cursor', e.text() == 'abX')
    e.insert(' word here')
    e.move(-5)
    e.kill_word()
    check('kill word removes word before cursor', e.text() == 'abX here')
    e.kill_to_start()
    check('kill to start', e.text() == ' here')
    e.reset()
    check('reset clears', e.text() == '')
    e.chars = list('first'); e.cursor = 5
    e.submit()
    e.chars = list('second'); e.cursor = 6
    e.submit()
    e.reset()
    e.history_nav(-1)
    check('history up recalls last', e.text() == 'second')
    e.history_nav(-1)
    check('history up again', e.text() == 'first')
    e.history_nav(1)
    check('history down', e.text() == 'second')


def test_picker():
    print('\nSuite: file picker')
    from cos.tui import Picker
    p = Picker(['a.py', 'b.py', 'c.py'])
    check('starts at first', p.selected() == 'a.py')
    p.move(1); p.move(1)
    check('moves down', p.selected() == 'c.py')
    p.move(1)
    check('clamps at bottom', p.selected() == 'c.py')
    check('renders selection marker', '> ' in p.rows(3, 80)[1])
    p2 = Picker([])
    check('empty picker message', '(no files)' in p2.rows(3, 80)[0])


def test_handle_command():
    print('\nSuite: shared command dispatch')
    from cos.cli import Session, handle_command
    s = Session('/tmp')
    out, quit_ = handle_command(s, '/help')
    check('help returns text', '/open <file>' in out and not quit_)
    check('quit flag', handle_command(s, '/quit')[1])
    out, _ = handle_command(s, '/context')
    check('context without file warns', 'no file open' in out)
    out, _ = handle_command(s, '/files')
    check('files lists entries', isinstance(out, str) and len(out) > 0)
    out, _ = handle_command(s, '/apply')
    check('apply without pending', 'nothing pending' in out)
    out, _ = handle_command(s, '')
    check('empty task noop', out == '')


def test_tui_pty_flow():
    print('\nSuite: TUI end-to-end (pty)')
    import pty
    import select
    import tempfile
    import time

    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as fh:
        fh.write('def total(items):\n    ...\n')
        path = fh.name
    try:
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir('/tmp')
            os.execv(sys.executable, [sys.executable, CLI, '--tui',
                                     '--file', path])
        out = b''
        died = False

        def drain(sec):
            nonlocal out
            end = time.time() + sec
            while time.time() < end:
                r, _, _ = select.select([fd], [], [], 0.05)
                if r:
                    try:
                        data = os.read(fd, 4096)
                    except OSError:
                        return
                    if not data:
                        return
                    out += data
                time.sleep(0.01)

        def send(b):
            os.write(fd, b)
            time.sleep(0.1)
            drain(0.3)

        drain(1.0)
        send(b'complete the function\r')
        drain(0.5)
        send(b'y\r')
        send(b'/quit\r')
        drain(0.5)
        os.close(fd)
        os.waitpid(pid, 0)
        txt = out.decode('utf-8', errors='replace')
        check('TUI header rendered', 'cos ·' in txt)
        check('task submitted', 'complete the function' in txt)
        check('diff shown', 'sum(items)' in txt)
        check('apply confirm shown', 'apply this edit' in txt)
        check('applied', 'applied edit' in txt)
        check('no traceback', 'Traceback' not in txt)
        check('file edited', 'return sum(items)' in open(path).read())
    finally:
        os.unlink(path)


def test_launcher_any_cwd():
    print('\nSuite: bin/cos launcher (any working directory)')
    proc = subprocess.run([LAUNCHER, '--help'], capture_output=True,
                          text=True, timeout=60)
    check('launcher --help exit 0', proc.returncode == 0
          and 'deterministic coding agent' in proc.stdout)
    proc = subprocess.run([LAUNCHER, 'what is a binary search'],
                          capture_output=True, text=True, timeout=60,
                          cwd='/tmp')
    check('launcher chats from /tmp', proc.returncode == 0
          and len(proc.stdout) > 60 and 'Traceback' not in proc.stdout)
    # non-tty interactive: falls back to the plain REPL, /quit exits
    proc = subprocess.run([LAUNCHER], input='/quit\n', capture_output=True,
                          text=True, timeout=60, cwd='/tmp')
    check('non-tty REPL fallback', proc.returncode == 0)


def test_tui_new_file_flow():
    print('\nSuite: TUI new-file creation (pty)')
    import pty
    import select
    import shutil
    import tempfile
    import time

    workdir = tempfile.mkdtemp()
    try:
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(workdir)
            os.execv(sys.executable, [sys.executable, CLI, '--tui'])
        out = b''

        def drain(sec):
            nonlocal out
            end = time.time() + sec
            while time.time() < end:
                r, _, _ = select.select([fd], [], [], 0.05)
                if r:
                    try:
                        data = os.read(fd, 4096)
                    except OSError:
                        return
                    if not data:
                        return
                    out += data
                time.sleep(0.01)

        def send(b):
            os.write(fd, b)
            time.sleep(0.1)
            drain(0.3)

        drain(1.0)
        send(b'create a website for a taco shop\r')
        drain(0.5)
        send(b'y\r')
        send(b'/quit\r')
        drain(0.5)
        os.close(fd)
        os.waitpid(pid, 0)
        txt = out.decode('utf-8', errors='replace')
        check('TUI create prompt names the file',
              'create taco-shop.html?' in txt)
        check('TUI created the file',
              os.path.isfile(os.path.join(workdir, 'taco-shop.html')))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_tui_fallback():
    print('\nSuite: TUI availability')
    from cos import tui
    check('available() false without a tty', not tui.available())


def main():
    test_wrap()
    test_colorize()
    test_history()
    test_editor()
    test_picker()
    test_handle_command()
    test_tui_pty_flow()
    test_tui_new_file_flow()
    test_launcher_any_cwd()
    test_tui_fallback()
    print(f'\nResults: {PASS}/{PASS + FAIL} passed')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
