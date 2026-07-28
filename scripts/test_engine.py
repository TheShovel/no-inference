"""Test the engine with specific queries."""
import sys
sys.path.insert(0, 'src')

from cos.engine import process_query, _handle_factual, _extract_search_topic, _clean_topic

# Test topic extraction
tests = [
    'Tell me about the philosophy of Stoicism and how it differs from Epicureanism',
    'What is the most isolated city in the world and why is it so hard to get to?',
    'Give me a detailed explanation of how quantum entanglement works',
    'Write me an essay about the fall of the Roman Empire. Make sure it covers the key events and discusses the main causes.',
    'Why is it that some songs can instantly trigger a vivid memory?',
]

print('=== Topic extraction ===')
for q in tests:
    topic = _extract_search_topic(q)
    clean = _clean_topic(topic)
    print(f'  Q: {q[:70]}...')
    print(f'  Topic: {topic}')
    print(f'  Clean: {clean}')
    print()

# Test actual responses (skip for now to save time)
# print('=== Quick responses ===')
# for q in tests[:2]:
#     resp = process_query(q)
#     print(f'  Q: {q[:60]}...')
#     print(f'  R: {resp[:200]}...' if resp else '  R: None')
#     print()
