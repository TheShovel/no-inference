"""Test word-overlap fallback."""
import sys
sys.path.insert(0, 'src')
from cos.knowledge import reload, lookup

reload()

queries = [
    'Write a comprehensive guide to the fall of the Roman Empire.',
    'What is the Fermi Paradox and why does it suggest we might not find aliens?',
    'Write me an essay about the ethics of CRISPR gene editing in humans.',
    'Create a landing page for a futuristic coffee shop using HTML.',
    'Write a detailed explanation of how quantum entanglement works.',
]

for q in queries:
    result = lookup(q)
    if result:
        has_tracking = 'track their progress' in result.lower()[:200]
        has_scattering = 'scattering' in result.lower()[:200]
        print(f'Q: {q[:60]}...')
        print(f'  Match: {len(result)} chars, tracking={has_tracking}, scattering={has_scattering}')
        print(f'  Preview: {result[:150]}')
    else:
        print(f'Q: {q[:60]}...')
        print(f'  Match: None')
