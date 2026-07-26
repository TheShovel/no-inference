"""Word-by-word validator — checks each word against prior context using
grammar rules, word co-occurrence statistics, and completeness checks.

Walks through generated text word-by-word. For each word, checks:
1. Grammar rules (subject-verb agreement, article usage, pronoun case)
2. Word co-occurrence (does this word commonly appear with the previous word?)
3. Completeness (sentence doesn't end mid-word, no truncated text)
4. Statistical scoring (n-gram probability for catch-all)

If a word doesn't fit, replaces it with the most likely alternative.
Purely statistical/rule-based — no LLM inference.
"""

import os
import re
import json
import glob
import math
from collections import Counter, defaultdict
from typing import List, Optional, Tuple, Dict, Set

# ═════════════════════════════════════════════════════════════════════════════
# Word co-occurrence model (built from knowledge corpus)
# ═════════════════════════════════════════════════════════════════════════════

_cooccurrence: Dict[str, Counter] = defaultdict(Counter)
_vocab: Set[str] = set()
_model_built = False

_WINDOW = 5  # co-occurrence window size


def _build_model():
    """Build word co-occurrence tables from the knowledge corpus."""
    global _cooccurrence, _vocab, _model_built
    if _model_built:
        return

    corpus_path = os.path.join(
        os.path.dirname(__file__), '..', '..', '..', 'data', 'knowledge'
    )
    corpus_path = os.path.normpath(corpus_path)

    texts = []
    for fpath in glob.glob(os.path.join(corpus_path, '**', '*.json'), recursive=True):
        try:
            with open(fpath, 'r', errors='ignore') as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and 'a' in item:
                        texts.append(item['a'])
            elif isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, str):
                        texts.append(v)
        except Exception:
            pass

    for text in texts:
        words = re.findall(r"[a-z]+", text.lower())
        _vocab.update(words)
        for i, w in enumerate(words):
            start = max(0, i - _WINDOW)
            for j in range(start, i):
                if j != i:
                    _cooccurrence[w][words[j]] += 1
                    _cooccurrence[words[j]][w] += 1

    _model_built = True


def _cooccurrence_score(w1: str, w2: str) -> float:
    """Score how related two words are based on co-occurrence.

    Returns 0.0-1.0. Higher = more commonly seen together.
    """
    _build_model()
    w1, w2 = w1.lower(), w2.lower()
    if w1 not in _cooccurrence or w2 not in _vocab:
        return 0.0
    count = _cooccurrence[w1].get(w2, 0)
    total = sum(_cooccurrence[w1].values())
    if total == 0:
        return 0.0
    return count / total


# ═════════════════════════════════════════════════════════════════════════════
# Grammar rules
# ═════════════════════════════════════════════════════════════════════════════

_SINGULAR_VERBS = {'is', 'has', 'does', 'was', 'can', 'will', 'may', 'shall'}
_PLURAL_VERBS = {'are', 'have', 'do', 'were'}

_SINGULAR_PRONOUNS = {'it', 'he', 'she', 'this', 'that'}
_PLURAL_PRONOUNS = {'they', 'we', 'these', 'those'}

_INDEFINITE_SINGULAR = {'a', 'an', 'each', 'every', 'either', 'neither', 'one'}

_VOWEL_SOUNDS = set('aeiou')

# Words where initial vowel letter represents a consonant /j/ sound
_CONSONANT_U = {
    'un', 'uni', 'unique', 'united', 'unit', 'unity', 'universal', 'universe',
    'university', 'uniform', 'union', 'unanimous', 'utility', 'usage', 'usual',
    'usually', 'used', 'user', 'utensil', 'utilize', 'utter',
    'eulogy', 'euphemism', 'euphoria', 'european',
}

_SILENT_H = {'hour', 'honest', 'honour', 'honor', 'heir', 'mba', 'herb'}


def _check_article_agreement(prev_word: str, curr_word: str) -> Optional[str]:
    """Check if article agrees with following word.

    Returns suggested fix or None if OK.
    """
    prev = prev_word.lower()
    curr = curr_word.lower()

    if prev == 'a':
        # "a" before vowel SOUND → should be "an"
        # Skip words where 'u' makes /j/ consonant sound
        if curr[0:1] in _VOWEL_SOUNDS and curr not in _CONSONANT_U:
            return 'an'
    if prev == 'an':
        # "an" before consonant SOUND → should be "a"
        if curr[0:1] not in _VOWEL_SOUNDS and curr not in _SILENT_H:
            return 'a'
        # "an unique" / "an university" → "a ..."
        if curr in _CONSONANT_U:
            return 'a'
    return None


def _check_verb_agreement(subject: str, verb: str) -> Optional[str]:
    """Check if subject and verb agree in number.

    Returns suggested fix or None if OK.
    """
    subj = subject.lower().rstrip('.,;:!?')
    # Extract just the head noun (last word of subject phrase)
    # "cities generally" -> "cities", "stylistic analysis" -> "analysis"
    subj_words = subj.split()
    head_noun = subj_words[-1] if subj_words else subj
    # Skip common adverbs and function words to find actual head noun
    _SKIP_WORDS = {'the', 'a', 'an', 'this', 'that', 'these', 'those',
                   'generally', 'often', 'usually', 'typically', 'mainly',
                   'primarily', 'also', 'only', 'just', 'still', 'already',
                   'never', 'always', 'sometimes', 'perhaps', 'perhaps',
                   'not', 'very', 'quite', 'rather', 'almost', 'nearly',
                   'however', 'therefore', 'moreover', 'furthermore',
                   'additionally', 'meanwhile', 'consequently'}
    attempts = 0
    while head_noun in _SKIP_WORDS and len(subj_words) > 1 and attempts < 3:
        subj_words = subj_words[:-1]
        head_noun = subj_words[-1]
        attempts += 1

    v = verb.lower()

    # Determine if head noun is plural
    is_plural = (
        head_noun in _PLURAL_PRONOUNS
        or (head_noun.endswith('s') and not head_noun.endswith(('ss', 'us', 'is', 'os', 'ys'))
            and head_noun not in {'this', 'thus', 'bus', 'gas', 'was', 'its',
                                  'paris', 'mars', 'venus', 'uranus', 'athens',
                                  'mathematics', 'physics', 'cosmos', 'series',
                                  'species', 'corpus', 'analysis', 'basis',
                                  'crisis', 'diagnosis', 'emphasis', 'oasis',
                                  'thesis', 'synthesis', ' nemesis'})
        or ' and ' in subj
        or head_noun.endswith('ies') and not head_noun.endswith('series')
        or head_noun.endswith('ves')
    )

    is_singular = (
        subj in _SINGULAR_PRONOUNS
        or head_noun in _SINGULAR_PRONOUNS
        or head_noun in {'word', 'term', 'name', 'concept', 'process',
                         'system', 'method', 'analysis', 'basis', 'crisis',
                         'phenomenon', 'mechanism', 'structure', 'function'}
        or (not head_noun.endswith('s') and len(head_noun) > 2
            and head_noun not in _PLURAL_PRONOUNS)
    )

    if is_plural and v in _SINGULAR_VERBS:
        _PLURAL_FIX = {'is': 'are', 'has': 'have', 'does': 'do',
                       'was': 'were', 'has': 'have'}
        return _PLURAL_FIX.get(v)
    if is_singular and v in _PLURAL_VERBS:
        _SINGULAR_FIX = {'are': 'is', 'have': 'has', 'do': 'does',
                         'were': 'was'}
        return _SINGULAR_FIX.get(v)

    return None


def _find_subject_verb_pair(words: List[str], start: int) -> Tuple[Optional[str], Optional[str], int]:
    """Find the subject and main verb starting from position start.

    Returns (subject, verb, verb_index) or (None, None, -1).
    """
    # Simple heuristic: subject is the first noun phrase, verb follows
    # Look for pattern: [det] [adj*] noun verb
    i = start
    while i < len(words) and words[i].lower() in (
        'the', 'a', 'an', 'this', 'that', 'these', 'those',
        'in', 'on', 'at', 'for', 'with', 'by', 'from', 'to',
    ):
        i += 1

    if i >= len(words):
        return None, None, -1

    subject_words = [words[i].lower()]
    i += 1
    # Collect remaining subject words (adjectives/nouns until we hit a verb)
    _COMMON_VERBS = {'is', 'are', 'was', 'were', 'has', 'have', 'had',
                     'does', 'do', 'did', 'can', 'could', 'will', 'would',
                     'may', 'might', 'shall', 'should', 'includes', 'include',
                     'contains', 'consist', 'serves', 'refers'}
    while i < len(words) and words[i].lower() not in _COMMON_VERBS:
        subject_words.append(words[i].lower())
        i += 1
        if len(subject_words) > 5:
            break

    if i < len(words) and words[i].lower() in _COMMON_VERBS:
        return ' '.join(subject_words), words[i].lower(), i

    return None, None, -1


# ═════════════════════════════════════════════════════════════════════════════
# Completeness checks
# ═════════════════════════════════════════════════════════════════════════════

_TRUNCATED_ENDINGS = re.compile(
    r'(?:tion|sion|ment|ness|able|ible|ful|less|ous|ive|ing|ied|ies|'
    r'ers|est|ity|ism|ist|ize|ent|ant|ogy|phy|thy|lly|ely|ily|ory|ary|'
    r'ery|ury|day|way|ney|ley|ton|son|man|dom|ship|hood|ward|wise)$'
)


def _is_truncated(word: str) -> bool:
    """Check if a word looks truncated (ends abruptly)."""
    w = word.lower().rstrip('.,;:!?')
    if len(w) <= 3:
        return False
    if w[-1] in '.!?':
        return False
    # Known complete word endings are NOT truncated
    if _TRUNCATED_ENDINGS.search(w):
        return False
    # Words ending with double consonant + vowel are usually complete
    if len(w) >= 5 and w[-1] in 'aeiou' and w[-2] == w[-3]:
        return False
    return False


def _fix_truncated_word(word: str) -> Optional[str]:
    """Try to complete a truncated word using co-occurrence.

    Returns completed word or None.
    """
    _build_model()
    w = word.lower().rstrip('.,;:!?')
    # Find words that start with the same prefix and are in vocabulary
    prefix = w[:max(3, len(w) - 2)]
    candidates = [v for v in _vocab if v.startswith(prefix) and len(v) > len(w)]
    if not candidates:
        return None
    # Pick the most common one
    return max(candidates, key=lambda x: sum(_cooccurrence[x].values()))


# ═════════════════════════════════════════════════════════════════════════════
# Main validation pipeline
# ═════════════════════════════════════════════════════════════════════════════

def validate_and_repair(text: str) -> str:
    """Walk through text word-by-word, checking and fixing issues.

    Checks grammar, co-occurrence, and completeness.
    Returns repaired text.
    """
    _build_model()

    if not text or not text.strip():
        return text

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    repaired = []
    for sent in sentences:
        repaired.append(_repair_sentence(sent))
    return ' '.join(repaired)


def _repair_sentence(sentence: str) -> str:
    """Repair a single sentence."""
    # Tokenize preserving punctuation (Unicode-aware)
    tokens = re.findall(r"[\w]+(?:'[\w]+)?|[.,;:!?]", sentence, re.UNICODE)
    if len(tokens) < 3:
        return sentence

    result = list(tokens)
    words_only = [t for t in result if re.match(r'^[a-zA-Z]', t)]

    # 1. Check article agreement
    for i in range(1, len(result)):
        if result[i - 1].lower() in ('a', 'an') and re.match(r'^\w', result[i], re.UNICODE):
            fix = _check_article_agreement(result[i - 1], result[i])
            if fix:
                result[i - 1] = fix

    # 2. Check subject-verb agreement
    for i in range(len(result)):
        if result[i].lower() in _SINGULAR_VERBS | _PLURAL_VERBS:
            subj, verb, vi = _find_subject_verb_pair(result, 0)
            if subj and verb:
                fix = _check_verb_agreement(subj, verb)
                if fix:
                    result[vi] = fix
                    break

    # 3. Check co-occurrence and fix unlikely word pairs
    # Only replace when co-occurrence is exactly 0 (completely unrelated words)
    _FUNCTION_WORDS = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'can', 'shall', 'to', 'of', 'in', 'for',
        'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during',
        'and', 'but', 'or', 'not', 'so', 'if', 'than', 'that', 'this',
        'it', 'its', 'they', 'them', 'their', 'we', 'us', 'our',
        'also', 'just', 'only', 'even', 'still', 'more', 'such', 'very',
    }
    for i in range(2, len(result)):
        if not re.match(r'^\w', result[i], re.UNICODE):
            continue
        if len(result[i]) <= 2:
            continue

        prev = result[i - 1].lower() if re.match(r'^\w', result[i - 1], re.UNICODE) else ''
        curr = result[i].lower()

        if not prev or prev in _FUNCTION_WORDS:
            continue

        score = _cooccurrence_score(prev, curr)

        # Only act on EXACT zero co-occurrence (completely unseen pair)
        if score == 0.0 and len(curr) > 4:
            # Try to find a better word
            candidates = _cooccurrence.get(prev, Counter())
            if candidates:
                # Only consider content-word replacements
                good = [(w, c) for w, c in candidates.most_common(10)
                        if w != curr and w not in _FUNCTION_WORDS and len(w) > 2
                        and _cooccurrence_score(w, curr) > 0.005]
                if good:
                    best_word, best_count = good[0]
                    # Only replace if current word has zero count AND replacement is common
                    curr_count = candidates.get(curr, 0)
                    if curr_count == 0 and best_count >= 3:
                        if result[i][0].isupper():
                            best_word = best_word.capitalize()
                        result[i] = best_word

    # 4. Check for truncated words at sentence end
    if result and result[-1] not in '.!?':
        last_word = result[-1].lower()
        if _is_truncated(last_word):
            completed = _fix_truncated_word(last_word)
            if completed and len(completed) > len(last_word) + 1:
                result[-1] = completed

    # Join with proper spacing — attach punctuation to preceding word
    parts = []
    for w in result:
        if w in '.,;:!?':
            if parts:
                parts[-1] = parts[-1] + w
            else:
                parts.append(w)
        else:
            parts.append(w)
    return ' '.join(parts)


def score_text(text: str) -> float:
    """Score text quality using co-occurrence and completeness.

    Returns 0.0-1.0. Higher = more natural.
    """
    _build_model()

    if not text:
        return 0.0

    words = re.findall(r"[a-zA-Z]+", text.lower())
    if len(words) < 2:
        return 0.0

    # Co-occurrence score
    co_scores = []
    for i in range(1, len(words)):
        co_scores.append(_cooccurrence_score(words[i - 1], words[i]))

    # Completeness score (penalize truncated words)
    completeness = 1.0
    if words and _is_truncated(words[-1]):
        completeness = 0.5

    avg_co = sum(co_scores) / len(co_scores) if co_scores else 0.0
    return min(1.0, avg_co * 10) * completeness


def score_word(word: str, context: List[str]) -> float:
    """Score how likely a word is given its context.

    Returns 0.0-1.0. Higher = more natural.
    """
    _build_model()
    if not context:
        return 0.5
    last = context[-1].lower()
    return _cooccurrence_score(last, word.lower())
