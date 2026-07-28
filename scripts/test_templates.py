"""Test if templates are still in KB."""
import sys
sys.path.insert(0, 'src')

from cos.knowledge import reload, lookup, get_all_knowledge

# Force reload
reload()

# Test Fermi Paradox
q = 'What is the "Fermi Paradox" and why does it suggest we have not found aliens?'
result = lookup(q)
if result:
    has_kpi = 'kpi' in result.lower() or 'track their progress' in result.lower() or 'milestone' in result.lower()
    print(f'Fermi Paradox result:')
    print(f'  Contains business tracking: {has_kpi}')
    print(f'  Preview: {result[:200]}')
else:
    print('Fermi Paradox: No KB match')

# Check if any templates have "what is" as a trigger
print('\nChecking what entries contain "what is":')
entries = get_all_knowledge()
matches = []
for pattern, answer in entries:
    pat_str = pattern.pattern
    if 'what is' in pat_str.lower() and len(pat_str) < 30:
        matches.append((pat_str, answer[:100]))
        if len(matches) > 10:
            break
for p, a in matches:
    print(f'  Pattern: {p}')
    print(f'  Answer preview: {a}')

# Count template entries
print(f'\nTotal entries: {len(entries)}')
template_count = sum(1 for p, a in entries if '/templates/' in str(p) or '.json' not in str(p))
print(f'Template entries (estimated): {template_count}')
