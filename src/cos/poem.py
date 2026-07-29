"""
COS Poem Generator -- Template-based poem generation from topics and Wikipedia text.

Generates poems using hand-authored templates with context-aware vocabulary.
No neural networks, no LLM inference.
"""

import re
import random
from pathlib import Path

from .context_extraction import extract_content_words


# ── Paths ────────────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).parent.absolute()
_POEMS_DIR = _SCRIPT_DIR.parent.parent / 'data' / 'knowledge' / 'templates' / 'poems'
_POEM_CACHE = None

_DEFAULT_CONTEXT_WORDS = [
    'wonderful', 'beautiful', 'endless', 'shining', 'gentle', 'silent',
    'glowing', 'ancient', 'mighty', 'golden', 'silver',
    'dancing', 'flowing', 'burning', 'frozen', 'hidden', 'sacred',
]


# ── Template loading ─────────────────────────────────────────────────────────

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


# ── Poetic word bank ─────────────────────────────────────────────────────────

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
    for prefix in ['the ', 'a ', 'an ']:
        if t.lower().startswith(prefix):
            t = t[len(prefix):].strip()
            break
    return t


def _is_plural(topic):
    """Rough heuristic: does the topic look plural?"""
    t = topic.strip().lower()
    return t.endswith('s') and not t.endswith(('ss', 'us'))


def generate_poem(topic, information=None):
    """Generate a poem about a topic using templates."""
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
        if topic_plural:
            line = re.sub(r'\ba\s+(?=\{topic\})', '', line)
            line = re.sub(r'\bThere once was a\b', 'There once were', line)
            line = re.sub(r'\bStands the\b', 'Stand the', line)
        line = re.sub(r'\bA\s+(?=[aeiou])', 'An ', line)
        line = re.sub(r'\ba\s+(?=[aeiou])', 'an ', line)

        if '{topic}' in line:
            is_start = line.strip().startswith('{topic}')
            replacement = topic_cap if is_start else topic_lower
            result.append(line.replace('{topic}', replacement))
        else:
            result.append(line)
    return '\n'.join(result)
