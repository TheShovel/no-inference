"""
COS Template Engine — Context-aware conversational response templates.

Templates are stored as JSON files in data/knowledge/templates/ organized by
category. Each template can reference previous conversation context using
{context} placeholders. The engine resolves these to the last discussed topic.

Template format:
  {
    "triggers": ["trigger phrase 1", "trigger phrase 2", ...],
    "context_role": "topic" | null,       # requires conversation context?
    "template": "Response with {context} placeholders",
    "fallback": "Response when no context available",
    "style": ["casual", "formal", ...],
    "response_length": "short" | "medium" | "long"
  }
"""

import json
import os
import re
from pathlib import Path
from cos.state import conversation_history, fact_memory

# ── Paths ────────────────────────────────────────────────────────────────────
TEMPLATE_DIR = Path(__file__).parent.parent.parent / 'data' / 'knowledge' / 'templates'

# ── Template cache ───────────────────────────────────────────────────────────
_TEMPLATES = []  # List of (trigger_regex, entry) tuples

def _load_all():
    """Load all template files from the template directory."""
    global _TEMPLATES
    _TEMPLATES = []

    if not TEMPLATE_DIR.exists():
        print(f"  Template directory not found: {TEMPLATE_DIR}")
        return

    for path in sorted(TEMPLATE_DIR.rglob('*.json')):
        if path.name.startswith('.'):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  Warning: Could not load {path}: {e}")
            continue

        if not isinstance(data, list):
            continue

        loaded = 0
        for entry in data:
            triggers = entry.get('triggers', [])
            template = entry.get('template', '')
            if not triggers or not template:
                continue
            if isinstance(triggers, str):
                triggers = [triggers]
            for trigger in triggers:
                if not trigger:
                    continue
                t = trigger.lower().strip()
                words = t.split()
                if len(words) == 1:
                    # Single word triggers always use word boundaries
                    regex = re.compile(r'\b' + re.escape(t) + r'\b', re.IGNORECASE)
                else:
                    # Multi-word: word boundary at start and end
                    regex = re.compile(r'\b' + re.escape(t) + r'\b', re.IGNORECASE)
                _TEMPLATES.append((regex, entry))
                loaded += 1

        if loaded > 0:
            rel = path.relative_to(TEMPLATE_DIR)
            # Quiet load

    _TEMPLATES.sort(key=lambda x: -len(x[0].pattern))  # longer patterns first


def get_last_topic():
    """Extract the main topic from the last conversation exchange.
    
    Looks for the last assistant response and extracts key nouns.
    Returns a topic string or None.
    """
    if not conversation_history:
        return None

    # Find the last assistant response
    last_topic = None
    for q, r in reversed(conversation_history):
        if r:
            # Extract topic from the response context
            # Check if we stored a topic
            last_topic = _extract_topic_from_query(q)
            break
    
    return last_topic


def _extract_topic_from_query(query):
    """Extract the main topic from a user query.
    
    Handles patterns like:
      - "What is X?" -> X
      - "Tell me about X" -> X
      - "Explain X" -> X
      - "I like X" -> X
    """
    q = query.lower().strip()
    
    # Remove common question words and get the key noun phrase
    patterns = [
        r'(?:what|who|how|why|where|when)\s+(?:is|are|was|were|does|do)\s+(?:a|an|the|this|that)?\s*(.+?)(?:\?|$)',
        r'(?:tell|teach|show)\s+(?:me|us)\s+(?:about|what|how)\s+(.+?)(?:\?|$)',
        r'(?:explain|describe|define)\s+(?:the\s+)?(?:concept\s+of\s+)?(.+?)(?:\?|$)',
        r'i\s+(?:like|love|enjoy|hate|want|have|use)\s+(.+?)(?:\.|$)',
        r'(?:write|create|make|compose|draft)\s+(?:an?\s+)?(?:\w+\s+){0,3}(?:about|on|regarding)\s+(.+?)(?:\?|$|\.)',
    ]
    
    for pat in patterns:
        m = re.search(pat, q)
        if m:
            topic = m.group(1).strip().rstrip('.!?,;:')
            # Clean up common artifacts
            topic = re.sub(r'\s+', ' ', topic)
            if len(topic) > 2 and len(topic) < 100:
                return topic
    
    # Fallback: use the longest noun phrase
    words = [w for w in q.split() if len(w) > 3 and w not in 
             {'what', 'when', 'where', 'which', 'who', 'whom', 'whose',
              'this', 'that', 'these', 'those', 'there', 'their', 'them',
              'have', 'with', 'from', 'than', 'been', 'were', 'does',
              'will', 'just', 'also', 'more', 'some', 'than', 'then',
              'very', 'your', 'about', 'would', 'could', 'should',
              'into', 'over', 'such', 'only', 'other', 'tell', 'show',
              'explain', 'describe', 'define', 'write', 'make', 'create'}]
    if words:
        return ' '.join(words[:5])
    
    return None


def get_context_topic():
    """Get the current conversation topic by analyzing recent history.
    
    Returns a dict with:
      - topic: the main subject
      - last_query: the last user query
      - last_response: the last assistant response
      - turn_count: how many turns back
    """
    if not conversation_history:
        return None
    
    # Find the last substantive exchange
    for i in range(min(len(conversation_history), 10)):
        idx = len(conversation_history) - 1 - i
        q, r = conversation_history[idx]
        if r and len(r) > 10:
            topic = _extract_topic_from_query(q)
            if topic:
                return {
                    'topic': topic,
                    'last_query': q,
                    'last_response': r,
                    'turn_count': i,
                }
    
    # Fallback: use the very last query
    if conversation_history:
        q = conversation_history[-1][0]
        topic = _extract_topic_from_query(q)
        if topic:
            return {
                'topic': topic,
                'last_query': q,
                'last_response': conversation_history[-1][1],
                'turn_count': 0,
            }
    
    return None


# ── Template matching ────────────────────────────────────────────────────────

def match_template(query, context=None):
    """Find the best matching template for a query.
    
    Args:
        query: The user's query string
        context: Optional context dict with 'topic' key
    
    Returns:
        A dict with 'response' and 'template_info', or None
    """
    global _TEMPLATES
    if not _TEMPLATES:
        _load_all()
    
    if not _TEMPLATES:
        return None
    
    q = query.lower().strip()
    if not q:
        return None
    
    # Try each template's triggers
    best = None
    best_score = 0
    
    for trigger_regex, entry in _TEMPLATES:
        m = trigger_regex.search(q)
        if m:
            # Calculate match quality
            matched_text = m.group(0)
            score = len(matched_text) / max(len(q), 1)  # proportion of query matched
            
            # Bonus for exact matches
            if matched_text == q:
                score *= 2
            
            # Bonus for longer trigger patterns (more specific)
            score *= len(matched_text) ** 0.3
            
            if score > best_score:
                best_score = score
                best = entry
    
    if not best or best_score < 0.1:
        return None
    
    # Check if this template requires context
    context_role = best.get('context_role')
    ctx = context or get_context_topic()

    # If the current query explicitly mentions a topic (e.g. "about carrots",
    # "on carrots"), prefer that over stale historical context.
    current_topic = _extract_topic_from_query(query)
    if current_topic and ctx:
        ctx['topic'] = current_topic
    
    if context_role and not ctx:
        # Template requires context but none available — use fallback
        fallback = best.get('fallback', '')
        if fallback:
            return {
                'response': fallback,
                'template_info': {
                    'id': best.get('id', 'unknown'),
                    'requires_context': True,
                    'used_fallback': True,
                }
            }
        return None
    
    # Fill in template
    template_text = best['template']
    topic = None
    if ctx:
        topic = ctx.get('topic', '')
    
    try:
        if topic:
            response = template_text.replace('{context}', topic)
            response = response.replace('{topic}', topic)
        else:
            response = template_text
    except Exception:
        response = template_text
    
    return {
        'response': response,
        'template_info': {
            'id': best.get('id', 'unknown'),
            'triggers': best.get('triggers', [])[:2],
            'style': best.get('style', []),
            'response_length': best.get('response_length', 'medium'),
            'requires_context': bool(context_role),
        }
    }


def get_all_templates():
    """Get all loaded templates for inspection."""
    if not _TEMPLATES:
        _load_all()
    
    seen = set()
    entries = []
    for _, entry in _TEMPLATES:
        eid = entry.get('id', '')
        if eid and eid not in seen:
            seen.add(eid)
            entries.append(entry)
    
    return entries


def reload():
    """Force reload of all templates from disk."""
    global _TEMPLATES
    _TEMPLATES = []
    _load_all()


def stats():
    """Return statistics about loaded templates."""
    if not _TEMPLATES:
        _load_all()
    
    # Count unique entries
    seen = set()
    categories = {}
    for _, entry in _TEMPLATES:
        eid = entry.get('id', '')
        if eid not in seen:
            seen.add(eid)
            style = entry.get('style', ['unknown'])
            cat = style[0] if style else 'unknown'
            categories[cat] = categories.get(cat, 0) + 1
    
    total = len(seen)
    result = f"Total templates: {total}\n"
    for cat, count in sorted(categories.items()):
        result += f"  {cat}: {count}\n"
    return result
