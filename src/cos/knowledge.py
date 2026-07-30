"""
COS Knowledge Base — Dynamically loads knowledge from data files.

Knowledge is stored as JSON files in data/knowledge/ organized by category:
  data/knowledge/
    science/       -- biology, physics, chemistry, food, human body
    geography/     -- capitals, countries, oceans, mountains
    history/       -- world events, famous people
    technology/    -- computers, internet, programming
    conversation/  -- greetings, small talk, common phrases
    general/       -- everything else

Each JSON file contains an array of entries:
  [{"q": ["question pattern 1", "pattern 2"], "a": "Answer text"}, ...]

To add knowledge: just create a new JSON file in the right category.
No code changes needed — it's loaded automatically at startup.
"""

import json
import os
import re
import glob
from pathlib import Path

# ── Knowledge directory ──────────────────────────────────────────────────────
# Path relative to this file: data/knowledge/
_KNOWLEDGE_DIR = Path(__file__).parent.parent.parent / 'data' / 'knowledge'


def _load_knowledge(base_dir=None):
    """Load all knowledge entries from the knowledge directory.

    Scans all .json files recursively, loads each entry, and returns
    a list of (compiled_regex, answer) tuples.

    Args:
        base_dir: Path to the knowledge directory. Defaults to data/knowledge/

    Returns:
        List of (pattern_regex, answer_text) tuples
    """
    if base_dir is None:
        base_dir = _KNOWLEDGE_DIR

    if not base_dir.exists():
        print(f"  Knowledge directory not found: {base_dir}")
        return []

    entries = []
    # Exclude the 'templates/' subdirectory which contains context-aware
    # conversational templates (not KB entries). These use 'triggers' and 'template'
    # fields instead of 'q'/'a' format, and their generic triggers like "what is"
    # can pollute KB lookups.
    if base_dir != _KNOWLEDGE_DIR:
        json_files = sorted(p for p in base_dir.rglob('*.json') if not p.name.startswith('.'))
    else:
        json_files = sorted(p for p in base_dir.rglob('*.json') if not p.name.startswith('.') and '/templates/' not in str(p) and '\\templates\\' not in str(p))

    if not json_files:
        print(f"  No JSON knowledge files found in {base_dir}")
        return []

    for path in json_files:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  Warning: Could not load {path}: {e}")
            continue

        if not isinstance(data, list):
            print(f"  Warning: {path} should contain a JSON array")
            continue

        loaded = 0
        for entry in data:
            if not isinstance(entry, dict):
                continue
            questions = entry.get('q', entry.get('patterns', []))
            answer = entry.get('a', entry.get('answer', ''))

            if not questions or not answer:
                continue

            # If questions is a string, wrap in list
            if isinstance(questions, str):
                questions = [questions]

            # Compile patterns into regexes (case-insensitive)
            for q_text in questions:
                q_clean = q_text.strip()
                if not q_clean:
                    continue
                try:
                    # Check if pattern contains explicit regex syntax (backslash escapes)
                    # Only treat as raw regex if the author intentionally used regex
                    # constructs like \b, \s, \d, etc. Otherwise escape the pattern
                    # to prevent accidental regex metacharacters (e.g., '+' in 'c++'
                    # becoming a quantifier, or '?' in questions becoming optional).
                    has_regex_backslash = '\\' in q_clean
                    if has_regex_backslash:
                        # Contains intentional regex escapes — use as-is
                        regex = re.compile(q_clean, re.IGNORECASE)
                    else:
                        # Escape the pattern so 'c++' matches literally 'c++',
                        # and 'What is X?' matches 'What is X?' literally.
                        # Use word boundary for single short words.
                        words = q_clean.split()
                        if len(words) == 1 and len(q_clean) <= 5:
                            regex = re.compile(r'\b' + re.escape(q_clean) + r'\b', re.IGNORECASE)
                        else:
                            regex = re.compile(re.escape(q_clean), re.IGNORECASE)
                    entries.append((regex, answer))
                    loaded += 1
                except re.error as e:
                    print(f'  Warning: Bad pattern "{q_clean}": {e}')
                    continue

        if loaded > 0:
            # Print category summary
            rel_path = path.relative_to(base_dir.parent.parent if base_dir == _KNOWLEDGE_DIR else base_dir)
            pass  # quiet load by default

    return entries

# ── Load knowledge at module import time ─────────────────────────────────────
_KNOWLEDGE_CACHE = None

def get_all_knowledge():
    """Get all loaded knowledge entries, caching after first load."""
    global _KNOWLEDGE_CACHE
    if _KNOWLEDGE_CACHE is None:
        _KNOWLEDGE_CACHE = _load_knowledge()
        if _KNOWLEDGE_CACHE:
            print(f"  Loaded {len(_KNOWLEDGE_CACHE)} knowledge entries from data/knowledge/")
    return _KNOWLEDGE_CACHE

def reload():
    """Force reload of all knowledge from disk."""
    global _KNOWLEDGE_CACHE
    _KNOWLEDGE_CACHE = None
    return get_all_knowledge()


def lookup(query):
    """Look up a query in the dynamic knowledge base.

    Matches against all loaded knowledge entries using regex.
    Returns the answer with the longest matching trigger, or None.
    This prevents short, generic triggers (e.g. "french") from
    overriding more specific ones (e.g. "french fries").

    Strips quotation marks and other common punctuation artifacts
    from the query before matching, so questions with quoted terms
    (e.g. How do headphones "erase" sound?) still match KB entries.

    Also tries matching against a version of the query with common
    filler/stop words removed, so patterns like "mushrooms communicate"
    match queries like "How do mushrooms actually communicate?"

    Args:
        query: The user's question string

    Returns:
        Answer string if found, None otherwise
    """
    entries = get_all_knowledge()
    if not entries:
        return None

    # Strip common punctuation artifacts that can prevent matching
    q = query.lower().strip()
    q = re.sub(r'[\"\'\'\"\u201c\u201d\u2018\u2019]', '', q)
    q = re.sub(r'\s+', ' ', q).strip()
    # Strip trailing sentence-ending punctuation (?, !, ., ;) that can prevent
    # KB entries ending in "?" from matching user queries without trailing "?"
    q = q.rstrip('?!.;,').strip()

    # Normalize common grammatical variations to increase matching.
    # E.g., "why is it that we dream" -> "why do we dream"
    # This lets patterns match despite different phrasing.
    q_norm = q
    _NORMALIZATIONS = [
        # "why is it that we X" -> "why do we X" (and similar)
        (r'\bwhy\s+is\s+it\s+that\s+(we|you|they|i|he|she|it)\b', r'why do \1'),
        (r'\bwhy\s+is\s+it\s+that\s+', 'why '),
        (r'\bwhat\s+is\s+it\s+that\s+', 'what '),
        (r'\bhow\s+is\s+it\s+that\b', 'how'),
        # "what would actually happen if" -> "what would happen if"
        (r'\bwhat\s+would\s+actually\s+happen\b', 'what would happen'),
        (r'\bwhat\s+actually\s+happens\b', 'what happens'),
        # Remove 'actually' and filler words from middle of questions
        (r'\bthat\s+(?:actually\s+)?can\b', 'that can'),
        # "tell me about" -> "tell me about" (keep as-is, already matches)
        # "how does the process of" -> "how does"
        (r'\bhow\s+does\s+the\s+process\s+of\b', 'how does'),
        # Expand common contractions so patterns using "it's" match "it is" queries
        (r"\bit\'s\b", 'it is'),
        (r"\bdon\'t\b", 'do not'),
        (r"\bcan\'t\b", 'cannot'),
        (r"\bwon\'t\b", 'will not'),
        (r"\bdoesn\'t\b", 'does not'),
        (r"\bdidn\'t\b", 'did not'),
        (r"\bhasn\'t\b", 'has not'),
        (r"\bhaven\'t\b", 'have not'),
        (r"\bisn\'t\b", 'is not'),
        (r"\baren\'t\b", 'are not'),
        (r"\bwasn\'t\b", 'was not'),
        (r"\bweren\'t\b", 'were not'),
        (r"\bcouldn\'t\b", 'could not'),
        (r"\bwouldn\'t\b", 'would not'),
        (r"\bshouldn\'t\b", 'should not'),
        (r"\bmustn\'t\b", 'must not'),
        (r"\bthat\'s\b", 'that is'),
        (r"\bthere\'s\b", 'there is'),
        (r"\bhere\'s\b", 'here is'),
        (r"\bwhat\'s\b", 'what is'),
        (r"\bhow\'s\b", 'how is'),
        (r"\bwho\'s\b", 'who is'),
        (r"\bwhere\'s\b", 'where is'),
        (r"\bwhen\'s\b", 'when is'),
        (r"\bwhy\'s\b", 'why is'),
    ]
    for pat, repl in _NORMALIZATIONS:
        q_norm = re.sub(pat, repl, q_norm)

    # Also create variants with common writing prefixes stripped.
    # E.g., "write a detailed explanation of how X works" -> "how X works"
    # This helps KB patterns match queries wrapped in essay/explanation requests.
    _WRITING_PREFIXES = [
        r'^(?:write|compose|draft|create|build|make|design|develop|generate)\s+(?:me|us)?\s*(?:a|an|the)?\s*(?:short|long|detailed|brief|comprehensive|complete|simple|quick|basic|advanced|small|big)?\s*(?:explanation|essay|article|report|paper|guide|tutorial|description|summary|description|analysis|page|site|function|program|script|component|hook)\s+(?:about|of|on|regarding|covering|for)\s+',
        r'^(?:write|compose|draft|create|build|make|design|develop)\s+(?:me|us)?\s*(?:a|an|the)?\s*(?:short|long|detailed|brief|comprehensive|complete|simple|quick)?\s+',
        r'^(?:give|provide|offer)\s+(?:me|us)?\s*(?:a|an|the)?\s*(?:detailed|comprehensive|brief|short|quick|complete)?\s*(?:explanation|overview|introduction|description|analysis|guide|tutorial)\s+(?:of|on|about|regarding)\s+',
        r'^tell\s+(?:me|us)\s+(?:about|what|how)\s+',
        r'^(?:explain|describe|define)\s+(?:the\s+)?(?:concept\s+of\s+|idea\s+of\s+)?',
        r'^what\s+is\s+(?:a|an|the|this|that)?\s*',
        r'^what\s+are\s+',
        r'^how\s+(?:does|do|would|can|should|could)\s+(?:a|an|the|this|that|i|we|you|they|he|she|it)?\s*',
        r'^why\s+(?:is|are|do|does|did|would|could|should)\s+(?:a|an|the|this|that|i|we|you|they|he|she|it)?\s*',
    ]
    q_writing_stripped = q
    for prefix in _WRITING_PREFIXES:
        stripped = re.sub(prefix, '', q, flags=re.IGNORECASE).strip()
        if stripped and len(stripped) > 5 and stripped != q:
            q_writing_stripped = stripped
            break
    
    # Also create a simplified query with filler/stop words removed.
    # This allows patterns like "how do mushrooms communicate" to match
    # queries like "How do mushrooms actually communicate with each other".
    _FILLER_WORDS = {
        'actually', 'basically', 'essentially', 'really', 'literally',
        'honestly', 'just', 'simply', 'truly', 'definitely', 'certainly',
        'absolutely', 'totally', 'completely', 'entirely', 'quite',
        'rather', 'somewhat', 'fairly', 'pretty', 'and',
        'with', 'their', 'your', 'our', 'its', 'his', 'her',
    }
    q_simple = ' '.join(w for w in q.split() if w not in _FILLER_WORDS)
    q_simple = re.sub(r'\s+', ' ', q_simple).strip()

    # Also create a contracted version of the query ("it is" -> "it's", etc.)
    # so patterns that use contractions match queries that don't.
    # E.g., KB pattern "How does a seed know when it's time?" matches
    # user query "how does a seed know when it is time?"
    _CONTRACTIONS = [
        (r'\bit\s+is\b', "it's"),
        (r'\bdo\s+not\b', "don't"),
        (r'\bcannot\b', "can't"),
        (r'\bwill\s+not\b', "won't"),
        (r'\bdoes\s+not\b', "doesn't"),
        (r'\bdid\s+not\b', "didn't"),
        (r'\bhas\s+not\b', "hasn't"),
        (r'\bhave\s+not\b', "haven't"),
        (r'\bis\s+not\b', "isn't"),
        (r'\bare\s+not\b', "aren't"),
        (r'\bwas\s+not\b', "wasn't"),
        (r'\bwere\s+not\b', "weren't"),
        (r'\bcould\s+not\b', "couldn't"),
        (r'\bwould\s+not\b', "wouldn't"),
        (r'\bshould\s+not\b', "shouldn't"),
        (r'\bmust\s+not\b', "mustn't"),
        (r'\bthat\s+is\b', "that's"),
        (r'\bthere\s+is\b', "there's"),
        (r'\bhere\s+is\b', "here's"),
        (r'\bwhat\s+is\b', "what's"),
        (r'\bhow\s+is\b', "how's"),
        (r'\bwho\s+is\b', "who's"),
        (r'\bwhere\s+is\b', "where's"),
        (r'\bwhen\s+is\b', "when's"),
        (r'\bwhy\s+is\b', "why's"),
    ]
    q_contracted = q
    for pat, repl in _CONTRACTIONS:
        q_contracted = re.sub(pat, repl, q_contracted)
    if q_contracted == q:
        q_contracted = None  # No change, skip it

    best_answer = None
    best_match_len = 0

    # Try matching against the original query and variants
    variants = [q, q_norm, q_simple]
    if q_contracted:
        variants.append(q_contracted)
    # Add the writing-stripped variant if different
    if q_writing_stripped != q and q_writing_stripped not in variants:
        variants.append(q_writing_stripped)
    for pattern, answer in entries:
        for variant in variants:
            if not variant or len(variant) < 5:
                continue
            m = pattern.search(variant)
            if m:
                match_len = len(m.group(0))
                # Require at least 3 characters to match — prevents accidental
                # matches like 'c' (from regex 'c++') matching 'metallic'
                if match_len >= 3 and match_len > best_match_len:
                    best_match_len = match_len
                    best_answer = answer

    # Word-overlap fallback: if no exact substring match found, try
    # matching by keyword overlap. This lets patterns match queries that
    # have the right words but in a different order or with extra words.
    if not best_answer:
        try:
            # Extract key content words from the query (exclude stop words)
            _STOP_WORDS_FUZZY = {
                'what', 'why', 'how', 'when', 'where', 'which', 'who', 'does',
                'this', 'that', 'with', 'from', 'they', 'have', 'been', 'tell',
                'about', 'just', 'also', 'still', 'even', 'only', 'more', 'some',
                'like', 'into', 'over', 'such', 'than', 'then', 'very', 'really',
                'actually', 'basically', 'essentially', 'these', 'those', 'their',
                'your', 'will', 'would', 'could', 'should', 'can', 'are', 'was',
                'were', 'did', 'been', 'being', 'has', 'had', 'its', 'his', 'her',
                'our', 'all', 'any', 'each', 'every', 'both', 'most', 'other',
                'such', 'way', 'ways', 'need', 'want', 'help', 'please', 'thanks',
                'write', 'create', 'make', 'build', 'give', 'show', 'get', 'use',
                'take', 'know', 'think', 'say', 'come', 'go', 'see', 'look',
                'find', 'leave', 'work', 'call', 'try', 'ask', 'need', 'feel',
                'tell', 'much', 'many', 'some', 'too', 'very', 'also', 'well',
                'back', 'away', 'here', 'there', 'thing', 'things', 'people',
                'world', 'life', 'time', 'year', 'day', 'part', 'kind', 'sort',
                'way', 'number', 'group', 'place', 'case', 'fact', 'side',
                'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can',
                'had', 'her', 'was', 'one', 'our', 'out', 'has', 'have', 'been',
                'new', 'first', 'last', 'long', 'great', 'make', 'made', 'also',
                'well', 'even', 'much', 'may', 'now', 'than', 'then', 'very',
                'just', 'over', 'such', 'take', 'used', 'using', 'based', 'called',
                'html', 'css', 'page', 'site', 'web', 'use', 'using', 'need',
                'guide', 'basic', 'simple', 'quick', 'easy', 'hard', 'start',
                'best', 'good', 'great', 'top', 'high', 'low', 'big', 'small',
                'long', 'short', 'full', 'free', 'open', 'close', 'left', 'right',
                'name', 'type', 'form', 'line', 'set', 'run', 'end',
            }
            q_words = set(w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', q)
                         if w.lower() not in _STOP_WORDS_FUZZY)
            if q_words:
                best_fuzzy_score = -999999  # Can be negative (with penalty)
                best_fuzzy_answer = None
                best_fuzzy_pattern = ''
                for pattern, answer in entries:
                    pattern_str = pattern.pattern.lower()
                    # Count how many query words appear in the pattern
                    word_hits = sum(1 for w in q_words if w in pattern_str)
                    # PENALTY: Count pattern words NOT in query (prevents false matches)
                    p_words = set(w for w in re.findall(r'\b[a-zA-Z]{3,}\b', pattern_str)
                                  if w not in _STOP_WORDS_FUZZY)
                    extraneous = len(p_words - q_words)
                    score = word_hits - extraneous * 3  # -3 per extraneous word
                    if score > best_fuzzy_score:
                        best_fuzzy_score = score
                        best_fuzzy_answer = answer
                        best_fuzzy_pattern = pattern_str
                # Only use fuzzy match if at least 2 key words overlap
                # AND the overlap covers at least 40% of query key words
                # AND the overlap covers at least 40% of pattern key words
                # Bidirectional check prevents false matches between unrelated topics
                # Compute the raw word_hits (without penalty) for ratio checks
                raw_hits = sum(1 for w in q_words if w in best_fuzzy_pattern)
                if q_words and raw_hits >= 2 and best_fuzzy_answer:
                    q_ratio = raw_hits / len(q_words)
                    # Count pattern words too for bidirectional check
                    pattern_words = set(w for w in re.findall(r'\b[a-zA-Z]{3,}\b', best_fuzzy_pattern)
                                       if w not in _STOP_WORDS_FUZZY)
                    p_ratio = raw_hits / max(len(pattern_words), 1)
                    if q_ratio >= 0.4 and p_ratio >= 0.4:
                        best_answer = best_fuzzy_answer
        except Exception:
            pass

    return best_answer


# ── Statistics ───────────────────────────────────────────────────────────────

def stats():
    """Return statistics about the loaded knowledge base."""
    entries = get_all_knowledge()
    if not entries:
        return "No knowledge loaded."

    # Count by category
    categories = {}
    for path in sorted(p for p in _KNOWLEDGE_DIR.rglob('*.json') if not p.name.startswith('.')):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            cat = path.parent.name
            categories[cat] = categories.get(cat, 0) + len(data)
        except:
            pass

    result = f"Total entries: {len(entries)}\n"
    for cat, count in sorted(categories.items()):
        result += f"  {cat}: {count} entries\n"
    return result
