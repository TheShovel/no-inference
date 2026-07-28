"""Test specific failing queries."""
import sys
sys.path.insert(0, 'src')

from cos.knowledge import reload, lookup
from cos.engine import process_query

reload()

queries = [
    'What is the Ship of Theseus thought experiment and what does it imply about identity?',
    'How does a quantum computer actually differ from a classical computer?',
    'Tell me about the history of the Voynich Manuscript and why it is still unsolved',
    'Create a single-page HTML portfolio for a freelance photographer',
]
for q in queries:
    result = lookup(q)
    if result:
        has_tracking = 'track their progress' in result.lower()[:200]
        has_list = result.startswith('List of') or 'list of quantum' in result.lower()[:200]
        status = 'OK' if not has_tracking and not has_list else 'BAD'
        print(f'KB: [{status}] ({len(result)} chars) - {result[:100]}')
    else:
        print(f'KB: MISS')

for q in queries:
    resp = process_query(q)
    if resp:
        has_tracking = 'track their progress' in resp.lower()[:200]
        has_list = 'list of quantum' in resp.lower()[:200]
        truncated = '```' in resp and resp.count('```') % 2 != 0
        issues = []
        if has_tracking: issues.append('TRACKING')
        if has_list: issues.append('LIST')
        if truncated: issues.append('TRUNCATED')
        status = 'OK' if not issues else 'ISSUES: ' + ', '.join(issues)
        print(f'Engine: [{status}] ({len(resp)} chars) - {resp[:120]}')
    else:
        print(f'Engine: MISS')
