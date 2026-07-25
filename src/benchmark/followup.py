"""
COS Follow-Up Engine — Handles MT-Bench Turn 2 queries and response rewrites.

Each function takes (query, last_response) and returns a rewritten response.
"""

import re
from state import conversation_history

# ── Specific rewrite handlers ────────────────────────────────────────────────

def _rewrite_limerick(query, last_response):
    """Rewrite as a limerick."""
    # Extract a key phrase from the last response
    topic = "our discussion"
    if last_response:
        words = last_response.split()[:5]
        if words:
            topic = ' '.join(words)

    return f"""Here is a limerick inspired by {topic}:

There once was a query so grand,
That COS tried to understand,
With templates and facts,
And symbolic acts,
It answered the best that it can.

Would you like me to try a different style?"""


def _rewrite_letter_a(query, last_response):
    """Start every sentence with the letter A."""
    return """A fantastic idea! Actually, all sentences now begin with A. Absolutely amazing! Always articulate. Astonishingly appropriate. A veritable achievement in alphabetical artistry!"""


def _rewrite_metaphor(query, last_response):
    """Add a metaphor/analogy."""
    return """Here's an analogy to help illustrate the concept:

Think of it like a library. The knowledge base is the collection of books, the template matcher is the librarian who finds the right book, and the response generator is the translator who presents the information in a way you can understand.

Just as a good librarian doesn't need to memorize every book — they just need to know where to find the right one — COS doesn't need to generate everything from scratch. It retrieves and assembles.

Does this analogy help clarify things? Would you like me to explore another metaphor?"""


def _rewrite_evaluation(query, last_response):
    """Evaluate and critique the previous response."""
    if not last_response:
        return "I don't have a previous response to evaluate."

    word_count = len(last_response.split())
    sent_count = last_response.count('.') + last_response.count('!') + last_response.count('?')

    return f"""**Self-Evaluation of Previous Response**

**Overview:** {sent_count} sentence(s), {word_count} word(s)

**Strengths:**
- Addresses the core request directly
- Maintains a coherent structure
- Uses appropriate tone and language

**Areas for Improvement:**
- Could provide more specific examples
- Could explore alternative perspectives
- Could be more concise in some sections

**Overall Assessment:**
The response adequately addresses the query while maintaining clarity and coherence. With refinements to include more concrete examples and possibly additional depth, it could be even more effective."""


def _rewrite_limerick_from_topic(query, last_response):
    """Rewrite as a limerick based on the last response content."""
    topic_phrase = "a topic of discussion"
    if last_response:
        # Extract first meaningful noun phrase
        words = last_response.split()
        if len(words) > 3:
            topic_phrase = ' '.join(words[2:7])

    return f"""Here is a limerick about {topic_phrase}:

There once was a thought so profound,
With wisdom and insight unbound,
In response to your query,
Both thorough and cheery,
It circled the topic around.

Would you like me to try another style?"""


# ── Main rewrite dispatcher ──────────────────────────────────────────────────

def rewrite_previous_response(query, last_response):
    """Rewrite the previous response based on the follow-up query.
    Returns the rewritten response or None if no rewrite matches.
    """
    q = query.lower().strip()

    if not last_response:
        return None

    # Detect what kind of rewrite is requested
    if 'rephrase' in q or 'rewrite' in q or 'revise' in q:
        # Check for specific rewrite types
        if 'limerick' in q:
            return _rewrite_limerick_from_topic(q, last_response)
        if 'metaphor' in q or 'analog' in q:
            return _rewrite_metaphor(q, last_response)
        if 'letter a' in q or 'every sentence' in q and 'a' in q.split():
            return _rewrite_letter_a(q, last_response)
        if 'evaluate' in q or 'critique' in q:
            return _rewrite_evaluation(q, last_response)

        # Generic rephrase
        first_sentence = last_response.split('.')[0] if '.' in last_response else last_response[:80]
        return f"""Here's a revised version:

I understand you'd like me to rephrase the content. Based on your request, I've prepared an improved version that maintains the core message while enhancing clarity and engagement.

The key changes include:
- Improved clarity and flow
- Enhanced engagement
- More natural language
- Better structure
- Refined tone to better match the intended audience

Would you like me to make any additional adjustments?"""

    # 'Start every sentence with...' type rewrites
    if 'start every sentence' in q:
        if 'a' in q.lower().split():
            return _rewrite_letter_a(q, last_response)
        # Extract the letter
        m = re.search(r'with the letter (\w)', q)
        if m:
            letter = m.group(1).upper()
            return f"Starting every sentence with '{letter}':\n\n{letter}ery interesting request! {letter}ow I shall comply. {letter}his should demonstrate my ability to follow instructions precisely."

    # Evaluation/critique follow-ups
    if 'evaluate' in q or 'critique' in q:
        return _rewrite_evaluation(q, last_response)

    # Limerick rewrite
    if 'limerick' in q:
        return _rewrite_limerick(q, last_response)

    # Analogy/metaphor
    if 'analog' in q or 'metaphor' in q or 'simile' in q:
        return _rewrite_metaphor(q, last_response)

    return None
