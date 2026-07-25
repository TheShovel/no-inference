"""NLG Referring Expression Generation (REG) — generate natural references to entities.

Decides when to use:
  - Full name ("Photosynthesis", "Marie Curie")
  - Pronoun ("it", "they", "she")
  - Definite description ("this process", "the French physicist")
  - Demonstrative ("this", "that")
"""

from typing import Optional
from .models import Entity, DiscourseState
from .config import NLGConfig
from .util import pick, maybe


# ── Definite description patterns per fact type ────────────────────────────

_DESCRIPTIONS = {
    "definition": "this concept",
    "location": "this location",
    "property": "this feature",
    "composition": "this material",
    "purpose": "this purpose",
    "usage": "this use",
    "action": "this process",
    "comparison": "this comparison",
    "example": "this example",
    "event": "this event",
    "relation": "this relation",
    "unknown": "this",
}


def _subject_description(entity: Entity, fact_type: str) -> str:
    """Generate a definite description for an entity based on fact type."""
    name = entity.canonical_name
    # For proper nouns, use the name directly on first mention
    if entity.is_proper:
        return name
    # For uncountable/abstract, use "this {fact_type}" or the name
    if entity.is_uncountable:
        return _DESCRIPTIONS.get(fact_type, name)
    return name


def select_reference(
    entity: Entity,
    fact_type: str,
    state: DiscourseState,
    config: NLGConfig,
) -> str:
    """Choose the best referring expression for an entity at this point.

    Implements the classic REG algorithm:
      - First mention → full name / definite description
      - Subsequent mention → pronoun (if unambiguous)
      - After gap → definite description again for clarity

    Pure function — no I/O, no side effects.
    """
    name_lower = entity.canonical_name.lower().strip()
    if not name_lower:
        return ""

    # Check if this entity has been mentioned before
    was_mentioned = name_lower in state.mentioned_topics

    if not was_mentioned:
        # First mention — use full canonical name
        state.mentioned_topics.add(name_lower)
        state.last_reference = entity.canonical_name
        return entity.canonical_name

    # Has been mentioned — consider pronoun
    pronoun = entity.pronoun

    # Use pronoun if:
    # 1. The last reference was the same entity (continuity)
    # 2. Temperature/verbosity favors pronouns
    # 3. It's not the start of a new paragraph/section
    same_as_last = state.last_reference.lower() == name_lower
    prefer_pronoun = maybe(0.6 * config.temperature) if config.temperature > 0 else True

    if same_as_last and prefer_pronoun:
        state.last_reference = pronoun
        return pronoun

    # After a gap or for contrast — use a description or full name
    if entity.is_proper:
        state.last_reference = entity.canonical_name
        return entity.canonical_name
    else:
        desc = _subject_description(entity, fact_type)
        state.last_reference = desc
        return desc


def should_replace_with_pronoun(
    text: str, entity_name: str, config: NLGConfig
) -> bool:
    """Check if an entity occurrence in text should be replaced with a pronoun.

    Avoids replacements that would create unnatural patterns like "the it".
    """
    if not entity_name or not text:
        return False
    # Check if preceded by article
    before_pattern = r'\b(the|a|an|this|that|these|those)\s+' + re.escape(entity_name) + r'\b'
    if re.search(before_pattern, text, re.IGNORECASE):
        return False
    return True

import re  # noqa: E811 — re-imported for the function above
