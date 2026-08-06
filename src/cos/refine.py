"""Iterative refinement: edit the last thing the agent generated.

The agent loop that makes this usable day-to-day is *make -> edit ->
refine*: "create a website for a taco shop", then "add a contact form",
then "change the accent color to green". Without a refinement layer those
follow-ups fall into the factual handler and return knowledge-article
garbage.

This module finds the most recent artifact (the last fenced code block the
engine produced, or code the user pasted), detects what refinement is being
asked for, and applies a deterministic edit to *that artifact*:

* code: convert language, add error handling, add comments, make faster
  (reuses the transformer ops), add a docstring, append a new function;
* HTML: change the accent color, dark mode, add a contact form, add a
  section, change the site name/title, change the hours, add a menu item,
  remove a section.

Never fabricates: when the intent is unclear or the edit can't be applied
to the artifact, it says so instead of inventing a change.
"""
import re

try:
    from cos.state import conversation_history
    from cos.text_editor import get_last_edit_content, get_last_edit_kind
except Exception:  # pragma: no cover - partial import safety
    conversation_history = []
    get_last_edit_content = None
    get_last_edit_kind = None


# ── Artifact discovery ───────────────────────────────────────────────────────

_FENCE_RE = re.compile(r'```(\w*)\n(.*?)```', re.DOTALL)


def find_last_artifact(kind: str = '') -> "tuple[str, str, str] | None":
    """The most recent code the engine produced or the user pasted.

    Returns (code, lang, original_query) or None. Prefers code the user
    pasted (last edit) over the last generated answer. When ``kind`` is
    'html', only HTML artifacts match (a website refinement must edit the
    website, not the fibonacci function generated in between).
    """
    if get_last_edit_content is not None and get_last_edit_kind is not None:
        try:
            if get_last_edit_kind() == 'code':
                pasted = get_last_edit_content()
                if pasted and pasted.strip():
                    lang = _detect_lang(pasted)
                    if kind != 'html' or lang == 'html':
                        return pasted, lang, ''
        except Exception:
            pass
    for _pq, _pa in reversed(conversation_history or []):
        if not _pa or '```' not in _pa:
            continue
        m = _FENCE_RE.search(_pa)
        if not (m and m.group(2).strip()):
            continue
        fence_lang = m.group(1) or _detect_lang(m.group(2))
        if kind == 'html' and fence_lang != 'html':
            continue
        if kind == 'code' and fence_lang == 'html':
            continue
        return m.group(2).strip('\n'), fence_lang, _pq or ''
    return None


def _detect_lang(code: str) -> str:
    try:
        from cos.code_transformer import detect_code_lang
        return detect_code_lang(code) or 'python'
    except Exception:
        return 'python'


# ── Intent detection ─────────────────────────────────────────────────────────

_REFINE_VERB = re.compile(
    r'\b(?:add|change|remove|delete|make|turn|set|refine|improve|'
    r'optimize|update|edit|convert|rewrite|style|rename|shorten|'
    r'fix|recolor)\b')

# words that point at a previously generated artifact (vs. brand-new content)
_ARTIFACT_REF = re.compile(
    r'\b(?:the|this|it|my|our|its)\s+(?:website|site|page|menu|'
    r'title|name|color|section|function|script|code|backup|'
    r'hours|form|style|theme|header|footer|hero|nav|robot|app|'
    r'docstring|errors?|compression|comments?)\b|'
    r'\b(?:the\s+)?(?:website|site|page|menu|title|color|section|'
    r'function|script|code|backup|hours|form|style|theme|header|'
    r'footer|hero|nav|docstring|error\s+handling|errors?|compression|'
    r'comments?)\b')

_COLORS = {
    'red': '#e74c3c', 'green': '#2ecc71', 'blue': '#3498db', 'orange': '#e67e22',
    'purple': '#9b59b6', 'pink': '#e91e63', 'yellow': '#f1c40f', 'teal': '#16a085',
    'brown': '#795548', 'gray': '#7f8c8d', 'grey': '#7f8c8d', 'black': '#222222',
    'white': '#ffffff', 'navy': '#2c3e50', 'indigo': '#30336b', 'crimson': '#c0392b',
    'gold': '#d4a017', 'cyan': '#00bcd4', 'lime': '#a3cb38', 'maroon': '#800000',
}


def detect_refinement(query: str) -> "dict | None":
    """Detect a refinement request; returns an intent dict or None.

    Returns {'intent': ..., 'params': {...}}. Only fires for imperative
    edits that reference a previous artifact — never for questions, math,
    or brand-new content requests.
    """
    q = query.strip()
    ql = q.lower()
    if len(q) < 8 or not _REFINE_VERB.search(ql):
        return None
    if re.match(r'^(?:what|how|why|when|where|who|which|is|are|can|could|'
                r'does|do|should|would|explain|describe|tell)\b', ql):
        return None
    # the query must reference the artifact or be an "it/this" phrasing
    if not _ARTIFACT_REF.search(ql) and not re.search(
            r'\b(?:it|this|that)\s+(?:instead|up|out|in|now)\b', ql) \
            and not re.search(r'\b(?:make|turn|set)\s+(?:it|this|the\s+site|'
                              r'the\s+website|the\s+page|the\s+code|the\s+'
                              r'script|the\s+function)\s+(?:more\s+)?[a-z]+\b', ql):
        return None

    # ── language conversion ("now do the same in rust") ────────────────
    m = re.search(
        r'\b(?:now\s+|then\s+|can\s+you\s+|please\s+)?'
        r'(?:do|write|make|create|implement|rewrite|convert|give|translate)\s+'
        r'(?:the\s+same|that|it|this|the\s+same\s+thing|that\s+again)?'
        r'\s*(?:again|too)?\s*(?:in|to|using|into|with)\s+'
        r'([a-z][a-z0-9+#.\s-]{0,20}?)[?.!]*$', ql)
    if m:
        try:
            from cos.code_knowledge import detect_query_lang
            new_lang = detect_query_lang('in ' + m.group(1))
        except Exception:
            new_lang = None
        if new_lang:
            return {'intent': 'convert_lang', 'params': {'lang': new_lang}}

    # ── HTML refinements ────────────────────────────────────────────────
    m = re.search(r'\b(?:change|make|turn|set|recolor)\b.*?\b'
                  r'(?:accent\s+)?color\s+(?:to|as)?\s*([a-z]+)', ql)
    if m and m.group(1) in _COLORS:
        return {'intent': 'set_accent', 'params': {'color': m.group(1)}}
    if re.search(r'\bdark\s+mode\b|\bmake\s+it\s+dark\b', ql):
        return {'intent': 'dark_mode', 'params': {}}
    if re.search(r'\b(?:add|insert)\b.*\bcontact\s+form\b', ql):
        return {'intent': 'add_contact_form', 'params': {}}
    if re.search(r'\badd\b.*\b(?:compression|zip|archive|compress)\b', ql):
        return {'intent': 'add_compression', 'params': {}}
    m = re.search(r'\b(?:add|insert)\b.*\bsection\b.*\b(?:about|for|on)\s+'
                  r'([\w\s]{2,30}?)[?.!]*$', ql)
    if m:
        return {'intent': 'add_section', 'params': {'heading': m.group(1).strip()}}
    m = re.search(r'\b(?:add|insert)\b\s+(?:a|an|the)?\s*([\w\s]{2,30}?)\s+section\b', ql)
    if m:
        return {'intent': 'add_section', 'params': {'heading': m.group(1).strip()}}
    m = re.search(r'\b(?:change|rename|set|update)\b.*\b(?:name|title|brand)\b'
                  r'.*\b(?:to|as)\s+([\w\s]{2,30}?)[?.!]*$', ql)
    if m:
        return {'intent': 'set_title', 'params': {'title': m.group(1).strip()}}
    m = re.search(r'\b(?:change|set|update)\b.*\bhours\b', ql)
    if m:
        return {'intent': 'set_hours', 'params': {}}
    m = re.search(r'\badd\b\s+([\w\s\-]{2,40}?)\s+(?:to\s+the\s+)?menu\b', ql)
    if m and 'section' not in ql:
        return {'intent': 'add_menu_item',
                'params': {'item': m.group(1).strip()}}
    m = re.search(r'\bremove\b\s+(?:the\s+)?([\w\s]{2,30}?)\s+section\b', ql)
    if m:
        return {'intent': 'remove_section',
                'params': {'heading': m.group(1).strip()}}

    # ── code refinements ─────────────────────────────────────────────────
    if re.search(r'\b(?:add|with)\b.*\b(?:error\s*handling|try|safe|'
                 r'guard)\b|\bhandle\s+errors\b|\bmake\s+it\s+safe\b', ql):
        return {'intent': 'add_errors', 'params': {}}
    if re.search(r'\b(?:add|more)\b.*\bcomments?\b|\bcomment\s+it\b', ql):
        return {'intent': 'add_comments', 'params': {}}
    if re.search(r'\b(?:make\s+it|more)\s+faster\b|\boptimize\b|\b(?:make|'
                 r'improve)\s+(?:it|the\s+code)\s+(?:more\s+)?efficient\b', ql):
        return {'intent': 'make_faster', 'params': {}}
    if re.search(r'\b(?:add|write)\b.*\bdocstring\b|\bdocument\s+(?:it|the\s+'
                 r'function)\b', ql):
        return {'intent': 'add_docstring', 'params': {}}
    m = re.search(r'\b(?:add|write|create)\b.*\bfunction\s+that\s+(.+?)[?.!]*$', ql)
    if m:
        return {'intent': 'add_function', 'params': {'task': m.group(1).strip()}}
    return None


# ── HTML edits ───────────────────────────────────────────────────────────────

def _html_edit(intent: str, params: dict, code: str) -> "tuple[str, list[str]] | None":
    if intent == 'set_accent':
        color = _COLORS.get(params['color'])
        if not color or '--accent:' not in code:
            return None
        new = re.sub(r'--accent:\s*#[0-9a-fA-F]{3,8}', f'--accent: {color}', code,
                     count=1)
        return (new, [f"changed the accent color to {params['color']} ({color})"])
    if intent == 'dark_mode':
        if '--accent:' not in code:
            return None
        css = ('\n    body { background: #121212; color: #eee; }\n'
               '    header, footer { background: #1e1e1e; border-color: #333; }\n'
               '    nav a { color: #ccc; }\n'
               '    .hero { background: var(--accent); color: #fff; }')
        new = code.replace('  </style>', css + '\n  </style>', 1)
        return (new, ['switched to a dark theme (dark background, light text)'])
    if intent == 'add_contact_form':
        if '<form' in code or '</main>' not in code:
            return None
        form = ('  <section id="contact">\n'
                '    <h2>Contact</h2>\n'
                '    <form action="#" method="post">\n'
                '      <label for="name">Name</label><br>\n'
                '      <input id="name" name="name" required><br><br>\n'
                '      <label for="email">Email</label><br>\n'
                '      <input id="email" name="email" type="email" required><br><br>\n'
                '      <label for="message">Message</label><br>\n'
                '      <textarea id="message" name="message" rows="4" required></textarea><br><br>\n'
                '      <button type="submit">Send</button>\n'
                '    </form>\n'
                '  </section>\n')
        new = code.replace('  </main>', form + '  </main>', 1)
        note = 'added a contact form section (name/email/message — wire the action to your form backend)'
        return new, [note]
    if intent == 'add_section':
        heading = params['heading'].title()
        anchor = re.sub(r'[^a-z0-9]+', '-', heading.lower()).strip('-')
        sec = (f'  <section id="{anchor}">\n'
               f'    <h2>{heading}</h2>\n'
               f'    <p>Add your content about {params["heading"].strip()} here.</p>\n'
               '  </section>\n')
        new = code.replace('  </main>', sec + '  </main>', 1)
        return (new, [f'added a "{heading}" section with a placeholder'])
    if intent == 'set_title':
        title = params['title'].title()
        new = re.sub(r'<title>.*?</title>', f'<title>{title}</title>', code, count=1)
        new = re.sub(r'class="brand">.*?</div>', f'class="brand">{title}</div>',
                     new, count=1)
        new = re.sub(r'<h1>.*?</h1>', f'<h1>{title}</h1>', new, count=1)
        if new != code:
            return (new, [f'renamed the site to "{title}" (title, brand, hero)'])
        return None
    if intent == 'set_hours':
        # replace the Hours list items with a sensible default
        if '<h2>Hours</h2>' not in code:
            return None
        lis = ('<li>Mon–Fri: 9am – 6pm</li>\n        <li>Sat: 10am – 4pm</li>\n'
               '        <li>Sun: closed</li>')
        new = re.sub(r'(<section id="hours">.*?<h2>Hours</h2>\n\s*<ul>\n\s*).*?'
                     r'(\n\s*</ul>)',
                     lambda m: m.group(1) + lis + m.group(2), code, count=1,
                     flags=re.DOTALL)
        if new != code:
            note = ('updated the hours (9–6 weekdays, 10–4 Sat, closed Sun) — '
                    "tell me your real hours and I'll set them")
            return new, [note]
        return None
    if intent == 'add_menu_item':
        if '<ul>' not in code:
            return None
        item = params['item']
        new = re.sub(r'(\n\s*<ul>\n)(\s*<li>)', r'\1        <li>' + item +
                     r'</li>\n\2', code, count=1)
        if new != code:
            return (new, [f'added "{item}" to the menu'])
        return None
    if intent == 'remove_section':
        heading = params['heading'].title()
        pat = re.compile(
            r'  <section id="[^"]*">\n    <h2>' + re.escape(heading) +
            r'</h2>\n.*?  </section>\n', re.DOTALL)
        new = pat.sub('', code, count=1)
        if new != code:
            return (new, [f'removed the "{heading}" section'])
        return None
    return None


# ── Code edits ───────────────────────────────────────────────────────────────

def _code_edit(intent: str, params: dict, code: str, lang: str) -> "tuple[str, list[str]] | None":
    if intent == 'convert_lang':
        try:
            from cos.code_transformer import transform_code
            edited, notes = transform_code('convert_lang', params, code, lang)
            if edited != code:
                return edited, list(notes)
        except Exception:
            pass
        return None
    if intent in ('add_errors', 'add_comments', 'make_faster'):
        try:
            from cos.code_transformer import transform_code
            edited, notes = transform_code(intent, {}, code, lang)
            if edited != code:
                return edited, list(notes)
        except Exception:
            pass
        return None
    if intent == 'add_docstring' and lang == 'python':
        m = re.search(r'^(\s*)(?:async\s+)?def\s+\w+\s*\([^)]*\)[^:]*:\s*$',
                      code, re.MULTILINE)
        if m and '"""' not in code[m.start():m.start() + 200]:
            indent = m.group(1) + '    '
            doc = f'{indent}"""{params.get("task", "TODO: describe what this does.")}"""\n'
            new = code[:m.end()] + '\n' + doc + code[m.end():]
            return (new, ['added a docstring to the first function'])
        return None
    if intent == 'add_compression':
        low = code.lower()
        if 'shutil' in low and ('copytree' in low or 'backup' in low):
            fn = ('\n\ndef backup_compressed(source: str, dest_root: str = "backups") -> str:\n'
                  '    """Back up a directory as a compressed .tar.gz archive."""\n'
                  '    import os\n'
                  '    import shutil\n'
                  '    from datetime import datetime\n'
                  '    if not os.path.isdir(source):\n'
                  '        raise ValueError(f"not a directory: {source}")\n'
                  '    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")\n'
                  '    name = os.path.basename(os.path.normpath(source)) or "backup"\n'
                  '    os.makedirs(dest_root, exist_ok=True)\n'
                  '    dest = os.path.join(dest_root, f"{name}-{stamp}.tar.gz")\n'
                  '    shutil.make_archive(dest[:-7], "gztar", source)\n'
                  '    return dest\n')
            note = ('added backup_compressed(): a .tar.gz archive variant '
                    '(call it instead of backup() when you want compression)')
            return code + fn, [note]
        if 'rsync' in low:
            fn = ('\n\n# Compressed archive variant (single .tar.gz file):\n'
                  'tar -czf "$DEST_ROOT/$NAME-$STAMP.tar.gz" \\n'
                  '    -C "$(dirname "$SOURCE")" "$(basename "$SOURCE")"\n'
                  'echo "archived to $DEST_ROOT/$NAME-$STAMP.tar.gz"')
            return (code + fn, ['added a compressed .tar.gz archive variant'])
        return None
    if intent == 'add_function':
        try:
            from cos.code_gen import generate_code
            gen = generate_code(params['task'])
            if gen:
                from cos.code_editor import first_function_def
                extracted = first_function_def(gen, 'python' if lang in
                                               ('python',) else lang)
                if extracted:
                    _dfl, body = extracted
                    fn = _dfl + '\n' + '\n'.join(body)
                    sep = '\n\n' if code and not code.endswith('\n') else ''
                    return (code + sep + fn + '\n',
                            [f'appended a function that {params["task"]}'])
        except Exception:
            pass
        return None
    return None


# ── Public API ───────────────────────────────────────────────────────────────

_HTML_INTS = {'set_accent', 'dark_mode', 'add_contact_form', 'add_section',
              'set_title', 'set_hours', 'add_menu_item', 'remove_section'}

def refine_last_artifact(intent: dict) -> "str | None":
    """Apply a refinement to the last artifact; returns a full answer."""
    kind = 'html' if intent['intent'] in _HTML_INTS else 'code'
    artifact = find_last_artifact(kind)
    if not artifact:
        return None
    code, lang, _query = artifact
    if lang == 'html':
        edited = _html_edit(intent['intent'], intent['params'], code)
    else:
        edited = _code_edit(intent['intent'], intent['params'], code, lang)
    if not edited:
        return (f"I understand you want to {intent['intent'].replace('_', ' ')} "
                f"the last thing I generated, but I couldn't apply that edit "
                f"to it reliably — tell me more specifically what to change "
                f"(or paste the code and I'll edit it directly).")
    new_code, changes = edited
    head = f"Here's the updated version ({', '.join(changes)}):"
    return f"{head}\n\n```{lang}\n{new_code}\n```\n\n" \
           f"Changes:\n- " + "\n- ".join(changes)


def refine_query(query: str) -> "str | None":
    """Convenience: detect a refinement and apply it (used by the engine)."""
    intent = detect_refinement(query)
    if not intent:
        return None
    return refine_last_artifact(intent)
