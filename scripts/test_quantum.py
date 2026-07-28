"""Debug quantum entanglement response."""
import sys
sys.path.insert(0, 'src')

from cos.knowledge import reload, lookup
from cos.engine import _handle_factual, process_query

reload()

q = 'Write a detailed explanation of how quantum entanglement works'
print(f'Query: {q}')

# KB lookup
kb = lookup(q)
if kb:
    print(f'KB lookup length: {len(kb)} chars')
    has_scattering = 'scattering' in kb.lower()[:200]
    print(f'Contains Rayleigh: {has_scattering}')
    print(f'Preview: {kb[:200]}')
else:
    print('KB lookup: None')

# Engine
resp = process_query(q)
if resp:
    print(f'\nEngine response length: {len(resp)} chars')
    has_scattering = 'scattering' in resp.lower()[:300] or 'rayleigh' in resp.lower()[:300]
    print(f'Contains Rayleigh: {has_scattering}')
    print(f'Preview: {resp[:300]}')
else:
    print('Engine: None')
