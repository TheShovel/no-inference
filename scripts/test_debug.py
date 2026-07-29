"""Debug failing queries."""
import sys
sys.path.insert(0, 'src')
from cos.engine import process_query
queries = [
    'What is the Fermi Paradox and why does it suggest we have not found aliens?',
    'Write a detailed explanation of how quantum entanglement works',
    'What actually happens to the light that falls into a black hole',
]
for q in queries:
    resp = process_query(q)
    if resp:
        has_tracking = 'track their progress' in resp.lower()[:200]
        has_scattering = 'scattering' in resp.lower()[:200]
        print(f'Q: {q[:50]}...')
        print(f'  Tracking: {has_tracking}, Scattering: {has_scattering}')
        print(f'  [{len(resp)} chars] {resp[:150]}...')
    else:
        print(f'Q: {q[:50]}... None')
