"""NLG Clause Combining — fuse related sentences into complex structures.

Transforms multiple choppy sentences into flowing prose using:
  - Relative clauses ("X, which is Y, does Z")
  - Coordination ("X and Y are both Z")
"""

import re
from typing import List, Optional, Tuple
from .config import NLGConfig
from .util import lower_first, upper_first, maybe


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
    m = re.match(
        r'((?:[A-Z]?\w+\s+){0,3}[A-Z]?\w+?)\s+(?:is|are|was|were|has|have|had|refers|means|can|will|does|do|may|might)\s',
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
            # Add rate-limiting: only combine occasionally to avoid "which is" overuse
            # At temp=0, always combine for determinism
            if config.temperature > 0.0 and not maybe(0.25):
                result.append(curr)
                continue
            # Only combine if the current sentence's body starts with a verb
            # (is/are/was/were/has/have)
            if curr_body.startswith(('is ', 'are ', 'was ', 'were ', 'has ', 'have ')):
                curr_clean = curr_body.lstrip(', ').strip()
                combined = prev.rstrip('.!?') + ", and " + _lower_clause(curr_clean)
                result[-1] = combined
                continue
            elif curr_body.startswith(('conducted', 'won', 'made', 'created', 'produced')):
                # Action verbs can also be combined
                combined = prev.rstrip('.!?') + ", and " + _lower_clause(curr_body)
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
            # Only use relative clauses at temp>0 and with low probability
            if config.temperature > 0.0 and maybe(0.15):
                curr_body = result[i][len(curr_subj):].strip().lstrip(',').strip()
                rel_clause = f", which {_lower_clause(curr_body)}"

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
