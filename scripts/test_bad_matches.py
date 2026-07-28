"""Find bad KB matches."""
import sys
sys.path.insert(0, 'src')

from cos.knowledge import reload, lookup

reload()

# Test specific failing queries
tests = [
    'Write a detailed guide on how to start an indoor hydroponic garden',
    'Write a detailed explanation of how the James Webb Space Telescope works',
    'Create a complete HTML page for a fictional Cyberpunk Coffee Shop',
    'How do I use a CSS pseudo-element to create a custom bullet point',
    'Write a comparative essay on the impact of the Industrial Revolution',
]

for q in tests:
    result = lookup(q)
    if result:
        preview = result[:200].replace('\n', ' ').strip()
        has_michelin = 'michelin' in preview.lower()
        has_automation = 'automation' in preview.lower() or 'process' in preview.lower()
        has_travel = 'travel' in preview.lower() or 'agency' in preview.lower()
        issues = []
        if has_michelin: issues.append('MICHELIN')
        if has_automation: issues.append('AUTOMATION')
        if has_travel: issues.append('TRAVEL')
        status = f'ISSUES: {", ".join(issues)}' if issues else 'OK'
        print(f'  [{status}] {q[:60]}...')
        print(f'    -> {preview[:150]}...')
    else:
        print(f'  [MISS] {q[:60]}...')
