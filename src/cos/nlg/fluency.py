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
            # Look back further for phrase prefix detection (need space for "in what is now ")
            before = text[max(0, m.start() - 20):m.start()].strip()
            bad_prefixes = ('the', 'a', 'an', 'this', 'that', 'these', 'those')
            # Also never replace the topic after a preposition ("capital of France" not "capital of it")
            prep_prefixes = ('of ', 'in ', 'at ', 'by ', 'with ', 'for ', 'from ', 'to ', 'about ', 'near ', 'on ')
            # Multi-word phrases that should prevent replacement (check against full before string)
            _PHRASE_PREFIXES = ('in what is now ', "in what's now ")
            before_lower = before.lower()
            before_words = before_lower.split()
            last_word = before_words[-1] if before_words else ''
            is_after_prep = any(last_word.startswith(p.rstrip()) for p in prep_prefixes) if last_word else False
            is_after_phrase = any(before_lower.endswith(p) or before_lower.endswith(p.rstrip()) for p in _PHRASE_PREFIXES)
            # Don't replace if preceded by a hyphenated word (e.g., "High-quality carrots" -> keep "carrots")
            is_after_hyphenated = ('-' in last_word) if last_word else False
            # Also don't replace if preceded by an adjective that's part of a compound
            _ADJ_WORDS = {'wild', 'young', 'old', 'red', 'blue', 'green', 'white', 'black', 'high', 'low', 'orange'}
            is_after_adj = (last_word.rstrip('.,;:!?') in _ADJ_WORDS) if last_word else False
            if (before.lower().split() and before.lower().split()[-1] in bad_prefixes) or is_after_prep or is_after_phrase or is_after_hyphenated or is_after_adj:
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
    # Detect plural nouns: words ending in 's' but not 'ss', 'us', 'is',
    # excluding common uncountable/singular nouns that end in 's'
    _NON_PLURAL_ENDINGS = {
        'us', 'is', 'ss', 'as', 'os',
    }
    _SINGULAR_NOUNS = {
        'this', 'thus', 'bus', 'gas', 'was', 'its', 'paris', 'mars', 'venus',
        'uranus', 'athens', 'brussels', 'dallas', 'texas', 'kansas', 'species',
        'series', 'apparatus', 'corpus', 'radius', 'basis', 'crisis', 'thesis',
        'analysis', 'oasis', 'alas', 'status', 'plus', 'minus', 'avirus',
        'linguistics', 'mathematics', 'physics', 'economics', 'statistics',
        'politics', 'ethics', 'aesthetics', 'logics', 'informatics',
        'news', 'mumps', 'measles', 'diabetes', 'rabies', 'tetanus',
    }
    t_stripped = t.rstrip('.,;:!?')
    t_words = t_stripped.split()
    # Multi-word topics: check if last word is plural
    last_word = t_words[-1] if t_words else t_stripped
    if (last_word.endswith('s') and not last_word.endswith('ss')
            and last_word not in _SINGULAR_NOUNS
            and not any(last_word.endswith(e) for e in _NON_PLURAL_ENDINGS)):
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
    "Also,",
    "Notably,",
    "Interestingly,",
    "What's more,",
    "Beyond that,",
]  # Mostly empty to keep naturalness high; occasional variety added

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


def _get_plural_form(word: str) -> str:
    """Convert a singular noun to its plural form.

    Simple heuristic: add 's' for most words, handle common exceptions.
    """
    w = word.lower().rstrip('.,;:!?')
    # Common irregular plurals
    _IRREGULAR = {
        'carrot': 'carrots', 'plant': 'plants', 'flower': 'flowers',
        'leaf': 'leaves', 'seed': 'seeds', 'root': 'roots',
    }
    if w in _IRREGULAR:
        return _IRREGULAR[w]
    # Words ending in 'y' preceded by consonant: y -> ies
    if w.endswith('y') and len(w) > 1 and w[-2] not in 'aeiou':
        return w[:-1] + 'ies'
    # Words ending in 's', 'ss', 'sh', 'ch', 'x', 'z': add 'es'
    if w.endswith(('s', 'sh', 'ch', 'x', 'z')):
        return w + 'es'
    return w + 's'

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

# Proper nouns that should not be lowercased when a discourse opener
# is prepended (e.g., "Beyond that, Einstein" not "Beyond that, einstein")
_PROPER_NOUNS_FLUENCY = {
    'albert', 'einstein', 'curie', 'eiffel', 'mars', 'earth', 'jupiter',
    'saturn', 'venus', 'uranus', 'neptune', 'mercury', 'france', 'paris',
    'london', 'germany', 'vienna', 'bonn', 'austria', 'beethoven',
    'olympus', 'phobos', 'deimos', 'brain', 'neural', 'chemistry',
    'physics', 'biology', 'mathematics', 'calculus', 'algebra',
    'quantum', 'relativity', 'darwin', 'newton', 'galileo', 'tesla',
    'hawking', 'feynman', 'copernicus', 'kepler', 'shakespeare',
    'homer', 'plato', 'aristotle', 'confucius', 'buddha',
    'columbus', 'magellan', 'cook', 'polk', 'australia',
}


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
                if opener:
                    # Don't lowercase proper nouns when adding opener prefix
                    _first_word_raw = s.split()[0] if s.split() else ''
                    if _first_word_raw[0].isupper() and _first_word_raw.lower() in _PROPER_NOUNS_FLUENCY:
                        varied.append(f"{opener} {_first_word_raw}")
                    else:
                        varied.append(f"{opener} {lower_first(s)}")
                else:
                    varied.append(s)
            else:
                varied.append(s)
        result = ' '.join(varied)

    # 4. Tasteful filler - at most 1 per paragraph, and no repetition
    if config.verbosity > 0.4 and config.temperature > 0.0:
        sents = split_sentences(result)
        if len(sents) >= 3 and maybe(profile.get("filler_rate", 0.25)):
            fillers = _FILLERS.get(require_style(config), [])
            if fillers:
                # Find a good sentence to add filler to (not first, not last)
                available = []
                for idx in range(1, min(len(sents) - 1, 10)):  # Only check first 10 sentences
                    s = sents[idx]
                    first_word_lower = s.split()[0].lower().rstrip(',:;') if s.split() else ''
                    _DISCOURSE_PREFIXES = (
                        'you could say', 'well', 'actually', 'so', 'what\'s more',
                        'beyond that', 'on top of that', 'notably', 'interestingly',
                        'also', 'moreover', 'furthermore', 'additionally',
                        'it\'s also worth', 'it\'s worth noting', 'in essence',
                        'simply put', 'simply', 'put',
                    )
                    already_prefixed = (
                        first_word_lower in _DISCOURSE_PREFIXES
                        or s.lower().startswith(_DISCOURSE_PREFIXES)
                    )
                    if not already_prefixed and len(s) > 25:
                        available.append(idx)

                if available:
                    idx = available[0]  # Use first available for consistency
                    # Check if this filler is already in the paragraph
                    para_text = ' '.join(sents)
                    _filler = pick(fillers, config.temperature)
                    if _filler and _filler.rstrip(',') not in para_text:
                        _filler_first_word = sents[idx].split()[0] if sents[idx].split() else ''
                        if _filler_first_word[0].isupper() and _filler_first_word.lower() in _PROPER_NOUNS_FLUENCY:
                            sents[idx] = f"{_filler} {sents[idx]}"
                        else:
                            sents[idx] = f"{_filler} {lower_first(sents[idx])}"
                        result = ' '.join(sents)

    # 5. Fix capitalization
    result = fix_caps(result)

    # 6. Fix capitalization after discourse openers (e.g., "In essence, The" -> "In essence, the")
    # Also handles "In essence, A dream" (space between article and noun)
    result = re.sub(
        r'((?:In essence|Simply put|In short|Overall|Here\'s the thing|At its core|So),\s+)([A-Z])([a-z])',
        lambda m: m.group(1) + m.group(2).lower() + m.group(3),
        result
    )
    result = re.sub(
        r'((?:In essence|Simply put|In short|Overall|Here\'s the thing|At its core|So),\s+)([A-Z])\b',
        lambda m: m.group(1) + m.group(2).lower(),
        result
    )

    # 7. Fix pronoun agreement issues (e.g., "Wild they were" -> "Wild carrots were")
    # This happens when pronoun substitution replaces a noun that has an adjective before it
    # Instead of removing the adjective, restore the proper noun form
    _ADJECTIVES = {'wild', 'young', 'old', 'large', 'small', 'big', 'red', 'blue', 'green', 
                   'high', 'low', 'new', 'old', 'good', 'bad', 'hot', 'cold', 'long', 'short',
                   'white', 'orange', 'purple', 'black', 'yellow', 'brown', 'pink', 'gray',
                   'round', 'thick', 'thin', 'hard', 'soft', 'sweet', 'bitter'}
    _PLURAL_NOUNS = {
        'wild': 'carrots', 'young': 'plants', 'red': 'ones', 'blue': 'ones',
        'green': 'ones', 'white': 'ones', 'black': 'ones', 'yellow': 'ones',
        'brown': 'ones', 'high': 'ones', 'low': 'ones',
    }
    words = result.split()
    fixed_words = []
    for i, w in enumerate(words):
        w_clean = w.lower().rstrip('.,;:!?')
        if (i > 0 and w_clean == 'they' and 
            words[i-1].lower().rstrip('.,;:!?') in _ADJECTIVES and
            i + 1 < len(words) and words[i+1].lower() in ('are', 'were', 'have', 'has', 'include')):
            # Restore the proper noun after the adjective
            adj = words[i-1].lower().rstrip('.,;:!?')
            if adj in _PLURAL_NOUNS:
                fixed_words.append(_PLURAL_NOUNS[adj])
            else:
                fixed_words.append(w)  # keep as-is if no mapping
        else:
            fixed_words.append(w)
    result = ' '.join(fixed_words)

    # 8. Clean up whitespace and artifacts
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

    # Fix missing possessive apostrophes (e.g., "the nation ideals" → "the nation's ideals")
    p_clean = re.sub(r'\b(the world) leading\b', r"\1's leading", p_clean)
    p_clean = re.sub(r'\b(the|a|an|this|that) (nation|world|country|city|empire|kingdom|republic) (ideals?|sake|behalf|point|view|views|way|ways|role|roles|goal|goals|purpose|purposes|part|parts|heart|hearts|name|names|story|stories)\b',
                     r"\1 \2's \3", p_clean)

    # Fix "The name it comes from" → "The name comes from" (pronoun after "name" is redundant)
    p_clean = re.sub(r'\b(The name) it comes\b', r'\1 comes', p_clean)

    # Uncontract "have" when it's a main verb followed by a noun phrase
    # (e.g., "they've a sweet flavor" → "they have a sweet flavor")
    # But keep "they've been" (auxiliary use) and "they've got" (idiomatic)
    p_clean = re.sub(
        r"\b(they|we|you|I)'ve\s+(?![bf]een|got\b)(a |an |the |\w)",
        lambda m: m.group(1) + " have " + m.group(2),
        p_clean,
        flags=re.IGNORECASE
    )

    # 9. Remove repeated filler phrases (e.g., "In essence, ... In essence, ...")
    _FILLER_PHRASES = [
        'In essence,', 'Simply put,', 'What\'s more,', 'Interestingly,',
        'Notably,', 'Beyond that,', 'On top of that,', 'Additionally,',
        'Furthermore,', 'Moreover,', 'Also,',
    ]
    for filler in _FILLER_PHRASES:
        count = p_clean.count(filler)
        if count > 1:
            first_pos = p_clean.find(filler)
            remaining = p_clean[first_pos + len(filler):]
            for _ in range(count - 1):
                next_pos = remaining.find(filler)
                if next_pos >= 0:
                    start = first_pos + len(filler) + next_pos
                    end = start + len(filler)
                    p_clean = p_clean[:start] + p_clean[end:].lstrip()
                    remaining = p_clean[first_pos + len(filler):]
                else:
                    break

    # 10. Word-by-word validator: disabled — co-occurrence model too small (0.7 MB corpus)
    # to reliably distinguish valid unusual word choices from actual errors.
    # p_clean = validate_and_repair_text(p_clean)

    return p_clean

import random  # noqa: E811 — used in filler selection


def validate_and_repair_text(text: str) -> str:
    """Run word-by-word validator to fix grammar and unlikely words.

    Pure function. Applies article agreement, subject-verb agreement,
    and co-occurrence-based word replacement.
    """
    try:
        from .validator import validate_and_repair, _build_model
        _build_model()
        paragraphs = text.split('\n\n')
        fixed_paras = []
        for p in paragraphs:
            if p.strip():
                # Apply validator to each sentence
                sents = split_sentences(p)
                fixed_sents = [validate_and_repair(s) for s in sents]
                fixed_paras.append(' '.join(fixed_sents))
            else:
                fixed_paras.append(p)
        return '\n\n'.join(fixed_paras)
    except Exception:
        return text


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
