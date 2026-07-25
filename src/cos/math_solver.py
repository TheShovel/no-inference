"""
COS Math Solver — Multi-strategy word problem solver and arithmetic evaluator.

Handles:
  - Word problems (GSM8K, MT-Bench math, general math questions)
  - Arithmetic expression evaluation
  - MT-Bench specific math problems (probability, geometry, etc.)
"""

import re
import math as _math


# ── Word-to-number conversion ────────────────────────────────────────────────

WORD_TO_NUM = {
    'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,
    'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,
    'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,
    'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20,
    'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,
    'eighty':80,'ninety':90,'hundred':100,'thousand':1000,
    'dozen':12, 'dozens':12, 'half':0.5, 'third':1/3,
}

def word_to_number(word):
    return WORD_TO_NUM.get(word.lower(), None)


def extract_all_nums(text):
    """Extract all integers from text, handling commas and word numbers."""
    text_clean = re.sub(r'(\d),(\d)', r'\1\2', text)
    nums = [int(n) for n in re.findall(r'\d+', text_clean)]
    for word in text.lower().split():
        val = word_to_number(word)
        if val is not None and val == int(val):
            nums.append(int(val))
    return nums


# ── Preprocessing ────────────────────────────────────────────────────────────

def _preprocess(question):
    """Normalize word numbers and extract all numeric values."""
    q = question.lower()
    # Replace word numbers with their digit equivalents
    for word, num in sorted(WORD_TO_NUM.items(), key=lambda x: -len(x[0])):
        q = re.sub(r'\b' + word + r'\b', str(num), q)
    # "twice" -> "2 times"
    q = re.sub(r'\btwice\b', '2 times', q)
    q = re.sub(r'\bdouble\b', '2 times', q)
    # Extract all numbers
    nums = [int(n) for n in re.findall(r'\d+', q.replace(',', ''))]
    # Also extract floats
    floats = [float(m.group(1)) for m in re.finditer(r'(\d+\.\d+)', q)]
    return q, nums + [int(f) if f == int(f) else f for f in floats]


# ── Strategy functions ───────────────────────────────────────────────────────
# These are imported/defined in the main cos_orchestrator.py for now.
# This file will be populated with strategy functions as they are moved
# from cos_orchestrator.py in future refactoring steps.
#
# For now, the orchestrator imports solve_word_problem from cos_orchestrator.py
# directly.

def solve_word_problem(question):
    """Placeholder — actual implementation is in cos_orchestrator.py
    and will be moved here in a future refactoring step."""
    # Import from the legacy orchestrator
    from cos.cos_orchestrator import solve_word_problem as _solve
    return _solve(question)
