"""
COS Pattern Loader — Loads social/emotional response patterns from data/patterns/*.json.

Each JSON file contains categories with:
  - patterns: list of regex strings
  - response: string or list of strings (random choice if list)

Patterns are matched by category priority (first match wins).
"""

import json
import os
import random
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

_PATTERNS_DIR = Path(__file__).parent.parent.parent / 'data' / 'patterns'
_CACHE: Optional[List[Tuple[str, re.Pattern, Union[str, List[str]]]]] = None


def _load_all():
    """Load all pattern files from data/patterns/ directory."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    entries = []
    if not _PATTERNS_DIR.exists():
        _PATTERNS_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE = []
        return []

    for path in sorted(_PATTERNS_DIR.glob('*.json')):
        if path.name.startswith('.'):
            continue
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"  Warning: Could not load {path}: {e}")
            continue

        if not isinstance(data, dict):
            continue

        for category, info in data.items():
            if category.startswith('_'):
                continue
            patterns = info.get('patterns', [])
            response = info.get('response', '')
            if not patterns or not response:
                continue
            for p in patterns:
                try:
                    regex = re.compile(p, re.IGNORECASE)
                    entries.append((category, regex, response))
                except re.error:
                    continue

    _CACHE = entries
    return entries


def reload():
    """Force reload all patterns from disk."""
    global _CACHE
    _CACHE = None
    return _load_all()


def match_pattern(query: str) -> Optional[str]:
    """Check if a query matches any social pattern.
    
    Returns a response string if matched, None otherwise.
    """
    entries = _load_all()
    if not entries:
        return None

    q = query.lower().strip().rstrip('!?.,;: ')
    if not q:
        return None

    for category, regex, response in entries:
        if regex.search(q):
            if isinstance(response, list):
                return random.choice(response)
            return response

    return None


def get_stats() -> str:
    """Return statistics about loaded patterns."""
    entries = _load_all()
    categories = {}
    for cat, _, _ in entries:
        categories[cat] = categories.get(cat, 0) + 1
    result = f"Total patterns: {len(entries)}\n"
    for cat, count in sorted(categories.items()):
        result += f"  {cat}: {count}\n"
    return result
