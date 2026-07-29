"""Debug quantum entanglement."""
import sys
sys.path.insert(0, 'src')
from cos.knowledge import reload, lookup
reload()
q = 'Write a detailed explanation of how quantum entanglement works'
result = lookup(q)
if result:
    has_scattering = 'scattering' in result.lower()[:200]
    print(f'KB: {len(result)} chars, scattering={has_scattering}')
    print(f'Preview: {result[:200]}')
else:
    print('KB: No match')
