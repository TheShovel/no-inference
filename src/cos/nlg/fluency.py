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


# Words that should stay uppercase mid-sentence
_PROPER_NOUNS = {
    'I', 'Paris', 'London', 'France', 'Mars', 'Earth', 'Sun', 'Moon',
    'Einstein', 'Newton', 'Curie', 'Eiffel', 'Olympus', 'Phobos', 'Deimos',
    'Louvre', 'Rayleigh', 'English', 'French', 'European',
}


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

def apply_pronouns(text: str, topic: str, config: NLGConfig, source_text: str = "") -> str:
    """Replace repeated topic mentions with appropriate pronouns.

    Uses the same algorithmic pronoun inference as the rest of the system
    (from cos.nlg.models._infer_gender_from_text) when source text is available.
    Falls back to heuristics (uncountable, plural, person-name, default it).

    Pure function.
    """
    if not topic or not text:
        return text

    # Try to infer pronoun from source text (same algorithm everywhere)
    pronoun = None
    if source_text:
        try:
            from .models import _infer_gender_from_text
            gender = _infer_gender_from_text(topic, source_text)
            if gender == "feminine":
                pronoun = "she"
            elif gender == "masculine":
                pronoun = "he"
        except Exception:
            pass

    if not pronoun:
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
            before = text[max(0, m.start() - 12):m.start()].strip()
            bad_prefixes = ('the', 'a', 'an', 'this', 'that', 'these', 'those')
            # Also never replace the topic after a preposition ("capital of France" not "capital of it")
            prep_prefixes = ('of ', 'in ', 'at ', 'by ', 'with ', 'for ', 'from ', 'to ', 'about ', 'near ', 'on ')
            before_words = before.lower().split()
            last_word = before_words[-1] if before_words else ''
            is_after_prep = any(last_word.startswith(p.rstrip()) for p in prep_prefixes) if last_word else False
            if (before.lower().split() and before.lower().split()[-1] in bad_prefixes) or is_after_prep:
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
    """Select the correct pronoun for a topic using algorithmic heuristics.

    Pure function.
    """
    t = topic.lower().strip()
    if " and " in t or " & " in t:
        return 'they'
    parts = topic.split()
    if len(parts) >= 2 and all(p[0].isupper() for p in parts if p):
        place_indicators = {'reef', 'island', 'river', 'mountain', 'lake', 'ocean', 'sea',
                            'bay', 'gulf', 'forest', 'desert', 'valley', 'plain', 'park',
                            'city', 'town', 'state', 'country', 'continent', 'planet',
                            'star', 'galaxy', 'nebula', 'asteroid', 'comet', 'rainforest',
                            'system', 'war', 'tower', 'ii', 'iii', 'iv', 'v', 'vi', 'vii'}
        last_word = parts[-1].lower().strip('.,;:!?')
        if last_word not in place_indicators:
            return 'they'
    return 'it'


# ── Pragmatic fillers ──────────────────────────────────────────────────────

_FILLERS = {
    "friendly": [
        "What's more,", "On top of that,",
        "It's also worth noting that", "Beyond that,",
    ],
    "neutral": ["Additionally,", "Furthermore,", "It's worth noting that"],
    "concise": [],
}

_OPENER_VARIETY = [
    "",
    "",
    "",
    "",
    "",
]

# Sentence-level transition injectors — added between sentences for flow
_TRANSITIONS = {
    "friendly": [
        "Beyond that,", "On top of that,", "What's more,",
        "Additionally,", "It's also worth noting that",
    ],
    "neutral": ["Additionally,", "Furthermore,", "Moreover,"],
    "concise": [],
}

# Words that indicate a sentence already has a discourse opener
_ALREADY_OPENED_WORDS = {
    'and', 'but', 'however', 'moreover', 'furthermore', 'additionally',
    'plus', 'so', 'then', 'also', 'nevertheless', 'nonetheless',
    'consequently', 'therefore', 'thus', 'hence',
}

# Words that indicate a sentence already has a discourse marker,
# even when followed by a comma (e.g. "Notably, Paris...")
_ALREADY_OPENED_PREFIXES = [
    'Plus,', 'Not only', 'So basically', 'And get',
    'Also,', 'Notably,', 'Interestingly,', 'In addition,',
    'Furthermore,', 'Moreover,', 'Additionally,', 'What\'s more,',
    'However,', 'That said,', 'In short,', 'Overall,',
    'For example,', 'For instance,', 'Similarly,',
    'First,', 'Then,', 'Next,', 'After that,', 'Finally,',
    'Because of that,', 'As a result,', 'Consequently,',
    'Worth mentioning,', 'Beyond that,', 'On top of that,',
    'It\'s also worth', 'It\'s worth noting',
]


def enhance_fluency(
    text: str,
    config: NLGConfig,
    topic: str = "",
    source_text: str = "",
) -> str:
    """Apply fluency enhancements: contractions, pronouns, fillers, caps.

    Pure function.
    """
    if not text or not text.strip():
        return ""

    paragraphs = text.split('\n\n')
    enhanced_paras = []

    for p in paragraphs:
        if not p.strip():
            continue
        p_res = _enhance_single_paragraph(p.strip(), config, topic, source_text)
        enhanced_paras.append(p_res)

    return '\n\n'.join(enhanced_paras).strip()


def _enhance_single_paragraph(
    text: str,
    config: NLGConfig,
    topic: str = "",
    source_text: str = "",
) -> str:
    profile = get_profile(config)
    result = text

    # 1. Apply pronouns
    if topic:
        result = apply_pronouns(result, topic, config, source_text=source_text)

    # 2. Apply contractions
    result = apply_contractions(result, rate=profile.get("contraction_rate", 0.8), temperature=config.temperature)

    # 3. Vary sentence openers (skip first sentence)
    sents = split_sentences(result)
    if len(sents) > 1 and config.temperature > 0.0:
        varied = [sents[0]]
        for s in sents[1:]:
            first_word = s.split()[0].lower().rstrip(',:;') if s.split() else ''
            already_opened = first_word in _ALREADY_OPENED_WORDS or any(
                s.startswith(m) for m in _ALREADY_OPENED_PREFIXES
            )
            if len(s) > 25 and not already_opened and maybe(profile.get("opener_variety_rate", 0.08)):
                opener = pick(_OPENER_VARIETY, config.temperature)
                varied.append(f"{opener} {lower_first(s)}")
            else:
                varied.append(s)
        result = ' '.join(varied)

    # 4. Tasteful filler
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

    # 6. Clean up whitespace and artifacts
    p_clean = re.sub(r'[ \t]+', ' ', result).strip()
    p_clean = re.sub(r'\.\.+', '.', p_clean)
    p_clean = re.sub(r'\s+\.', '.', p_clean)
    p_clean = re.sub(r'\s+,', ',', p_clean)
    p_clean = re.sub(r'\bit is it\b', 'it is', p_clean, flags=re.IGNORECASE)
    p_clean = re.sub(r'\bis she she\b', 'is she', p_clean, flags=re.IGNORECASE)
    p_clean = re.sub(r'\band is she\b', 'and she', p_clean, flags=re.IGNORECASE)
    p_clean = re.sub(r'\bunlike unlike\b', 'unlike', p_clean, flags=re.IGNORECASE)
    p_clean = re.sub(r'\b(\w+)\s+\1\b', r'\1', p_clean, flags=re.IGNORECASE)
    p_clean = re.sub(r'\b([Ss]o)\s+[Ss]o\b', r'\1', p_clean)

    return p_clean

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
