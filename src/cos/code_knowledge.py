"""
COS Code Knowledge — Answers coding questions using:
  1. Knowledge files in data/knowledge/coding/*.json
  2. HuggingFace Datasets Server API (Stack-v3 dataset) as fallback
"""

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

# Language detection for coding queries (delegates to the code generator's
# alias table so "c++", "c#", "js", "golang" etc. are all recognized).
try:
    from cos.code_gen import _LANG_ALIASES as _CG_LANG_ALIASES
    from cos.code_gen import detect_language as _detect_query_lang
except ImportError:
    _detect_query_lang = None
    _CG_LANG_ALIASES = {}


def detect_query_lang(query: str) -> "str | None":
    """Canonical language mentioned in a query, or None."""
    if _detect_query_lang is None:
        return None
    try:
        return _detect_query_lang(query)
    except (TypeError, ValueError, re.error):
        return None


_LANG_PATTERNS = None  # list of (lang, compiled regex) built lazily


def _pattern_langs(text: str):
    """Return the set of canonical languages mentioned in a KB pattern string."""
    global _LANG_PATTERNS
    if _LANG_PATTERNS is None:
        _LANG_PATTERNS = []
        for _lang, _aliases in _CG_LANG_ALIASES.items():
            for _al in _aliases:
                _an = re.sub(r'\bc\s*\+\+\s*\d*\b', 'cplusplus', _al.lower())
                _an = re.sub(r'\bc\s*#\s*(?:\.net)?\b', 'csharp', _an)
                if _an in ('go',) or not _an:
                    continue
                try:
                    _re = re.compile(r'(?<![a-z0-9])' + re.escape(_an) + r'(?![a-z0-9])')
                    _LANG_PATTERNS.append((_lang, _re))
                except re.error:
                    continue
    out = set()
    t = text.lower()
    t = re.sub(r'\bc\s*\+\+\s*\d*\b', 'cplusplus', t)
    t = re.sub(r'\bc\s*#\s*(?:\.net)?\b', 'csharp', t)
    for _lang, _re in _LANG_PATTERNS:
        if _re.search(t):
            out.add(_lang)
    return out


def _lang_adjust(query_lang: "str | None", pattern_str: str) -> int:
    """Scoring bonus/penalty so same-language KB entries beat mismatches."""
    if not query_lang:
        return 0
    plangs = _pattern_langs(pattern_str)
    if not plangs:
        return 0
    if query_lang in plangs:
        return 80
    return -80


def answer_language(answer: str) -> "str | None":
    """Language of the first code fence in an answer, or None."""
    m = re.search(r'```([^\s`]+)', answer or '')
    if not m:
        return None
    lang = m.group(1).lower()
    return {'js': 'javascript', 'py': 'python', 'cpp': 'c++', 'cs': 'c#',
            'jsx': 'javascript', 'tsx': 'javascript', 'ts': 'typescript'}.get(lang, lang)


# Action verbs that mark a "do it for me" code request. A fuzzy KB match
# whose pattern lacks the query's task verb is usually the wrong entry.
_TASK_VERBS = (
    'write', 'create', 'implement', 'build', 'make', 'generate', 'remove',
    'find', 'check', 'sort', 'reverse', 'convert', 'read', 'fetch', 'fix',
    'debug', 'delete', 'add', 'count', 'merge', 'flatten', 'split', 'parse',
    'validate', 'extract', 'rename', 'install', 'kill', 'print',
)
_TASK_VERB_SET = frozenset(_TASK_VERBS)

# Language/framework names: they tell us the target language, but a shared
# language word must never substantiate a topic match on its own ("write a
# python script to check if a website is up" must not match the entry
# "how to check if a key exists in a python dictionary" just because both
# mention python).
_LANG_WORD_SET = frozenset(
    """python javascript typescript java c++ cpp c# csharp go golang rust
    ruby php swift kotlin scala sql bash shell html css js ts py django flask
    fastapi express react vue node pandas numpy git docker curl regex regexp
    json csv xml""".split())

# ── Stack dataset API ──────────────────────────────────────────────────────

_STACK_DATASET = "HuggingFaceCode/stack-v3-train"
_DATASETS_SERVER = "https://datasets-server.huggingface.co"
_STACK_CACHE = {}


def _search_stack(query: str, max_files: int = 2) -> list[dict]:
    """Search Stack dataset for code relevant to the query.

    Network fallback — only runs when COS_ALLOW_NETWORK=1. Without it the
    system stays fully offline and deterministic (returns no results, so
    callers fall through to their local KB / synthesizer paths).
    """
    if os.environ.get("COS_ALLOW_NETWORK") != "1":
        return []

    cache_key = query.lower().strip()
    if cache_key in _STACK_CACHE:
        return _STACK_CACHE[cache_key]

    results = []
    key_terms = _extract_code_terms(query)
    search_queries = [query] + key_terms
    seen_repos = set()

    for sq in search_queries:
        if len(results) >= max_files:
            break
        try:
            search_url = (
                f"{_DATASETS_SERVER}/search"
                f"?dataset={urllib.parse.quote(_STACK_DATASET)}"
                f"&config=default&split=train"
                f"&query={urllib.parse.quote(sq)}"
            )
            req = urllib.request.Request(search_url, headers={
                'User-Agent': 'COS/1.0'
            })
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode())

            for row_wrapper in data.get('rows', []):
                if len(results) >= max_files:
                    break
                row = row_wrapper.get('row', {})
                repo_path = row.get('repo_path', '')
                if repo_path in seen_repos:
                    continue
                seen_repos.add(repo_path)

                for f in row.get('files', []):
                    if len(results) >= max_files:
                        break
                    content = f.get('content', '')
                    path = f.get('file_path', '')
                    lang = f.get('language') or f.get('lang') or ''
                    if content and len(content) > 50:
                        results.append({
                            'content': content,
                            'path': path or f"{repo_path}/unknown",
                            'language': lang or _detect_lang(path),
                            'repo': repo_path,
                        })
        except (OSError, ValueError):
            continue

    _STACK_CACHE[cache_key] = results
    return results


def _extract_code_terms(query: str) -> list[str]:
    """Extract programming-specific terms from a coding question."""
    q = query.lower()
    terms = []

    langs = ['python', 'javascript', 'typescript', 'java', 'c++', 'c#',
             'rust', 'go', 'ruby', 'php', 'swift', 'kotlin', 'scala',
             'perl', 'lua', 'r', 'matlab', 'bash', 'shell', 'sql',
             'html', 'css', 'react', 'node', 'django', 'flask']
    for lang in langs:
        if lang in q:
            terms.append(lang)

    stop = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'do', 'does',
            'did', 'how', 'what', 'why', 'when', 'where', 'which', 'who',
            'to', 'in', 'on', 'at', 'for', 'with', 'by', 'from', 'of',
            'and', 'or', 'but', 'not', 'can', 'could', 'would', 'should',
            'will', 'shall', 'may', 'might', 'this', 'that', 'these',
            'those', 'i', 'you', 'we', 'they', 'he', 'she', 'it',
            'me', 'my', 'your', 'our', 'their', 'its', 'his', 'her',
            'have', 'has', 'had', 'been', 'being', 'be', 'get', 'got',
            'use', 'used', 'using', 'make', 'made', 'making', 'write',
            'writes', 'writing', 'written', 'create', 'creates',
            'creating', 'called', 'calling', 'call', 'like', 'just',
            'also', 'very', 'much', 'many', 'some', 'any', 'every',
            'each', 'all', 'both', 'most', 'more', 'other', 'such',
            'into', 'over', 'than', 'then', 'now', 'about', 'tell',
            'explain', 'describe', 'define', 'show', 'give', 'need',
            'want', 'help', 'please', 'thanks', 'thank', 'way', 'ways',
            'best', 'good', 'great', 'easy', 'simple', 'different', 'thing'}
    words = re.findall(r'\b\w+\b', q)
    content_words = [w for w in words if w not in stop and len(w) >= 3]
    if len(content_words) >= 2:
        for i in range(len(content_words) - 1):
            terms.append(f"{content_words[i]} {content_words[i+1]}")

    return terms[:5]


def _detect_lang(path: str) -> str:
    ext_map = {
        '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
        '.java': 'java', '.cpp': 'c++', '.c': 'c', '.cs': 'c#',
        '.rs': 'rust', '.go': 'go', '.rb': 'ruby', '.php': 'php',
        '.swift': 'swift', '.kt': 'kotlin', '.scala': 'scala',
        '.pl': 'perl', '.lua': 'lua', '.r': 'r', '.m': 'matlab',
        '.sh': 'bash', '.sql': 'sql', '.html': 'html', '.css': 'css',
        '.jsx': 'react', '.tsx': 'react',
    }
    _, ext = os.path.splitext(path)
    return ext_map.get(ext.lower(), 'unknown')


# ── Coding Knowledge Files ─────────────────────────────────────────────────

_KNOWLEDGE_DIR = Path(__file__).parent.parent.parent / 'data' / 'knowledge' / 'coding'
_KB_CACHE = None  # List of (regex_pattern, answer)

# Word index for fast coding lookup: significant word (lowercase) -> set of
# entry indices into _KB_CACHE. Built during _load_coding_knowledge so
# code_lookup only scans candidate entries instead of all ~1.7k patterns on
# every query. SOUND for the exact-match phase: an escaped-literal pattern can
# only match text that contains every one of its words.
_CODE_WORD_INDEX = {}
# Parallel to _KB_CACHE: frozenset of word tokens for each entry.
_CODE_ENTRY_WORDS = []
# All distinct index keys, for substring expansion in the fuzzy phase
# (query word "api" should find patterns containing "apis" or "api_key").
_CODE_WORD_KEYS = set()

_CODE_WORD_TOKEN_RE = re.compile(r'[a-z0-9]+')


def _code_word_tokens(text):
    """Extract the set of significant word tokens from text."""
    return set(_CODE_WORD_TOKEN_RE.findall(text.lower()))


def _load_coding_knowledge():
    """Load all coding knowledge entries from data/knowledge/coding/"""
    global _KB_CACHE, _CODE_WORD_INDEX, _CODE_ENTRY_WORDS, _CODE_WORD_KEYS
    if _KB_CACHE is not None:
        return _KB_CACHE

    if not _KNOWLEDGE_DIR.exists():
        _KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        _KB_CACHE = []
        _CODE_WORD_INDEX = {}
        _CODE_ENTRY_WORDS = []
        _CODE_WORD_KEYS = set()
        return []

    entries = []
    _CODE_WORD_INDEX = {}
    _CODE_ENTRY_WORDS = []
    _CODE_WORD_KEYS = set()
    for path in sorted(_KNOWLEDGE_DIR.glob('*.json')):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue

        if not isinstance(data, list):
            data = [data]

        for entry in data:
            questions = entry.get('q', entry.get('patterns', []))
            # Normalize: if q is a single string, wrap it in a list so iteration
            # doesn't decompose it into individual characters.
            if isinstance(questions, str):
                questions = [questions]
            answer = entry.get('a', entry.get('answer', ''))
            code = entry.get('code', '')
            full = answer
            if code:
                lang = entry.get('lang', '')
                fences = f"```{lang}\n{code}\n```"
                full += f"\n\n{fences}" if fences.strip(f"```{lang}") else fences

            if not questions or not answer:
                continue

            for q_text in questions:
                if isinstance(q_text, str) and q_text.strip():
                    try:
                        regex = re.compile(re.escape(q_text.strip()), re.IGNORECASE)
                        idx = len(entries)
                        entries.append((regex, full))
                        _entry_words = _code_word_tokens(q_text)
                        _CODE_ENTRY_WORDS.append(_entry_words)
                        for _w in _entry_words:
                            _CODE_WORD_INDEX.setdefault(_w, set()).add(idx)
                            _CODE_WORD_KEYS.add(_w)
                    except re.error:
                        continue

    _KB_CACHE = entries
    return entries


# ── Coding Query Detection ─────────────────────────────────────────────────

# Strict coding keywords — only match when query is CLEARLY about coding.
# Avoid overly generic words like "app", "server", "api" that appear in
# non-coding contexts (e.g., "what is an api" is a general question).
_CODING_KEYWORDS_STRICT = {
    # Programming languages (must appear with a coding context)
    'python', 'javascript', 'typescript', 'java', 'c++', 'c#', '.net',
    'rust', 'golang', 'ruby', 'php', 'swift', 'kotlin', 'scala',
    # Code-specific terms
    'function', 'method', 'class', 'variable', 'algorithm',
    'programming', 'code snippet', 'code example', 'code block',
    'sort a list', 'sort an array', 'merge dict', 'binary search',
    'async function', 'arrow function', 'lambda function',
    'list comprehension', 'dict comprehension',
    'for loop', 'while loop', 'if statement', 'switch case',
    'break and continue', 'break statement', 'continue statement',
    'try except', 'try catch', 'error handling', 'exception handling',
    'html', 'css', 'flexbox', 'css grid', 'react component',
    'usestate', 'useeffect', 'useref', 'custom hook',
    'virtual environment', 'virtualenv', 'pip install',
    'npm install', 'yarn add', 'import statement',
    'git commit', 'git branch', 'git merge', 'git push',
    'sql query', 'sql join', 'sql select', 'create table',
    'api endpoint', 'rest api', 'graphql',
    'docker container', 'docker compose', 'kubernetes',
    'unit test', 'integration test', 'test case', 'tdd',
    'regex', 'regular expression', 'parsing', 'duplicate lines', 'unique lines',
    'crud operation', 'mvc pattern', 'design pattern',
    'recursion', 'recursive function', 'callback', 'promise',
    'async await', 'concurrency', 'parallelism',
    'operator', 'modulo', 'modulus', 'mod operator',
    'goroutine', 'goroutines', 'channel', 'keyerror', 'segfault',
    'segmentation fault', 'null pointer', 'nullpointerexception',
    'race condition', 'deadlock', 'multithreading',
    'memory leak', 'memory management', 'garbage collection',
    'pointer', 'reference', 'inheritance', 'polymorphism',
    'encapsulation', 'abstraction', 'interface',
    'dependency injection', 'singleton', 'factory',
    'middleware', 'authentication', 'authorization',
    'jwt', 'oauth', 'session', 'cookie',
    'database migration', 'orm', 'sqlalchemy',
    'django', 'flask', 'fastapi', 'express', 'spring boot',
    'react', 'vue', 'angular', 'svelte', 'next.js', 'nuxt',
    'node.js', 'deno', 'bun', 'webpack', 'vite',
    'babel', 'eslint', 'prettier', 'jest', 'pytest',
    'ci/cd', 'github actions', 'gitlab ci',
    'time complexity', 'space complexity', 'big o',
    'data structure', 'linked list', 'binary tree',
    'hash map', 'hash set', 'stack', 'queue', 'heap',
    'depth-first', 'breadth-first', 'dynamic programming',
    'greedy algorithm', 'divide and conquer',
    'decorator', 'generator', 'iterator', 'yield',
    'context manager', 'with statement',
    'list slice', 'string slice', 'substring',
    'json parse', 'json stringify', 'serialize',
    'http request', 'http response', 'fetch api',
    'http', 'https', 'status code', 'status codes',
    'write a function', 'write a program', 'write code',
    'how to code', 'how to program',
    'center a div', 'responsive layout',
    'handle exception', 'handle error',
    'merge array', 'merge list',
}


def is_coding_query(query: str) -> bool:
    """Check if a query is clearly a coding/programming question.

    Conservative: uses multi-word patterns and specific coding terms
    to avoid flagging general questions as coding questions.
    """
    q = query.lower().strip()

    # Unambiguous domain words: these only make sense as coding/tech topics
    # in a Q&A bot, so a single hit is enough. Punctuation-heavy names
    # (c++, c#) use lookarounds — a trailing `\b` can't match after '+'/'.'
    if re.search(r'(?<![a-z0-9])(?:sql|mysql|postgres|postgresql|sqlite|csv|'
                 r'pandas|dataframe|json|git|golang|typescript|docker|'
                 r'kubernetes|kubectl|regex|regexp|api\s+endpoint|rest\s+api|graphql|'
                 r'npm|pip|bash|shell|command\s+line|curl|flask|django|'
                 r'fastapi|express|react|linux|ubuntu|unix|debian|'
                 r'dockerfile|gitignore|github\s+actions|docker[- ]compose|'
                 r'setup\.py|pyproject\.toml|requirements\.txt|package\.json|'
                 r'cron|systemd|ffmpeg|rsync|inotify|yaml|c\+\+|c#|'
                 r'xargs|awk|sed|jq|matplotlib|seaborn|scipy|toml|ini|'
                 r'cherry[- ]?pick|revert|disk\s+space|disk\s+usage|pods?|'
                 r'terraform|ansible|kubernetes|axios|tar|'
                 r'rate\s+limiter|url\s+shortener|task\s+queue|argparse|'
                 r'sqlalchemy|jest|ownership|go|grep|scikit[- ]?learn|sklearn)(?![a-z0-9])', q):
        return True

    # Building a website/page is a code task even when no language is named.
    if re.search(r'\b(?:create|make|build|design|generate|develop)\b.*\b'
                 r'(?:website|web\s*site|web\s*page|landing\s*page|'
                 r'homepage|home\s*page)\b', q):
        return True

    # Code syntax patterns (most reliable indicator)
    # "from" alone is too broad (matches English preposition).
    # Only check "from x import" pattern.
    # NOTE: "class" alone is intentionally excluded from this check because it
    # is a common English word ("working-class"). Instead, "class" followed by
    # an identifier (capitalized or with colon/brace) is matched below.
    if re.search(r'\b(?:def |function |import |#include|public |private |int |float |string |var |let |const |=>|from\s+\w+\s+import|`[^`]+`|class\s+\w+\s*[:{(])', q):
        return True

    # English word that is also a coding keyword — requires a second
    # coding indicator (another keyword match or code punctuation) to avoid
    # false positives on queries like "working-class families".
    _AMBIGUOUS = {'class', 'method'}

    # Check for code-specific punctuation (braces, arrows, semicolons, etc.)
    # NOTE: parentheses are intentionally NOT treated as code punctuation —
    # they appear in ordinary English queries ("(e.g. X)") and the engine's
    # context-rewrite wraps topics in parens ("what is X (topic)"), which
    # would otherwise misroute factual questions to the code handler.
    has_code_punct = bool(re.search(r'[{}]|->|::|;|==', q))

    # "js" is shorthand for JavaScript in coding contexts
    if re.search(r'\bjs\b', q):
        return True

    # Multi-word coding phrases (reliable)
    # Check longest phrases first using WORD BOUNDARIES to avoid
    # false positives like "class" matching inside "classical".
    # Also normalize hyphens: "try-except" -> "try except" to match
    # the keyword set which uses spaces. c++/c# need lookarounds (a `\b`
    # can't match after '+'/'#').
    q_norm = re.sub(r'[-–—]', ' ', q)
    # Plural tolerance: "pointers", "structs", "interfaces" match the
    # singular keywords. Simple trailing-s strip; false positives ("has"
    # -> "ha") simply don't match any keyword, so they're harmless.
    q_plural = re.sub(r'\b(\w+)s\b', r'\1', q_norm)
    sorted_kw = sorted(_CODING_KEYWORDS_STRICT, key=len, reverse=True)

    unambiguous_match = False
    ambiguous_count = 0
    for kw in sorted_kw:
        kw_re = (r'(?<![a-z0-9])' + re.escape(kw) + r'(?![a-z0-9])'
                 if kw in ('c++', 'c#', 'node.js') else
                 r'\b' + re.escape(kw) + r'\b')
        if re.search(kw_re, q_norm) or re.search(kw_re, q_plural):
            if kw in _AMBIGUOUS:
                ambiguous_count += 1
            else:
                unambiguous_match = True

    # If we have at least one unambiguous keyword + OR code punctuation
    # OR two ambiguous keywords, treat as coding.
    if unambiguous_match or has_code_punct:
        return True
    return ambiguous_count >= 2


# ── Main Lookup ────────────────────────────────────────────────────────────

def code_lookup(query: str) -> "str | None":
    """Look up a coding query in local knowledge base, fallback to Stack API.

    Args:
        query: The user's coding question.

    Returns:
        Answer with code example if found, else None.
    """
    q = query.lower().strip()
    q = re.sub(r'[`\'\"\u201c\u201d\u2018\u2019]', '', q)

    # 1. Local knowledge base
    entries = _load_coding_knowledge()
    best = None
    best_len = 0
    _query_lang = detect_query_lang(query)

    _FILLER = {'actually', 'basically', 'essentially', 'really',
               'literally', 'honestly', 'just', 'simply', 'please',
               'do', 'does', 'did', 'i', 'you', 'we', 'they', 'he', 'she', 'it',
               'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
               'can', 'could', 'would', 'should', 'will', 'shall', 'may', 'might',
               'my', 'your', 'our', 'their', 'its', 'his', 'her',
               'also', 'very', 'much', 'many', 'some', 'any', 'every', 'each',
               'all', 'both', 'most', 'more', 'other', 'such',
               'what', 'how', 'why', 'when', 'where', 'which', 'who',
               'tell', 'explain', 'describe', 'show', 'give', 'need', 'want',
               'help', 'thanks', 'thank', 'way', 'ways',
               'quite', 'rather', 'somewhat',
               'or', 'and', 'but', 'not', 'so', 'then', 'now',
               'have', 'has', 'had', 'been', 'being', 'be', 'get', 'got',
               'use', 'used', 'using', 'make', 'made', 'making',
               'write', 'writes', 'writing', 'written', 'called', 'call', 'like',
               'into', 'over', 'than',}
    # Also normalize common grammatical patterns
    q_norm = q
    _NORMALIZE = [
        (r'\bhow\s+to\b', 'how to'),
        (r'\bhow\s+do\s+i\b', 'how to'),
        (r'\bhow\s+can\s+i\b', 'how to'),
        (r'\bhow\s+would\s+i\b', 'how to'),
        (r'\bhow\s+does\s+one\b', 'how to'),
        # Expand "whats"/"whos" etc. so patterns using "what is" match
        (r'\bwhats\b', 'what is'),
        (r'\bwhos\b', 'who is'),
        (r'\bwheres\b', 'where is'),
        (r'\bwhens\b', 'when is'),
        (r'\bwhys\b', 'why is'),
        (r'\bhow s\b', 'how is'),
        # Keep "in <language>" intact to match KB patterns
        (r'\b(?:using|with\s+the)\s+', ''),
        (r'\b(?:properly|efficiently|effectively|correctly)\b', ''),
        # Normalize hyphens in compound terms like "try-except" -> "try except"
        (r'[-–—]', ' '),
        # Normalize nouns: plural -> singular (so patterns match both forms)
        (r'\berrors\b', 'error'),
        (r'\bhandles\b', 'handle'),
        (r'\bhandling\b', 'handle'),
        (r'\bfunctions\b', 'function'),
        (r'\barrays\b', 'array'),
        (r'\blists\b', 'list'),
        (r'\bvalues\b', 'value'),
        (r'\bnums\b', 'number'),
        (r'\bstrings\b', 'string'),
        (r'\bobjects\b', 'object'),
        (r'\bdecorators\b', 'decorator'),
        (r'\blogging\b', 'log'),
        (r'\blogged\b', 'log'),
        (r'\blogs\b', 'log'),
        (r'\bsorting\b', 'sort'),
        (r'\bsorted\b', 'sort'),
        (r'\bmerging\b', 'merge'),
        (r'\bmerged\b', 'merge'),
        # Normalize punctuation: remove commas, semicolons, and extra spaces
        (r'[,;:()]+', ' '),
        (r'\s+', ' '),
    ]
    for pat, repl in _NORMALIZE:
        q_norm = re.sub(pat, repl, q_norm).strip()

    # Build multiple query variants
    # Normalize all variants: hyphens -> spaces, commas -> spaces
    def _norm_variant(t):
        t = re.sub(r'[-–—]', ' ', t)
        t = re.sub(r'[,;:()]+', ' ', t)
        t = re.sub(r'\s+', ' ', t).strip()
        return t
    variants = [_norm_variant(q)]
    if q_norm and q_norm != q:
        variants.append(_norm_variant(q_norm))
    q_simple = ' '.join(w for w in q_norm.split() if w not in _FILLER) if q_norm else ''
    if q_simple and q_simple != q_norm:
        variants.append(_norm_variant(q_simple))
    q_simple2 = ' '.join(w for w in q.split() if w not in _FILLER)
    if q_simple2 and q_simple2 != q:
        variants.append(_norm_variant(q_simple2))

    # Candidate pre-filter (exact phase): an escaped-literal pattern can only
    # match a variant containing every one of its words. For each variant, take
    # its rarest word's candidate list and union across variants, then verify
    # each entry's word set is fully contained in the variant word union.
    _variant_words = set()
    _candidate_indices = set()
    for _v in variants:
        if not _v or len(_v) < 3:
            continue
        _vwords = _code_word_tokens(_v)
        if not _vwords:
            continue
        _variant_words |= _vwords
        _vrarest = min(_vwords, key=lambda w: len(_CODE_WORD_INDEX.get(w, ())))
        _candidate_indices |= set(_CODE_WORD_INDEX.get(_vrarest, ()))

    for _ci in sorted(_candidate_indices):
        pattern, answer = entries[_ci]
        _entry_words = _CODE_ENTRY_WORDS[_ci]
        if _entry_words is not None and not (_entry_words <= _variant_words):
            continue
        for variant in variants:
            if not variant or len(variant) < 3:
                continue
            m = pattern.search(variant)
            if m:
                # Language-aware scoring: a same-language entry with a shorter
                # span beats a different-language entry with a longer span
                # ("reverse a linked list in c++" must not match the Python
                # entry first).
                _adjusted = len(m.group(0)) + _lang_adjust(
                    _query_lang, getattr(pattern, 'pattern', ''))
                if _adjusted > best_len:
                    best_len = _adjusted
                    best = answer

    if best:
        # Post-process the answer: substitute topic from the query
        # into any __TOPIC__ placeholders in the answer text.
        # This lets KB entries provide generic templates that get
        # customized with the user's specific topic.
        if '__TOPIC__' in best:
            try:
                # Extract the topic from the query (the subject the user is asking about)
                # Try multiple patterns to find the topic
                topic = None
                topic_patterns = [
                    (r'(?:about|covering|for|on|regarding)\s+'
                     r'(.+?)(?:\.\s*|\?\s*|\,\s*(?:including|covering|with|that|which|featuring)|$)'),
                    (r'(?:page|site|portfolio)\s+(?:about|for|covering|on)\s+'
                     r'(.+?)(?:\.\s*|\?\s*|$)'),
                    r'"([^"]+)"',
                    r"['\"]([^'\"]+?)['\"]\s*(?:theme|style|layout)",
                ]
                for p in topic_patterns:
                    m = re.search(p, query, re.IGNORECASE)
                    if m:
                        topic = m.group(1).strip().rstrip('.!?,;:')
                        # Clean trailing clauses
                        topic = re.sub(r'\s+(?:with|and|using|featuring|that|which|where)\s+.*$', '', topic)
                        # Clean leading articles
                        topic = re.sub(r'^(?:a|an|the)\s+', '', topic)
                        if topic and len(topic) > 2:
                            break
                
                if topic:
                    best = best.replace('__TOPIC__', topic.title())
                else:
                    # Fallback: replace placeholder with extracted query keywords
                    # Look for the main noun phrases
                    words = [w for w in re.findall(r'\b[A-Z][a-z]+\b', query) if len(w) > 2]
                    if words:
                        best = best.replace('__TOPIC__', ' '.join(words))
                    else:
                        # Last resort: just use a clean version of the query
                        clean = re.sub(r'^(?:create|make|write|build|design)\s+(?:a|an|the|me|us)?\s*', '', query.lower())
                        clean = re.sub(r'\s+with\s+.*$', '', clean).strip()
                        if clean:
                            best = best.replace('__TOPIC__', clean.title())
            except (IndexError, ValueError):
                pass
        return best

    # 2. Keyword-based fallback: if no exact match, find entries with
    # high word overlap with the query.
    if not best:
        # IMPORTANT: Do NOT include programming language names or code concepts
        # in stop words — they are key discriminators between coding entries.
        # Removing them caused matches like 'map function javascript' matching
        # 'async function javascript' because 'function' and 'javascript'
        # were both treated as meaningless filler.
        _STOP_WORDS = {'how', 'what', 'why', 'when', 'where', 'which',
                       'does', 'this', 'that', 'with', 'from', 'they',
                       'have', 'been', 'tell', 'about', 'just', 'will',
                       'can', 'get', 'use', 'also', 'into', 'over',
                       'than', 'then', 'way', 'ways', 'need', 'like',
                       'one', 'two', 'many', 'some', 'any', 'every',
                       'code', 'program', 'example', 'tutorial', 'guide',
                       'learn', 'basic', 'simple', 'easy', 'quick',
                       'write', 'create', 'make', 'build', 'implement',
                       'item', 'element', 'key', 'set', 'call', 'return',
                       'work', 'want', 'using', 'used', 'based', 'show',
                       'give', 'take', 'know',
                       # Generic code nouns that appear in nearly every entry:
                       # without these, "check if a number is even" matches the
                       # prime entry on "function" + "number" alone.
                       'function', 'method', 'class',
                       # Common function words: without these, "what is the
                       # difference between X and Y" queries all share
                       # "difference between and" and match EACH OTHER
                       # ("react vs vue" matched "stack vs queue").
                       'the', 'a', 'an', 'and', 'or', 'but', 'not', 'so',
                       'of', 'to', 'in', 'on', 'at', 'by', 'for', 'is', 'are',
                       'was', 'were', 'be', 'being', 'do', 'did',
                       'between', 'vs', 'versus', 'difference', 'differences',
                       'similarities', 'similar', 'different', 'same', 'should',
                       'would', 'could', 'might', 'may', 'its', 'it', 'his', 'her',
                       'their', 'our', 'your', 'my', 'me', 'we', 'you', 'he', 'she',
                       'them', 'as', 'if', 'while', 'after', 'before',
                       'there', 'here', 'all', 'each', 'both',
                       'more', 'most', 'other', 'another', 'such', 'no', 'yes',
                       'good', 'great', 'best', 'help',
                       'explain', 'describe', 'please',
                       }
        # Use 3+ char words to catch important short coding terms like 'div', 'css', 'js', 'api'
        q_words = {w for w in re.findall(r'\b\w{3,}\b', q.lower())
                   if w not in _STOP_WORDS}
        # Two-letter terms that are decisive topic words: "regex to match an
        # IP address" must not match the "regex to match an email address"
        # entry just because both say "address".
        if re.search(r'\bip\s+address\b', q.lower()):
            q_words.add('ip')
        if re.search(r'\bhtml\s+(?:page|file)\b', q.lower()):
            q_words.add('html')
        if q_words:
            # Detect the language being asked about in the query
            query_lang = detect_query_lang(query)

            # Candidate pre-filter (fuzzy phase): the scorer rewards patterns
            # sharing query words, so restrict to entries whose pattern shares
            # at least one token with the query — plus substring-key expansion
            # (query word "api" should still reach patterns containing "apis"
            # or "api_key", mirroring the scorer's substring matching).
            _fuzzy_candidates = set()
            for _w in q_words:
                _fuzzy_candidates |= set(_CODE_WORD_INDEX.get(_w, ()))
            if _CODE_WORD_KEYS:
                for _w in q_words:
                    for _key in _CODE_WORD_KEYS:
                        if _w in _key:
                            _fuzzy_candidates |= _CODE_WORD_INDEX[_key]

            for _ci in sorted(_fuzzy_candidates):
                pattern, answer = entries[_ci]
                pattern_str = pattern.pattern.lower() if hasattr(pattern, 'pattern') else ''
                if not pattern_str:
                    continue

                # Topic-substantiation gate: a "write a python script to check
                # if a website is up" request must not match the "check if a
                # key exists in a dictionary" entry just because both share
                # "check" + "python". Require at least TWO THIRDS of the
                # query's topic words (non-stop, non-verb, non-language words)
                # to appear in the pattern OR the answer — terser patterns
                # like "how to sort a dictionary" still pass when their answer
                # covers "by value", while an unrelated entry that only shares
                # a generic word ("sum of numbers 1 to n" vs a "for loop"
                # entry that mentions "numbers") is rejected. When the query
                # has no topic words ("sort a list in python"), fall back to
                # the plain overlap rules below.
                _topic_words = (q_words - _TASK_VERB_SET - _LANG_WORD_SET)
                if _topic_words:
                    answer_lower = answer.lower()[:600]
                    _topic_hits = sum(1 for w in _topic_words
                                      if w in pattern_str or w in answer_lower)
                    if _topic_hits * 3 < len(_topic_words) * 2:
                        continue

                # Count how many query words appear in the PATTERN
                pattern_overlap = sum(1 for w in q_words if w in pattern_str)
                
                # PENALTY: Count how many PATTERN-specific words (not found in query)
                # appear in the pattern. This prevents entries about unrelated topics
                # (e.g., 'palindromes') from matching queries that don't mention them
                # just because they share common words like 'list', 'string', etc.
                pattern_words = {w for w in re.findall(r'\b[a-zA-Z]{3,}\b', pattern_str)
                                 if w not in _STOP_WORDS}
                extraneous_words = pattern_words - q_words
                penalty = len(extraneous_words) * 5  # -5 per extraneous word
                
                # TASK-VERB PENALTY: for "do it for me" queries ("write a for
                # loop", "convert a string"), a pattern that doesn't contain the
                # query's action verb is a concept entry, not an answer to the
                # task ("what is the event loop" must not answer "write a for
                # loop in javascript"). 100 points — decisive enough that the
                # language bonus can't rescue it; the query then falls through
                # to the code synthesizer.
                _task_verbs = [v for v in _TASK_VERBS
                               if re.search(r'\b' + v + r'\w*\b', q)]
                if _task_verbs and not any(v in pattern_str for v in _task_verbs):
                    penalty += 100  # -100 for missing the task verb
                
                # Count answer overlap (weighted lower)
                if not _topic_words:
                    answer_lower = answer.lower()[:300]
                answer_overlap = sum(1 for w in q_words if w in answer_lower)

                # MISSING-TOPIC PENALTY: a decisive topic word the entry
                # doesn't cover at all ("regex to match an IP address" vs the
                # email-address entry) is -40 each — bigger than any overlap
                # the shared words can earn, so the wrong entry loses and the
                # query falls through to the synthesizer.
                if _topic_words:
                    _missing = [w for w in _topic_words
                                if w not in pattern_str and w not in answer_lower]
                    penalty += len(_missing) * 40
                
                # Combined: pattern match is paramount, answer match is tiebreaker
                # Penalty: subtract for extraneous pattern words not in query
                combined = pattern_overlap * 10 + answer_overlap - penalty

                # Minimum-overlap gate: an entry sharing only ONE common word
                # with the query (e.g. just "python") is not a real match —
                # without this, "how to check python version" matched a
                # palindrome function and "git pull" matched dictionary
                # iteration. Requiring two pattern-word overlaps stops
                # plausible-looking wrong answers.
                if pattern_overlap < 2:
                    continue

                # Language bonus: if query asks for a specific language, prefer
                # entries whose pattern mentions that language. This prevents
                # returning Python code when Java was requested (e.g., "binary search
                # in Java" matching a generic "implement binary search" Python entry).
                if query_lang and query_lang in _pattern_langs(pattern_str):
                    combined += 50  # Big bonus for matching the requested language

                # Language penalty for MISMATCH: If query asks for Java but
                # pattern mentions a different language, apply a penalty so
                # Python entries don't dominate over the requested language.
                if query_lang:
                    _plangs = _pattern_langs(pattern_str)
                    if _plangs and query_lang not in _plangs:
                        combined -= 30  # Penalty for wrong language

                if combined > best_len:
                    best_len = combined
                    best = answer

    if best:
        return best

    # 3. Stack dataset API (last resort) — searches HuggingFace stack-v3 dataset.
    # Heavily gated: the dataset search is slow (up to a minute per call) and
    # frequently returns unrelated files for natural-language questions. Only
    # run when the query looks like an actual "give me code / example / snippet"
    # request, and only keep results whose content actually overlaps the
    # query's significant terms — otherwise an irrelevant notebook or
    # unrelated source file would be presented as the answer.
    if re.search(r'\b(?:show|give|provide|write|need|find)\s+(?:me\s+)?(?:an?\s+)?(?:code|example|example\s+code|snippet|implementation|function)\b', q, re.IGNORECASE):
        try:
            results = _search_stack(query, max_files=1)
            if results:
                q_terms = [w for w in re.findall(r'\b[a-z]{4,}\b', q.lower())
                           if w not in {'what', 'how', 'why', 'when', 'where',
                                        'which', 'would', 'should', 'could',
                                        'with', 'from', 'have', 'been', 'about',
                                        'this', 'that', 'their', 'them', 'there',
                                        'your', 'code', 'example', 'python',
                                        'javascript', 'java', 'want', 'need',
                                        'show', 'give', 'write', 'find',
                                        'implement', 'function', 'snippet',
                                        'using', 'use', 'used'}]
                for r in results:
                    lang = r.get('language', '')
                    path = r.get('path', '')
                    content = r.get('content', '')
                    content_lower = content.lower()
                    overlap = sum(1 for w in q_terms if w in content_lower)
                    # Require real topic overlap (or a perfect title match) or
                    # skip — a code dump about an unrelated subject is worse
                    # than no answer at all.
                    if q_terms and overlap < 2:
                        continue
                    snippet = '\n'.join(content.split('\n')[:25])
                    if len(snippet) > 1800:
                        snippet = snippet[:1800]
                    if snippet:
                        header = f"Here's an example from `{path}`:" if path else "Here's a code example:"
                        return f"{header}\n\n```{lang}\n{snippet}\n```"
        except (OSError, ValueError):
            pass

    return None


# ── High-level helpers used by the engine ──────────────────────────────────

# Terms that mark a topic as programming-related even when is_coding_query()
# misses (e.g. "how to read a csv file with pandas" mentions neither a
# function nor code syntax). Used to keep code questions out of the Wikipedia
# fallback, which returns unrelated articles for code topics.
_CODING_TOPIC_RE = re.compile(
    r'\b(?:python|javascript|typescript|java|c\+\+|c#|golang|rust|ruby|'
    r'php|swift|kotlin|sql|bash|shell|html|css|js|ts|py)\b|'
    r'\b(?:git|docker|npm|pip|pandas|numpy|flask|django|fastapi|express|'
    r'react|vue|node|curl|api|http|url|csv|json|xml|regex|regexp|database|'
    r'function|method|class|variable|array|object|string|list|dict|dictionary|'
    r'algorithm|data\s+structure|web\s+scrap|endpoint|query|snippet|'
    r'code|program|script|syntax|bug|debug|deploy|commit|branch|repo|'
    r'framework|library|backend|frontend|server|client|async|thread|'
    r'cache|serialize|parse|encrypt|hash|website|web\s*site|web\s*page|'
    r'landing\s*page|homepage|portfolio|static\s+site|process|port|'
    r'kill|count|length|character|characters|letters?|filename|directory|'
    r'celsius|centigrade|fahrenheit|kelvin|in\s+go|'
    r'palindrome|anagram|vowel|hashtag|slug|'
    r'log\s+file|tail|gitignore|'
    r'dockerfile|docker[- ]compose|github\s+actions|'
    r'setup\.py|pyproject\.toml|requirements\.txt|package\.json|'
    r'cron|systemd|ffmpeg|rsync|inotify|yaml|yml|toml|ini|'
    r'kubectl|xargs|awk|sed|jq|matplotlib|seaborn|scipy|'
    r'cherry[- ]?pick|duplicate\s+lines|unique\s+lines|'
    r'disk\s+space|disk\s+usage|pods?|terraform|ansible|axios|tar|'
    r'rate\s+limiter|url\s+shortener|task\s+queue|argparse|sqlalchemy|'
    r'jest|ownership|pointer|struct|trait|interface|grep|scikit[- ]?learn|'
    r'sklearn|'
    r'(?:sort|reverse|split|join|parse|count|check|find|remove|convert)\s+'
    r'(?:a|an|the|by|from)\b)',
    re.IGNORECASE)

# Phrases that make a query a "do it for me" code task rather than a concept
# question: "write a function to ...", "how do I ... in python", "sql to ...".
_CODE_TASK_RE = re.compile(
    r'\b(?:write|implement|create|make|build|fix|debug|generate|produce|'
    r'give|show|need|find|count|check|extract|sort|reverse|remove|delete|'
    r'rename|convert|read|print|parse|list|search|validate|split|join|get|'
    r'replace|match|merge|concatenate|concat|flatten|dedupe|deduplicate|'
    r'duplicate|append|insert|update|group|aggregate|rank|filter|map|reduce|'
    r'watch|monitor|follow|schedule|backup|sync|archive|download|upload|hash|'
    r'encode|decode|encrypt|decrypt|compress|zip|unzip|compile|test|'
    r'deploy|containerize|dockerize|query|format|normalize|round|truncate|'
    r'chain|iterate|loop|top|trim|return|calculate|compute|strip)\b.*'
    r'\b(?:code|function|program|script|snippet|class|query|sql|regex|'
    r'regexp|algorithm|loop|parser|api|website|web\s*site|web\s*page|'
    r'landing\s*page|homepage|html|css|portfolio|string|array|list|dict|'
    r'dictionary|object|file|json|csv|character|number|data|process|port|'
    r'url|email|line|word|sentence|element|item|occurrence|tree|node|graph|'
    r'stack|queue|heap|trie|set|tuple|map|interval|substring|prefix|matrix|'
    r'vector|field|row|record|table|column|key|value|address|gitignore|'
    r'dockerfile|docker|compose|service|job|task|config|directory|folder|'
    r'log|database|index|file|div|button|footer|navbar|sidebar)(?:s|es)?\b|'
    r'\bhow\s+(?:do|to|can|would|should|could)\b.*\b(?:python|javascript|'
    r'java|c\+\+|sql|git|node|flask|react|api|file|array|list|json|csv|'
    r'regex|website|web\s*site|web\s*page|html|css|process|port|string|'
    r'url|email|data|count|kill|extract|merge|hash|encode|decode|sort|'
    r'backup|compress|unzip|deploy|container|docker|grep|tar|rsync|'
    r'rebase|cherry[- ]?pick|amend|revert|undo|div|flexbox|button|footer)\b|'
    r'\b(?:celsius|centigrade|fahrenheit|miles?|kilometers?|km|pounds?|lbs?|'
    r'kg|kilograms?|inches?|feet|yards?|meters?|gallons?|liters?)\s+'
    r'(?:to|into)\s+(?:fahrenheit|celsius|miles?|kilometers?|km|pounds?|'
    r'lbs?|kg|kilograms?|inches?|feet|yards?|meters?|gallons?|liters?)\b',
    re.IGNORECASE)


def looks_like_coding_topic(text: str) -> bool:
    """True when the text mentions a language, library, tool, or code term.

    Broader than is_coding_query: used to keep code questions away from the
    Wikipedia fallback, where "read a csv with pandas" would fetch the giant
    panda bear article.
    """
    if not text or not text.strip():
        return False
    return bool(_CODING_TOPIC_RE.search(text))


def looks_like_code_task(query: str) -> bool:
    """True when the query asks for code to be written (not a concept)."""
    return bool(_CODE_TASK_RE.search(query))


# Concept questions: "explain what a decorator does", "what is a closure",
# "how do generators work" — the concept noun follows a fixed set of wrappers.
_CONCEPT_EXTRACT_RE = re.compile(
    r'\b(?:what\s+(?:is|are|was|were|does|do|is\s+a|are\s+a|exactly\s+is)'
    r'\s+(?:a\s+|an\s+|the\s+)?'
    r'|explain\s+(?:what\s+)?(?:a\s+|an\s+|the\s+|how\s+)?'
    r'|define\s+(?:a\s+|an\s+|the\s+)?'
    r'|describe\s+(?:a\s+|an\s+|the\s+)?'
    r'|how\s+(?:do|does|to)\s+(?:a\s+|an\s+|the\s+)?'
    r'|what\s+does\s+(?:a\s+|an\s+|the\s+)?'
    r')([a-z][a-z0-9_-]*(?:\s+[a-z][a-z0-9_-]*){0,3})'
    r'(?:\s+(?:do|does|work|works|mean|means|in|with|and|or|is|are))?$',
    re.IGNORECASE,
)

# Concept words that must never be treated as the concept itself.
_CONCEPT_STOP = {
    'the', 'a', 'an', 'this', 'that', 'it', 'what', 'how', 'why', 'when',
    'where', 'which', 'who', 'code', 'program', 'function', 'do', 'does',
    'work', 'works', 'mean', 'means', 'language', 'python', 'javascript',
    'java', 'c++', 'c#', 'go', 'rust', 'in', 'with', 'and', 'or', 'is',
    'are', 'explain', 'define', 'describe', 'please', 'me', 'my',
}


def extract_concept(query: str) -> "str | None":
    """Pull the concept noun phrase out of a concept question.

    'explain what a decorator does' -> 'decorator'
    'what is the difference between a list and a tuple' -> None (not single)
    """
    if not re.search(r'\b(?:what|explain|define|describe|how)\b', query,
                     re.IGNORECASE):
        return None
    if re.search(r'\bdifference\s+between\b', query, re.IGNORECASE):
        return None
    m = _CONCEPT_EXTRACT_RE.search(query.strip())
    if not m:
        return None
    concept = m.group(1).strip().lower()
    # strip trailing prepositions like "in" ("what is a generator in python")
    concept = re.sub(r'\s+(?:in|with|using)\s+.*$', '', concept).strip()
    # strip trailing helper verbs ("explain what a decorator does")
    concept = re.sub(r'\s+(?:work|works|mean|means|do|does)$', '', concept).strip()
    words = concept.split()
    if not words or len(concept) > 40:
        return None
    if any(w in _CONCEPT_STOP for w in words):
        return None
    return concept


def concept_lookup(query: str) -> "str | None":
    """Answer a concept question directly from the code KB patterns.

    Searches entries whose PATTERN contains the concept noun, preferring
    definition-style patterns ('what is X', 'explain X'). This fixes queries
    like 'explain what a decorator does' that carry too few shared words for
    the fuzzy scorer but are clearly about one concept.
    """
    concept = extract_concept(query)
    if not concept:
        return None
    entries = _load_coding_knowledge()
    if not entries:
        return None
    concept_words = set(concept.split())
    best = None
    best_score = 0
    for pattern, answer in entries:
        try:
            ps = pattern.pattern.lower()
        except AttributeError:
            continue
        # every concept word must appear in the pattern
        if not all(w in ps for w in concept_words):
            continue
        # the pattern must be a definition-style entry, not an incidental
        # mention ("map with a lambda" is not a definition of lambda)
        if not re.match(r'^(?:what|explain|define|describe|how)\b', ps):
            continue
        score = len(ps)
        if concept in ps[:50]:
            score += 100
        if len(concept_words) >= 2:
            score += 50
        if score > best_score:
            best_score = score
            best = answer
    return best


# Library/framework names that mean the KB's specialized entry is likely
# better than the synthesizer's generic template ("read a csv with pandas"
# should stay a pandas answer, not a csv-module one).
_LIBRARY_TOKENS = frozenset("""pandas numpy matplotlib seaborn requests
flask django fastapi sqlalchemy tornado bottle aiohttp httpx express react vue
angular svelte next.js nuxt remix axios superagent jquery bootstrap tailwind d3
tensorflow pytorch torch keras opencv scikit-learn sklearn selenium
beautifulsoup bs4 scrapy pygame pillow boto3 psycopg2 celery redis gunicorn
uvicorn node.js nodejs """.split())


def _mentions_library(query: str) -> bool:
    """True when the query names a specialized library/framework."""
    q = query.lower()
    for tok in _LIBRARY_TOKENS:
        if re.search(r'(?<![a-z0-9])' + re.escape(tok) + r'(?![a-z0-9])', q):
            return True
    return False


def smart_code_answer(query: str) -> "str | None":
    """Answer a coding question from the curated KB first, then by synthesis.

    Never touches Wikipedia: for code topics Wikipedia returns unrelated
    articles ("pandas" → giant panda). The code generator synthesizes code
    for the common tasks that the KB doesn't cover.

    Priority rules:
    - When the query names a language, the answer must present code in that
      language; the synthesizer's language-exact templates win whenever the
      KB answer is prose or in a different language.
    - When the KB matches the requested language too, it normally wins (its
      answers are more explanatory) EXCEPT for plain imperative "write X"
      requests with no specialized library involved — there the synthesizer
      wins because its templates are hand-verified and task-exact.
    - Queries that name a library (pandas, flask, …) keep the KB answer.
    """
    ans = code_lookup(query)
    q_lang = detect_query_lang(query)
    gen = None
    try:
        from cos.code_gen import generate_code
        gen = generate_code(query)
    except Exception:
        pass
    g_lang = answer_language(gen) if gen else None
    a_lang = answer_language(ans) if ans else None
    if q_lang and g_lang:
        if a_lang == q_lang:
            # KB already delivers the right language — keep it, unless this
            # is a plain imperative request the synthesizer covers exactly.
            if (gen and looks_like_code_task(query)
                    and not _mentions_library(query)):
                return gen
            return ans
        if g_lang == q_lang:
            return gen
        # g_lang != q_lang: the language mention is incidental to the task
        # ("a .gitignore for a python project" -> python, but the artifact
        # is a bash/text file). A task-matched synthesis still beats prose.
        if gen and ans and not a_lang and looks_like_code_task(query):
            return gen
    elif gen and ans and not a_lang and looks_like_code_task(query):
        # No language named but a clear "write code" request: real code
        # beats prose.
        return gen
    elif (gen and ans and a_lang and g_lang and a_lang != g_lang
          and not q_lang and looks_like_code_task(query)
          and not _mentions_library(query)):
        # No language named; the KB fuzzy-matched an entry in a DIFFERENT
        # language than the synthesizer's task-exact template ("write a
        # regex for a valid ip address" must not return the JS email
        # regex). The task-exact template wins.
        return gen
    elif (gen and ans and a_lang and g_lang and a_lang == g_lang
          and looks_like_code_task(query) and not _mentions_library(query)
          and not q_lang):
        # No language named and both sides agree on the language: the
        # synthesizer's task-exact template wins over a loosely-matched KB
        # entry ("how do i commit changes with git" must not return the
        # git-undo recipe).
        return gen
    if ans:
        return ans
    if gen:
        return gen
    # Last KB attempt: definition-style concept lookup for "explain what a
    # decorator does" style questions the fuzzy scorer can't reach.
    return concept_lookup(query)


# The coding KB is loaded lazily on the first code query (via
# _load_coding_knowledge inside code_lookup) rather than at import time,
# so plain chat processes never pay for it.
