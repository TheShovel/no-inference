"""Debug Game Theory query."""
import sys
sys.path.insert(0, 'src')
from cos.knowledge import reload, lookup
from cos.engine import process_query, _handle_factual

reload()

q = 'Give me a deep dive into the concept of Game Theory as applied to economics'

# KB lookup
result = lookup(q)
if result:
    print(f'KB match: {len(result)} chars')
    print(f'Preview: {result[:200]}')
else:
    print('KB: No match')

# Engine
resp = process_query(q)
if resp:
    print(f'\nEngine: {len(resp)} chars')
    print(f'Preview: {resp[:200]}')
