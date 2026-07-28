"""Debug quantum computer engine response."""
import sys
sys.path.insert(0, 'src')
from cos.engine import process_query
resp = process_query('How does a quantum computer actually differ from a classical computer')
if resp:
    print(f'Length: {len(resp)}')
    # Check for fragmented search terms
    has_list = 'list of quantum' in resp.lower()[:300]
    has_fragments = '...' in resp[:200] or 'search' in resp[:200].lower()
    print(f'Has list: {has_list}')
    print(f'Has fragments: {has_fragments}')
    print(f'Preview: {resp[:300]}')
else:
    print('No response')
