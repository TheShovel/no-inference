"""Test quantum computer KB matching."""
import sys
sys.path.insert(0, 'src')
from cos.knowledge import reload, lookup
reload()

q = 'How does a quantum computer actually differ from a classical computer'
result = lookup(q)
if result:
    print(f'KB match: {len(result)} chars')
    print(f'Preview: {result[:200]}')
else:
    print('KB: No match')
