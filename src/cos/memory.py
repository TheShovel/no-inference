"""
COS Fact Memory — Tracks user-stated facts across conversation turns.

Stores facts extracted from statements like:
  "I like pizza"  →  {interest: [pizza]}
  "I have a cat"  →  {pet: [cat]}
  "I use python"  →  {language: [python]}

Answers recall questions instantly without invoking the C pipeline.
"""

import re
from cos.state import fact_memory


def extract_and_store(query):
    """Extract facts from user statements and store in fact memory.

    Returns list of (key, value) fact tuples, or empty list if none found.
    """
    q = query.lower().strip()
    facts = []

    # Pattern: "I like/love/enjoy X"
    m = re.search(r'i (?:like|love|enjoy|am (?:a )?fan of)\s+(.+?)(?:\.|$)', q)
    if m:
        thing = m.group(1).strip().rstrip('.!?')
        if 'pizza' in thing: facts.append(('food', 'pizza'))
        elif 'program' in thing: facts.append(('activity', 'programming'))
        elif 'music' in thing: facts.append(('music', thing))
        elif 'game' in thing: facts.append(('game', thing))
        else: facts.append(('interest', thing))

    # Pattern: "I have a/an X"
    m = re.search(r'i have a(?:n)?\s+(.+?)(?:\.|$)', q)
    if m:
        thing = m.group(1).strip().rstrip('.!?')
        if 'cat' in thing: facts.append(('pet', 'cat'))
        elif 'dog' in thing: facts.append(('pet', 'dog'))
        else: facts.append(('possession', thing))

    # Pattern: "I use X"
    m = re.search(r'i use\s+(.+?)(?:\.|$)', q)
    if m:
        thing = m.group(1).strip().rstrip('.!?')
        if 'python' in thing: facts.append(('language', 'python'))
        else: facts.append(('tool', thing))

    # Pattern: "my favorite X is Y" or "my favorite X are Y"
    m = re.search(r'my favorite\s+(\w+)\s+(?:is|are)\s+(.+?)(?:\.|$)', q)
    if m:
        category = m.group(1).strip()
        thing = m.group(2).strip().rstrip('.!?')
        facts.append((f'favorite_{category}', thing))

    # Pattern: "I want X"
    m = re.search(r'i want\s+(?:an?\s+)?(.+?)(?:\.|$)', q)
    if m:
        thing = m.group(1).strip().rstrip('.!?')
        facts.append(('desire', thing))

    # Store facts
    for key, value in facts:
        if key not in fact_memory:
            fact_memory[key] = []
        if value not in fact_memory[key]:
            fact_memory[key].append(value)

    return facts


def recall(query):
    """Try to answer a memory recall question from fact memory.
    Returns a response string if found, None otherwise.
    """
    q = query.lower().strip()

    if not fact_memory:
        return None

    def _join(items):
        if not items:
            return None
        if len(items) == 1:
            return items[0]
        return ', '.join(items[:-1]) + ' and ' + items[-1]

    def _all_values():
        items = []
        for key, values in fact_memory.items():
            items.extend(values)
        return items

    # "what do I like" / "what do I enjoy"
    if re.search(r'what\s+do\s+i\s+(like|enjoy)', q):
        categories = ['food', 'interest', 'activity', 'hobby', 'music', 'game']
        all_interests = []
        for cat in categories:
            if cat in fact_memory:
                all_interests.extend(fact_memory[cat])
        if all_interests:
            return f'Based on our conversation, you like {_join(all_interests)}.'

    # "what language do I use" / "what tool do I use" / "what X do I use"
    m = re.search(r'what\s+(\w+)\s+do\s+i\s+use', q)
    if m:
        key = m.group(1)
        if key in fact_memory:
            return f'You use {_join(fact_memory[key])}.'
        key_s = key.rstrip('s')
        if key_s in fact_memory:
            return f'You use {_join(fact_memory[key_s])}.'

    # Generic: "what X do I..."
    m = re.search(r'what\s+(.+?)\s+do\s+i', q)
    if m:
        key = m.group(1).strip()
        if key in fact_memory:
            return f'Based on our conversation, your {key} is {_join(fact_memory[key])}.'
        key_s = key.rstrip('s')
        if key_s in fact_memory:
            return f'Based on our conversation, your {key_s} is {_join(fact_memory[key_s])}.'

    # "what is my favorite X"
    m = re.search(r'what\s+is\s+my\s+favorite\s+(\w+)', q)
    if m:
        key = f'favorite_{m.group(1)}'
        if key in fact_memory:
            return f'Your favorite {m.group(1)} is {_join(fact_memory[key])}.'

    # "do I have X" / "do I have a X"
    m = re.search(r'do\s+i\s+have\s+(?:a|an)?\s*(.+?)(?:\?|$)', q)
    if m:
        thing = m.group(1).strip().rstrip('.!?')
        for key, values in fact_memory.items():
            for v in values:
                if thing in v or v in thing:
                    return f'Yes, you have a {v}.'
        return f'I don\'t recall you having a {thing}.'

    # "what do I have"
    if re.search(r'what\s+do\s+i\s+have', q):
        possessions = []
        for key in ['possession', 'pet', 'tool']:
            if key in fact_memory:
                possessions.extend(fact_memory[key])
        if possessions:
            return f'You have {_join(possessions)}.'
        all_items = _all_values()
        if all_items:
            return f'You have {_join(all_items)}.'

    return None


def get_all_facts_text():
    """Return a human-readable summary of all stored facts."""
    if not fact_memory:
        return None
    items = []
    for key, values in fact_memory.items():
        items.extend(values)
    if not items:
        return None
    if len(items) == 1:
        return f'I remember you mentioned {items[0]} in our conversation.'
    joined = ', '.join(items[:-1]) + ' and ' + items[-1] if len(items) > 1 else items[0]
    return f'I remember you mentioned {joined} in our conversation.'
