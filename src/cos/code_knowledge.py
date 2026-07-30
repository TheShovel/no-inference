"""
COS Code Knowledge — Answers coding questions using:
  1. Knowledge files in data/knowledge/coding/*.json
  2. HuggingFace Datasets Server API (Stack-v3 dataset) as fallback
"""

import json
import os
import re
import urllib.request
import urllib.parse
from pathlib import Path
from typing import List, Optional, Tuple

# ── Stack dataset API ──────────────────────────────────────────────────────

_STACK_DATASET = "HuggingFaceCode/stack-v3-train"
_DATASETS_SERVER = "https://datasets-server.huggingface.co"
_STACK_CACHE = {}


def _search_stack(query: str, max_files: int = 2) -> List[dict]:
    """Search Stack dataset for code relevant to the query."""
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
            with urllib.request.urlopen(req, timeout=60) as resp:
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
        except Exception:
            continue

    _STACK_CACHE[cache_key] = results
    return results


def _extract_code_terms(query: str) -> List[str]:
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


def _load_coding_knowledge():
    """Load all coding knowledge entries from data/knowledge/coding/"""
    global _KB_CACHE
    if _KB_CACHE is not None:
        return _KB_CACHE

    if not _KNOWLEDGE_DIR.exists():
        _KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        _KB_CACHE = []
        return []

    entries = []
    for path in sorted(_KNOWLEDGE_DIR.glob('*.json')):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
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
                        entries.append((regex, full))
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
    'regex', 'regular expression', 'parsing',
    'crud operation', 'mvc pattern', 'design pattern',
    'recursion', 'recursive function', 'callback', 'promise',
    'async await', 'concurrency', 'parallelism',
    'multithreading', 'race condition', 'deadlock',
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
    'write a function', 'write a program', 'write code',
    'how to code', 'how to program',
    'center a div', 'responsive layout',
    'handle exception', 'handle error',
    'merge array', 'merge list', 'merge dict',
}


def is_coding_query(query: str) -> bool:
    """Check if a query is clearly a coding/programming question.

    Conservative: uses multi-word patterns and specific coding terms
    to avoid flagging general questions as coding questions.
    """
    q = query.lower().strip()

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

    # Check for code-specific punctuation (braces, parens, semicolons, etc.)
    has_code_punct = bool(re.search(r'[{}\(\)]|->|::|;', q))

    # Multi-word coding phrases (reliable)
    # Check longest phrases first using WORD BOUNDARIES to avoid
    # false positives like "class" matching inside "classical".
    # Also normalize hyphens: "try-except" -> "try except" to match
    # the keyword set which uses spaces.
    q_norm = re.sub(r'[-–—]', ' ', q)
    sorted_kw = sorted(_CODING_KEYWORDS_STRICT, key=len, reverse=True)

    unambiguous_match = False
    ambiguous_count = 0
    for kw in sorted_kw:
        if re.search(r'\b' + re.escape(kw) + r'\b', q_norm):
            if kw in _AMBIGUOUS:
                ambiguous_count += 1
            else:
                unambiguous_match = True

    # If we have at least one unambiguous keyword + OR code punctuation
    # OR two ambiguous keywords, treat as coding.
    if unambiguous_match or has_code_punct:
        return True
    if ambiguous_count >= 2:
        return True

    return False


# ── Main Lookup ────────────────────────────────────────────────────────────

def code_lookup(query: str) -> Optional[str]:
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
               'help', 'please', 'thanks', 'thank', 'way', 'ways',
               'actually', 'basically', 'essentially', 'literally', 'really',
               'just', 'simply', 'quite', 'rather', 'somewhat',
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

    for pattern, answer in entries:
        for variant in variants:
            if not variant or len(variant) < 3:
                continue
            m = pattern.search(variant)
            if m and len(m.group(0)) > best_len:
                best_len = len(m.group(0))
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
                    r'(?:about|covering|for|on|regarding)\s+'
                    r'(.+?)(?:\.\s*|\?\s*|\,\s*(?:including|covering|with|that|which|featuring)|$)',
                    r'(?:page|site|portfolio)\s+(?:about|for|covering|on)\s+'
                    r'(.+?)(?:\.\s*|\?\s*|$)',
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
            except Exception:
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
                       'give', 'take', 'know'}
        # Use 3+ char words to catch important short coding terms like 'div', 'css', 'js', 'api'
        q_words = set(w for w in re.findall(r'\b\w{3,}\b', q.lower())
                      if w not in _STOP_WORDS)
        if q_words:
            # Detect the language being asked about in the query
            # Used to prefer entries that match the requested language
            _LANG_WORDS = {'python', 'javascript', 'java', 'c++', 'c#', 'typescript',
                           'rust', 'go', 'golang', 'ruby', 'swift', 'kotlin', 'php'}
            query_lang = next((w for w in q_words if w in _LANG_WORDS), None)
            
            for pattern, answer in entries:
                pattern_str = pattern.pattern.lower() if hasattr(pattern, 'pattern') else ''
                
                # Count how many query words appear in the PATTERN
                pattern_overlap = sum(1 for w in q_words if w in pattern_str)
                
                # PENALTY: Count how many PATTERN-specific words (not found in query)
                # appear in the pattern. This prevents entries about unrelated topics
                # (e.g., 'palindromes') from matching queries that don't mention them
                # just because they share common words like 'list', 'string', etc.
                pattern_words = set(w for w in re.findall(r'\b[a-zA-Z]{3,}\b', pattern_str)
                                   if w not in _STOP_WORDS)
                extraneous_words = pattern_words - q_words
                penalty = len(extraneous_words) * 5  # -5 per extraneous word
                
                # Count answer overlap (weighted lower)
                answer_lower = answer.lower()[:300]
                answer_overlap = sum(1 for w in q_words if w in answer_lower)
                
                # Combined: pattern match is paramount, answer match is tiebreaker
                # Penalty: subtract for extraneous pattern words not in query
                combined = pattern_overlap * 10 + answer_overlap - penalty
                
                # Language bonus: if query asks for a specific language, prefer
                # entries whose pattern mentions that language. This prevents
                # returning Python code when Java was requested (e.g., "binary search
                # in Java" matching a generic "implement binary search" Python entry).
                if query_lang and query_lang in pattern_str:
                    combined += 50  # Big bonus for matching the requested language

                # Language penalty for MISMATCH: If query asks for Java but
                # pattern mentions a different language, apply a penalty so
                # Python entries don't dominate over the requested language.
                if query_lang:
                    for other_lang in _LANG_WORDS:
                        if other_lang != query_lang and other_lang in pattern_str:
                            combined -= 30  # Penalty for wrong language
                            break

                if combined > best_len:
                    best_len = combined
                    best = answer

    if best:
        return best

    # 3. Stack dataset API (last resort) — searches HuggingFace stack-v3 dataset
    try:
        results = _search_stack(query, max_files=1)
        if results:
            parts = []
            for r in results:
                lang = r.get('language', '')
                path = r.get('path', '')
                content = r.get('content', '')
                snippet = '\n'.join(content.split('\n')[:25])
                if len(snippet) > 1800:
                    snippet = snippet[:1800]
                if snippet:
                    header = f"Here's an example from `{path}`:" if path else "Here's a code example:"
                    parts.append(f"{header}\n\n```{lang}\n{snippet}\n```")
            if parts:
                return "\n\n".join(parts)
    except Exception:
        pass

    return None


# Pre-load coding knowledge at import time
_load_coding_knowledge()
