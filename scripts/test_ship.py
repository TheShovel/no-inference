"""Quick test of specific queries that failed in benchmark."""
import sys
sys.path.insert(0, 'src')

from cos.knowledge import reload, lookup

# Force reload knowledge
reload()

# Test Ship of Theseus - check if it's the KB entry or the template
q = 'What is the "Ship of Theseus" paradox and how does it relate to our modern understanding of identity?'
result = lookup(q)
if result:
    has_tracking = 'track their progress' in result.lower()
    print(f'Ship of Theseus KB lookup:')
    print(f'  Contains tracking: {has_tracking}')
    print(f'  Preview: {result[:150]}')
else:
    print(f'Ship of Theseus: No KB match')

# Also test via engine
from cos.engine import process_query
resp = process_query(q)
has_tracking = 'track their progress' in resp.lower() if resp else False
print(f'\nEngine response:')
print(f'  Contains tracking: {has_tracking}')
print(f'  Preview: {resp[:200] if resp else "None"}...')
