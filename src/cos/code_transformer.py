"""
COS Code Transformer — deterministic, rule-based transformation of pasted code.

Takes code that the user pasted into a query and applies a requested
modification: add error handling, convert between languages, rename an
identifier, add comments, optimize, explain, convert loops, etc.

All transformations are pure, deterministic rewrites of the given code —
no inference anywhere. When a transformation can't be applied safely, the
module says so instead of guessing.

Public API:
    detect_code_transform(query) -> Optional[(op, params, code, lang)]
    transform_code(op, params, code, lang) -> (edited_code, notes)
"""

import re
from typing import List, Optional, Tuple

# ── Language detection from code content ────────────────────────────────────
_LANG_BY_SYNTAX = [
    (r'^\s*(?:from\s+\w+\s+)?import\s+\w+|^\s*def\s+\w+|^\s*class\s+\w+\s*:|'
     r'^\s*print\(|^\s*if\s+__name__|:\s*(?:pass|break)\s*$', 'python'),
    (r'#include\s*[<"]|std::|::\s*\w+\s*\(', 'c++'),
    (r'public\s+(?:static\s+)?(?:class|void|int|String)\b|System\.out\.',
     'java'),
    (r'^\s*(?:const|let|var)\s+\w+\s*=|=>|console\.log\(|function\s+\w+\s*\(',
     'javascript'),
    (r'^\s*package\s+\w+|^\s*use\s+strict', 'javascript'),
    (r'^\s*func\s+\w+|^\s*package\s+\w+$|:=', 'go'),
    (r'^\s*fn\s+\w+|^\s*use\s+\w+::', 'rust'),
    (r'^\s*SELECT\b|^\s*INSERT\b|^\s*CREATE\s+TABLE\b', 'sql'),
    (r'^\s*#!/|^\s*echo\s|^\s*export\s+\w+=', 'bash'),
    (r'^\s*<\?php', 'php'),
    (r'^\s*(public\s+)?class\s+\w+\s*\{', 'c#'),
]


def detect_code_lang(code: str) -> str:
    """Best-effort language detection from the pasted code itself."""
    for pattern, lang in _LANG_BY_SYNTAX:
        if re.search(pattern, code, re.MULTILINE):
            return lang
    if re.search(r'def\s+\w+\s*\([^)]*\)\s*:', code):
        return 'python'
    if re.search(r'\b(?:const|let|var)\b|=>', code):
        return 'javascript'
    return 'python'


# ── Query detection ──────────────────────────────────────────────────────────

def extract_code_from_query(query: str) -> Tuple[str, str]:
    """Split 'instruction: code' — returns (instruction_head, code)."""
    q = query.strip()
    # fenced code block wins
    m = re.search(r'```(?:\w+)?\n(.*?)```', q, re.DOTALL)
    if m:
        return q[:m.start()].strip(), m.group(1).strip('\n')
    # after the first colon (code can itself contain colons, so take the
    # first colon after a short instruction head)
    m = re.match(r'^(.{2,80}?):\s*(.+)$', q, re.DOTALL)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return q, ''


def detect_code_transform(query: str) -> Optional[Tuple[str, dict, str, str]]:
    """Detect a code-transformation request.

    Returns (op, params, code, lang) or None. ops:
      add_errors, convert_lang, rename, add_comments, make_faster,
      explain, loop_convert, fix (reuse editor).
    """
    q = query.strip()
    if len(q) < 12:
        return None
    head, code = extract_code_from_query(q)
    if not code or len(code) < 3:
        return None
    head_l = head.lower()

    # ── explain this code ───────────────────────────────────────────────
    if re.search(r'\b(?:explain|what\s+does|whats?)\s+(?:this|the|that)\s+'
                 r'(?:python|javascript|code|script|function|program)', head_l) \
            or re.search(r'\bexplain\s+(?:the\s+)?code\b', head_l):
        return ('explain', {}, code, detect_code_lang(code))

    # ── convert / translate between languages ───────────────────────────
    _PROG_LANGS = {
        'python', 'javascript', 'js', 'typescript', 'ts', 'java', 'c++',
        'cpp', 'c#', 'csharp', 'go', 'golang', 'rust', 'ruby', 'php',
        'swift', 'kotlin', 'scala', 'sql', 'bash', 'html', 'css', 'c',
    }
    m = re.search(
        r'\b(?:convert|translate|port|rewrite|migrate|change)\s+'
        r'(?:this\s+|the\s+|that\s+|it\s+)?(?:code|script|program|function)?'
        r'(?:\s*(?:from|in)\s+([a-z#+.\s]+?))?\s*(?:to|into|in)\s+'
        r'([a-z#+.\s]+?)(?:\s+language)?$', head_l)
    # "convert this python code to javascript" — the language sits between
    # "this" and "code", so it needs its own pattern (checked independently
    # of m; the captured word must be a real language, otherwise
    # "convert this code to javascript" would grab "this" as the source).
    m2 = re.search(
        r'\bconvert\s+(?:this\s+|the\s+)?([a-z#+.]+)\s+code\s+(?:to|into)\s+'
        r'([a-z#+.]+)$', head_l)
    src = dst = None
    if m2 is not None and re.sub(r'\s+', '', m2.group(1).lower()) in _PROG_LANGS:
        src, dst = m2.group(1), m2.group(2)
    elif m is not None:
        src, dst = m.group(1), m.group(2)
    if dst is not None:
        dst = dst.strip().rstrip('?!.')
        dst_norm = re.sub(r'\s+', '', dst.lower())
        # the target must be a programming language — "translate to spanish"
        # and "rewrite to be more formal" are text edits, not code converts
        if dst_norm not in _PROG_LANGS:
            return None
        if src:
            src_norm = re.sub(r'\s+', '', src.lower())
            if src_norm not in _PROG_LANGS:
                return None
        # src may be empty for "convert it to javascript" follow-ups —
        # the transformer then infers it from the code itself
        return ('convert_lang', {'src': (src or '').strip(),
                                 'dst': dst.strip()},
                code, detect_code_lang(code))

    # ── add error handling ──────────────────────────────────────────────
    if re.search(r'\b(?:add|include|implement|insert)\s+(?:error|exception)'
                 r'\s+handling\b', head_l) \
            or re.search(r'\b(?:make|wrap)\s+(?:it|this|that|the\s+code|'
                         r'this\s+code)\s*(?:code|script|function)?\s+'
                         r'(?:more\s+)?(?:error\s+)?(?:safe|robust)\b', head_l):
        return ('add_errors', {}, code, detect_code_lang(code))

    # ── rename an identifier ────────────────────────────────────────────
    m = re.search(r'\b(?:rename|change)\s+(?:the\s+)?(?:variable|function|'
                  r'class|method|parameter|argument|name)\s+'
                  r'([A-Za-z_]\w*)\s+(?:to|into)\s+([A-Za-z_]\w*)\b', head_l)
    if m:
        return ('rename', {'old': m.group(1), 'new': m.group(2)}, code,
                detect_code_lang(code))
    m = re.search(r'\brename\s+([A-Za-z_]\w*)\s+(?:to|into)\s+'
                  r'([A-Za-z_]\w*)\b', head_l)
    if m:
        return ('rename', {'old': m.group(1), 'new': m.group(2)}, code,
                detect_code_lang(code))

    # ── add comments / document ─────────────────────────────────────────
    if re.search(r'\b(?:add|write|insert|put)\s+(?:some\s+|more\s+|'
                 r'explanatory\s+|helpful\s+|proper\s+)?comments?\b', head_l) \
            or re.search(r'\bdocument\s+(?:this|the)\s+(?:code|script)\b', head_l) \
            or re.search(r'\bcomment\s+(?:this|the)\s+(?:code|script)\b', head_l):
        return ('add_comments', {}, code, detect_code_lang(code))

    # ── make faster / optimize ──────────────────────────────────────────
    if re.search(r'\b(?:make|speed\s+up)\s+(?:this|the|it|that|the\s+code|'
                 r'this\s+code|the\s+script|this\s+script)\s*(?:code|script|'
                 r'function|program)?\s+(?:faster|quicker|more\s+efficient|'
                 r'efficient)\b', head_l) \
            or re.search(r'\boptimize\s+(?:this|the)\s+(?:code|script|'
                         r'function|program)\b', head_l):
        return ('make_faster', {}, code, detect_code_lang(code))

    # ── loop conversion ─────────────────────────────────────────────────
    m = re.search(r'\b(?:convert|change|rewrite|turn)\s+(?:the\s+|this\s+)?'
                  r'(for\s+loop|while\s+loop)\s+(?:in\s+this\s+code\s+)?'
                  r'(?:to|into)\s+(?:a\s+)?(for\s+loop|while\s+loop)\b', head_l)
    if m:
        return ('loop_convert', {'from': m.group(1), 'to': m.group(2)}, code,
                detect_code_lang(code))

    return None


# ── Transformations ──────────────────────────────────────────────────────────

def _comment_marker(lang: str) -> str:
    if lang in ('python', 'bash', 'ruby', 'go' if False else 'go'):
        return '# '
    return '// '


def transform_code(op: str, params: dict, code: str,
                   lang: Optional[str] = None) -> Tuple[str, List[str]]:
    """Apply a transformation. Returns (edited_code, notes)."""
    if lang is None:
        lang = detect_code_lang(code)
    handler = {
        'add_errors': _add_errors,
        'rename': _rename,
        'add_comments': _add_comments,
        'make_faster': _make_faster,
        'convert_lang': _convert_lang,
        'explain': _explain,
        'loop_convert': _loop_convert,
    }.get(op)
    if handler is None:
        return code, [f"unknown transformation '{op}'"]
    try:
        return handler(code, lang, params or {})
    except Exception:
        return code, ["I couldn't apply that transformation to this code — "
                      "it may use constructs I don't handle yet."]


# ── add error handling ──────────────────────────────────────────────────────

def _split_function_blocks_py(code: str) -> List[Tuple[str, List[str]]]:
    """Split python code into (kind, lines) blocks where kind is
    'func' (with the def line + body) or 'other'."""
    lines = code.split('\n')
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'^(\s*)def\s+(\w+)\s*\([^)]*\)\s*'
                     r'(?:->\s*[^:]+)?\s*:\s*(.*)$', line)
        if m and not m.group(3).strip():
            # collect the body
            indent = m.group(1)
            body = []
            j = i + 1
            while j < len(lines):
                if lines[j].strip() and not lines[j].startswith(indent + ' '):
                    break
                body.append(lines[j])
                j += 1
            blocks.append(('func', [line] + body))
            i = j
        else:
            blocks.append(('other', [line]))
            i += 1
    return blocks


def _add_errors(code: str, lang: str, params: dict) -> Tuple[str, List[str]]:
    if lang == 'python':
        blocks = _split_function_blocks_py(code)
        if len(blocks) == 1 and blocks[0][0] == 'other':
            # whole script wrap
            indent = '    '
            wrapped = ('try:\n' +
                       '\n'.join(indent + ln if ln.strip() else ln
                                 for ln in code.split('\n')) +
                       '\nexcept Exception as e:\n'
                       '    print(f"Error: {e}")\n'
                       '    raise')
            return wrapped, ["wrapped the whole script in try/except — it now "
                             "logs the error before re-raising; adjust the "
                             "handler to your needs"]
        out = []
        n_funcs = 0
        for kind, blk in blocks:
            if kind == 'other':
                out.extend(blk)
                continue
            def_line = blk[0]
            m = re.match(r'^(\s*)def\s+(\w+)\s*\([^)]*\)\s*'
                         r'(?:->\s*[^:]+)?\s*:\s*(.*)$', def_line)
            if m is None:
                out.extend(blk)   # never silently drop an unmatched block
                continue
            indent, fname = m.group(1), m.group(2)
            one_liner = m.group(3).strip()
            body = blk[1:]
            if one_liner:
                body = [indent + '    ' + one_liner]
                def_line = f'{indent}def {fname}():'
                # rebuild the signature line without the one-liner body
                def_line = re.sub(r':\s*[^:]*$', ':', def_line)
            # wrap the body
            wrapped = [f'{indent}def {fname}():'] if one_liner else [def_line]
            wrapped.append(f'{indent}    try:')
            for bl in body:
                wrapped.append('    ' + bl if bl.strip() else bl)
            wrapped.append(f'{indent}    except Exception as e:')
            wrapped.append(f'{indent}        print(f"Error in {fname}: {{e}}")')
            wrapped.append(f'{indent}        raise')
            out.extend(wrapped)
            n_funcs += 1
        unit = 'function bodies' if n_funcs != 1 else 'function body'
        note = (f"wrapped {n_funcs} {unit} in try/except — each logs and "
                "re-raises; tailor the handler to your needs")
        return '\n'.join(out), [note]
    # brace languages
    if lang in ('javascript', 'typescript', 'java', 'c++', 'c#', 'go'):
        return _wrap_braced(code, lang)
    return code, [f"I can add error handling for python/javascript/java/C++/Go, "
                  f"but not for {lang or 'this code'} yet."]


def _wrap_braced(code: str, lang: str) -> Tuple[str, List[str]]:
    comment = '//' if lang != 'go' else '//'
    lines = code.split('\n')
    out = []
    wrapped = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        # function definitions: "function name(...) {", "name(...) {", "func name(...) {"
        m = re.match(r'^(\s*)((?:function\s+|func\s+|public\s+static\s+)?'
                     r'\w[\w.]*\s*\([^)]*\)\s*(?::\s*\w+\s*)?)\{\s*$', line)
        if m and not re.search(r'\b(?:if|for|while|switch|catch)\b', m.group(2)):
            # find matching closing brace
            indent = m.group(1)
            depth = 1
            body = []
            j = i + 1
            while j < len(lines) and depth > 0:
                depth += lines[j].count('{') - lines[j].count('}')
                body.append(lines[j])
                j += 1
            if depth == 0 and body:
                # the collected body includes the function's own closing
                # brace — drop it, the wrapper adds its own
                if body and body[-1].strip() == '}':
                    body = body[:-1]
                inner = [(l if not l.strip() else '  ' + l) for l in body]
                wrapped_code = [line, f'{indent}  try {{'] + inner + [
                    f'{indent}  }} catch (err) {{',
                    f'{indent}    console.error(err);',
                    f'{indent}  }}']
                out.extend(wrapped_code)
                wrapped += 1
                i = j
                continue
        out.append(line)
        i += 1
    if wrapped:
        unit = 'function bodies' if wrapped != 1 else 'function body'
        note = (f"wrapped {wrapped} {unit} in try/catch — errors are logged "
                "to the console; tailor the catch handler to your needs")
        return '\n'.join(out), [note]
    return code, ["I didn't find a function body to wrap — paste a complete "
                  "function or script and I'll add try/catch to it."]


# ── rename ──────────────────────────────────────────────────────────────────

def _rename(code: str, lang: str, params: dict) -> Tuple[str, List[str]]:
    old, new = params.get('old', ''), params.get('new', '')
    if not old or not new:
        return code, ["I need both the old and the new name."]
    if old == new:
        return code, ["the old and new name are the same — nothing to change"]
    pattern = re.compile(r'(?<![A-Za-z0-9_])' + re.escape(old) +
                         r'(?![A-Za-z0-9_])')
    count = len(pattern.findall(code))
    if count == 0:
        return code, [f'"{old}" doesn\'t appear in the code — nothing to rename.']
    fixed = pattern.sub(new, code)
    return fixed, [f'renamed "{old}" -> "{new}" ({count} occurrence'
                   + ('s' if count != 1 else '') + ')']


# ── add comments ────────────────────────────────────────────────────────────

_CSHARP_LIKE = {'javascript', 'typescript', 'java', 'c++', 'c#', 'go', 'rust'}


def _describe_line(line: str, lang: str) -> Optional[str]:
    """Produce a short English description of what a code line does."""
    s = line.strip()
    if not s:
        return None
    m = re.match(r'^(?:def|function|func)\s+(\w+)', s)
    if m:
        return f"Define the function {m.group(1)}"
    m = re.match(r'^class\s+(\w+)', s)
    if m:
        return f"Define the class {m.group(1)}"
    m = re.match(r'^(?:import\s+\w+|from\s+\w+\s+import\s+\w+|'
                 r'const\s+\w+\s*=\s*require\s*\([^)]*\)|use\s+\w+(?:::)?)', s)
    if m:
        return "Import a module or package"
    m = re.match(r'^(?:if|elif|else\s+if)\s+(.+?)(?::|\s*\{)\s*$', s)
    if m:
        return "Check the condition: " + m.group(1).strip()[:60]
    if s.startswith('else:'):
        return "Fallback branch when the conditions above are false"
    m = re.match(r'^for\s+(.+?)(?::|\s*\{)\s*$', s)
    if m:
        return "Loop over: " + m.group(1).strip()[:60]
    m = re.match(r'^while\s+(.+?)(?::|\s*\{)\s*$', s)
    if m:
        return "Loop while: " + m.group(1).strip()[:60]
    m = re.match(r'^try\s*:', s)
    if m:
        return "Start a try block (code that may raise errors)"
    m = re.match(r'^except\s+(.+?)(?:\s+as\s+\w+)?\s*:', s)
    if m:
        return "Handle the exception: " + m.group(1).strip()[:60]
    m = re.match(r'^return\s+(.+)$', s)
    if m:
        return "Return the value: " + m.group(1).strip()[:60]
    m = re.match(r'^print\s*\((.+)\)\s*$', s)
    if m:
        return "Print: " + m.group(1).strip()[:60]
    m = re.match(r'^console\.log\s*\((.+)\)\s*;?$', s)
    if m:
        return "Log to the console: " + m.group(1).strip()[:60]
    m = re.match(r'^(\w+(?:\.\w+)*)\s*(?:\+=|-=|\*=|/=|=)\s*(.+)$', s)
    if m:
        op = 'adds' if '+=' in s else ('appends to' if '.append' in s else
                                       'assigns')
        return f"Assign {m.group(2).strip()[:50]} to {m.group(1)}"
    return None


def _add_comments(code: str, lang: str, params: dict) -> Tuple[str, List[str]]:
    marker = '# ' if lang in ('python', 'bash', 'ruby') else '// '
    lines = code.split('\n')
    out = []
    added = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        if stripped.startswith(('#', '//', '/*', '*', '"""', "'''")):
            out.append(line)
            continue
        if stripped in ('}', '{', ');'):
            out.append(line)
            continue
        desc = _describe_line(line, lang)
        if desc:
            out.append(marker + desc)
            added += 1
        out.append(line)
    if added == 0:
        return code, ["I didn't recognize any constructs to comment — "
                      "paste code with functions, loops, or conditions."]
    return '\n'.join(out), [f"added {added} explanatory comment"
                            + ('s' if added != 1 else '')]


# ── make faster ─────────────────────────────────────────────────────────────

def _make_faster(code: str, lang: str, params: dict) -> Tuple[str, List[str]]:
    notes = []
    fixed = code

    if lang == 'python':
        # accumulate-append loop -> list comprehension:
        #   result = []
        #   for x in <iter>:
        #       result.append(<expr>)
        m = re.search(
            r'^\s*(\w+)\s*=\s*\[\]\n'
            r'^\s*for\s+(.+?)\s+in\s+(.+?):\n'
            r'^\s*\1\.append\((.+)\)\s*$',
            fixed, re.MULTILINE)
        if m:
            name, var, iterable, expr = m.group(1), m.group(2), m.group(3), m.group(4)
            pattern = re.compile(
                r'^\s*' + re.escape(name) + r'\s*=\s*\[\]\n'
                r'^\s*for\s+' + re.escape(var) + r'\s+in\s+'
                r'(.+?):\n' +
                r'^\s*' + re.escape(name) + r'\.append\((.*)\)\s*$',
                re.MULTILINE)
            fixed = pattern.sub(
                lambda mm: f'{name} = [{mm.group(2)} for {var} in {mm.group(1)}]',
                fixed)
            notes.append("replaced the accumulate-and-append loop with a list "
                         "comprehension (faster and more readable)")

        # string += in a loop -> list + join
        m = re.search(r'(\w+)\s*=\s*["\']\s*["\']', fixed)
        if m and re.search(r'\b' + re.escape(m.group(1)) + r'\s*\+=', fixed):
            name = m.group(1)
            parts = re.split(r'\n\s*' + re.escape(name) + r'\s*\+=\s*', fixed)
            if len(parts) == 2:
                notes.append("string concatenation in a loop is O(n²) — collect "
                             "pieces in a list and join() them once instead")
        if not notes:
            return code, ["I looked for the common optimizations (loop→list "
                          "comprehension, string += → join) but didn't find "
                          "any to apply safely. Paste the code and I'll take "
                          "another look."]
        return fixed, notes

    if lang == 'javascript':
        # const result = []; for (const x of xs) { result.push(expr); } -> xs.map()
        m = re.search(
            r'const\s+(\w+)\s*=\s*\[\];?\s*\n'
            r'for\s*\(\s*(?:const\s+)?(\w+)\s+of\s+(.+?)\s*\)\s*\{\s*\n'
            r'\s*\1\.push\((.+?)\);\s*\n\s*\}',
            fixed)
        if m:
            name, var, iterable, expr = m.group(1), m.group(2), m.group(3), m.group(4)
            pattern = re.compile(
                r'const\s+' + re.escape(name) + r'\s*=\s*\[\];?\s*\n'
                r'for\s*\(\s*(?:const\s+)?' + re.escape(var) +
                r'\s+of\s+(.+?)\s*\)\s*\{\s*\n'
                r'\s*' + re.escape(name) + r'\.push\((.+?)\);\s*\n\s*\}')
            fixed = pattern.sub(
                lambda mm: f'const {name} = {mm.group(1)}.map({var} => '
                          f'{mm.group(2)});',
                fixed)
            notes.append("replaced the for-push loop with Array.map() "
                         "(cleaner and often faster)")
        if not notes:
            return code, ["I looked for the common optimization (push-loop → "
                          "map) but didn't find it. Paste the code and I'll "
                          "take another look."]
        return fixed, notes

    return code, [f"I can suggest optimizations for Python and JavaScript, "
                  f"but not for {lang or 'this code'} yet."]


# ── language conversion (python <-> javascript) ─────────────────────────────

def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(' '))


def _py_to_js(code: str) -> str:
    lines = code.split('\n')
    out = []
    declared = set()
    stack = []  # indents of open blocks

    def close_to(level: int):
        # a line at the same indent as a block opener closes that block
        while stack and stack[-1] >= level:
            indent = stack.pop()
            out.append(' ' * indent + '}')

    for raw in lines:
        if not raw.strip():
            continue
        indent = _indent_of(raw)
        s = raw.strip()
        # else/elif/except/finally continue a block already opened at this
        # indent — they close it inline ("} else {") instead of emitting a
        # separate closing brace.
        _continues_block = bool(re.match(r'^(?:else|finally)\s*:|^elif\b|^except\b', s))
        if not _continues_block:
            close_to(indent)
        # comments
        if s.startswith('#'):
            out.append(' ' * indent + '// ' + s[1:].strip())
            continue
        # function def
        m = re.match(r'^def\s+(\w+)\s*\(([^)]*)\)\s*:\s*(.*)$', s)
        if m:
            args = re.sub(r'\s+', ' ', m.group(2)).strip()
            args = re.sub(r':\s*\w+', '', args)
            out.append(' ' * indent + f'function {m.group(1)}({args}) {{')
            stack.append(indent)
            if m.group(3).strip():
                out.append(' ' * (indent + 2) + m.group(3).strip() + ';')
                close_to(indent)
            continue
        # class
        m = re.match(r'^class\s+(\w+)(?:\(([^)]*)\))?\s*:', s)
        if m:
            parent = m.group(2) or ''
            out.append(' ' * indent + f'class {m.group(1)} {{')
            stack.append(indent)
            continue
        # loops / conditions / try
        m = re.match(r'^for\s+(\w+)\s+in\s+range\s*\(\s*(\w+|\d+)\s*\)\s*:\s*(.*)$', s)
        if m:
            out.append(' ' * indent +
                       f'for (let i = 0; i < {m.group(2)}; i++) {{')
            stack.append(indent)
            if m.group(3).strip():
                out.append(' ' * (indent + 2) + m.group(3).strip() + ';')
                close_to(indent)
            continue
        m = re.match(r'^for\s+(\w+)\s+in\s+(.+?)\s*:\s*(.*)$', s)
        if m:
            out.append(' ' * indent + f'for (const {m.group(1)} of {m.group(2)}) {{')
            stack.append(indent)
            if m.group(3).strip():
                out.append(' ' * (indent + 2) + m.group(3).strip() + ';')
                close_to(indent)
            continue
        m = re.match(r'^while\s+(.+?)\s*:\s*(.*)$', s)
        if m:
            out.append(' ' * indent + f'while ({m.group(1)}) {{')
            stack.append(indent)
            if m.group(3).strip():
                out.append(' ' * (indent + 2) + m.group(3).strip() + ';')
                close_to(indent)
            continue
        m = re.match(r'^(if|elif)\s+(.+?)\s*:\s*(.*)$', s)
        if m:
            if m.group(1) == 'elif':
                if stack and stack[-1] == indent:
                    stack.pop()
                out.append(' ' * indent + f'}} else if ({m.group(2)}) {{')
            else:
                out.append(' ' * indent + f'if ({m.group(2)}) {{')
            stack.append(indent)
            if m.group(3).strip():
                out.append(' ' * (indent + 2) + m.group(3).strip() + ';')
                close_to(indent)
            continue
        if s == 'else:':
            if stack and stack[-1] == indent:
                stack.pop()
            out.append(' ' * indent + '} else {')
            stack.append(indent)
            continue
        m = re.match(r'^try\s*:\s*(.*)$', s)
        if m:
            out.append(' ' * indent + 'try {')
            stack.append(indent)
            if m.group(1).strip():
                out.append(' ' * (indent + 2) + m.group(1).strip() + ';')
                close_to(indent)
            continue
        m = re.match(r'^except\s+(\w+)\s+as\s+(\w+)\s*:', s)
        if m:
            if stack and stack[-1] == indent:
                stack.pop()
            out.append(' ' * indent + f'}} catch ({m.group(2)}) {{')
            stack.append(indent)
            continue
        m = re.match(r'^finally\s*:', s)
        if m:
            if stack and stack[-1] == indent:
                stack.pop()
            out.append(' ' * indent + '} finally {')
            stack.append(indent)
            continue
        # statements
        s = _py_stmt_to_js(s)
        # assignment declarations (single vars and tuple destructuring)
        m = re.match(r'^\[([\w,\s]+)\]\s*=(?!=)\s*(.+)$', s)
        if m:
            names = [n.strip() for n in m.group(1).split(',')]
            if any(n not in declared for n in names):
                declared.update(names)
                s = 'let ' + s
        else:
            m = re.match(r'^(\w+)\s*=(?!=)\s*(.+)$', s)
            if m and m.group(1) not in declared:
                declared.add(m.group(1))
                s = f'let {s}'
        out.append(' ' * indent + s.rstrip() + ';' if not s.rstrip().endswith(';')
                   else ' ' * indent + s.rstrip())
    close_to(-1)
    return '\n'.join(out)


def _py_stmt_to_js(s: str) -> str:
    s = re.sub(r'\bprint\s*\((.*)\)', r'console.log(\1)', s)
    s = re.sub(r'\b(True|False|None)\b', lambda m:
               {'True': 'true', 'False': 'false', 'None': 'null'}[m.group(1)], s)
    s = re.sub(r'\.append\(', '.push(', s)
    s = re.sub(r'\blen\((\w+)\)', r'\1.length', s)
    s = re.sub(r'\bstr\(', 'String(', s)
    s = re.sub(r'\bint\(', 'parseInt(', s)
    s = re.sub(r'\bfloat\(', 'parseFloat(', s)
    s = re.sub(r'\bnot\s+', '! ', s)
    s = re.sub(r'\band\b', '&&', s)
    s = re.sub(r'\bor\b', '||', s)
    s = re.sub(r'==\s*None', '=== null', s)
    s = re.sub(r'==', '===', s)
    s = re.sub(r'!=', '!==', s)
    # tuple assignment / swap: a, b = b, a + b  ->  [a, b] = [b, a + b];
    s = re.sub(r'^(\w+(?:\s*,\s*\w+)+)\s*=\s*(.+)$',
               r'[\1] = [\2]', s)
    s = re.sub(r'\\n', '\\n', s)
    return s


def _js_to_py(code: str) -> str:
    lines = code.split('\n')
    out = []
    stack = []

    def dedent_to(level: int):
        while stack and stack[-1] > level:
            stack.pop()

    for raw in lines:
        if not raw.strip():
            continue
        indent = _indent_of(raw)
        s = raw.strip().rstrip(';')
        if s == '}':
            # closing brace: pop the block
            dedent_to(indent - 2 if indent >= 2 else 0)
            continue
        if s.startswith('//'):
            out.append(' ' * indent + '# ' + s[2:].strip())
            continue
        if s == '{':
            continue
        m = re.match(r'^function\s+(\w+)\s*\(([^)]*)\)\s*\{?$', s)
        if m:
            args = ', '.join(a.strip() for a in m.group(2).split(',') if a.strip())
            out.append(' ' * indent + f'def {m.group(1)}({args}):')
            stack.append(indent)
            continue
        m = re.match(r'^class\s+(\w+)\s*\{?$', s)
        if m:
            out.append(' ' * indent + f'class {m.group(1)}:')
            stack.append(indent)
            continue
        m = re.match(r'^for\s*\(\s*let\s+(\w+)\s*=\s*0;\s*\1\s*<\s*'
                     r'(\w+|\d+)\s*;\s*\1\+\+\s*\)\s*\{?$', s)
        if m:
            out.append(' ' * indent + f'for {m.group(1)} in range({m.group(2)}):')
            stack.append(indent)
            continue
        m = re.match(r'^for\s*\(\s*(?:const|let|var)\s+(\w+)\s+of\s+(.+?)\s*\)\s*\{?$', s)
        if m:
            out.append(' ' * indent + f'for {m.group(1)} in {m.group(2)}:')
            stack.append(indent)
            continue
        m = re.match(r'^while\s*\((.+?)\)\s*\{?$', s)
        if m:
            out.append(' ' * indent + f'while {m.group(1)}:')
            stack.append(indent)
            continue
        m = re.match(r'^if\s*\((.+?)\)\s*\{?$', s)
        if m:
            out.append(' ' * indent + f'if {_js_cond_to_py(m.group(1))}:')
            stack.append(indent)
            continue
        m = re.match(r'^\}\s*else\s+if\s*\((.+?)\)\s*\{?$', s)
        if m:
            out.append(' ' * indent + f'elif {_js_cond_to_py(m.group(1))}:')
            stack.append(indent)
            continue
        if re.match(r'^\}\s*else\s*\{?$', s):
            out.append(' ' * indent + 'else:')
            stack.append(indent)
            continue
        m = re.match(r'^try\s*\{?$', s)
        if m:
            out.append(' ' * indent + 'try:')
            stack.append(indent)
            continue
        m = re.match(r'^\}\s*catch\s*\((\w+)\)\s*\{?$', s)
        if m:
            out.append(' ' * indent + f'except Exception as {m.group(1)}:')
            stack.append(indent)
            continue
        m = re.match(r'^\}\s*finally\s*\{?$', s)
        if m:
            out.append(' ' * indent + 'finally:')
            stack.append(indent)
            continue
        m = re.match(r'^(?:const|let|var)\s+(\w+)\s*=\s*(.+)$', s)
        if m:
            out.append(' ' * indent + f'{m.group(1)} = {_js_stmt_to_py(m.group(2))}')
            continue
        out.append(' ' * indent + _js_stmt_to_py(s))
    # close remaining blocks
    while stack:
        stack.pop()
    return '\n'.join(out)


def _js_cond_to_py(cond: str) -> str:
    cond = re.sub(r'===', '==', cond)
    cond = re.sub(r'!==', '!=', cond)
    cond = re.sub(r'\s&&\s', ' and ', cond)
    cond = re.sub(r'\s\|\|\s', ' or ', cond)
    cond = re.sub(r'!\s*(\w)', r'not \1', cond)
    return cond.strip()


def _js_stmt_to_py(s: str) -> str:
    s = re.sub(r'\bconsole\.log\s*\((.*)\)\s*$', r'print(\1)', s)
    s = re.sub(r'\.push\(', '.append(', s)
    s = re.sub(r'(\w+)\.length\b', r'len(\1)', s)
    s = re.sub(r'\b(true|false|null)\b', lambda m:
               {'true': 'True', 'false': 'False', 'null': 'None'}[m.group(1)], s)
    s = re.sub(r'\bString\s*\(', 'str(', s)
    s = re.sub(r'\bparseInt\s*\(', 'int(', s)
    s = re.sub(r'\bparseFloat\s*\(', 'float(', s)
    s = re.sub(r'===', '==', s)
    s = re.sub(r'!==', '!=', s)
    return s


def _convert_lang(code: str, lang: str, params: dict) -> Tuple[str, List[str]]:
    src = (params.get('src') or '').strip().lower()
    dst = (params.get('dst') or '').strip().lower()

    def _norm(l):
        l = re.sub(r'\s+', '', l)
        return {'py': 'python', 'js': 'javascript', 'ts': 'typescript',
                'cpp': 'c++', 'cs': 'c#'}.get(l, l)

    src, dst = _norm(src), _norm(dst)
    if not src:
        src = detect_code_lang(code)  # "convert it to javascript" follow-ups
    if not dst:
        return code, ["tell me the target language: 'convert this code to "
                      "javascript: ...'"]
    pairs = {('python', 'javascript'), ('javascript', 'python')}
    if (src, dst) not in pairs:
        return code, [f"I can convert between python and javascript, but not "
                      f"from {src} to {dst} yet."]
    try:
        if (src, dst) == ('python', 'javascript'):
            return _py_to_js(code), ["converted python -> javascript. This is "
                                     "a best-effort mechanical translation — "
                                     "check names, imports, and edge cases."]
        return _js_to_py(code), ["converted javascript -> python. This is a "
                                 "best-effort mechanical translation — check "
                                 "names, imports, and edge cases."]
    except Exception:
        return code, ["I couldn't convert this code — it may use constructs "
                      "my converter doesn't handle (classes with complex "
                      "bodies, decorators, destructuring, ...)."]


# ── explain code ────────────────────────────────────────────────────────────

def _explain(code: str, lang: str, params: dict) -> Tuple[str, List[str]]:
    lines = code.split('\n')
    parts = [f"Here's what this {lang} code does, line by line:"]
    funcs = []
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        s = line.strip()
        m = re.match(r'^(?:def|function|func)\s+(\w+)', s)
        if m:
            funcs.append(m.group(1))
        desc = _describe_line(line, lang)
        if desc:
            parts.append(f"`L{i}`: {desc}")
        else:
            parts.append(f"`L{i}`: {s[:70]}")
    if funcs:
        parts.append("")
        parts.append("**In a nutshell:** this code defines the function"
                     + ("s" if len(funcs) > 1 else "")
                     + f" `{', '.join(funcs)}`. "
                     + "To trace what it does, read the lines in order — "
                       "each `L{n}` above describes one step.")
    else:
        parts.append("")
        parts.append("**In a nutshell:** this is a standalone script. Read the "
                     "lines in order — each `L{n}` above describes one step.")
    return '\n'.join(parts), ["line-by-line explanation (heuristic — read it "
                              "as a guide, not a guarantee)"]


# ── loop conversion ─────────────────────────────────────────────────────────

def _loop_convert(code: str, lang: str, params: dict) -> Tuple[str, List[str]]:
    to_while = params.get('to', '').startswith('while')
    if lang != 'python':
        return code, ["loop conversion currently works for python "
                      "(for-range <-> while)."]
    if to_while:
        # for i in range(a, b, c): -> i = a; while ...; i += c
        m = re.search(
            r'^(\s*)for\s+(\w+)\s+in\s+range\(\s*'
            r'(\d+|\w+)\s*(?:,\s*(\d+|\w+)\s*(?:,\s*([-+]?\d+)\s*)?)?'
            r'\)\s*:\s*(.*)$',
            code, re.MULTILINE)
        if not m:
            return code, ["I couldn't find a `for i in range(...)` loop to "
                          "convert."]
        indent, var, first, second, step, one_liner = (m.group(1), m.group(2),
                                                       m.group(3), m.group(4),
                                                       m.group(5), m.group(6))
        if second is None:
            # range(n) == range(0, n)
            a, b = '0', first
        else:
            a, b = first, second
        step = int(step) if step else 1
        # body = the loop's indented block
        body = []
        if one_liner.strip():
            body = [indent + '    ' + one_liner]
        else:
            rest = code[code.index(m.group(0)):].split('\n')
            k = 1
            while k < len(rest):
                ln = rest[k]
                if ln.strip() and not ln.startswith(indent + ' '):
                    break
                body.append(ln)
                k += 1
        cond = f'{var} < {b}' if step > 0 else f'{var} > {b}'
        lines = [f'{indent}{var} = {a}', f'{indent}while {cond}:']
        lines.extend(body)
        lines.append(f'{indent}    {var} += {step}')
        return '\n'.join(lines), ["converted the for-range loop to a while "
                                  "loop (same behavior)"]
    # while -> for: only counter loops `i = 0 / while i < n: / i += 1`
    m = re.search(
        r'^(\s*)(\w+)\s*=\s*(0|\d+)\n'
        r'\1while\s+\2\s*<\s*(\w+|\d+)\s*:\n(.*?)'
        r'\1\s{4}\2\s*\+=\s*1\s*$',
        code, re.MULTILINE | re.DOTALL)
    if not m:
        return code, ["I can only convert a counter loop (`i = 0; while i < n; "
                      "i += 1`) back to a for loop — this one doesn't match "
                      "that shape."]
    indent, var, a, b, body = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
    body = body.rstrip('\n')
    return (f'{indent}for {var} in range({a}, {b}):\n{body}',
            ["converted the counter while-loop to a for-range loop"])
