"""NLG Essay Generator — generates unique, content-rich essays from extracted facts.

Unlike template-only approaches, this system:
  1. Parses information into structured facts (using existing parser)
  2. Groups facts thematically into paragraphs (definition, location, properties, etc.)
  3. Generates varied topic sentences, supporting paragraphs, and conclusions
  4. Weaves actual fact content into prose — not just placeholder templates
  5. Produces different essays each time through structural randomization

Usage:
    essay = generate_essay("Photosynthesis", information, NLGConfig(style="friendly"))
"""

import re

from .config import DEFAULT_CONFIG, NLGConfig
from .fluency import enhance_fluency
from .models import Fact
from .parser import parse_facts
from .realize import realize_fact
from .util import lower_first, maybe, pick, require_style, split_sentences, upper_first


# ═════════════════════════════════════════════════════════════════════════════
# ESSAY STRUCTURE COMPONENTS
# ═════════════════════════════════════════════════════════════════════════════

# ── Introduction templates ─────────────────────────────────────────────────

_INTRODUCTIONS = {
    "friendly": [
        "Let's talk about {topic}. {topic_article} {fact_short}.",
        "So what's the deal with {topic}? Well, {topic_article} {fact_short}.",
        "I'm glad you asked about {topic}. Here's what you should know: {topic_article} {fact_short}.",
        "Ah, {topic}! That's a fascinating subject. {topic_article} {fact_short}.",
        "Great topic! So {topic} — {fact_short}.",
    ],
    "neutral": [
        "{topic} is a significant subject. {topic_article} {fact_short}.",
        "To understand {topic}, it helps to start with the basics. {topic_article} {fact_short}.",
        "{topic} refers to {fact_short}.",
        "When examining {topic}, one finds that {topic_article} {fact_short}.",
    ],
    "concise": [
        "{topic}: {fact_short}.",
    ],
}

# ── Paragraph topic sentence templates per fact type ───────────────────────

_TOPIC_SENTENCES = {
    "definition": {
        "friendly": [
            "So what exactly is {topic}? {topic_article} {verb} {obj}.",
            "At its core, {topic} {verb} {obj}.",
            "Here's the simplest way to think about it: {topic} {verb} {obj}.",
            "So {topic} is basically {obj}.",
        ],
        "neutral": [
            "{topic} {verb} {obj}.",
            "By definition, {topic} {verb} {obj}.",
        ],
    },
    "location": {
        "friendly": [
            "You can find {topic} {prep} {place}.",
            "Where is {topic}? {topic_article} located {prep} {place}.",
        ],
        "neutral": [
            "{topic} is located {prep} {place}.",
        ],
    },
    "property": {
        "friendly": [
            "One of the key things about {topic} is that it {verb} {obj}.",
            "What makes {topic} distinctive is that it {verb} {obj}.",
            "Here's something notable: {topic} {verb} {obj}.",
        ],
        "neutral": [
            "{topic} {verb} {obj}.",
            "A notable characteristic of {topic} is that it {verb} {obj}.",
        ],
    },
    "composition": {
        "friendly": [
            "So what's {topic} made of? {topic_article} {verb} {obj}.",
            "The composition of {topic} is {obj}.",
        ],
        "neutral": [
            "{topic} {verb} {obj}.",
            "{topic} consists of {obj}.",
        ],
    },
    "purpose": {
        "friendly": [
            "So what's {topic} used for? {topic_article} {verb} {obj}.",
            "People use {topic} primarily for {obj}.",
        ],
        "neutral": [
            "{topic} {verb} {obj}.",
        ],
    },
    "action": {
        "friendly": [
            "Here's what {topic} does: it {verb} {obj}.",
            "One of the main functions of {topic} is that it {verb} {obj}.",
        ],
        "neutral": [
            "{topic} {verb} {obj}.",
        ],
    },
    "comparison": {
        "friendly": [
            "Here's an interesting comparison: {topic} {verb} {obj}.",
            "What sets {topic} apart is that it {verb} {obj}.",
        ],
        "neutral": [
            "{topic} {verb} {obj}.",
        ],
    },
    "example": {
        "friendly": [
            "For instance, {obj}.",
        ],
        "neutral": [
            "For example, {obj}.",
        ],
    },
    "unknown": {
        "friendly": [
            "Here's something to know about {topic}: {obj}.",
        ],
        "neutral": [
            "{topic} {verb} {obj}.",
        ],
    },
}


def _is_plural_topic(topic: str) -> bool:
    """Check if a topic name refers to a plural noun.

    Pure function.
    """
    t = topic.lower().strip().rstrip('.,;:!?')
    if " and " in t or " & " in t:
        return True
    t_words = t.split()
    last_word = t_words[-1] if t_words else t
    _SINGULAR_NOUNS = {
        'this', 'thus', 'bus', 'gas', 'was', 'its', 'paris', 'mars', 'venus',
        'uranus', 'athens', 'brussels', 'dallas', 'texas', 'kansas', 'species',
        'series', 'apparatus', 'corpus', 'radius', 'basis', 'crisis', 'thesis',
        'analysis', 'oasis', 'alas', 'status', 'plus', 'minus',
        'linguistics', 'mathematics', 'physics', 'economics', 'statistics',
        'politics', 'ethics', 'aesthetics', 'logics', 'informatics',
        'news', 'mumps', 'measles', 'diabetes', 'rabies', 'tetanus',
    }
    return (last_word.endswith('s') and not last_word.endswith('ss')
            and last_word not in _SINGULAR_NOUNS)


def _get_topic_sentence(fact: Fact, config: NLGConfig) -> str:
    """Generate a topic sentence for a paragraph about this fact type."""
    style = require_style(config)
    templates = _TOPIC_SENTENCES.get(fact.fact_type, _TOPIC_SENTENCES["unknown"])
    style_templates = templates.get(style, templates.get("neutral", templates["friendly"]))
    template = pick(style_templates, config.temperature)

    topic = fact.subject
    obj_lower = lower_first(fact.obj)
    topic_article = _get_article(topic)

    # Detect if topic is plural for verb agreement
    is_plural = _is_plural_topic(topic)
    if is_plural:
        # Only replace "is" when it's the main copular verb, not in subordinate clauses
        # e.g., "So what exactly is {topic}?" → "So what exactly are {topic}?"
        # But NOT "One of the key things about {topic} is that..." (singular subject)
        template = re.sub(r'\bis\b(?=\s+\{topic\}|\s+what\b|\s+this\b)', 'are', template)
        template = template.replace("What's", "What are")
        topic_article = ""  # No article for plurals
        # Replace hardcoded "it" with "they" for plural topics
        # e.g., "One of the key things about Carrots are that it {verb}" → "...they {verb}"
        template = re.sub(r'\bit\b(?=\s+\{verb\})', 'they', template)

    # Fix predicate when obj starts with "been" (e.g., "include been found" → "have been found")
    verb = fact.predicate
    if verb.lower() == "include" and obj_lower.startswith("been"):
        verb = "have" if is_plural else "has"

    # For templates that use "{topic_article} {verb}" as a sentence fragment
    # (e.g., "So what exactly is {topic}? {topic_article} {verb} {obj}."),
    # we need an explicit subject. Replace "{topic_article} {verb}" with
    # "{topic} {verb}" so it becomes "{topic} verb obj" (e.g., "Carrots are ...").
    # This prevents fragments like "Are originally from..." when topic_article is empty.
    if is_plural:
        # Replace "{topic_article} {verb}" with "{topic} {verb}" so the subject is explicit
        template = template.replace("{topic_article} {verb}", "{topic} {verb}")
    else:
        # For singular, replace "{topic_article} {verb}" with "it {verb}"
        template = template.replace("{topic_article} {verb}", "it {verb}")

    # Handle location facts specially
    if fact.fact_type == "location":
        loc_match = re.match(
            r'(?:located|situated|found|based)?\s*(in|on|at|near)\s+(.+)',
            fact.obj, re.IGNORECASE
        )
        if not loc_match:
            loc_match = re.match(r'(in|on|at|near)\s+(.+)', fact.obj, re.IGNORECASE)
        if loc_match:
            place = loc_match.group(2)
            prep = loc_match.group(1)
        else:
            place = fact.obj
            prep = "in"
    else:
        place = fact.obj
        prep = "in"

    try:
        sentence = template.format(
            topic=topic,
            topic_article=topic_article,
            obj=_lower_article(obj_lower),
            verb=verb,
            place=place,
            prep=prep,
        )
    except (KeyError, ValueError):
        sentence = f"{topic} {verb} {fact.obj}."

    sentence = upper_first(sentence.strip())
    if not sentence.endswith(('.', '!', '?')):
        sentence += "."

    # Fix: lowercase topic after "So" prefix (e.g., "So Carrots" -> "So carrots")
    sentence = re.sub(r'\bSo\s+([A-Z][a-z])', lambda m: "So " + m.group(1).lower(), sentence)

    # Fix: lowercase topic mid-sentence after verbs like "are", "is"
    # (e.g., "So what exactly are Carrots?" -> "So what exactly are carrots?")
    # Only apply if topic is more than one word or doesn't start the sentence
    topic_lower = lower_first(topic)
    sentence = sentence.replace(f"are {topic}?", f"are {topic_lower}?")
    sentence = sentence.replace(f"are {topic}.", f"are {topic_lower}.")
    sentence = sentence.replace(f"is {topic}?", f"is {topic_lower}?")
    sentence = sentence.replace(f"is {topic}.", f"is {topic_lower}.")
    # Also lowercase topic in "One of the key things about {topic}" patterns
    sentence = sentence.replace(f"about {topic} ", f"about {topic_lower} ")

    return sentence


# ── Supporting sentence generation ─────────────────────────────────────────

_SUPPORTING_SENTENCES = {
    "friendly": [
        "To elaborate, {fact}",
        "More specifically, {fact}",
        "In fact, {fact}",
        "What's interesting is that {fact}",
        "It's worth noting that {fact}",
    ],
    "neutral": [
        "In addition, {fact}",
        "Furthermore, {fact}",
        "Additionally, {fact}",
    ],
    "concise": [
        "{fact}",
    ],
}


def _get_supporting_sentence(fact: Fact, config: NLGConfig, is_first: bool = False) -> str:
    """Generate a supporting sentence that incorporates fact content naturally."""
    style = require_style(config)
    templates = _SUPPORTING_SENTENCES.get(style, _SUPPORTING_SENTENCES["neutral"])

    # Build a natural sentence from the fact
    fact_sentence = realize_fact(fact, config, use_pronoun=True)
    fact_clean = fact_sentence[0].lower() + fact_sentence[1:] if fact_sentence else ""

    if is_first or not maybe(0.5 * config.temperature):
        return fact_sentence

    template = pick(templates, config.temperature)
    sentence = template.format(fact=fact_clean)
    sentence = upper_first(sentence.strip())
    if not sentence.endswith(('.', '!', '?')):
        sentence += "."
    return sentence


# ── Paragraph transitions ──────────────────────────────────────────────────

_PARAGRAPH_TRANSITIONS = {
    "friendly": [
        "Now, here's another key point: {topic}",
        "Moving on, let's talk about {topic}",
        "Another important aspect is {topic}",
        "Here's something else worth knowing: {topic}",
        "Beyond that, {topic}",
    ],
    "neutral": [
        "Moving on, {topic}",
        "Another key aspect of {topic} is that",
        "In addition, {topic}",
        "Furthermore, {topic}",
    ],
    "concise": [],
}


def _get_paragraph_transition(topic: str, prev_type: str, next_type: str, config: NLGConfig) -> str:
    """Generate a transition between paragraphs of different fact types."""
    style = require_style(config)
    if config.temperature <= 0.0 or config.verbosity < 0.3:
        return ""
    if not maybe(config.temperature):
        return ""
    templates = _PARAGRAPH_TRANSITIONS.get(style, _PARAGRAPH_TRANSITIONS["neutral"])
    if not templates:
        return ""
    template = pick(templates, config.temperature)
    try:
        return template.format(topic=topic)
    except (KeyError, ValueError):
        return ""


# ── Conclusion templates ───────────────────────────────────────────────────

_CONCLUSIONS = {
    "friendly": [
        "So that's the gist of {topic}. Fascinating stuff, right?",
        "And that's {topic} in a nutshell. Pretty interesting when you think about it.",
        "So there you have it — that covers the main things to know about {topic}.",
        "That's the key information about {topic}. Hope that gives you a clearer picture!",
    ],
    "neutral": [
        "In summary, {topic} is a subject with several important characteristics.",
        "To summarize, {topic} encompasses the features described above.",
        "These are the key points to understand about {topic}.",
    ],
    "concise": [
        "That covers the essentials of {topic}.",
    ],
}


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _get_article(noun: str) -> str:
    """Get the appropriate article ('a' or 'an') for a noun.

    Returns empty string for plurals and uncountable nouns.
    """
    if not noun:
        return ""
    n = noun.strip().rstrip('.,;:!?')
    n_lower = n.lower()

    # Common uncountable nouns
    if n_lower in {'photosynthesis', 'quantum computing', 'music', 'research',
                    'information', 'knowledge', 'nature', 'life', 'gravity',
                    'electricity', 'radiation', 'energy', 'weather', 'physics',
                    'mathematics', 'biology', 'chemistry', 'geometry'}:
        return ""

    # Check for plural: ends in 's' but not 'ss', excluding singular nouns ending in 's'
    _SINGULAR_NOUNS = {
        'this', 'thus', 'bus', 'gas', 'was', 'its', 'paris', 'mars', 'venus',
        'uranus', 'athens', 'brussels', 'dallas', 'texas', 'kansas', 'species',
        'series', 'apparatus', 'corpus', 'radius', 'basis', 'crisis', 'thesis',
        'analysis', 'oasis', 'alas', 'status', 'plus', 'minus',
        'linguistics', 'mathematics', 'physics', 'economics', 'statistics',
        'politics', 'ethics', 'aesthetics', 'logics', 'informatics',
        'news', 'mumps', 'measles', 'diabetes', 'rabies', 'tetanus',
    }
    if (n_lower.endswith('s') and not n_lower.endswith('ss')
            and n_lower not in _SINGULAR_NOUNS):
        return ""  # No article for plurals

    first = n[0].lower()
    if first in 'aeiou':
        return "an"
    return "a"


def _lower_article(text: str) -> str:
    """If text starts with an article, lowercase it for mid-sentence flow."""
    if text.startswith(('A ', 'An ')):
        return text[0].lower() + text[1:]
    return text


# ═════════════════════════════════════════════════════════════════════════════
# FACT GROUPING
# ═════════════════════════════════════════════════════════════════════════════

# Preferred order for paragraphs
_PARAGRAPH_TYPE_ORDER = [
    "definition",
    "location",
    "composition",
    "property",
    "purpose",
    "usage",
    "action",
    "comparison",
    "example",
    "unknown",
]


def _group_facts_by_type(facts: list[Fact]) -> list[tuple[str, list[Fact]]]:
    """Group facts by their type into paragraph groups.

    Preserves a natural flow: definition first, then specifics, then comparison.
    Within each group, facts are kept in their original order.
    """
    groups: dict[str, list] = {}
    for fact in facts:
        groups.setdefault(fact.fact_type, []).append(fact)

    # Order groups by preferred paragraph order
    ordered = []
    for ftype in _PARAGRAPH_TYPE_ORDER:
        if ftype in groups:
            ordered.append((ftype, groups[ftype]))
    # Add any remaining types not in the order list
    for ftype, group_facts in groups.items():
        if ftype not in _PARAGRAPH_TYPE_ORDER:
            ordered.append((ftype, group_facts))

    return ordered


# ═════════════════════════════════════════════════════════════════════════════
# MAIN ESSAY GENERATION FUNCTION
# ═════════════════════════════════════════════════════════════════════════════

def generate_essay(
    topic: str,
    information: str,
    config: "NLGConfig | None" = None,
) -> str:
    """Generate a unique, content-rich essay from retrieved information.

    Unlike template-only approaches, this function:
      - Parses the information into structured facts
      - Groups facts thematically into paragraphs
      - Generates unique topic sentences for each paragraph
      - Weaves actual fact content into flowing prose
      - Produces different essays each run through structural randomization

    Args:
        topic: The essay topic/subject.
        information: The retrieved information text to base the essay on.
        config: NLG configuration. Uses defaults if None.

    Returns:
        A multi-paragraph essay string.
    """
    if config is None:
        config = DEFAULT_CONFIG

    if not information or not information.strip():
        return _fallback_essay(topic, config)

    # Parse the information into structured facts
    facts = parse_facts(information, topic)
    if not facts:
        return _fallback_essay(topic, config)

    # Clean up incomplete fragments from Wikipedia parsing
    facts = _clean_fragments(facts)

    # Deduplicate facts to avoid repetition
    facts = _deduplicate_facts(facts)

    # Group facts by type for paragraph organization
    grouped = _group_facts_by_type(facts)

    if not grouped:
        return _fallback_essay(topic, config)

    paragraphs: list[str] = []

    # ── Introduction paragraph ──
    first_fact = facts[0]
    first_realized = realize_fact(first_fact, config, use_pronoun=False)
    intro_templates = _INTRODUCTIONS.get(require_style(config), _INTRODUCTIONS["neutral"])
    intro_template = pick(intro_templates, config.temperature)

    try:
        intro = intro_template.format(
            topic=topic,
            topic_article="",
            fact_short=upper_first(first_realized).rstrip('.!?'),
        )
        intro = re.sub(r'\s+', ' ', intro).strip()
    except (KeyError, ValueError):
        intro = f"Let's talk about {topic}. {first_realized}"
    paragraphs.append(upper_first(intro.strip()))

    # Track which facts have been used
    used_objects: set[str] = {first_fact.obj}

    # ── Body paragraphs ──
    # Split facts into small paragraphs of 3-5 sentences each
    # Target: 200-400 chars per paragraph for readable essays
    remaining_facts = [f for f in facts if f.obj not in used_objects]

    if remaining_facts:
        # Group into small chunks of max 4 facts, breaking if paragraph would exceed 400 chars
        MAX_PARA_FACTS = 4
        MAX_PARA_CHARS = 400
        fact_chunks = []
        current_chunk = []
        current_len = 0

        for fact in remaining_facts:
            fact_sent = realize_fact(fact, config, use_pronoun=len(current_chunk) > 0)
            fact_len = len(fact_sent) + 1  # +1 for space

            if (len(current_chunk) >= MAX_PARA_FACTS
                    or (current_len + fact_len > MAX_PARA_CHARS and current_chunk)):
                fact_chunks.append(current_chunk)
                current_chunk = [fact]
                current_len = fact_len
            else:
                current_chunk.append(fact)
                current_len += fact_len

        if current_chunk:
            fact_chunks.append(current_chunk)

        for i, chunk in enumerate(fact_chunks):
            para_sentences: list[str] = []
            lead_fact = chunk[0]
            used_objects.add(lead_fact.obj)

            if lead_fact.fact_type == "unknown" or not lead_fact.predicate:
                topic_sent = realize_fact(lead_fact, config, use_pronoun=(i > 0))
            else:
                topic_sent = _get_topic_sentence(lead_fact, config)
            para_sentences.append(topic_sent)

            for fact in chunk[1:]:
                used_objects.add(fact.obj)
                support = realize_fact(fact, config, use_pronoun=True)
                para_sentences.append(support)

            paragraph = " ".join(para_sentences)
            paragraphs.append(paragraph)

    # ── Conclusion paragraph ──
    conclusion_templates = _CONCLUSIONS.get(require_style(config), _CONCLUSIONS["neutral"])
    conclusion_template = pick(conclusion_templates, config.temperature)
    try:
        conclusion = conclusion_template.format(topic=topic)
    except (KeyError, ValueError):
        conclusion = f"So that covers the key points about {topic}."

    paragraphs.append(conclusion)

    # ── Assemble essay ──
    essay = "\n\n".join(paragraphs)

    # ── Fluency pass ──
    essay = enhance_fluency(essay, config, topic)

    # Ensure first paragraph is capitalized
    if essay and essay[0].isalpha() and essay[0].islower():
        essay = upper_first(essay)

    return essay


def _shorten(text: str, max_len: int = 60) -> str:
    """Shorten text to approximately max_len characters, breaking at word boundaries."""
    if len(text) <= max_len:
        return text
    # Try to break at a sentence boundary first
    sentences = split_sentences(text)
    if sentences and len(sentences[0]) <= max_len:
        return sentences[0]
    # Break at word boundary
    truncated = text[:max_len]
    last_space = truncated.rfind(' ')
    if last_space > 0:
        return truncated[:last_space] + "..."
    return truncated + "..."


def _clean_fragments(facts: list[Fact]) -> list[Fact]:
    """Remove incomplete sentence fragments from Wikipedia parsing.

    Filters out sentences that end mid-word, have unmatched parentheses,
    are too short to be meaningful facts, or look like parsing artifacts.
    """
    if not facts:
        return []

    from .parser import _is_fragment

    cleaned = []
    for fact in facts:
        obj = fact.obj.strip()
        orig = (fact.original or obj).strip()

        # Use the parser's fragment detection on both obj and original
        if _is_fragment(orig) or _is_fragment(obj):
            continue

        # Skip very short fragments (less than 15 chars)
        if len(obj) < 15 and fact.fact_type != "unknown":
            continue

        # Skip fragments ending with incomplete parenthetical
        if obj.endswith(('subsp.', 'var.', 'f.', 'spp.')):
            continue

        # Skip fragments with unmatched opening parenthesis
        if obj.count('(') > obj.count(')'):
            continue

        # Skip fragments that look like truncated words (ending with lowercase letter
        # followed by period, suggesting the sentence was cut off)
        if re.search(r'[a-z]\.$', obj) and not obj.endswith(('etc.', 'e.g.', 'i.e.')):
            continue

        # Skip fragments that end mid-word (no punctuation at all, ends lowercase)
        if obj and re.search(r'[a-z]$', obj) and not any(obj.endswith(w) for w in (
            'etc', 'e.g', 'i.e', 'ie', 'eg', 'vs', 'al', 'approx',
        )):
            # Skip incomplete-looking fragments regardless of length
            # A complete sentence should end with punctuation or look complete
            if len(obj) < 120:
                continue
            # For longer objects, check if the last word looks complete
            # by verifying it's a word we'd expect at end of sentence
            last_word = re.findall(r'\b(\w+)$', obj)
            if last_word:
                lw = last_word[0].lower()
                # Very short last words or words ending in common truncation
                # signals are likely truncated
                if len(lw) <= 3:
                    continue

        # Skip fragments ending with incomplete quoted string
        if obj.count('"') % 2 != 0 or obj.count("'") % 2 != 0:
            continue

        # Skip facts where subject is "The word" or similar generic reference
        # (these come from etymology sentences like "The word is first recorded...")
        subject_lower = fact.subject.lower().strip()
        if subject_lower in ('the word', 'word', 'the name', 'name', 'the term', 'term'):
            # Convert to unknown type so it passes through as-is
            fact = Fact(
                subject=fact.subject,
                predicate="",
                obj=fact.original or obj,
                fact_type="unknown",
                original=fact.original,
                certainty=fact.certainty,
                tense=fact.tense,
                is_negated=fact.is_negated,
            )

        cleaned.append(fact)

    return cleaned if cleaned else facts


def _deduplicate_facts(facts: list[Fact]) -> list[Fact]:
    """Remove duplicate or near-duplicate facts.

    Uses a combination of exact object matching, word overlap,
    and substring detection to catch semantically similar facts
    that convey the same information.
    """
    if not facts:
        return []

    seen_objects = set()
    seen_words = set()
    seen_originals = set()
    deduplicated = []

    for fact in facts:
        # Normalize the object for comparison
        obj_key = fact.obj.lower().strip().rstrip('.,;:!?')
        orig_key = (fact.original or obj_key).lower().strip().rstrip('.,;:!?')

        # Check for exact duplicate object
        if obj_key in seen_objects:
            continue

        # Check for exact duplicate original
        if orig_key in seen_originals:
            continue

        # Check if this object is a substring of a previously seen object
        # (e.g., "is a bird" is a substring of "is a bird that can fly")
        if any(obj_key in s or s in obj_key for s in seen_objects if len(s) > 10):
            continue

        # Remove articles and common words for fuzzy matching
        obj_words = {w for w in re.findall(r'\w{3,}', obj_key)
                     if w not in {'the', 'and', 'are', 'for', 'with', 'from',
                                  'this', 'that', 'which', 'into', 'over', 'also',
                                  'has', 'have', 'been', 'can', 'may', 'will'}}

        # Check for high word overlap (>70% shared words = likely duplicate)
        if obj_words and seen_words:
            overlap = len(obj_words & seen_words) / max(len(obj_words), 1)
            if overlap > 0.7:
                continue

        seen_objects.add(obj_key)
        seen_originals.add(orig_key)
        seen_words.update(obj_words)
        deduplicated.append(fact)

    return deduplicated


def _fallback_essay(topic: str, config: NLGConfig) -> str:
    """Generate a fallback essay when no information is available."""
    from .fallback import fallback_response
    return fallback_response(f"Tell me about {topic}", config)


# ═════════════════════════════════════════════════════════════════════════════
# SELF-TEST
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    info = (
        "Photosynthesis is the process plants use to convert sunlight into energy. "
        "Plants use chlorophyll to capture light energy. "
        "The process produces oxygen as a byproduct. "
        "Photosynthesis is essential for life on Earth. "
        "It takes place in the chloroplasts of plant cells. "
        "There are two stages: light-dependent reactions and the Calvin cycle."
    )

    for style in ["friendly", "neutral", "concise"]:
        cfg = NLGConfig(style=style, verbosity=0.6, temperature=0.7)
        print(f"\n{'='*60}")
        print(f"  STYLE: {style.upper()}")
        print(f"{'='*60}")
        print(generate_essay("photosynthesis", info, cfg))
