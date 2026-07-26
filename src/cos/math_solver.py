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


def _solve_distance_time(q):
    """Solve distance = speed * time problems.
    
    "If a train travels at 60 mph for 2.5 hours, how far?"
    """
    # Extract speed (number before mph, miles per hour, km/h, etc.)
    speed_m = re.search(r'(\d+(?:\.\d+)?)\s*(?:mph|miles?\s*per\s*hour|kmh|km/h|km\s*per\s*hour)', q, re.IGNORECASE)
    if not speed_m:
        return None
    speed = float(speed_m.group(1))
    
    # Extract time (number before hours, hrs, minutes, etc.)
    time_m = re.search(r'(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)', q, re.IGNORECASE)
    if not time_m:
        return None
    time_val = float(time_m.group(1))
    unit = time_m.group(2).lower()
    # Convert minutes to hours if needed
    if unit.startswith('min'):
        time_val /= 60.0
    
    distance = speed * time_val
    
    # Get unit from context
    unit_m = re.search(r'(?:miles?|kilometers?|metres?|feet|yards?)', q, re.IGNORECASE)
    dist_unit = unit_m.group(0).lower() if unit_m else 'miles'
    
    return f"The distance is {distance:.1f} {dist_unit}. (Distance = speed × time = {speed} × {time_val} = {distance:.1f})"


def _solve_percentage(q):
    """Solve percentage problems.
    
    "What is 5 percent of 200?"
    "What percent of 200 is 10?"
    "15% of 80"
    """
    m = re.search(r'(\d+(?:\.\d+)?)\s*%?\s*(?:percent|per cent|%)\s*(?:of|in)\s*(\d+(?:\.\d+)?)', q, re.IGNORECASE)
    if m:
        pct = float(m.group(1))
        total = float(m.group(2))
        result = (pct / 100.0) * total
        return f"{pct}% of {total} is {result:.1f}. ({pct}/100 × {total} = {result:.1f})"
    
    # "what percent of X is Y"
    m2 = re.search(r'(?:what|how much)\s*(?:percent|per cent|%)\s*(?:of|in)\s*(\d+(?:\.\d+)?)\s*(?:is|are)\s*(\d+(?:\.\d+)?)', q, re.IGNORECASE)
    if m2:
        total = float(m2.group(1))
        part = float(m2.group(2))
        pct = (part / total) * 100
        return f"{part} is {pct:.1f}% of {total}. ({part}/{total} × 100 = {pct:.1f}%)"
    
    return None


def _solve_simple_arithmetic(q):
    """Solve simple arithmetic expressions embedded in natural language.
    
    "What is 25 times 4 plus 10?"
    "Calculate 15 + 27"
    """
    # Normalize words to operators
    expr = q.lower()
    expr = re.sub(r'\btimes\b', '*', expr)
    expr = re.sub(r'\bmultiplied by\b', '*', expr)
    expr = re.sub(r'\bdivided by\b', '/', expr)
    expr = re.sub(r'\bplus\b', '+', expr)
    expr = re.sub(r'\bminus\b', '-', expr)
    expr = re.sub(r'\bover\b', '/', expr)
    
    # Extract an arithmetic expression from the text
    m = re.search(r'(\d+\s*[+\-*/]\s*\d+(?:\s*[+\-*/]\s*\d+)*)', expr)
    if m:
        expr_text = m.group(1).strip()
        # Validate: only digits and operators
        if re.match(r'^[\d\s+\-*/.()]+$', expr_text):
            try:
                result = eval(expr_text)
                if result == int(result):
                    return f"The answer is {int(result)}."
                return f"The answer is {result:.2f}."
            except:
                pass
    return None


def _solve_survey_probability(q):
    """Solve survey/inclusion-exclusion probability problems.
    
    "A survey of 100 people found that 60 like coffee, 40 like tea, and 20 like both."
    """
    m = re.search(r'(\d+)\s*(?:people|respondents|surveyed|total)', q, re.IGNORECASE)
    if not m:
        return None
    total = int(m.group(1))
    
    # Find all numbers that look like group counts (typically 2-3 numbers after the total)
    all_nums = [int(n) for n in re.findall(r'\d+', q)]
    if len(all_nums) < 3:
        return None
    
    # Assume: total, group_a, group_b, both (if present)
    # Or: total, group_a, group_b
    total_n = all_nums[0]
    group_a = all_nums[1]
    
    # Check if 'both' is mentioned
    has_both = 'both' in q.lower()
    
    if has_both and len(all_nums) >= 4:
        group_b = all_nums[2]
        both = all_nums[3]
        # P(A or B) = P(A) + P(B) - P(A and B)
        prob_a = group_a / total_n
        prob_b = group_b / total_n
        prob_both = both / total_n
        prob_either = prob_a + prob_b - prob_both
        return f"The probability is {prob_either:.2f} ({prob_either*100:.1f}%). P(A or B) = P(A) + P(B) - P(A and B) = {group_a}/{total_n} + {group_b}/{total_n} - {both}/{total_n} = {prob_either:.2f}"
    elif len(all_nums) >= 3:
        group_b = all_nums[2]
        prob_a = group_a / total_n
        prob_b = group_b / total_n
        return f"P(A) = {prob_a:.2f}, P(B) = {prob_b:.2f}"
    
    return None


def solve_word_problem(question):
    """Solve a word problem using multiple strategies."""
    q = question.strip()
    if not q:
        return None
    
    # Try each strategy in order
    strategies = [
        _solve_simple_arithmetic,   # "What is 25 times 4 plus 10?"
        _solve_distance_time,        # "train travels at 60 mph for 2.5 hours"
        _solve_percentage,           # "5 percent of 200"
        _solve_survey_probability,   # "survey of 100 people"
    ]
    
    for strategy in strategies:
        try:
            result = strategy(q)
            if result:
                return result
        except Exception:
            continue
    
    return None
