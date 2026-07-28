"""Debug Ship of Theseus thoroughly."""
import sys
sys.path.insert(0, 'src')

from cos.knowledge import reload, lookup, get_all_knowledge
from cos.intent import detect_intent

reload()

q = 'What is the "Ship of Theseus" paradox and how does it apply to modern identity?'

# Check intent
intent = detect_intent(q)
print(f'Intent: {intent}')

# Check KB
result = lookup(q)
if result:
    has_tracking = 'track their progress' in result.lower()[:200] or 'kpi' in result.lower()[:200]
    print(f'KB match: {len(result)} chars, has_tracking={has_tracking}')
    print(f'Preview: {result[:200]}')
else:
    print('KB match: None')

# Check if any pattern matches corporate tracking
entries = get_all_knowledge()
for pat, ans in entries:
    if 'track their progress' in ans.lower() or 'kpi' in ans.lower() or 'milestone' in ans.lower():
        if pat.search(q):
            print(f'BAD MATCH: pattern={pat.pattern}')
            print(f'  answer={ans[:150]}')
            break
else:
    print('No bad pattern matches')

# Try engine
from cos.engine import process_query
resp = process_query(q)
if resp:
    has_tracking = 'track their progress' in resp.lower()[:200] or 'kpi' in resp.lower()[:200]
    print(f'Engine: {len(resp)} chars, has_tracking={has_tracking}')
    print(f'Preview: {resp[:200]}')
