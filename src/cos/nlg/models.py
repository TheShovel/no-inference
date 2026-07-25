"""NLG Data Models — structured representations for NLG pipeline stages."""

from dataclasses import dataclass, field
from typing import List, Optional, Literal


# ═════════════════════════════════════════════════════════════════════════════
# Fact Representation
# ═════════════════════════════════════════════════════════════════════════════

FactType = Literal[
    "definition", "location", "property", "composition", "purpose",
    "usage", "action", "comparison", "example", "event", "relation", "unknown",
]


@dataclass
class Fact:
    """A single atomic fact extracted from information text.

    This is the core data structure that flows through the NLG pipeline.
    Each fact has a subject, predicate, object, and metadata about its type,
    certainty, and source.
    """
    subject: str
    predicate: str
    obj: str
    fact_type: FactType = "unknown"
    original: str = ""
    certainty: float = 0.8        # 0.0 (speculative) to 1.0 (definite)
    tense: str = "present"        # "present", "past", "future"
    temporal_order: Optional[int] = None  # for event sequencing
    is_negated: bool = False
    source: str = ""              # "kb", "wikipedia", "inferred"

    def __post_init__(self):
        # Infer type from predicate if not set
        if self.fact_type == "unknown":
            self.fact_type = self._infer_type()

    def _infer_type(self) -> FactType:
        p = self.predicate.lower().strip()
        if p in ("is", "are", "was", "were"):
            return "definition"
        if any(w in p for w in ("locate", "situat", "found", "based", "lie", "sit")):
            return "location"
        if any(w in p for w in ("has", "have", "had", "contain", "include", "feature")):
            return "property"
        if any(w in p for w in ("make", "compose", "consist", "form")):
            return "composition"
        if any(w in p for w in ("use", "purpose", "design", "serve", "function")):
            return "purpose"
        if any(w in p for w in ("like", "similar", "unlike", "different", "compared")):
            return "comparison"
        if any(w in p for w in ("example", "such as", "including")):
            return "example"
        if any(w in p for w in ("produce", "generate", "create", "convert", "absorb", "release")):
            return "action"
        return "definition"


# ═════════════════════════════════════════════════════════════════════════════
# Entity Representation
# ═════════════════════════════════════════════════════════════════════════════

_UNCOUNTABLE_NOUNS = {
    "photosynthesis", "quantum computing", "machine learning",
    "artificial intelligence", "recursion", "gravity",
    "electricity", "radiation", "dark matter", "energy",
    "information", "knowledge", "nature", "life", "death",
    "time", "space", "music", "furniture", "equipment",
    "research", "advice", "news", "weather", "homework",
    "traffic", "pollution", "progress", "poetry", "fiction",
}

# Pronoun indicator words (for algorithmic inference from text)
# These are used to detect what pronoun the source text uses for an entity
_PRONOUN_INDICATORS = {
    "she": "feminine",
    "her": "feminine",
    "hers": "feminine",
    "herself": "feminine",
    "he": "masculine",
    "him": "masculine",
    "his": "masculine",
    "himself": "masculine",
}


@dataclass
class Entity:
    """A named entity that can be referenced in generated text."""
    canonical_name: str
    aliases: List[str] = field(default_factory=list)
    is_proper: bool = False
    is_plural: bool = False
    is_uncountable: bool = False
    gender: Optional[Literal["neutral", "masculine", "feminine"]] = None

    def __post_init__(self):
        if not self.is_uncountable:
            name_lower = self.canonical_name.lower().strip()
            self.is_uncountable = name_lower in _UNCOUNTABLE_NOUNS
        if self.is_uncountable:
            self.is_plural = False

    @property
    def pronoun(self) -> str:
        """Get the subject pronoun for this entity.

        Algorithmic — no hardcoded name lists:
          1. Use gender inferred from source text if available
          2. Check plural/uncountable
          3. Person-name heuristic (multi-word capitalized -> they)
          4. Default to it
        """
        if self.gender == "masculine":
            return "he"
        if self.gender == "feminine":
            return "she"
        if self.is_plural:
            return "they"
        if self.is_uncountable:
            return "it"
        # Person name heuristic: multi-word, all parts capitalized
        parts = self.canonical_name.split()
        if len(parts) >= 2 and all(p[0].isupper() for p in parts if p):
            return "they"  # gender-neutral singular they
        if self.canonical_name.lower().endswith("s") and not self.canonical_name.lower().endswith("ss"):
            return "they"
        return "it"

    @property
    def objective_pronoun(self) -> str:
        p = self.pronoun
        return {"he": "him", "she": "her", "they": "them", "it": "it"}.get(p, "it")

    @property
    def possessive_pronoun(self) -> str:
        p = self.pronoun
        return {"he": "his", "she": "her", "they": "their", "it": "its"}.get(p, "its")


def build_entity(name: str, source_text: str = "") -> Entity:
    """Build an Entity from a name string with auto-inferred properties.

    Gender/pronoun is inferred ALGORITHMICALLY from the source text
    by checking what pronouns are used to refer to the entity.
    No hardcoded name lists.
    """
    n = name.strip()
    if not n:
        return Entity(canonical_name="")
    is_proper = n[0].isupper() if n else False
    is_plural = n.lower().endswith("s") and not n.lower().endswith("ss") and not is_proper

    gender = _infer_gender_from_text(n, source_text)

    return Entity(
        canonical_name=n,
        is_proper=is_proper,
        is_plural=is_plural,
        gender=gender,
    )


def _infer_gender_from_text(entity_name: str, source_text: str) -> Optional[str]:
    """Infer an entity's gender from pronoun usage in source text.

    Algorithm:
      1. Find sentences in source_text that mention the entity
      2. In nearby sentences, look for gendered pronouns (she/her, he/him)
      3. Return the gender corresponding to the most common pronoun found
      4. If no pronouns found, return None (default to "it")

    No hardcoded name lists. Purely data-driven.
    """
    if not source_text or not entity_name:
        return None

    import re
    name_lower = entity_name.lower().strip()
    name_words = name_lower.split()
    sentences = re.split(r'(?<=[.!?])\s+', source_text)

    # Find sentences that mention the entity (or are nearby)
    relevant_sentences = []
    for i, sent in enumerate(sentences):
        s_lower = sent.lower()
        # Check if entity name appears in this sentence
        if name_lower in s_lower:
            relevant_sentences.append(sent)
            # Also include adjacent sentences (they often continue using the same pronoun)
            if i > 0:
                relevant_sentences.append(sentences[i - 1])
            if i < len(sentences) - 1:
                relevant_sentences.append(sentences[i + 1])

    # Also check what pronouns appear as standalone references (not inside the entity name itself)
    # E.g., "She conducted..." in a sentence right after "Marie Curie was..."
    for sent in sentences:
        s_lower = sent.lower()
        # Check if sentence starts with a pronoun (common pattern: "She/He/They did X")
        # This often follows an introductory sentence about the entity
        if re.match(r'\b(She|He|They|It)\b', sent):
            # Check if the previous sentence mentions the entity
            idx = sentences.index(sent)
            if idx > 0:
                prev_lower = sentences[idx - 1].lower()
                if name_lower in prev_lower:
                    relevant_sentences.append(sent)

    if not relevant_sentences:
        return None

    # Tally pronouns used in relevant sentences
    pronoun_counts = {"feminine": 0, "masculine": 0}
    pronoun_pattern = re.compile(
        r'\b(she|her|hers|herself|he|him|his|himself)\b', re.IGNORECASE
    )

    for sent in relevant_sentences:
        for match in pronoun_pattern.finditer(sent):
            word = match.group(1).lower()
            if word in _PRONOUN_INDICATORS:
                gender = _PRONOUN_INDICATORS[word]
                pronoun_counts[gender] += 1

    # Return the gender with the most pronoun references
    if pronoun_counts["feminine"] > pronoun_counts["masculine"]:
        return "feminine"
    elif pronoun_counts["masculine"] > pronoun_counts["feminine"]:
        return "masculine"
    return None  # No clear signal in text


# ═════════════════════════════════════════════════════════════════════════════
# Discourse Structure
# ═════════════════════════════════════════════════════════════════════════════

DiscourseRelation = Literal[
    "introduce", "elaborate", "contrast", "cause", "example",
    "concession", "conclude", "sequence", "compare",
]


@dataclass
class DiscourseUnit:
    """A unit of discourse with a rhetorical relation and its facts."""
    relation: DiscourseRelation = "elaborate"
    facts: List[Fact] = field(default_factory=list)
    marker: str = ""

    def add_fact(self, fact: Fact) -> None:
        self.facts.append(fact)

    @property
    def text(self) -> str:
        return " ".join(f.original for f in self.facts if f.original)


@dataclass
class DiscourseTree:
    """A tree-structured discourse plan.

    Unlike a flat list of sentences, this tree allows nested discourse
    relations (e.g., contrast containing elaboration) and paragraph
    grouping for longer responses.
    """
    relation: DiscourseRelation = "introduce"
    children: List["DiscourseTree"] = field(default_factory=list)
    unit: Optional[DiscourseUnit] = None
    paragraph_break: bool = False

    def add_child(self, child: "DiscourseTree") -> None:
        self.children.append(child)

    def is_leaf(self) -> bool:
        return not self.children


# ═════════════════════════════════════════════════════════════════════════════
# Discourse State (tracks what's been expressed)
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class DiscourseState:
    """Track what's been mentioned during generation to avoid repetition."""
    entities: dict = field(default_factory=dict)       # name -> Entity
    mentioned_facts: set = field(default_factory=set)   # indices of expressed facts
    mentioned_topics: set = field(default_factory=set)  # topics already introduced
    last_reference: str = ""                            # last referring expression
    sentence_count: int = 0

    def register_entity(self, name: str, entity: Entity) -> None:
        self.entities[name.lower()] = entity

    def get_entity(self, name: str) -> Optional[Entity]:
        return self.entities.get(name.lower())

    def mark_mentioned(self, fact_index: int) -> None:
        self.mentioned_facts.add(fact_index)

    def was_mentioned(self, fact_index: int) -> bool:
        return fact_index in self.mentioned_facts

    def __post_init__(self):
        if self.entities is None:
            self.entities = {}
        if self.mentioned_facts is None:
            self.mentioned_facts = set()
        if self.mentioned_topics is None:
            self.mentioned_topics = set()
