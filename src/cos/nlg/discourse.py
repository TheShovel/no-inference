"""NLG Discourse Planning — discourse tree construction and rhetorical relations.

Takes parsed facts and packages them into a structured discourse tree with
rhetorical relations (elaboration, contrast, cause, example, concession, etc.).
"""

import re
from typing import List, Dict, Optional
from .models import Fact, DiscourseTree, DiscourseUnit, DiscourseRelation
from .config import NLGConfig
from .util import pick, maybe, lower_first


# ── Discourse markers per relation per style ────────────────────────────────

_MARKERS: Dict[str, Dict[str, List[str]]] = {
    "elaborate": {
        "friendly": [
            "What's interesting is that",
            "Here's the cool part:",
            "On top of that,",
            "Not only that, but",
            "And get this:",
            "Plus,",
        ],
        "neutral": [
            "In addition,",
            "Furthermore,",
            "Moreover,",
            "Additionally,",
            "What's more,",
        ],
        "concise": ["", "", ""],
    },
    "contrast": {
        "friendly": [
            "But here's the thing:",
            "However,",
            "That said,",
            "At the same time,",
            "On the flip side,",
        ],
        "neutral": [
            "However,",
            "Nevertheless,",
            "On the other hand,",
            "In contrast,",
        ],
        "concise": ["But,", "", ""],
    },
    "cause": {
        "friendly": [
            "Because of that,",
            "That's why",
            "As a result,",
            "So",
        ],
        "neutral": [
            "Consequently,",
            "As a result,",
            "Therefore,",
        ],
        "concise": ["So,", "", ""],
    },
    "example": {
        "friendly": [
            "For example,",
            "Like,",
            "For instance,",
            "Take this:",
        ],
        "neutral": [
            "For example,",
            "For instance,",
        ],
        "concise": ["E.g.,", "", ""],
    },
    "concession": {
        "friendly": [
            "I mean, sure,",
            "Of course,",
            "Admittedly,",
            "To be fair,",
        ],
        "neutral": [
            "Admittedly,",
            "While it's true that",
            "Of course,",
        ],
        "concise": ["Sure,", "", ""],
    },
    "conclude": {
        "friendly": [
            "So basically,",
            "At the end of the day,",
            "Long story short,",
            "So yeah,",
        ],
        "neutral": [
            "In short,",
            "To summarize,",
            "Overall,",
        ],
        "concise": ["So:", "", ""],
    },
    "sequence": {
        "friendly": ["First,", "Then,", "Next,", "After that,", "Finally,"],
        "neutral": ["First,", "Subsequently,", "Next,", "Finally,"],
        "concise": ["", "", ""],
    },
    "compare": {
        "friendly": [
            "Similarly,",
            "Likewise,",
            "In the same way,",
            "By contrast,",
        ],
        "neutral": [
            "Similarly,",
            "Likewise,",
            "By comparison,",
        ],
        "concise": ["", ""],
    },
}


# ── Sentence-level relation detection ──────────────────────────────────────

_KEYWORD_MAP: List[tuple] = [
    (['unlike', 'similar', 'different', 'however', 'but', 'although',
      'though', 'compared', 'whereas', 'while', 'yet', 'nevertheless',
      'nonetheless', 'on the other hand', 'in contrast'], 'contrast'),
    (['example', 'like ', 'such as', 'including', 'for instance',
      'for example'], 'example'),
    (['because', 'so ', 'therefore', 'thus', 'hence', 'as a result',
      'due to', 'leads to', 'causes', 'consequently'], 'cause'),
    (['first', 'second', 'third', 'then', 'next', 'after', 'before',
      'subsequently', 'finally', 'initially', 'later'], 'sequence'),
    (['similarly', 'likewise', 'in the same way', 'by comparison',
      'by contrast', 'compared to'], 'compare'),
    (['admittedly', 'of course', 'to be fair', 'while it is true',
      'conceding', 'granted'], 'concession'),
    (['also', 'in addition', 'furthermore', 'moreover', 'additionally',
      'another', 'as well', 'besides'], 'elaborate'),
    (['in conclusion', 'to summarize', 'overall', 'in short',
      'to sum up', 'all in all'], 'conclude'),
]


def detect_relation(text: str) -> DiscourseRelation:
    """Detect the discourse relation of a sentence from its lexical cues."""
    lower = text.lower()
    for keywords, relation in _KEYWORD_MAP:
        for kw in keywords:
            if kw in lower:
                return relation  # type: ignore
    return "elaborate"


def get_marker(relation: DiscourseRelation, config: NLGConfig) -> str:
    """Get a discourse marker for the given relation and style."""
    style = config.style if config.style in ("friendly", "neutral", "concise") else "neutral"
    pool = _MARKERS.get(relation, {}).get(style, _MARKERS.get(relation, {}).get("neutral", [""]))
    return pick(pool, config.temperature)


# ═════════════════════════════════════════════════════════════════════════════
# Discourse Tree Construction
# ═════════════════════════════════════════════════════════════════════════════

_FACT_TYPE_ORDER = [
    "definition", "location", "composition", "property",
    "purpose", "usage", "action", "comparison", "example", "unknown",
]


def build_discourse_tree(
    facts: List[Fact],
    config: NLGConfig,
) -> DiscourseTree:
    """Build a discourse tree from a list of facts.

    Groups facts by type into discourse units, orders them for natural flow,
    and assigns rhetorical relations between units.

    Pure function.
    """
    if not facts:
        return DiscourseTree(relation="introduce")

    root = DiscourseTree(relation="introduce")

    # Group facts by type
    groups: Dict[str, List[Fact]] = {}
    for fact in facts:
        groups.setdefault(fact.fact_type, []).append(fact)

    # Order groups by priority
    ordered_types = sorted(groups.keys(), key=lambda t: _FACT_TYPE_ORDER.index(t) if t in _FACT_TYPE_ORDER else 99)

    prev_type = None
    for i, ftype in enumerate(ordered_types):
        group_facts = groups[ftype]

        # Determine relation from previous group
        if i == 0:
            relation: DiscourseRelation = "introduce"
        else:
            relation = _transition_relation(prev_type or "", ftype, i, len(ordered_types))

        unit = DiscourseUnit(
            relation=relation,
            facts=group_facts,
            marker="" if i == 0 else get_marker(relation, config),
        )
        child = DiscourseTree(
            relation=relation,
            unit=unit,
            paragraph_break=(i > 0 and relation in ("contrast", "compare")),
        )
        root.add_child(child)
        prev_type = ftype

    # If there's only one type and one fact, the root IS the leaf
    if len(root.children) == 1 and root.children[0].is_leaf():
        root = root.children[0]

    return root


def _transition_relation(prev_type: str, next_type: str, position: int, total: int) -> DiscourseRelation:
    """Determine the discourse relation between two fact types."""
    transitions = {
        ("definition", "location"): "elaborate",
        ("definition", "property"): "elaborate",
        ("definition", "composition"): "elaborate",
        ("definition", "purpose"): "elaborate",
        ("location", "property"): "elaborate",
        ("location", "composition"): "elaborate",
        ("composition", "purpose"): "cause",
        ("property", "usage"): "elaborate",
        ("property", "comparison"): "contrast",
        ("purpose", "usage"): "elaborate",
        ("purpose", "example"): "example",
        ("usage", "example"): "example",
        ("usage", "comparison"): "contrast",
    }
    key = (prev_type, next_type)
    if key in transitions:
        return transitions[key]  # type: ignore
    if position >= total - 1:
        return "conclude"
    return "elaborate"


# ── Fact ordering ──────────────────────────────────────────────────────────

def order_facts(facts: List[Fact]) -> List[Fact]:
    """Order facts for natural flow: definitions first, then specifics.

    Within each type, facts are ordered by type priority then by
    object length (shorter first) so that general/atomic facts come
    before elaborated ones.

    Pure function.
    """
    if not facts:
        return facts

    def type_rank(t: str) -> int:
        try:
            return _FACT_TYPE_ORDER.index(t)
        except ValueError:
            return len(_FACT_TYPE_ORDER)

    # Sort by type rank first, then by obj length within each type
    sorted_facts = sorted(facts, key=lambda f: (type_rank(f.fact_type), len(f.obj)))

    # Separate definitions from everything else
    definitions = [f for f in sorted_facts if f.fact_type == "definition"]
    others = [f for f in sorted_facts if f.fact_type != "definition"]

    # Within definitions, prefer shorter, more atomic statements first.
    # This keeps general definitions ("X is Y") before verbose ones.
    definitions.sort(key=lambda f: (len(f.subject) + len(f.obj)))

    return definitions + others


# ── Flatten tree to ordered units ──────────────────────────────────────────

def flatten_tree(tree: DiscourseTree) -> List[DiscourseUnit]:
    """Flatten a discourse tree into an ordered list of discourse units.

    Pure function.
    """
    units: List[DiscourseUnit] = []

    if tree.is_leaf() and tree.unit:
        units.append(tree.unit)
    else:
        for child in tree.children:
            if child.is_leaf() and child.unit:
                units.append(child.unit)
            else:
                units.extend(flatten_tree(child))

    return units
