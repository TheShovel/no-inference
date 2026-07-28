"""Debug Fermi Paradox"""
import sys
sys.path.insert(0, 'src')

from cos.knowledge import reload, lookup

reload()

q = 'What is the "Fermi Paradox" and why is it significant?'
result = lookup(q)
if result:
    print(f'Match found: {len(result)} chars')
    has_kpi = 'kpi' in result.lower()[:200]
    has_tracking = 'track their progress' in result.lower()[:200]
    print(f'Contains KPI: {has_kpi}')
    print(f'Contains tracking: {has_tracking}')
    print(f'Preview: {result[:300]}')
else:
    print('No KB match')

# Try engine
from cos.engine import process_query
resp = process_query(q)
if resp:
    has_kpi = 'kpi' in resp.lower()[:200]
    has_tracking = 'track their progress' in resp.lower()[:200]
    print(f'\nEngine response: {len(resp)} chars')
    print(f'Contains KPI: {has_kpi}')
    print(f'Contains tracking: {has_tracking}')
    print(f'Preview: {resp[:300]}')
