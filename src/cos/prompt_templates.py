"""
Prompt Template System — matches user prompts to structured templates
stored in data/prompt_templates/*.json files.

Each JSON template defines:
  - id: unique identifier
  - patterns: regex patterns with named groups for slot extraction
  - slots: mapping from slot names to regex group names  
  - response_type: which handler to use (essay, html_page, explanation, code_function)
  - weight: priority score for matching

To add a new template: just create a new JSON file in data/prompt_templates/
No code changes needed!
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# ── Paths ──────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / 'data' / 'prompt_templates'
_LOADED_TEMPLATES = None  # cache


# ── Template class ──────────────────────────────────────────────────────────

class PromptTemplate:
    """A single prompt template loaded from a JSON file."""
    
    def __init__(self, data: dict):
        self.id = data.get('id', 'unnamed')
        self.patterns = [re.compile(p, re.IGNORECASE) for p in data.get('patterns', [])]
        self.slots = data.get('slots', {})  # slot_name -> regex_group_name
        self.response_type = data.get('response_type', 'essay')
        self.weight = data.get('weight', 0.5)
    
    def match(self, query: str) -> Optional[Dict[str, str]]:
        """Try to match this template against a query.
        Returns extracted slots dict if match, None otherwise."""
        for pattern in self.patterns:
            m = pattern.search(query)
            if m:
                extracted = {}
                for slot_name, group_name in self.slots.items():
                    try:
                        val = m.group(group_name)
                        if val:
                            extracted[slot_name] = val.strip().rstrip('.!?,;: ')
                    except (IndexError, KeyError):
                        pass
                return extracted if extracted else {}
        return None


# ── Template Loader ─────────────────────────────────────────────────────────

def _load_templates() -> List[PromptTemplate]:
    """Load all template JSON files from data/prompt_templates/"""
    global _LOADED_TEMPLATES
    if _LOADED_TEMPLATES is not None:
        return _LOADED_TEMPLATES
    
    templates = []
    if not _TEMPLATES_DIR.exists():
        _TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        _LOADED_TEMPLATES = []
        return []
    
    for path in sorted(_TEMPLATES_DIR.glob('*.json')):
        if path.name.startswith('.'):
            continue
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and entry.get('patterns'):
                        templates.append(PromptTemplate(entry))
        except Exception as e:
            print(f"  Warning: Could not load {path}: {e}")
    
    _LOADED_TEMPLATES = templates
    return templates


def reload_templates():
    """Force reload all templates from disk."""
    global _LOADED_TEMPLATES
    _LOADED_TEMPLATES = None
    return _load_templates()


# ── Response Functions ──────────────────────────────────────────────────────

def _handle_essay(query: str, slots: Dict[str, str]) -> str:
    """Write an essay using retrieved Wikipedia content processed through NLG.
    
    Handles multi-requirement queries by retrieving content for each
    requirement and combining them into a comprehensive response.
    """
    from cos.engine import (_retrieve_multi_content, _make_conversational,
                            _handle_factual, _search_wikipedia, _extract_search_topic)
    
    topic = slots.get('topic', '')
    if not topic:
        return _handle_factual(query, True)
    
    # Clean the topic: use _extract_search_topic to get the core topic
    # This handles verbose slots like "the implementation of a four-day work week"
    # by extracting just "four-day work week" for better Wikipedia matching
    core_topic = _extract_search_topic(topic)
    if core_topic and len(core_topic) > 3 and len(core_topic) < len(topic):
        topic = core_topic
    # Also strip leading articles and verbose prefixes
    topic = re.sub(r'^(?:the\s+)?(?:concept\s+of\s+|idea\s+of\s+|implementation\s+of\s+|history\s+of\s+)', '', topic, flags=re.IGNORECASE)
    
    # Collect all content requirements
    content_parts = []
    
    # 1. Main topic content
    main_content = _retrieve_multi_content(topic, max_sources=3)
    if main_content and len(main_content) > 100:
        content_parts.append(main_content)
    
    # 2. Additional requirements (from complex templates)
    req_slots = ['requirement1', 'requirement2', 'requirement3',
                 'emphasis', 'counterarg', 'examples', 'focus',
                 'element1', 'element2', 'sections']
    for slot_name in req_slots:
        req = slots.get(slot_name, '')
        if req and len(req) > 3:
            # Try to get content about this specific requirement
            req_content = _search_wikipedia(req)
            if req_content and req_content[0] and len(req_content[0]) > 50:
                content_parts.append(req_content[0])
            else:
                # Try as a KB lookup
                from cos.knowledge import lookup as knowledge_lookup
                kb = knowledge_lookup(req)
                if kb and len(kb) > 50:
                    content_parts.append(kb)
    
    # Combine all content
    if content_parts:
        combined = '\n\n'.join(content_parts)
        return _make_conversational(combined)
    
    return _handle_factual(query, True)


def _handle_html_page(query: str, slots: Dict[str, str]) -> str:
    """Create an HTML page using the KB template with topic substitution.
    
    Handles multi-requirement HTML requests (topic, style, features, sections).
    """
    from cos.code_knowledge import code_lookup
    from cos.engine import _handle_factual
    
    topic = slots.get('topic', 'web page')
    style = slots.get('style', '')
    features = slots.get('features', '')
    header = slots.get('header', '')
    content_slot = slots.get('content', '')
    footer = slots.get('footer', '')
    
    # Build an enhanced query that includes all requirements
    extra_parts = []
    if style:
        extra_parts.append(f"{style} style")
    if features:
        extra_parts.append(features)
    if header:
        extra_parts.append(f"header about {header}")
    if content_slot:
        extra_parts.append(f"content about {content_slot}")
    if footer:
        extra_parts.append(f"footer about {footer}")
    
    enhanced_query = query
    if extra_parts:
        enhanced_query = f"Create an HTML page about {topic} with {' and '.join(extra_parts)}"
    
    # Try KB lookup first (which handles __TOPIC__ substitution)
    answer = code_lookup(enhanced_query)
    if answer:
        return answer
    
    # Fallback to factual handler
    result = _handle_factual(query, True)
    if result:
        return result
    
    # Provide a specific response even without KB match
    style_desc = f" with a {style} style" if style else ""
    feat_desc = f" featuring {features}" if features else ""
    return f"I can create an HTML page about {topic}{style_desc}{feat_desc}. Let me provide you with a complete, responsive HTML document."


def _handle_explanation(query: str, slots: Dict[str, str]) -> str:
    """Provide an explanation using Wikipedia content.
    Uses _handle_factual which has the alias system and KB lookup."""
    from cos.engine import _retrieve_multi_content, _make_conversational, _handle_factual
    
    topic = slots.get('topic', '')
    
    # First try direct KB lookup (which has full alias support)
    result = _handle_factual(query, True)
    if result and len(result) > 100:
        return result
    
    # Fallback: search Wikipedia with the extracted topic
    if topic:
        # Strip leading articles for better Wikipedia matching
        topic = re.sub(r'^(a|an|the)\s+', '', topic.strip(), flags=re.IGNORECASE)
        content = _retrieve_multi_content(topic, max_sources=2)
        if content and len(content) > 100:
            return _make_conversational(content)
    
    return result or f"I found some information about {topic} but couldn't generate a full response. Could you ask a more specific question?"


def _handle_code_function(query: str, slots: Dict[str, str]) -> str:
    """Write a function using the KB system.
    
    Handles multi-requirement coding queries by extracting all requirements
    and looking up or synthesizing code for each.
    """
    from cos.code_knowledge import code_lookup
    from cos.engine import _handle_factual
    
    # Try KB lookup first
    answer = code_lookup(query)
    if answer:
        return answer
    
    # Extract coding requirements from slots
    lang = slots.get('language', '') or 'python'
    task = slots.get('task', '')
    return_val = slots.get('returnval', '')
    handling = slots.get('handling', '')
    members = slots.get('members', '')
    
    # Build a comprehensive search query from all requirements
    search_parts = [task]
    if return_val:
        search_parts.append(return_val)
    if handling:
        search_parts.append(handling)
    if members:
        search_parts.append(members)
    
    enhanced_query = f"{lang} {' '.join(search_parts)}"
    
    # Try again with enhanced query
    answer = code_lookup(enhanced_query)
    if answer:
        return answer
    
    # Fallback to factual handler for Wikipedia content
    result = _handle_factual(query, True)
    if result:
        return result
    
    # Provide a useful response even without KB match
    task_desc = task or 'process data'
    return_desc = f" returning {return_val}" if return_val else ""
    handle_desc = f" with {handling}" if handling else ""
    return f"I'd be happy to write a {lang} function that {task_desc}{return_desc}{handle_desc}. Could you provide any additional requirements?"


# ── Router ──────────────────────────────────────────────────────────────────

_RESPONSE_HANDLERS = {
    'essay': _handle_essay,
    'html_page': _handle_html_page,
    'explanation': _handle_explanation,
    'code_function': _handle_code_function,
}


def find_best_template(query: str) -> Tuple[Optional[PromptTemplate], Optional[Dict[str, str]]]:
    """Find the best matching template for a query.
    
    Scoring: filled_slots * 100 + match_length * weight
    """
    templates = _load_templates()
    best_template = None
    best_slots = None
    best_score = -1
    
    for template in templates:
        slots = template.match(query)
        if slots is not None:
            n_slots = len(slots) if slots else 0
            longest_match = 0
            for pattern in template.patterns:
                m = pattern.search(query)
                if m:
                    longest_match = max(longest_match, len(m.group(0)))
            
            score = n_slots * 100 + longest_match * template.weight
            
            if score > best_score:
                best_score = score
                best_template = template
                best_slots = slots
    
    return best_template, best_slots


def process_with_templates(query: str) -> Optional[str]:
    """Try to process a query using the template system.
    Returns a response if a matching template was found, None otherwise."""
    template, slots = find_best_template(query)
    if template and slots is not None:
        handler = _RESPONSE_HANDLERS.get(template.response_type)
        if handler:
            return handler(query, slots)
    return None
