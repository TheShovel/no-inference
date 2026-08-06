"""
COS Code Generator — deterministic, rule-based code synthesis.

Unlike the curated code KB (code_knowledge.py) which answers "what is X" /
"how do I do X" from hand-written entries, this module *synthesizes* code for
common developer tasks by detecting the programming language and the task
from the query, then assembling a correct, complete code template.

The code is always real and runnable — it comes from a template library, not
from generation. There is no inference anywhere in this module.

All task knowledge lives in data files so it can be added to and iterated
without touching Python:

    data/knowledge/code_tasks/*.json

Each file holds a ``tasks`` array; files load in sorted filename order and
tasks within a file keep their array order, so the order of the files doubles
as detection priority (01_web, 02_algorithms, ...). A task looks like:

    {
      "task": "reverse_string",          // unique id, used by callers
      "patterns": ["regex", ...],        // any match routes the query here
      "intro": "Here's a {lang} function that reverses a string.",
      "notes": "Strings are immutable ...",      // optional
      "languages": {
        "python": "def reverse_string(s):\\n    return s[::-1]",
        "javascript": "...", ...                  // raw code, never .format()-ed
      }
    }

To add a task: create/edit a JSON file under data/knowledge/code_tasks/ and
either restart or call reload() (the CLI / server pick it up on the next
query). Language detection stays in code (detect_language below) because it
is shared logic; everything task-shaped is data.

Pipeline:
    query -> detect_language(query) -> detect_task(query) -> compose_answer()

Public API:
    generate_code(query) -> Optional[str]   full markdown answer, or None
    detect_language(query) -> Optional[str] canonical language name
    detect_task(query) -> Optional[str]     task id
    task_languages(task_id) -> dict         {lang: code} templates
    reload()                                drop cached knowledge files
"""

import json
import re
from pathlib import Path
from typing import Optional

# ── Language detection ──────────────────────────────────────────────────────
# canonical language -> (aliases with word boundaries, regex patterns)
_LANG_ALIASES = {
    'python':    {'python', 'python3', 'py', 'pandas', 'numpy', 'django',
                  'flask', 'fastapi', 'requests library', 'venv'},
    'javascript': {'javascript', 'js', 'node', 'node.js', 'nodejs', 'express',
                   'react', 'vue', 'axios', 'fetch api'},
    'typescript': {'typescript', 'ts', 'tsx'},
    'java':      {'java', 'javac', 'spring boot'},
    'c++':       {'c++', 'cpp', 'cplusplus'},
    'c':         {'c programming', 'c language'},
    'c#':        {'c#', 'csharp', 'c sharp', '.net'},
    'go':        {'go', 'golang'},
    'rust':      {'rust', 'rs'},
    'ruby':      {'ruby', 'rails'},
    'php':       {'php', 'laravel'},
    'swift':     {'swift'},
    'kotlin':    {'kotlin'},
    'sql':       {'sql', 'mysql', 'postgres', 'postgresql', 'sqlite',
                  'sql server', 'oracle'},
    'bash':      {'bash', 'shell', 'sh', 'zsh', 'command line', 'terminal',
                  'cli', 'curl', 'linux', 'ubuntu', 'unix', 'debian', 'mac'},
    'html':      {'html'},
    'css':       {'css'},
}

# Aliases that need a bit of context before they are treated as languages.
# "go" is a normal English word ("how to go about this"), so it only counts
# when a coding cue is nearby ("in go", "go program", "write ... in go").
_CONTEXTUAL_LANGS = {'go'}

_CODING_CUE_RE = re.compile(
    r'\b(?:write|implement|create|make|build|fix|debug|function|program|'
    r'code|snippet|class|algorithm|using|in|with)\b', re.IGNORECASE)


def _norm_aliases(text: str) -> str:
    """Normalize punctuation-heavy language names so they match aliases."""
    t = text.lower()
    # "c++" -> "cplusplus"  (also "c++11", "c++17")
    t = re.sub(r'\bc\s*\+\+\s*(?:\d+)?\b', 'cplusplus', t)
    # "c#" -> "csharp"
    t = re.sub(r'\bc\s*#\b', 'csharp', t)
    t = re.sub(r'\bc#\s*(?:\.net)?\b', 'csharp', t)
    # "node.js" -> "node.js" is already a literal alias
    return t


def detect_language(query: str) -> Optional[str]:
    """Return the canonical language name mentioned in the query, or None.

    If no language is mentioned, returns None — callers decide the default.
    """
    q = _norm_aliases(query)
    # 0. Explicit script-language phrases outrank any coincidental mention of
    #    another language's name ("write a bash script to list all python
    #    files" is a bash request even though 'python' appears).
    if re.search(r'\b(?:bash|shell|zsh|sh)\s+script\b', q, re.IGNORECASE):
        return 'bash'
    if re.search(r'\b(?:command\s*line|terminal|cli)\b', q, re.IGNORECASE):
        return 'bash'
    # 1. Exact alias hits (word-boundary), longest alias first.
    for lang, aliases in _LANG_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            alias_n = _norm_aliases(alias)
            if not alias_n:
                continue
            if alias_n in ('go',) and lang == 'go':
                # contextual: "go" must sit next to a coding cue
                if re.search(r'\bgolang\b', q):
                    return 'go'
                if re.search(r'\bgo\b', q) and _CODING_CUE_RE.search(query):
                    return 'go'
                continue
            if re.search(r'(?<![a-z0-9])' + re.escape(alias_n) + r'(?![a-z0-9])', q):
                return lang
    # 2. Tool-to-language fallbacks for framework names.
    if re.search(r'\bflask\b|\bfastapi\b|\bdjango\b', q, re.IGNORECASE):
        return 'python'
    if re.search(r'\bexpress\b|\bnode\b|react|vue', q, re.IGNORECASE):
        return 'javascript'
    if re.search(r'\bpandas\b|\bnumpy\b', q, re.IGNORECASE):
        return 'python'
    return None


# ── Task knowledge files ────────────────────────────────────────────────────
# data/knowledge/code_tasks/*.json — see the module docstring for the format.
_TASKS_DIR = Path(__file__).parent.parent.parent / 'data' / 'knowledge' / 'code_tasks'
_TASKS_CACHE = None       # list of task dicts in priority order
_WEB_TYPES_CACHE = None   # list of website business-type dicts


def _load_code_tasks() -> list:
    """All task definitions, in detection-priority order (cached)."""
    global _TASKS_CACHE
    if _TASKS_CACHE is not None:
        return _TASKS_CACHE
    tasks = []
    if _TASKS_DIR.exists():
        for path in sorted(_TASKS_DIR.glob('*.json')):
            if path.name.startswith('_'):
                continue
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            items = data.get('tasks', []) if isinstance(data, dict) else data
            if not isinstance(items, list):
                continue
            for t in items:
                if not (isinstance(t, dict) and t.get('task') and t.get('patterns')):
                    continue
                langs = dict(t.get('languages') or {})
                # TypeScript shares JavaScript syntax unless a task overrides it
                if 'typescript' not in langs and 'javascript' in langs:
                    langs['typescript'] = langs['javascript']
                t['languages'] = langs
                tasks.append(t)
    _TASKS_CACHE = tasks
    return tasks


def _load_web_types() -> list:
    """Website business types for the HTML generator (cached)."""
    global _WEB_TYPES_CACHE
    if _WEB_TYPES_CACHE is not None:
        return _WEB_TYPES_CACHE
    types = []
    try:
        data = json.loads((_TASKS_DIR / '_web_types.json').read_text(encoding='utf-8'))
        types = data.get('web_types', []) or []
    except (OSError, ValueError):
        types = []
    _WEB_TYPES_CACHE = types
    return types


def reload():
    """Drop cached knowledge so the next query re-reads the data files."""
    global _TASKS_CACHE, _WEB_TYPES_CACHE
    _TASKS_CACHE = None
    _WEB_TYPES_CACHE = None
    return _load_code_tasks()


def _task_entry(task_id: str) -> "dict | None":
    for t in _load_code_tasks():
        if t['task'] == task_id:
            return t
    return None


def task_languages(task_id: str) -> dict:
    """The {lang: code} templates for a task ({} when the task is unknown)."""
    entry = _task_entry(task_id)
    return entry['languages'] if entry else {}


# ── Composition ────────────────────────────────────────────────────────────

def detect_task(query: str) -> Optional[str]:
    """Return the task id matching the query, or None.

    First task whose any pattern matches wins — pattern order across the
    knowledge files is the detection priority.
    """
    q = query.lower().strip()
    for task in _load_code_tasks():
        for pat in task['patterns']:
            try:
                if re.search(pat, q):
                    return task['task']
            except re.error:
                continue
    return None


def _lang_name(lang: str) -> str:
    display = {
        'python': 'Python', 'javascript': 'JavaScript', 'typescript': 'TypeScript',
        'java': 'Java', 'c++': 'C++', 'c': 'C', 'c#': 'C#', 'go': 'Go',
        'rust': 'Rust', 'ruby': 'Ruby', 'php': 'PHP', 'swift': 'Swift',
        'kotlin': 'Kotlin', 'sql': 'SQL', 'bash': 'bash', 'html': 'HTML',
        'css': 'CSS',
    }
    return display.get(lang, lang.title())


# ── Website generator (deterministic HTML/CSS) ──────────────────────────────
# "create a website for a taco shop" is a code task, not a knowledge lookup.
# The generator builds a single self-contained HTML file, with content chosen
# deterministically from the business type in the topic (web types live in
# data/knowledge/code_tasks/_web_types.json).

_WEB_STOP = re.compile(
    r'\b(?:create|make|build|design|generate|develop|craft|code|simple|'
    r'basic|minimal|modern|responsive|beautiful|static|personal|'
    r'professional|small|one-page|a|an|the|my|our|your|for|about|of|'
    r'please|website|web\s*site|web\s*page|site|landing\s*page|'
    r'homepage|home\s*page|portfolio)\b', re.IGNORECASE)


class _WebPlan:
    pass


def _extract_website_topic(query: str) -> str:
    """Pull the topic out of a website request ("taco shop")."""
    q = query.strip()
    # 1. "website for <topic>" / "page about <topic>"
    m = re.search(
        r'\b(?:website|web\s*site|web\s*page|landing\s*page|homepage|'
        r'home\s*page|portfolio|site)\b\s*(?:for|about|of|to\s+promote)?\s*'
        r'(?:a|an|the|my|our)?\s*(.+)$', q, re.IGNORECASE)
    if m:
        topic = _WEB_STOP.sub(' ', m.group(1))
        topic = re.sub(r'\s+', ' ', topic).strip(' .')
        if topic:
            return topic
    # 2. noun-first: "<topic> website" / "build a portfolio website" — the
    #    words before the site-type keyword are the topic.
    m2 = re.search(
        r'^(.*?)\s+(?:website|web\s*site|web\s*page|site|landing\s*page|'
        r'homepage|home\s*page|portfolio)\b', q, re.IGNORECASE)
    if m2:
        topic = _WEB_STOP.sub(' ', m2.group(1))
        topic = re.sub(r'\s+', ' ', topic).strip(' .')
        if topic:
            return topic
    # 3. the site type itself is the topic ("a portfolio")
    m3 = re.search(r'\b(?:portfolio|landing\s*page)\b', q, re.IGNORECASE)
    if m3:
        return m3.group(0).title()
    return 'Our Business'


def _website_plan(topic: str) -> dict:
    """Map a topic to a site plan (name, tagline, sections, accent)."""
    low = topic.lower()
    for wt in _load_web_types():
        kw = (wt.get('keywords') or '').lower()
        if kw and kw in low:
            return {
                'name': topic.title(),
                'tagline': wt.get('tagline', ''),
                'accent': wt.get('accent', '#2c3e50'),
                'sections': [('Menu', wt.get('menu_items', [])),
                             ('About',
                              [f"{topic.title()} started with one simple idea: do the basics right, every day.",
                               'Everything here is made fresh in-house.']),
                             ('Hours',
                              ['Mon–Fri: 11am – 9pm',
                               'Sat: 10am – 10pm',
                               'Sun: 10am – 8pm']),
                             ('Find Us',
                              ['123 Main Street',
                               '(555) 010-5555']),
                             ],
            }
    return {
        'name': topic.title(),
        'tagline': f'{topic.title()} — quality you can count on.',
        'accent': '#2c3e50',
        'sections': [('About',
                      [f"{topic.title()} serves our customers with care and consistency."],
                      ),
                     ('Hours',
                      ['Mon–Fri: 9am – 6pm', 'Sat: 10am – 4pm',
                       'Sun: closed']),
                     ('Contact',
                      ['123 Main Street', '(555) 010-5555',
                       'hello@example.com']),
                     ],
    }


def _website_html(plan: dict) -> str:
    """Render the plan as a single self-contained HTML file."""
    name = plan['name']
    accent = plan['accent']
    nav = '\n      '.join(
        f'<a href="#{re.sub(r"[^a-z0-9]+", "-", h.lower()).strip("-")}">{h}</a>'
        for h, _ in plan['sections'])
    secs = []
    for heading, items in plan['sections']:
        anchor = re.sub(r'[^a-z0-9]+', '-', heading.lower()).strip('-')
        lis = '\n        '.join(f'<li>{it}</li>' for it in items)
        secs.append(
            f'  <section id="{anchor}">\n'
            f'    <h2>{heading}</h2>\n'
            f'    <ul>\n        {lis}\n    </ul>\n'
            f'  </section>')
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{name}</title>
  <style>
    :root {{ --accent: {accent}; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: system-ui, -apple-system, sans-serif;
           color: #222; line-height: 1.6; }}
    header {{ display: flex; justify-content: space-between;
             align-items: center; padding: 1rem 2rem;
             border-bottom: 1px solid #eee; }}
    .brand {{ font-weight: 700; font-size: 1.2rem; }}
    nav a {{ margin-left: 1.2rem; color: #444; text-decoration: none; }}
    nav a:hover {{ color: var(--accent); }}
    .hero {{ background: var(--accent); color: #fff; text-align: center;
            padding: 4rem 2rem; }}
    .hero h1 {{ margin: 0 0 .5rem; font-size: 2.6rem; }}
    .hero p {{ margin: 0; font-size: 1.2rem; opacity: .95; }}
    main {{ max-width: 46rem; margin: 0 auto; padding: 2rem; }}
    section {{ margin-bottom: 2.5rem; }}
    h2 {{ color: var(--accent); border-bottom: 2px solid var(--accent);
         padding-bottom: .3rem; }}
    ul {{ padding-left: 1.2rem; }}
    li {{ margin: .35rem 0; }}
    footer {{ text-align: center; color: #888; padding: 1.5rem;
             border-top: 1px solid #eee; }}
    @media (max-width: 640px) {{
      header {{ flex-direction: column; gap: .5rem; }}
      nav a {{ margin: 0 .6rem; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="brand">{name}</div>
    <nav>
      {nav}
    </nav>
  </header>
  <main>
    <section class="hero">
      <h1>{name}</h1>
      <p>{plan['tagline']}</p>
    </section>
{chr(10).join(secs)}
  </main>
  <footer>© 2026 {name}</footer>
</body>
</html>'''


def _website_answer(query: str) -> str:
    """Full chat answer for a website-creation request."""
    topic = _extract_website_topic(query)
    plan = _website_plan(topic)
    html = _website_html(plan)
    slug = re.sub(r'[^a-z0-9]+', '-', plan['name'].lower()).strip('-')
    intro = (f"Here's a complete, self-contained website for {plan['name']} — "
             f"a single HTML file with embedded CSS. Save it as "
             f"`{slug}.html` and open it in any browser.")
    notes = ("Sample content only — swap in your real menu, hours, address, "
             "and photos. To publish, drop the file into a static host "
             "(GitHub Pages, Netlify) or ask me to add a contact form.")
    return f"{intro}\n\n```html\n{html}\n```\n\n{notes}"


def generate_code(query: str, lang: Optional[str] = None) -> Optional[str]:
    """Synthesize a complete answer (intro + code + notes) for a coding query.

    Args:
        query: the coding question.
        lang:  force a language (used for "now do the same in rust" style
               follow-ups); when None the language is detected from the query.

    Returns None when the query doesn't map to a known task + language combo.
    """
    if lang is None:
        lang = detect_language(query)
    task = detect_task(query)
    if task is None:
        return None
    if task == 'web_page':
        return _website_answer(query)

    entry = _task_entry(task)
    if entry is None:
        return None
    code_templates = entry['languages']

    # Task-specific default languages: git/bash tasks are shell commands;
    # sql_* tasks are SQL; everything else defaults to Python when the query
    # doesn't name a language.
    if lang is None:
        if task.startswith('sql'):
            lang = 'sql'
        elif (task.startswith(('git', 'bash', 'sys'))
              or task in ('pip_install', 'npm_install')):
            lang = 'bash'
        else:
            lang = 'python'

    code = code_templates.get(lang)
    if code is None:
        # Task known but no template for the requested language: only
        # typescript→javascript is close enough to fall back to; otherwise
        # give up (never silently hand over the wrong language).
        if lang == 'typescript' and 'javascript' in code_templates:
            code = code_templates['javascript']
        else:
            return None

    intro = entry.get('intro') or "Here's a {lang} snippet for that."
    notes = entry.get('notes', '')
    display = _lang_name(lang)

    parts = [intro.format(lang=display)]
    parts.append(f"```{lang}\n{code}\n```")
    if notes:
        parts.append(notes)
    if lang == 'typescript':
        parts.append("Note: TypeScript and JavaScript share syntax — the code above runs in both, with type annotations you can add as needed.")
    if lang == 'python' and detect_language(query) is None and not task.startswith(('sql', 'git', 'bash')):
        parts.append("I assumed Python since you didn't name a language — tell me another language and I'll give you the same thing in it.")
    _detected = detect_language(query)
    if _detected and _detected != lang:
        parts.append(f"Here's the same thing in {display}.")
    return '\n\n'.join(parts)
