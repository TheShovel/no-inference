"""NLG Fluency Enhancement — post-processing for natural speech patterns.

Applies contractions, pronoun substitutions, pragmatic fillers,
sentence opener variety, and capitalization cleanup.
"""

import re
from typing import List, Optional
from .config import NLGConfig, get_profile
from .models import Entity, DiscourseState, _UNCOUNTABLE_NOUNS
from .util import split_sentences, lower_first, upper_first, pick, maybe, require_style


# ── Contractions ───────────────────────────────────────────────────────────

_CONTRACTIONS = [
    (r"\bit is\b", "it's"), (r"\bthat is\b", "that's"),
    (r"\bthere is\b", "there's"), (r"\bwhat is\b", "what's"),
    (r"\bhere is\b", "here's"), (r"\bwho is\b", "who's"),
    (r"\bhow is\b", "how's"), (r"\bdo not\b", "don't"),
    (r"\bdoes not\b", "doesn't"), (r"\bdid not\b", "didn't"),
    (r"\bcannot\b", "can't"), (r"\bcan not\b", "can't"),
    (r"\bcould not\b", "couldn't"), (r"\bwould not\b", "wouldn't"),
    (r"\bshould not\b", "shouldn't"), (r"\bwill not\b", "won't"),
    (r"\bwas not\b", "wasn't"), (r"\bwere not\b", "weren't"),
    (r"\bhave not\b", "haven't"), (r"\bhas not\b", "hasn't"),
    (r"\bare not\b", "aren't"), (r"\bis not\b", "isn't"),
    (r"\byou are\b", "you're"), (r"\bwe are\b", "we're"),
    (r"\bthey are\b", "they're"), (r"\bi am\b", "I'm"),
    (r"\bi have\b", "I've"), (r"\byou have\b", "you've"),
    (r"\bwe have\b", "we've"), (r"\bthey have\b", "they've"),
    (r"\bi will\b", "I'll"), (r"\byou will\b", "you'll"),
    (r"\bwe will\b", "we'll"), (r"\bthey will\b", "they'll"),
    (r"\bthat will\b", "that'll"), (r"\blet us\b", "let's"),
]


def apply_contractions(text: str, rate: float = 1.0, temperature: float = 1.0) -> str:
    """Apply common contractions to text.

    At temperature=0.0, contractions are deterministic (rate effectively 1.0).

    Pure function.
    """
    if rate <= 0:
        return text
    # At temp=0, apply all contractions deterministically
    effective_rate = 1.0 if temperature <= 0.0 else rate
    result = text
    for pattern, replacement in _CONTRACTIONS:
        if effective_rate >= 1.0 or maybe(effective_rate):
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


# ── Pronoun substitution ───────────────────────────────────────────────────

def apply_pronouns(text: str, topic: str, config: NLGConfig) -> str:
    """Replace repeated topic mentions with appropriate pronouns.

    Detects person names, uncountable nouns, and plural nouns to
    select the correct pronoun (he/she/it/they).

    Pure function.
    """
    if not topic or not text:
        return text

    pronoun = _select_pronoun(topic)

    pattern = re.compile(r'\b' + re.escape(topic) + r'\b', re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if len(matches) < 2:
        return text

    result_parts = []
    prev_end = 0
    replaced = 0
    for m in matches:
        if replaced == 0:
            result_parts.append(text[prev_end:m.end()])
            prev_end = m.end()
            replaced += 1
        else:
            before = text[max(0, m.start() - 6):m.start()].strip()
            bad_prefixes = ('the', 'a', 'an', 'this', 'that', 'these', 'those')
            if before.lower().split() and before.lower().split()[-1] in bad_prefixes:
                result_parts.append(text[prev_end:m.end()])
            else:
                result_parts.append(text[prev_end:m.start()])
                result_parts.append(pronoun)
            prev_end = m.end()
            replaced += 1
    result_parts.append(text[prev_end:])
    return ''.join(result_parts)


# ── Pragmatic fillers ──────────────────────────────────────────────────────
def _select_pronoun(topic: str) -> str:
    """Select the correct pronoun for a topic using purely algorithmic heuristics.

    No hardcoded name lists. Uses:
      1. Uncountable noun detection
      2. Plural ending detection
      3. Person-name heuristics (capitalized multi-word names use singular they)
      4. Default to "it"

    Pure function.
    """
    t = topic.lower().strip()

    # Uncountable/abstract nouns take "it"
    if t in _UNCOUNTABLE_NOUNS or t.endswith('ing'):
        return 'it'

    # Plural (ends in 's' but not 'ss')
    if t.endswith('s') and not t.endswith('ss'):
        return 'they'

    # Person name heuristic: capitalized multi-word name
    # Without source text, use gender-neutral singular "they"
    parts = topic.split()
    if len(parts) >= 2 and all(p[0].isupper() for p in parts if p):
        # Could be a person — if we had source text we'd check pronoun usage
        # Fall back to "they" (accepted gender-neutral singular)
        return 'they'

    return 'it'


# ── Pragmatic fillers ──────────────────────────────────────────────────────

_FILLERS = {
    "friendly": [
        "I mean,", "you know,", "like,", "honestly,", "basically,",
        "actually,", "really,", "truth be told,",
    ],
    "neutral": ["in fact,", "indeed,", "essentially,", "effectively,"],
    "concise": [],
}

_OPENER_VARIETY = [
    "What's interesting is that",
    "Here's the thing:",
    "The thing about it is",
    "One thing to note is that",
    "Fun fact:",
    "Interestingly,",
    "Notably,",
    "As it turns out,",
]

# Words that indicate a sentence already has a discourse opener
_ALREADY_OPENED_WORDS = {
    'and', 'but', 'however', 'moreover', 'furthermore', 'additionally',
    'plus', 'so', 'then', 'also', 'nevertheless', 'nonetheless',
    'consequently', 'therefore', 'thus', 'hence',
}


def enhance_fluency(
    text: str,
    config: NLGConfig,
    topic: str = "",
) -> str:
    """Apply fluency enhancements: contractions, pronouns, fillers, caps.

    Pure function.
    """
    if not text or not text.strip():
        return ""

    profile = get_profile(config)

    # At temperature=0, disable all probabilistic features for determinism
    is_deterministic = config.temperature <= 0.0

    result = text

    # 1. Apply pronouns (before contractions so "it is" -> "it's")
    if topic:
        result = apply_pronouns(result, topic, config)

    # 2. Apply contractions (pass temperature for determinism at temp=0)
    result = apply_contractions(result, rate=profile.get("contraction_rate", 0.8), temperature=config.temperature)

    # 3. Vary sentence openers (skip first sentence)
    sents = split_sentences(result)
    if len(sents) > 1 and config.temperature > 0.0:
        varied = [sents[0]]
        for s in sents[1:]:
            first_word = s.split()[0].lower().rstrip(',:;') if s.split() else ''
            already_opened = first_word in _ALREADY_OPENED_WORDS or any(
                s.startswith(m) for m in ['And get', 'Plus,', 'Not only', 'So basically']
            )
            if len(s) > 25 and not already_opened and maybe(profile.get("opener_variety_rate", 0.2)):
                opener = pick(_OPENER_VARIETY, config.temperature)
                varied.append(f"{opener} {lower_first(s)}")
            else:
                varied.append(s)
        result = ' '.join(varied)

    # 4. Tasteful filler (one, in the middle)
    if config.verbosity > 0.4 and config.temperature > 0.0:
        sents = split_sentences(result)
        if len(sents) >= 3 and maybe(profile.get("filler_rate", 0.25)):
            fillers = _FILLERS.get(require_style(config), [])
            if fillers:
                idx = random.randint(1, len(sents) - 1)
                sents[idx] = f"{pick(fillers, config.temperature)} {lower_first(sents[idx])}"
                result = ' '.join(sents)

    # 5. Fix capitalization
    result = fix_caps(result)

    # 6. Clean up whitespace and double punctuation
    result = re.sub(r'\s+', ' ', result).strip()
    result = re.sub(r'\.\.+', '.', result)
    result = re.sub(r'\s+\.', '.', result)
    result = re.sub(r'\s+,', ',', result)
    
    # 7. Remove doubled words ("So so", "and and", "the the")
    result = re.sub(r'\b(\w+)\s+\1\b', lambda m: m.group(1), result, flags=re.IGNORECASE)
    # Also handle "So So" with different cases
    result = re.sub(r'\b([Ss]o)\s+[Ss]o\b', r'\1', result)

    return result

import random  # noqa: E811 — used in filler selection


def fix_caps(text: str) -> str:
    """Ensure each sentence starts with an uppercase letter.

    Pure function.
    """
    sents = split_sentences(text)
    fixed = []
    for s in sents:
        s = s.strip()
        if s and len(s) > 1 and s[0].isalpha() and s[0].islower():
            s = upper_first(s)
        fixed.append(s)
    return ' '.join(fixed)
