"""
COS Knowledge Base — Dynamically loads knowledge from data files.

Knowledge is stored as JSON files in data/knowledge/ organized by category:
  data/knowledge/
    science/       -- biology, physics, chemistry, food, human body
    geography/     -- capitals, countries, oceans, mountains
    history/       -- world events, famous people
    technology/    -- computers, internet, programming
    conversation/  -- greetings, small talk, common phrases
    general/       -- everything else

Each JSON file contains an array of entries:
  [{"q": ["question pattern 1", "pattern 2"], "a": "Answer text"}, ...]

To add knowledge: just create a new JSON file in the right category.
No code changes needed — it's loaded automatically at startup.
"""

import json
import os
import re
import glob
from pathlib import Path

# ── Knowledge directory ──────────────────────────────────────────────────────
# Path relative to this file: data/knowledge/
_KNOWLEDGE_DIR = Path(__file__).parent.parent.parent / 'data' / 'knowledge'


def _load_knowledge(base_dir=None):
    """Load all knowledge entries from the knowledge directory.

    Scans all .json files recursively, loads each entry, and returns
    a list of (compiled_regex, answer) tuples.

    Args:
        base_dir: Path to the knowledge directory. Defaults to data/knowledge/

    Returns:
        List of (pattern_regex, answer_text) tuples
    """
    if base_dir is None:
        base_dir = _KNOWLEDGE_DIR

    if not base_dir.exists():
        print(f"  Knowledge directory not found: {base_dir}")
        return []

    entries = []
    json_files = sorted(p for p in base_dir.rglob('*.json') if not p.name.startswith('.'))

    if not json_files:
        print(f"  No JSON knowledge files found in {base_dir}")
        return []

    for path in json_files:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  Warning: Could not load {path}: {e}")
            continue

        if not isinstance(data, list):
            print(f"  Warning: {path} should contain a JSON array")
            continue

        loaded = 0
        for entry in data:
            if not isinstance(entry, dict):
                continue
            questions = entry.get('q', entry.get('patterns', []))
            answer = entry.get('a', entry.get('answer', ''))

            if not questions or not answer:
                continue

            # If questions is a string, wrap in list
            if isinstance(questions, str):
                questions = [questions]

            # Compile patterns into regexes (case-insensitive)
            for q_text in questions:
                q_clean = q_text.strip()
                if not q_clean:
                    continue
                try:
                    # Check if pattern contains regex special characters
                    has_regex_chars = any(c in q_clean for c in '.*+?[](){}|\\^$')
                    if has_regex_chars:
                        # Use as-is (user wrote a regex)
                        regex = re.compile(q_clean, re.IGNORECASE)
                    else:
                        # Simple word/phrase match — use word boundaries to prevent
                        # 'hi' matching inside 'china' or 'this' matching inside 'history'
                        words = q_clean.split()
                        if len(words) == 1 and len(q_clean) <= 5:
                            # Single short word — use word boundary
                            regex = re.compile(r'\b' + re.escape(q_clean) + r'\b', re.IGNORECASE)
                        else:
                            # Multi-word phrase — use as escaped substring
                            regex = re.compile(re.escape(q_clean), re.IGNORECASE)
                    entries.append((regex, answer))
                    loaded += 1
                except re.error as e:
                    print(f'  Warning: Bad pattern "{q_clean}": {e}')
                    continue

        if loaded > 0:
            # Print category summary
            rel_path = path.relative_to(base_dir.parent.parent if base_dir == _KNOWLEDGE_DIR else base_dir)
            pass  # quiet load by default

    return entries

# ── Load knowledge at module import time ─────────────────────────────────────
_KNOWLEDGE_CACHE = None

def get_all_knowledge():
    """Get all loaded knowledge entries, caching after first load."""
    global _KNOWLEDGE_CACHE
    if _KNOWLEDGE_CACHE is None:
        _KNOWLEDGE_CACHE = _load_knowledge()
        if _KNOWLEDGE_CACHE:
            print(f"  Loaded {len(_KNOWLEDGE_CACHE)} knowledge entries from data/knowledge/")
    return _KNOWLEDGE_CACHE

def reload():
    """Force reload of all knowledge from disk."""
    global _KNOWLEDGE_CACHE
    _KNOWLEDGE_CACHE = None
    return get_all_knowledge()


def lookup(query):
    """Look up a query in the dynamic knowledge base.

    Matches against all loaded knowledge entries using regex.
    Returns the answer with the longest matching trigger, or None.
    This prevents short, generic triggers (e.g. "french") from
    overriding more specific ones (e.g. "french fries").

    Strips quotation marks and other common punctuation artifacts
    from the query before matching, so questions with quoted terms
    (e.g. How do headphones "erase" sound?) still match KB entries.

    Args:
        query: The user's question string

    Returns:
        Answer string if found, None otherwise
    """
    entries = get_all_knowledge()
    if not entries:
        return None

    # Strip common punctuation artifacts that can prevent matching
    q = query.lower().strip()
    # Remove quotation marks and normalize whitespace
    q = re.sub(r'[\"\'\'\"\u201c\u201d\u2018\u2019]', '', q)
    q = re.sub(r'\s+', ' ', q).strip()

    best_answer = None
    best_match_len = 0

    for pattern, answer in entries:
        m = pattern.search(q)
        if m:
            match_len = len(m.group(0))
            if match_len > best_match_len:
                best_match_len = match_len
                best_answer = answer

    return best_answer


# ── Statistics ───────────────────────────────────────────────────────────────

def stats():
    """Return statistics about the loaded knowledge base."""
    entries = get_all_knowledge()
    if not entries:
        return "No knowledge loaded."

    # Count by category
    categories = {}
    for path in sorted(p for p in _KNOWLEDGE_DIR.rglob('*.json') if not p.name.startswith('.')):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            cat = path.parent.name
            categories[cat] = categories.get(cat, 0) + len(data)
        except:
            pass

    result = f"Total entries: {len(entries)}\n"
    for cat, count in sorted(categories.items()):
        result += f"  {cat}: {count} entries\n"
    return result
