"""Debug northern lights query."""
import sys
sys.path.insert(0, 'src')
from cos.knowledge import reload, lookup
reload()
q = 'What causes the Northern Lights and why can they sometimes be seen at lower latitudes?'
result = lookup(q)
if result:
    print(f'KB: {len(result)} chars')
    has_html = '```' in result or 'html' in result.lower()[:100]
    print(f'Contains HTML: {has_html}')
    print(f'Preview: {result[:200]}')
else:
    print('KB: No match')
