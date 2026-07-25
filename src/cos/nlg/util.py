"""NLG Utilities — shared helper functions used across all pipeline stages."""

import re
import random
from typing import List


def pick(items: list, temp: float = 0.5) -> str:
    """Pick from list with temperature control. temp=0.0 = first item always."""
    if not items:
        return ""
    if temp <= 0.0:
        return items[0]
    return random.choice(items)


def maybe(prob: float) -> bool:
    """Return True with probability prob (0.0-1.0)."""
    return random.random() < prob


def split_sentences(text: str) -> List[str]:
    """Split text into sentences, preserving punctuation."""
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if p.strip()]


def lower_first(word: str) -> str:
    """Lowercase the first character."""
    if not word:
        return word
    return word[0].lower() + word[1:] if len(word) > 1 else word.lower()


def upper_first(text: str) -> str:
    """Uppercase the first character."""
    if not text:
        return text
    return text[0].upper() + text[1:] if len(text) > 1 else text.upper()


VALID_STYLES = {"friendly", "neutral", "concise", "witty"}


def require_style(config) -> str:
    """Get the config style, falling back to 'neutral' if invalid."""
    style = getattr(config, 'style', 'neutral')
    return style if style in VALID_STYLES else 'neutral'
