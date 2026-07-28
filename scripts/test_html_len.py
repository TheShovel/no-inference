"""Test HTML response length."""
import sys
sys.path.insert(0, 'src')
from cos.engine import process_query

q = 'Create a single-file HTML page about the history of Jazz. Use a dark theme with musical note decorations.'
resp = process_query(q)
if resp:
    print(f'Response length: {len(resp)} chars')
    print(f'Has code fence: {"```" in resp}')
    if resp.count('```') > 0:
        print(f'Code fences: {resp.count("```")}')
        print(f'Even fences: {resp.count("```") % 2 == 0}')
    # Show last 300 chars
    print(f'Ends with: ...{resp[-300:]}')
else:
    print('No response')
