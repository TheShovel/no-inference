"""Test the newly added KB entries and fixes."""
import sys
sys.path.insert(0, 'src')

from cos.knowledge import lookup, reload

# Force reload knowledge to pick up new files
reload()

# Test the specific failing queries
tests = {
    'Ship of Theseus': 'What is the "Ship of Theseus" paradox and how does it relate to our modern understanding of identity?',
    'Doorway Effect': 'Why is it that we forget why we entered a room the moment we walk through a doorway?',
    'Python String Reverse': 'Write a Python function that takes a string and returns it in reverse',
    'Persuasive Essay AI': 'Write me a persuasive essay arguing whether artificial intelligence will surpass human intelligence in our lifetime',
}

from cos.engine import process_query

for name, q in tests.items():
    try:
        resp = process_query(q)
        if resp:
            # Check for the "failed" indicators
            has_corporate_tracking = 'track their progress' in resp.lower() or 'corporate tracking' in resp.lower()
            has_walking_def = 'gaits of terrestrial' in resp.lower() or 'inverted pendulum' in resp.lower()
            has_csv = 'csv' in resp.lower() and 'reverse' not in resp.lower()
            has_template = "couldn't find enough information" in resp.lower() or 'academic topic' in resp.lower()
            
            issues = []
            if has_corporate_tracking:
                issues.append('CORPORATE TRACKING FOUND')
            if has_walking_def:
                issues.append('WALKING DEFINITION FOUND')
            if has_csv:
                issues.append('CSV FUNCTION FOUND')
            if has_template:
                issues.append('TEMPLATE ARTIFACT')
            
            status = 'OK' if not issues else f'ISSUES: {", ".join(issues)}'
            preview = resp[:120].replace('\n', ' ').strip()
            print(f'  [{status}] {name}')
            print(f'    -> {preview}...')
        else:
            print(f'  [MISS] {name}')
    except Exception as e:
        print(f'  [ERROR] {name}: {e}')
