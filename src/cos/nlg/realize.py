"""NLG Sentence Realization — generate syntactic variants per fact type.

Provides pattern-based sentence generation for typed facts. Each fact type
has multiple surface realizations depending on style and context.
"""

import re
from typing import List, Optional
from .models import Fact, DiscourseState
from .config import NLGConfig
from .util import pick, maybe, lower_first, upper_first, require_style


# ── Sentence patterns per fact type per style ──────────────────────────────

_PATTERNS = {
    "definition": {
        "friendly": [
            "{subject} {verb} {obj}.",
            "So {subject} {verb} {obj}.",
            "Basically, {subject} {verb} {obj}.",
            "{subject} {verb} {obj} — plain and simple.",
        ],
        "neutral": [
            "{subject} {verb} {obj}.",
        ],
        "concise": [
            "{subject}: {obj}.",
        ],
    },
    "location": {
        "friendly": [
            "You can find it {prep} {place}.",
            "It's located {prep} {place}.",
            "It's over {prep} {place}.",
        ],
        "neutral": [
            "{subject} is located {prep} {place}.",
            "It's located {prep} {place}.",
        ],
        "concise": [
            "{prep} {place}.",
        ],
    },
    "property": {
        "friendly": [
            "{subject} has {obj}.",
            "It's got {obj}.",
            "It comes with {obj}.",
        ],
        "neutral": [
            "{subject} has {obj}.",
            "{subject} includes {obj}.",
            "It features {obj}.",
        ],
        "concise": [
            "Has {obj}.",
        ],
    },
    "composition": {
        "friendly": [
            "It's made from {obj}.",
            "It's made up of {obj}.",
            "It consists of {obj}.",
        ],
        "neutral": [
            "It's made of {obj}.",
            "{subject} consists of {obj}.",
        ],
        "concise": [
            "Made of {obj}.",
        ],
    },
    "purpose": {
        "friendly": [
            "It's used for {obj}.",
            "People use it to {obj}.",
        ],
        "neutral": [
            "It's used for {obj}.",
            "{subject} serves as {obj}.",
        ],
        "concise": [
            "Used {obj}.",
        ],
    },
    "action": {
        "friendly": [
            "{subject} {verb} {obj}.",
        ],
        "neutral": [
            "{subject} {verb} {obj}.",
        ],
        "concise": [
            "{verb} {obj}.",
        ],
    },
    "comparison": {
        "friendly": [
            "It's like {obj}.",
            "Think of it as {obj}.",
        ],
        "neutral": [
            "It is similar to {obj}.",
        ],
        "concise": [
            "Like {obj}.",
        ],
    },
    "unknown": {
        "friendly": ["{obj}.", "Also, {obj_lower}."],
        "neutral": ["{obj}."],
        "concise": ["{obj}."],
    },
}


def realize_fact(
    fact: Fact,
    config: NLGConfig,
    state: Optional[DiscourseState] = None,
    use_pronoun: bool = True,
) -> str:
    """Generate a natural sentence from a Fact.

    Pure function.

    Args:
        fact: The fact to realize.
        config: NLG configuration.
        state: Optional discourse state for reference tracking.
        use_pronoun: Whether to use pronouns for known entities.

    Returns:
        A natural language sentence.
    """
    style = require_style(config)
    templates = _PATTERNS.get(fact.fact_type)
    if not templates:
        templates = _PATTERNS["unknown"]
    style_templates = list(templates.get(style, templates.get("neutral", [])))

    # ── Ensure "refers to" is only used for true definition predicates ──
    # The "refers to" variant should only fire when the fact's predicate
    # is a copular verb (is/are/was/were), not for action or other predicates
    # that happened to be classified as "definition".
    copular = fact.predicate.strip().lower() in ("is", "are", "was", "were")
    if not copular:
        # Remove any "refers to" template from the pool
        style_templates = [t for t in style_templates if "refers to" not in t]
        if not style_templates:
            style_templates = ["{subject} {verb} {obj}."]

    template = pick(style_templates, config.temperature)

    subject = fact.subject
    obj = fact.obj
    obj_lower = lower_first(obj)

    # ── Determine if subject is plural for verb agreement ──
    # This mirrors the heuristic in apply_pronouns().
    subj_lower = subject.strip().lower()
    is_plural_subject = (
        subj_lower.endswith("s") and not subj_lower.endswith("ss")
        and subj_lower not in ("this", "thus", "bus", "gas", "was", "its")
    )

    # ── Resolve "refers to"/"refer to" based on subject number ──
    if "refers to" in template and is_plural_subject:
        template = template.replace("refers to", "refer to")

    # Try to build the sentence from the template
    try:
        if fact.fact_type == "location":
            # Parse location: "located in Paris" -> prep="in", place="Paris"
            loc_match = re.match(
                r'(?:located|situated|found|based)\s+(in|on|at|near)\s+(.+)',
                obj, re.IGNORECASE
            )
            if not loc_match:
                loc_match = re.match(r'(in|on|at|near)\s+(.+)', obj, re.IGNORECASE)
            if loc_match:
                prep = loc_match.group(1)
                place = loc_match.group(2)
            else:
                prep = "in"
                place = obj
            sentence = template.format(subject=subject, verb=fact.predicate,
                                       obj=obj, obj_pro=lower_first(obj),
                                       prep=prep, place=place)
        elif fact.fact_type == "composition":
            comp_match = re.match(r'(?:made|composed|consisting)\s+(?:of|from|with|using)\s+(.+)', obj, re.IGNORECASE)
            clean_obj = comp_match.group(1) if comp_match else obj
            sentence = template.format(subject=subject, verb=fact.predicate,
                                       obj=lower_first(clean_obj), obj_pro=lower_first(clean_obj))
        else:
            sentence = template.format(subject=subject, verb=fact.predicate,
                                       obj=obj, obj_pro=obj_lower, obj_lower=obj_lower,
                                       place=obj)
    except (KeyError, ValueError):
        # Fallback: simple subject-verb-object
        sentence = f"{subject} {fact.predicate} {obj}."

    # Capitalize and ensure ending punctuation
    sentence = upper_first(sentence.strip())
    if not sentence.endswith(('.', '!', '?')):
        sentence += "."

    return sentence


# ── Opening generation ─────────────────────────────────────────────────────

_OPENINGS = {
    "how": {
        "friendly": ["Here's what you do:", "Here's how it works:", "It's pretty straightforward:"],
        "neutral": ["Here's how:", "The process is:"],
        "concise": [""],
    },
    "who": {
        "friendly": ["Let me tell you:", "Here's what I know:", "Great question!"],
        "neutral": ["So,", "Well,"],
        "concise": [""],
    },
    "explain": {
        "friendly": ["Great question! So", "Happy to explain!", "Okay, so", "So here's the thing:"],
        "neutral": ["So,", "Well,", "Here's the answer:"],
        "concise": [""],
    },
    "define": {
        "friendly": ["Great question! So", "Okay, so", "Alright, so"],
        "neutral": ["So,", "Well,", "By definition,"],
        "concise": [""],
    },
    "where": {
        "friendly": ["You can find it", "It's over in", "It's located"],
        "neutral": ["It's located", "It's found"],
        "concise": [""],
    },
    "factual": {
        "friendly": ["So here's the deal:", "Well,", "Okay, so"],
        "neutral": ["So,", "Well,", "Here's the answer:"],
        "concise": [""],
    },
}


def classify_query(query: str) -> str:
    """Classify query into a communicative type."""
    q = query.lower().strip()
    if any(p in q for p in ['how do i', 'how can i', 'how to', 'how would i']):
        return 'how'
    if any(p in q for p in ['who is', 'who was', 'who are', 'who were']):
        return 'who'
    if any(p in q for p in ['define', 'what is the definition', 'what does', 'mean']):
        return 'define'
    if any(p in q for p in ['explain', 'describe', 'tell me about', 'what is', "what's", 'what are']):
        return 'explain'
    if any(p in q for p in ['where is', 'where are', 'where was', 'where can']):
        return 'where'
    return 'factual'


def get_opening(query: str, config: NLGConfig) -> str:
    """Get an intent-aware opening phrase."""
    qtype = classify_query(query)
    style = require_style(config)
    pool = _OPENINGS.get(qtype, _OPENINGS['factual']).get(style, _OPENINGS['factual']['neutral'])
    return pick(pool, config.temperature)


# ── Closings ───────────────────────────────────────────────────────────────

_CLOSINGS = {
    "friendly": [
        "Hope that helps!",
        "Hope that clears things up!",
        "Let me know if you want to dive deeper!",
        "Happy to help! Anything else?",
        "That's the gist of it!",
        "",
        "",
    ],
    "neutral": [
        "Hope that answers your question.",
        "Let me know if you need more details.",
        "",
        "",
    ],
    "concise": [],
}


def get_closing(config: NLGConfig) -> str:
    """Get a style-appropriate closing."""
    if config.verbosity < 0.3:
        return ""
    closings = _CLOSINGS.get(config.style, _CLOSINGS["neutral"])
    return pick(closings, config.temperature)
