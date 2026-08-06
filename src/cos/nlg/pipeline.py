"""NLG Pipeline — orchestrates full naturalize pipeline.

Five-pass pipeline:
  1. Clean — Remove noise from raw information
  2. Parse — Extract structured Facts and entities
  3. Discourse — Build discourse tree with rhetorical relations
  4. Realize — Generate varied sentences per fact type
  5. Fluency — Contractions, pronouns, fillers, capitalization

Pure functions — no I/O, no side effects.
"""

import re

from .cleaner import clean_information
from .combine import combine_all
from .config import DEFAULT_CONFIG, NLGConfig
from .discourse import build_discourse_tree, flatten_tree
from .fallback import fallback_response
from .fluency import enhance_fluency
from .models import DiscourseState
from .parser import extract_entities, merge_subject_entities, parse_facts
from .realize import get_closing, get_opening, realize_fact
from .util import lower_first, maybe, pick, split_sentences, upper_first


def naturalize(
    query: str,
    topic: "str | None",
    information: str,
    intent: str = "factual",
    config: "NLGConfig | None" = None,
) -> str:
    """Generate a natural conversational response from retrieved information.

    Five-pass pipeline:
      1. Clean — Remove noise from raw information
      2. Parse — Extract structured Facts and entities
      3. Discourse — Build discourse tree with rhetorical relations
      4. Realize — Generate varied sentences per fact type
      5. Fluency — Contractions, pronouns, fillers, capitalization

    Pure function — no I/O, no side effects.

    Args:
        query: The user's original query.
        topic: The extracted topic (or None).
        information: Retrieved information text.
        intent: Query intent ('factual', 'instruction', etc.).
        config: NLG configuration. Uses defaults if None.

    Returns:
        Natural language response string.
    """
    if config is None:
        config = DEFAULT_CONFIG

    if not information or not information.strip():
        # Try knowledge base lookup as a last resort — this allows naturalize()
        # to provide answers even when called directly with empty info (e.g.,
        # in regression tests or when the caller hasn't pre-fetched information).
        try:
            from cos.knowledge import lookup as _kb_lookup
            kb_answer = _kb_lookup(query)
            if kb_answer and len(kb_answer) > 10:
                information = kb_answer
        except Exception:
            pass

    if not information or not information.strip():
        return fallback_response(query, config)

    # If the info is a code answer (fenced code block), don't run it through
    # the prose pipeline — clean/parse/realize/combine would strip parens,
    # collapse newlines, and mangle braces inside the code. The KB code
    # answers are already well-formed prose + code, so return them as-is.
    if '```' in information:
        return information.strip()

    info = clean_information(information)
    if not info:
        return fallback_response(query, config)

    effective_topic = topic or _extract_topic_from_info(info, query)
    sents = split_sentences(info)

    # ── Pass 1-2: Parse facts and extract entities ──
    facts = parse_facts(info, effective_topic)
    entity_registry = extract_entities(facts, info)  # pass source text for pronoun inference
    entity_registry = merge_subject_entities(entity_registry, effective_topic)

    # Initialize discourse state
    state = DiscourseState()
    for name, entity in entity_registry.items():
        state.register_entity(name, entity)

    # ── Pass 3: Discourse planning — preserve natural order from info
    # Don't reorder facts; use them in the order they were parsed
    tree = build_discourse_tree(facts, config)
    units = flatten_tree(tree)

    # For concise style or low verbosity, summarize to top 2-3 units for style separation
    if config.style == "concise" or config.verbosity < 0.25:
        units = units[:2]


    # ── Pass 4: Sentence realization ──
    opening = get_opening(query, config)
    realized_sentences: list[str] = []

    for i, unit in enumerate(units):
        for j, fact in enumerate(unit.facts):
            use_pronoun = (i > 0 or j > 0)
            sentence = realize_fact(fact, config, state, use_pronoun=use_pronoun)

            # Add discourse marker
            marker = unit.marker if (j == 0 and unit.marker) else ""
            if marker:
                # Capitalize the first word after the marker
                first_word = sentence.split()[0] if sentence.split() else ""
                sentence = marker + " " + upper_first(sentence)

            realized_sentences.append(sentence)
            state.sentence_count += 1
            state.mark_mentioned(j)

    # If no facts were parsed, use original sentences
    if not realized_sentences:
        realized_sentences = sents

    # ── Sentence combining (clause fusion) ──
    if len(realized_sentences) > 1:
        realized_sentences = combine_all(realized_sentences, config)

        # Light transition insertion between different-subject sentences
        realized_sentences = _insert_transitions(realized_sentences, config)

        # Post-combine cleanup:
        # 1. Fix "[Name] is She/He/It" -> "[Name] is she/he/it"
        # 2. Remove "and is" artifacts from combine
        # 3. Fix discourse markers with wrong capitalization after them
        _DISCOURSE_MARKER_WORDS = {
            'unlike', 'however', 'moreover', 'furthermore', 'additionally',
            'consequently', 'therefore', 'thus', 'hence', 'meanwhile',
            'interestingly', 'notably', 'basically', 'essentially', 'honestly',
            'actually', 'apparently', 'admittedly', 'fortunately',
            'unfortunately', 'importantly', 'specifically', 'well', 'so',
            'okay', 'alright', 'look', 'hey', 'now', 'also',
            'beyond', 'worth', 'what', 'on',
        }
        _PROPER_NOUNS = {
            'i', 'paris', 'london', 'france', 'marie', 'curie', 'new', 'york',
            'united', 'states', 'river', 'seine', 'einstein', 'eiffel',
            'olympus', 'phobos', 'deimos', 'mars', 'earth', 'jupiter',
            'saturn', 'venus', 'uranus', 'neptune', 'mercury', 'sun',
            'moon', 'brain', 'neural', 'chemistry', 'physics', 'biology',
            'mathematics', 'calculus', 'algebra', 'quantum', 'relativity',
            'albert', 'german', 'germany', 'vienna', 'bonn', 'austria',
            'beethoven', 'symphony', 'olympiad', 'principia', 'nobel',
            'prix', 'shakespeare', 'homer', 'plato',
            'aristotle', 'confucius', 'buddha', 'tesla', 'newton',
            'galileo', 'copernicus', 'kepler', 'hawking', 'feynman',
            'darwin', 'atlas', 'pacific', 'atlantic', 'indian', 'arctic',
            'amazon', 'africa', 'asia', 'europe', 'australia', 'antarctica',
            'canada', 'mexico', 'brazil', 'argentina', 'chile', 'peru',
            'andes', 'himalaya', 'alps', 'pyrenees', 'ural', 'appalachian',
        }
        for i, sent in enumerate(realized_sentences):
            # Fix pronoun capitalization after verbs
            sent = re.sub(
                r'\b(is|are|was|were|has|have)\s+(She|He|It|They|We|You)\b',
                lambda m: f"{m.group(1)} {m.group(2).lower()}",
                sent
            )
            # Fix "and is she" -> "and she" (combine artifact)
            sent = re.sub(
                r'\band\s+is\s+(she|he|it|they|this)\s+',
                lambda m: f"and {m.group(1)} ",
                sent
            )
            # Fix capitalization after filler phrases: "worth noting that You" -> "worth noting that you"
            sent = re.sub(
                r'\b(it\'s also worth noting that|it\'s worth noting that|worth noting that|it\'s also worth|worth noting)\s+(You|He|She|They|We)\b',
                lambda m: f"{m.group(1)} {m.group(2).lower()}",
                sent,
                flags=re.IGNORECASE
            )
            # Fix capitalization after multi-word transition phrases:
            # "On top of that, You" -> "On top of that, you"
            # "What's more, You" -> "What's more, you"
            # "On top of that, It" -> "On top of that, it"
            sent = re.sub(
                r'\b(on top of that|what\'s more|on top of that,|what\'s more,)\s+(You|He|She|It|They|We)\b',
                lambda m: f"{m.group(1)} {m.group(2).lower()}",
                sent,
                flags=re.IGNORECASE
            )
            # Lowercase transition words mid-sentence ("Unlike" -> "unlike")
            sent = re.sub(
                r'\b(Unlike|However|Moreover|Furthermore|Additionally|Consequently|'
                r'Therefore|Thus|Hence|Meanwhile|Interestingly|Notably|Basically|'
                r'Essentially|Honestly|Actually|Apparently|Admittedly|Fortunately|'
                r'Unfortunately|Importantly|Specifically|Notably)\b',
                lambda m: m.group(1).lower(),
                sent
            )
            # Fix capitalization after discourse markers followed by comma
            # "Well, Plants" -> "Well, plants" (but keep "Well, Albert")
            # Only lowercase after known discourse markers, not all commas,
            # to avoid lowercasing proper nouns like "Albert" after "Well, "
            def _lower_after_marker(m):
                marker = m.group(1)
                word = m.group(2)
                if word.lower() in _PROPER_NOUNS:
                    return m.group(0)
                return marker + ", " + word.lower()
            sent = re.sub(
                r'\b(' + '|'.join(_DISCOURSE_MARKER_WORDS) + r')\b,\s+([A-Z]\w+)',
                _lower_after_marker,
                sent,
                flags=re.IGNORECASE
            )
            # Also handle multi-word transition phrases: "On top of that, Plants" -> "On top of that, plants"
            _MULTI_WORD_TRANSITIONS = [
                "on top of that,", "what's more,", "beyond that,",
                "it's also worth noting that", "it's worth noting that",
                "worth noting that",
            ]
            def _lower_after_multi_word(m):
                phrase = m.group(1)
                word = m.group(2)
                if word.lower() in _PROPER_NOUNS:
                    return m.group(0)
                return phrase + " " + word.lower()
            sent = re.sub(
                r'\b(' + '|'.join(_MULTI_WORD_TRANSITIONS) + r')\s+(You|He|She|It|They|We|Plants?|The\s+|[A-Z]\w+)\b',
                _lower_after_multi_word,
                sent,
                flags=re.IGNORECASE
            )
            realized_sentences[i] = sent
    # Post-combine cleanup v2 (fix combine artifacts)
    for i, sent in enumerate(realized_sentences):
        # Only convert "and is" to ", which is" — this is safe because "is"
        # creates copular clauses where the subject carries over naturally.
        # Avoid converting "and was/has/have/had" which can attach to the
        # wrong antecedent (e.g., "conducted X, and was Y" -> "conducted X, which was Y").
        sent = re.sub(r', and is ', ', which is ', sent)
        # Keep simple "and" for active past-tense verbs ("conducted", "won", etc.)
        # But clean up "and is" before articles/determiners
        sent = re.sub(r' and is (a|an|the)', r' and is \1', sent)
        sent = re.sub(r' and is ([A-Z][a-z]+)', r', which is \1', sent)
        sent = re.sub(r', and is ([a-z])', r', and \1', sent)
        sent = re.sub(r', and it is ', " and it's ", sent)
        realized_sentences[i] = sent

    # Build response
    result = " ".join(realized_sentences)

    # Prepend opening
    if opening:
        # Avoid double "So" if opening ends with "So" and response starts with "So"
        opening_stripped = opening.rstrip().rstrip(',').rstrip()
        response_stripped = result.lstrip()
        if opening_stripped.lower().endswith('so') and response_stripped.lower().startswith('so'):
            opening = opening_stripped.rstrip('.,!?:; ') + " "
        # Also avoid when opening contains "So" and response starts with same marker
        first_word = response_stripped.split()[0].lower().rstrip(',:;') if response_stripped.split() else ''
        opening_last_word = opening_stripped.split()[-1].lower().rstrip(',:;') if opening_stripped.split() else ''
        if opening_last_word == first_word and first_word in ('so', 'well', 'okay'):
            opening = opening_stripped + " "

        first_sent = sents[0] if sents else result
        if first_sent and first_sent[0].isupper():
            result = opening + " " + result
        else:
            result = opening + " " + lower_first(result)

    # ── Pass 5: Fluency ──
    result = enhance_fluency(result, config, effective_topic, source_text=info)

    # Add closing
    closing = get_closing(config)
    if closing:
        result = result.rstrip() + " " + closing

    # Final safety: ensure the response doesn't end mid-word or mid-sentence.
    # If the text doesn't end with sentence-ending punctuation,
    # trim back to the last complete sentence boundary.
    result = _ensure_complete_sentences(result)

    return result


def make_conversational(text: str, config: "NLGConfig | None" = None) -> str:
    """Convert raw information into conversational text quickly."""
    if config is None:
        config = DEFAULT_CONFIG
    # Simple path: just apply contractions and fluency
    from .fluency import apply_contractions, fix_caps
    result = apply_contractions(text, rate=1.0, temperature=0.0)
    result = fix_caps(result)
    return result


def _extract_topic_from_info(info: str, query: str) -> str:
    """Extract a topic from the info text if not explicitly provided."""
    if not info:
        return query
    # Use first sentence of info as topic if it starts with a definition pattern
    first_line = info.split('\n')[0].strip()
    match = re.match(r'^([A-Z][^,\.]+?)\s+(?:is|are|was|were|refers to|means)\b', first_line)
    if match:
        return match.group(1).strip()
    return query


def _insert_transitions(sentences: list[str], config: NLGConfig) -> list[str]:
    """Insert light discourse transitions between different-subject sentences."""
    if len(sentences) < 2:
        return sentences

    result = [sentences[0]]
    for i in range(1, len(sentences)):
        curr = sentences[i]
        prev = result[-1]

        # Extract subjects heuristically (first noun phrase)
        prev_subj = _get_noun_phrase(prev)
        curr_subj = _get_noun_phrase(curr)

        # Skip if subjects are the same (flow is natural)
        if prev_subj and curr_subj and prev_subj.lower() == curr_subj.lower():
            result.append(curr)
            continue

        # For different subjects, occasionally insert a light transition
        if config.temperature > 0.0 and maybe(0.12):
            transition = pick([
                "Speaking of which,",
                "On a related note,",
                "In addition,",
                "What's more,",
                "",
                "",
                "",
            ], config.temperature)
            if transition:
                curr = transition + " " + curr

        result.append(curr)

    return result


def _get_noun_phrase(sentence: str) -> str:
    """Extract the likely subject/noun phrase from a sentence."""
    m = re.match(r'^([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)?)', sentence)
    if m:
        return m.group(1)
    return ""


def _ensure_complete_sentences(text: str) -> str:
    """Ensure text doesn't end mid-sentence.
    
    Adds punctuation if missing but does NOT truncate content.
    Handles code blocks by preserving them unchanged.
    """
    if not text:
        return text
    
    text = text.rstrip()
    
    # If text contains code blocks, don't modify to avoid corrupting code
    if '```' in text:
        return text
    
    # If already ending with proper punctuation, we're good
    if text.endswith(('.', '!', '?')):
        return text
    
    # Check if the text ends with a single-letter fragment (likely a truncated word)
    # In that case, find the last sentence boundary and trim there
    words = text.split()
    if words:
        last_word = words[-1].lower().rstrip('.,;:!?"\'')
        if len(last_word) == 1 and last_word not in ('i', 'a'):
            dots = [m.end() for m in re.finditer(r'\. ', text)]
            if dots:
                text = text[:dots[-1]]
            return text.strip()
    
    # Just ensure it ends with a period
    text = text.rstrip()
    if text and not text[-1] in '.!?' and not text[-1].isupper():
        text += '.'
    
    return text.strip()
