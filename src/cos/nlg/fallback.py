"""NLG Fallback Responses — natural responses when no information is available."""

from .config import NLGConfig
from .util import pick


_FALLBACK_HOW = [
    "I don't have a clear answer on how to do that yet. Could you give me a bit more detail?",
    "That's not something I know off the top of my head. Can you be more specific?",
]

_FALLBACK_GENERIC = [
    "I'm not sure I have the information to answer that. Could you rephrase your question?",
    "I don't have a great answer for that one. Can you ask it a different way?",
    "Hmm, I'm drawing a blank on that. What else can I help you with?",
    "Good question, but I don't have the details handy. Can you narrow it down?",
]

_FALLBACK_MATH = [
    "Hmm, I'm not sure about that calculation. Could you double-check the numbers?",
    "I can't quite figure that one out. Can you rephrase the problem?",
]


def fallback_response(query: str, config: NLGConfig) -> str:
    """Generate a natural response when no information is available.

    Pure function.

    Args:
        query: The original user query (for intent detection).
        config: NLG configuration.

    Returns:
        A natural fallback response string.
    """
    q = query.lower().strip()

    if any(p in q for p in ['how do i', 'how can i', 'how to', 'how would i']):
        return pick(_FALLBACK_HOW, config.temperature)

    if any(p in q for p in ['+', '-', '*', '/', '^']) and any(p in q for p in ['what is', 'calculate']):
        import re
        if re.search(r'\d', q):
            return pick(_FALLBACK_MATH, config.temperature)

    return pick(_FALLBACK_GENERIC, config.temperature)
