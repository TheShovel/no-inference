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
from typing import List, Optional, Tuple
from .models import Fact, DiscourseState
from .config import NLGConfig, DEFAULT_CONFIG
from .parser import parse_facts, extract_entities
from .realize import realize_fact, classify_query
from .fluency import enhance_fluency
from .util import pick, maybe, split_sentences, lower_first, upper_first, require_style


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


def _get_topic_sentence(fact: Fact, config: NLGConfig) -> str:
    """Generate a topic sentence for a paragraph about this fact type."""
    style = require_style(config)
    templates = _TOPIC_SENTENCES.get(fact.fact_type, _TOPIC_SENTENCES["unknown"])
    style_templates = templates.get(style, templates.get("neutral", templates["friendly"]))
    template = pick(style_templates, config.temperature)

    topic = fact.subject
    obj_lower = lower_first(fact.obj)
    topic_article = _get_article(topic)

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
            verb=fact.predicate,
            place=place,
            prep=prep,
        )
    except (KeyError, ValueError):
        sentence = f"{topic} {fact.predicate} {fact.obj}."

    sentence = upper_first(sentence.strip())
    if not sentence.endswith(('.', '!', '?')):
        sentence += "."
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
    """Get the appropriate article ('a' or 'an') for a noun."""
    if not noun:
        return ""
    n = noun.strip()
    # Check for uncountable/plural
    if n.lower().endswith('s') and not n.lower().endswith('ss'):
        return ""  # No article for plurals
    if n.lower() in {'photosynthesis', 'quantum computing', 'music', 'research',
                      'information', 'knowledge', 'nature', 'life', 'gravity',
                      'electricity', 'radiation', 'energy', 'weather'}:
        return ""
    first = n[0].lower()
    if first in 'aeiou':
        return "an"
    return "a"


def _lower_article(text: str) -> str:
    """If text starts with an article, lowercase it for mid-sentence flow."""
    if text.startswith('A ') or text.startswith('An '):
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


def _group_facts_by_type(facts: List[Fact]) -> List[Tuple[str, List[Fact]]]:
    """Group facts by their type into paragraph groups.

    Preserves a natural flow: definition first, then specifics, then comparison.
    Within each group, facts are kept in their original order.
    """
    groups: dict = {}
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
    config: Optional[NLGConfig] = None,
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

    # Group facts by type for paragraph organization
    grouped = _group_facts_by_type(facts)

    if not grouped:
        return _fallback_essay(topic, config)

    paragraphs: List[str] = []

    # ── Introduction paragraph ──
    first_fact = facts[0]
    # Use the properly realized first fact (includes subject + predicate + object)
    first_realized = realize_fact(first_fact, config, use_pronoun=False)
    intro_templates = _INTRODUCTIONS.get(require_style(config), _INTRODUCTIONS["neutral"])
    intro_template = pick(intro_templates, config.temperature)

    try:
        intro = intro_template.format(
            topic=topic,
            topic_article=upper_first(topic),
            fact_short=lower_first(first_realized),
        )
    except (KeyError, ValueError):
        intro = f"Let's talk about {topic}. {first_realized}"
    paragraphs.append(upper_first(intro.strip()))

    # Track which facts have been used (to avoid repetition)
    used_objects: set = {first_fact.obj}  # first fact's object used in intro

    # ── Body paragraphs (one per fact type group) ──
    prev_type = None
    for i, (ftype, group_facts) in enumerate(grouped):
        # Skip facts already used (by object content)
        fresh_facts = [f for f in group_facts if f.obj not in used_objects]
        if not fresh_facts:
            continue

        # Build a paragraph from this group
        para_sentences: List[str] = []

        # Topic sentence (first unused fact in the group)
        lead_fact = fresh_facts[0]
        used_objects.add(lead_fact.obj)
        topic_sent = _get_topic_sentence(lead_fact, config)
        para_sentences.append(topic_sent)

        # Supporting sentences (remaining unused facts in the group)
        for fact in fresh_facts[1:]:
            used_objects.add(fact.obj)
            support = _get_supporting_sentence(fact, config, is_first=False)
            para_sentences.append(support)

        # Add paragraph transition if not the first paragraph
        transition = ""
        if i > 0 and prev_type:
            transition = _get_paragraph_transition(topic, prev_type, ftype, config)

        paragraph = " ".join(para_sentences)
        if transition:
            # Capitalize first letter of transition
            paragraph = transition + " " + lower_first(paragraph)

        paragraphs.append(paragraph)
        prev_type = ftype

    # ── Conclusion paragraph ──
    conclusion_templates = _CONCLUSIONS.get(require_style(config), _CONCLUSIONS["neutral"])
    conclusion_template = pick(conclusion_templates, config.temperature)
    try:
        conclusion = conclusion_template.format(topic=topic)
    except (KeyError, ValueError):
        conclusion = f"So that covers the key points about {topic}."

    # Only add conclusion if we have enough content
    if len(paragraphs) >= 2 and config.verbosity > 0.2:
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
