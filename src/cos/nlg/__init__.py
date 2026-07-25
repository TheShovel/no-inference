"""COS NLG Package — Natural Language Generation layer.

Transforms retrieved information into natural, conversational responses
using a purely symbolic multi-pass architecture.

Pipeline:
  1. cleaner   — Remove noise, pronunciation guides, truncate
  2. parser    — Extract structured Facts from raw text
  3. discourse — Build discourse tree with rhetorical relations
  4. realize   — Generate varied sentence forms per fact type
  5. fluency   — Contractions, pronouns, fillers, caps

Every public function is pure — no I/O, no network, no global state.
All functions accept and return plain Python types for easy testing.

Usage:
    from cos.nlg import naturalize, NLGConfig
    response = naturalize("What is the capital of France?", "France", info)
"""

from .pipeline import naturalize, make_conversational
from .config import NLGConfig, DEFAULT_CONFIG
from .models import Fact, Entity, DiscourseUnit, DiscourseTree, DiscourseState
from .cleaner import clean_information
from .parser import parse_facts, extract_entities
from .discourse import build_discourse_tree, flatten_tree, detect_relation
from .reference import select_reference
from .lexical import apply_contractions, vary_predicate
from .combine import combine_all, combine_by_coordination, combine_by_relative_clause
from .realize import realize_fact, classify_query, get_opening, get_closing
from .fluency import enhance_fluency, fix_caps
from .fallback import fallback_response
from .essay import generate_essay
from .util import split_sentences, lower_first, upper_first, pick, maybe

__all__ = [
    "naturalize", "make_conversational",
    "NLGConfig", "DEFAULT_CONFIG",
    "generate_essay",
    "Fact", "Entity", "DiscourseUnit", "DiscourseTree", "DiscourseState",
    "clean_information", "parse_facts", "extract_entities",
    "build_discourse_tree", "flatten_tree", "detect_relation",
    "select_reference",
    "apply_contractions", "vary_predicate",
    "combine_all", "combine_by_coordination", "combine_by_relative_clause",
    "realize_fact", "classify_query", "get_opening", "get_closing",
    "enhance_fluency", "fix_caps",
    "fallback_response",
    "split_sentences", "lower_first", "upper_first", "pick", "maybe",
]
