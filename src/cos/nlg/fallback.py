"""NLG Fallback Responses — natural responses when no information is available."""

from .config import NLGConfig
from .util import pick


_FALLBACK_HOW = [
    "I don't have a clear answer on how to do that yet. Could you give me a bit more detail?",
    "That's not something I know off the top of my head. Can you be more specific?",
]

_FALLBACK_GENERIC = [
    "I don't have enough details on that subject to give you a thorough answer right now.",
    "I wish I could give you a more complete answer, but I don't have reliable details on that yet.",
    "I'm not confident I can give you an accurate answer on that one yet. Can you tell me more?",
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
