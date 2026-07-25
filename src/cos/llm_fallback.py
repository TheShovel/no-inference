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


def _extract_context_words(text, max_words=10):
    """Extract descriptive words from text using symbolic extraction.

    This replaces the previous LFM2-350M based extraction.
    Uses content word scoring from context_extraction.
    """
    if not text or len(text.strip()) < 10:
        return []

    words = extract_content_words(text, max_words=max_words * 2)
    # Filter to likely descriptive words (adjectives)
    descriptive = []
    stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'it', 'its',
                  'they', 'them', 'also', 'very', 'just', 'more', 'some',
                  'such', 'both', 'each', 'this', 'that'}
    for word, score in words:
        w = word.lower().strip()
        if w.isalpha() and len(w) > 2 and w not in stop_words and score > 0.3:
            descriptive.append(w)
        if len(descriptive) >= max_words:
            break

    if descriptive:
        import random
        random.shuffle(descriptive)
        return descriptive[:max_words]
    return []


def generate_poem(topic, information=None):
    """Generate a poem about a topic using templates."""
    import random
    templates = _get_poem_templates()
    if not templates:
        return f"A poem about {topic}."
    template = random.choice(templates)

    topic_lower = topic.strip().lower()
    topic_cap = topic.strip().capitalize()

    context_words = _extract_context_words(information or '')
    if not context_words:
        context_words = list(_DEFAULT_CONTEXT_WORDS)
        random.shuffle(context_words)

    context_count = template.count('{context}')
    chosen = []
    for i in range(context_count):
        chosen.append(context_words[i % len(context_words)])

    for cw in chosen:
        template = template.replace('{context}', cw, 1)

    result = []
    for line in template.split('\n'):
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
