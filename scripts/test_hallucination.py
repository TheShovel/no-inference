"""Test hallucination detection."""
import sys
sys.path.insert(0, 'src')

from cos.engine import process_query, _detect_false_premise

# Test hallucination detection
tests = [
    "Why is the sky green?",
    "How does a perpetual motion machine work?",
    "Is it true that humans only use 10% of their brain?",
    "Why do birds fly underwater?",
    "What is a perpetual energy device?",
    "Tell me about the flat earth theory",
    "Do vaccines cause autism?",
    "How does the five-second rule work?",
    "Why is the sky purple during the day?",
]

print("=== Hallucination Detection ===\n")
for q in tests:
    resp = _detect_false_premise(q)
    if resp:
        preview = resp[:120].replace('\n', ' ').strip()
        print(f"  Q: {q}")
        print(f"  R: {preview}...")
    else:
        print(f"  Q: {q}")
        print(f"  R: [Not detected]")
    print()

# Test non-hallucination queries (should NOT be flagged)
normal_tests = [
    "Why is the sky blue?",
    "How does a refrigerator work?",
    "Tell me about the Roman Empire",
]

print("=== Normal Queries (should NOT be flagged) ===\n")
for q in normal_tests:
    resp = _detect_false_premise(q)
    if resp:
        print(f"  [FALSE POSITIVE!] {q} -> {resp[:80]}")
    else:
        print(f"  [OK] {q} -> Not detected (correct)")
