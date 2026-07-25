"""NLG Fact Parser — extract structured Fact objects from raw information text.

Turns raw sentences into typed facts with subject, predicate, object, and
metadata. Uses regex patterns to identify sentence structure and fact type.
"""

import re
from typing import List, Optional, Tuple
from .models import Fact, Entity, build_entity
from .util import split_sentences


# ── Sentence structure patterns ────────────────────────────────────────────

# Pattern: (Subject) (predicate) (object/rest)
_SVO_PATTERN = re.compile(
    r'((?:The|A|An|This|That|These|Those|Some|Many|Most|Several)?'
    r'(?:[A-Z]?[\w\'-]+(?:\s+[A-Z]?[\w\'-]+?)??))\s+'
    r'(is|are|was|were|has|have|had|refers?\s+to|means?|'
    r'can\s+be\s+(?:defined|described|found|used|made)|'
    r'is\s+(?:located|situated|found|based|made|used|known|'
    r'served|eaten|called|considered|regarded|seen)|'
    r'are\s+(?:located|situated|found|based|made|used|known|'
    r'served|eaten|called|considered|regarded|seen)|'
    r'was\s+(?:released|created|invented|developed|born|formed|attacked|dropped|performed)|'
    r'were\s+(?:released|created|invented|developed|born|formed|attacked|dropped|performed)|'
    r'consists?\s+of|composed\s+of|'
    r'contain[s]?|include[s]?|feature[s]?|'
    r'produce[s]?|generate[s]?|create[s]?|convert[s]?|'
    r'discover(?:ed)?|invent(?:ed)?|develop(?:ed)?|formulat(?:e|ed|es)|'
    r'conduct(?:ed)?|win|won|write?|wrote|written|built|build?|'
    r'use[s]?|require[s]?|need[s]?|'
    r'lie[s]?|occur(?:red|s)?|live[s]?|'
    r'work(?:ed)?|stud(?:y|ied)|play[s]?|serv(?:e|ed)?|'
    r'allow[s]?|enable[s]?|help[s]?|make[s]?|made|take[s]?|took|given?|give[s]?|'
    r'orbit[s]?|rotate[s]?|revolve[s]?|circle[s]?|travel[s]?|move[s]?|'
    r'remain[s]?|stay[s]?|keep[s]?|last[s]?|continue[s]?|span[s]?|cover[s]?|weigh[s]?|'
    r'protect[s]?|stabiliz(?:e|es|ed)|emphasiz(?:e|es|ed)|support[s]?|consum(?:e|es|ed)|'
    r'invad(?:e|es|ed)|attack(?:ed|s)|surrender(?:ed|s)|enter(?:ed|s)|mark(?:ed|s)|die[s|d]|'
    r'begin[s]?|start[s]?|stop[s]?|end[s]?|finish[s]?)\s+'
    r'(.+)',
    re.IGNORECASE,
)


# ── Predicate → Fact type mapping ──────────────────────────────────────────

_PREDICATE_TYPE_MAP = [
    (r'\b(?:is|are|was|were)\s+(?:a|an|the)\s', 'definition'),
    (r'\brefers?\s+to\b', 'definition'),
    (r'\b(?:is|are)\s+defined\s+as\b', 'definition'),
    (r'\b(?:is|are)\s+known\s+as\b', 'definition'),
    (r'\b(?:is|are)\s+(?:located|situated|found|based)\s+(?:in|on|at|near)\b', 'location'),
    (r'\blie[s]?\s+(?:in|on|at|near)\b', 'location'),
    (r'\b(?:is|are)\s+made\s+(?:of|from|with|using)\b', 'composition'),
    (r'\bconsists?\s+of\b', 'composition'),
    (r'\b(?:is|are)\s+composed\s+of\b', 'composition'),
    (r'\bcontain[s]?\b', 'property'),
    (r'\binclude[s]?\b', 'property'),
    (r'\bfeature[s]?\b', 'property'),
    (r'\bhas|have\b', 'property'),
    (r'\b(?:is|are)\s+used\s+(?:for|to)\b', 'purpose'),
    (r'\b(?:is|are)\s+designed\s+(?:for|to)\b', 'purpose'),
    (r'\bserves?\s+as\b', 'purpose'),
    (r'\bproduce[s]?\b', 'action'),
    (r'\bgenerate[s]?\b', 'action'),
    (r'\bcreate[s]?\b', 'action'),
    (r'\bconvert[s]?\b', 'action'),
    (r'\bwin|won\b', 'action'),
    (r'\bconduct[ed]?\b', 'action'),
    (r'\bdiscover[ed]?\b', 'action'),
    (r'\binvent[ed]?\b', 'action'),
    (r'\bdevelop[ed]?\b', 'action'),
    (r'\bformulat[ed]?\b', 'action'),
    (r'\bfound[ed]?\b', 'action'),
    (r'\bbuild?|built\b', 'action'),
    (r'\bwrite?|wrote|written\b', 'action'),
    (r'\bstudy?|studied\b', 'action'),
    (r'\bwork[ed]?\s+(?:as|on|for|with)\b', 'action'),
    (r'\bplay[s]?\b', 'action'),
    (r'\bserve[ed]?\s+as\b', 'purpose'),
    (r'\bunlike\b', 'comparison'),
    (r'\bsimilar\b', 'comparison'),
    (r'\bfor example\b', 'example'),
    (r'\bsuch as\b', 'example'),
]


def _classify_predicate(predicate: str, obj: str) -> Tuple[str, float]:
    """Determine fact type from predicate."""
    combined = predicate + " " + obj
    for pattern, ftype in _PREDICATE_TYPE_MAP:
        if re.search(pattern, combined, re.IGNORECASE):
            return ftype, 0.8
    return 'definition', 0.5


# ── Tense detection ────────────────────────────────────────────────────────

_TENSE_PATTERNS = [
    (r'\bwas\b|\bwere\b|\bhad\b|\bdid\b|ed\b', 'past'),
    (r'\bwill\b|\bshall\b', 'future'),
    (r'\bis\b|\bare\b|\bhas\b|\bhave\b|\bdoes\b|\bdo\b', 'present'),
]


def _detect_tense(text: str) -> str:
    for pattern, tense in _TENSE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return tense
    return 'present'


# ═════════════════════════════════════════════════════════════════════════════
# Main Parsing API
# ═════════════════════════════════════════════════════════════════════════════

def parse_facts(information: str, topic: str = "") -> List[Fact]:
    """Parse raw information text into structured Fact objects.

    Extracts subject-predicate-object triples from each sentence,
    classifies each fact by type, and detects tense.

    Pure function — no I/O, no side effects.

    Args:
        information: Raw text to parse.
        topic: The known topic (used for entity resolution).

    Returns:
        List of Fact objects, one per parseable sentence.
    """
    if not information or not information.strip():
        return []

    topic_lower = topic.lower().strip() if topic else ""
    facts: List[Fact] = []
    sentences = split_sentences(information)

    for sentence in sentences:
        orig = sentence.strip()
        if not orig:
            continue

        fact = _parse_sentence(orig, topic_lower)
        if fact:
            facts.append(fact)
        else:
            # Fallback: unknown fact type — store original sentence in obj with empty predicate
            # so realization returns the sentence as-is without prepending "Topic is "
            facts.append(Fact(
                subject=topic or "",
                predicate="",
                obj=orig,
                fact_type="unknown",
                original=orig,
                certainty=0.4,
                is_negated=bool(re.search(r'\b(?:not|never|no|without|neither|nor)\b', orig, re.IGNORECASE)),
            ))

    return facts


def _parse_sentence(sentence: str, topic_lower: str) -> Optional[Fact]:
    """Parse a single sentence into a Fact, or None if unparseable."""
    # Remove leading discourse markers for analysis
    analysis = re.sub(
        r'^(Well|So|Actually|Oh|Okay|Now|However|Moreover|Furthermore|'
        r'In addition|Additionally|Nevertheless|Nonetheless|Meanwhile),?\s+',
        '', sentence, flags=re.IGNORECASE
    )

    m = _SVO_PATTERN.match(analysis)
    if not m:
        return None

    subject = m.group(1).strip()
    predicate = m.group(2).strip()
    obj = m.group(3).strip().rstrip('.,;:')

    # Determine fact type
    fact_type, confidence = _classify_predicate(predicate, obj)

    # Detect tense
    tense = _detect_tense(analysis)

    # Check for negation across sentence, predicate, or object
    is_negated = bool(re.search(r'\b(?:not|never|no|without|neither|nor)\b', sentence, re.IGNORECASE))

    return Fact(
        subject=subject,
        predicate=predicate,
        obj=obj,
        fact_type=fact_type,
        original=sentence,
        certainty=confidence,
        tense=tense,
        is_negated=is_negated,
    )


# ── Entity extraction ──────────────────────────────────────────────────────

def extract_entities(facts: List[Fact], source_text: str = "") -> dict:
    """Extract a name->Entity registry from a list of Facts.

    Uses source text to algorithmically infer entity gender/pronoun
    from pronoun usage in the data itself (no hardcoded name lists).

    Pure function.
    """
    registry: dict = {}
    for fact in facts:
        for name in (fact.subject, fact.obj):
            n = name.strip()
            if not n or n.lower() in ('it', 'they', 'he', 'she', 'we', 'you'):
                continue
            key = n.lower()
            if key not in registry:
                registry[key] = build_entity(n, source_text)
    return registry


def merge_subject_entities(registry: dict, topic: str) -> dict:
    """Merge topic into entity registry, normalizing references.

    Ensures that pronoun references like 'it' or 'they' in facts
    get linked to their canonical entity.
    """
    if not topic:
        return registry
    t_key = topic.lower().strip()
    if t_key and t_key not in registry:
        registry[t_key] = build_entity(topic)
    return registry
