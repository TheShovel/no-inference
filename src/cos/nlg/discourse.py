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
            "",
            "",
        ],
        "neutral": [
            "",
        ],
        "concise": ["", "", ""],
    },
    "locate": {
        "friendly": [
            "",
            "",
        ],
        "neutral": [
            "",
        ],
        "concise": ["", ""],
    },
    "attribute": {
        "friendly": [
            "",
            "",
        ],
        "neutral": [
            "",
        ],
        "concise": ["", ""],
    },
    "structure": {
        "friendly": [
            "",
        ],
        "neutral": [
            "",
        ],
        "concise": ["", ""],
    },
    "reason": {
        "friendly": [
            "",
        ],
        "neutral": [
            "",
        ],
        "concise": ["", ""],
    },
    "contrast": {
        "friendly": [
            "However,",
            "That said,",
            "At the same time,",
        ],
        "neutral": [
            "However,",
            "On the other hand,",
            "In contrast,",
        ],
        "concise": ["But,", "", ""],
    },
    "cause": {
        "friendly": [
            "Because of that,",
            "That's why",
            "So",
        ],
        "neutral": [
            "As a result,",
            "Therefore,",
        ],
        "concise": ["So,", "", ""],
    },
    "example": {
        "friendly": [
            "For example,",
            "For instance,",
        ],
        "neutral": [
            "For example,",
            "For instance,",
        ],
        "concise": ["E.g.,", "", ""],
    },
    "concession": {
        "friendly": [
            "Of course,",
            "Admittedly,",
            "To be fair,",
        ],
        "neutral": [
            "Admittedly,",
            "Of course,",
        ],
        "concise": ["Sure,", "", ""],
    },
    "conclude": {
        "friendly": [
            "In short,",
            "So overall,",
            "",
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
        ],
        "neutral": [
            "Similarly,",
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

    Assigns markers based on the relationship between consecutive facts:
    - Same subject → no marker (combine.py handles these naturally)
    - Different subject → light connector sometimes, based on fact type transition
    - Never forces a concluding marker — they only appear when the relation fits

    Pure function.
    """
    if not facts:
        return DiscourseTree(relation="introduce")

    root = DiscourseTree(relation="introduce")

    for i, fact in enumerate(facts):
        marker = ""
        rel: DiscourseRelation = "introduce" if i == 0 else "elaborate"

        if i > 0:
            prev = facts[i - 1]
            same_subj = fact.subject.lower().strip() == prev.subject.lower().strip()

            if not same_subj:
                # Different subject — pick a relation based on type transition
                rel = _transition_relation(prev.fact_type, fact.fact_type, i, len(facts))
                # Use markers for natural flow between different subjects
                if rel != "introduce":
                    if config.temperature <= 0.0 or maybe(0.35):
                        marker = get_marker(rel, config)
            elif i >= 4 and config.temperature > 0.0:
                # Same subject, deep in response — very occasional connector for flow
                if maybe(0.15):
                    marker = get_marker("elaborate", config)

        unit = DiscourseUnit(
            relation=rel,
            facts=[fact],
            marker=marker,
        )
        child = DiscourseTree(
            relation=rel,
            unit=unit,
        )
        root.add_child(child)

    return root


def _transition_relation(prev_type: str, next_type: str, position: int, total: int) -> DiscourseRelation:
    """Determine the discourse relation between two fact types."""
    transitions = {
        ("definition", "location"): "locate",
        ("definition", "property"): "attribute",
        ("definition", "composition"): "structure",
        ("definition", "purpose"): "reason",
        ("location", "property"): "attribute",
        ("location", "composition"): "structure",
        ("composition", "purpose"): "cause",
        ("composition", "property"): "attribute",
        ("property", "usage"): "elaborate",
        ("property", "comparison"): "contrast",
        ("purpose", "usage"): "elaborate",
        ("purpose", "example"): "example",
        ("usage", "example"): "example",
        ("usage", "comparison"): "contrast",
        ("action", "property"): "attribute",
        ("action", "purpose"): "reason",
        ("comparison", "property"): "attribute",
    }
    key = (prev_type, next_type)
    if key in transitions:
        return transitions[key]  # type: ignore
    # Only conclude for longer responses (5+ facts); otherwise just elaborate
    if total >= 5 and position >= total - 1:
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
