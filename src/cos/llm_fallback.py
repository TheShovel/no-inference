"""
LLM Fallback — Replaced by symbolic context extraction.

This module previously used LFM2-350M-Extract and Tiny-LLM GGUF models
for keyword extraction and response synthesis. It now delegates entirely
to the symbolic context_extraction module.

No neural networks, no LLMs, no GGUF models required.
"""

import re
from pathlib import Path
from typing import List, Optional, Tuple

from .context_extraction import (
    extract_keywords,
    extract_topic as _extract_topic_safe,
    extract_entities_only,
    extract_content_words,
    clean_query,
    remove_stop_words,
)

# All model references removed — purely symbolic extraction only.


def extract_search_terms(query: str) -> List[str]:
    """Extract search keywords from a query using symbolic extraction.

    Uses the multi-strategy context_extraction system.
    Returns a list of keyword strings, or [query] on failure.

    This replaces the previous LFM2-350M-Extract model.
    """
    if not query or not query.strip():
        return [query] if query else []

    keywords = extract_keywords(query, max_keywords=5)
    result = [phrase for phrase, score in keywords if score > 0.20]

    if result:
        return result

    # Fallback: extract the main noun phrase from the query
    m = re.search(
        r'(?:what|how|who|why)\s+(?:(?:is|are|was|were|does|do|can|to)\s+)?(.+)',
        query.lower(),
    )
    if m:
        return [m.group(1).strip().rstrip('?')]
    return [query]


def extract_topic(query: str) -> Optional[str]:
    """Extract the main topic from a query using symbolic extraction.

    This replaces the previous LFM2-350M-Extract model.
    """
    topic, confidence = _extract_topic_safe(query)
    if topic and confidence > 0.15:
        return topic

    # Fallback: regex extraction
    m = re.search(
        r'(?:what|how|who|why)\s+(?:(?:is|are|was|were|does|do|can|to)\s+)?'
        r'(?:i|we|you|they|he|she|it|one\s+)?(?:to\s+)?'
        r'(?:make|bake|cook|create|build|write|find|get|know)?\s*(.+)',
        query.lower(),
    )
    if m:
        topic = m.group(1).strip().rstrip('?')
        if topic:
            return topic
    return query.strip()


# ── Prompt / template text (kept as constants for any code that references them) ──

EXTRACTION_PROMPT = ""  # No longer used; kept for import compatibility
SYNTHESIS_PROMPT = ""   # No longer used; kept for import compatibility
ESSAY_PROMPT = ""       # No longer used; kept for import compatibility


# ── Poem generator ────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).parent.absolute()
_POEMS_DIR = _SCRIPT_DIR.parent.parent / 'data' / 'knowledge' / 'templates' / 'poems'
_POEM_CACHE = None

_DEFAULT_CONTEXT_WORDS = [
    'wonderful', 'beautiful', 'endless', 'shining', 'gentle', 'silent',
    'glowing', 'ancient', 'mighty', 'golden', 'silver',
    'dancing', 'flowing', 'burning', 'frozen', 'hidden', 'sacred',
]


def _load_poem_templates():
    """Load poem templates from external JSON files."""
    global _POEM_CACHE
    templates = []
    if _POEMS_DIR.exists():
        for path in sorted(_POEMS_DIR.rglob('*.json')):
            if path.name.startswith('.'):
                continue
            try:
                import json
                data = json.loads(path.read_text())
                if isinstance(data, list):
                    for entry in data:
                        tmpl = entry.get('template', '')
                        if tmpl and '{topic}' in tmpl:
                            templates.append(tmpl.replace('\\n', '\n'))
            except Exception:
                pass
    if not templates:
        templates = [
            "{topic}\nA wonder to behold,\nA story to be told.",
            "Oh, {topic}!\nHow brilliantly you shine,\nA truly great design.",
            "{topic} in the night,\nA silent graceful wonder,\nForever shining.",
            "{topic}, {topic},\nA beauty beyond measure,\nA timeless treasure.",
            "I dream of {topic},\nWhere wonders never cease,\nA moment of peace.",
        ]
    _POEM_CACHE = templates
    return templates


def _get_poem_templates():
    if _POEM_CACHE is None:
        return _load_poem_templates()
    return _POEM_CACHE


def reload_poems():
    """Force reload poem templates from disk."""
    global _POEM_CACHE
    _POEM_CACHE = None
    return _load_poem_templates()


# ── Universal poetic word bank ──────────────────────────────────────────────
# These words work for any topic — no need to extract from Wikipedia text
_POETIC_WORDS = [
    'beautiful', 'gentle', 'peaceful', 'golden', 'silent', 'ancient',
    'mighty', 'bright', 'deep', 'rich', 'warm', 'soft', 'wild', 'vast',
    'rare', 'pure', 'calm', 'bold', 'fair', 'swift', 'keen',
    'humble', 'noble', 'grand', 'serene', 'vivid',
    'endless', 'graceful', 'lovely', 'shining', 'timeless', 'wondrous',
    'sacred', 'subtle', 'tender', 'fierce', 'quiet', 'luminous',
    'fragrant', 'crimson', 'amber', 'crystal', 'velvet', 'silver',
]


def _extract_context_words(text, max_words=10):
    """Extract descriptive words from text.

    Returns a blend of the curated poetic word bank (primary) and
    any genuinely poetic words found in the text (bonus). This
    ensures poems always use beautiful language regardless of topic.
    """
    import random
    
    # Start with the curated poetic word bank as foundation
    result = list(_POETIC_WORDS)
    
    # Try to enrich with topic-specific descriptive words
    if text and len(text.strip()) >= 10:
        try:
            words = extract_content_words(text, max_words=20)
            _ADJ_LIKE = ('ous', 'ive', 'ful', 'less', 'ish', 'like', 'some',
                         'ant', 'ent', 'ic', 'al', 'ial', 'ual', 'y')
            _NOUN_WORDS = {
                'family', 'species', 'genus', 'type', 'form', 'part', 'area',
                'system', 'process', 'method', 'technique', 'study', 'field',
                'research', 'center', 'unit', 'structure', 'element', 'source',
                'level', 'group', 'class', 'includes', 'including', 'known',
                'called', 'refers', 'example', 'found', 'described', 'located',
                'galaxy', 'planet', 'star', 'nebula', 'species', 'organism',
                'mineral', 'chemical', 'protein', 'bacteria', 'fungus', 'plant',
                'animal', 'fabric', 'texture', 'surface', 'pattern',
            }
            for word, score in words:
                w = word.lower().strip()
                if not w.isalpha() or len(w) < 3 or w.endswith('ly'):
                    continue
                if w in _NOUN_WORDS:
                    continue
                if w.endswith(_ADJ_LIKE) and score > 0.3 and w not in result:
                    result.append(w)
        except Exception:
            pass
    
    random.shuffle(result)
    return result[:max_words]


def _clean_topic(topic):
    """Clean a topic string for use in poems.
    Strips leading articles so templates don't produce 'the the moon'.
    """
    t = topic.strip()
    # Strip leading articles
    for prefix in ['the ', 'a ', 'an ']:
        if t.lower().startswith(prefix):
            t = t[len(prefix):].strip()
            break
    return t


def _is_plural(topic):
    """Rough heuristic: does the topic look plural?"""
    t = topic.strip().lower()
    return t.endswith('s') and not t.endswith(('ss', 'us'))


def _format_article(word):
    """Return 'an' if word starts with a vowel sound, 'a' otherwise."""
    return 'an' if word[0].lower() in 'aeiou' else 'a'


def generate_poem(topic, information=None):
    """Generate a poem about a topic using templates."""
    import random
    templates = _get_poem_templates()
    if not templates:
        return f"A poem about {topic}."
    template = random.choice(templates)

    raw_topic = topic.strip()
    clean_topic = _clean_topic(raw_topic)
    topic_lower = clean_topic.lower()
    topic_cap = clean_topic[0].upper() + clean_topic[1:] if clean_topic else ''
    topic_plural = _is_plural(clean_topic)

    context_words = _extract_context_words(information or '')
    if not context_words:
        context_words = list(_POETIC_WORDS)
        random.shuffle(context_words)

    # Fill context placeholders
    context_count = template.count('{context}')
    chosen = []
    for i in range(context_count):
        chosen.append(context_words[i % len(context_words)])
    for cw in chosen:
        template = template.replace('{context}', cw, 1)

    # Fill topic placeholders with grammar fixes
    result = []
    for line in template.split('\n'):
        # Fix 'a [plural]' -> '[plural]'
        if topic_plural:
            line = re.sub(r'\ba\s+(?=\{topic\})', '', line)
            line = re.sub(r'\bThere once was a\b', 'There once were', line)
            line = re.sub(r'\bStands the\b', 'Stand the', line)
        # Fix 'a [vowel]' -> 'an [vowel]'
        line = re.sub(r'\bA\s+(?=[aeiou])', 'An ', line)
        line = re.sub(r'\ba\s+(?=[aeiou])', 'an ', line)
        
        if '{topic}' in line:
            is_start = line.strip().startswith('{topic}')
            replacement = topic_cap if is_start else topic_lower
            result.append(line.replace('{topic}', replacement))
        else:
            result.append(line)
    return '\n'.join(result)


# ── Bad response detection ───────────────────────────────────────────────────

_BAD_RESPONSES = {
    'i understand', 'i don\'t know', 'i do not know',
    'i don\'t understand', 'i have no information',
    'i am not sure', 'i cannot answer',
    'that is a good question', 'that\'s a good question',
    'i am a helpful assistant',
}


def _is_garbage(text):
    """Check if a generated response is garbage (too short, generic, or incoherent)."""
    t = text.lower().strip().rstrip('.!?')
    if len(t) < 20:
        return True
    if t in _BAD_RESPONSES:
        return True
    if t.startswith('i am'):
        return True
    if re.search(r'\b(\w+)( \1){3,}', t):
        return True
    content_words = {'is', 'are', 'was', 'were', 'has', 'have', 'can', 'will',
                     'use', 'uses', 'used', 'made', 'makes', 'make', 'called',
                     'known', 'found', 'located', 'contains'}
    if not any(w in t for w in content_words):
        if len(t) < 40:
            return True
    return False


def synthesize_response(query, information):
    """Synthesize a response from retrieved information.

    Previously used Tiny-LLM. Now constructs a simple answer using
    the information directly, combined with the query context.
    """
    if not information or not information.strip():
        return None

    # Simple symbolic synthesis: combine query and information
    info = information.strip()
    if len(info) > 800:
        # Take first paragraph
        info = info.split('\n')[0]
        if len(info) > 800:
            # Truncate at last sentence boundary
            info = info[:info.rfind('. ', 0, 800) + 1] or info[:800]

    # Extract the key topic to build a natural response
    topic, _ = _extract_topic_safe(query)

    if topic:
        response = f"{topic.capitalize()}: {info}"
    else:
        response = info

    if not _is_garbage(response):
        return response

    # If it looks garbage, try just using the information directly
    if not _is_garbage(info):
        return info

    return None


def models_available():
    """Check if model files exist on disk.

    Always returns False now — all functionality is symbolic.
    Kept for backward compatibility with code that checks this.
    """
    return False
