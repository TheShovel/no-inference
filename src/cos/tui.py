"""cos TUI — dependency-free terminal UI for the deterministic agent.

A small full-screen interface (raw terminal + ANSI) so ``cos`` feels like a
coding-agent TUI rather than a bare prompt loop:

* scrollable task log (PageUp/PageDown, colored diffs and notes);
* an input line with editing keys and command history (Up/Down);
* a file picker (Tab) to switch the buffer the agent reads;
* an inline apply/skip confirm after a task stages an edit;
* auto file-suggestion when you type a fill task with no file open.

No external dependencies and no network — the same deterministic engine
underneath. If the terminal isn't interactive (not a tty, or no termios),
:func:`available` returns False and the caller falls back to the plain REPL.

Key map::

    Enter           submit task / confirm
    Tab             file picker (or complete ``/open <pref>``)
    Esc             close picker / cancel
    Up/Down         command history (on the input line)
    Left/Right      move the cursor
    Ctrl-W          delete word  ·  Ctrl-U  delete to start of line
    Ctrl-C          clear input (quit when empty)
    Ctrl-D          quit
    PageUp/PageDown scroll the log
"""
import os
import re
import select
import shutil
import sys

try:
    import termios
    import tty
except Exception:  # pragma: no cover - non-POSIX platforms
    termios = None
    tty = None

# ── ANSI helpers ──────────────────────────────────────────────────────────────

_BOLD = '\x1b[1m'
_DIM = '\x1b[2m'
_RED = '\x1b[31m'
_GREEN = '\x1b[32m'
_YELLOW = '\x1b[33m'
_CYAN = '\x1b[36m'
_RESET = '\x1b[0m'

_DIFF_HEAD = re.compile(r'^(---|\+\+\+) ')
_DIFF_AT = re.compile(r'^@@')
_DIFF_ADD = re.compile(r'^\+')
_DIFF_DEL = re.compile(r'^-')
_NOTE_LINE = re.compile(r'^(notes:|  - )')


def colorize(line: str) -> str:
    """ANSI-color a log line by what it is (diff/note/status)."""
    if _DIFF_HEAD.match(line):
        return _BOLD + line + _RESET
    if _DIFF_AT.match(line):
        return _CYAN + line + _RESET
    if _DIFF_ADD.match(line) and not line.startswith('+++'):
        return _GREEN + line + _RESET
    if _DIFF_DEL.match(line) and not line.startswith('---'):
        return _RED + line + _RESET
    if _NOTE_LINE.match(line):
        return _DIM + line + _RESET
    if line.startswith(('applied ', 'filled ')):
        return _GREEN + line + _RESET
    if line.startswith(('no such file', 'nothing ')):
        return _RED + line + _RESET
    return line


def wrap(text: str, cols: int) -> list[str]:
    """Wrap text to `cols` for rendering (words kept whole where possible)."""
    if cols <= 1:
        return [text]
    lines: list[str] = []
    for raw in text.split('\n'):
        while len(raw) > cols:
            cut = raw.rfind(' ', 0, cols)
            if cut < 1:
                cut = cols
            lines.append(raw[:cut])
            raw = raw[cut:].lstrip()
        lines.append(raw)
    return lines


# ── History buffer (scrollable content) ─────────────────────────────────────

class History:
    """Plain-text log with a viewport. Tracks whether we follow the tail."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.offset = 0
        self.follow = True

    def append(self, text: str) -> None:
        for ln in text.split('\n'):
            self.lines.append(ln)
        if self.follow:
            self.offset = 0

    def scroll(self, delta: int, view_h: int) -> None:
        self.follow = False
        max_off = max(0, len(self.lines) - view_h)
        self.offset = max(0, min(self.offset + delta, max_off))

    def page(self, delta: int, view_h: int) -> None:
        self.scroll(delta * max(1, view_h - 2), view_h)

    def to_tail(self, view_h: int) -> None:
        self.follow = True
        self.offset = 0

    def view(self, view_h: int, cols: int) -> list[str]:
        """Visual rows for the viewport (wrapping applied)."""
        if self.follow:
            self.offset = 0
        visual: list[str] = []
        for ln in self.lines:
            visual.extend(wrap(ln, cols))
        start = max(0, len(visual) - view_h - self.offset)
        end = start + view_h
        return visual[start:end]


# ── Input line editor ────────────────────────────────────────────────────────

class Editor:
    """Single-line input buffer with cursor + command history."""

    def __init__(self, prompt: str) -> None:
        self.prompt = prompt
        self.chars: list[str] = []
        self.cursor = 0
        self.history: list[str] = []
        self.hist_idx = -1
        self._saved = ''

    def text(self) -> str:
        return ''.join(self.chars)

    def insert(self, text: str) -> None:
        for ch in text:
            self.chars.insert(self.cursor, ch)
            self.cursor += 1

    def backspace(self) -> None:
        if self.cursor > 0:
            del self.chars[self.cursor - 1]
            self.cursor -= 1

    def delete(self) -> None:
        if self.cursor < len(self.chars):
            del self.chars[self.cursor]

    def move(self, delta: int) -> None:
        self.cursor = max(0, min(self.cursor + delta, len(self.chars)))

    def home(self) -> None:
        self.cursor = 0

    def end(self) -> None:
        self.cursor = len(self.chars)

    def kill_to_start(self) -> None:
        del self.chars[:self.cursor]
        self.cursor = 0

    def kill_word(self) -> None:
        i = self.cursor
        while i > 0 and self.chars[i - 1] == ' ':
            i -= 1
        while i > 0 and self.chars[i - 1] != ' ':
            i -= 1
        if i > 0 and self.chars[i - 1] == ' ':
            i -= 1          # also drop the space before the word
        del self.chars[i:self.cursor]
        self.cursor = i

    def reset(self, prompt: str | None = None) -> None:
        if prompt is not None:
            self.prompt = prompt
        self.chars = []
        self.cursor = 0
        self.hist_idx = -1
        self._saved = ''

    def submit(self) -> str:
        text = self.text()
        if text and (not self.history or self.history[-1] != text):
            self.history.append(text)
        self.reset()
        return text

    def history_nav(self, delta: int) -> None:
        """delta=-1 moves back (older), +1 moves forward (newer)."""
        if not self.history:
            return
        n = len(self.history)
        if self.hist_idx == -1:
            self._saved = self.text()
            target = 0 if delta < 0 else -1   # first Up -> most recent entry
        else:
            target = self.hist_idx - delta
        if target < -1 or target >= n:
            return
        self.hist_idx = target
        if target == -1:
            self.chars = list(self._saved)
        else:
            self.chars = list(self.history[n - 1 - target])
        self.cursor = len(self.chars)


# ── File picker ──────────────────────────────────────────────────────────────

class Picker:
    """Modal file list: Up/Down select, Enter open, Esc cancel."""

    def __init__(self, items: list[str]) -> None:
        self.items = items
        self.index = 0

    def move(self, delta: int) -> None:
        self.index = max(0, min(self.index + delta, len(self.items) - 1))

    def selected(self) -> str | None:
        if not self.items:
            return None
        return self.items[self.index]

    def rows(self, height: int, cols: int) -> list[str]:
        if not self.items:
            return ['(no files)']
        out: list[str] = []
        for i in range(max(0, self.index - height // 2),
                       min(len(self.items), self.index + height // 2 + 1)):
            name = self.items[i][:cols - 4]
            if i == self.index:
                out.append('> ' + _BOLD + name + _RESET)
            else:
                out.append('  ' + name)
        return out


# ── The TUI itself ───────────────────────────────────────────────────────────

class TUI:
    def __init__(self, session) -> None:
        self.session = session
        self.history = History()
        self.editor = Editor('cos> ')
        self.picker: Picker | None = None
        self.mode: str = 'task'          # 'task' | 'apply'
        self.quit = False
        self.fd = sys.stdin.fileno()
        self._saved_term: list | None = None
        self._status = ''

    # ── lifecycle ────────────────────────────────────────────────────────
    def _enter(self) -> None:
        assert termios is not None and tty is not None  # gated by available()
        self._saved_term = termios.tcgetattr(self.fd)
        tty.setraw(self.fd)

    def _leave(self) -> None:
        assert termios is not None  # gated by available()
        if self._saved_term is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._saved_term)
            self._saved_term = None
        sys.stdout.write('\x1b[?25h' + _RESET + '\r\n')
        sys.stdout.flush()

    def _write(self, s: str) -> None:
        # raw mode swallows \n output processing — translate explicitly
        sys.stdout.write(s.replace('\n', '\r\n'))
        sys.stdout.flush()

    # ── input ────────────────────────────────────────────────────────────
    def _read_key(self) -> str:
        ch = os.read(self.fd, 1)
        if ch == b'\x1b':
            seq = ch
            while select.select([self.fd], [], [], 0.04)[0]:
                seq += os.read(self.fd, 1)
            return seq.decode('utf-8', errors='replace')
        return ch.decode('utf-8', errors='replace')

    def _handle(self, key: str) -> None:
        if self.picker is not None:
            self._picker_key(key)
            return
        if self.mode == 'apply':
            if key in ('y', 'Y'):
                self._apply_choice('y')
            elif key in ('n', 'N', '\x1b'):
                self._apply_choice('n')
            return
        if key in ('\r', '\n'):
            self._submit()
            return
        if key == '\x1b':
            self._cancel()
            return
        if key in ('\x03',):            # ctrl-c
            if self.editor.text():
                self.editor.reset()
            else:
                self.quit = True
            return
        if key == '\x04':               # ctrl-d
            self.quit = True
            return
        if key == '\x7f' or key == '\x08':
            self.editor.backspace()
            return
        if key == '\x15':               # ctrl-u
            self.editor.kill_to_start()
            return
        if key == '\x17':               # ctrl-w
            self.editor.kill_word()
            return
        if key == '\t':
            self._tab()
            return
        if key == '\x1b[A':
            self.editor.history_nav(-1)
            return
        if key == '\x1b[B':
            self.editor.history_nav(1)
            return
        if key == '\x1b[C':
            self.editor.move(1)
            return
        if key == '\x1b[D':
            self.editor.move(-1)
            return
        if key in ('\x1b[H', '\x1b[1~'):
            self.editor.home()
            return
        if key in ('\x1b[F', '\x1b[4~'):
            self.editor.end()
            return
        if key == '\x1b[3~':
            self.editor.delete()
            return
        if key == '\x1b[5~':            # PageUp -> older content
            self.history.page(1, self._content_h())
            return
        if key == '\x1b[6~':            # PageDown -> newer content
            self.history.page(-1, self._content_h())
            return
        if len(key) == 1 and (key.isprintable() or key == ' '):
            self.editor.insert(key)

    def _cancel(self) -> None:
        if self.mode == 'apply':
            self.mode = 'task'
            self.editor.reset('cos> ')
            self._status = 'edit kept pending — use /apply to apply later'
        else:
            self.editor.reset()

    def _submit(self) -> None:
        if self.mode == 'apply':
            self._apply_choice('n')
            return
        task = self.editor.submit()
        if not task:
            return
        self._log(_YELLOW + '› ' + task + _RESET)
        out, quit_ = self._run(task)
        if quit_:
            self.quit = True
            return
        if out:
            self._log(out)
        if self.session.pending:
            self.mode = 'apply'
            path = self.session.pending[0]
            if self.session.pending[1] == '':
                self.editor.reset(f'create {os.path.basename(path)}? [y/N] ')
            else:
                self.editor.reset('apply this edit? [y/N] ')

    def _apply_choice(self, choice: str) -> None:
        self.mode = 'task'
        if choice == 'y':
            self._log(_GREEN + self.session.apply() + _RESET)
        else:
            self._status = 'edit kept pending — use /apply to apply later'
        self.editor.reset('cos> ')

    def _run(self, task: str):
        from cos.cli import handle_command
        return handle_command(self.session, task)

    # ── commands ─────────────────────────────────────────────────────────
    def _tab(self) -> None:
        text = self.editor.text()
        if text.startswith('/open '):
            prefix = text[6:]
            matches = [f for f in self._files()
                       if f.startswith(prefix)]
            if len(matches) == 1:
                self.editor.chars = list('/open ' + matches[0] + ' ')
                self.editor.cursor = len(self.editor.chars)
            elif matches:
                self.picker = Picker(matches)
            else:
                self.picker = Picker(self._files())
        elif text == '':
            self.picker = Picker(self._files())
        else:
            self.editor.insert('    ')

    def _picker_key(self, key: str) -> None:
        p = self.picker
        if p is None:
            return
        if key == '\x1b':
            self.picker = None
            return
        if key in ('\r', '\n'):
            sel = p.selected()
            self.picker = None
            if sel:
                msg = self.session.open_file(sel)
                self._log(msg)
                self._status = f'buffer: {sel}'
            return
        if key == '\x1b[A':
            p.move(-1)
            return
        if key == '\x1b[B':
            p.move(1)
            return
        if key in ('\x1b[5~', '\x1b[6~'):
            p.move(-1 if key == '\x1b[5~' else 1)

    def _files(self) -> list[str]:
        exts = ('.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs', '.java',
                '.cpp', '.cs', '.sh', '.rb', '.php', '.md', '.json', '.yaml',
                '.yml', '.toml', '.txt', '.html', '.css', '.sql')
        return [n for n in sorted(os.listdir(self.session.workdir))
                if os.path.isfile(os.path.join(self.session.workdir, n))
                and n.endswith(exts)]

    # ── rendering ────────────────────────────────────────────────────────
    def _size(self) -> tuple[int, int]:
        try:
            cols, rows = shutil.get_terminal_size(fallback=(80, 24))
        except Exception:
            cols, rows = 80, 24
        return cols, max(rows, 8)

    def _content_h(self) -> int:
        return self._size()[1] - 3

    def _draw(self) -> None:
        cols, rows = self._size()
        header = (f"cos · {self.session.workdir}"
                  + (f" · {os.path.basename(self.session.filename)}"
                     if self.session.filename else ''))
        header = header[:cols - 1]
        out = ['\x1b[?25l']               # hide cursor while drawing
        out.append('\x1b[1;1H' + _BOLD + header + _RESET + '\x1b[K')
        content = self.history.view(self._content_h(), cols)
        for i, ln in enumerate(content):
            row = 2 + i
            out.append(f'\x1b[{row};1H' + colorize(ln)[:cols] + '\x1b[K')
        # clear the rest of the content area
        for i in range(len(content), self._content_h()):
            out.append(f'\x1b[{2 + i};1H\x1b[K')
        if self.picker is not None:
            pick_rows = self.picker.rows(rows - 4, cols)
            base = rows - 4 - len(pick_rows)
            for i, ln in enumerate(pick_rows):
                out.append(f'\x1b[{base + i};1H' + ln + '\x1b[K')
        status = self._status or ('PageUp/PgDn scroll · Tab files · '
                                  'Ctrl-D quit · /help')
        out.append(f'\x1b[{rows - 1};1H' + _DIM + status[:cols - 1] + _RESET
                   + '\x1b[K')
        prompt = self.editor.prompt
        out.append(f'\x1b[{rows};1H' + _YELLOW + prompt + _RESET
                   + self.editor.text() + '\x1b[K')
        cur = 1 + len(prompt) + self.editor.cursor
        out.append(f'\x1b[{rows};{cur}H\x1b[?25h')
        self._write(''.join(out))
        self._status = ''

    def _log(self, text: str) -> None:
        # strip ANSI before storing (colorize happens at draw time)
        plain = re.sub(r'\x1b\[[0-9;]*m', '', text)
        self.history.append(plain)

    # ── main loop ────────────────────────────────────────────────────────
    def run(self) -> int:
        try:
            self._enter()
            self._log('cos — deterministic coding agent. Type /help. '
                      'Tab to pick a file.')
            while not self.quit:
                self._draw()
                key = self._read_key()
                self._handle(key)
            return 0
        except (KeyboardInterrupt, EOFError):
            return 0
        finally:
            self._leave()


def available() -> bool:
    """True when a real terminal is present (TUI usable)."""
    if termios is None or tty is None:
        return False
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def run_tui(session, args) -> int:
    """Launch the TUI; returns the process exit code."""
    return TUI(session).run()
