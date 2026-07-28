"""Debug Ship of Theseus intent and KB matching."""
import sys
sys.path.insert(0, 'src')
from cos.intent import detect_intent
from cos.knowledge import reload, lookup
from cos.engine import process_query

reload()

q = 'What is the "Ship of Theseus" paradox and what does it say about identity?'
print(f'Query: {q}')
print(f'Intent: {detect_intent(q)}')

result = lookup(q)
if result:
    has_tracking = 'track their progress' in result.lower()[:200]
    print(f'KB match: {len(result)} chars, tracking={has_tracking}')
    print(f'Preview: {result[:200]}')
else:
    print('KB: No match')

resp = process_query(q)
if resp:
    has_tracking = 'track their progress' in resp.lower()[:200]
    print(f'Engine: {len(resp)} chars, tracking={has_tracking}')
    print(f'Preview: {resp[:200]}')
