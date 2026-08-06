"""COS Code Editor Harness — fill-in / completion for editor integrations.

This module is the entry point for a *harness*: an editor plugin or IDE
integration that hands the engine the current buffer and asks it to fill
in code. Unlike ``process_query`` (chat-style answers), this API is
buffer-aware:

    * it reads the surrounding code (language, imports, defined names,
      indentation, quote style) and makes its insertion consistent with it;
    * it fills the empty body of a function (``...`` marker, bare ``pass``,
      empty ``{ }``) — either from the signature alone, from the function
      name, or from an instruction (comment / chat text);
    * it generates whole functions that fit the buffer's context.

Deterministic and offline: every insertion is produced by rules over the
signature, the function name, and the curated task templates in
``code_gen`` — never by sampling.

Public API (what a harness should use)::

    from cos.code_editor import analyze_buffer, complete_buffer, fill_in

    ctx = analyze_buffer(code, filename="tool.py")        # what's in the file
    res = complete_buffer(code, instruction="sum the two numbers")
    # res["text"]  -> the exact text to insert (already indented)
    # res["notes"] -> what was assumed / inferred

    answer = fill_in("complete this function: def add(a, b):\\n    ...")
    # full chat-style answer, for the engine / CLI path
"""

import os
import re

try:
    from cos.code_gen import _CODE, detect_task, generate_code
except Exception:  # pragma: no cover - only when cos is partially importable
    _CODE = {}
    detect_task = None
    generate_code = None


# ── Language detection (buffer + filename aware) ────────────────────────────

_EXT_LANG = {
    '.py': 'python', '.pyw': 'python', '.js': 'javascript', '.mjs': 'javascript',
    '.cjs': 'javascript', '.jsx': 'javascript', '.ts': 'typescript',
    '.tsx': 'typescript', '.java': 'java', '.c': 'c', '.h': 'c',
    '.cpp': 'c++', '.cc': 'c++', '.hpp': 'c++', '.cs': 'c#',
    '.go': 'go', '.rs': 'rust', '.rb': 'ruby', '.php': 'php',
    '.swift': 'swift', '.kt': 'kotlin', '.sh': 'bash', '.bash': 'bash',
    '.zsh': 'bash', '.sql': 'sql', '.html': 'html', '.css': 'css',
}


def detect_lang(code: str, filename: str = "") -> str:
    """Language of the buffer: filename extension wins, then syntax."""
    ext = os.path.splitext(filename or '')[1].lower()
    if ext in _EXT_LANG:
        return _EXT_LANG[ext]
    try:
        from cos.code_transformer import detect_code_lang
        return detect_code_lang(code)
    except Exception:
        return 'python'


# ── Buffer context ----------------------------------------------------------

_IMPORT_RES = {
    'python': [r'^\s*(?:import|from)\s+([\w.]+)', r'^\s*import\s+(\w+)'],
    'javascript': [(r'^\s*import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]'),
                   r'^\s*(?:const|let|var)\s+(\w+)\s*=\s*require\s*\('],
    'typescript': [r'^\s*import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]'],
    'go': [r'^\s*([\w./]+)\s*$'],  # package block lines handled separately
    'java': [r'^\s*import\s+([\w.]+)'],
    'c++': [r'^\s*#include\s*[<"]([^>"]+)[>"]'],
    'c#': [r'^\s*using\s+([\w.]+)'],
    'rust': [r'^\s*use\s+([\w:]+)'],
}


def extract_imports(code: str, lang: str) -> list[str]:
    """Module names this buffer already imports (unique, in order)."""
    names: list[str] = []
    for pat in _IMPORT_RES.get(lang, []):
        for m in re.finditer(pat, code, re.MULTILINE):
            name = m.group(1)
            if name not in names:
                names.append(name)
    return names


_DEF_RES = {
    'python': [r'^\s*(?:async\s+)?def\s+(\w+)', r'^\s*class\s+(\w+)'],
    'javascript': [r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)',
                   r'^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\(.*\)|\w+)\s*=>'],
    'typescript': [r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)(?:<[^>]*>)?',
                   r'^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:<[^>]*>)?\s*(?:async\s*)?(?:\(.*\)|\w+)\s*=>'],
    'java': [(r'^\s*(?:public|private|protected|static|final|synchronized|abstract|\s)*\s*'
              r'[\w<>\[\],\s]+\s+(\w+)\s*\(')],
    'c++': [r'^\s*(?:virtual\s+)?[\w:<>,&*\s]+\s+(\w+)\s*\([^;]*\)\s*(?:const\s*)?\{'],
    'c#': [(r'^\s*(?:public|private|protected|internal|static|async|override|virtual|\s)*\s*'
           r'[\w<>\[\],\s]+\s+(\w+)\s*\(')],
    'go': [r'^\s*func\s+(\w+)'],
    'rust': [r'^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)'],
    'bash': [r'^\s*(?:function\s+)?(\w+)\s*\(\s*\)\s*\{'],
}


def extract_defs(code: str, lang: str) -> list[tuple[str, str]]:
    """Defined names as (kind, name). kind is 'function' or 'class'."""
    out: list[tuple[str, str]] = []
    for pat in _DEF_RES.get(lang, []):
        for m in re.finditer(pat, code, re.MULTILINE):
            name = m.group(1)
            if name in ('if', 'for', 'while', 'switch', 'catch', 'with'):
                continue
            kind = 'class' if (pat.startswith(r'^\s*class') or name[:1].isupper()
                               and lang == 'java' and 'class' in m.group(0)) else 'function'
            out.append((kind, name))
    return out


def detect_indent(code: str) -> tuple[str, int]:
    """Return ('spaces'|'tabs', unit). Defaults to 4 spaces.

    The unit is the GCD of every observed space indent width, so a file
    whose deepest block is 8 or 12 spaces still reports a 4-space unit
    (a majority vote of absolute widths would overcount deep nesting).
    """
    from math import gcd
    tab_lines = 0
    widths: list[int] = []
    for line in code.split('\n'):
        stripped = line.lstrip()
        if not stripped or stripped == line:
            continue
        if line[0] == '\t':
            tab_lines += 1
        else:
            n = len(line) - len(line.lstrip(' '))
            if n > 0:
                widths.append(n)
    if tab_lines > len(widths):
        return ('tabs', 1)
    if widths:
        unit = 0
        for w in widths:
            unit = gcd(unit, w)
        return ('spaces', unit if unit > 0 else 4)
    return ('spaces', 4)


def _quote_style(code: str, lang: str) -> str:
    """Dominant quote style in string literals: \"'\" or '\"'."""
    singles = len(re.findall(r"'(?:[^'\\]|\\.)*'", code))
    doubles = len(re.findall(r'"(?:[^"\\]|\\.)*"', code))
    return '"' if doubles > singles else "'"


def _has_type_hints(code: str, lang: str) -> bool:
    if lang == 'python':
        return bool(re.search(r'^\s*(?:async\s+)?def\s+\w+\s*\([^)]*:\s*',
                              code, re.MULTILINE))
    return lang in ('typescript', 'java', 'c#', 'go', 'rust', 'c++')


def analyze_buffer(code: str, filename: str = "") -> dict:
    """Describe the buffer: language, imports, definitions, style.

    This is what a harness uses to understand the file *before* deciding
    what to ask. Everything returned is deterministic.
    """
    lang = detect_lang(code, filename)
    indent_kind, indent_unit = detect_indent(code)
    return {
        'language': lang,
        'imports': extract_imports(code, lang),
        'definitions': extract_defs(code, lang),
        'indent': {'kind': indent_kind, 'unit': indent_unit},
        'quote_style': _quote_style(code, lang),
        'type_hints': _has_type_hints(code, lang),
        'line_count': code.count('\n') + 1,
    }


# ── Signature parsing -------------------------------------------------------

_PARAMS = r'((?:[^()]|\([^()]*\))*)'


_SIG_RES = {
    'python': r'^\s*(?:async\s+)?def\s+(\w+)\s*\(' + _PARAMS + r'\)\s*(?:->\s*([^:#]+))?\s*:',
    'javascript': [
        r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*\(' + _PARAMS + r'\)\s*(?::\s*([^{]+))?\s*\{',
        r'^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(' + _PARAMS + r'\)\s*=>\s*\{',
    ],
    'typescript': [
        r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)(?:<[^>]*>)?\s*\(' + _PARAMS + r'\)\s*:\s*([^{]+?)\s*\{',
        r'^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:<[^>]*>)?\s*(?:async\s*)?\(' + _PARAMS + r'\)\s*(?::\s*([^{]+?))?\s*=>\s*\{',
        r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)(?:<[^>]*>)?\s*\(' + _PARAMS + r'\)\s*\{',
    ],
    'go': r'^\s*func\s+(\w+)\s*\(' + _PARAMS + r'\)\s*([\w\[\]\*\.<>]+)?\s*\{',
    'rust': r'^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*\(' + _PARAMS + r'\)\s*(?:->\s*([^{]+))?\s*\{',
    'c++': r'^\s*(?:virtual\s+)?([\w:<>,&*\s]+?)\s+(\w+)\s*\(' + _PARAMS + r'\)\s*(?:const\s*)?\{',
    'c#': [(r'^\s*(?:public|private|protected|internal|static|async|override|virtual|\s)*\s*'
           r'([\w<>\[\],\s]+?)\s+(\w+)\s*\(' + _PARAMS + r'\)\s*\{')],
    'java': [(r'^\s*(?:public|private|protected|static|final|synchronized|abstract|\s)*\s*'
             r'([\w<>\[\],\s]+?)\s+(\w+)\s*\(' + _PARAMS + r'\)\s*(?:throws\s+[\w,\s]+)?\s*\{')],
    'bash': r'^\s*(?:function\s+)?(\w+)\s*\(\s*\)\s*\{',
}


def _split_params(text: str) -> list[tuple[str, str]]:
    """Split a parameter list on top-level commas; return (name, type)."""
    if not text.strip():
        return []
    parts, depth, cur = [], 0, ''
    for ch in text:
        if ch in '([{<':
            depth += 1
        elif ch in ')]}>':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(cur)
            cur = ''
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    params = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # drop defaults: name: type = default
        p = re.split(r'\s*=\s*', p, maxsplit=1)[0].strip()
        # js/ts/rust/c++ type forms: "name: type" / "name type"
        if ':' in p:
            name, _, typ = p.partition(':')
        else:
            bits = p.split()
            if len(bits) >= 2 and bits[0] not in ('const', 'let', 'var', 'final', 'mut', 'ref', 'val'):
                name, typ = bits[-1], ' '.join(bits[:-1])
            else:
                name, typ = bits[0] if bits else '', ''
        name = name.strip()
        if name:
            params.append((name, typ.strip()))
    return params


def _parse_signature(line: str, lang: str) -> "dict | None":
    """Parse a function signature line into {name, params, ret, is_method}."""
    pats = _SIG_RES.get(lang)
    if not pats:
        return None
    if isinstance(pats, str):
        pats = [pats]
    for pat in pats:
        m = re.match(pat, line)
        if not m:
            continue
        if lang in ('c++', 'c#', 'java'):
            ret, name, params_txt = m.group(1).strip(), m.group(2), m.group(3)
        elif lang == 'go':
            name, params_txt, ret = m.group(1), m.group(2), (m.group(3) or '').strip()
        else:
            name, params_txt = m.group(1), m.group(2)
            ret = (m.group(3) or '').strip() if m.lastindex and m.lastindex >= 3 else ''
            ret = ret.rstrip('{').strip()
        params = _split_params(params_txt)
        is_method = lang == 'python' and bool(params) and params[0][0] in ('self', 'cls')
        is_async = bool(re.search(r'\basync\b', line))
        return {
            'name': name, 'params': params, 'ret': ret,
            'is_method': is_method, 'is_async': is_async,
            'indent': len(line) - len(line.lstrip()),
        }
    return None


# ── Task lookup by function name ─────────────────────────────────────────────

_NAME_TASK_RULES = [
    (r'\bflatten\b', 'flatten'),
    (r'\bchunk', 'chunk_list'),
    (r'\bdedup|deduplicate|unique', 'dedup'),
    (r'\btranspose\b', 'transpose_matrix'),
    (r'\bslug', 'slugify'),
    (r'\bcaesar\b|\brot13|\brot47', 'caesar_cipher'),
    (r'\bpassword', 'password_gen'),
    (r'\bshuffle\b', 'shuffle_list'),
    (r'\bmemoiz', 'memoize'),
    (r'\bretry\b', 'retry_backoff'),
    (r'\bpretty.*json|json.*pretty', 'json_pretty'),
    (r'\bword.*count|count.*word', 'count_words'),
    (r'\breverse.*(?:str|char)', 'reverse_string'),
    (r'\breverse', 'reverse_array'),
    (r'\bprime', 'prime'),
    (r'\bfactorial|\bfact\b', 'factorial'),
    (r'\bfib', 'fibonacci'),
    (r'\bfizz', 'fizzbuzz'),
    (r'\bgcd\b|\bhcf\b', 'gcd'),
    (r'\bbinary.*search', 'binary_search'),
    (r'\bpalindrom', 'palindrome_string'),
    (r'\banagram', 'anagram'),
    (r'\bmerge', 'merge_sorted'),
    (r'\bsort', 'sort_list'),
    (r'\bfrequent', 'most_frequent'),
    (r'\boccurrence', 'count_occurrences'),
]


def _task_by_name(name: str) -> "str | None":
    low = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', name).lower()
    low = low.replace('_', ' ').replace('-', ' ')
    for rule, task in _NAME_TASK_RULES:
        if re.search(rule, low):
            return task
    return None


# ── Module-state awareness -------------------------------------------------

_CONTAINER_RE = re.compile(
    r'^(?:const\s+|let\s+|var\s+)?([A-Za-z_]\w*)\s*=\s*(\[\]|\{\}|set\(\))\s*;?$',
    re.MULTILINE)

_STATE_GROUPS = [
    {'todo', 'task', 'tasks', 'remaining', 'open', 'pending', 'backlog',
     'queue', 'waiting', 'unfinished', 'active', 'work', 'jobs'},
    {'done', 'finished', 'completed', 'complete', 'resolved', 'closed',
     'archived', 'processed', 'cleared', 'removed'},
    {'item', 'items', 'cart', 'entries', 'rows', 'records', 'elements',
     'data', 'lines'},
]


def _module_containers(code: str) -> dict:
    """Module-level container names -> kind ('list' | 'dict' | 'set')."""
    out = {}
    for m in _CONTAINER_RE.finditer(code):
        name, init = m.group(1), m.group(2)
        kind = {'[]': 'list', '{}': 'dict', 'set()': 'set'}[init]
        out[name] = kind
    return out


def _pick_container(noun: str, containers: dict) -> "str | None":
    """Best module-level container for a noun, or None.

    Exact substring wins, then a shared synonym group. With several
    containers and no match we return None so the caller can scaffold
    honestly instead of guessing wrong.
    """
    if not containers:
        return None
    keys = list(containers)
    if len(keys) == 1:
        return keys[0]
    nl = noun.lower()
    for k in keys:
        kl = k.lower()
        if kl and (nl in kl or kl in nl):
            return k
    for k in keys:
        kl = k.lower()
        for group in _STATE_GROUPS:
            if kl in group and nl in group:
                return k
    return None


def _lookup_container(name: str, containers: dict) -> "str | None":
    """The real container key for a (possibly different-case) name."""
    if name in containers:
        return name
    nl = name.lower()
    for k in containers:
        if k.lower() == nl:
            return k
    return None


# ── Name-verb recipes that use module-level containers ------------------------

_MODULE_VERB_RE = re.compile(
    r'^(add|append|push|insert|remove|delete|pop|clear|reset|empty|wipe|'
    r'count|num|number|size|len|total|sum|avg|average|mean|'
    r'list|show|print|dump|is|has|contains|sort|sorted)'
    r'(_|(?=[A-Z0-9])|$)')


def _module_body(lang: str, verb: str, c: str,
                 params: list) -> "list[str] | None":
    """Body for a verb+container recipe (module-level state)."""
    if lang == 'python':
        if verb in ('add', 'append', 'push', 'insert'):
            return None if not params else [f'{c}.append({params[0]})']
        if verb in ('remove', 'delete'):
            return None if not params else [f'{c}.remove({params[0]})']
        if verb == 'pop':
            return None if not params else [f'{c}.pop({params[0]})']
        if verb in ('clear', 'reset', 'empty', 'wipe'):
            return [f'{c}.clear()']
        if verb in ('count', 'num', 'number', 'size', 'len'):
            return [f'return len({c})']
        if verb in ('total', 'sum'):
            return [f'return sum({c})', f'# Assumes {c} holds numbers']
        if verb in ('avg', 'average', 'mean'):
            return [f'return sum({c}) / len({c})', f'# Assumes {c} holds numbers']
        if verb in ('list', 'show', 'print', 'dump'):
            return [f'for item in {c}:', '    print(item)']
        if verb in ('is', 'has', 'contains'):
            return None if not params else [f'return {params[0]} in {c}']
        if verb in ('sort', 'sorted'):
            return [f'return sorted({c})']
        return None
    # javascript / typescript
    if verb in ('add', 'append', 'push', 'insert'):
        if not params:
            return None
        if len(params) >= 2:
            obj = ', '.join(params)
            return [f'{c}.push({{ {obj} }});']
        return [f'{c}.push({params[0]});']
    if verb in ('remove', 'delete'):
        return None if not params else [
            f'const i = {c}.indexOf({params[0]});',
            f'if (i !== -1) {c}.splice(i, 1);']
    if verb == 'pop':
        return [f'return {c}.pop();']
    if verb in ('clear', 'reset', 'empty', 'wipe'):
        return [f'{c}.length = 0;']
    if verb in ('count', 'num', 'number', 'size', 'len'):
        return [f'return {c}.length;']
    if verb in ('total', 'sum'):
        return [f'return {c}.reduce((acc, item) => acc + item.price, 0);']
    if verb in ('avg', 'average', 'mean'):
        return [f'return {c}.reduce((acc, item) => acc + item.price, 0) / {c}.length;']
    if verb in ('list', 'show', 'print', 'dump'):
        return [f'for (const item of {c}) {{', '  console.log(item);', '}']
    if verb in ('is', 'has', 'contains'):
        return None if not params else [f'return {c}.includes({params[0]});']
    if verb in ('sort', 'sorted'):
        return [f'return [...{c}].sort();']
    return None


def _module_recipe_body(sig: dict, lang: str, containers: dict) -> "tuple[list[str], str] | None":
    """Name-verb recipes that use module-level containers.

    ``add_task(text)`` -> ``TODO.append(text)`` when the buffer defines
    ``TODO = []``; ``count_remaining()`` -> ``len(TODO)``; ``itemCount()``
    -> ``cart.length``. Returns (body, note) or None (honest scaffold).
    """
    if lang not in ('python', 'javascript', 'typescript') or not containers:
        return None
    m = _MODULE_VERB_RE.match(sig['name'])
    if not m:
        return None
    verb = m.group(1).lower()
    noun = sig['name'][m.end():].strip('_')
    noun = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', noun).lower()
    params = [p[0] for p in sig['params']]
    if not noun:
        c = next(iter(containers))
    else:
        c = _pick_container(noun, containers)
        if c is None:
            return None
    body = _module_body(lang, verb, c, params)
    if body is None:
        return None
    note = (f"Body built from the function name and the module-level `{c}` "
            f"container in this buffer.")
    if verb in ('total', 'sum', 'avg', 'average', 'mean'):
        if lang == 'python':
            note = (f"Body built from the function name: sums the module-level "
                    f"`{c}` list (assumed to hold numbers).")
        else:
            note = (f"Body built from the function name: sums the `price` of "
                    f"each entry in the module-level `{c}` list (assumed to "
                    f"be objects with a numeric `price` field).")
    return body, note


# ── Instruction recipes that need buffer context ------------------------------

def _instruction_recipe_body(sig: dict, lang: str, inst: str,
                             containers: dict, defs: list) -> "tuple[list[str], str] | None":
    """Instruction-driven recipes that use the buffer's state.

    Handles the everyday TODO-comment phrasing: "move X from A to B",
    "average of rows[*][key]", "group X by Y and sum Z", "reduce by a
    percent", "total number of ...", CSV/JSON readers. Returns
    (body, note) or None.
    """
    if lang not in ('python', 'javascript', 'typescript'):
        return None
    params = [p[0] for p in sig['params']]
    inst_l = inst.lower()
    py = lang == 'python'

    # 1. "move the <thing> at <idx> from A to B"
    m1 = re.search(r'\bmove\s+(?:the\s+)?(\w+)', inst_l)
    m2 = re.search(r'\bfrom\s+(\w+)\s+to\s+(\w+)\b', inst_l)
    if m1 and m2 and params:
        a = _lookup_container(m2.group(1), containers)
        b = _lookup_container(m2.group(2), containers)
        if a and b:
            thing = m1.group(1)
            if py:
                body = [f'{thing} = {a}.pop({params[0]})',
                        f'{b}.append({thing})']
            else:
                body = [f'const {thing} = {a}.splice({params[0]}, 1)[0];',
                        f'{b}.push({thing});']
            note = (f"Moves an item between the module-level `{a}` and `{b}` "
                    f"lists, as the instruction says.")
            return body, note

    # 2. "average of <coll>[*][<key>]"
    m = re.search(r'\baverage\s+of\s+(\w+)(?:\[\*\]|\[\])?\[(\w+)\]', inst_l)
    if m and m.group(1) in params:
        coll, k = m.group(1), m.group(2)
        if py:
            body = [f'return sum(r[{k}] for r in {coll}) / len({coll})']
        else:
            body = [f'return {coll}.reduce((acc, r) => acc + r[{k}], 0) / {coll}.length;']
        note = f"Averages the `{k}` field across `{coll}`, per the instruction."
        return body, note

    # 3. "group <coll> by <gk> and sum <vk> per group"
    m = re.search(r'\bgroup\s+(?:the\s+)?(\w+)\s+by\s+(\w+)\s+and\s+'
                  r'(?:sum|total)\s+(\w+)', inst_l)
    if m and m.group(1) in params:
        coll, gk, vk = m.group(1), m.group(2), m.group(3)
        if py:
            body = ['out = {}',
                    f'for r in {coll}:',
                    f'    out[r[{gk}]] = out.get(r[{gk}], 0) + r[{vk}]',
                    'return out']
        else:
            body = ['const out = {};',
                    f'for (const r of {coll}) {{',
                    f'  out[r[{gk}]] = (out[r[{gk}]] || 0) + r[{vk}];',
                    '}',
                    'return out;']
        note = (f"Groups `{coll}` by `{gk}` and sums `{vk}` per group, "
                f"per the instruction.")
        return body, note

    # 4. generic "group <coll> by <key>" (bucket grouping)
    m = re.search(r'\bgroup\s+(?:the\s+)?(\w+)\s+by\s+(?:the\s+)?(\w+)\b', inst_l)
    if m and m.group(1) in params:
        coll, k = m.group(1), m.group(2)
        if py:
            body = ['out = {}',
                    f'for item in {coll}:',
                    f'    out.setdefault(item[{k}], []).append(item)',
                    'return out']
        else:
            body = ['const out = {};',
                    f'for (const item of {coll}) {{',
                    f'  const g = {k}(item);',
                    '  (out[g] = out[g] || []).push(item);',
                    '}',
                    'return out;']
        note = (f"Buckets `{coll}` by `{k}`" +
                ("(called as a function)" if not py else "(used as a field)") +
                ", per the instruction.")
        return body, note

    # 5. "reduce the total by the given percent"
    m = re.search(r'\b(?:reduce|lower|decrease|cut)\b.*\bby\b.*\b'
                  r'(?:percent|percentage|pct)\b', inst_l)
    if m and params:
        p = params[0]
        fn = next((d for d in defs if d in ('total', 'sum')), None)
        if fn:
            body = ([f'return {fn}() * (1 - {p} / 100)'] if py else
                    [f'return {fn}() * (1 - {p} / 100);'])
            note = (f"Applies the `{p}` discount on top of the `{fn}()` "
                    f"defined in this buffer.")
            return body, note
        if containers:
            c = next(iter(containers))
            if py:
                body = [f'return sum({c}) * (1 - {p} / 100)',
                        f'# Assumes {c} holds numbers']
            else:
                body = [f'return {c}.reduce((acc, item) => acc + item.price, 0) * (1 - {p} / 100);']
            note = (f"Discount applied to the sum of the module-level `{c}` "
                    f"list.")
            return body, note

    # 6. "total number of <noun>" / "how many ..." -> len(container)
    m = re.search(r'\b(?:total|number|count)\s+number\s+of\s+(\w+)'
                  r'|\bhow\s+many\b', inst_l)
    if m:
        noun = m.group(1) if m.lastindex and m.group(1) else None
        c = _pick_container(noun, containers) if noun else \
            (next(iter(containers)) if containers else None)
        if c:
            body = ([f'return len({c})'] if py else [f'return {c}.length;'])
            note = (f"Counts the module-level `{c}` list, per the "
                    f"instruction.")
            return body, note

    # 7. CSV reader -> list of dicts
    if py and re.search(r'\bcsv\b', inst_l) and re.search(r'\bdict', inst_l) \
            and params:
        body = [f'with open({params[0]}) as f:',
                '    return list(csv.DictReader(f))']
        note = ("Uses the csv module's DictReader, so the header row "
                "becomes the dict keys.")
        return body, note

    # 8. JSON reader
    if py and re.search(r'\bjson\b', inst_l) and re.search(r'\b(?:load|read|parse)\b', inst_l) \
            and params:
        body = [f'with open({params[0]}) as f:',
                '    return json.load(f)']
        note = "Uses json.load to read the whole file."
        return body, note

    return None


# ── Extract the first function definition from a generated program ──────────

_DEF_START = {
    'python': re.compile(r'^(?:async\s+)?def\s+\w+\s*\('),
    'javascript': re.compile(r'^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+\w+\s*\(|'
                             r'^(?:export\s+)?(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>'),
    'typescript': re.compile(r'^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+\w+(?:<[^>]*>)?\s*\(|'
                             r'^(?:export\s+)?(?:const|let|var)\s+\w+\s*=\s*(?:<[^>]*>)?\s*(?:async\s*)?\([^)]*\)\s*=>'),
    'go': re.compile(r'^func\s+\w+\s*\('),
    'rust': re.compile(r'^(?:pub\s+)?(?:async\s+)?fn\s+\w+\s*\('),
    'java': re.compile(r'^\s*(?:public|private|protected|static|final|abstract|\s)*\s*'
                       r'[\w<>\[\],\s]+\s+\w+\s*\('),
    'c++': re.compile(r'^\s*(?:virtual\s+)?[\w:<>,&*\s]+\s+\w+\s*\([^;]*\)\s*(?:const\s*)?\{'),
    'c#': re.compile(r'^\s*(?:public|private|protected|internal|static|async|\s)*\s*'
                     r'[\w<>\[\],\s]+\s+\w+\s*\('),
}


def first_function_def(text: str, lang: str) -> "tuple[str, list[str]] | None":
    """Extract (def_line, body_lines) of the first top-level function.

    Stops at the function's end: a matching closing brace for braced
    languages, or the next top-level statement / example block for Python.
    """
    lines = text.split('\n')
    start_pat = _DEF_START.get(lang)
    if not start_pat:
        return None
    start = None
    for i, ln in enumerate(lines):
        if ln.strip() and not ln.startswith((' ', '\t')) and start_pat.search(ln):
            start = i
            break
    if start is None:
        return None
    def_line = lines[start]
    if lang == 'python':
        body: list[str] = []
        for ln in lines[start + 1:]:
            if not ln.strip():
                body.append(ln)
                continue
            if not ln.startswith((' ', '\t')):
                # next top-level statement ends the function (examples, etc.)
                break
            body.append(ln)
        while body and not body[-1].strip():
            body.pop()
        return def_line, body
    # brace-counted languages
    depth = def_line.count('{') - def_line.count('}')
    body = []
    for ln in lines[start + 1:]:
        body.append(ln)
        depth += ln.count('{') - ln.count('}')
        if depth <= 0:
            # drop the closing brace line itself — the harness inserts the
            # body inside the existing braces, so we must not duplicate it
            if body and body[-1].strip() in ('}', '};'):
                body.pop()
            break
    return def_line, body


# ── Generic scaffold bodies (honest fallback) ───────────────────────────────

_BOOL_WORDS = {'bool', 'boolean'}
_INT_WORDS = {'int', 'integer', 'i32', 'i64', 'u32', 'u64', 'long', 'size_t'}
_FLOAT_WORDS = {'float', 'double', 'f32', 'f64', 'decimal'}
_STR_WORDS = {'str', 'string', 'char'}


def _scaffold_body(sig: dict, lang: str) -> tuple[list[str], list[str]]:
    """A minimal, honest body for a signature we can't infer logic from.

    Returns (body_lines, notes). The note always tells the user the body
    is a scaffold and what would unlock a real implementation.
    """
    ret = sig['ret'].lower()
    params = sig['params']
    note = ("I couldn't infer the logic from the signature alone, so this is "
            "honest scaffolding. Tell me what the function should do (or give "
            "the function a descriptive name like ``reverse_string``) and I'll "
            "fill in the real body.")
    if lang == 'python':
        if any(w in ret for w in _BOOL_WORDS):
            return ['return False'], [note]
        if any(w in ret for w in _INT_WORDS):
            return ['return 0'], [note]
        if any(w in ret for w in _FLOAT_WORDS):
            return ['return 0.0'], [note]
        if any(w in ret for w in _STR_WORDS):
            return ['return ""'], [note]
        if 'list' in ret or 'dict' in ret or 'tuple' in ret:
            return [f'return {ret.split("[")[0].strip() or "[]"}()'], [note]
        if not ret or ret == 'none':
            return ['pass  # TODO: implement'], [note]
        if params:
            return [f'return {params[0][0]}'], [note]
        return ['pass  # TODO: implement'], [note]
    # braced languages: return default by type, else TODO comment
    if any(w in ret for w in _BOOL_WORDS):
        return ['return false;'], [note]
    if any(w in ret for w in _INT_WORDS | _FLOAT_WORDS):
        return ['return 0;'], [note]
    if any(w in ret for w in _STR_WORDS):
        return ['return "";'], [note]
    if 'void' in ret or not ret:
        return ['// TODO: implement'], [note]
    if params:
        return [f'return {params[0][0]};'], [note]
    return ['// TODO: implement'], [note]


def _rename_identifiers(text: str, old: str, new: str) -> str:
    """Word-boundary identifier rename (safe for snake/camel case names)."""
    if old == new or not old:
        return text
    return re.sub(r'(?<![A-Za-z0-9_])' + re.escape(old) + r'(?![A-Za-z0-9_])',
                  new, text)


def _strip_leading_docstring(body: list[str]) -> list[str]:
    """Drop a template's own leading docstring before reuse.

    The user's buffer already carries the spec (their docstring or TODO
    comment), so inserting the template's docstring would duplicate it.
    """
    out = list(body)
    while out:
        s = out[0].strip()
        if s.startswith(('"""', "'''")):
            marker = s[:3]
            while out and marker not in out[0]:
                out.pop(0)
            if out:
                out.pop(0)
        elif s.startswith(('/*', '/**')):
            while out and '*/' not in out[0]:
                out.pop(0)
            if out:
                out.pop(0)
        else:
            break
    return out


def _little_task_body(sig: dict, lang: str,
                      instruction: str) -> "list[str] | None":
    """Tiny inline recipes for short, unambiguous instructions.

    Only fires when the instruction clearly names one of these operations and
    the signature has the matching parameter shape — otherwise None (caller
    falls through to scaffolding).
    """
    inst = instruction.lower()
    params = sig['params']
    pnames = [p[0] for p in params]
    if lang == 'python':
        if re.search(r'\b(?:greeting|hello|welcome|greet)\b', inst) and pnames:
            return [f'return f"Hello, {{{pnames[0]}}}!"']
        if len(pnames) >= 2:
            a, b = pnames[0], pnames[1]
            if re.search(r'\b(?:add|sum|plus)\b', inst):
                return [f'return {a} + {b}']
            if re.search(r'\b(?:subtract|minus|difference)\b', inst):
                return [f'return {a} - {b}']
            if re.search(r'\b(?:multiply|product|times)\b', inst):
                return [f'return {a} * {b}']
            if re.search(r'\b(?:divide|quotient)\b', inst):
                return [f'return {a} / {b}']
            if re.search(r'\b(?:max|maximum|larger)\b', inst):
                return [f'return max({a}, {b})']
            if re.search(r'\b(?:min|minimum|smaller)\b', inst):
                return [f'return min({a}, {b})']
        if pnames and re.search(r'\b(?:length|count)\b.*\b(?:of|items|list|string|elements)\b', inst):
            return [f'return len({pnames[0]})']
        return None
    if len(pnames) >= 2:
        a, b = pnames[0], pnames[1]
        if re.search(r'\b(?:add|sum|plus)\b', inst):
            return [f'return {a} + {b};']
        if re.search(r'\b(?:subtract|minus|difference)\b', inst):
            return [f'return {a} - {b};']
        if re.search(r'\b(?:multiply|product|times)\b', inst):
            return [f'return {a} * {b};']
        if re.search(r'\b(?:divide|quotient)\b', inst):
            return [f'return {a} / {b};']
        if re.search(r'\b(?:max|maximum|larger)\b', inst):
            return [f'return Math.max({a}, {b});']
        if re.search(r'\b(?:min|minimum|smaller)\b', inst):
            return [f'return Math.min({a}, {b});']
    if pnames and re.search(r'\b(?:greeting|hello|welcome|greet)\b', inst):
        return [f'return `Hello, ${{{pnames[0]}}}!`;']
    return None


def _align_params(def_line: str, body: list[str], sig: dict, lang: str) -> list[str]:
    """Rename the template's parameter names to match the user's signature.

    The curated templates use their own param names (``text``, ``items``, …)
    while the user's signature may call them something else (``title``,
    ``orders``, …). When the arity matches, rename by position so the body
    actually compiles against the signature.
    """
    tpl = _parse_signature(def_line, lang)
    if not tpl:
        return body
    sig_params = [p[0] for p in sig['params']]
    tpl_params = [p[0] for p in tpl['params']]
    if len(sig_params) != len(tpl_params):
        return body
    out = body
    for tp, sp in zip(tpl_params, sig_params):
        if tp != sp:
            out = [_rename_identifiers(b, tp, sp) for b in out]
    return out


def _name_recipe_body(sig: dict, lang: str) -> "list[str] | None":
    """Small name-prefix recipes: total/sum/count/avg/max/min + a collection.

    Fires only when the function name clearly names the operation and there
    is a parameter to operate on. The note the caller adds says what was
    assumed (e.g. the parameter is a list of numbers).
    """
    name = sig['name'].lower()
    params = [p[0] for p in sig['params']]
    if not params:
        return None
    p = params[-1]
    if lang == 'python':
        if re.match(r'^(total|sum)(?:_|$)', name):
            return [f'return sum({p})', f'# Assumes {p} is a list of numbers']
        if re.match(r'^count(?:_|$)', name):
            return [f'return len({p})']
        if re.match(r'^(avg|average|mean)(?:_|$)', name):
            return [f'return sum({p}) / len({p})',
                    f'# Assumes {p} is a list of numbers']
        if re.match(r'^max(?:_|$)', name):
            return [f'return max({p})']
        if re.match(r'^min(?:_|$)', name):
            return [f'return min({p})']
        if re.match(r'^(?:top|best|largest|highest)(?:_|$)', name) \
                and len(sig['params']) >= 2:
            coll = sig['params'][0][0]
            k = sig['params'][1][0]
            n = sig['params'][2][0] if len(sig['params']) >= 3 else 'n'
            return [f'return sorted({coll}, key=lambda r: r[{k}], reverse=True)[:{n}]']
        return None
    if re.match(r'^(total|sum)(?:_|$)', name):
        return [f'return {p}.reduce((acc, x) => acc + x, 0);']
    if re.match(r'^count(?:_|$)', name):
        return [f'return {p}.length;']
    if re.match(r'^(avg|average|mean)(?:_|$)', name):
        return [f'return {p}.reduce((acc, x) => acc + x, 0) / {p}.length;']
    if re.match(r'^max(?:_|$)', name):
        return [f'return Math.max(...{p});']
    if re.match(r'^min(?:_|$)', name):
        return [f'return Math.min(...{p});']
    if re.match(r'^(?:top|best|largest|highest)(?:_|$)', name) \
            and len(sig['params']) >= 2:
        coll = sig['params'][0][0]
        k = sig['params'][1][0]
        n = sig['params'][2][0] if len(sig['params']) >= 3 else 'n'
        return [f'return [...{coll}].sort((a, b) => b[{k}] - a[{k}]).slice(0, {n});']
    return None


def _body_from_signature(sig: dict, lang: str,
                         instruction: str = "",
                         code: str = "") -> tuple[list[str], list[str]]:
    """Produce the body for a parsed signature.

    Priority: (1) the instruction maps to a known task whose template has
    the same arity; (2) the function name maps to a known task; (3) the
    instruction maps to a buffer-aware recipe (module lists, defined
    functions); (4) the function name maps to a module-level container;
    (5) name-prefix recipes; (6) free-form generation; (7) tiny inline
    recipes; (8) an honest scaffold.
    """
    name = sig['name']
    notes: list[str] = []
    containers = _module_containers(code) if code else {}
    defs = [n for _, n in extract_defs(code, lang)] if code else []
    sig_arity = len(sig['params'])

    def _from_template(task: str, why: str) -> "tuple[list[str], list[str]] | None":
        if not (_CODE.get(task) and lang in _CODE[task]):
            return None
        extracted = first_function_def(_CODE[task][lang], lang)
        if not extracted:
            return None
        _def_line, body = extracted
        body = _strip_leading_docstring(body)
        tpl = _parse_signature(_def_line, lang)
        if tpl and len(tpl['params']) != sig_arity:
            # a template with different params would reference names the
            # user's signature doesn't have - refuse rather than emit
            # plausible-looking broken code
            return None
        orig_name = _def_line.split('(')[0].split()[-1].strip()
        body = [_rename_identifiers(b, orig_name, name) for b in body]
        body = _align_params(_def_line, body, sig, lang)
        notes.append(why)
        return body, notes

    # 1. instruction -> known task template (arity-guarded)
    if instruction and detect_task:
        task = detect_task(instruction)
        if task:
            got = _from_template(task, f"Body generated from the '{task}' "
                                      f"recipe - parameter names were aligned "
                                      f"to your signature.")
            if got:
                return got

    # 2. function name -> known task template
    task = _task_by_name(name)
    if task:
        got = _from_template(task, f"Recognized '{name}' as the '{task}' task "
                                   f"and reused the curated implementation "
                                   f"for {lang}.")
        if got:
            return got

    # 3. instruction -> buffer-aware recipe
    if instruction:
        got = _instruction_recipe_body(sig, lang, instruction, containers, defs)
        if got:
            body, note = got
            notes.append(note)
            return body, notes

    # 4. name -> module-level container recipe
    got = _module_recipe_body(sig, lang, containers)
    if got:
        body, note = got
        notes.append(note)
        return body, notes

    # 5. name-prefix recipes: total_revenue / count_items / avg_price ...
    recipe = _name_recipe_body(sig, lang)
    if recipe is not None:
        notes.append("Body built from the function name - the last parameter "
                     "was treated as the collection to operate on.")
        return recipe, notes

    # 6. instruction as a free-form generation attempt (any language)
    if instruction and generate_code:
        gen = generate_code(instruction + (f' in {lang}' if lang != 'python' else ''))
        if gen:
            extracted = first_function_def(gen, lang)
            if extracted:
                _def_line, body = extracted
                body = _strip_leading_docstring(body)
                tpl = _parse_signature(_def_line, lang)
                if tpl and len(tpl['params']) != sig_arity:
                    body = []
                else:
                    orig_name = _def_line.split('(')[0].split()[-1].strip()
                    body = [_rename_identifiers(b, orig_name, name) for b in body]
                    body = _align_params(_def_line, body, sig, lang)
                if body:
                    notes.append("Body generated from your instruction.")
                    return body, notes

    # 7. tiny inline recipes for short, unambiguous instructions
    little = _little_task_body(sig, lang, instruction)
    if little is not None:
        notes.append("Body built from a small inline recipe.")
        return little, notes

    # 8. honest scaffold
    return _scaffold_body(sig, lang)


# ── Fill-in point detection ─────────────────────────────────────────────────

def _marker_lines(code: str) -> list[int]:
    """0-based line indexes that are fill-in markers.

    A marker is a line whose content is exactly '...', a bare 'pass'
    inside a function, an empty '{ }' block line, a '// ...'/'# ...'
    ellipsis comment, or a `throw new Error(...)` stub (JS/TS).
    """
    lines = code.split('\n')
    out = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if (s == '...' or s == 'pass' or s in ('{}', '{ }', '{};')
                or re.match(r'^(?:#|//)\s*\.\.\.$', s)
                or re.match(r'^throw\s+new\s+Error\([^)]*\)\s*;?$', s)):
            out.append(i)
    return out


def _instruction_at(code: str, line_idx: int) -> str:
    """Instruction embedded in a marker line or the comment above it.

    Handles '# TODO: do X', '// do X', and the plain '...' marker.
    """
    lines = code.split('\n')
    for idx in (line_idx, line_idx - 1):
        if not (0 <= idx < len(lines)):
            continue
        s = lines[idx].strip()
        m = re.match(r'^(?:#|//)\s*(?:\.\.\.\s*)?(?:TODO|FIXME|todo|fixme)?:?\s*(.+)$', s)
        if m and s != '...':
            return m.group(1).strip()
    return ''


def _enclosing_signature(code: str, line_idx: int,
                         lang: str) -> "dict | None":
    """The signature whose body contains line_idx (or the def just before it)."""
    lines = code.split('\n')
    best = None
    for i, ln in enumerate(lines):
        if i > line_idx:
            break
        sig = _parse_signature(ln, lang)
        if sig:
            best = sig
            best['def_line_idx'] = i
    return best


def _docstring_at(code: str, line_idx: int,
                  def_line_idx: int) -> str:
    """Instruction hidden in the function's docstring (before the marker).

    The docstring often carries the spec ('Read a CSV file into a list of
    dicts ...') when there is no ``# TODO:`` comment, so it is treated as
    the instruction.
    """
    lines = code.split('\n')
    for i in range(line_idx - 1, def_line_idx, -1):
        s = lines[i].strip()
        if not s:
            continue
        m = re.match(r'^(?:"""|\'\'\'|/\*\*?|//|#)\s*(.+?)\s*'
                     r'("""|\'\'\'|\*/)?$', s)
        if m:
            body = m.group(1).strip().strip('"\'')
            if len(body) > 4:
                return body
        break
    return ''


# ── Public API ──────────────────────────────────────────────────────────────

def complete_buffer(code: str, instruction: str = "",
                    cursor_pos: "int | None" = None,
                    filename: str = "") -> dict:
    """Fill in code at a marker in the buffer.

    Args:
        code: the full buffer text.
        instruction: what the code should do (optional; may also live in a
            ``# TODO:`` comment on the marker line).
        cursor_pos: 0-based line index of the fill-in point. When None the
            first ``...`` / ``pass`` marker is used.
        filename: used for language detection.

    Returns::

        {
          'text':   exact text to insert (already indented for the scope),
          'lang':   detected language,
          'notes':  human-readable assumptions,
          'changed': bool,
          'context': buffer analysis (imports/defs/indent),
          'replace_line': 0-based line index the insertion replaces (or None),
        }

    Deterministic and offline.
    """
    lang = detect_lang(code, filename)
    ctx = analyze_buffer(code, filename)

    # resolve the fill-in point
    marker = cursor_pos
    if marker is None:
        markers = _marker_lines(code)
        if markers:
            marker = markers[0]
    if marker is None:
        return {
            'text': '', 'lang': lang, 'notes': [],
            'changed': False, 'context': ctx, 'replace_line': None,
        }

    sig = _enclosing_signature(code, marker, lang)
    if sig is None:
        return {
            'text': '', 'lang': lang,
            'notes': [("I couldn't find a function signature around the marker — "
                       "put the fill-in marker inside a function body.")],
            'changed': False, 'context': ctx, 'replace_line': marker,
        }

    embedded = _instruction_at(code, marker)
    doc = ''
    if sig.get('def_line_idx') is not None:
        doc = _docstring_at(code, marker, sig['def_line_idx'])
    passed = instruction.strip()
    if embedded:
        inst = embedded
    elif doc and _is_generic_instruction(passed):
        # a generic "complete the function" must not override the spec the
        # developer already wrote into the buffer's docstring
        inst = doc
    else:
        inst = passed or doc
    body, notes = _body_from_signature(sig, lang, inst, code)

    # re-indent the body to the scope's indent + one unit. Template bodies
    # carry their own indentation, so compute each line's *relative* level
    # and rebuild it with the buffer's indent unit (spaces or tabs).
    indent_kind, unit = ctx['indent']['kind'], ctx['indent']['unit']
    base = sig.get('indent', 0)
    step = unit if indent_kind == 'spaces' else 1
    prefix = ' ' * (base + step) if indent_kind == 'spaces' else '\t' * (base + step)

    indents = [len(ln) - len(ln.lstrip(' \t')) for ln in body if ln.strip()]
    src_base = min(indents) if indents else 0
    diffs = [i - src_base for i in indents if i - src_base > 0]
    from collections import Counter as _C
    src_unit = (_C(diffs).most_common(1)[0][0]) if diffs else 4
    if src_unit <= 0:
        src_unit = 4

    out_lines = []
    for ln in body:
        if not ln.strip():
            out_lines.append('')
            continue
        cur = len(ln) - len(ln.lstrip(' \t'))
        level = max(round((cur - src_base) / src_unit), 0)
        content = ln.strip()
        if indent_kind == 'spaces':
            out_lines.append(prefix + ' ' * (step * level) + content)
        else:
            out_lines.append(prefix + '\t' * level + content)
    text = '\n'.join(out_lines)

    # context notes: only flag imports the generated body actually calls
    missing_imports = []
    if lang == 'python':
        body_text = '\n'.join(ln for ln in body)
        for mod in ('re', 'random', 'collections', 'json', 'math', 'secrets',
                    'functools', 'time', 'string'):
            if (re.search(r'\b' + mod + r'\.', body_text)
                    and mod not in ctx['imports']):
                missing_imports.append(mod)
    if missing_imports:
        notes.append("This body uses `" + ", ".join(missing_imports) +
                     "` — add the import at the top of the file (it wasn't imported yet).")

    return {
        'text': text,
        'lang': lang,
        'notes': notes,
        'changed': bool(body),
        'context': ctx,
        'replace_line': marker,
    }


def fill_function(code: str, func_name: "str | None" = None,
                  instruction: str = "", filename: str = "") -> dict:
    """Fill the body of a named function (or the last function) in the buffer.

    Convenience wrapper over :func:`complete_buffer` for harnesses that know
    which function they're editing.
    """
    if func_name:
        lines = code.split('\n')
        for i, ln in enumerate(lines):
            sig = _parse_signature(ln, detect_lang(code, filename))
            if sig and sig['name'] == func_name:
                return complete_buffer(code, instruction, cursor_pos=i + 1,
                                       filename=filename)
    # last function in the buffer
    lang = detect_lang(code, filename)
    last_def = None
    for i, ln in enumerate(code.split('\n')):
        if _parse_signature(ln, lang):
            last_def = i
    if last_def is not None:
        return complete_buffer(code, instruction, cursor_pos=last_def + 1,
                               filename=filename)
    return complete_buffer(code, instruction, filename=filename)


def _apply_insertion(code: str, text: str, line_idx: int) -> str:
    """Replace the marker line at `line_idx` with the (already indented) text."""
    lines = code.split('\n')
    if not (0 <= line_idx < len(lines)):
        return code
    lines[line_idx] = text
    return '\n'.join(lines)


# ── Query-level integration (chat / CLI) ────────────────────────────────────

_FILL_VERBS_RE = re.compile(
    r'complete|fill\s*(?:in|out)?|finish|implement\s+(?:the\s+)?'
    r'(?:body|function|method|logic)|what\s+should\s+(?:the\s+)?'
    r'(?:body|function)|write\s+the\s+body|todo',
    re.IGNORECASE,
)

_FILLER_WORDS = {'complete', 'finish', 'fill', 'out', 'the', 'this', 'that',
                 'function', 'method', 'logic', 'body', 'code', 'script',
                 'please', 'for', 'me', 'in', 'up', 'with', 'its', 'their'}


def _is_generic_instruction(inst: str) -> bool:
    """True when the instruction is just a fill-in request, no real spec.

    "complete the function" / "fill this in" are generic; "sum the two
    numbers" / "implement a binary search" are not. A generic passed
    instruction must not override the spec embedded in the buffer (a
    docstring or TODO comment).
    """
    low = inst.lower()
    if not _FILL_VERBS_RE.search(low):
        return False
    words = re.findall(r'[a-z]{3,}', low)
    return not [w for w in words if w not in _FILLER_WORDS]


def detect_fill_request(query: str) -> bool:
    """True when the query is a fill-in request (empty body + a fill verb)."""
    q = query.strip()
    if len(q) < 12:
        return False
    has_marker = False
    code = None
    m = re.search(r'```(?:\w+)?\n(.*?)```', q, re.DOTALL)
    if m:
        code = m.group(1)
        has_marker = bool(_marker_lines(code))
    else:
        # code after a colon: "...: def add(a, b):\n    ..."
        cm = re.match(r'^(.{2,120}?):\s*(.+)$', q, re.DOTALL)
        if cm and re.search(r'def\s+\w+\s*\(|function\s+\w+\s*\(', cm.group(2)):
            code = cm.group(2)
            has_marker = bool(_marker_lines(code))
    if not has_marker:
        return False
    q_low = q.lower()
    if _FILL_VERBS_RE.search(q_low):
        return True
    # a bare code block with an explicit '...' marker and no other instruction
    return code is not None and '...' in code and len(q) < 200


def _last_edit_with_marker() -> "str | None":
    """The last code the user pasted/edited, if it still has a fill-in marker."""
    try:
        from cos.text_editor import get_last_edit_content, get_last_edit_kind
        if get_last_edit_kind() == 'code':
            content = get_last_edit_content()
            if content and _marker_lines(content):
                return content
    except Exception:
        pass
    return None


def fill_in(query: str) -> str:
    """Answer a fill-in request as chat text (for process_query / CLI).

    Returns the edited buffer (insertion applied) inside a code fence, plus
    the notes. Honest message when nothing could be filled.
    """
    q = query.strip()

    # follow-up form: "complete the last code" / "fill in the last function"
    last = _last_edit_with_marker()
    if last and re.search(r'\b(?:complete|fill\s*in|finish)\s+(?:the\s+)?'
                          r'(?:last|previous)\s+(?:code|function|script)\b',
                          q, re.IGNORECASE):
        code, instruction = last, ''
    else:
        try:
            from cos.code_transformer import extract_code_from_query
            head, code = extract_code_from_query(q)
        except Exception:
            head, code = '', q
        instruction = head

    if not code:
        return ("I need the code to fill in. Paste a function with an empty "
                "body — a `...` marker, a bare `pass`, or an empty `{ }` — "
                "and tell me what it should do.")
    result = complete_buffer(code, instruction=instruction)
    if not result['changed']:
        notes = result['notes']
        return ("I couldn't fill anything in there. " +
                (" ".join(notes) if notes else "Make sure the marker (`...`, "
                 "`pass`, or `{ }`) sits inside a function body."))
    edited = _apply_insertion(code, result['text'], result['replace_line'] or 0)
    lang = result['lang']
    try:
        from cos.text_editor import set_last_edit
        set_last_edit('code', edited)
    except Exception:
        pass
    from cos.code_gen import _lang_name as _ln
    parts = [f"Here's the completed code in {_ln(lang)}:"]
    parts.append(f"```{lang}\n{edited}\n```")
    if result['notes']:
        parts.append("Notes:\n- " + "\n- ".join(result['notes']))
    parts.append("Paste it back into your editor and the marker line gets "
                 "replaced by the body.")
    return "\n\n".join(parts)
