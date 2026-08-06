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
    # Equations ("solve x/2 + 1 = 6") and root/power questions are handled by
    # their own strategies — extracting a bare fragment like "2 + 1" from
    # "x/2 + 1 = 6" would produce a wrong, context-free answer.
    if '=' in q:
        return None
    if re.search(r'\b(square|sqrt|cube|cubed|squared|power|root)\b', q):
        return None
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


def _solve_square_root(q):
    """Solve square/cube root problems.
    
    "What is the square root of 144?"
    "sqrt of 81"
    "cube root of 27"
    """
    m = re.search(r'(?:square\s+root|sqrt)\s+(?:of\s+)?(\d+(?:\.\d+)?)', q, re.IGNORECASE)
    if m:
        n = float(m.group(1))
        r = n ** 0.5
        if abs(r - round(r)) < 1e-9:
            r = round(r)
            return f"The square root of {int(n)} is {int(r)}. ({int(r)} × {int(r)} = {int(n)})"
        return f"The square root of {n:g} is approximately {r:.4f}."
    m = re.search(r'cube\s+root\s+(?:of\s+)?(\d+(?:\.\d+)?)', q, re.IGNORECASE)
    if m:
        n = float(m.group(1))
        r = n ** (1.0 / 3.0)
        if abs(r - round(r)) < 1e-9:
            r = round(r)
            return f"The cube root of {int(n)} is {int(r)}. ({int(r)} × {int(r)} × {int(r)} = {int(n)})"
        return f"The cube root of {n:g} is approximately {r:.4f}."
    return None


def _solve_power(q):
    """Solve power/exponent problems.
    
    "What is 2 to the power of 10?"
    "3^4"
    "What is 5 cubed?"
    """
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:\^|to\s+the\s+(?:power|exponent)\s+of)\s*(\d+(?:\.\d+)?)', q, re.IGNORECASE)
    if m:
        base, exp = float(m.group(1)), float(m.group(2))
        if exp == int(exp) and int(exp) <= 100:
            result = base ** int(exp)
            return f"{base:g} to the power of {int(exp)} is {result:g}."
        result = base ** exp
        return f"{base:g} to the power of {exp:g} is approximately {result:.6g}."
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:squared|cubed|squared\b)', q, re.IGNORECASE)
    if m:
        n = float(m.group(1))
        if 'cubed' in q:
            return f"{n:g} cubed is {n**3:g}. ({n:g} × {n:g} × {n:g} = {n**3:g})"
        return f"{n:g} squared is {n**2:g}. ({n:g} × {n:g} = {n**2:g})"
    return None


def _solve_linear_equation(q):
    """Solve linear equations in one variable.
    
    "solve x + 3 = 10"
    "solve 2x - 4 = 8"
    "what is x if 3x + 5 = 20"
    "solve for x: x/2 + 1 = 6"
    """
    if not re.search(r'\b(solve|find|x\s*=|for\s+x)\b', q, re.IGNORECASE) and '=' not in q:
        return None
    # Only handle equations with a single variable and one "=" sign
    if q.count('=') != 1:
        return None
    # Strip instruction prefixes so the variable in "solve for x: x/2 + 1 = 6"
    # isn't counted twice ("for x" is an instruction, not part of the equation)
    eq = q
    for pat in (
        r'^\s*solve\s+for\s+[xyz]\s*[:\-,]?\s*',
        r'^\s*solve\s+for\s+[xyz]\s*',
        r'^\s*solve\s+',
        r'^\s*find\s+[xyz]\s+(?:if|where|when|given|such\s+that)\s+',
        r'^\s*find\s+',
        r'^\s*what\s+is\s+[xyz]\s+(?:if|where|when|given)\s+',
        r'^\s*what\s+is\s+[xyz]\s*[:\-,]?\s*',
        r'^\s*determine\s+[xyz]\s+(?:if|where|when|given)\s+',
        r'^\s*calculate\s+[xyz]\s*[:\-,]?\s*',
    ):
        eq = re.sub(pat, '', eq, flags=re.IGNORECASE)
        if '=' in eq:
            break
    m = re.search(r'([^=]+)=([^=]+)', eq)
    if not m:
        return None
    left, right = m.group(1), m.group(2)
    var_match = re.search(r'[xyz](?![a-z])', left + right)
    if not var_match:
        return None
    var = var_match.group(0)

    def _parse_side(side, var):
        """Parse a linear expression ax+b into (coeff, const)."""
        # normalize: remove spaces, handle 'x' -> '1x'
        s = side.lower().replace(' ', '')
        # remove trailing punctuation
        s = re.sub(r'[\?:]+$', '', s)
        coeff, const = 0.0, 0.0
        # "x/2" style terms: the variable divided by a constant contributes
        # 1/2 to the coefficient (and the denominator is not a bare constant)
        div_terms = re.findall(r'([+-]?)(\d*\.?\d*)[a-z]\s*/\s*(\d+\.?\d*)', s)
        for sign, num, den in div_terms:
            num = num or '1'
            coeff += float(sign + num) / float(den)
        s = re.sub(r'[a-z]\s*/\s*\d+\.?\d*', '', s)
        # variable terms: optional sign, optional coefficient, then the variable
        var_terms = re.findall(r'([+-]?)(\d*\.?\d*)[a-z]\b', s)
        for sign, num in var_terms:
            num = num or '1'
            coeff += float(sign + num)
        # bare constants: numbers NOT followed by a letter (so '2' in '2x' is skipped)
        consts = re.findall(r'([+-]?\d+\.?\d*)(?![a-z])', s)
        for c in consts:
            const += float(c)
        return coeff, const

    try:
        lc, lk = _parse_side(left, var)
        rc, rk = _parse_side(right, var)
    except Exception:
        return None
    # (lc * x + lk) = (rc * x + rk)  ->  x = (rk - lk) / (lc - rc)
    denom = lc - rc
    if abs(denom) < 1e-12:
        return None
    sol = (rk - lk) / denom
    if sol == int(sol):
        sol_str = str(int(sol))
    else:
        sol_str = f"{sol:.4f}"
    return (f"Solving for {var}: {var} = {sol_str}. "
            f"({left.strip()} = {right.strip()} → move like terms: "
            f"({lc:g}{var} + {lk:g}) = ({rc:g}{var} + {rk:g}), so "
            f"{var} = ({rk:g} - {lk:g}) / ({lc:g} - {rc:g}) = {sol_str})")


def _solve_geometry(q):
    """Solve basic geometry problems.
    
    "area of a circle with radius 5"
    "circumference of a circle with diameter 10"
    "area of a rectangle with length 4 and width 3"
    "area of a triangle with base 6 and height 4"
    """
    import math as _m
    # Circle area from radius or diameter
    m = re.search(r'area\s+of\s+(?:a\s+)?circle.*?(?:radius|diameter)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)', q, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        if 'diameter' in q:
            r = val / 2.0
            a = _m.pi * r ** 2
            return f"The area of a circle with diameter {val:g} is {a:.2f} square units. (Area = π × r² = π × {r:g}² = {a:.2f})"
        a = _m.pi * val ** 2
        return f"The area of a circle with radius {val:g} is {a:.2f} square units. (Area = π × r² = π × {val:g}² = {a:.2f})"
    # Circle circumference
    m = re.search(r'circumference\s+of\s+(?:a\s+)?circle.*?(?:radius|diameter)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)', q, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        if 'diameter' in q:
            c = _m.pi * val
            return f"The circumference of a circle with diameter {val:g} is {c:.2f} units. (C = π × d = π × {val:g} = {c:.2f})"
        c = 2 * _m.pi * val
        return f"The circumference of a circle with radius {val:g} is {c:.2f} units. (C = 2πr = 2 × π × {val:g} = {c:.2f})"
    # Rectangle area
    m = re.search(r'area\s+of\s+(?:a\s+)?rectangle.*?(?:length|side)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?).*?(?:width|side)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)', q, re.IGNORECASE)
    if m:
        l, w = float(m.group(1)), float(m.group(2))
        return f"The area of a {l:g} × {w:g} rectangle is {l*w:g} square units. (Area = length × width = {l:g} × {w:g} = {l*w:g})"
    # Triangle area
    m = re.search(r'area\s+of\s+(?:a\s+)?triangle.*?(?:base)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?).*?(?:height)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)', q, re.IGNORECASE)
    if m:
        b, h = float(m.group(1)), float(m.group(2))
        a = 0.5 * b * h
        return f"The area of a triangle with base {b:g} and height {h:g} is {a:g} square units. (Area = ½ × base × height = ½ × {b:g} × {h:g} = {a:g})"
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
        _solve_square_root,          # "what is the square root of 144"
        _solve_power,                # "2 to the power of 10"
        _solve_linear_equation,      # "solve x + 3 = 10"
        _solve_geometry,             # "area of a circle with radius 5"
    ]
    
    for strategy in strategies:
        try:
            result = strategy(q)
            if result:
                return result
        except Exception:
            continue
    
    return None
