"""Quick test of KB lookups and template system."""
import sys
sys.path.insert(0, 'src')

from cos.knowledge import lookup, stats
from cos.prompt_templates import _load_templates

print('Knowledge stats:')
print(stats())

# Test some lookups
tests = [
    'Why do we dream in stories instead of random images?',
    'How did people navigate the open ocean before modern instruments?',
    'What would happen to the Earth atmosphere if all plants disappeared?',
    'Tell me about the most mysterious unsolved manuscript ever discovered',
    'Why does time seem to speed up as we get older?',
    'How does a noise-canceling headphone erase sound?',
    'What is the philosophical argument for why there is something rather than nothing?',
    'Which city in the world has the most unique architecture?',
    'How do fungi communicate with each other underground?',
    'Why is it that some songs can instantly trigger a vivid memory?',
]
for q in tests:
    result = lookup(q)
    status = 'OK' if result and len(result) > 50 else 'MISS'
    print(f'  [{status}] {q[:60]}...')

# Test template loading
templates = _load_templates()
print(f'\nLoaded {len(templates)} prompt templates:')
for t in templates:
    print(f'  - {t.id} ({t.response_type}, {len(t.patterns)} patterns)')
