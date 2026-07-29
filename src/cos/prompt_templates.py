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
                            _handle_factual, _search_wikipedia, _extract_search_topic,
                            _format_as_essay)
    
    topic = slots.get('topic', '')
    if not topic:
        return _handle_factual(query, True)
    
    # Aggressively clean the topic before searching:
    # 1. Strip trailing clauses after sentence boundaries
    topic_clean = re.sub(r'[?.:!]\s+.*$', '', topic)
    if len(topic_clean) > 5:
        topic = topic_clean
    # 2. Strip "make sure it covers...", "ensuring..." type trailing constraints
    topic = re.sub(r'\s+make\s+sure\s+(?:it|this|the)\s+.*$', '', topic, flags=re.IGNORECASE)
    topic = re.sub(r'\s+ensuring\s+(?:that\s+)?(?:it|the|this)\s+.*$', '', topic, flags=re.IGNORECASE)
    # 3. Strip trailing "and how..." type clauses
    topic = re.sub(r'\s+and\s+how\s+(?:the|this|it|they)\s+.*$', '', topic, flags=re.IGNORECASE)
    # 4. Strip comparison clauses after question marks
    topic = re.sub(r'[?]\s+and\s+how\s+.*$', '', topic, flags=re.IGNORECASE)
    # 5. Strip "and what makes..." type clauses
    topic = re.sub(r'\s+and\s+what\s+makes\s+.*$', '', topic, flags=re.IGNORECASE)
    
    # Clean the topic: use _extract_search_topic to get the core topic
    # This handles verbose slots like "the implementation of a four-day work week"
    # by extracting just "four-day work week" for better Wikipedia matching
    if len(topic) > 5:
        core_topic = _extract_search_topic(topic)
        if core_topic and len(core_topic) > 3 and len(core_topic) < len(topic):
            topic = core_topic
    # Also strip leading articles and verbose prefixes
    topic = re.sub(r'^(?:the\s+)?(?:concept\s+of\s+|idea\s+of\s+|implementation\s+of\s+|history\s+of\s+)', '', topic, flags=re.IGNORECASE)
    # Strip leading interrogatives and conditionals that get captured as part of the topic
    # e.g., "whether artificial intelligence can surpass..." -> "artificial intelligence"
    topic = re.sub(r'^(?:whether|if|that|how|what|why|when|where|who|which)\s+(?:it\s+)?(?:is\s+|are\s+|was\s+|were\s+|does\s+|do\s+|did\s+|can\s+|could\s+|would\s+|should\s+|will\s+|may\s+|might\s+|has\s+|have\s+|had\s+)?', '', topic, flags=re.IGNORECASE).strip()
    # Strip trailing modal/copula verbs that make Wikipedia search fail
    # e.g., "artificial intelligence can surpass" -> "artificial intelligence"
    topic = re.sub(r'\s+(?:can|could|would|should|will|may|might|is|are|was|were|has|have|had|does|do|did)\s+.*$', '', topic, flags=re.IGNORECASE)
    
    # Determine if this is a persuasive/argumentative essay for formatting
    q_lower = query.lower()
    is_persuasive = bool(re.search(r'persuasive|argumentative|argu(e|ing)', q_lower))
    is_comparison = bool(re.search(r'comparing|compare|comparative|contrast|versus|vs', q_lower))
    
    # Collect all content requirements
    content_parts = []
    
    # 1. First try KB lookup (curated content) before Wikipedia search
    try:
        from cos.knowledge import lookup as knowledge_lookup
        kb_content = knowledge_lookup(topic)
        if kb_content and len(kb_content) > 100:
            content_parts.append(kb_content)
    except Exception:
        pass
    
    # 2. If no KB content found, try Wikipedia
    if not content_parts:
        main_content = _retrieve_multi_content(topic, max_sources=3)
        if main_content and len(main_content) > 100:
            content_parts.append(main_content)
    
    # Note: Additional requirement-specific content lookup is disabled because
    # it often returns irrelevant Wikipedia definitions (e.g., "Politics is the
    # activity of...") that contaminate the response. The main topic content
    # above provides sufficient coverage.
    
    # Combine all content
    if content_parts:
        combined = '\n\n'.join(content_parts)
        cleaned = _make_conversational(combined)
        return _format_as_essay(cleaned, topic)
    
    result = _handle_factual(query, True)
    if result:
        return _format_as_essay(result, topic)
    return result


def _handle_html_page(query: str, slots: Dict[str, str]) -> str:
    """Create an HTML page using the inline template generator.
    
    Handles multi-requirement HTML requests (topic, style, features, sections).
    Generates a complete, responsive HTML page inline with masonry gallery,
    contact form, and style-aware colors.
    """
    from cos.engine import _handle_factual
    
    topic = slots.get('topic', 'web page')
    style = slots.get('style', '')
    features = slots.get('features', '')
    
    # Generate HTML page directly using topic
    topic_title = topic.title() if topic else 'Web Page'
    
    # Determine if the user requested specific layout features
    q_lower = query.lower()
    needs_masonry = 'masonry' in q_lower or 'gallery' in q_lower or 'portfolio' in q_lower
    needs_form = 'contact' in q_lower or 'form' in q_lower
    
    # Determine accent color based on style (if provided)
    accent_color = '#8ab4f8'
    bg_color = '#0a0a2e'
    card_bg = '#1a1a3e'
    style_lower = style.lower().strip() if style else ''
    if style_lower:
        if 'dark' in style_lower:
            accent_color = '#bb86fc'
            bg_color = '#121212'
            card_bg = '#1e1e1e'
        elif 'light' in style_lower or 'white' in style_lower:
            accent_color = '#1976d2'
            bg_color = '#f5f5f5'
            card_bg = '#ffffff'
        elif 'gold' in style_lower:
            accent_color = '#ffd700'
            bg_color = '#1a1410'
            card_bg = '#2a2018'
        elif 'nature' in style_lower or 'green' in style_lower:
            accent_color = '#4caf50'
            bg_color = '#1b2e1b'
            card_bg = '#1e3a1e'
        elif 'minimal' in style_lower:
            accent_color = '#333333'
            bg_color = '#ffffff'
            card_bg = '#f0f0f0'
    
    # Detect page type for content adaptation
    q_lower_for_type = query.lower()
    # Check for topic-specific pages (history, about, info) BEFORE portfolio
    is_topic_page = 'history of' in q_lower_for_type or 'about the history' in q_lower_for_type or 'about the' in q_lower_for_type
    is_city_page = ('city' in q_lower_for_type or 'town' in q_lower_for_type) and not is_topic_page
    is_landing_page = 'landing' in q_lower_for_type or 'coming soon' in q_lower_for_type or 'startup' in q_lower_for_type
    is_portfolio = ('portfolio' in q_lower_for_type or 'photograph' in q_lower_for_type or 'artist' in q_lower_for_type or 'illustrat' in q_lower_for_type) and not is_topic_page
    
    # Detect fictional/creative pages (skip Wikipedia for these)
    q_lower_for_fiction = query.lower()
    is_fictional = ('fictional' in q_lower_for_fiction or 'futuristic' in q_lower_for_fiction or 
                    'cyberpunk' in q_lower_for_fiction or 'imagine' in q_lower_for_fiction or
                    'made up' in q_lower_for_fiction)
    
    if is_topic_page or is_city_page:
        # Extract clean topic name for display (removing leading 'the history of' etc)
        clean_title = topic_title
        clean_title = re.sub(r'^(The History Of|The Story Of|About) ', '', clean_title, flags=re.IGNORECASE).strip()
        header_subtitle = f'Discover the story of {clean_title}'
        about_heading = f'About {clean_title}'
        about_text = f'{clean_title} is a fascinating subject with deep historical roots and cultural significance. This page provides an overview of its key aspects, developments, and lasting impact.'
        services_heading = 'Key Aspects'
        services_texts = ['Historical Background', 'Cultural Impact', 'Modern Significance']
        services_section_id = 'key-aspects'
        services_nav_label = 'Key Aspects'
        footer_text = f'Learn more about {clean_title}'
        # Try to enrich with real content from KB/Wikipedia (skip for fictional)
        if not is_fictional:
            try:
                from cos.engine import _retrieve_multi_content
                real_content = _retrieve_multi_content(clean_title, max_sources=1)
                if real_content and len(real_content) > 150:
                    first_para = real_content.split('\n')[0][:500]
                    if len(first_para) > 50:
                        about_text = first_para
            except Exception:
                pass
    elif is_portfolio:
        header_subtitle = 'Creative professional specializing in unique visual experiences'
        about_heading = 'About Me'
        about_text = 'I am a dedicated creative professional with a passion for delivering exceptional work. My approach combines artistic vision with technical precision to create unique and memorable experiences.'
        services_heading = 'Services'
        services_texts = ['Creative Direction', 'Project Management', 'Technical Excellence']
        services_section_id = 'services'
        services_nav_label = 'Services'
        footer_text = f'&copy; 2025 {topic_title}. All rights reserved.'
    else:
        header_subtitle = f'Welcome to the official page for {topic_title}'
        about_heading = f'About {topic_title}'
        about_text = f'A comprehensive overview of {topic_title} covering its main features and characteristics.'
        services_heading = 'Features'
        services_texts = ['Key Highlights', 'Core Offerings', 'Additional Resources']
        services_section_id = 'features'
        services_nav_label = 'Features'
        footer_text = f'&copy; 2025 {topic_title}. All rights reserved.'
    
    # Build gallery section if requested
    gallery_section = ''
    if needs_masonry:
        gallery_section = f'''
        <section class="gallery">
            <h2 style="text-align:center;color:{accent_color};padding:40px 0 20px;">Gallery</h2>
            <div class="masonry">
                <div class="masonry-item"><img src="https://picsum.photos/seed/1/400/300" alt="Project 1" loading="lazy"><div class="overlay"><h3>Project 1</h3></div></div>
                <div class="masonry-item"><img src="https://picsum.photos/seed/2/400/500" alt="Project 2" loading="lazy"><div class="overlay"><h3>Project 2</h3></div></div>
                <div class="masonry-item"><img src="https://picsum.photos/seed/3/400/400" alt="Project 3" loading="lazy"><div class="overlay"><h3>Project 3</h3></div></div>
                <div class="masonry-item"><img src="https://picsum.photos/seed/4/400/350" alt="Project 4" loading="lazy"><div class="overlay"><h3>Project 4</h3></div></div>
                <div class="masonry-item"><img src="https://picsum.photos/seed/5/400/600" alt="Project 5" loading="lazy"><div class="overlay"><h3>Project 5</h3></div></div>
                <div class="masonry-item"><img src="https://picsum.photos/seed/6/400/450" alt="Project 6" loading="lazy"><div class="overlay"><h3>Project 6</h3></div></div>
            </div>
        </section>'''
    
    # Build contact form if requested
    contact_section = ''
    if needs_form:
        contact_section = f'''
        <section class="contact">
            <h2 style="text-align:center;color:{accent_color};padding:40px 0 20px;">Contact</h2>
            <form class="contact-form" action="#" method="post">
                <input type="text" name="name" placeholder="Your Name" required>
                <input type="email" name="email" placeholder="Your Email" required>
                <textarea name="message" placeholder="Your Message" rows="5" required></textarea>
                <button type="submit">Send Message</button>
            </form>
        </section>'''
    
    # Build the complete HTML page with gallery and contact sections  
    html = f'''Here is a complete, responsive HTML page for {topic_title}:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{topic_title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: {bg_color};
            color: #e0e0e0;
            line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        header {{
            background: linear-gradient(135deg, {card_bg}, {bg_color});
            padding: 60px 20px;
            text-align: center;
        }}
        header h1 {{ font-size: 2.5em; color: {accent_color}; margin-bottom: 10px; }}
        nav {{
            background: {card_bg};
            padding: 15px 0;
            position: sticky;
            top: 0;
            z-index: 100;
        }}
        nav ul {{ list-style: none; display: flex; justify-content: center; gap: 30px; flex-wrap: wrap; }}
        nav a {{ color: {accent_color}; text-decoration: none; font-weight: 500; }}
        nav a:hover {{ color: #fff; }}
        .masonry {{ column-count: 3; column-gap: 15px; padding: 20px 0; }}
        .masonry-item {{ break-inside: avoid; margin-bottom: 15px; background: {card_bg}; border-radius: 8px; overflow: hidden; position: relative; }}
        .masonry-item img {{ width: 100%; display: block; }}
        .overlay {{ position: absolute; bottom: 0; left: 0; right: 0; background: rgba(0,0,0,0.7); padding: 10px; }}
        .overlay h3 {{ color: {accent_color}; font-size: 0.9em; }}
        .contact-form {{ max-width: 600px; margin: 0 auto; padding: 20px 0; }}
        .contact-form input, .contact-form textarea {{ width: 100%; padding: 12px; margin-bottom: 15px; background: {card_bg}; border: 1px solid #444; border-radius: 5px; color: #fff; }}
        .contact-form button {{ background: {accent_color}; color: #fff; padding: 12px 30px; border: none; border-radius: 5px; cursor: pointer; }}
        footer {{ text-align: center; padding: 20px; background: {card_bg}; color: #666; }}
        @media (max-width: 768px) {{ header h1 {{ font-size: 1.8em; }} nav ul {{ flex-direction: column; align-items: center; gap: 10px; }} .masonry {{ column-count: 2; }} }}
        @media (max-width: 480px) {{ .masonry {{ column-count: 1; }} }}
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1>{topic_title}</h1>
            <p>{header_subtitle}</p>
        </div>
    </header>
    <nav>
        <ul>
            <li><a href="#about">About</a></li>
            <li><a href="#{services_section_id}">{services_nav_label}</a></li>
            <li><a href="#contact">Contact</a></li>
        </ul>
    </nav>
    <main class="container">
        <section id="about">
            <h2 style="color:{accent_color};margin:40px 0 20px;">{about_heading}</h2>
            <p>{about_text}</p>
        </section>
        <section id="{services_section_id}">
            <h2 style="color:{accent_color};margin:40px 0 20px;">{services_heading}</h2>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px;">
                <div style="background:{card_bg};padding:20px;border-radius:8px;"><h3 style="color:{accent_color};">{services_texts[0]}</h3><p style="color:#bbb;">{services_texts[0]}</p></div>
                <div style="background:{card_bg};padding:20px;border-radius:8px;"><h3 style="color:{accent_color};">{services_texts[1]}</h3><p style="color:#bbb;">{services_texts[1]}</p></div>
                <div style="background:{card_bg};padding:20px;border-radius:8px;"><h3 style="color:{accent_color};">{services_texts[2]}</h3><p style="color:#bbb;">{services_texts[2]}</p></div>
            </div>
        </section>
        {gallery_section}
        {contact_section}
    </main>
    <footer>
        <p>{footer_text}</p>
    </footer>
</body>
</html>
```'''
    return html

    # Fallback to factual handler (only if all else fails)
    result = _handle_factual(query, True)
    if result:
        return result
    
    # Final generic response
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

def _handle_comparing_essay(query: str, slots: Dict[str, str]) -> str:
    """Write a comparative essay by retrieving Wikipedia content for both topics.
    
    Retrieves content for each topic separately and combines them into a
    comparative structure.
    """
    from cos.engine import (_retrieve_multi_content, _make_conversational,
                            _search_wikipedia, _handle_factual)
    
    topic1 = slots.get('topic1', slots.get('topic', ''))
    topic2 = slots.get('topic2', '')
    emphasis = slots.get('emphasis', '')
    
    if not topic1 and not topic2:
        return _handle_factual(query, True)
    
    parts = []
    
    # Get content for topic 1
    if topic1:
        content1 = _retrieve_multi_content(topic1, max_sources=2)
        if content1 and len(content1) > 50:
            parts.append(f"**{topic1.title()}**:\n{content1}")
        else:
            wiki1, _ = _search_wikipedia(topic1)
            if wiki1 and len(wiki1) > 50:
                parts.append(f"**{topic1.title()}**:\n{wiki1}")
    
    # Get content for topic 2
    if topic2:
        content2 = _retrieve_multi_content(topic2, max_sources=2)
        if content2 and len(content2) > 50:
            parts.append(f"**{topic2.title()}**:\n{content2}")
        else:
            wiki2, _ = _search_wikipedia(topic2)
            if wiki2 and len(wiki2) > 50:
                parts.append(f"**{topic2.title()}**:\n{wiki2}")
    
    if parts:
        combined = '\n\n'.join(parts)
        if emphasis:
            combined = f"**Comparison of {topic1.title()} and {topic2.title()}** (focusing on {emphasis}):\n\n{combined}"
        return _make_conversational(combined)
    
    return _handle_factual(query, True)


def _handle_poem(query: str, slots: Dict[str, str]) -> str:
    """Generate a poem about a topic."""
    from cos.engine import _search_wikipedia
    from cos.poem import generate_poem

    topic = slots.get('topic', '')
    if not topic:
        m = re.search(r'(?:about|on|for|covering|titled|called)\s+(.+?)(?:\.\s*|\?\s*|$)', query, re.IGNORECASE)
        if m:
            topic = m.group(1).strip()
    if not topic:
        topic = query.strip()

    wiki_summary, wiki_url = _search_wikipedia(topic)
    poem = generate_poem(topic, wiki_summary or '')
    source = f'\n  (inspired by Wikipedia)' if wiki_url else ''
    return f"A poem about {topic}:\n\n{poem}{source}"


_RESPONSE_HANDLERS = {
    'essay': _handle_essay,
    'html_page': _handle_html_page,
    'explanation': _handle_explanation,
    'code_function': _handle_code_function,
    'comparing_essay': _handle_comparing_essay,
    'poem': _handle_poem,
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
