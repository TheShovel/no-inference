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
