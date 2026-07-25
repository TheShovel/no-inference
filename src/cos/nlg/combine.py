"""NLG Clause Combining — fuse related sentences into complex structures.

Transforms multiple choppy sentences into flowing prose using:
  - Relative clauses ("X, which is Y, does Z")
  - Coordination ("X and Y are both Z")
"""

import re
from typing import List, Optional, Tuple
from .config import NLGConfig
from .util import lower_first, upper_first, maybe


# ── Verbs that can follow a subject in declarative sentences ──
# Used by _get_subject to find the subject-verb boundary.
_SUBJECT_VERBS = (
    # Copular / auxiliary / modal
    'is', 'are', 'was', 'were', 'has', 'have', 'had',
    'refers', 'means', 'can', 'will', 'does', 'do', 'may', 'might',
    'shall', 'should', 'could', 'would', 'must',
    # Common transitive / intransitive verbs (base, 3sg, past, participle)
    'include', 'includes', 'included',
    'contain', 'contains', 'contained',
    'feature', 'features', 'featured',
    'require', 'requires', 'required',
    'involve', 'involves', 'involved',
    'support', 'supports', 'supported',
    'use', 'uses', 'used', 'using',
    'provide', 'provides', 'provided',
    'offer', 'offers', 'offered',
    'allow', 'allows', 'allowed',
    'produce', 'produces', 'produced',
    'create', 'creates', 'created',
    'develop', 'develops', 'developed',
    'discover', 'discovers', 'discovered',
    'invent', 'invents', 'invented',
    'design', 'designs', 'designed',
    'publish', 'publishes', 'published',
    'conduct', 'conducts', 'conducted',
    'perform', 'performs', 'performed',
    'function', 'functions', 'functioned',
    'operate', 'operates', 'operated',
    'serve', 'serves', 'served',
    'represent', 'represents', 'represented',
    'describe', 'describes', 'described',
    'connect', 'connects', 'connected',
    'combine', 'combines', 'combined',
    'convert', 'converts', 'converted',
    'prevent', 'prevents', 'prevented',
    'protect', 'protects', 'protected',
    'destroy', 'destroys', 'destroyed',
    'occur', 'occurs', 'occurred',
    'appear', 'appears', 'appeared',
    'remain', 'remains', 'remained',
    'exist', 'exists', 'existed',
    'stand', 'stands', 'stood',
    'live', 'lives', 'lived',
    'work', 'works', 'worked',
    'start', 'starts', 'started',
    'take', 'takes', 'took', 'taken',
    'make', 'makes', 'made',
    'build', 'builds', 'built',
    'become', 'becomes', 'became',
    'win', 'wins', 'won',
    'earn', 'earns', 'earned',
    'receive', 'receives', 'received',
    'found', 'founds', 'founded',
    'come', 'comes', 'came',
    'go', 'goes', 'went', 'gone',
    'grow', 'grows', 'grew',
    'call', 'calls', 'called',
    'know', 'knows', 'knew', 'known',
    'show', 'shows', 'showed', 'shown',
    'tell', 'tells', 'told',
    'say', 'says', 'said',
    'lead', 'leads', 'led',
    'result', 'results', 'resulted',
    'cause', 'causes', 'caused',
    'follow', 'follows', 'followed',
    'contribute', 'contributes', 'contributed',
    'focus', 'focuses', 'focused',
    'cover', 'covers', 'covered',
    'span', 'spans', 'spanned',
    'consist', 'consists', 'consisted',
    'compose', 'composed',
    'form', 'forms', 'formed',
    'set', 'sets',
    'run', 'runs', 'ran',
)


def _get_subject(text: str) -> Optional[str]:
    """Extract the grammatical subject of a sentence (heuristic)."""
    s = text.strip()
    if not s:
        return None
    # Remove leading discourse markers
    s = re.sub(
        r'^(Well|So|Actually|Oh|Okay|Alright|Now|Look|Hey|I mean|You know|The thing is),?\s+',
        '', s, flags=re.IGNORECASE
    )
    verbs_pattern = '|'.join(_SUBJECT_VERBS)
    m = re.match(
        r'((?:[A-Z]?\w+\s+){0,3}[A-Z]?\w+?)\s+(?:' + verbs_pattern + r')\s',
        s, re.IGNORECASE
    )
    if not m:
        return None
    candidate = m.group(1).strip()
    # Reject subjects containing punctuation (crossed phrase boundary)
    if re.search(r'[,;:()]', candidate):
        return None
    return candidate


def _get_clause_body(text: str) -> Tuple[str, str]:
    """Split a sentence into subject and the rest (verb phrase)."""
    subj = _get_subject(text)
    if not subj:
        return "", text
    rest = text[len(subj):].strip()
    return subj, rest


def _lower_clause(text: str) -> str:
    """Lowercase clause-initial words for embedding in larger sentences."""
    result = lower_first(text)
    # Lowercase clause-initial capitalized transition words
    result = re.sub(
        r'\b(Unlike|However|Moreover|Furthermore|Additionally|Consequently|'
        r'Nevertheless|Nonetheless|Therefore|Thus|Hence|Meanwhile|'
        r'Interestingly|Notably|Basically|Essentially|Honestly|Actually|Apparently|'
        r'Admittedly|Of|In|On|At|By|For|With|Without)\b',
        lambda m: m.group(1).lower() if m.group(1)[0].isupper() else m.group(1),
        result
    )
    return result


def combine_by_coordination(sentences: List[str], config: NLGConfig) -> List[str]:
    """Combine sentences with the same subject using 'and'.

    "X is Y. X is also Z." -> "X is Y and also Z."

    Pure function.
    """
    if len(sentences) < 2:
        return sentences

    result = [sentences[0]]
    for i in range(1, len(sentences)):
        prev = result[-1]
        curr = sentences[i]
        prev_subj = _get_subject(prev)
        curr_subj = _get_subject(curr)

        # Check if sentences share same subject (including pronoun reference)
        same_subj = False
        curr_body = ""  # body AFTER subject, used for combining
        if prev_subj and curr_subj:
            prev_lower = prev_subj.lower().strip()
            curr_lower = curr_subj.lower().strip()
            curr_is_pronoun = curr_lower in ('it', 'she', 'he', 'they', 'this')
            same_subj = (
                prev_lower == curr_lower or
                (curr_is_pronoun and prev_lower not in ('it', 'she', 'he', 'they'))
            )
            if same_subj:
                # Find the subject in the actual curr text (accounting for markers)
                # The _get_subject function strips markers, so we need to find
                # where the subject actually appears in curr
                curr_lower = curr.lower()
                subj_pos = curr_lower.find(curr_subj.lower())
                if subj_pos >= 0:
                    curr_body = curr[subj_pos + len(curr_subj):].strip()
                else:
                    curr_body = curr[len(curr_subj):].strip()
                curr_body = curr_body.lstrip(', ').strip()

        if same_subj and curr_body:
            # Don't chain more than 2 clauses together — avoids run-on sentences.
            # Check if the previous sentence already contains a coordinate ('and' + verb).
            _already_chained = bool(re.search(r', and [a-z]+(?:ed|s |\b)', result[-1]))
            if _already_chained:
                # Already have 2+ clauses — avoid run-on sentences.
                # At temp=0, always break the chain (deterministic quality).
                # At temp>0, rarely allow 3+ clauses.
                if config.temperature <= 0.0 or not maybe(0.10):
                    result.append(curr)
                    continue
            else:
                # First chain opportunity — combine aggressively
                # At temp=0, always combine for determinism; at temp>0, combine 70% of the time.
                if config.temperature > 0.0 and not maybe(0.7):
                    result.append(curr)
                    continue
            # Combine if the current sentence's body starts with a known verb form
            _COMBINABLE_VERBS = (
                # Copular / auxiliary
                'is ', 'are ', 'was ', 'were ', 'has ', 'have ', 'had ',
                # Past tense / participle verbs
                'conducted', 'won', 'made', 'created', 'produced',
                'became', 'received', 'earned', 'founded', 'built',
                'designed', 'published', 'discovered', 'invented',
                'developed', 'called', 'located', 'situated',
                'known', 'considered', 'composed', 'based',
                'used', 'required', 'designed', 'described',
                'connected', 'combined', 'converted', 'prevented',
                'protected', 'destroyed', 'occurred', 'appeared',
                'remained', 'followed', 'resulted', 'caused',
                'contributed', 'covered', 'spanned',
                # 3rd person singular verbs
                'includes ', 'contains ', 'features ', 'requires ',
                'involves ', 'supports ', 'uses ', 'provides ',
                'offers ', 'allows ', 'produces ', 'creates ',
                'represents ', 'describes ', 'connects ', 'combines ',
                'functions ', 'operates ', 'performs ', 'serves ',
                'occurs ', 'appears ', 'remains ', 'exists ',
                'takes ', 'makes ', 'becomes ', 'comes ', 'goes ',
                'grows ', 'leads ', 'results ', 'causes ',
                'follows ', 'focuses ', 'covers ', 'spans ',
                'consists ', 'consist ', 'consisted',
                'composed', 'formed', 'formed',
            )
            if curr_body.startswith(_COMBINABLE_VERBS):
                curr_clean = curr_body.lstrip(', ').strip()
                combined = prev.rstrip('.!?') + ", and " + _lower_clause(curr_clean)
                result[-1] = combined
                continue

        result.append(curr)

    return result


def combine_by_relative_clause(sentences: List[str], config: NLGConfig) -> List[str]:
    """Combine sentences sharing a subject using a relative clause.

    "X is Y. X is located in Z." -> "X, which is located in Z, is Y."

    Pure function.
    """
    if len(sentences) < 2:
        return sentences

    result = list(sentences)
    i = 1
    while i < len(result):
        prev_subj = _get_subject(result[i - 1])
        curr_subj = _get_subject(result[i])

        if prev_subj and curr_subj and prev_subj.lower() == curr_subj.lower():
            # Use relative clauses at temp>0 with moderate probability for richer prose
            if config.temperature > 0.0 and maybe(0.45):
                curr_body = result[i][len(curr_subj):].strip().lstrip(',').strip()
                # Use 'who' for people/animate, 'which' for things
                _PERSON_PRONOUNS = {'she', 'he', 'they', 'i', 'we', 'who', 'everyone', 'somebody'}
                _KNOWN_PEOPLE = {'marie curie', 'einstein', 'newton', 'curie', 'gustave eiffel'}
                subj_lower = curr_subj.lower().strip()
                rel_pronoun = "who" if (
                    subj_lower in _PERSON_PRONOUNS
                    or subj_lower in _KNOWN_PEOPLE
                    # Proper name (capitalized) that isn't a known place/thing
                    or (curr_subj[0].isupper() and subj_lower not in (
                        'france', 'paris', 'london', 'mars', 'earth', 'it', 'this',
                    ))
                ) else "which"
                rel_clause = f", {rel_pronoun} {_lower_clause(curr_body)}"

                if result[i - 1].endswith('.'):
                    result[i - 1] = result[i - 1][:-1] + rel_clause + "."
                    result.pop(i)
                else:
                    i += 1
            else:
                i += 1
        else:
            i += 1

    return result


def combine_all(sentences: List[str], config: NLGConfig) -> List[str]:
    """Apply all combining strategies to a list of sentences.

    Pure function.
    """
    if len(sentences) < 2:
        return sentences

    # First pass: coordination
    result = combine_by_coordination(sentences, config)
    # Second pass: relative clauses
    result = combine_by_relative_clause(result, config)
    return result
