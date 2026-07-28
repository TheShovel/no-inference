"""Test HTML page generation."""
import sys
sys.path.insert(0, 'src')

from cos.code_knowledge import code_lookup, is_coding_query
from cos.engine import process_query

# Test queries
tests = [
    'Create a single-page HTML portfolio for a freelance photographer',
    'Create a complete HTML and CSS page for a fictional Cyberpunk Cafe',
    'Create a single-file HTML page about the solar system with a dark space theme',
]

for q in tests:
    print(f'\n=== Q: {q} ===')
    
    # Check if it's detected as coding
    coding = is_coding_query(q)
    print(f'  is_coding: {coding}')
    
    # Try code_lookup
    result = code_lookup(q)
    if result:
        print(f'  code_lookup returns: {len(result)} chars')
        # Check for code block completeness
        opening = result.count('```')
        print(f'  Code fences: {opening}')
        if opening > 0 and opening % 2 != 0:
            print(f'  *** UNCLOSED CODE BLOCK! ***')
        # Show last 200 chars
        print(f'  Ends with: ...{result[-200:]}')
    else:
        print(f'  code_lookup: None')
    
    # Try process_query
    resp = process_query(q)
    if resp:
        print(f'  engine returns: {len(resp)} chars')
        opening = resp.count('```')
        print(f'  Code fences: {opening}')
        if opening > 0 and opening % 2 != 0:
            print(f'  *** UNCLOSED CODE BLOCK! ***')
    else:
        print(f'  engine: None')
