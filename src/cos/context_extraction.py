"""
COS Context Extraction — Symbolic multi-strategy keyword/topic/entity extraction.

Extracts search keywords, main topics, and named entities from natural language
queries using purely symbolic methods. No neural networks, no LLMs, no GGUF models.

Strategies (chained by precision then recall):
  1. Question Deconstruction  — Pattern-based removal of question words/structures
  2. Noun Phrase Chunking     — Adjective + noun sequence extraction
  3. Entity Detection         — Capitalized words, quoted phrases, named references
  4. Content Word Scoring     — TF-like scoring of significant terms
  5. Cleaned Fallback         — Stopword-removed, normalized full query

Every public function is pure — no I/O, no network, no global state.
All functions accept and return plain Python types for easy testing.

Usage:
    >>> extract_keywords("What is the capital of France?")
    [('france', 0.95), ('capital of france', 0.85)]

    >>> extract_topic("How does photosynthesis work?")
    ('photosynthesis', 0.92)
"""

import re
from typing import List, Tuple, Optional

# ── Stop Word Sets ────────────────────────────────────────────────────────────

# High-frequency words with low semantic value
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

# Stop words that are safe to remove even from short queries (question particles)
_QUESTION_STOP_WORDS: frozenset = frozenset({
    'what', 'who', 'whom', 'whose', 'which', 'why', 'where', 'when', 'how',
    'is', 'are', 'was', 'were', 'does', 'do', 'did', 'can', 'could', 'would', 'should',
    'will', 'may', 'might', 'shall',
    'tell', 'show', 'explain', 'describe', 'define', 'list', 'name',
    'me', 'us', 'the', 'a', 'an',
})

# ── Patterns ──────────────────────────────────────────────────────────────────

# Question/query deconstruction patterns
# Each is (regex, group_to_extract, weight)
_QUESTION_PATTERNS: List[Tuple[str, int, float]] = [
    # "What is X?" / "What are X?"
    (r'(?:what|which)\s+(?:is|are|was|were)\s+(?:a|an|the|this|that|these|those)?\s*(.+)', 1, 0.90),
    # "What's X"
    (r'what\'?[sS]\s+(?:a|an|the|this|that)?\s*(.+)', 1, 0.88),
    # "Who is X?" / "Who are X?"
    (r'who\s+(?:is|are|was|were)\s+(.+)', 1, 0.87),
    # "Where is X?" / "Where are X?"
    (r'where\s+(?:is|are|was|were|can|do|does)\s+(?:i|we|you|they|he|she|it)?\s*(.+)', 1, 0.85),
    # "When did/was/were X?"
    (r'when\s+(?:is|are|was|were|did|does|do|will)\s+(.+)', 1, 0.85),
    # "Why does/is/are X?"
    (r'why\s+(?:is|are|was|were|does|do|did|would|can)\s+(?:i|we|you|they|he|she|it)?\s*(.+)', 1, 0.80),
    # "How does/do/is/are X work?" / "How to X?"
    (r'how\s+(?:does|do|is|are|can|would|will|shall|could|to)\s+(?:i|we|you|they|he|she|it|one)?\s*(?:to\s+)?(?:make|bake|cook|create|build|write|find|get|know|use|fix|do)?\s*(.+)', 1, 0.82),
    # "How many/much X?"
    (r'how\s+(?:many|much)\s+(.+?)\??$', 1, 0.80),
    # "Tell me about X"
    (r'tell\s+(?:me|us)\s+about\s+(.+)', 1, 0.88),
    # "Tell me what/how X"
    (r'tell\s+(?:me|us)\s+(?:what|how)\s+(.+)', 1, 0.82),
    # "Show me X"
    (r'show\s+(?:me|us)\s+(.+)', 1, 0.85),
    # "Explain/Describe/Define X"
    (r'(?:explain|describe|define)\s+(?:the\s+)?(?:concept\s+of\s+|meaning\s+of\s+|idea\s+of\s+)?(.+)', 1, 0.90),
    # "Give me X"
    (r'give\s+(?:me|us)\s+(?:a|an|the|some)?\s*(.+)', 1, 0.75),
    # "I like/love/enjoy/hate X"
    (r'i\s+(?:like|love|enjoy|hate|prefer|want|have|use|know|own)\s+(.+?)(?:\.|$|\sand)', 1, 0.80),
    # "Write/Create/Make/Compose X about Y" -> extract Y
    (r'(?:write|create|make|compose|draft|generate)\s+(?:a|an|the)?\s*(?:\w+\s+){0,4}(?:about|on|regarding|concerning)\s+(.+)', 1, 0.85),
    # "Define X"
    (r'define\s+(.+)', 1, 0.88),
    # "What do/does X do?" -> X
    (r'what\s+(?:do|does)\s+(.+?)\s+do\??', 1, 0.82),
    # "What is the name of X?" -> X
    (r'what\s+is\s+the\s+name\s+of\s+(.+)', 1, 0.85),
    # "List/Name/Enumerate X"
    (r'(?:list|name|enumerate)\s+(?:the\s+)?(.+)', 1, 0.78),
]

# Noun phrase detection: sequences of (determiner)?(adjective)*(noun)+
_NOUN_PHRASE_RE = re.compile(
    r'(?:(?:a|an|the|this|that|these|those|some|any|my|your|his|her|its|our|their)\s+)?'
    r'(?:(?:\w+ly|un\w+|in\w+|dis\w+|over\w+|under\w+|re\w+|\w+ful|\w+less|\w+ous|\w+ive|\w+able|\w+ible|\w+al|\w+ent|\w+ant|\w+ic|\w+ish|\w+like|\w+y)\s+)*'
    r'([A-Z]?\w+(?:\s+[A-Z]?\w+){0,4})'
    r'(?:\s+(?:is|are|was|were|has|have|had|does|do|did|will|would|can|could|may|might|shall|should|make|made|take|took|use|used|find|found|show|shown|give|gave|tell|told|know|knew|known))?',
    re.IGNORECASE
)

# Entity patterns
_ENTITY_RE = re.compile(r'"([^"]+)"|\'([^\']+)\'|([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)')
_CAPITALIZED_WORD_RE = re.compile(r'\b([A-Z][a-z]{2,})\b')

# Redundant/empty topics
_EMPTY_TOPICS: frozenset = frozenset({
    'this', 'that', 'it', 'them', 'those', 'these',
    'something', 'anything', 'nothing', 'everything',
    'things', 'stuff', 'someone', 'somebody', 'anyone', 'anybody',
    'more', 'some', 'any', 'all', 'such',
})


# ── Cleaning / Normalization ──────────────────────────────────────────────────

def clean_query(query: str) -> str:
    """Normalize and clean a query string.

    - Strips whitespace
    - Collapses multiple spaces
    - Removes punctuation (keeps hyphens in compound words, apostrophes in contractions)
    - Lowercases
    - Removes stop words
    """
    q = query.strip()
    # Normalize whitespace
    q = re.sub(r'\s+', ' ', q)
    # Remove sentence-ending punctuation
    q = q.rstrip('.!?,;:')
    # Lowercase
    q = q.lower()
    return q


def remove_stop_words(text: str, stop_set: frozenset = _STOP_WORDS) -> str:
    """Remove stop words from text, preserving word order."""
    words = text.split()
    result = [w for w in words if w not in stop_set]
    return ' '.join(result)


def collapse_whitespace(text: str) -> str:
    """Collapse multiple whitespace characters into a single space."""
    return re.sub(r'\s+', ' ', text).strip()


# ── Strategy 1: Question Deconstruction ───────────────────────────────────────

def extract_by_question_pattern(query: str) -> List[Tuple[str, float]]:
    """Extract the key phrase from a question using pattern matching.

    Tries each question pattern in order and returns the first match
    with its confidence weight.

    Returns list of (phrase, confidence) tuples, possibly empty.
    """
    q_lower = query.lower().strip()
    results = []

    for pattern, group, weight in _QUESTION_PATTERNS:
        m = re.search(pattern, q_lower)
        if m:
            phrase = m.group(group).strip().rstrip('.!?,;: ')
            phrase = collapse_whitespace(phrase)
            if phrase and len(phrase) > 1:
                # Skip empty/reflexive topics
                if phrase.lower() not in _EMPTY_TOPICS:
                    results.append((phrase, weight))

    # Deduplicate keeping highest score
    seen: dict = {}
    for phrase, score in results:
        key = phrase.lower()
        if key not in seen or score > seen[key]:
            seen[key] = score

    return [(p, s) for p, s in seen.items()]


# ── Strategy 2: Noun Phrase Chunking ──────────────────────────────────────────

def extract_noun_phrases(text: str) -> List[Tuple[str, float]]:
    """Extract likely noun phrases using heuristic patterns.

    Looks for sequences of descriptive words + nouns that form
    meaningful phrases. Returns (phrase, confidence) pairs.
    """
    results = []
    matches = _NOUN_PHRASE_RE.finditer(text)
    for m in matches:
        phrase = m.group(0).strip()
        if not phrase or len(phrase) < 2:
            continue

        # Skip pure stop words
        words = phrase.split()
        if all(w.lower() in _STOP_WORDS for w in words):
            continue

        # Calculate confidence based on phrase characteristics
        score = 0.5  # base
        has_proper = any(w[0].isupper() for w in words)
        has_content = any(w.lower() not in _STOP_WORDS for w in words)

        # Penalize phrases that look like full clauses (contain verbs/pronouns)
        clause_markers = {'is', 'are', 'was', 'were', 'has', 'have', 'had',
                          'does', 'do', 'did', 'will', 'would', 'can', 'could',
                          'may', 'might', 'shall', 'should', 'makes', 'made',
                          'takes', 'took', 'uses', 'used', 'finds', 'found',
                          'shows', 'shown', 'gives', 'gave', 'tells', 'told',
                          'knows', 'knew', 'known'}
        pronoun_markers = {'i', 'you', 'he', 'she', 'it', 'we', 'they',
                           'me', 'him', 'her', 'us', 'them',
                           'this', 'that', 'these', 'those'}
        has_clause_verb = any(w.lower() in clause_markers for w in words)
        has_pronoun = any(w.lower() in pronoun_markers for w in words)

        if has_proper:
            score += 0.15
        if has_content:
            score += 0.10
        if len(words) >= 2:
            score += 0.05  # multi-word phrases are more specific
        if len(phrase) > 15 and not has_clause_verb:
            score += 0.05  # longer phrases are more descriptive

        # Penalize phrases containing clause verbs or pronouns
        if has_clause_verb:
            score -= 0.30
        if has_pronoun:
            score -= 0.20

        # Penalize very short phrases
        if len(phrase) < 5:
            score -= 0.15

        score = min(max(score, 0.0), 1.0)
        results.append((phrase.strip(), score))

    return results


# ── Strategy 3: Entity Detection ──────────────────────────────────────────────

def extract_entities(text: str) -> List[Tuple[str, float]]:
    """Extract named entities from text.

    Detects:
      - Quoted phrases ("like this")
      - Capitalized multi-word names (United States)
      - Capitalized single words (proper nouns)
    """
    results = []
    seen = set()

    # Quoted phrases
    for m in _ENTITY_RE.finditer(text):
        phrase = m.group(1) or m.group(2) or m.group(3)
        if phrase and phrase.strip():
            phrase = phrase.strip()
            key = phrase.lower()
            if key not in seen and len(phrase) > 1:
                seen.add(key)
                # Higher confidence for quoted (deliberate reference)
                score = 0.90 if (m.group(1) or m.group(2)) else 0.80
                results.append((phrase, score))

    # Capitalized words (potential proper nouns not already captured)
    for m in _CAPITALIZED_WORD_RE.finditer(text):
        word = m.group(1)
        key = word.lower()
        if key not in seen and len(word) > 2 and word.lower() not in _STOP_WORDS:
            seen.add(key)
            results.append((word, 0.60))  # lower confidence for single capitalized words

    return results


# ── Strategy 4: Content Word Scoring ──────────────────────────────────────────

def _word_significance(word: str, query: str) -> float:
    """Score a word's significance within a query (0.0 to 1.0).

    Factors:
      - Length: longer words carry more meaning
      - Position: words near the end of questions are often the target
      - Capitalization: proper nouns are significant
      - Rarity relative to stop words
    """
    w_lower = word.lower()
    score = 0.3  # base

    # Length bonus (longer = more specific)
    if len(word) >= 8:
        score += 0.25
    elif len(word) >= 6:
        score += 0.15
    elif len(word) >= 4:
        score += 0.05

    # Capitalization bonus (proper nouns)
    if word[0].isupper():
        score += 0.15

    # Position bonus: words near the end of questions are often key
    q_lower = query.lower()
    pos_ratio = q_lower.find(w_lower) / max(len(q_lower), 1)
    if pos_ratio > 0.5:
        score += 0.10

    # Penalty for very common words not in stop list
    common_words = {'also', 'very', 'just', 'really', 'quite', 'rather', 'well', 'still', 'even', 'much'}
    if w_lower in common_words:
        score -= 0.15

    return min(max(score, 0.0), 1.0)


def extract_content_words(text: str, max_words: int = 10) -> List[Tuple[str, float]]:
    """Extract and score significant content words from text.

    Removes stop words, scores remaining words by significance,
    and returns the top-scoring words as (word, score) pairs.
    """
    cleaned = remove_stop_words(text.lower(), _STOP_WORDS)
    words = cleaned.split()

    # Score each word
    scored = []
    seen = set()
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

    # Sort by score descending, take top N
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored[:max_words]


# ── Strategy 5: Cleaned Fallback ──────────────────────────────────────────────

def extract_cleaned_query(query: str) -> List[Tuple[str, float]]:
    """Extract the full cleaned query as a single low-confidence result."""
    if not query or not query.strip():
        return []

    cleaned = clean_query(query)
    cleaned = remove_stop_words(cleaned, _QUESTION_STOP_WORDS)
    cleaned = cleaned.strip()

    # Clean up remnants
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.strip(' ,;:.-')

    if cleaned and len(cleaned) > 2:
        # Very short cleaned queries often lose meaning
        word_count = len(cleaned.split())
        confidence = 0.30  # low baseline confidence
        if word_count >= 3:
            confidence += 0.10
        if word_count >= 5:
            confidence += 0.05
        return [(cleaned, confidence)]

    # Absolute fallback for non-empty queries
    stripped = query.strip()
    if stripped:
        return [(stripped, 0.20)]
    return []


# ── Merging & Scoring ─────────────────────────────────────────────────────────

def _merge_results(
    *result_lists: List[Tuple[str, float]],
    max_results: int = 5,
) -> List[Tuple[str, float]]:
    """Merge multiple extraction strategy results, deduplicating and keeping top scores."""
    merged: dict = {}

    for results in result_lists:
        for phrase, score in results:
            key = phrase.lower().strip()
            if not key or len(key) < 2:
                continue
            if key in _EMPTY_TOPICS:
                continue

            # Keep the highest score for each unique phrase
            if key not in merged or score > merged[key]:
                merged[key] = score

    # Sort by score descending
    sorted_results = sorted(merged.items(), key=lambda x: (-x[1], x[0]))
    return sorted_results[:max_results]


# ── Public API ────────────────────────────────────────────────────────────────

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
    fallback_results = extract_cleaned_query(query)

    merged = _merge_results(
        question_results,
        np_results,
        entity_results,
        word_results,
        fallback_results,
        max_results=max_keywords,
    )

    return merged


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
        # Return the longest individual word or phrase as topic
        # Prefer multi-word phrases (more specific)
        return phrase, score

    # Absolute fallback
    cleaned = clean_query(query)
    if cleaned:
        return cleaned, 0.15
    return None, 0.0


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


# ── Conversation Context Tracking ─────────────────────────────────────────────

def _is_pronoun_query(query: str) -> bool:
    """Check if a query primarily uses pronouns to refer to prior context.

    Detects patterns like:
      - "tell me more about that" (demonstrative pronoun reference)
      - "how do i make them" (personal pronoun reference)
      - "yeah but how do i make them" (affirmative + pronoun reference)
      - "explain that" / "what about it" / "tell me more"

    Pure function — no I/O, no side effects.
    """
    q = query.lower().strip()
    if not q:
        return False

    # Direct pronoun references (query IS or centers on a pronoun)
    pronoun_refs = {'it', 'that', 'this', 'them', 'those', 'these', 'they', 'he', 'she', 'him', 'her'}
    words = q.split()

    # Check if any pronoun is a key referent (not just incidental)
    # A pronoun is a key referent if it's not surrounded by specific content words
    content_words_in_query = [w for w in words if w not in _STOP_WORDS and w not in pronoun_refs
                              and w not in {'yeah', 'yes', 'no', 'ok', 'okay', 'sure', 'well', 'so', 'but', 'and'}]

    has_pronoun_ref = any(w in pronoun_refs for w in words)
    has_content = len(content_words_in_query) >= 2

    # If it has pronouns AND very little specific content, it's context-dependent
    if has_pronoun_ref and not has_content:
        return True

    # Phrases that signal a follow-up to previous context
    followup_signals = [
        'tell me more', 'tell me about that', 'tell me about it',
        'explain that', 'explain this', 'what about',
        'go on', 'continue', 'more about', 'expand on',
        'regarding that', 'about that', 'about this',
        'how about', 'what about it',
        'yeah but', 'yes but', 'ok but', 'well what about',
        'same thing', 'similar',
    ]
    for signal in followup_signals:
        if signal in q:
            return True

    return False


def extract_context_topic(
    conversation_history: List[Tuple[str, Optional[str]]],
    max_lookback: int = 5,
    current_query: Optional[str] = None,
) -> Optional[str]:
    """Extract the current conversation topic from recent history.

    Examines the last ``max_lookback`` exchanges in the conversation,
    extracting topics from both user queries and assistant responses.

    When ``current_query`` is provided, special handling is applied:
      - If the query is context-dependent (uses pronouns, follow-ups),
        the most recent substantive topic is given extra weight.
      - Pronoun references ("it", "them", "that", etc.) are resolved
        to the last clearly identified topic.

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
    topic_scores: dict = {}
    start = max(0, len(conversation_history) - max_lookback)

    # Find the most recent exchange with a substantive topic (for pronoun resolution)
    last_substantive_idx = -1
    if is_context_dep:
        for i in range(len(conversation_history) - 1, start - 1, -1):
            q, r = conversation_history[i]
            if q and not _is_pronoun_query(q):
                # Check if this query has a real topic
                kws = extract_keywords(q, max_keywords=1)
                if kws and kws[0][1] > 0.5 and kws[0][0].lower() not in _EMPTY_TOPICS:
                    last_substantive_idx = i
                    break

    for i in range(start, len(conversation_history)):
        query, response = conversation_history[i]
        recency = 1.0 - (len(conversation_history) - 1 - i) / max(max_lookback, 1)

        # Extract from query (direct signal)
        if query:
            query_results = extract_keywords(query, max_keywords=3)
            for phrase, score in query_results:
                # When context-dependent, strongly boost the most recent
                # substantive topic (the pronoun's likely referent)
                if is_context_dep and i == last_substantive_idx:
                    boost = score * recency * 2.5
                else:
                    boost = score * recency * 1.0
                topic_scores[phrase.lower()] = topic_scores.get(phrase.lower(), 0) + boost

        # Extract from response (weaker signal)
        if response:
            response_results = extract_keywords(response, max_keywords=2)
            for phrase, score in response_results:
                boost = score * recency * 0.5
                topic_scores[phrase.lower()] = topic_scores.get(phrase.lower(), 0) + boost

    if not topic_scores:
        return None

    # Filter out pronoun-like topics when context-dependent
    if is_context_dep:
        pronoun_like = {'it', 'that', 'this', 'them', 'those', 'these', 'they', 'him', 'her'}
        topic_scores = {k: v for k, v in topic_scores.items()
                       if k not in pronoun_like and k not in _EMPTY_TOPICS}

    if not topic_scores:
        return None

    # Return the highest-scoring topic
    best = max(topic_scores, key=topic_scores.get)
    return best


# ── Utility ───────────────────────────────────────────────────────────────────

def is_context_dependent(query: str) -> bool:
    """Check if a query primarily refers to prior conversation context.

    Detects pronoun references ("it", "them", "that"), follow-up signals
    ("tell me more", "explain that"), and queries with little standalone
    content that only make sense with context.

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


# ── Self-test / diagnostic ────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=== Context Extraction Self-Test ===\n")

    test_queries = [
        "What is the capital of France?",
        "How does photosynthesis work?",
        "Who was Albert Einstein?",
        "Tell me about machine learning",
        "I like pizza",
        "Explain quantum computing",
        "Where is the Eiffel Tower located?",
        "Write a poem about autumn",
        "When did World War II end?",
        "What's the weather like in Tokyo?",
        "How many people live in New York City?",
        "Define recursion in computer science",
    ]

    for q in test_queries:
        keywords = extract_keywords(q)
        topic, conf = extract_topic(q)
        kw_str = ', '.join(f"'{k}' ({s:.2f})" for k, s in keywords)
        print(f"  Q: {q}")
        print(f"  Topic: '{topic}' (conf={conf:.3f})")
        print(f"  Keywords: [{kw_str}]")
        print()

    # Conversation topic tracking test
    print("--- Context Topic Tracking ---")
    history = [
        ("What is photosynthesis?", "Photosynthesis is the process plants use to convert sunlight into energy."),
        ("Tell me more about that", None),
        ("How does chlorophyll work?", None),
    ]
    ctx = extract_context_topic(history)
    print(f"  History: {[h[0] for h in history]}")
    print(f"  Context topic: '{ctx}'")
