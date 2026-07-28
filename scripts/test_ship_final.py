"""Debug Ship of Theseus."""
import sys
sys.path.insert(0, 'src')
from cos.knowledge import reload, lookup
from cos.engine import process_query

reload()

q = 'What is the Ship of Theseus paradox and how does it apply to personal identity?'
result = lookup(q)
if result:
    has_tracking = 'track their progress' in result.lower()[:200]
    print(f'KB: {len(result)} chars, tracking={has_tracking}')
    print(f'Preview: {result[:200]}')
else:
    print('KB: No match')

resp = process_query(q)
if resp:
    has_tracking = 'track their progress' in resp.lower()[:200]
    print(f'Engine: {len(resp)} chars, tracking={has_tracking}')
    print(f'Preview: {resp[:200]}')
