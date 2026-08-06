#!/usr/bin/env python3
"""COS CLI — an opencode-style deterministic coding agent.

A terminal agent that works on the file you point it at: it reads the
buffer (language, imports, definitions, indent), understands the task
(fill in a body, transform the code, or generate something new), shows a
diff, and applies the edit — exactly like a small ``opencode``. The
difference from an LLM agent: every edit is produced by the deterministic
rules in ``cos.code_editor`` / ``cos.code_transformer`` / ``cos.code_gen``
(no sampling, no network).

Usage::

    # full-screen terminal UI (interactive session)
    cos
    python3 src/cos/cli.py

    # plain prompt loop instead of the TUI
    cos --repl

    # one-shot: fill the first marker in tool.py and show the diff
    cos "complete the function" --file tool.py
    python3 src/cos/cli.py "complete the function" --file tool.py

    # one-shot, apply without asking
    cos "complete the function" --file tool.py --yes

    # generate code for a task and append it to the open file
    cos "write a function that flattens a nested list" --file tool.py --yes

    # chat questions never become edits
    cos "what is a binary search"

REPL commands::

    /open <file>    open a file (the buffer the agent reads)
    /context        show the analyzed buffer (imports/defs/indent)
    /diff           show the pending edit as a diff
    /apply          apply the pending edit
    /undo           revert the last applied edit
    /files          list files in the working directory
    /help           this help
    /quit           exit

Anything else is a task for the agent. The agent routes it as:

    1. fill-in requests  -> complete_buffer   (reads the buffer context)
    2. code transforms   -> transform_code    ("convert to javascript", ...)
    3. code tasks        -> generate_code     (offered as a pending edit)
    4. everything else   -> process_query     (chat answer)

See docs/editor-harness.md for the underlying API.
"""
import argparse
import difflib
import os
import re
import sys

# Run from source (``python3 src/cos/cli.py``) without an install:
# make the package root (src/) importable. Harmless when cos is pip-installed.
_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from cos.code_editor import (_FILL_VERBS_RE, _apply_insertion, _marker_lines,
                             analyze_buffer, complete_buffer, detect_fill_request)
from cos.code_transformer import detect_code_transform, transform_code
from cos.engine import process_query


class Session:
    """Holds the open file, the pending edit, and an undo stack."""

    def __init__(self, workdir: str | None = None):
        self.workdir = workdir or os.getcwd()
        self.filename: str | None = None   # open buffer
        self.pending: tuple[str, str, str] | None = None  # (path, before, after)
        self.undo_stack: list[tuple[str, str]] = []       # (path, content)

    # ── file helpers ────────────────────────────────────────────────────
    def open_file(self, path: str) -> str:
        full = path if os.path.isabs(path) else os.path.join(self.workdir, path)
        if not os.path.isfile(full):
            return f"no such file: {path}"
        self.filename = full
        return f"opened {full}"

    def read(self) -> str:
        assert self.filename is not None, "no file open"
        with open(self.filename, 'r', encoding='utf-8') as fh:
            return fh.read()

    def write(self, path: str, content: str) -> None:
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(content)

    def suggest_file(self) -> str | None:
        """The most likely target: a source file in cwd with a fill-in marker."""
        exts = ('.py', '.js', '.ts', '.go', '.rs', '.java', '.cpp', '.cs')
        for name in sorted(os.listdir(self.workdir)):
            if not name.endswith(exts):
                continue
            full = os.path.join(self.workdir, name)
            try:
                with open(full, encoding='utf-8') as fh:
                    content = fh.read()
            except OSError:
                continue
            if _marker_lines(content):
                return full
        return None

    # ── pending-edit helpers ────────────────────────────────────────────
    def stage(self, after: str) -> None:
        assert self.filename is not None, "no file open"
        before = self.read()
        self.pending = (self.filename, before, after)

    def stage_file(self, path: str, content: str) -> None:
        """Stage a brand-new file (no open buffer needed)."""
        self.pending = (path, '', content)

    def apply(self) -> str:
        if self.pending is None:
            return "nothing pending — give the agent a task first"
        path, before, after = self.pending
        self.undo_stack.append((path, before))
        self.write(path, after)
        self.pending = None
        if before == '':
            return f"created {path}"
        return f"applied edit to {path}"

    def undo(self) -> str:
        if not self.undo_stack:
            return "nothing to undo"
        path, content = self.undo_stack.pop()
        if content == '':
            # the undone action created the file — remove it
            if os.path.isfile(path):
                os.remove(path)
            return f"deleted {path}"
        self.write(path, content)
        return f"reverted {path}"

    def diff(self) -> str:
        if self.pending is None:
            return "no pending edit"
        path, before, after = self.pending
        if before == '':
            # brand-new file: show every line as an addition
            delta = list(difflib.unified_diff(
                [], after.splitlines(),
                fromfile='dev/null',
                tofile=os.path.basename(path), lineterm=''))
            return '\n'.join(delta) if delta else '(empty file)'
        delta = list(difflib.unified_diff(
            before.splitlines(), after.splitlines(),
            fromfile='before', tofile='after', lineterm=''))
        return '\n'.join(delta) if delta else '(no textual change)'


# ── task routing ────────────────────────────────────────────────────────────

def run_task(session: Session, task: str, auto_apply: bool = False) -> str:
    """Handle one task string; returns text to print (no side-channel prints)."""
    # 0. no file open: try to find a sensible target, else chat
    if session.filename is None:
        suggestion = session.suggest_file()
        if suggestion:
            session.open_file(suggestion)
            note = f"(no file open — using {suggestion})\n"
        else:
            return _chat_or_save(session, task)
    else:
        note = ''

    code = session.read()

    # 1. fill-in requests: the task names a fill verb and the buffer has a
    #    marker. (detect_fill_request() alone expects the code inline in the
    #    query — here the code lives in the open file.)
    if detect_fill_request(task) or (_FILL_VERBS_RE.search(task)
                                     and _marker_lines(code)):
        result = complete_buffer(code, instruction=task)
        if result['changed']:
            after = _apply_insertion(code, result['text'],
                                     result['replace_line'] or 0)
            session.stage(after)
            out = [f"filled {os.path.basename(session.filename or '')}:"]
            out.append(session.diff())
            if result['notes']:
                out.append('notes:\n- ' + '\n- '.join(result['notes']))
            return note + '\n'.join(out)

    # 2. code transformations on the open buffer ("convert this to js", ...)
    try:
        ct = detect_code_transform(task + ':\n' + code)
    except Exception:
        ct = None
    if ct:
        op, params, _code, lang = ct
        edited, notes = transform_code(op, params, code, lang)
        if edited != code:
            session.stage(edited)
            out = [f"{op}: {os.path.basename(session.filename or '')}"]
            out.append(session.diff())
            if notes:
                out.append('notes:\n- ' + '\n- '.join(notes))
            return note + '\n'.join(out)

    # 3. code-generation task ("write a function that ...") -> pending append.
    #    Questions ("what is a binary search") must chat, not append code.
    if _is_question(task):
        return process_query(task)
    from cos.code_gen import generate_code
    gen = generate_code(task)
    if gen is None and session.filename:
        # the chat answer may still contain a useful code block — offer it
        gen = process_query(task)
    if gen and session.filename:
        fenced = extract_fenced(gen)
        if fenced:
            after = code + ('\n' if code and not code.endswith('\n') else '') + fenced + '\n'
            session.stage(after)
            return (note + "generated code for the task (pending append to "
                    f"{os.path.basename(session.filename or '')}):\n"
                    + session.diff())

    # 4. chat
    return _chat_or_save(session, task)


# ── new-file offering ("create a website" with no file open) ────────────────

_EXT_BY_LANG = {
    'python': 'py', 'javascript': 'js', 'typescript': 'ts', 'html': 'html',
    'bash': 'sh', 'go': 'go', 'rust': 'rs', 'java': 'java', 'c++': 'cpp',
    'c#': 'cs', 'sql': 'sql', 'css': 'css', 'json': 'json', 'ruby': 'rb',
    'php': 'php', 'swift': 'swift', 'kotlin': 'kt', 'c': 'c',
}

_DEF_NAME_RE = {
    'python': re.compile(r'^\s*(?:async\s+)?def\s+(\w+)'),
    'javascript': re.compile(r'^(?:export\s+)?(?:function\s+|const\s+\w+\s*=\s*\()'
                             r'[^=]*?(\w+)'),
    'typescript': re.compile(r'^(?:export\s+)?(?:function\s+|const\s+\w+\s*=\s*\()'
                             r'[^=]*?(\w+)'),
    'go': re.compile(r'^func\s+(\w+)'),
    'rust': re.compile(r'^(?:pub\s+)?fn\s+(\w+)'),
    'bash': re.compile(r'^(?:function\s+)?(\w+)\s*\(\)'),
    'html': re.compile(r'<title>([^<]+)</title>'),
}

_CODE_INTRO_RE = re.compile(r"^here's (?:a|an|the|your|the\s+updated)", re.IGNORECASE)


def _derive_filename(code: str, lang: str) -> str:
    """A sensible filename for a generated artifact."""
    ext = _EXT_BY_LANG.get(lang, 'txt')
    pat = _DEF_NAME_RE.get(lang)
    if pat:
        m = pat.search(code)
        if m:
            sep = '_' if lang in ('python', 'go', 'rust', 'c++', 'c#', 'java',
                                  'javascript', 'typescript', 'ruby', 'kotlin') else '-'
            name = re.sub(r'[^a-z0-9]+', sep, m.group(1).lower()).strip(sep)
            if name:
                return f'{name}.{ext}'
    slug = 'index' if lang == 'html' else 'output'
    return f'{slug}.{ext}'


def _extract_new_file(answer: str) -> "tuple[str, str] | None":
    """(filename, code) when the answer is a savable artifact.

    Two signals: an explicit ``Save it as `X``` hint (the website
    generator), or a dominant code fence at the head of the answer
    (``Here's a ...`` generation). Prose answers with small example
    blocks (knowledge lookups) never become files.
    """
    import re as _re
    m = _re.search(r'```(\w*)\n(.*?)```', answer, _re.DOTALL)
    if not m:
        return None
    lang, code = m.group(1), m.group(2).strip('\n')
    hint = _re.search(r'Save it as `([^`]+)`', answer)
    if hint:
        return hint.group(1), code
    if not _CODE_INTRO_RE.match(answer.strip()):
        return None
    if len(code) * 2 <= len(answer):
        return None
    return _derive_filename(code, lang), code


def _chat_or_save(session: Session, task: str) -> str:
    """Chat answer; when it's a generated artifact, offer a new file."""
    answer = process_query(task)
    newfile = _extract_new_file(answer)
    if not newfile:
        return answer
    fname, code = newfile
    full = os.path.join(session.workdir, fname)
    if os.path.exists(full):
        return (answer + "\n\n(I'd save this as " + fname +
                ", but that file already exists here — /open it and I'll "
                "edit it instead.)")
    session.stage_file(full, code)
    return (f"generated {fname} (new file, pending):\n"
            + session.diff()
            + "\n\nThe code above is the whole file — apply it to write it "
              "to disk, or n to keep it as a chat answer only.")


_QUESTION_RE = re.compile(
    r'^(what|how|why|when|where|who|which|is|are|can|could|does|do|'
    r'should|would|explain|describe|tell)\b', re.IGNORECASE)


def _is_question(task: str) -> bool:
    """True for a chat question (not an imperative code request)."""
    t = task.strip()
    return bool(_QUESTION_RE.match(t)) or t.endswith('?')


def extract_fenced(answer: str) -> str:
    """Pull the fenced code block out of a generate_code answer."""
    import re
    m = re.search(r'```\w*\n(.*?)```', answer, re.DOTALL)
    return m.group(1).rstrip('\n') if m else ''


# ── REPL ────────────────────────────────────────────────────────────────────

HELP = """commands:
  /open <file>    open a file (the buffer the agent reads)
  /context        show the analyzed buffer (imports/defs/indent)
  /diff           show the pending edit as a diff
  /apply          apply the pending edit
  /undo           revert the last applied edit
  /files          list files in the working directory
  /help           this help
  /quit           exit

anything else is a task for the agent, e.g.:
  complete the function
  convert this code to javascript
  write a function that flattens a nested list
"""


def handle_command(session: Session, task: str) -> tuple[str, bool]:
    """Process one interactive command; returns (output_text, should_quit).

    Shared by the plain REPL and the full-screen TUI.
    """
    task = task.strip()
    if not task:
        return '', False
    if task in ('/quit', '/exit'):
        return '', True
    if task == '/help':
        return HELP, False
    if task.startswith('/open '):
        return session.open_file(task[6:].strip()), False
    if task == '/context':
        if not session.filename:
            return "no file open — use /open <file>", False
        import json
        return json.dumps(analyze_buffer(session.read(), session.filename),
                          indent=2), False
    if task == '/diff':
        return session.diff(), False
    if task == '/apply':
        return session.apply(), False
    if task == '/undo':
        return session.undo(), False
    if task == '/files':
        return '\n'.join(
            ' ' + n for n in sorted(os.listdir(session.workdir))
            if os.path.isfile(os.path.join(session.workdir, n))), False
    return run_task(session, task), False


def repl(session: Session) -> None:
    print("COS CLI — opencode-style deterministic agent. Type /help for commands.")
    while True:
        try:
            task = input('cos> ')
        except (EOFError, KeyboardInterrupt):
            print()
            return
        out, quit_ = handle_command(session, task)
        if quit_:
            return
        if out:
            print(out)
        if session.pending:
            if session.pending[1] == '':
                answer = input(f'create {os.path.basename(session.pending[0])}? [y/N] ').strip().lower()
            else:
                answer = input('apply this edit? [y/N] ').strip().lower()
            if answer in ('y', 'yes'):
                print(session.apply())


def main() -> int:
    parser = argparse.ArgumentParser(
        prog='cos',
        description='OpenCode-style deterministic coding agent for COS.')
    parser.add_argument('task', nargs='?', default=None,
                        help='one-shot task; omit for an interactive session')
    parser.add_argument('--file', default=None, metavar='FILE',
                        help='file the agent works on')
    parser.add_argument('--yes', action='store_true',
                        help='apply pending edits without asking')
    parser.add_argument('--cwd', default=None, metavar='DIR',
                        help='working directory (default: current)')
    parser.add_argument('--tui', action='store_true',
                        help='launch the full-screen TUI (default for '
                             'interactive sessions on a terminal)')
    parser.add_argument('--repl', action='store_true',
                        help='force the plain prompt-loop REPL instead of the TUI')
    args = parser.parse_args()

    session = Session(args.cwd)
    if args.file:
        print(session.open_file(args.file))

    if args.task is None:
        if not args.repl and os.environ.get('COS_NO_TUI') != '1':
            try:
                from cos import tui
                if tui.available():
                    return tui.run_tui(session, args)
            except Exception:
                pass
        repl(session)
        return 0

    print(run_task(session, args.task, auto_apply=args.yes))
    if session.pending:
        if args.yes:
            print(session.apply())
        else:
            if session.pending[1] == '':
                answer = input(f'\ncreate {os.path.basename(session.pending[0])}? [y/N] ').strip().lower()
            else:
                answer = input('\napply this edit? [y/N] ').strip().lower()
            if answer in ('y', 'yes'):
                print(session.apply())
    return 0


if __name__ == '__main__':
    sys.exit(main())
