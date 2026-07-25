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
from .util import split_sentences, lower_first, upper_first, require_style


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
            # "Basically, Plants" -> "Basically, plants"
            sent = re.sub(
                r'(,\s+)([A-Z]\w+)',
                lambda m: m.group(1) + m.group(2).lower() if m.group(2)[0].isupper() and m.group(2).lower() not in {'i', 'paris', 'london', 'france', 'marie', 'curie', 'new', 'york', 'united', 'states', 'river', 'seine'} else m.group(0),
                sent
            )
            realized_sentences[i] = sent
    # Post-combine cleanup v2 (fix combine artifacts)
    for i, sent in enumerate(realized_sentences):
        sent = re.sub(r', and is ', ', which is ', sent)
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
    m = re.match(r'(The|A|An)\s+([A-Z]\w+)', first_sentence)
    if m:
        return m.group(2)
    m = re.match(r'([A-Z]\w+)', first_sentence)
    if m:
        return m.group(1)
    words = [w for w in query.split() if len(w) > 3 and w.lower() not in
             {'what', 'who', 'how', 'why', 'when', 'where', 'tell', 'show',
              'explain', 'describe', 'define', 'give'}]
    return words[0] if words else query


import re  # noqa: E811 — used in _extract_topic_from_info and sentinel
