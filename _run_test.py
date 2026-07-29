import sys
sys.path.insert(0, 'src')
from cos.engine import process_query, reset_conversation

reset_conversation()

for i, q in enumerate([
    "Tell me about the history of jazz music",
    "Who were the key pioneers?",  
    "What instruments are typically used?",
    "Tell me more about Miles Davis",
    "What album should I start with?",
    "How did his style change over his career?",
    "What other musicians were in his Kind of Blue session?",
]):
    print(f"\n--- TURN {i+1}: {q} ---")
    r = process_query(q)
    print(r[:500] if r else "[None]")
