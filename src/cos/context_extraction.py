"""
COS Context Extraction — Symbolic multi-strategy keyword/topic/entity extraction.

Extracts search keywords, main topics, and named entities from natural language
queries using purely symbolic methods. No neural networks, no LLMs, no GGUF models.

Strategies (chained by precision then recall):
  1. Question Deconstruction     — Pattern-based removal of question words/structures
  2. Noun Phrase Chunking        — Adjective + noun sequence extraction
  3. Entity Detection            — Capitalized words, quoted phrases, named references
  4. Content Word Scoring        — TF-IDF-like scoring of significant terms
  5. Compound Phrase Detection   — Bigram/trigram multi-word compound recognition
  6. Verb Phrase Extraction      — Action-oriented context (make french fries -> french fries)
  7. Cleaned Fallback            — Stopword-removed, normalized full query

Every public function is pure — no I/O, no network, no global state.
All functions accept and return plain Python types for easy testing.

Usage:
    >>> extract_keywords("What is the capital of France?")
    [('france', 0.95), ('capital of france', 0.85)]

    >>> extract_topic("How does photosynthesis work?")
    ('photosynthesis', 0.92)

    >>> classify_question("What is the capital of France?")
    'factual_definition'
"""

import re
from typing import List, Tuple, Optional, Dict, Set, Literal

# ═════════════════════════════════════════════════════════════════════════════
# Constants — Stop Word Sets
# ═════════════════════════════════════════════════════════════════════════════

_STOP_WORDS: frozenset = frozenset({
    'a', 'an', 'the', 'this', 'that', 'these', 'those',
    'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
    'may', 'might', 'must', 'shall', 'can',
    'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
    'my', 'your', 'his', 'its', 'our', 'their', 'mine', 'yours', 'hers', 'ours', 'theirs',
    'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'into', 'onto', 'upon',
    'about', 'around', 'between', 'through', 'during', 'before', 'after', 'above', 'below',
    'and', 'or', 'but', 'nor', 'yet', 'so', 'because', 'if', 'when', 'while', 'where',
    'why', 'how', 'what', 'which', 'who', 'whom', 'whose',
    'not', 'no', 'nor', 'never', 'neither',
    'just', 'also', 'very', 'too', 'quite', 'rather', 'somewhat',
    'here', 'there', 'then', 'than', 'now', 'well',
    'much', 'many', 'some', 'any', 'all', 'both', 'each', 'every', 'few', 'more', 'most',
    'other', 'such', 'only', 'own', 'same',
    'up', 'down', 'out', 'off', 'over', 'under',
    'get', 'got', 'gotten', 'make', 'made', 'take', 'took', 'taken',
    'tell', 'show', 'give', 'find', 'know', 'like', 'want', 'need', 'use', 'used',
    'thing', 'things', 'way', 'ways', 'part', 'parts',
})

_QUESTION_STOP_WORDS: frozenset = frozenset({
    'what', 'who', 'whom', 'whose', 'which', 'why', 'where', 'when', 'how',
    'is', 'are', 'was', 'were', 'does', 'do', 'did', 'can', 'could', 'would', 'should',
    'will', 'may', 'might', 'shall',
    'tell', 'show', 'explain', 'describe', 'define', 'list', 'name',
    'me', 'us', 'the', 'a', 'an',
})

# ═════════════════════════════════════════════════════════════════════════════
# Constants — Semantic Sets
# ═════════════════════════════════════════════════════════════════════════════

# Known compound concepts (multi-word terms that should stay together)
_KNOWN_COMPOUNDS: frozenset = frozenset({
    'french fries', 'french fry', 'machine learning', 'artificial intelligence',
    'deep learning', 'reinforcement learning', 'natural language processing',
    'quantum computing', 'quantum mechanics', 'dark matter', 'dark energy',
    'black hole', 'black holes', 'solar system', 'solar panel', 'solar panels',
    'world war', 'world war ii', 'world war i', 'world war 2', 'world war 1',
    'cold war', 'civil war', 'stock market', 'real estate',
    'global warming', 'climate change', 'climate crisis',
    'roman empire', 'ottoman empire', 'byzantine empire',
    'middle ages', 'middle east', 'far east',
    'new york', 'new york city', 'los angeles', 'san francisco',
    'united states', 'united kingdom', 'united nations', 'united arab emirates',
    'new zealand', 'south africa', 'south korea', 'north korea',
    'great britain', 'great barrier reef', 'great depression',
    'eiffel tower', 'liberty statue', 'statue of liberty',
    'golden gate bridge', 'great wall', 'great wall of china',
    'magna carta', 'bill of rights', 'prime minister', 'president of',
    'search engine', 'operating system', 'operating systems',
    'central processing unit', 'graphics processing unit',
    'computer science', 'data science', 'data structure', 'data structures',
    'software engineering', 'software development',
    'web development', 'mobile development', 'game development',
    'object oriented', 'object oriented programming',
    'graphical user interface', 'command line interface',
    'human being', 'human beings', 'human race',
    'life cycle', 'life on earth', 'natural selection',
    'cell phone', 'cell phones', 'smart phone', 'smart phones',
    'social media', 'social network', 'social networks',
    'vice president', 'chief executive', 'chief executive officer',
    'ice cream', 'peanut butter', 'baking soda', 'olive oil',
    'credit card', 'credit cards', 'debit card', 'debit cards',
    'high school', 'middle school', 'elementary school',
    'law enforcement', 'health care', 'healthcare',
    'world record', 'chain reaction', 'nuclear reaction',
    'barack obama', 'albert einstein', 'marie curie', 'isaac newton',
    'elon musk', 'steve jobs', 'bill gates', 'martin luther king',
    'martin luther', 'sigmund freud', 'charles darwin',
    'william shakespeare', 'winston churchill', 'nelson mandela',
    'mahatma gandhi', 'mother teresa', 'queen elizabeth',
    'turing test', 'turing machine',
    'large language model', 'small language model',
    'neural network', 'neural networks', 'expert system', 'expert systems',
    'frequently asked questions', 'frequently asked question',
    'science fiction', 'virtual reality', 'augmented reality',
    'holy bible', 'holy grail', 'holy roman empire',
    'post office', 'white house', 'pentagon building',
    'milky way', 'milky way galaxy', 'andromeda galaxy',
    'van gogh', 'leonardo da vinci', 'vincent van gogh',
    'pablo picasso', 'michaelangelo', 'michelangelo',
})

# Light verbs that signal the object is the topic (not the verb)
_LIGHT_VERBS: frozenset = frozenset({
    'make', 'makes', 'making', 'made',
    'bake', 'bakes', 'baking', 'baked',
    'cook', 'cooks', 'cooking', 'cooked',
    'create', 'creates', 'creating', 'created',
    'build', 'builds', 'building', 'built',
    'write', 'writes', 'writing', 'wrote',
    'draw', 'draws', 'drawing', 'drew',
    'paint', 'paints', 'painting', 'painted',
    'play', 'plays', 'playing', 'played',
    'sing', 'sings', 'singing', 'sang',
    'use', 'uses', 'using', 'used',
    'find', 'finds', 'finding', 'found',
    'do', 'does', 'doing', 'did', 'done',
})

# Words that suggest we should look for compounds before/after them
_COMPOUND_HINT_WORDS: frozenset = frozenset({
    'of', 'in', 'for', 'and', 'vs', 'versus',
})

# Redundant/empty topics
_EMPTY_TOPICS: frozenset = frozenset({
    'this', 'that', 'it', 'them', 'those', 'these',
    'something', 'anything', 'nothing', 'everything',
    'things', 'stuff', 'someone', 'somebody', 'anyone', 'anybody',
    'more', 'some', 'any', 'all', 'such',
})

# ═════════════════════════════════════════════════════════════════════════════
# Patterns
# ═════════════════════════════════════════════════════════════════════════════

_QUESTION_PATTERNS: List[Tuple[str, int, float]] = [
    # --- Core fact patterns (high precision) ---
    (r'(?:what|which)\s+(?:is|are|was|were)\s+(?:a|an|the|this|that|these|those)?\s*(.+)', 1, 0.90),
    (r'what\'?[sS]\s+(?:a|an|the|this|that)?\s*(.+)', 1, 0.88),
    (r'who\s+(?:is|are|was|were)\s+(.+)', 1, 0.87),
    (r'where\s+(?:is|are|was|were|can|do|does)\s+(?:i|we|you|they|he|she|it)?\s*(.+)', 1, 0.85),
    (r'when\s+(?:is|are|was|were|did|does|do|will)\s+(.+)', 1, 0.85),

    # --- Causal/reason patterns ---
    (r'why\s+(?:is|are|was|were|does|do|did|would|can)\s+(?:i|we|you|they|he|she|it)?\s*(.+)', 1, 0.80),

    # --- How patterns ---
    (r'how\s+(?:does|do|is|are|can|would|will|shall|could|to)\s+(?:i|we|you|they|he|she|it|one)?\s*(?:to\s+)?(?:make|bake|cook|create|build|write|find|get|know|use|fix|do)?\s*(.+)', 1, 0.82),
    (r'how\s+(?:many|much)\s+(.+?)\??$', 1, 0.80),
    (r'how\s+(?:big|large|small|far|long|tall|deep|wide|heavy|fast|slow|high|low|old|hot|cold)\s+(?:is|are|was|were)\s+(.+)', 1, 0.84),

    # --- Request patterns ---
    (r'tell\s+(?:me|us)\s+about\s+(.+)', 1, 0.88),
    (r'tell\s+(?:me|us)\s+(?:what|how)\s+(.+)', 1, 0.82),
    (r'show\s+(?:me|us)\s+(.+)', 1, 0.85),

    # --- Definition/explanation patterns ---
    (r'(?:explain|describe|define)\s+(?:the\s+)?(?:concept\s+of\s+|meaning\s+of\s+|idea\s+of\s+)?(.+)', 1, 0.90),
    (r'define\s+(.+)', 1, 0.88),

    # --- "Give me" patterns ---
    (r'give\s+(?:me|us)\s+(?:a|an|the|some)?\s*(.+)', 1, 0.75),

    # --- Personal statement patterns ---
    (r'i\s+(?:like|love|enjoy|hate|prefer|want|have|use|know|own)\s+(.+?)(?:\.|$|\sand)', 1, 0.80),

    # --- Creation patterns ---
    (r'(?:write|create|make|compose|draft|generate)\s+(?:a|an|the)?\s*(?:\w+\s+){0,4}(?:about|on|regarding|concerning)\s+(.+)', 1, 0.85),

    # --- Action patterns ---
    (r'what\s+(?:do|does)\s+(.+?)\s+do\??', 1, 0.82),
    (r'what\s+is\s+the\s+name\s+of\s+(.+)', 1, 0.85),
    (r'(?:list|name|enumerate)\s+(?:the\s+)?(.+)', 1, 0.78),

    # --- Comparison patterns ---
    (r'(?:compare|difference|between|versus|vs\.?)\s+(.+?)\s+(?:and|vs\.?|versus)\s+(.+)', 1, 0.70),
]

_NOUN_PHRASE_RE = re.compile(
    r'(?:(?:a|an|the|this|that|these|those|some|any|my|your|his|her|its|our|their)\s+)?'
    r'(?:(?:\w+ly|un\w+|in\w+|dis\w+|over\w+|under\w+|re\w+|\w+ful|\w+less|\w+ous|\w+ive|\w+able|\w+ible|\w+al|\w+ent|\w+ant|\w+ic|\w+ish|\w+like|\w+y)\s+)*'
    r'([A-Z]?\w+(?:\s+[A-Z]?\w+){0,4})'
    r'(?:\s+(?:is|are|was|were|has|have|had|does|do|did|will|would|can|could|may|might|shall|should|make|made|take|took|use|used|find|found|show|shown|give|gave|tell|told|know|knew|known))?',
    re.IGNORECASE
)

_ENTITY_RE = re.compile(r'"([^"]+)"|\'([^\']+)\'|([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)')
_CAPITALIZED_WORD_RE = re.compile(r'\b([A-Z][a-z]{2,})\b')

# Question type patterns
_YES_NO_PATTERNS = [
    r'^(?:is|are|was|were|has|have|had|does|do|did|will|would|can|could|may|might|shall|should)\s',
    r'\?.*\?\s*$',  # Multiple question marks
]

_FACTUAL_PATTERNS = [
    r'^what\s+(?:is|are|was|were)',
    r'^which\s+(?:\w+\s+)?(?:is|are|was|were)',
    r'^who\s+(?:is|are|was|were)',
    r'^where\s+(?:is|are|was|were)',
    r'^when\s+(?:is|was|were|did)',
]

_HOW_TO_PATTERNS = [
    r'^how\s+(?:to|do|does|can|would)',
    r'(?:how|way|method|technique|process|steps?|instructions?)\s+(?:to|for|of)',
]

_WHY_PATTERNS = [
    r'^why\s+',
    r'(?:reason|cause|purpose|motive|explanation)\s+(?:for|behind|of|why)',
]

_ADJECTIVE_SUFFIXES = frozenset({
    'ful', 'less', 'ous', 'ive', 'able', 'ible', 'al', 'ent', 'ant',
    'ic', 'ish', 'like', 'y', 'ly', 'some', 'oid',
})

# ═════════════════════════════════════════════════════════════════════════════
# Cleaning / Normalization
# ═════════════════════════════════════════════════════════════════════════════

def clean_query(query: str) -> str:
    """Normalize and clean a query string.

    - Strips whitespace
    - Collapses multiple spaces
    - Removes punctuation (keeps hyphens in compound words, apostrophes in contractions)
    - Lowercases
    """
    q = query.strip()
    q = re.sub(r'\s+', ' ', q)
    q = q.rstrip('.!?,;:')
    q = q.lower()
    return q


def remove_stop_words(text: str, stop_set: frozenset = _STOP_WORDS) -> str:
    """Remove stop words from text, preserving word order."""
    if not text:
        return ""
    words = text.split()
    result = [w for w in words if w not in stop_set]
    return ' '.join(result)


def collapse_whitespace(text: str) -> str:
    """Collapse multiple whitespace characters into a single space."""
    return re.sub(r'\s+', ' ', text).strip()


# ═════════════════════════════════════════════════════════════════════════════
# Strategy 0: Question Type Classification
# ═════════════════════════════════════════════════════════════════════════════

QuestionType = Literal[
    "factual_definition", "factual_location", "factual_person",
    "how_to", "why_causal", "yes_no", "comparison",
    "instruction", "personal", "follow_up", "unknown",
]


def classify_question(query: str) -> QuestionType:
    """Classify a query into a question type using symbolic patterns.

    Pure function — no I/O, no side effects.

    Args:
        query: The user's query string.

    Returns:
        QuestionType string identifying the class of question.
    """
    q = query.lower().strip()
    if not q:
        return "unknown"

    # Comparison detection (MUST be before factual since "what is the difference..." matches both)
    if re.search(r'(?:compare|difference|between|versus|vs\.?)', q):
        if not re.search(r'(?:>|<|=|\+|\-|\*)', q):  # not math
            return "comparison"

    # Yes/no questions
    if q.endswith('?'):
        for pat in _YES_NO_PATTERNS:
            if re.search(pat, q):
                return "yes_no"

    # Factual what/who/where/when
    for pat in _FACTUAL_PATTERNS:
        if re.search(pat, q):
            if q.startswith('who'):
                return "factual_person"
            if q.startswith('where'):
                return "factual_location"
            return "factual_definition"

    # How-to
    for pat in _HOW_TO_PATTERNS:
        if re.search(pat, q):
            return "how_to"

    # Why/causal
    for pat in _WHY_PATTERNS:
        if re.search(pat, q):
            return "why_causal"

    # Personal statements
    if re.search(r'^\s*i\s+(?:like|love|enjoy|hate|prefer|want|have|use|know|own|am|think|believe|feel)', q):
        return "personal"

    # Instruction/imperative
    if re.search(r'^(?:write|create|make|draw|paint|sing|tell|show|give|list|find|describe|explain|define)\b', q):
        return "instruction"

    return "unknown"


# ═════════════════════════════════════════════════════════════════════════════
# Strategy 1: Question Deconstruction
# ═════════════════════════════════════════════════════════════════════════════

def extract_by_question_pattern(query: str) -> List[Tuple[str, float]]:
    """Extract the key phrase from a question using pattern matching.

    Tries each question pattern in order and returns matches
    with confidence weights, sorted by score descending.

    Pure function — no I/O, no side effects.
    """
    q_lower = query.lower().strip()
    results: List[Tuple[str, float]] = []

    if not q_lower:
        return results

    for pattern, group, weight in _QUESTION_PATTERNS:
        m = re.search(pattern, q_lower)
        if m:
            phrase = m.group(group).strip().rstrip('.!?,;: ')
            phrase = collapse_whitespace(phrase)
            if phrase and len(phrase) > 1:
                if phrase.lower() not in _EMPTY_TOPICS:
                    results.append((phrase, weight))

    # Deduplicate keeping highest score
    seen: Dict[str, float] = {}
    for phrase, score in results:
        key = phrase.lower()
        if key not in seen or score > seen[key]:
            seen[key] = score

    sorted_results = [(p, s) for p, s in sorted(seen.items(), key=lambda x: -x[1])]
    return sorted_results


# ═════════════════════════════════════════════════════════════════════════════
# Strategy 2: Noun Phrase Chunking
# ═════════════════════════════════════════════════════════════════════════════

def extract_noun_phrases(text: str) -> List[Tuple[str, float]]:
    """Extract likely noun phrases using heuristic patterns.

    Uses regex-based pattern matching, with scoring that accounts for
    phrase length, proper noun detection, and content word presence.

    Pure function — no I/O, no side effects.
    """
    results: List[Tuple[str, float]] = []
    if not text or not text.strip():
        return results

    matches = _NOUN_PHRASE_RE.finditer(text)
    for m in matches:
        phrase = m.group(0).strip()
        if not phrase or len(phrase) < 2:
            continue

        words = phrase.split()

        # Skip pure stop words
        if all(w.lower() in _STOP_WORDS for w in words):
            continue

        # Multi-dimensional scoring
        score = 0.45  # base

        has_proper = any(w[0].isupper() for w in words if w)
        has_content = any(w.lower() not in _STOP_WORDS for w in words)

        # Penalty for clause verbs
        clause_markers = {'is', 'are', 'was', 'were', 'has', 'have', 'had',
                          'does', 'do', 'did', 'will', 'would', 'can', 'could',
                          'may', 'might', 'shall', 'should'}
        pronoun_markers = {'i', 'you', 'he', 'she', 'it', 'we', 'they',
                           'me', 'him', 'her', 'us', 'them',
                           'this', 'that', 'these', 'those'}
        has_clause_verb = any(w.lower() in clause_markers for w in words)
        has_pronoun = any(w.lower() in pronoun_markers for w in words)

        # Check if the phrase is a known compound (bonus)
        phrase_lower = phrase.lower()
        is_known_compound = phrase_lower in _KNOWN_COMPOUNDS

        if has_proper:
            score += 0.18
        if has_content:
            score += 0.12
        if len(words) >= 2:
            score += 0.08  # multi-word phrases are more specific
        if len(words) >= 3:
            score += 0.05  # tri-grams are even more specific
        if len(phrase) > 15 and not has_clause_verb:
            score += 0.05
        if is_known_compound:
            score += 0.25  # major boost for known compounds

        # Penalties
        if has_clause_verb:
            score -= 0.35
        if has_pronoun:
            score -= 0.25
        if len(phrase) < 5:
            score -= 0.15
        if phrase_lower in _EMPTY_TOPICS:
            score -= 0.50

        score = min(max(score, 0.0), 1.0)
        results.append((phrase.strip(), score))

    # Sort by score descending
    results.sort(key=lambda x: -x[1])
    return results


# ═════════════════════════════════════════════════════════════════════════════
# Strategy 3: Entity Detection
# ═════════════════════════════════════════════════════════════════════════════

def extract_entities(text: str) -> List[Tuple[str, float]]:
    """Extract named entities from text.

    Detects:
      - Quoted phrases ("like this") — high confidence
      - Capitalized multi-word names (United States) — medium-high confidence
      - Capitalized single words (proper nouns) — medium confidence
      - Known compound terms (case-insensitive match) — medium-low confidence

    Pure function — no I/O, no side effects.
    """
    results: List[Tuple[str, float]] = []
    seen: Set[str] = set()

    if not text or not text.strip():
        return results

    # Quoted phrases (high confidence)
    for m in _ENTITY_RE.finditer(text):
        phrase = m.group(1) or m.group(2) or m.group(3)
        if phrase and phrase.strip():
            phrase = phrase.strip()
            key = phrase.lower()
            if key not in seen and len(phrase) > 1:
                seen.add(key)
                score = 0.92 if (m.group(1) or m.group(2)) else 0.82
                results.append((phrase, score))

    # Capitalized words (potential proper nouns)
    for m in _CAPITALIZED_WORD_RE.finditer(text):
        word = m.group(1)
        key = word.lower()
        if key not in seen and len(word) > 2 and word.lower() not in _STOP_WORDS:
            seen.add(key)
            results.append((word, 0.60))

    # Check for known compounds in the text (lowercase matches)
    text_lower = text.lower()
    for compound in sorted(_KNOWN_COMPOUNDS, key=len, reverse=True):
        if compound in text_lower:
            key = compound
            if key not in seen:
                seen.add(key)
                results.append((compound.title() if text[0].isupper() else compound, 0.70))

    return results


# ═════════════════════════════════════════════════════════════════════════════
# Strategy 4: Content Word Scoring
# ═════════════════════════════════════════════════════════════════════════════

_WORD_SIGNIFICANCE_CACHE: Dict[str, float] = {}


def _word_significance(word: str, query: str) -> float:
    """Score a word's significance within a query (0.0 to 1.0).

    Factors:
      - Length: longer words carry more meaning
      - Position: words near the end of questions are often the target
      - Capitalization: proper nouns are significant
      - Rarity relative to stop words
      - Adjective/compound suffix bonus
      - Noun phrase context bonus

    Cacheable by (word, query) for performance in batch processing.

    Pure function — no I/O, no side effects.
    """
    w_orig = word
    w_lower = word.lower()
    score = 0.30  # base

    # Length bonus (longer = more specific)
    if len(word) >= 10:
        score += 0.30
    elif len(word) >= 8:
        score += 0.22
    elif len(word) >= 6:
        score += 0.15
    elif len(word) >= 4:
        score += 0.05

    # Capitalization bonus (proper nouns)
    if word[0].isupper():
        score += 0.15

    # Position bonus: words near the end of questions are often key targets
    q_lower = query.lower()
    idx = q_lower.find(w_lower)
    if idx >= 0:
        pos_ratio = idx / max(len(q_lower), 1)
        # Words in the second half of the query get a bonus
        if pos_ratio > 0.5:
            score += 0.12
        # Last 30% gets even more
        if pos_ratio > 0.7:
            score += 0.08
        # Words at the very end
        if pos_ratio > 0.85:
            score += 0.05

    # Adjective/compound suffix bonus (words ending in -tion, -ment, -ity, etc.)
    if any(w_lower.endswith(s) for s in ('tion', 'sion', 'ment', 'ity', 'ness', 'ence', 'ance')):
        score += 0.10
    if any(w_lower.endswith(s) for s in ('ing', 'ism', 'ist', 'ian', 'eer')):
        score += 0.05

    # Penalty for very common words not in stop list
    common_words = {'also', 'very', 'just', 'really', 'quite', 'rather', 'well',
                    'still', 'even', 'much', 'many', 'some', 'any', 'thing',
                    'stuff', 'way', 'make', 'made', 'like', 'get', 'got'}
    if w_lower in common_words:
        score -= 0.20

    # Bonus for multi-syllable words (indicative of significance)
    syllable_count = max(1, len(re.findall(r'[aeiouy]+', w_lower)))
    if syllable_count >= 3:
        score += 0.08

    return min(max(score, 0.0), 1.0)


def extract_content_words(text: str, max_words: int = 10) -> List[Tuple[str, float]]:
    """Extract and score significant content words from text.

    Removes stop words, scores remaining words by significance,
    and returns the top-scoring words as (word, score) pairs.

    Pure function — no I/O, no side effects.
    """
    if not text or not text.strip():
        return []

    cleaned = remove_stop_words(text.lower(), _STOP_WORDS)
    words = cleaned.split()

    scored: List[Tuple[str, float]] = []
    seen: Set[str] = set()
    for w in words:
        w_clean = w.strip('"\'(),.!?;:-')
        if not w_clean or len(w_clean) < 3:
            continue
        key = w_clean.lower()
        if key in seen:
            continue
        seen.add(key)

        if key in _EMPTY_TOPICS:
            continue

        score = _word_significance(w_clean, text)
        scored.append((w_clean, score))

    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored[:max_words]


# ═════════════════════════════════════════════════════════════════════════════
# Strategy 5: Compound Phrase Detection (NEW)
# ═════════════════════════════════════════════════════════════════════════════

def extract_compound_phrases(query: str) -> List[Tuple[str, float]]:
    """Extract multi-word compound phrases using known compounds and patterns.

    Two-phase approach:
      1. Dictionary lookup against _KNOWN_COMPOUNDS
      2. Algorithmic detection of adjective-noun and noun-noun compounds

    Pure function — no I/O, no side effects.
    """
    results: List[Tuple[str, float]] = []
    if not query or not query.strip():
        return results

    q_lower = query.lower().strip()

    # Phase 1: Check known compounds
    for compound in sorted(_KNOWN_COMPOUNDS, key=len, reverse=True):
        if compound in q_lower:
            # Calculate confidence based on match quality
            match_idx = q_lower.index(compound)
            # Closer to end of query = more likely the target
            pos_ratio = match_idx / max(len(q_lower), 1)
            score = 0.75  # base for known compound
            if pos_ratio > 0.5:
                score += 0.10
            if len(compound.split()) >= 3:
                score += 0.05  # tri-gram compounds are more specific
            results.append((compound, min(score, 0.95)))

    # Phase 2: Algorithmic compound detection
    # Look for "X of Y" patterns where X and Y are content words
    # Strip leading stop words from X (e.g., "the capital" -> "capital")
    of_pattern = re.findall(r'(\w+(?:\s+\w+){0,2})\s+of\s+(\w+(?:\s+\w+){0,3})', q_lower)
    for left, right in of_pattern:
        # Strip leading stop words from left
        left_words = left.split()
        while left_words and left_words[0] in _STOP_WORDS:
            left_words = left_words[1:]
        left_clean = ' '.join(left_words)
        if left_clean and right not in _STOP_WORDS and left_clean[0] not in 'wq':  # skip question words
            compound = f"{left_clean} of {right}"
            compound_key = compound.lower()
            if not any(compound_key == c.lower() for c, _ in results):
                results.append((compound, 0.72))

    # Phase 3: Detect adjacent content words that form compounds
    # (algorithmic bigram/trigram detection)
    words = q_lower.split()
    for i in range(len(words) - 1):
        # Skip if any word is a stop word
        if words[i] in _STOP_WORDS or words[i + 1] in _STOP_WORDS:
            continue
        # Skip if words are clause markers
        if words[i] in {'is', 'are', 'was', 'were', 'has', 'have', 'do', 'does', 'did'}:
            continue
        bigram = f"{words[i]} {words[i + 1]}"
        bigram_key = bigram.lower()
        if not any(bigram_key == c.lower() for c, _ in results):
            # Both words are content words and form a meaningful pair
            confidence = 0.55
            if len(words[i]) >= 4 and len(words[i + 1]) >= 4:
                confidence += 0.10
            results.append((bigram, confidence))

    # Deduplicate keeping highest score
    seen: Dict[str, float] = {}
    for phrase, score in results:
        key = phrase.lower()
        if key not in seen or score > seen[key]:
            seen[key] = score

    sorted_results = [(p, s) for p, s in sorted(seen.items(), key=lambda x: -x[1])]
    return sorted_results


# ═════════════════════════════════════════════════════════════════════════════
# Strategy 6: Verb-Focused Topic Extraction (NEW)
# ═════════════════════════════════════════════════════════════════════════════

def extract_by_verb_pattern(query: str) -> List[Tuple[str, float]]:
    """Extract topic using verb-object patterns from imperative/action queries.

    Detects patterns like:
      - "how to make french fries" -> "french fries"
      - "how to bake a cake" -> "cake"
      - "tell me about photosynthesis" -> "photosynthesis"

    Uses light verb detection to identify object-as-topic relationships.

    Pure function — no I/O, no side effects.
    """
    results: List[Tuple[str, float]] = []
    if not query or not query.strip():
        return results

    q_lower = query.lower().strip()

    # Pattern: "how to <light_verb> <object>"
    # e.g., "how to make french fries", "how to bake a cake"
    for verb in ['make', 'bake', 'cook', 'create', 'build', 'write', 'draw',
                  'paint', 'play', 'use', 'find', 'fix', 'do']:
        m = re.search(
            r'how\s+(?:to|do|does|can|would)\s+' + re.escape(verb) +
            r'\s+(?:a|an|the|some|this|that)?\s*(.+)',
            q_lower
        )
        if m:
            obj = m.group(1).strip().rstrip('.!?')
            if obj and len(obj) > 1 and obj not in _EMPTY_TOPICS:
                results.append((obj, 0.78))
                break  # Take first match only

    # Pattern: "<light_verb> <object>" (imperative)
    # e.g., "make french fries", "bake a cake"
    if not results:
        for verb in ['make', 'bake', 'cook', 'create', 'build', 'write', 'draw',
                      'paint', 'play', 'use', 'find', 'fix', 'do']:
            m = re.match(
                r'^' + re.escape(verb) + r'\s+(?:a|an|the|some|this|that|me|us)?\s*(.+)',
                q_lower
            )
            if m:
                obj = m.group(1).strip().rstrip('.!?')
                if obj and len(obj) > 1 and obj not in _EMPTY_TOPICS:
                    results.append((obj, 0.72))
                    break

    # Pattern: "how <adj> is <object>" (measurement questions)
    # e.g., "how tall is the Eiffel Tower"
    if not results:
        m = re.search(r'how\s+(?:big|large|small|far|long|tall|deep|wide|heavy|fast|slow|high|low|old|hot|cold)\s+(?:is|are|was|were)\s+(.+)', q_lower)
        if m:
            obj = m.group(1).strip().rstrip('.!?')
            if obj and len(obj) > 1:
                results.append((obj, 0.80))

    # Pattern: "what is the <attr> of <object>" 
    # e.g., "what is the capital of France"
    if not results:
        m = re.search(r'what\s+is\s+the\s+\w+\s+of\s+(.+)', q_lower)
        if m:
            obj = m.group(1).strip().rstrip('.!?')
            if obj and len(obj) > 1:
                results.append((obj, 0.82))

    # Pattern: "<verb> <object> with/without..." extracts the object
    for verb in ['make', 'bake', 'cook', 'build', 'write', 'draw', 'create']:
        m = re.search(
            re.escape(verb) + r'\s+(?:a|an|the|some)?\s*(.+?)\s+(?:with|without|using|from|out\s+of|in|on)\s+',
            q_lower
        )
        if m:
            obj = m.group(1).strip()
            if obj and len(obj) > 1:
                results.append((obj, 0.70))
                break

    return results


# ═════════════════════════════════════════════════════════════════════════════
# Strategy 7: Cleaned Fallback
# ═════════════════════════════════════════════════════════════════════════════

def extract_cleaned_query(query: str) -> List[Tuple[str, float]]:
    """Extract the full cleaned query as a single low-confidence result.

    Pure function — no I/O, no side effects.
    """
    if not query or not query.strip():
        return []

    cleaned = clean_query(query)
    cleaned = remove_stop_words(cleaned, _QUESTION_STOP_WORDS)
    cleaned = cleaned.strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.strip(' ,;:.-')

    if cleaned and len(cleaned) > 2:
        word_count = len(cleaned.split())
        confidence = 0.30
        if word_count >= 3:
            confidence += 0.10
        if word_count >= 5:
            confidence += 0.05
        if word_count >= 7:
            confidence += 0.05
        return [(cleaned, confidence)]

    stripped = query.strip()
    if stripped:
        return [(stripped, 0.20)]
    return []


# ═════════════════════════════════════════════════════════════════════════════
# Merging & Scoring
# ═════════════════════════════════════════════════════════════════════════════

def _merge_results(
    *result_lists: List[Tuple[str, float]],
    max_results: int = 5,
) -> List[Tuple[str, float]]:
    """Merge multiple extraction strategy results, deduplicating and keeping top scores.

    Pure function — no I/O, no side effects.
    """
    merged: Dict[str, float] = {}

    for results in result_lists:
        for phrase, score in results:
            key = phrase.lower().strip()
            if not key or len(key) < 2:
                continue
            if key in _EMPTY_TOPICS:
                continue
            if key in merged:
                merged[key] = max(merged[key], score)
            else:
                merged[key] = score

    sorted_results = sorted(merged.items(), key=lambda x: (-x[1], x[0]))
    return sorted_results[:max_results]


# ═════════════════════════════════════════════════════════════════════════════
# Public API — Keyword Extraction
# ═════════════════════════════════════════════════════════════════════════════

def extract_keywords(query: str, max_keywords: int = 5) -> List[Tuple[str, float]]:
    """Extract search keywords from a query.

    Uses all available strategies and merges results by confidence score.
    Returns up to ``max_keywords`` (phrase, score) pairs, sorted by score descending.

    Pure function — no I/O, no side effects.

    Args:
        query: The user's query string.
        max_keywords: Maximum number of keywords to return.

    Returns:
        List of (keyword_phrase, confidence_score) tuples, sorted by confidence.
    """
    if not query or not query.strip():
        return []

    # Run all extraction strategies
    question_results = extract_by_question_pattern(query)
    np_results = extract_noun_phrases(query)
    entity_results = extract_entities(query)
    word_results = extract_content_words(query)
    compound_results = extract_compound_phrases(query)
    verb_results = extract_by_verb_pattern(query)
    fallback_results = extract_cleaned_query(query)

    merged = _merge_results(
        question_results,
        np_results,
        entity_results,
        word_results,
        compound_results,
        verb_results,
        fallback_results,
        max_results=max_keywords,
    )

    return merged


# ═════════════════════════════════════════════════════════════════════════════
# Public API — Topic Extraction
# ═════════════════════════════════════════════════════════════════════════════

def extract_topic(query: str) -> Tuple[Optional[str], float]:
    """Extract the single best topic from a query.

    Returns (topic_string, confidence) where the topic is the highest-confidence
    result across all extraction strategies.

    Pure function — no I/O, no side effects.

    Args:
        query: The user's query string.

    Returns:
        (topic, confidence) tuple. Topic is None if nothing meaningful could be extracted.
        Confidence is 0.0 to 1.0.
    """
    keywords = extract_keywords(query, max_keywords=1)
    if keywords:
        phrase, score = keywords[0]
        return phrase, score

    cleaned = clean_query(query)
    if cleaned:
        return cleaned, 0.15
    return None, 0.0


# ═════════════════════════════════════════════════════════════════════════════
# Public API — Convenience Wrappers
# ═════════════════════════════════════════════════════════════════════════════

def extract_noun_phrases_only(text: str) -> List[str]:
    """Extract noun phrases as plain strings (convenience wrapper).

    Pure function — no I/O, no side effects.
    """
    return [p for p, _ in extract_noun_phrases(text)]


def extract_entities_only(text: str) -> List[str]:
    """Extract named entities as plain strings (convenience wrapper).

    Pure function — no I/O, no side effects.
    """
    return [e for e, _ in extract_entities(text)]


# ═════════════════════════════════════════════════════════════════════════════
# Conversation Context Tracking
# ═════════════════════════════════════════════════════════════════════════════

# Follow-up signals that indicate context dependence
_FOLLOWUP_SIGNALS: List[str] = [
    'tell me more', 'tell me about that', 'tell me about it',
    'explain that', 'explain this', 'what about',
    'go on', 'continue', 'more about', 'expand on',
    'regarding that', 'about that', 'about this',
    'how about', 'what about it',
    'yeah but', 'yes but', 'ok but', 'well what about',
    'same thing', 'similar',
    'and then what', 'and then', 'what else', 'anything else',
    'what does that mean', 'how does that work',
    'can you elaborate', 'can you expand',
    'what were the', 'what colors', 'why is that', 'how does that',
    'how does it', 'what about that', 'tell me about that',
]

# Pronoun referents (words that primarily refer to prior context)
_PRONOUN_REFS: frozenset = frozenset({
    'it', 'that', 'this', 'them', 'those', 'these', 'they', 'he', 'she',
    'him', 'her', 'his', 'its', 'their',
})


def _is_pronoun_query(query: str) -> bool:
    """Check if a query primarily uses pronouns to refer to prior context.

    Detects patterns like:
      - "tell me more about that" (demonstrative pronoun reference)
      - "how do i make them" (personal pronoun reference)
      - "yeah but how do i make them" (affirmative + pronoun reference)
      - "explain that" / "what about it" / "tell me more"

    Uses algorithmic analysis of the query structure:
      1. Direct pronoun reference detection
      2. Follow-up signal matching
      3. Content-to-pronoun ratio analysis

    Pure function — no I/O, no side effects.
    """
    q = query.lower().strip()
    if not q:
        return False

    words = q.split()

    # Quick check: if the query IS or starts with a pronoun reference
    # "it", "that", "this", "them" as standalone queries
    if q in _PRONOUN_REFS:
        return True

    # Check follow-up signals (whole phrase matches)
    # But only if the query doesn't have enough specific content to stand alone
    # e.g., "how about the Eiffel Tower" has content, but "how about it" doesn't
    for signal in _FOLLOWUP_SIGNALS:
        if signal in q:
            # Check if there's specific content (not just pronouns/particles)
            q_after = q.replace(signal, '', 1).strip().lstrip(',;: ')
            after_words = q_after.split()
            # If the remaining query is just pronouns/punctuation, it IS context-dependent
            # Also treat question verbs (see, show, tell, etc.) as non-content words
            # since they're part of the question structure, not the topic
            non_content = _PRONOUN_REFS | _STOP_WORDS | {
                'yeah', 'yes', 'no', 'ok', 'okay', 'sure', 'well', 'so',
                'but', 'and', 'oh', 'ah', 'hmm', '?',
                'see', 'show', 'tell', 'explain', 'describe', 'find', 'give',
                'make', 'do', 'does', 'did', 'can', 'could', 'would', 'should',
                'will', 'may', 'might', 'shall',
            }
            is_vague = all(
                w.rstrip('.,;:!?') in non_content
                for w in after_words
            ) if after_words else True
            if is_vague:
                return True
            # If there's meaningful content, it's introducing a new topic — NOT context-dependent
            continue

    # Content-to-pronoun ratio analysis
    # Count content words vs pronoun references
    # Strip punctuation from words so "it?" is recognized as "it"
    _word_cleaner = lambda w: w.rstrip('.,;:!?()[]"\'')
    words_clean = [_word_cleaner(w) for w in words]

    content_words_in_query = [
        w for w in words_clean
        if w not in _STOP_WORDS
        and w not in _PRONOUN_REFS
        and w not in {'yeah', 'yes', 'no', 'ok', 'okay', 'sure', 'well', 'so', 'but', 'and', 'oh', 'ah', 'hmm'}
    ]

    has_pronoun_ref = any(w in _PRONOUN_REFS for w in words_clean)

    # If it has pronouns AND very little specific content, it's context-dependent
    if has_pronoun_ref and len(content_words_in_query) <= 1:
        return True

    # Referential pronouns ("it", "them", "they", "that", "this") are almost always
    # references to prior context, even in longer queries.
    # e.g., "What are some fun facts about it?" — "it" refers to France.
    # e.g., "How does that compare to other empires?" — "that" refers to the topic.
    referential_pronouns = {'it', 'them', 'they', 'that', 'this'}
    has_referential_pronoun = any(w in referential_pronouns for w in words_clean)
    if has_referential_pronoun:
        return True

    # Queries starting with "what about", "how about" with a pronoun
    # e.g., "what about it", "how about that"
    if re.match(r'^(?:what|how)\s+about\s+(?:it|that|this|them)\s*', q):
        return True

    # "yeah", "yes", "ok", "but", "so" followed by a pronoun-heavy clause
    if re.match(r'^(?:yeah|yes|ok|okay|sure|well|so|but|and)\s+,?\s*(?:how|what|why|where|when)\s+', q):
        # Check if the main reference is a pronoun
        main_part = re.sub(r'^(?:yeah|yes|ok|okay|sure|well|so|but|and)\s+,?\s*', '', q).strip()
        main_words = main_part.split()
        pronoun_ratio = sum(1 for w in main_words if w in _PRONOUN_REFS) / max(len(main_words), 1)
        if pronoun_ratio > 0.3:
            return True

    return False


def extract_context_topic(
    conversation_history: List[Tuple[str, Optional[str]]],
    max_lookback: int = 5,
    current_query: Optional[str] = None,
) -> Optional[str]:
    """Extract the current conversation topic from recent history.

    Uses a scoring algorithm with:
      - Temporal recency weighting (exponential decay)
      - Pronoun resolution (maps pronouns to most recent substantive topic)
      - Boosted weighting for context-dependent queries
      - Response-side topic integration
      - Filtering of pronoun-like empty topics

    Pure function — no I/O, no side effects.

    Args:
        conversation_history: List of (user_query, assistant_response) pairs.
            Responses may be None for unanswered queries.
        max_lookback: Number of recent exchanges to examine.
        current_query: The current user query (optional). Used for pronoun resolution.

    Returns:
        Topic string, or None if no clear topic can be determined.
    """
    if not conversation_history:
        return None

    is_context_dep = False
    if current_query:
        is_context_dep = _is_pronoun_query(current_query)

    # Score topics from recent exchanges
    topic_scores: Dict[str, float] = {}
    start = max(0, len(conversation_history) - max_lookback)

    # Find the most recent exchange with a substantive topic (for pronoun resolution)
    last_substantive_idx = -1
    if is_context_dep:
        for i in range(len(conversation_history) - 1, start - 1, -1):
            q, r = conversation_history[i]
            if q and not _is_pronoun_query(q):
                kws = extract_keywords(q, max_keywords=1)
                if kws and kws[0][1] > 0.5 and kws[0][0].lower() not in _EMPTY_TOPICS:
                    last_substantive_idx = i
                    break

    for i in range(start, len(conversation_history)):
        query, response = conversation_history[i]

        # Skip the current query — it's the one we're trying to resolve.
        # Its keywords (e.g., "see", "main factors") would pollute the topic
        # scores. We want to resolve from prior context, not from itself.
        if current_query and query == current_query:
            continue

        # Exponential recency weight: most recent exchanges count most
        distance_from_end = len(conversation_history) - 1 - i
        recency = 0.4 * (0.65 ** distance_from_end)

        # Extract from query (direct signal)
        if query:
            query_results = extract_keywords(query, max_keywords=3)
            for phrase, score in query_results:
                # When context-dependent, strongly boost the most recent
                # substantive topic (the pronoun's likely referent)
                if is_context_dep and i == last_substantive_idx:
                    boost = score * recency * 3.0
                else:
                    boost = score * recency * 1.2
                topic_scores[phrase.lower()] = topic_scores.get(phrase.lower(), 0) + boost

        # Extract from response (weaker signal, but still informative)
        if response:
            response_results = extract_keywords(response, max_keywords=2)
            for phrase, score in response_results:
                boost = score * recency * 0.6
                topic_scores[phrase.lower()] = topic_scores.get(phrase.lower(), 0) + boost

    if not topic_scores:
        return None

    # Filter out pronoun-like topics when context-dependent
    # Also always filter topics that contain pronoun words as standalone tokens
    # e.g., "that work" should be filtered because "that" is a pronoun
    def _contains_pronoun(topic: str) -> bool:
        words = topic.split()
        return any(w in _PRONOUN_REFS or w in _EMPTY_TOPICS for w in words)

    if is_context_dep:
        topic_scores = {k: v for k, v in topic_scores.items()
                       if k not in _PRONOUN_REFS
                       and k not in _EMPTY_TOPICS
                       and not _contains_pronoun(k)}
    else:
        # Even when not explicitly context-dependent, filter out topics
        # that contain pronouns (they're never good standalone topics)
        topic_scores = {k: v for k, v in topic_scores.items()
                       if not _contains_pronoun(k)}

    if not topic_scores:
        return None

    # Return the highest-scoring topic
    best = max(topic_scores, key=topic_scores.get)
    return best


# ═════════════════════════════════════════════════════════════════════════════
# Utility Functions
# ═════════════════════════════════════════════════════════════════════════════

def is_context_dependent(query: str) -> bool:
    """Check if a query primarily refers to prior conversation context.

    Pure function — no I/O, no side effects.

    Args:
        query: The user's query string.

    Returns:
        True if the query appears to depend on conversation context.
    """
    return _is_pronoun_query(query)


def is_empty_topic(topic: str) -> bool:
    """Check if a topic string is empty or a reflexive pronoun."""
    return not topic or topic.strip().lower() in _EMPTY_TOPICS


def normalize_topic(topic: str) -> str:
    """Normalize a topic string for consistent matching.

    Lowercases, strips, and collapses whitespace.
    """
    return collapse_whitespace(topic.lower())


def get_stop_words() -> frozenset:
    """Return the current stop word set (for inspection/testing)."""
    return _STOP_WORDS


def get_known_compounds() -> frozenset:
    """Return the known compound phrases (for inspection/testing)."""
    return _KNOWN_COMPOUNDS


def get_empty_topics() -> frozenset:
    """Return the empty topics set (for inspection/testing)."""
    return _EMPTY_TOPICS
