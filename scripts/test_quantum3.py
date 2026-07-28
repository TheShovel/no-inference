"""Debug quantum computer path."""
import sys
sys.path.insert(0, 'src')
from cos.intent import detect_intent
from cos.engine import process_query
from cos.knowledge import reload, lookup

reload()

q = 'How does a quantum computer actually differ from a classical computer'
print(f'Intent: {detect_intent(q)}')

result = lookup(q)
if result:
    print(f'KB: {len(result)} chars - {result[:100]}')
else:
    print('KB: No match')

resp = process_query(q)
if resp:
    print(f'Engine: {len(resp)} chars - {resp[:200]}')
else:
    print('Engine: None')
