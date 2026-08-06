"""
COS Shared State — Global state accessible across all orchestrator modules.

Each module imports what it needs. No circular dependencies.
"""

# Conversation context for multi-turn queries
conversation_history = []      # List of (query, response) tuples
current_roleplay = None        # Current roleplay persona, if any

# Structured fact memory: maps attribute -> value
# E.g., {"food": ["pizza"], "pet": ["cat"], "language": ["python"]}
fact_memory = {}

# Long-running processes (the API server) accumulate a turn per query, so
# keep only the most recent turns: enough for multi-turn follow-ups, not
# enough to grow without bound.
MAX_TURNS = 200


def trim_conversation(limit: int = MAX_TURNS) -> None:
    """Keep only the last `limit` turns of conversation history."""
    if len(conversation_history) > limit:
        del conversation_history[:-limit]
