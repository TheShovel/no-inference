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
    global _WORD_INDEX, _RAW_ENTRY_INDICES, _ENTRY_WORDS
    _WORD_INDEX = {}
    _RAW_ENTRY_INDICES = set()
    _ENTRY_WORDS = []

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

            # Category index: entries may declare which categories they belong
            # to via 'categories' (list), 'category' (str), or 'tags' (list).
            # This powers multi-entity composition ("what types of X are there")
            # across ALL subjects — any tagged entry becomes a member of its
            # category, no per-category registry needed.
            declared = entry.get('categories') or entry.get('category') or entry.get('tags') or []
            if isinstance(declared, str):
                declared = [declared]
            declared = [str(c).strip().lower() for c in declared if str(c).strip()]

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
                    # Index the entry by its significant words so lookup() can
                    # skip patterns whose words cannot appear in the query.
                    idx = len(entries) - 1
                    if has_regex_backslash:
                        _RAW_ENTRY_INDICES.add(idx)
                        _ENTRY_WORDS.append(None)
                    else:
                        _entry_words = _word_tokens(q_clean)
                        _ENTRY_WORDS.append(_entry_words)
                        for _w in _entry_words:
                            _WORD_INDEX.setdefault(_w, set()).add(idx)
                except re.error as e:
                    print(f'  Warning: Bad pattern "{q_clean}": {e}')
                    continue

            # Register entry in the category index (once per entry, not per question)
            if declared:
                name = _derive_entry_name(entry, questions)
                for cat in declared:
                    _CATEGORY_INDEX.setdefault(cat, [])
                    if not any(a == answer for _, a in _CATEGORY_INDEX[cat]):
                        _CATEGORY_INDEX[cat].append((name, answer))

        if loaded > 0:
            # Print category summary
            rel_path = path.relative_to(base_dir.parent.parent if base_dir == _KNOWLEDGE_DIR else base_dir)
            pass  # quiet load by default

    return entries

# ── Load knowledge at module import time ─────────────────────────────────────
_KNOWLEDGE_CACHE = None

# Word index for fast lookup: significant word (lowercase) -> set of entry
# indices into _KNOWLEDGE_CACHE. Built during _load_knowledge so lookup()
# only scans candidate entries instead of all 40k+ patterns on every query.
# The index is SOUND: an escaped-literal pattern can only match text that
# contains every one of its words, so patterns whose words are missing from
# the query can never match it and are safely skipped.
_WORD_INDEX = {}
# Entry indices whose pattern is a raw regex (contains backslash escapes);
# these cannot be word-indexed and are always considered candidates.
_RAW_ENTRY_INDICES = set()
# Parallel to _KNOWLEDGE_CACHE: frozenset of word tokens for each entry, or
# None for raw-regex entries (never filtered).
_ENTRY_WORDS = []

_WORD_TOKEN_RE = re.compile(r'[a-z0-9]+')


def _word_tokens(text):
    """Extract the set of significant word tokens from text."""
    return set(_WORD_TOKEN_RE.findall(text.lower()))

# Category index: category name (lowercase) -> [(display_name, answer), ...]
# Built during _load_knowledge from entries declaring 'categories'/'tags'.
_CATEGORY_INDEX = {}


def _derive_entry_name(entry, questions):
    """Derive a display name for a KB entry for category composition.

    Prefers an explicit 'name' field; otherwise the shortest question that
    looks like a noun phrase (no leading question word).
    """
    name = entry.get('name')
    if isinstance(name, str) and name.strip():
        return name.strip()
    _QUESTION_LEADERS = ('what', 'which', 'who', 'where', 'when', 'why', 'how',
                         'tell', 'explain', 'describe', 'define', 'is', 'are',
                         'do', 'does', 'did', 'list', 'name', 'give')
    # Multi-word prefixes to strip from question-style questions
    _LEADER_PHRASES = (
        'what is ', 'what are ', 'what was ', 'what were ', 'what does ',
        'what do ', 'what did ', 'which is ', 'which are ', 'who is ',
        'who was ', 'where do ', 'where does ', 'how does ', 'how do ',
        'how is ', 'how are ', 'tell me about ', 'tell me what ', 'tell me how ',
        'explain ', 'describe ', 'define ', 'why is ', 'why do ', 'why are ',
        'what is the ', 'what are the ',
    )
    _CUT_WORDS = {' and ', ' or ', ' how ', ' why ', ' which ', ' where ',
                  ' when ', ' who ', ' with ', ' by ', ' including ',
                  ' such as ', ' like ', ' versus ', ' vs ', ' compared to '}

    best = None
    for q in questions:
        q = str(q).strip().rstrip('?!.,;:')
        if not q or len(q) < 2:
            continue
        words = q.split()
        candidate = None
        if words and words[0].lower() not in _QUESTION_LEADERS:
            candidate = q  # already a noun phrase (e.g. "european wildcat")
        else:
            stripped = q
            for leader in _LEADER_PHRASES:
                if stripped.lower().startswith(leader):
                    stripped = stripped[len(leader):].strip()
                    break
            if stripped and stripped.lower() != q.lower():
                candidate = stripped
        if not candidate:
            continue
        # Cut at conjunctions / sub-question words: "black tea and how is it
        # processed" -> "black tea"
        lower_c = candidate.lower()
        cut_at = None
        for cut in _CUT_WORDS:
            idx = lower_c.find(cut)
            if idx > 0 and (cut_at is None or idx < cut_at):
                cut_at = idx
        if cut_at:
            candidate = candidate[:cut_at].strip()
        if len(candidate) < 2:
            continue
        # Prefer the shortest cleaned name
        if best is None or len(candidate.split()) < len(best.split()):
            best = candidate
    if best:
        return best.title()
    return 'Item'


def get_category_members(category):
    """Return [(display_name, answer)] for all entries tagged with a category.

    Matches the category name case-insensitively, trying exact, singular,
    and plural forms so "cats" finds entries tagged "cat" and vice versa.
    Returns None if the category index has no members (caller decides
    whether to fall back to the registry / Wikipedia).
    """
    global _CATEGORY_INDEX
    if _KNOWLEDGE_CACHE is None:
        get_all_knowledge()
    if not _CATEGORY_INDEX:
        return None
    cat = category.strip().lower()
    candidates = {cat}
    if cat.endswith('s') and not cat.endswith('ss'):
        candidates.add(cat[:-1])  # cats -> cat
    else:
        candidates.add(cat + 's')  # cat -> cats
    results = []
    seen_names = set()
    seen_answers = set()
    # Normalize display names so "The Planet Mercury" and "Mercury" (and
    # other "the <label> <name>" derivations) collapse to the same member
    # instead of listing the same planet twice.
    _norm = lambda n: re.sub(
        r'^(?:the|a|an)\s+(?:(?:planet|animal|plant|fish|bird|tree|rock|storm|cloud|dragon|sword|dance|sport|pasta|cheese|type|kind|breed|species|variety|style|form|member|cat|dog|whale|shark|bear|snake|insect|bird|flower|fruit|vegetable|mushroom|country|city|river|mountain|desert|ocean|sea|lake|island|continent|god|goddess|hero|creature|monster|dinosaur|genus|species)\s+)?',
        '', n.lower().strip())
    # Iterate candidates in sorted order — a set's iteration order varies
    # per process (hash randomization), which made "list all the planets"
    # sometimes list my new entries first and sometimes the legacy ones.
    for c in sorted(candidates):
        for name, answer in _CATEGORY_INDEX.get(c, []):
            _key = _norm(name)
            if _key in seen_names or answer in seen_answers:
                continue
            seen_names.add(_key)
            seen_answers.add(answer)
            results.append((name, answer))
    return results or None


def get_all_knowledge():
    """Get all loaded knowledge entries, caching after first load."""
    global _KNOWLEDGE_CACHE
    if _KNOWLEDGE_CACHE is None:
        _KNOWLEDGE_CACHE = _load_knowledge()
        if _KNOWLEDGE_CACHE:
            print(f"  Loaded {len(_KNOWLEDGE_CACHE)} knowledge entries from data/knowledge/")
    return _KNOWLEDGE_CACHE


def find_best_match(query):
    """Find the KB entry whose pattern matches the query with the longest span.

    Returns (match_len, answer) or (0, None). Uses the word index so it does
    not scan all 40k+ patterns. Equivalent to:

        for pattern, answer in get_all_knowledge():
            m = pattern.search(query)
            ...keep longest m.group(0)...

    Callers wanting curated-over-composed behavior (e.g. comparison queries
    that have a hand-written KB entry) use this to check the full query first.
    """
    entries = get_all_knowledge()
    if not entries:
        return 0, None
    q = query.lower().strip()
    q_words = _word_tokens(q)
    if q_words:
        # Use the two rarest words' candidate lists — the rarest word is the
        # content noun matching patterns share, and the second covers cases
        # where the rarest word is slang/incidental to the pattern.
        _sorted = sorted(q_words, key=lambda w: len(_WORD_INDEX.get(w, ())))
        candidates = set(_RAW_ENTRY_INDICES)
        for _w in _sorted[:2]:
            candidates |= set(_WORD_INDEX.get(_w, ()))
    else:
        candidates = set(range(len(entries)))
    best_len = 0
    best_answer = None
    for ci in sorted(candidates):
        pattern, answer = entries[ci]
        _entry_word_set = _ENTRY_WORDS[ci]
        if _entry_word_set is not None and not (_entry_word_set <= q_words):
            continue
        try:
            m = pattern.search(q)
        except Exception:
            continue
        if m and len(m.group(0)) > best_len:
            best_len = len(m.group(0))
            best_answer = answer
    return best_len, best_answer

def reload():
    """Force reload of all knowledge from disk."""
    global _KNOWLEDGE_CACHE
    _KNOWLEDGE_CACHE = None
    return get_all_knowledge()


# ── Question wrapper / trailing qualifier stripping ───────────────────────────
# Stripping these lets one KB entry match many different phrasings:
#   "do you know what X is" -> "X is"      "whats the deal with X" -> "X"
#   "explain X like i'm five" -> "the X"   "what is X exactly" -> "X"
_QUESTION_WRAPPERS = [
    r'^(?:not\s+going\s+to\s+lie|not\s+gonna\s+lie|ngl|no\s+cap|for\s+real|fr)\s+',
    r'^(?:yo|hey|heya|yo\s+yo|hey\s+there)\s+',
    r'^(?:i\'?m|i\s+am)\s+(?:going\s+to|gonna|want\s+to|wanna)\s+ask\s+(?:you\s+)?(?:about|on)\s+',
    r'^(?:whats|what\'s|wuts|wut\'s|wats|wat\'s)\s+up\s+with\s+',
    r'^(?:i\s+)?(?:wanna|want\s+to)\s+know\s+',
    r'^(?:gimme|give\s+me)\s+the\s+lowdown\s+on\s+',
    r'^(?:do|does|did)\s+you\s+know\s+(?:what|who|where|when|why|how|if|whether)\s+',
    r'^(?:do|does|did)\s+you\s+know\s+(?:anything\s+)?(?:about|on)\s+',
    r'^(?:do|does|did)\s+you\s+know\s+',
    r'^(?:can|could|would|will)\s+you\s+(?:tell|show|give)\s+(?:me|us)\s+(?:about|what|how)\s+',
    r'^(?:can|could|would|will)\s+you\s+(?:tell|show|give)\s+(?:me|us)\s+(?:a|an|the)?\s*(?:brief\s+|quick\s+|short\s+|little\s+|bit\s+)?(?:explanation|summary|overview|description|introduction)\s+(?:of|about|on)\s+',
    r'^(?:can|could|would|will)\s+you\s+(?:explain|describe|define)\s+',
    r'^(?:can|could|would|will)\s+you\s+happen\s+to\s+know\s+',
    r'^(?:can|could|would|will)\s+you\s+help\s+(?:me|us)\s+(?:with|understand|learn)\s+',
    r'^(?:can|could|would|will)\s+you\s+please\s+(?:tell|show|give|explain|describe|define)\s+',
    r'^(?:i\s+was\s+wondering|i\s+wondered|i\s+want\s+to\s+know|i\s+wanna\s+know|i\s+need\s+to\s+know|i\s+d\'?d\s+like\s+to\s+know|i\s+would\s+like\s+to\s+know)\s+(?:what|who|where|when|why|how|if|whether)\s+',
    r'^(?:i\s+was\s+wondering|i\s+wondered|i\s+want\s+to\s+know|i\s+wanna\s+know|i\s+need\s+to\s+know|i\s+d\'?d\s+like\s+to\s+know|i\s+would\s+like\s+to\s+know)\s+(?:about|on)\s+',
    r'^(?:i\'?m|i\s+am)\s+(?:curious|wondering)\s+(?:about|what)\s+',
    r'^curious\s+(?:about|what)\s+',
    r'^(?:i\s+heard|i\'ve\s+heard|i\s+heard\s+that|i\'ve\s+heard\s+that|i\s+read\s+somewhere\s+that|apparently)\s+(?:that\s+)?',
    r'^(?:is\s+it\s+true\s+that|is\s+it\s+true|correct\s+me\s+if\s+i\'?m\s+wrong\s+but|am\s+i\s+right\s+that)\s+',
    r'^(?:whats|what\'s)\s+the\s+(?:deal|story)\s+with\s+',
    r'^(?:whats|what\'s)\s+the\s+story\s+of\s+',
    r'^tell\s+(?:me|us)\s+(?:a\s+(?:bit|little)\s+|a\s+bit\s+more\s+|some\s+|everything\s+|all\s+|what\s+you\s+know\s+)(?:about|on)\s+',
    r'^tell\s+(?:me|us)\s+(?:about|what|how|everything|all|more)\s+',
    r'^(?:brief\s+me\s+on|brief\s+me\s+about|fill\s+me\s+in\s+on|fill\s+me\s+in\s+about|catch\s+me\s+up\s+on)\s+',
    r'^(?:give|gimme|provide)\s+(?:me|us)?\s*(?:the\s+)?(?:lowdown|rundown|scoop|411|info|information|facts|details|insight|deets)\s+(?:on|about|regarding)\s+',
    r'^(?:the\s+)?(?:lowdown|rundown|scoop)\s+(?:on|about)\s+',
    r'^(?:walk\s+me\s+through|break\s+down)\s+',
    r'^(?:shed\s+(?:some|a\s+little)\s+light\s+on|enlighten\s+me\s+(?:about|on)|educate\s+me\s+(?:on|about)|school\s+me\s+(?:on|about))\s+',
    r'^(?:quick\s+question(?:\s+about)?|question\s+(?:about|on|re|:))\s*',
    r'^(?:do\s+you\s+have\s+any\s+info\s+on|got\s+any\s+info\s+on|any\s+info\s+on|any\s+thoughts\s+on|do\s+you\s+know\s+anything\s+about)\s+',
    r'^(?:any\s+idea|any\s+clue|any\s+guesses?|any\s+thoughts?)\s+(?:what|who|where|when|why|how)\s+',
    r'^(?:any\s+idea|any\s+clue|any\s+guesses?|any\s+thoughts?)\s+(?:about|on)\s+',
    r'^(?:everything|all)\s+about\s+',
    r'^(?:explain|describe|define)\s+(?:the\s+)?(?:concept\s+of\s+|idea\s+of\s+|process\s+of\s+|science\s+behind\s+|basics\s+of\s+|fundamentals\s+of\s+)?',
    r'^(?:regarding|as\s+for|speaking\s+of|on\s+the\s+topic\s+of|the\s+topic\s+of|re:|about|on)\s+',
    r'^(?:please|pls|plz)\s+(?:tell\s+(?:me|us)|explain|describe|define|give\s+(?:me|us))\s+',
    r'^(?:please|pls|plz)\s+',
    r'^(?:what|wats|wat|wut)\s+do\s+you\s+know\s+about\s+',
    r'^(?:what|wats|wat|wut)\s+do\s+you\s+know\s+',
    r'^(?:what|wats|wat|wut)\s+can\s+you\s+tell\s+(?:me|us)\s+(?:about|on)\s+',
    r'^(?:what\s+should\s+i\s+know\s+about|what\s+do\s+i\s+need\s+to\s+know\s+about|what\s+should\s+one\s+know\s+about)\s+',
    r'^(?:teach\s+me\s+about|teach\s+me\s+on|teach\s+me)\s+',
    r'^(?:do\s+you\s+have\s+anything\s+on|got\s+anything\s+on|anything\s+on)\s+',
    r'^(?:can\s+i\s+get\s+some\s+info\s+on|can\s+i\s+get\s+info\s+on|can\s+i\s+get\s+information\s+(?:on|about)|i\s+want\s+some\s+info\s+on)\s+',
    r'^(?:what\s+is\s+going\s+on\s+with|whats\s+going\s+on\s+with|what\s+is\s+the\s+(?:situation|story|deal)\s+with|what\s+is\s+up\s+with)\s+',
    r'^(?:what\s+happened\s+(?:with|to)|whats\s+going\s+on\s+with)\s+',
    r'^(?:where\s+did|where\'?d)\s+',
    r'^(?:how\s+did|how\'?d)\s+',
    r'^(?:who\s+(?:invented|discovered|created|built|founded|wrote|made|designed|developed)|who\s+was\s+the\s+(?:inventor|creator|founder)\s+of)\s+',
    r'^(?:give\s+me|give|name|list|some)\s+(?:some\s+|a\s+few\s+|any\s+)?(?:examples?|instances?|cases?)\s+of\s+',
    r'^(?:what\s+are\s+(?:some\s+|a\s+few\s+)?(?:examples?|instances?|types?|kinds?)\s+of)\s+',
    r'^(?:the\s+)?(?:history|origins?|definition|basics|fundamentals|overview|introduction|intro|summary|workings|mechanics|causes|benefits|effects|signs|symptoms|types|features|characteristics|properties|importance|significance|role|future|science|purpose|meaning|language|religion|climate|capital|population|currency|economy|government|ruler|leader|structure|parts|components|elements|ingredients|members|anatomy|biology|message|theme|moral|lesson|plot|story|ending|finale|outcome|result|setting|symbolism|legacy|risks|dangers|drawbacks|downsides|side\s+effects|advantages|disadvantages|pros|cons|nutrition|nutritional\s+value|taste|flavor|color|size|weight|height|speed|average\s+height|average\s+weight|average\s+lifespan|average\s+life\s+span|average\s+life\s+expectancy|life\s+expectancy|average\s+age|average\s+size|average\s+speed|average\s+cost|average\s+price|average\s+temperature|average\s+rainfall|annual\s+rainfall|lifespan)\s+of\s+',
    r'^intro\s+to\s+',
    r'^(?:more\s+about|more\s+on|further\s+details\s+on|more\s+info\s+on|more\s+information\s+(?:about|on))\s+',
    r'^(?:expand\s+on|elaborate\s+on|go\s+deeper\s+on|deep\s+dive\s+into|dive\s+into)\s+',
    r'^(?:explain\s+to\s+me|describe\s+to\s+me)\s+',
    r'^(?:why\s+do\s+(?:we|humans|people|i|you)\s+(?:have|need)\s+|why\s+does\s+(?:the|a|an)\s+|why\s+do\s+we\s+have\s+|why\s+is\s+the\s+)',
    r'^(?:what\s+is\s+the\s+(?:point|purpose|goal|aim)\s+of|whats\s+the\s+(?:point|purpose|goal|aim)\s+of)\s+',
    r'^(?:the\s+)?(?:pros\s+and\s+cons|advantages\s+and\s+disadvantages|good\s+and\s+bad)\s+of\s+',
    r'^(?:the\s+)?(?:gist|basics|fundamentals|idea|concept|meaning|definition|summary|lowdown|rundown)\s+of\s+',
    r'^(?:whats|what\'s)\s+the\s+(?:gist|idea|concept)\s+of\s+',
    r'^(?:so|ok|okay|well|hey|right|anyway|just|like|hmm|um|uh|wait)\s+(?:what|which|who|where|when|why|how|tell|explain|describe|define)\s+',
    r'^(?:in\s+brief|in\s+short|in\s+one\s+word|in\s+simple\s+terms|to\s+sum\s+up|basically|long\s+story\s+short),\s+',
    r'^(?:i\s+need\s+(?:some\s+|any\s+|the\s+)?(?:info|information|facts|details|deets)\s+(?:on|about)\s+)',
    r'^fun\s+fact:?\s+',
    r'^(?:what\s+year\s+did|what\s+year\s+was)\s+',
    r'^(?:in\s+what\s+year\s+(?:did|was|were|is|are)|when\s+exactly\s+(?:was|were|is|are|did))\s+',
    r'^(?:what\s+do\s+you\s+got\s+on|whaddya\s+know\s+about|waddaya\s+know\s+about|whatcha\s+know\s+about)\s+',
    r'^(?:how\s+long\s+(?:does|do|is|are|has|have|did)\s+)',
    r'^(?:how\s+(?:old|big|tall|far|fast|heavy|hot|cold|large|small|wide|deep|high|many|much)\s+(?:is|are|was|were|does|do|did)\s+)',
    r'^(?:how\s+(?:old|big|tall|far|fast|heavy|hot|cold|large|small|wide|deep|high|many|much)\s+[a-z]+\s+(?:does|do|has|have|did)\s+)',
    r'^(?:how\s+much\s+does\s+|how\s+much\s+do\s+)',
    r'^(?:does|do|did)\s+',
    r'^(?:can|could|is|are|was|were)\s+',
    r'^(?:what\s+makes|what\s+made)\s+',
    r'^(?:what\s+do\s+you\s+mean\s+by|what\s+did\s+you\s+mean\s+by|what\s+is\s+meant\s+by)\s+',
    r'^(?:what\s+does\s+the\s+term|what\s+is\s+the\s+term|define\s+the\s+term|the\s+term)\s+',
    r'^(?:the\s+story\s+behind|what\s+is\s+the\s+story\s+behind)\s+',
    r'^(?:summarize|summarise|sum\s+up)\s+',
    r'^(?:who\s+killed|who\s+won|who\s+lost|who\s+beat)\s+',
    r'^(?:where\s+does\s+the\s+name|what\s+is\s+the\s+origin\s+of\s+the\s+name|the\s+origin\s+of\s+the\s+name)\s+',
    r'^(?:in\s+other\s+words|put\s+simply|simply\s+put|to\s+put\s+it\s+simply),\s+',
    r'^(?:what\s+information\s+do\s+you\s+have\s+on|what\s+do\s+you\s+have\s+on|what\s+can\s+you\s+say\s+about|anything\s+you\s+can\s+tell\s+me\s+about)\s+',
    r'^(?:i\'?d\s+(?:love|like)\s+to\s+hear\s+about|i\s+want\s+to\s+hear\s+about|i\s+wanna\s+hear\s+about)\s+',
    r'^(?:spill\s+the\s+beans\s+(?:about|on)|the\s+skinny\s+on|the\s+dirt\s+on)\s+',
    r'^(?:who\s+exactly\s+is|what\s+exactly\s+is|where\s+exactly\s+is|how\s+exactly\s+(?:does|do|is|are)|why\s+exactly\s+(?:is|are|does|do))\s+',
    r'^(?:what\s+is\s+your\s+knowledge\s+of|your\s+knowledge\s+of)\s+',
    r"^(?:what'?s|what\s+is)\s+wrong\s+with\s+",
    r'^(?:who\s+first\s+(?:discovered|invented|created|used|found)|when\s+was\s+the\s+first)\s+',
    r'^(?:what\s+day\s+is|what\s+date\s+is|when\s+is|when\s+are)\s+',
    r'^(?:what\s+do\s+people\s+call|what\s+is\s+another\s+name\s+for|what\s+is\s+the\s+nickname\s+for)\s+',
    r'^(?:what\s+is\s+the\s+job\s+of|what\s+is\s+the\s+duty\s+of)\s+',
    r'^(?:why\s+do\s+(?:we|humans|people)\s+use)\s+',
    r'^(?:how\s+many\s+people\s+live\s+in|how\s+many\s+people\s+live\s+on|how\s+many\s+people\s+live\s+in\s+the)\s+',
    r'^(?:how\s+strong\s+(?:is|are|was|were)|how\s+smart\s+(?:is|are|was|were)|how\s+intelligent\s+(?:is|are|was|were))\s+',
    r'^(?:how\s+(?:big|tall|heavy|large|long|fast|far|deep|high|wide|old)\s+can\s+)',
    r'^(?:what\s+are\s+the\s+parts\s+of|what\s+are\s+the\s+components\s+of|what\s+are\s+the\s+elements\s+of|what\s+are\s+the\s+ingredients\s+of|what\s+are\s+the\s+members\s+of)\s+',
    r'^(?:can\s+you\s+eat|can\s+you\s+drink|can\s+humans\s+eat|can\s+humans\s+drink)\s+',
    r'^(?:how\s+many\s+people\s+(?:speak|use|play|watch|visit|read|own|drive)\s+)\s+',
    r'^(?:who\s+is\s+the\s+main\s+character\s+of|who\s+are\s+the\s+main\s+characters\s+of|who\s+is\s+the\s+villain\s+of|who\s+is\s+the\s+protagonist\s+of|who\s+is\s+the\s+antagonist\s+of|who\s+dies\s+in)\s+',
    r'^(?:what\s+happens\s+at\s+the\s+end\s+of|what\s+happens\s+in\s+the\s+end\s+of)\s+',
    r'^(?:what\s+came\s+(?:after|before)|what\s+was\s+(?:before|after)|what\s+led\s+to\s+the\s+(?:fall|decline|rise|end)\s+of|what\s+led\s+to|what\s+caused\s+the\s+(?:fall|decline|rise|end)\s+of)\s+',
    r'^(?:what\s+is\s+the\s+effect\s+of|what\s+are\s+the\s+effects\s+of)\s+',
    r'^(?:what\s+is\s+the\s+population\s+of|what\s+was\s+the\s+population\s+of|what\s+is\s+the\s+currency\s+of)\s+',
    r'^(?:what\s+language\s+do\s+they\s+speak\s+in|what\s+language\s+is\s+spoken\s+in)\s+',
    r'^(?:why\s+is\s+it\s+called|why\s+are\s+they\s+called)\s+',
    r'^(?:how\s+often\s+(?:does|do|is|are|did)|how\s+frequently\s+(?:does|do|is|are|did))\s+',
    r'^(?:what\s+(?:family|group|class|category|kingdom|phylum|order)\s+(?:does|do|is|are))\s+',
    r'^(?:why\s+do\s+we\s+celebrate|when\s+do\s+we\s+celebrate|how\s+do\s+we\s+celebrate)\s+',
    r'^(?:what|which|who|where|when|why|how)\s+(?:even|exactly|actually|the\s+heck|the\s+actual\s+heck|on\s+earth|in\s+the\s+world|the\s+hell|the\s+actual\s+hell|in\s+the\s+heck|in\s+the\s+actual\s+world)\s+',
    r'^how\s+come\s+',
    r'^(?:whats|what\'s|wat\'s|wats)\s+',
    r'^(?:how|why|what)\s+is\s+it\s+that\s+',
    r'^(?:tell|show|give|name|list)\s+(?:me|us)?\s*',
]

# Trailing qualifiers stripped after the topic ("what is X exactly",
# "what is X made of", "explain X to me") so the bare topic remains.
_TRAILING_QUALIFIERS = [
    r'\s+exactly$', r'\s+actually$', r'\s+anyway$', r'\s+again$', r'\s+then$',
    r'\s+please$', r'\s+pls$', r'\s+plz$', r'\s+rn$', r'\s+tbh$', r'\s+fr$',
    r'\s+tho$', r'\s+though$', r'\s+for\s+real$', r'\s+in\s+simple\s+terms$',
    r'\s+in\s+plain\s+(?:english|words)$', r'\s+for\s+dummies$', r'\s+to\s+me$',
    r'\s+mean\??$', r'\s+even\s+mean\??$', r'\s+mean\s+by\s+that$',
    r'\s+used\s+for$', r'\s+made\s+of$', r'\s+known\s+for$', r'\s+do\??$',
    r'\s+look\s+like$', r'\s+consist\s+of$', r'\s+all\s+about$', r'\s+about$',
    r'\s+and\s+stuff$', r'\s+and\s+things$', r'\s+and\s+all$',
    r'\s+briefly$', r'\s+quickly$', r'\s+for\s+me$', r'\s+to\s+know$',
    r'\s+in\s+detail$', r'\s+in\s+depth$', r'\s+more$', r'\s+some\s+more$',
    r'\s+like\s+i\'?m\s+(?:five|5|a\s+fifth\s+grader|a\s+child)$',
    # Topic-first suffix formats: "X explained", "X basics", "X 101",
    # "X facts", "X history", "X overview"
    r'\s+explained\s+simply$', r'\s+explained$', r'\s+in\s+simple\s+words$',
    r'\s+for\s+beginners$', r'\s+for\s+kids$', r'\s+basics$', r'\s+101$',
    r'\s+facts$', r'\s+fact$', r'\s+overview$', r'\s+history$', r'\s+origins$',
    r'\s+introduction$', r'\s+intro$', r'\s+summary$', r'\s+details$',
    r'\s+more\s+details$', r'\s+in\s+general$', r'\s+man$', r'\s+dude$',
    r'\s+bro$', r'\s+fam$', r'\s+my\s+dude$', r'\s+my\s+guy$', r'\s+pal$',
    r'\s+friend$', r'\s+buddy$', r'\s+mate$',
    # "how did X come to be / start / begin / originate",
    # "where did X come from / originate"
    r'\s+(?:come\s+to\s+be|come\s+about|start|begin|originate|get\s+started)$',
    r'\s+come\s+from$', r'\s+come\s+into\s+existence$', r'\s+first\s+appear$',
    # Attribute / descriptor suffixes: "what is X like", "what does X
    # stand for", "when was X invented", "where is X located"
    r'\s+like$', r'\s+good\s+for$', r'\s+famous\s+for$', r'\s+best\s+known\s+for$',
    r'\s+known\s+for$', r'\s+stand\s+for$', r'\s+composed\s+of$', r'\s+made\s+out\s+of$',
    r'\s+made\s+from$', r'\s+invented$', r'\s+discovered$', r'\s+founded$', r'\s+built$',
    r'\s+established$', r'\s+created$', r'\s+located$', r'\s+meaning$', r'\s+definition$',
    r'\s+in\s+your\s+own\s+words$', r'\s+examples$', r'\s+example$',
    r'\s+out\s+loud$', r'\s+real\s+quick$', r'\s+real\s+fast$', r'\s+rn\s+please$',
    # Round 5: more casual suffix formats
    r'\s+in\s+a\s+nutshell$', r'\s+at\s+a\s+glance$', r'\s+summarized$',
    r'\s+tl;?dr$', r'\s+tldr$', r'\s+cheat\s+sheet$', r'\s+timeline$',
    r'\s+causes$', r'\s+benefits$', r'\s+effects$', r'\s+examples\s+please$',
    r'\s+for\s+real\s+tho$', r'\s+tho\s+fr$', r'\s+ngl$', r'\s+deadass$',
    r'\s+lowkey$', r'\s+highkey$', r'\s+rn\s+fr$', r'\s+real\s+quick\s+fr$',
    r'\s+one\s+more\s+time$', r'\s+again\s+please$', r'\s+real\s+talk$',
    # Round 6 trailing qualifiers
    r'\s+for$', r'\s+called$', r'\s+happen$', r'\s+happened$', r'\s+take$',
    r'\s+lasted$', r'\s+last$', r'\s+started$', r'\s+released$', r'\s+published$',
    r'\s+invented\s+by\s+someone$', r'\s+made\s+of\s+what$', r'\s+made\s+up\s+of$',
    r'\s+sort\s+of\s+thing$', r'\s+and\s+such$', r'\s+and\s+so\s+on$', r'\s+etc$',
    r'\s+or\s+something$', r'\s+or\s+so$', r'\s+or\s+whatever$', r'\s+anyway\s+tho$',
    # Round 7 trailing qualifiers: attribute/have-questions
    r'\s+weigh$', r'\s+weighs$', r'\s+from\s+scratch$', r'\s+really$', r'\s+truly$',
    r'\s+have\s+(?:a|an|the)?\s+[a-z]+$', r'\s+has\s+(?:a|an|the)?\s+[a-z]+$',
    r'\s+have$', r'\s+has$',
    r'\s+and\s+why$', r'\s+then\s+what$', r'\s+now\s+what$',
    # Round 8 trailing qualifiers
    r'\s+work$', r'\s+function$', r'\s+functions$', r'\s+so\s+[a-z]+$',
    r'\s+special$', r'\s+unique$', r'\s+interesting$', r'\s+fascinating$',
    r'\s+special\s+about$', r'\s+different\s+about$', r'\s+so\s+special$',
    r'\s+(?:a|an)\s+[a-z]+$', r'\s+tho\s+ngl$', r'\s+or\s+nah$',
    # Round 9: sensory / descriptor / verification qualifiers
    # NOTE: only keep qualifiers whose words don't commonly form compound
    # topics ("dark matter", "big bang", "fast food", "hot sauce") — those
    # would get wrongly stripped.
    r'\s+real$', r'\s+actually\s+exist$', r'\s+really\s+exist$',
    r'\s+dangerous$', r'\s+safe$', r'\s+worth\s+it$', r'\s+healthy$',
    r'\s+taste\s+like$', r'\s+smell\s+like$', r'\s+sound\s+like$', r'\s+feel\s+like$',
    r'\s+important$', r'\s+so\s+important$', r'\s+necessary$', r'\s+essential$',
    r'\s+useful$', r'\s+helpful$',
    # Round 10 trailing qualifiers
    r'\s+end$', r'\s+die$', r'\s+died$', r'\s+get\s+its\s+name$', r'\s+get\s+the\s+name$',
    r'\s+and\s+how$', r'\s+or\s+how$', r'\s+and\s+why$',
    # Round 11 trailing qualifiers
    r'\s+a\s+thing$', r'\s+even\s+a\s+thing$', r'\s+even\s+real$', r'\s+actually\s+real$',
    r'\s+to\s+me$', r'\s+like\s+i\'?m\s+(?:stupid|dumb|an\s+idiot|a\s+moron)$',
    r'\s+these\s+days$', r'\s+nowadays$', r'\s+anymore$', r'\s+these\s+days\s+fr$',
    r'\s+for\s+real\s+tho\s+fr$', r'\s+tho\s+fr\s+fr$', r'\s+lowkey\s+fr$',
    # Round 12 trailing qualifiers
    r'\s+the\s+way\s+it\s+is$', r'\s+first\s+invented$', r'\s+first\s+discovered$',
    r'\s+first\s+created$', r'\s+first\s+used$', r'\s+first\s+found$',
    r'\s+existed$', r'\s+been\s+around$', r'\s+been\s+around\s+for\s+ages$',
    r'\s+classified\s+as$', r'\s+categorized\s+as$', r'\s+grouped\s+as$',
    r'\s+belong\s+to$', r'\s+symbolize$', r'\s+represent$', r'\s+celebrate$',
    r'\s+celebrate\s+it$', r'\s+occur$', r'\s+take\s+place$', r'\s+happen\s+in\s+general$',
    r'\s+is\s+it$', r'\s+or\s+not$',
    # Round 13 trailing qualifiers
    r'\s+cost$', r'\s+overrated$', r'\s+made$', r'\s+produced$', r'\s+created$',
    r'\s+grown$', r'\s+formed$', r'\s+written\s+by$', r'\s+written$', r'\s+created\s+by$',
    r'\s+made\s+by$', r'\s+killed\s+by$', r'\s+caused\s+by$', r'\s+first\s+mentioned$',
    r'\s+first\s+recorded$', r'\s+first\s+documented$', r'\s+first\s+used\s+in\s+writing$',
    r'\s+grow$', r'\s+form$',
    # Round 14 trailing qualifiers
    r'\s+called\s+the\s+[a-z\s]+$', r'\s+also\s+called$', r'\s+exist$', r'\s+exist\s+at\s+all$',
    r'\s+affect\s+[a-z]+$', r'\s+affects\s+[a-z]+$', r'\s+get\s+its\s+nickname$',
    r'\s+for\s+humans$', r'\s+for\s+the\s+body$', r'\s+for\s+your\s+health$',
    # "effect of X on Y" — strip the qualifier target (curated list so
    # compound topics like "life on mars" are never broken)
    r'\s+on\s+(?:sleep|health|the\s+body|the\s+brain|the\s+mind|the\s+heart|mood|memory|focus|the\s+skin|the\s+gut|the\s+environment|the\s+climate|the\s+economy|the\s+weather|the\s+planet|the\s+earth|plants|animals|humans|children|adults|athletes|performance|appetite|energy|the\s+nervous\s+system|the\s+immune\s+system|the\s+digestive\s+system)$',
    # Round 15 trailing qualifiers
    r'\s+based\s+on\s+a\s+true\s+story$', r'\s+a\s+real\s+place$', r'\s+still\s+around$',
    r'\s+still\s+exist$', r'\s+now$', r'\s+still\s+alive$', r'\s+married\s+to$',
    r'\s+have\s+kids$', r'\s+have\s+children$', r'\s+from\s+[a-z]+$',
    r'\s+are\s+in\s+the\s+world$', r'\s+are\s+on\s+earth$', r'\s+exist\s+in\s+the\s+world$',
    r'\s+in\s+the\s+world\s+today$', r'\s+left\s+in\s+the\s+world$', r'\s+left\s+on\s+earth$',
    r'\s+are\s+left\s+in\s+the\s+world$', r'\s+are\s+left\s+on\s+earth$',
    # Round 16: animal-behavior trailing qualifiers
    r'\s+live$', r'\s+eat$', r'\s+eats$', r'\s+feed\s+on$', r'\s+run$', r'\s+runs$',
    r'\s+fly$', r'\s+flies$', r'\s+jump$', r'\s+dive$', r'\s+swim$', r'\s+swims$',
    r'\s+climb$', r'\s+climbs$', r'\s+talk$', r'\s+talks$', r'\s+purr$', r'\s+purrs$',
    r'\s+bark$', r'\s+meow$', r'\s+hibernate$', r'\s+hibernates$', r'\s+mate$',
    r'\s+nest$', r'\s+migrate$', r'\s+migrates$', r'\s+sing$', r'\s+sings$',
    r'\s+hunt$', r'\s+hunts$', r'\s+attack$', r'\s+attacks$', r'\s+sleep$', r'\s+sleeps$',
    # Round 17: capability/process trailing qualifiers
    r'\s+reproduce$', r'\s+communicate$', r'\s+see$', r'\s+hear$', r'\s+smell$',
    r'\s+navigate$', r'\s+find\s+their\s+way$', r'\s+defend\s+themselves$',
    r'\s+protect\s+themselves$', r'\s+survive$', r'\s+adapt$', r'\s+breathe$',
    r'\s+breathe\s+underwater$', r'\s+see\s+in\s+the\s+dark$', r'\s+walk\s+on\s+walls$',
    r'\s+get$', r'\s+gets$', r'\s+go$', r'\s+travel$', r'\s+hold\s+its\s+breath$',
    r'\s+structured$', r'\s+organized$', r'\s+made\s+up\s+of$',
    # Round 18 trailing qualifiers
    r'\s+most\s+known\s+for$', r'\s+really\s+about$', r'\s+actually\s+about$',
    r'\s+set$', r'\s+set\s+in$', r'\s+based\s+on\s+a\s+book$', r'\s+based\s+on\s+true\s+events$',
    r'\s+written\s+for$', r'\s+made\s+for$', r'\s+known\s+for\s+being$',
    # Round 19: rise/fall/history trailing qualifiers
    r'\s+become\s+popular$', r'\s+become\s+famous$', r'\s+popular$', r'\s+so\s+popular$',
    r'\s+fall$', r'\s+falls$', r'\s+fall\s+apart$', r'\s+collapse$', r'\s+collapses$',
    r'\s+decline$', r'\s+declines$', r'\s+came\s+after$', r'\s+came\s+before$',
    r'\s+succeeded$', r'\s+ended$', r'\s+replaced$', r'\s+rise\s+to\s+power$',
    r'\s+rise\s+and\s+fall$', r'\s+fall\s+of$',
r'\s+rise\s+to\s+power$', r'\s+rise\s+and\s+fall$', r'\s+fall\s+of$',
    # Round 20: health/process trailing qualifiers
    r'\s+edible$', r'\s+safe\s+to\s+eat$', r'\s+poisonous$', r'\s+venomous$',
    r'\s+good\s+for\s+you$', r'\s+bad\s+for\s+you$', r'\s+good\s+for\s+your\s+health$',
    r'\s+bad$', r'\s+unhealthy$', r'\s+healthy$',
    r'\s+harvested$', r'\s+extracted$', r'\s+refined$', r'\s+processed$',
    r'\s+manufactured$', r'\s+cooked$', r'\s+prepared$', r'\s+stored$', r'\s+preserved$',
    r'\s+fermented$', r'\s+brewed$', r'\s+distilled$', r'\s+bottled$', r'\s+packaged$',
    # Round 21 trailing qualifiers
    r'\s+exist$', r'\s+are\s+left$', r'\s+in\s+existence$', r'\s+in\s+circulation$',
    r'\s+currently$', r'\s+today$', r'\s+right\s+now$', r'\s+in\s+the\s+us$',
]


def _apply_slang(text):
    """Apply slang/text-speak normalization: "wat is x" -> "what is x".

    Word-boundary replacements only. Shared by lookup() and unwrap_query().
    """
    _SLANG = [
        (r'\bwat\b', 'what'), (r'\bwut\b', 'what'), (r'\bwat\'s\b', 'what is'),
        (r'\bwats\b', 'what is'), (r'\bwhos\b', 'who is'), (r'\bwhys\b', 'why is'),
        (r'\bhows\b', 'how is'), (r'\bwheres\b', 'where is'), (r'\bwhens\b', 'when is'),
        (r'\bu\b', 'you'), (r'\bur\b', 'your'), (r'\bu\'re\b', 'you are'),
        (r'\bim\b', 'i am'), (r'\bive\b', 'i have'),
        (r'\byr\b', 'your'), (r'\btho\b', 'though'), (r'\btho\b', 'though'),
        (r'\bthx\b', 'thanks'), (r'\bty\b', 'thanks'), (r'\bplz\b', 'please'),
        (r'\bpls\b', 'please'), (r'\bplss\b', 'please'),
        (r'\bcuz\b', 'because'), (r'\bcoz\b', 'because'), (r'\bbc\b', 'because'),
        (r'\bcos\b', 'because'), (r'\bdonno\b', 'do not know'), (r'\bdunno\b', 'do not know'),
        (r'\bidk\b', 'i do not know'), (r'\bwth\b', 'what the heck'),
        (r'\bwtf\b', 'what the'), (r'\brly\b', 'really'), (r'\brlly\b', 'really'),
        (r'\bgonna\b', 'going to'), (r'\bwanna\b', 'want to'), (r'\bgotta\b', 'got to'),
        (r'\bkinda\b', 'kind of'), (r'\bsorta\b', 'sort of'),
        (r'\bsmth\b', 'something'), (r'\bsomethin\b', 'something'),
        (r'\bsomethin\'\b', 'something'), (r'\babt\b', 'about'),
        (r'\bthats\b', 'that is'), (r'\btheres\b', 'there is'), (r'\bheres\b', 'here is'),
        (r'\bbtw\b', 'by the way'), (r'\brn\b', 'right now'), (r'\byall\b', 'you all'),
        (r'\bluv\b', 'love'), (r'\bgud\b', 'good'), (r'\bgr8\b', 'great'),
        (r'\bk\b', 'okay'), (r'\boke\b', 'okay'), (r'\bokeh\b', 'okay'),
        (r'\br\b', 'are'), (r'\by\b', 'why'),
        (r'\bda\b', 'the'), (r'\bdis\b', 'this'),
        (r'\bdat\b', 'that'), (r'\bdem\b', 'them'), (r'\bdere\b', 'there'),
        (r'\bgimme\b', 'give me'), (r'\blemme\b', 'let me'),
        (r'\bwhar\b', 'what'), (r'\bwaht\b', 'what'), (r'\bwahts\b', 'what is'),
        (r'\bwhas\b', 'what is'), (r'\bwass\b', 'what is'), (r'\bwatz\b', 'what is'),
        (r'\bwutz\b', 'what is'), (r'\bwhad\b', 'what'), (r'\bwhadd\b', 'what'),
        (r'\bwen\b', 'when'), (r'\bwhn\b', 'when'), (r'\bwhr\b', 'where'),
        (r'\bwy\b', 'why'), (r'\bhwy\b', 'why'), (r'\biz\b', 'is'),
        (r'\bizit\b', 'is it'), (r'\bar\b', 'are'), (r'\bhav\b', 'have'),
        (r'\bcud\b', 'could'), (r'\bwud\b', 'would'), (r'\bshud\b', 'should'),
        (r'\bdu\b', 'do'), (r'\bdun\b', 'done'), (r'\bbin\b', 'been'),
        (r'\bbcoz\b', 'because'), (r'\bbcz\b', 'because'), (r'\bb/cth\b', 'because'),
        (r'\bnope\b', 'no'), (r'\bnaw\b', 'no'), (r'\byep\b', 'yes'),
        (r'\byeah\b', 'yes'), (r'\byah\b', 'yes'), (r'\byup\b', 'yes'),
        (r'\blil\b', 'little'), (r'\bbout\b', 'about'),
        (r'\bdont\b', 'do not'), (r'\bcant\b', 'cannot'), (r'\bwont\b', 'will not'),
        (r'\bisnt\b', 'is not'), (r'\barent\b', 'are not'), (r'\bwasnt\b', 'was not'),
        (r'\bwerent\b', 'were not'), (r'\bhasnt\b', 'has not'), (r'\bhavent\b', 'have not'),
        (r'\bdoesnt\b', 'does not'), (r'\bdidnt\b', 'did not'), (r'\bcouldnt\b', 'could not'),
        (r'\bwouldnt\b', 'would not'), (r'\bshouldnt\b', 'should not'), (r'\bmustnt\b', 'must not'),
        (r'\bits\b', 'it is'), (r'\byoure\b', 'you are'), (r'\btheyll\b', 'they will'),
        (r'\bshes\b', 'she is'), (r'\bhes\b', 'he is'), (r'\bid\b', 'i would'),
        (r'\bsmh\b', 'shaking my head'), (r'\bomg\b', 'oh my god'), (r'\btbh\b', 'to be honest'),
        (r'\bimo\b', 'in my opinion'), (r'\bimho\b', 'in my humble opinion'),
        (r'\birl\b', 'in real life'), (r'\bjk\b', 'just kidding'), (r'\bidc\b', 'i do not care'),
        (r'\bafaik\b', 'as far as i know'), (r'\biirc\b', 'if i recall correctly'),
        (r'\b2morrow\b', 'tomorrow'), (r'\b2day\b', 'today'), (r'\b2nite\b', 'tonight'),
        (r'\btmrw\b', 'tomorrow'), (r'\bsrsly\b', 'seriously'), (r'\bsrs\b', 'serious'),
        (r'\bdefo\b', 'definitely'), (r'\bdeffo\b', 'definitely'),
        (r'\bprolly\b', 'probably'), (r'\bprobly\b', 'probably'), (r'\bppl\b', 'people'),
        (r'\bsome1\b', 'someone'), (r'\bany1\b', 'anyone'), (r'\bno1\b', 'no one'),
        (r'\bw/e\b', 'whatever'), (r'\bwya\b', 'where are you'), (r'\bwyd\b', 'what are you doing'),
        (r'\bwbu\b', 'what about you'), (r'\bhbu\b', 'how about you'), (r'\bnm\b', 'not much'),
        (r'\bfr\b', 'for real'), (r'\bong\b', 'on god'),
        (r'\bimma\b', 'i am going to'), (r'\bima\b', 'i am going to'), (r'\bfinna\b', 'going to'),
        (r'\btryna\b', 'trying to'), (r'\baint\b', 'is not'), (r'\bwuz\b', 'was'),
        (r'\bwhut\b', 'what'), (r'\bwha\b', 'what'), (r'\bwit\b', 'with'),
        (r'\bwanna\b', 'want to'), (r'\bb4\b', 'before'), (r'\bl8r\b', 'later'),
        (r'\bstr8\b', 'straight'), (r'\bcya\b', 'see you'), (r'\bc\s+u\b', 'see you'),
        (r'\bcud\b', 'could'), (r'\bwud\b', 'would'), (r'\bshud\b', 'should'),
        (r'\bdat\b', 'that'), (r'\bdem\b', 'them'), (r'\bdere\b', 'there'),
        (r'&', ' and '),
        # Round 5
        (r'\bwsp\b', 'what is up'), (r'\bwsg\b', 'what is good'), (r'\byoo\b', 'yo'),
        (r'\bhewwo\b', 'hello'), (r'\bikr\b', 'i know right'), (r'\biono\b', 'i do not know'),
        (r'\bngl\b', 'not going to lie'), (r'\bstg\b', 'swear to god'),
        (r'\bistg\b', 'i swear to god'), (r'\bgotchu\b', 'got you'), (r'\blwk\b', 'lowkey'),
        (r'\bnite\b', 'night'), (r'\bmornin\b', 'morning'),
        (r'\bevenin\b', 'evening'), (r'\bwassup\b', 'what is up'), (r'\bwazup\b', 'what is up'),
        (r'\bwasup\b', 'what is up'), (r'\bwhats\s+up\b', 'what is up'),
        (r'\bsupp\b', 'sup'), (r'\bdeadass\b', 'for real'),
        # Round 6: contractions of question phrases
        (r'\bwhaddya\b', 'what do you'), (r'\bwaddaya\b', 'what do you'),
        (r'\bwhatcha\b', 'what do you'), (r'\bd\'you\b', 'do you'), (r'\bdidja\b', 'did you'),
        (r'\bwouldja\b', 'would you'), (r'\bcouldja\b', 'could you'), (r'\by\'know\b', 'you know'),
        # Round 6: casual verb contractions
        (r'\bhafta\b', 'have to'), (r'\busta\b', 'used to'), (r'\bshoulda\b', 'should have'),
        (r'\bcoulda\b', 'could have'), (r'\bwoulda\b', 'would have'), (r'\bmighta\b', 'might have'),
        (r'\bmusta\b', 'must have'), (r'\boutta\b', 'out of'), (r'\blotsa\b', 'lots of'),
        (r'\bbetcha\b', 'bet you'),
        # Round 7: internet / gaming slang
        (r'\bwym\b', 'what do you mean'), (r'\bwdym\b', 'what do you mean'),
        (r'\btmi\b', 'too much information'), (r'\bsus\b', 'suspicious'),
        (r'\bcringe\b', 'cringeworthy'), (r'\byolo\b', 'you only live once'),
        (r'\bfomo\b', 'fear of missing out'), (r'\biykyk\b', 'if you know you know'),
        (r'\bomw\b', 'on my way'), (r'\bily\b', 'i love you'), (r'\bhmu\b', 'hit me up'),
        (r'\bglhf\b', 'good luck have fun'), (r'\bafk\b', 'away from keyboard'),
        (r'\bidm\b', 'i do not mind'), (r'\bnp\b', 'no problem'),
        (r'\bgg\b', 'good game'), (r'\bwp\b', 'well played'), (r'\bez\b', 'easy'),
        (r'\bnoob\b', 'newbie'), (r'\brekt\b', 'destroyed'),
        # Round 8
        (r'\bight\b', 'alright'), (r'\bsayless\b', 'say less'), (r'\bfrfr\b', 'for real for real'),
        (r'\bokayy\b', 'okay'), (r'\bokayyy\b', 'okay'), (r'\bsuree\b', 'sure'),
        (r'\bidts\b', 'i do not think so'), (r'\bprobz\b', 'probably'),
        (r'\bdats\b', 'that is'), (r'\bidgaf\b', 'i do not care'),
        # Round 9
        (r'\bfyi\b', 'for your information'), (r'\bjs\b', 'just saying'),
        (r'\basap\b', 'as soon as possible'), (r'\baka\b', 'also known as'),
        (r'\bik\b', 'i know'), (r'\bmhm\b', 'mm hmm'), (r'\bsmh\b', 'shaking my head'),
        (r'\bnp\b', 'no problem'), (r'\bidc\b', 'i do not care'), (r'\bidgaf\b', 'i do not care'),
        # Round 10
        (r'\bicymi\b', 'in case you missed it'), (r'\btfw\b', 'that feeling when'),
        (r'\bftw\b', 'for the win'), (r'\bdw\b', 'do not worry'), (r'\btotes\b', 'totally'),
        (r'\bobvi\b', 'obviously'), (r'\bhundo\b', 'one hundred percent'),
        (r'\bfax\b', 'facts'), (r'\brl\b', 'real'),
        # Round 11
        (r'\bhundo\s+p\b', 'one hundred percent'), (r'\bpreciate\b', 'appreciate'),
        (r'\bappreesh\b', 'appreciate'), (r'\ball\s+g\b', 'all good'),
        (r'\bpreesh\b', 'appreciate'), (r'\btotes\s+magotes\b', 'totally'),
        (r'\bwassgood\b', 'what is good'), (r'\bwassup\b', 'what is up'),
        # Round 12
        (r'\bjsyk\b', 'just so you know'), (r'\bjic\b', 'just in case'),
        (r'\bpov\b', 'point of view'), (r'\bfwiw\b', 'for what it is worth'),
        (r'\bggez\b', 'good game easy'), (r'\bunlucky\b', 'that is unlucky'),
        # Round 14
        (r'\bidek\b', 'i do not even know'), (r'\byk\b', 'you know'),
        (r'\bwhatchu\b', 'what do you'), (r'\bwhachu\b', 'what do you'),
        (r'\bbroski\b', 'bro'), (r'\bbrotha\b', 'brother'), (r'\bsis\b', 'sister'),
        (r'\bdawg\b', 'friend'), (r'\bhomie\b', 'friend'),
        # Round 15
        (r'\bbestie\b', 'best friend'), (r'\bbff\b', 'best friend'),
        (r'\bhubby\b', 'husband'), (r'\bwifey\b', 'wife'), (r'\bboi\b', 'boy'),
        (r'\bgurl\b', 'girl'), (r'\bcuh\b', 'cousin'), (r'\bsupa\b', 'super'),
        (r'\bbros\b', 'brothers'), (r'\bsis\b', 'sister'),
        # Round 16
        (r'\bkewl\b', 'cool'), (r'\bsanks\b', 'thanks'), (r'\bmmhm\b', 'mm hmm'),
        # Round 17
        (r'\bprobs\b', 'probably'), (r'\bbday\b', 'birthday'), (r'\bidky\b', 'i do not know why'),
        (r'\bkthx\b', 'thanks'), (r'\btysvm\b', 'thank you so much'),
        (r'\bxoxo\b', 'hugs and kisses'), (r'\bsmt\b', 'something'),
        # Round 18
        (r'\bnoice\b', 'nice'), (r'\bnooice\b', 'nice'), (r'\bniceee\b', 'nice'),
        (r'\bsheeeeesh\b', 'sheesh'), (r'\bggwp\b', 'good game well played'),
        (r'\bhol\s+up\b', 'hold up'), (r'\bhol\'\s+up\b', 'hold up'), (r'\blmaooo\b', 'laughing my a off'),
        # Round 19
        (r'\b100%\b', 'one hundred percent'), (r'\b100\s*percent\b', 'one hundred percent'),
        # Round 21
        (r'\bpeeps\b', 'people'), (r'\bya\'ll\b', 'you all'), (r'\brizz\b', 'charisma'),
        # Round 22
        (r'\bbffr\b', 'be for real'), (r'\bdeadass\b', 'for real'), (r'\bngl\b', 'not going to lie'),
    ]
    result = text
    for pat, repl in _SLANG:
        result = re.sub(pat, repl, result)
    return result


def unwrap_query(query):
    """Strip casual question wrappers and trailing qualifiers from a query.

    "whats the story of the titanic" -> "titanic"
    "do you know what photosynthesis is" -> "photosynthesis is"
    "explain the milgram experiment like i'm five" -> "the milgram experiment"

    Returns the cleaned string (unchanged if nothing matched). Used by lookup()
    as a matching variant and by the engine for better Wikipedia fallback.
    """
    q = query.lower().strip()
    q = re.sub(r'[\"\'\'\"\“\”\‘\’]', '', q)
    q = re.sub(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]', '', q)
    q = re.sub(r'\s+', ' ', q).strip()
    q = q.rstrip('?!.;,').strip()

    unwrapped = q
    # Normalize slang FIRST so wrappers/trailing qualifiers see the
    # expanded form ("rock & roll history" -> "rock and roll history").
    slanged = _apply_slang(unwrapped)
    if slanged != unwrapped:
        unwrapped = slanged
    # "i don't know what X is" / "idk what X is" -> "what is X"
    _idk_match = re.match(
        r'^i\s+do\s+not\s+know\s+what\s+(?:a\s+|an\s+|the\s+)?(.+?)(?:\s+is|\s+are|\s+means?|\s+means|\s+stand\s+for|\s+was|\s+were)?$',
        unwrapped)
    if _idk_match:
        _idk_topic = _idk_match.group(1).strip()
        if len(_idk_topic) > 2:
            unwrapped = f"what is {_idk_topic}"
    for wrapper in _QUESTION_WRAPPERS:
        stripped = re.sub(wrapper, '', unwrapped, flags=re.IGNORECASE).strip()
        if stripped and len(stripped) > 3 and stripped != unwrapped:
            unwrapped = stripped
            break
    for qual in _TRAILING_QUALIFIERS:
        unwrapped = re.sub(qual, '', unwrapped, flags=re.IGNORECASE).strip()
    if unwrapped != q and len(unwrapped) < 5:
        unwrapped = f"what is {unwrapped}"
    return unwrapped


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
    q = re.sub(r'[\"\'\'\"\“\”\‘\’]', '', q)
    # Strip emoji and common symbols that add no search meaning
    q = re.sub(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]', '', q)
    q = re.sub(r'\s+', ' ', q).strip()
    # Strip trailing sentence-ending punctuation (?, !, ., ;) that can prevent
    # KB entries ending in "?" from matching user queries without trailing "?"
    q = q.rstrip('?!.;,').strip()

    # Slang/text-speak normalization: "wat is x" -> "what is x", "u" -> "you"
    # so KB patterns match casual phrasing. Word-boundary replacements only.
    q_slang = _apply_slang(q)
    if q_slang == q:
        q_slang = None

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
        r'^how\s+(?:does|do|would|can|should|could)\s+(?:(?:a|an|the|this|that|i|we|you|they|he|she|it)\s+)?',
        r'^why\s+(?:is|are|do|does|did|would|could|should)\s+(?:(?:a|an|the|this|that|i|we|you|they|he|she|it)\s+)?',
    ]
    q_writing_stripped = q
    for prefix in _WRITING_PREFIXES:
        stripped = re.sub(prefix, '', q, flags=re.IGNORECASE).strip()
        if stripped and len(stripped) > 5 and stripped != q:
            q_writing_stripped = stripped
            break

    # Create a variant with casual question wrappers stripped via the
    # module-level unwrap_query() helper (defined above lookup).
    q_unwrapped = unwrap_query(q)
    if q_unwrapped == q:
        q_unwrapped = None

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
    if q_slang and q_slang not in variants:
        variants.append(q_slang)
    if q_unwrapped and q_unwrapped not in variants:
        variants.append(q_unwrapped)
    # Add the writing-stripped variant if different
    if q_writing_stripped != q and q_writing_stripped not in variants:
        variants.append(q_writing_stripped)

    # Candidate pre-filter: an escaped-literal pattern can only match a
    # variant that contains every one of its words. For each variant, take its
    # rarest (least-common) word and pull that word's candidate list — the
    # rarest word of a natural-language query is almost always the content
    # noun that matching patterns also contain. Union across variants (so
    # slang-normalized variants like "what is a cat" contribute their own
    # candidates even when the raw query has none), then verify each entry's
    # word set is fully contained in the variant word union (raw-regex
    # entries always pass).
    _candidate_indices = set(_RAW_ENTRY_INDICES)
    _variant_words = set()
    for _v in variants:
        if not _v or len(_v) < 3:
            continue
        _vwords = _word_tokens(_v)
        if not _vwords:
            continue
        _variant_words |= _vwords
        _vrarest = min(_vwords, key=lambda w: len(_WORD_INDEX.get(w, ())))
        _candidate_indices |= set(_WORD_INDEX.get(_vrarest, ()))

    for _ci in sorted(_candidate_indices):
        pattern, answer = entries[_ci]
        _entry_word_set = _ENTRY_WORDS[_ci]
        if _entry_word_set is not None and not (_entry_word_set <= _variant_words):
            continue
        for variant in variants:
            if not variant or len(variant) < 3:
                continue
            m = pattern.search(variant)
            if m:
                match_len = len(m.group(0))
                # Require at least 3 characters to match — prevents accidental
                # matches like 'c' (from regex 'c++') matching 'metallic'
                if match_len >= 3:
                    # Matches on the cleaned topic (q_unwrapped) are a much
                    # stronger signal than equal-length matches on the raw
                    # query — "is the moon a planet" should match "the moon"
                    # (4 chars) over "a planet" (8 chars) on the raw query.
                    if variant is q_unwrapped or variant == q_unwrapped:
                        match_len += 5
                    if match_len > best_match_len:
                        best_match_len = match_len
                        best_answer = answer

    # Word-overlap fallback: if no exact substring match found, try
    # matching by keyword overlap. This lets patterns match queries that
    # have the right words but in a different order or with extra words.
    if not best_answer:
        try:
            # Extract key content words from the query (exclude stop words)
            # Prefer the unwrapped query so "is the moon a planet" matches
            # "the moon" rather than fuzzy-matching "planet".
            _fuzzy_source = q_unwrapped if q_unwrapped else q
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
            q_words = set(w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', _fuzzy_source)
                         if w.lower() not in _STOP_WORDS_FUZZY)
            if q_words:
                def _fuzzy_word_match(w, words):
                    """True if w (or its singular/plural form) is in the set:
                    capitals matches capital and vice versa."""
                    if w in words:
                        return True
                    if len(w) > 4 and w.endswith('s') and not w.endswith('ss') \
                            and w[:-1] in words:
                        return True
                    if len(w) > 3 and w + 's' in words:
                        return True
                    return False
                best_fuzzy_score = -999999  # Can be negative (with penalty)
                best_fuzzy_answer = None
                best_fuzzy_pattern = ''
                # Fuzzy candidates: any entry sharing at least one query word
                # (plus raw-regex entries). Winners need raw_hits >= 2, so
                # entries sharing zero words can never win and are skipped.
                _fuzzy_candidates = set(_RAW_ENTRY_INDICES)
                for _w in q_words:
                    _fuzzy_candidates |= _WORD_INDEX.get(_w, ())
                for _ci in _fuzzy_candidates:
                    pattern, answer = entries[_ci]
                    pattern_str = pattern.pattern.lower()
                    p_words = set(w for w in re.findall(r'\b[a-zA-Z]{3,}\b', pattern_str)
                                  if w not in _STOP_WORDS_FUZZY)
                    # Count how many query words appear in the pattern
                    # (singular/plural forms count: "capitals" ~ "capital")
                    word_hits = sum(1 for w in q_words if _fuzzy_word_match(w, p_words))
                    # PENALTY: Count pattern words NOT in query (prevents false matches)
                    extraneous = len([pw for pw in p_words
                                      if not _fuzzy_word_match(pw, q_words)])
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
                best_p_words = set(w for w in re.findall(r'\b[a-zA-Z]{3,}\b', best_fuzzy_pattern)
                                   if w not in _STOP_WORDS_FUZZY)
                raw_hits = sum(1 for w in q_words if _fuzzy_word_match(w, best_p_words))
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
