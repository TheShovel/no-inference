"""
COS Sentence Constructor — Learns sentence patterns from knowledge base text.

Instead of hand-crafted templates in realize.py, this module extracts sentence
patterns from the curated knowledge base entries and uses them to construct
natural sentences for any fact type.

Architecture:
  1. TRAIN: Parse KB text into generalized sentence patterns
  2. GENERATE: Match patterns to facts and fill slots

Each pattern is a tuple of (template_str, fact_type, key_verb, slot_map)
where template_str contains {subject}, {verb}, {obj} placeholders.
"""

import re
import json
import random
from typing import List, Optional, Tuple, Dict
from pathlib import Path


# ── Pattern data structures ──────────────────────────────────────────────────

# A pattern is: (template, fact_type, verb_original, style)
# template has {subject}, {obj} placeholders
Pattern = Tuple[str, str, str, str]


# ── Pattern Extraction ───────────────────────────────────────────────────────

_TOPIC_WORDS = {'the', 'a', 'an', 'this', 'that', 'these', 'those'}


def _normalize_topic(text: str) -> str:
    """Strip leading articles from a topic string."""
    for art in ['the ', 'a ', 'an ']:
        if text.lower().startswith(art):
            return text[len(art):].strip()
    return text.strip()


def _extract_patterns_from_text(text: str, source_topic: str = "") -> List[Pattern]:
    """Extract sentence patterns from a paragraph of text.

    Uses _get_subject to find the subject, then extracts the verb phrase
    and generalizes it by replacing known objects with {obj}.
    """
    from .combine import _get_subject
    
    patterns = []
    topic = _normalize_topic(source_topic) if source_topic else ""
    
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    
    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 15:
            continue
        
        subj = _get_subject(sent)
        if not subj:
            continue
        
        # Extract verb phrase (everything after the subject)
        subj_pos = sent.lower().find(subj.lower())
        if subj_pos < 0:
            continue
        verb_phrase = sent[subj_pos + len(subj):].strip()
        if len(verb_phrase) < 5:
            continue
        
        # Determine verb and fact_type
        first_word = verb_phrase.split()[0].lower().rstrip(',;') if verb_phrase.split() else ''
        fact_type = _classify_sentence(verb_phrase, topic.lower())
        style = _classify_style(sent)
        
        # Generalize: replace topic reference in verb phrase with {obj}
        # The topic might appear as the last noun phrase in the complement
        vp_generalized = _generalize_verb_phrase(verb_phrase, topic, fact_type)
        
        template = "{subject} " + vp_generalized
        patterns.append((template, fact_type, first_word, style))
    
    return patterns


def _generalize_verb_phrase(vp: str, topic: str, fact_type: str) -> str:
    """Replace the most likely 'object' in a verb phrase with {obj}.
    
    For definition: "is the capital of France" → "is the capital of {obj}"
    For property: "has a population of 2 million" → "has {obj}"
    For location: "is located in Paris" → "is located {obj}"
    """
    vp_lower = vp.lower()
    
    # If topic appears at the end of the vp, replace it
    if topic and topic.lower() in vp_lower:
        idx = vp_lower.rfind(topic.lower())
        if idx >= 0:
            return vp[:idx] + '{obj}' + vp[idx + len(topic):]
    
    # For specific fact_types, use targeted patterns
    if fact_type == 'definition':
        # Replace the complement after "is a/an/the X"
        m = re.search(r'(is|are|was|were)\s+(a|an|the)\s+(.+)', vp, re.IGNORECASE)
        if m:
            article = m.group(2)
            return m.group(1) + ' ' + article + ' {obj}'
    
    elif fact_type == 'location':
        # Replace the location after "located in/at/on X"
        m = re.search(r'(located|situated|found|sits|lies)\s+(in|on|at|near)\s+(.+)', vp, re.IGNORECASE)
        if m:
            return m.group(1) + ' ' + m.group(2) + ' {obj}'
    
    elif fact_type == 'property':
        # For "has X" or "includes X", replace the object
        for verb in ['has ', 'have ', 'includes ', 'contains ', 'features ']:
            if verb in vp_lower:
                idx = vp_lower.find(verb)
                after_verb = vp[idx + len(verb):].strip().rstrip('.,!?')
                if after_verb and not any(p in after_verb for p in ['{', '}']):
                    return vp[:idx] + verb + '{obj}'
    
    elif fact_type == 'composition':
        # Replace "made of X" or "consists of X"
        m = re.search(r'(made|composed|consists?)\s+(of|from|with|using)\s+(.+)', vp, re.IGNORECASE)
        if m:
            return m.group(1) + ' ' + m.group(2) + ' {obj}'
    
    elif fact_type == 'purpose':
        # Replace "used for X" or "serves as X"
        m = re.search(r'(used|serves|functions)\s+(for|as|to)\s+(.+)', vp, re.IGNORECASE)
        if m:
            return m.group(1) + ' ' + m.group(2) + ' {obj}'
    
    # If no specific pattern matches, keep the full verb phrase but
    # replace the last noun-like word with {obj} as a best guess
    words = vp.split()
    if len(words) >= 3:
        # Replace the last word that looks like a proper noun or long noun
        for j in range(len(words) - 1, 0, -1):
            w = words[j].strip('.,!?;:')
            if len(w) > 3 and w[0].isupper():
                words[j] = '{obj}'
                break
        vp = ' '.join(words)
    
    return vp


def _classify_sentence(sent: str, topic_lower: str) -> str:
    """Classify a sentence into a fact type based on its content."""
    s = sent.lower()
    
    # How-to / instructional
    if any(s.startswith(w) for w in ['here', 'first', 'next', 'then', 'finally', 
                                       'start by', 'begin by', 'you\'ll need']):
        return 'action'
    if re.search(r'\b(?:step|tip|key|important|common mistake|pro tip)\b', s):
        return 'property'
    
    # Definition / identification
    if re.search(r'\b(?:is a |is an |are a |are an |refers to|means|defined as)\b', s):
        return 'definition'
    
    # Location
    if re.search(r'\b(?:located|situated|found in|found on|found at|sits |lies )\b', s):
        return 'location'
    
    # Composition / material
    if re.search(r'\b(?:made of|made from|made up of|consists of|composed of)\b', s):
        return 'composition'
    
    # Purpose / function
    if re.search(r'\b(?:used for|used to|serves as|functions as|designed for|designed to)\b', s):
        return 'purpose'
    
    # Property / attribute
    if re.search(r'\b(?:has |have |includes|contains|features|known for|rich in|good source)\b', s):
        return 'property'
    
    # Comparison
    if re.search(r'\b(?:similar to|like |unlike |compared to|than |as .* as)\b', s):
        return 'comparison'
    
    return 'property'  # default


def _classify_style(sent: str) -> str:
    """Classify sentence style."""
    if sent.startswith('Here') or sent.startswith('You'):
        return 'friendly'
    if any(w in sent.lower() for w in ['firstly', 'secondly', 'moreover', 'furthermore']):
        return 'neutral'
    if len(sent) < 60:
        return 'concise'
    return 'friendly'


def _generalize_sentence(sent: str, topic: str, fact_type: str) -> str:
    """Replace topic-specific content with {subject} and {obj} placeholders.
    
    This is the core generalization step. It identifies the topic mention
    and replaces it with {subject}, then tries to identify the object
    (complement) and replaces it with {obj}.
    """
    if not topic:
        # No known topic — try to find the main noun phrase
        # Use the first capitalized noun phrase as topic
        m = re.match(r'(The|A|An)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', sent)
        if m:
            topic = m.group(0)
        else:
            return ""  # can't generalize without knowing the topic
    
    # Replace topic with {subject}
    template = sent
    
    # Case-insensitive replacement of topic
    topic_pos = template.lower().find(topic.lower())
    if topic_pos >= 0:
        template = template[:topic_pos] + '{subject}' + template[topic_pos + len(topic):]
    
    # For definition sentences, try to identify the object (complement)
    if fact_type == 'definition':
        # "X is a Y" -> "X is a {obj}"
        obj_match = re.search(
            r'{subject}\s+(?:is|are|was|were)\s+(a|an|the)\s+(.+)',
            template
        )
        if obj_match:
            article = obj_match.group(1)
            remainder = obj_match.group(2).strip().rstrip('.')
            template = template.replace(
                f'{{subject}} is {article} {remainder}',
                f'{{subject}} is {article} {{obj}}'
            )
    
    # For property sentences, try to identify the property value
    elif fact_type == 'property':
        # "X has Y" -> "X has {obj}"
        for verb in ['has ', 'have ', 'includes ', 'contains ', 'features ']:
            if verb in template.lower():
                parts = template.lower().split(verb, 1)
                if len(parts) == 2:
                    obj_text = template[len(parts[0]) + len(verb):].strip().rstrip('.')
                    if obj_text and len(obj_text) < 100:
                        template = template.replace(obj_text, '{obj}', 1)
                        break
    
    # For action/how-to sentences
    elif fact_type == 'action':
        # Look for imperative patterns or step descriptions
        step_match = re.match(r'(Step \d+:?\s*)(.+)', template)
        if step_match:
            action = step_match.group(2).strip().rstrip('.')
            template = template.replace(action, '{obj}', 1)
    
    return template.strip()


# ── Pattern Database ─────────────────────────────────────────────────────────

_PATTERN_DB: List[Pattern] = []


def load_knowledge_patterns(knowledge_dir: Optional[str] = None) -> int:
    """Load all KB files and extract sentence patterns from them.
    
    Returns the number of patterns extracted.
    """
    global _PATTERN_DB
    
    if knowledge_dir is None:
        knowledge_dir = str(Path(__file__).parent.parent.parent.parent / 'data' / 'knowledge')
    
    patterns = []
    kb_dir = Path(knowledge_dir)
    
    if not kb_dir.exists():
        return 0
    
    for json_file in sorted(kb_dir.rglob('*.json')):
        if json_file.name.startswith('.'):
            continue
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        
        if not isinstance(data, list):
            continue
        
        for entry in data:
            answer = entry.get('a', entry.get('answer', ''))
            if not answer or len(answer) < 30:
                continue
            
            # Try to extract topic from the q patterns
            topic = ""
            questions = entry.get('q', entry.get('patterns', []))
            if questions and isinstance(questions, list):
                q = questions[0]
                # Extract the main noun from the query pattern
                noun_m = re.search(r'[\w\s]+', q.replace('.*', ''))
                if noun_m:
                    topic = noun_m.group(0).strip()
            
            # Extract patterns from the answer text
            entry_patterns = _extract_patterns_from_text(answer, topic)
            patterns.extend(entry_patterns)
    
    _PATTERN_DB = patterns
    return len(patterns)


def get_patterns(fact_type: str, style: str = "friendly") -> List[Pattern]:
    """Get patterns matching a fact type and style."""
    matching = []
    for p in _PATTERN_DB:
        if p[1] == fact_type and p[3] == style:
            matching.append(p)
    # Also include patterns that match fact type with any style
    if not matching:
        for p in _PATTERN_DB:
            if p[1] == fact_type:
                matching.append(p)
    return matching


# ── Sentence Construction ────────────────────────────────────────────────────

def _clean_template(template: str) -> str:
    """Clean up common template artifacts from generalization."""
    # Fix double articles ("a a country" -> "a country")
    template = re.sub(r'\b(a|an)\s+(a|an)\b', r'\1', template)
    template = re.sub(r'\bthe\s+the\b', 'the', template)
    # Fix double prepositions ("located in in Paris" -> "located in Paris")
    template = re.sub(r'\b(in|on|at|near|for|to|of|with|from)\s+\1\b', r'\1', template)
    # Fix "is are" / "are is" / "was were" etc.
    template = re.sub(r'\b(is|are|was|were)\s+(is|are|was|were)\b', r'\1', template)
    return template


def _select_template(
    fact_type: str,
    verb: str,
    obj: str,
    style: str = "friendly"
) -> str:
    """Select the best template for a fact by learning from KB patterns.
    
    Instead of using raw learned patterns (which have artifacts), this function
    uses the learned patterns to WEIGHT which fallback template to prefer.
    Patterns that match the current verb more closely get higher weight.
    """
    _FALLBACKS = {
        "definition": [
            ("{subject} is {obj}.", 0),
            ("{subject} refers to {obj}.", 0),
        ],
        "property": [
            ("{subject} has {obj}.", 0),
            ("{subject} includes {obj}.", 0),
            ("{subject} features {obj}.", 0),
        ],
        "location": [
            ("{subject} is located {obj}.", 0),
            ("{subject} is found {obj}.", 0),
            ("You can find {subject} {obj}.", 0),
        ],
        "composition": [
            ("{subject} is made of {obj}.", 0),
            ("{subject} consists of {obj}.", 0),
            ("{subject} is composed of {obj}.", 0),
        ],
        "purpose": [
            ("{subject} is used for {obj}.", 0),
            ("{subject} serves as {obj}.", 0),
            ("{subject} functions as {obj}.", 0),
        ],
        "action": [
            ("{subject} {verb} {obj}.", 0),
        ],
        "comparison": [
            ("{subject} is like {obj}.", 0),
            ("{subject} resembles {obj}.", 0),
        ],
    }
    
    # Get base fallbacks
    weighted = list(_FALLBACKS.get(fact_type, [("{subject} {verb} {obj}.", 0)]))
    
    # Learn from patterns: boost templates whose verb matches the fact's verb
    patterns = get_patterns(fact_type, style)
    if not patterns:
        patterns = get_patterns(fact_type, "friendly")
    verb_lower = verb.lower().split()[0] if verb else ''
    
    for template, ft, key_verb, sty in patterns:
        if key_verb and verb_lower and key_verb == verb_lower:
            for i, (fb_temp, fb_weight) in enumerate(weighted):
                if fb_temp.replace('{verb}', '').replace('{subject}', '').replace('{obj}', '') == \
                   template.replace('{verb}', '').replace('{subject}', '').replace('{obj}', ''):
                    weighted[i] = (fb_temp, fb_weight + 1)
                    break
    
    # Sort by weight, pick top 3 randomly
    weighted.sort(key=lambda x: -x[1])
    top_weight = max(w for _, w in weighted) if weighted else 0
    best = [t for t, w in weighted if w >= top_weight - 1]
    return random.choice(best) if best else weighted[0][0]


def construct_sentence(
    subject: str,
    verb: str,
    obj: str,
    fact_type: str = "property",
    style: str = "friendly"
) -> str:
    """Construct a sentence using learned pattern weights.
    
    Uses learned patterns to select the best template, then fills
    {subject}, {obj}, and {verb} slots. Cleans up preposition conflicts.
    """
    # Select the best template using learned weights
    template = _select_template(fact_type, verb, obj, style)
    
    # Find the word BEFORE {obj} in the template — that's the preposition
    # E.g., "is used for {obj}" → preposition is "for"
    # If obj starts with the same preposition, strip it to avoid "for for"
    clean_obj = obj
    parts = template.strip().rstrip('.,!?').split()
    template_prep = ''
    for idx, part in enumerate(parts):
        if part == '{obj}' and idx > 0:
            template_prep = parts[idx - 1].lower()
            break
    obj_first = clean_obj.split()[0].lower() if clean_obj.split() else ''
    if template_prep in ('in', 'on', 'at', 'for', 'to', 'of', 'with', 'from', 'near', 'as') \
            and obj_first == template_prep:
        clean_obj = ' '.join(clean_obj.split()[1:])
    
    try:
        sentence = template.replace('{subject}', subject).replace('{verb}', verb).replace('{obj}', clean_obj)
        sentence = re.sub(r'\s+', ' ', sentence).strip()
        if sentence[0].islower():
            sentence = sentence[0].upper() + sentence[1:]
        if not sentence.endswith(('.', '!', '?')):
            sentence += '.'
        return sentence
    except Exception:
        return f"{subject} {verb} {obj}."


def get_stats() -> Dict:
    """Return statistics about the learned pattern database."""
    counts = {}
    for p in _PATTERN_DB:
        ft = p[1]
        counts[ft] = counts.get(ft, 0) + 1
    return {
        "total_patterns": len(_PATTERN_DB),
        "by_type": counts,
    }
