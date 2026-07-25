"""NLG Lexical Variation — synonym selection and register-aware vocabulary.

Provides per-style synonym tables for common predicates and expressions.
Makes the three styles (friendly, neutral, concise) lexically distinct.
"""

import re
from typing import Dict, List, Optional
from .config import NLGConfig
from .util import pick, maybe, require_style


# ── Predicate synonym tables per style ─────────────────────────────────────

_PREDICATE_SYNONYMS: Dict[str, Dict[str, List[str]]] = {
    "is": {
        "friendly": ["is", "is basically", "is pretty much", "can be thought of as"],
        "neutral": ["is", "can be defined as", "constitutes", "represents"],
        "concise": ["is", "="],
    },
    "are": {
        "friendly": ["are", "are basically"],
        "neutral": ["are"],
        "concise": ["are"],
    },
    "located": {
        "friendly": ["located", "situated", "found", "over in", "based"],
        "neutral": ["located", "situated", "found", "based"],
        "concise": ["in"],
    },
    "has": {
        "friendly": ["has", "has got", "comes with", "features"],
        "neutral": ["has", "contains", "includes", "features"],
        "concise": ["has"],
    },
    "made of": {
        "friendly": ["made from", "made out of", "made up of"],
        "neutral": ["made of", "composed of", "consists of"],
        "concise": ["made of"],
    },
    "used for": {
        "friendly": ["used for", "used to", "for"],
        "neutral": ["used for", "utilized for", "employed for"],
        "concise": ["for"],
    },
    "produces": {
        "friendly": ["produces", "makes", "creates", "gives off"],
        "neutral": ["produces", "generates", "yields"],
        "concise": ["produces"],
    },
    "because": {
        "friendly": ["because", "since", "cause"],
        "neutral": ["because", "since", "as"],
        "concise": ["because"],
    },
}


def vary_predicate(predicate: str, config: NLGConfig) -> str:
    """Replace a predicate with a style-appropriate synonym.

    Pure function.
    """
    pred_lower = predicate.lower().strip()
    style = require_style(config)

    # Check for matches in synonym tables
    for key, variants in _PREDICATE_SYNONYMS.items():
        if key in pred_lower:
            style_variants = variants.get(style, variants.get("neutral", [predicate]))
            if style_variants and config.temperature > 0 and maybe(0.5):
                return pick(style_variants, config.temperature)
            return predicate

    return predicate


# ── Light verb constructions ───────────────────────────────────────────────

_LIGHT_VERBS = {
    "friendly": {
        "use": "make use of",
        "help": "lend a hand",
        "try": "give it a go",
    },
    "neutral": {},
    "concise": {},
}


def lighten_verb(verb: str, config: NLGConfig) -> str:
    """Replace a simple verb with a light verb construction (friendly style)."""
    style = require_style(config)
    replacements = _LIGHT_VERBS.get(style, {})
    if verb.lower() in replacements and config.temperature > 0 and maybe(0.3):
        return replacements[verb.lower()]
    return verb


# ── Contraction-appropriate substitutions ──────────────────────────────────

_CONTRACTION_SUBSTITUTIONS = {
    "it is": "it's",
    "that is": "that's",
    "there is": "there's",
    "do not": "don't",
    "does not": "doesn't",
    "cannot": "can't",
    "will not": "won't",
    "you are": "you're",
    "they are": "they're",
    "we are": "we're",
    "I am": "I'm",
    "I have": "I've",
    "I will": "I'll",
    "you will": "you'll",
    "let us": "let's",
    "is not": "isn't",
    "are not": "aren't",
    "was not": "wasn't",
    "were not": "weren't",
    "have not": "haven't",
    "has not": "hasn't",
    "could not": "couldn't",
    "would not": "wouldn't",
    "should not": "shouldn't",
}


def apply_contractions(text: str, rate: float = 1.0) -> str:
    """Apply common contractions to text.

    Pure function.

    Args:
        text: Text to contract.
        rate: Probability of applying each contraction (0.0-1.0).

    Returns:
        Text with contractions applied.
    """
    if rate <= 0:
        return text
    result = text
    for full, contracted in _CONTRACTION_SUBSTITUTIONS.items():
        if rate >= 1.0 or maybe(rate):
            result = re.sub(r'\b' + re.escape(full) + r'\b', contracted, result, flags=re.IGNORECASE)
    return result
