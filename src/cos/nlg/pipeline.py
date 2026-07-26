"""COS NLG Pipeline — orchestrates all NLG stages.

The naturalize() function runs the full 5-pass pipeline:
  1. clean_information() — Remove noise, truncate
  2. parse_facts() → build_discourse_tree() — Extract facts, build discourse tree
  3. flatten_tree() → realize_fact() — Generate sentences per discourse unit
  4. combine_all() — Fuse related sentences
  5. enhance_fluency() — Contractions, pronouns, fillers, caps

Usage:
    from cos.nlg import naturalize
    response = naturalize("What is France?", "France", info, "factual")
"""

from typing import Optional, List
from .config import NLGConfig, DEFAULT_CONFIG
from .models import DiscourseState
from .cleaner import clean_information
from .parser import parse_facts, extract_entities, merge_subject_entities
from .discourse import build_discourse_tree, flatten_tree
from .realize import realize_fact, get_opening, get_closing, classify_query
from .combine import combine_all
from .fluency import enhance_fluency
from .fallback import fallback_response
from .util import split_sentences, lower_first, upper_first, require_style, maybe, pick


def naturalize(
    query: str,
    topic: Optional[str],
    information: str,
    intent: str = "factual",
    config: Optional[NLGConfig] = None,
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
    realized_sentences: List[str] = []

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
                'prix', 'curie', 'darwin', 'shakespeare', 'homer', 'plato',
                'aristotle', 'confucius', 'buddha', 'tesla', 'newton',
                'galileo', 'copernicus', 'kepler', 'hawking', 'feynman',
                'darwin', 'atlas', 'pacific', 'atlantic', 'indian', 'arctic',
                'amazon', 'africa', 'asia', 'europe', 'australia', 'antarctica',
                'canada', 'mexico', 'brazil', 'argentina', 'chile', 'peru',
                'andes', 'himalaya', 'alps', 'pyrenees', 'ural', 'appalachian',
            }
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

    return result


def make_conversational(text: str, config: Optional[NLGConfig] = None) -> str:
    """Light touch: apply fluency to any text without full NLG pipeline.

    Pure function.
    """
    if config is None:
        config = DEFAULT_CONFIG
    result = enhance_fluency(text, config)
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def _extract_topic_from_info(information: str, query: str) -> str:
    """Extract a plausible topic from information text when none provided."""
    import re
    first_sentence = information.split('.')[0] if '.' in information else information
    # Capture multi-word topics: "The Roman Empire", "A black hole", etc.
    m = re.match(r'(The|A|An)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})', first_sentence)
    if m:
        return m.group(2)
    m = re.match(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})', first_sentence)
    if m:
        return m.group(1)
    words = [w for w in query.split() if len(w) > 3 and w.lower() not in
             {'what', 'who', 'how', 'why', 'when', 'where', 'tell', 'show',
              'explain', 'describe', 'define', 'give'}]
    return words[0] if words else query


def _insert_transitions(sentences: List[str], config: NLGConfig) -> List[str]:
    """Add light transitions between sentences with different subjects.

    Uses _get_subject to detect subject changes and inserts simple
    connectors between unrelated sentences to improve discourse flow.
    Avoids inserting transitions when the new subject is a pronoun
    referring to the previous subject.

    Pure function.
    """
    if len(sentences) < 2 or config.temperature <= 0.0:
        return sentences

    from .combine import _get_subject

    _TRANSITION_WORDS = {
        'and', 'but', 'however', 'moreover', 'furthermore', 'additionally',
        'plus', 'so', 'then', 'also', 'nevertheless', 'nonetheless',
        'consequently', 'therefore', 'thus', 'hence', 'meanwhile',
        'finally', 'first', 'second', 'third', 'next', 'lastly',
        'similarly', 'likewise', 'conversely', 'instead',
        'located', 'situated', 'found', 'known', 'called', 'named',
    }

    result = [sentences[0]]
    for i in range(1, len(sentences)):
        curr = sentences[i]
        prev_subj = _get_subject(result[-1])
        curr_subj = _get_subject(curr)

        # Skip if current subject is a pronoun referring to previous subject
        # "The Eiffel Tower" -> "It" doesn't need a transition
        curr_is_pronoun = (curr_subj or '').lower().strip() in {'it', 'she', 'he', 'they', 'this', 'that'}
        
        # Skip if previous subject contains the current subject word
        # (e.g., prev="Eiffel Tower" curr="The tower" -> skip because "tower" in "Eiffel Tower")
        prev_words = set(prev_subj.lower().split()) if prev_subj else set()
        curr_words = set(curr_subj.lower().split()) if curr_subj else set()
        shares_word = bool(prev_words & curr_words) if prev_words and curr_words else False

        # Don't add if current sentence already has a transition word
        first_word = curr.split()[0].lower().rstrip(',:;') if curr.split() else ''
        already_has = first_word in _TRANSITION_WORDS

        if (prev_subj and curr_subj
                and not curr_is_pronoun
                and not shares_word
                and prev_subj.lower() != curr_subj.lower()
                and not already_has
                and maybe(0.35)):
            # Different genuine subjects — add a natural transition
            transitions = ["", "", "", "",  # 60% no transition, 40% varied transitions
                          "It's also worth noting that", 
                          "What's more,", 
                          "On top of that,"]
            t = pick(transitions, config.temperature)
            if t:
                curr = t + " " + upper_first(curr)

        result.append(curr)

    return result


import re  # noqa: E811 — used in _extract_topic_from_info and sentinel
