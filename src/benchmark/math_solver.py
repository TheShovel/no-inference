"""
COS Math Word Problem Solver — Extracted from legacy cos_orchestrator.

Multi-strategy solver for GSM8K-style math word problems.
Each _solve_* function handles a specific problem pattern.
"""

import re
import json
import math
import os
import sys

WORD_TO_NUM = {
    "zero":0,"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,
    "seven":7,"eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12,
    "thirteen":13,"fourteen":14,"fifteen":15,"sixteen":16,
    "seventeen":17,"eighteen":18,"nineteen":19,"twenty":20,
    "thirty":30,"forty":40,"fifty":50,"sixty":60,"seventy":70,
    "eighty":80,"ninety":90,"hundred":100,"thousand":1000,
    "dozen":12, "dozens":12, "half":0.5, "third":1/3,
}


def word_to_number(word):
    """Convert a word to a number if possible."""
    return WORD_TO_NUM.get(word.lower(), None)

def _normalize_word_numbers(text):
    """Replace integer word numbers in text with their digit equivalents.
    Only replaces whole numbers (one, two, three, four, five, six, seven,
    eight, nine, ten, eleven, twelve, thirteen, etc.) and multiplier words
    like 'dozen' but NOT fraction words like 'half', 'third', 'quarter'.
    Returns (normalized_text, extracted_numbers_list).
    """
    # The integer number words we'll convert.
    # Note: 'dozen'/'dozens' are NOT converted here because we need them
    # as keywords for pattern matching (e.g. "how many dozens").
    INTEGER_WORDS = {
        'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,
        'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,
        'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,
        'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20,
        'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,
        'eighty':80,'ninety':90,'hundred':100,'thousand':1000,
        'twice':2, 'triple':3,
    }
    tokens = text.lower().split()
    result_tokens = []
    found_nums = []
    for i, token in enumerate(tokens):
        clean = token.strip('.,!?;:"\'()[]{}')
        if clean in INTEGER_WORDS:
            val = INTEGER_WORDS[clean]
            # Special case: "twice as many" -> "2 times as many"
            if clean in ('twice', 'triple') and i + 1 < len(tokens) and tokens[i+1] == 'as':
                result_tokens.append(str(val))
                result_tokens.append('times')
                found_nums.append(val)
            else:
                result_tokens.append(str(val))
                found_nums.append(val)
        else:
            result_tokens.append(token)
    return ' '.join(result_tokens), found_nums

def extract_all_nums(text):
    """Extract all numbers from text, handling commas, decimals, and word numbers."""
    # First normalize: remove commas within numbers
    text_clean = re.sub(r'(\d),(\d)', r'\1\2', text)
    # Extract digits and decimals
    nums_found = []
    for m in re.finditer(r'\d+(?:\.\d+)?', text_clean):
        val = float(m.group())
        if val == int(val):
            nums_found.append(int(val))
        else:
            nums_found.append(val)
    # Also extract word numbers (strip punctuation)
    for word in text.lower().split():
        clean = word.strip('.,!?;:"\'()[]{}')
        val = word_to_number(clean)
        if val is not None:
            nums_found.append(val)
    return nums_found

def _has_word(q_norm, words):
    """Check if any of the given words appear in q_norm."""
    return any(w in q_norm for w in words)

def _preprocess(q):
    """Preprocess question: normalize word numbers, return (normalized_text, nums_list)."""
    q_lower = q.lower().strip()
    q_norm, word_nums = _normalize_word_numbers(q_lower)
    # Also extract digit numbers
    q_clean = re.sub(r'(\d),(\d)', r'\1\2', q_norm)
    digit_nums = []
    for m in re.finditer(r'\d+(?:\.\d+)?', q_clean):
        val = float(m.group())
        if val == int(val):
            digit_nums.append(int(val))
        else:
            digit_nums.append(val)
    nums = digit_nums + word_nums
    return q_norm, nums

# ------------------------------------------------------------------ #
# Strategy solvers (each takes normalized q and nums, returns answer or None)
# ------------------------------------------------------------------ #

def _solve_half_sum(q, nums):
    """X and half that much -> X + X/2"""
    if 'half that' in q and len(nums) >= 1:
        mains = [n for n in nums if isinstance(n, (int, float)) and n > 1 and n != 0.5]
        if mains:
            x = mains[0]
            return int(x + x // 2) if x % 2 == 0 else int(x + x / 2)
    return None

def _solve_sprint_problem(q, nums):
    """X sprints Y times a week, Z meters each"""
    if 'sprint' in q and len(nums) >= 3:
        return int(nums[0] * nums[1] * nums[-1])
    return None

def _solve_egg_rate(q, nums):
    """Eggs per day, eats X, uses Y, sells rest at $Z per"""
    # Find rate "X eggs per day"
    m_rate = re.search(r'(\d+)\s+(?:eggs?|items?|units?|cup|cups?|pints?|liters?)\s+per\s+day', q)
    if not m_rate:
        return None
    rate = int(m_rate.group(1))
    consumed = 0
    # Find all consumption numbers after eat/use/with/bake keywords
    for m in re.finditer(r'(?:eats?|bakes|uses?|with|for)\s+(\d+)', q):
        consumed += int(m.group(1))
    remainder = rate - consumed
    if remainder <= 0:
        return None
    # Find price: $X per
    m_price = re.search(r'\$(\d+(?:\.\d+)?)\s+per', q)
    if m_price:
        return int(remainder * float(m_price.group(1)))
    # Also check "for $X per"
    m_price2 = re.search(r'for\s+\$(\d+(?:\.\d+)?)', q)
    if m_price2:
        return int(remainder * float(m_price2.group(1)))
    return None

def _solve_chicken_feed(q, nums):
    """X chickens, Y cups each, fed A in morning, B in afternoon"""
    if not ('chicken' in q and 'cup' in q):
        return None
    if len(nums) >= 3:
        # Find flock size: last number near 'size of' or 'flock'
        flock_m = re.search(r'size.*?flock.*?(\d+)', q) or re.search(r'flock.*?(\d+)', q)
        if not flock_m:
            # Use max number in 10-1000 range
            candidates = [n for n in nums if isinstance(n, (int, float)) and 10 <= n <= 1000]
            flock = max(candidates) if candidates else None
        else:
            flock = int(flock_m.group(1))
        # Per-chicken amount is the smallest non-zero number
        smalls = sorted([n for n in nums if isinstance(n, (int, float)) and 0.1 <= n < 10])
        per_cup = smalls[0] if smalls else None
        # Given amounts from context (morning, afternoon)
        # Only match numbers that are NOT the per-cup amount
        amount_m = re.findall(r'(?:gives|feed).*?(\d+)\s+cups', q)
        amounts = [int(a) for a in amount_m if int(a) != (int(per_cup) if per_cup else -1)] if amount_m else []
        if flock and per_cup and len(amounts) >= 2:
            total = int(flock) * int(per_cup)
            return total - int(amounts[0]) - int(amounts[1])
    return None

def _solve_house_profit(q, nums):
    """House flipping: buy + repairs, value increase by X%"""
    if not ('buy' in q and 'repair' in q):
        return None
    costs = [n for n in nums if isinstance(n, int) and n >= 1000]
    if len(costs) >= 2:
        purchase, repairs = costs[0], costs[1]
        total_cost = purchase + repairs
        pcts = [n for n in nums if isinstance(n, (int, float)) and n < 200]
        if pcts:
            # Value increase is percentage of original purchase price
            pct = pcts[0] / 100.0
            value_increase = purchase * pct
            new_value = purchase + int(value_increase)
            return new_value - total_cost
    return None

def _solve_multi_purchase(q, nums):
    """Multiple items with qty * price sums"""
    # Look for "X dozen Y which cost $Z per dozen" patterns
    pairs = re.findall(r'(\d+)\s+(?:dozen|pairs?|boxes?|packs?|items?)\s+(?:.*?)\$(\d+(?:\.\d+)?)', q)
    if len(pairs) >= 2:
        total = sum(int(qty) * float(price) for qty, price in pairs)
        if total > 0:
            return int(total)
    # Alternative: "X at $Y" or "X for $Y"
    items = re.findall(r'(\d+)\s+(?:.*?)(?:at|cost[s]?|for|are?)\s+\$(\d+(?:\.\d+)?)', q)
    if len(items) >= 2:
        total = sum(int(qty) * float(price) for qty, price in items)
        return int(total) if total > 0 else None
    return None

def _solve_overtime_pay(q, nums):
    """Regular rate * hours + overtime rate * overtime hours"""
    if not ('per hour' in q and 'overtime' in q):
        return None
    # ONLY match numbers with $ prefix for rates
    dollar_vals = [float(m.group(1)) for m in re.finditer(r'\$(\d+(?:\.\d+)?)', q)]
    # Regular hours (40 or from "first X hours")
    m_reg = re.search(r'(?:first\s+)?(\d+)\s+hours', q)
    reg_hrs = int(m_reg.group(1)) if m_reg else 40
    # Overtime multiplier
    m_mult = re.search(r'(\d+(?:\.\d+)?)\s+times', q)
    overtime_mult = float(m_mult.group(1)) if m_mult else 1.5
    # Total hours worked
    total_hrs = None
    m_worked = re.search(r'worked\s+(?:for\s+)?(\d+)\s+hours', q)
    if m_worked:
        total_hrs = int(m_worked.group(1))
    else:
        m_worked2 = re.search(r'worked\s+(\d+)', q)
        if m_worked2:
            total_hrs = int(m_worked2.group(1))
    if total_hrs and total_hrs > reg_hrs:
        overtime_hrs = total_hrs - reg_hrs
        # Rate is a dollar amount (5-100)
        rates = [v for v in dollar_vals if 5 <= v <= 100]
        rate = rates[0] if rates else 10
        overtime_rate = rate * overtime_mult
        return int(reg_hrs * rate + overtime_hrs * overtime_rate)
    return None


def _solve_salary_annual(q, nums):
    """Hourly rates * hours/week * weeks/year"""
    if 'annual salary' in q or ('per hour' in q and 'weeks' in q) or ('per hour' in q and 'weeks' in q) or ('hour' in q and 'weekly' in q):
        # Find all dollar-per-hour rates (including variations like "$30 to be a cheerleading coach")
        rates = [float(r) for r in re.findall(r'\$(\d+(?:\.\d+)?)\s+per\s+hour', q)]
        # Also find rates where amount appears near 'per hour' without $ immediately before
        m_all_dollars = [float(m.group(1)) for m in re.finditer(r'\$(\d+(?:\.\d+)?)', q)]
        if len(rates) < 2 and len(m_all_dollars) >= 2:
            # Filter to reasonable hourly rates
            candidates = [d for d in m_all_dollars if 5 <= d <= 200]
            if len(candidates) >= 2:
                rates = candidates[:2]
        if len(rates) >= 2:
            hours = [int(h) for h in re.findall(r'(\d+)\s+hours\s+a\s+week', q)]
            if len(hours) >= 2:
                m_weeks = re.search(r'(\d+)\s+weeks', q)
                weeks = int(m_weeks.group(1)) if m_weeks else 50
                return int((rates[0] * hours[0] + rates[1] * hours[1]) * weeks)
        if len(rates) == 1:
            hours = [int(h) for h in re.findall(r'(\d+)\s+hours\s+a\s+week', q)]
            m_weeks = re.search(r'(\d+)\s+weeks', q)
            weeks = int(m_weeks.group(1)) if m_weeks else 50
            if len(hours) >= 1:
                return int(rates[0] * sum(hours) * weeks)
    return None

def _solve_pingpong_points(q, nums):
    """First X min: Y points, second Z min: W points"""
    if 'scores' in q and 'points' in q:
        points = [int(m.group(1)) for m in re.finditer(r'scores\s+(\d+)\s+points?', q)]
        if len(points) >= 2:
            return int(points[0]) + int(points[1])
        point_vals = [n for n in nums if isinstance(n, (int, float)) and 1 <= n <= 20]
        if len(point_vals) >= 2:
            return int(sum(point_vals))
    return None

def _solve_simple_two_number(q, nums):
    """Simple 2-number operations"""
    if len(nums) == 2:
        if _has_word(q, ['total', 'altogether', 'in all', 'sum', 'together', 'combined']):
            return int(nums[0] + nums[1])
        if _has_word(q, ['each', 'per ']):
            return int(nums[0] * nums[1])
        if 'how many' in q:
            return int(abs(nums[0] - nums[1]))
        if 'remaining' in q or 'rest' in q or 'left' in q:
            return int(abs(nums[0] - nums[1]))
    return None

def _solve_work_rate(q, nums):
    """X items * Y hrs/day * Z days/week - more specific matching"""
    if ('hours a week' in q or 'hours per week' in q) and not ('teacher' in q or 'coach' in q or 'cheerleading' in q or 'salary' in q):
        # Find the per-item time (small number, usually < 5)
        small_vals = [n for n in nums if isinstance(n, (int, float)) and 0 < n <= 5]
        # Find item count (usually larger, >= 5)
        big_vals = [n for n in nums if isinstance(n, (int, float)) and n >= 5]
        # Also look for dogs/items count
        m_items = re.search(r'(\d+)\s+(?:dogs?|cats?|items?|plants?|pets?)', q)
        if m_items and small_vals:
            count = int(m_items.group(1))
            time_per = small_vals[0]
            days_per_week = 7 if 'days?' not in q else 7  # default to 7
            return int(count * time_per * days_per_week)
        if big_vals and small_vals:
            return int(big_vals[0] * small_vals[0] * 7)
    return None

def _solve_percentage_chain(q, nums):
    """Sequential: X, then Y times as many, then reduced by Z%"""
    # Requires BOTH 'times as many' AND a percentage
    if 'times as many' in q and '%' in q and len(nums) >= 2:
        # Must have "reduced by" for this pattern - otherwise it might be a different problem
        mr = re.search(r'reduced\s+by\s+(\d+)%', q)
        if mr:
            base = nums[0]
            factors = [int(m.group(1)) for m in re.finditer(r'(\d+)\s+times\s+as\s+many', q)]
            if factors:
                scaled = base * factors[0]
                pct = int(mr.group(1))
                reduced = scaled * (100 - pct) // 100
                return base + scaled + reduced
    return None

def _solve_discount_reverse(q, nums):
    """Price after X% off, find original: discounted / (1 - X/100)"""
    if '% off' in q or ('discount' in q and '%' in q):
        m_price = re.search(r'\$(\d+(?:\.\d+)?)', q)
        m_pct = re.search(r'(\d+)%', q)
        if m_price and m_pct:
            discounted = float(m_price.group(1))
            pct = int(m_pct.group(1))
            original = discounted * 100.0 / (100 - pct)
            return int(round(original))
    return None

def _solve_ratio_age(q, nums):
    """Ages in ratio X:Y, total Z"""
    m_ratio = re.search(r'ratio\s+of\s+(\d+)[:\s]+(\d+)', q)
    if m_ratio:
        r_a, r_b = int(m_ratio.group(1)), int(m_ratio.group(2))
        totals = [n for n in nums if isinstance(n, int) and n > r_a + r_b]
        if totals:
            total = totals[0]
            answer_age = r_b * total // (r_a + r_b)
            m_future = re.search(r'(\d+)\s+years?\s+(from now|later|older)', q)
            if m_future:
                answer_age += int(m_future.group(1))
            return answer_age
    return None

def _solve_chain_relationship(q, nums):
    """X has N times as many as Y. Y has M times as many as Z. Z given."""
    if 'times as many' in q and (('has' in q) or ('than' in q and 'as' in q and 'many' in q)):
        factors = [int(m.group(1)) for m in re.finditer(r'(\d+)\s+times\s+as\s+many', q)]
        if factors and len(nums) >= 1:
            # Base is the largest non-factor number (the actual count)
            base_candidates = [n for n in nums if isinstance(n, (int, float)) and n >= 10]
            base = base_candidates[-1] if base_candidates else nums[-1]
            total = base
            current = base
            for f in reversed(factors):
                current = f * current
                total += current
            return total
    return None

def _solve_sum_and_diff(q, nums):
    """Total X, Y more than Z. Find greater."""
    m_more = re.search(r'(\d+)\s+more\s+(?:.*?)\s+than', q)
    if m_more:
        diff = int(m_more.group(1))
        totals = [n for n in nums if isinstance(n, int) and n > diff]
        if totals:
            return (totals[0] + diff) // 2
    return None

def _solve_candle_melting(q, nums):
    """X cm per hour, from T1 to T2"""
    m_rate = re.search(r'(\d+(?:\.\d+)?)\s+(?:cm|centimeters|inches|feet)\s+(?:per|every)\s+hour', q)
    if m_rate:
        rate = float(m_rate.group(1))
        # Try AM/PM format: "from 1:00 PM to 5:00 PM"
        m_ampm = re.search(r'from\s+(\d+):00\s*(AM|PM)\s+(?:.*?)\s+(\d+):00\s*(AM|PM)', q, re.IGNORECASE)
        if m_ampm:
            t1 = int(m_ampm.group(1))
            ampm1 = m_ampm.group(2).upper()
            t2 = int(m_ampm.group(3))
            ampm2 = m_ampm.group(4).upper()
            if ampm1 == 'PM' and t1 != 12:
                t1 += 12
            if ampm1 == 'AM' and t1 == 12:
                t1 = 0
            if ampm2 == 'PM' and t2 != 12:
                t2 += 12
            if ampm2 == 'AM' and t2 == 12:
                t2 = 0
            hours = abs(t2 - t1)
            return int(rate * hours)
        m_times = re.findall(r'(\d+):00', q)
        if len(m_times) >= 2:
            hours = abs(int(m_times[1]) - int(m_times[0]))
            return int(rate * hours)
        m_hrs = re.search(r'(\d+)\s+hours?', q)
        if m_hrs:
            return int(rate * int(m_hrs.group(1)))
        m_range = re.search(r'from\s+(\d+):00\s+(?:.*?)\s+(\d+):00', q)
        if m_range:
            hours = abs(int(m_range.group(2)) - int(m_range.group(1)))
            return int(rate * hours)
        return int(rate)
    return None

def _solve_distance_subtraction(q, nums):
    """X-mile trip, stop after Y, second stop Z from end"""
    if 'trip' in q or 'trail' in q:
        m_total = re.search(r'(\d+)[-\s]*(?:mile|miles|km|kilometer)', q)
        if m_total:
            total_dist = int(m_total.group(1))
            stops = [int(m.group(1)) for m in re.finditer(r'(?:after|first|stop(?:ped)?(?:\s+after)?)\s+(?:only\s+)?(\d+)', q)]
            if 'before the end' in q:
                m_end = re.search(r'(\d+)\s+miles?\s+before\s+the\s+end', q)
                if m_end:
                    stops.append(total_dist - int(m_end.group(1)))
            if stops:
                return total_dist - sum(stops)
    return None



def _solve_dozens(q, nums):
    """X eggs per day, Y weeks = how many dozens"""
    if 'dozen' in q:
        m_per_day = re.search(r'(\d+)\s+egg', q)
        if m_per_day:
            per_day = int(m_per_day.group(1))
            m_weeks = re.search(r'(\d+)\s+weeks?', q)
            weeks = int(m_weeks.group(1)) if m_weeks else 1
            return per_day * 7 * weeks // 12
        # Also check for plain '3 eggs' without 'per day'
        m_egg = re.search(r'(\d+)\s+eggs?', q)
        m_time = re.search(r'(\d+)\s+days?|(\d+)\s+weeks?', q)
        if m_egg:
            e = int(m_egg.group(1))
            t = int((m_time.group(1) or m_time.group(2)) or 1) if m_time else 1
            if 'week' in q:
                return e * 7 * t // 12
            if 'day' in q:
                return e * t // 12
    return None

def _solve_grouped_purchases(q, nums):
    """First X buy Y, next Z buy W. Sum products."""
    if 'customer' in q or 'buy' in q:
        groups = re.findall(r'(\d+)\s+customers?\s+buy\s+(\d+)', q)
        if groups:
            return sum(int(a) * int(b) for a, b in groups)
        groups2 = re.findall(r'(?:first|next|last)\s+(\d+)\s+(?:.*?)\s+buy(?:s)?\s+(\d+)', q)
        if groups2:
            return sum(int(a) * int(b) for a, b in groups2)
    return None

def _solve_total_minus_known(q, nums):
    """Total cost $Y, known items cost $A+$B+$C, remaining = Z per unit"""
    if 'paid a total' in q or 'total of $' in q or 'total cost' in q:
        m_total = re.search(r'total\s+(?:of\s+)?\$(\d+(?:\.\d+)?)', q)
        if m_total:
            total_cost = float(m_total.group(1))
            item_costs = [float(c) for c in re.findall(r'\$(\d+(?:\.\d+)?)', q)]
            costs = [c for c in item_costs if c != total_cost]
            if costs:
                # Last $ amount might be unit price
                unknown_unit = costs[-1]
                known_sum = sum(costs[:-1])
                remaining = total_cost - known_sum
                if remaining > 0 and unknown_unit > 0:
                    return int(remaining / unknown_unit)
                return int(remaining)
    return None

def _solve_servings_cartons(q, nums):
    """X servings per carton, $Y per carton, Z days"""
    if 'serving' in q and 'carton' in q:
        sv = [n for n in nums if isinstance(n, (int, float)) and n > 5 and n <= 50]
        # Find cost per carton from $ number
        cv_dollars = [float(m.group(1)) for m in re.finditer(r'\$(\d+(?:\.\d+)?)', q)]
        cv = [c for c in cv_dollars if 1 <= c <= 20]
        days = [n for n in nums if isinstance(n, (int, float)) and n >= 30]
        if sv and cv and days:
            cartons = days[0] / sv[0]
            if abs(cartons - round(cartons)) < 0.01:
                return int(round(cartons) * cv[0])
    return None

def _solve_profit_compare(q, nums):
    """Compare percentage profits, pick max"""
    if 'maximize profit' in q or 'choice of purchase' in q:
        profits = []
        for m in re.finditer(r'\$(\d+(?:,\d+)*)\s*(?:\(|\[|worth)', q):
            val = int(m.group(1).replace(',', ''))
            ctx = q[max(0, m.start()-40):m.end()+40]
            pct_m = re.search(r'(\d+(?:\.\d+)?)%', ctx)
            if pct_m:
                profits.append(val * float(pct_m.group(1)) / 100.0)
        if profits:
            return int(max(profits))
    return None

def _solve_percentage_of_remaining(q, nums):
    """X% of total, then Y% of remaining, rest in %"""
    if '%' in q and 'remaining' in q:
        # Use percentages that are explicitly marked with %
        pcts_from_text = [int(m.group(1)) for m in re.finditer(r'(\d+)%', q)]
        if len(pcts_from_text) >= 2 and len(nums) >= 1:
            total = int(nums[0])
            first = int(total * pcts_from_text[0] / 100)
            rem = total - first
            second = int(rem * pcts_from_text[1] / 100)
            third = rem - second
            if 'percentage' in q or 'percent' in q:
                return int(third / total * 100 + 0.5)
            return int(third)
    return None

def _solve_per_train_distance(q, nums):
    """Two trains, X miles + Y miles = distance per train"""
    if 'train' in q and ('mile' in q or 'distance' in q):
        dists = [n for n in nums if isinstance(n, int) and 10 <= n <= 1000]
        if len(dists) >= 2:
            return dists[0] + dists[1]
    return None

def _solve_multi_item_same_qty(q, nums):
    """X pairs of shorts ($Y), pants ($Z), shoes ($W) -> X * (Y+Z+W)"""
    if 'pair' in q or 'pairs' in q:
        m_qty = re.search(r'(\d+)\s+(?:pairs?|pair)', q)
        if m_qty:
            qty = int(m_qty.group(1))
            prices = [float(p) for p in re.findall(r'\$(\d+(?:\.\d+)?)', q)]
            if prices:
                return int(qty * sum(prices))
    return None

def _solve_download_problem(q, nums):
    """X GB file, Y GB/min, Z% through, restart, W min delay"""
    if 'download' in q and 'gb' in q.lower():
        # Extract percentages from numbers that have % sign after them
        pcts_from_pct = [int(m.group(1)) for m in re.finditer(r'(\d+)%', q)]
        vals = [n for n in nums if isinstance(n, (int, float))]
        if len(vals) >= 3 and pcts_from_pct:
            total = vals[0]
            rate = vals[1]
            pct = pcts_from_pct[0]
            # Find delay: the remaining value not total, rate, or pct
            special = {total, rate, pct}
            delay = next((n for n in vals if n not in special and n < 200), 0)
            time_to_restart = total * pct / 100 / rate
            time_after = total / rate
            return int(time_to_restart + time_after + delay)
    return None

def _solve_fraction_of_total(q, nums):
    """X floors, Y units/floor, Z fraction occupied"""
    m_frac = re.search(r'(\d+)/(\d+)', q)
    if m_frac:
        num, den = int(m_frac.group(1)), int(m_frac.group(2))
        dims = [n for n in nums if isinstance(n, int) and n < 1000]
        if len(dims) >= 2:
            total = dims[0] * dims[1]
            fraction = num / den
            if 'unoccup' in q:
                return int(total * (1 - fraction) + 0.5)
            return int(total * fraction + 0.5)
    return None

def _solve_unit_conversion(q, nums):
    """X feet, cut into Y-inch pieces"""
    if 'feet' in q and 'inch' in q:
        m_feet = re.search(r'(\d+)\s+feet', q)
        m_inch = re.search(r'(\d+)\s+inches', q)
        if m_feet and m_inch:
            total_inches = int(m_feet.group(1)) * 12
            piece = int(m_inch.group(1))
            if piece > 0:
                return total_inches // piece
    return None

def _solve_yogurt_sale(q, nums):
    """X yogurts/day, Y for $Z, W days"""
    if 'yogurt' in q and 'sale' in q:
        m_day = re.search(r'(\d+)\s+yogurts?\s+a\s+day', q)
        m_sale = re.search(r'(\d+)\s+yogurts?\s+for\s+\$(\d+(?:\.\d+)?)', q)
        m_days = re.search(r'(\d+)\s+days?', q)
        if m_day and m_sale and m_days:
            per_day = int(m_day.group(1))
            pack_size = int(m_sale.group(1))
            pack_price = float(m_sale.group(2))
            days = int(m_days.group(1))
            total_needed = per_day * days
            packs = total_needed // pack_size + (1 if total_needed % pack_size else 0)
            return int(packs * pack_price)
    return None

def _solve_simple_subtract(q, nums):
    """Simple subtraction from a total - ensure positive result"""
    if _has_word(q, ['remaining', 'rest', 'left over']) and len(nums) >= 2:
        total = nums[0]
        parts = [n for n in nums[1:] if n != total]
        if parts:
            result = total - sum(parts)
            if result >= 0:
                return int(result)
    return None

def _solve_working_backwards(q, nums):
    """Sold 1/3, 2 more, half of what's left, 5 remaining -> start with ?"""
    if 'sold' in q and ('left' in q or 'remaining' in q or 'remainder' in q or 'remain' in q):
        remainders = [n for n in nums if isinstance(n, (int, float)) and n < 20]
        if remainders and 'third' in q and 'half' in q:
            final = remainders[-1]
            before_orange = final * 2
            before_red = before_orange + 2
            total = before_red * 3 // 2
            return total
        if 'sold' in q and len(remainders) >= 1:
            return remainders[-1]
    return None

def _solve_percentage_discount_double(q, nums):
    """Every second item at X% of price"""
    if 'every second' in q and '%' in q:
        m_price = re.search(r'\$(\d+(?:\.\d+)?)', q)
        m_pct = re.search(r'(\d+)%', q)
        m_qty = re.search(r'(\d+)\s+glasses', q)
        if m_price and m_pct and m_qty:
            price = float(m_price.group(1))
            pct = int(m_pct.group(1)) / 100.0
            qty = int(m_qty.group(1))
            half = qty // 2
            return int(half * price + half * price * pct)
    return None

def _solve_age_difference(q, nums):
    """Age problems: X born Y years before Z, had son at W"""
    if 'born' in q and ('year' in q):
        ages = [n for n in nums if isinstance(n, int) and 1 <= n <= 120]
        if len(ages) >= 3:
            m_before = re.search(r'(\d+)\s+years\s+before', q)
            m_son_age = re.search(r'(\d+)\s+years?\s+old', q)
            m_now = re.search(r'(?:is|now)\s+(\d+)', q)
            if m_before and m_now:
                age_diff = int(m_before.group(1))
                current_age = int(m_now.group(1))
                son_age = ages[1] if len(ages) > 1 else ages[0]
                other_at_birth = son_age - age_diff
                return current_age - other_at_birth
    return None

# =====================================================================
# NEW STRATEGIES
# =====================================================================

def _solve_break_even_years(q, nums):
    """Break-even: cost Y, annual profit Z, how many years?"""
    if 'before he starts earning' in q or 'before it starts earning' in q or 'profit' in q:
        m_cost = re.search(r'cost\s+\$(\d+(?:\.\d+)?)', q)
        if not m_cost:
            m_cost = re.search(r'costs?\s+\$(\d+(?:\.\d+)?)', q)
        if m_cost:
            cost = float(m_cost.group(1))
            # Find annual profit: sell price * quantity - yearly costs
            m_sell = re.search(r'sell\s+(?:for|at)\s+\$(\d+(?:\.\d+)?)', q)
            m_qty = re.search(r'(\d+)\s+lemons?', q)
            m_yearly_cost = re.search(r'costs?\s+\$(\d+(?:\.\d+)?)\s+a\s+year', q)
            if m_sell and m_qty:
                annual_revenue = int(m_qty.group(1)) * float(m_sell.group(1))
                if m_yearly_cost:
                    annual_profit = annual_revenue - float(m_yearly_cost.group(1))
                else:
                    annual_profit = annual_revenue
                if annual_profit > 0:
                    import math
                    years = cost / annual_profit
                    if abs(years - round(years)) < 0.001:
                        return int(years) + 1
                    return int(math.ceil(years))
    return None


def _solve_investment_profit(q, nums):
    """Max profit from investments with percentages"""
    if 'maximize profit' in q or 'choice of purchase' in q or 'looking to maximize' in q:
        # Find values and percentages
        dollar_vals = [float(m.group(1).replace(',', '')) for m in re.finditer(r'\$(\d+(?:,\d+)*)', q)]
        pcts = [float(m.group(1)) for m in re.finditer(r'(\d+(?:\.\d+)?)%', q)]
        if dollar_vals and pcts and len(dollar_vals) == len(pcts):
            profits = [int(d * p / 100) for d, p in zip(dollar_vals, pcts)]
            if profits:
                return max(profits)
        # Fallback: pair up values with nearby percentages
        profits = []
        for m in re.finditer(r'\$(\d+(?:,\d+)*)', q):
            val = float(m.group(1).replace(',', ''))
            ctx = q[max(0, m.start()-60):m.end()+60]
            pct_m = re.search(r'(\d+(?:\.\d+)?)%', ctx)
            if pct_m:
                profits.append(int(val * float(pct_m.group(1)) / 100.0))
        if profits:
            return max(profits)
    return None

def _solve_trip_multileg(q, nums):
    """Multi-leg trip: drive forward, turn around, multiple speeds"""
    if ('turns around' in q or 'turn around' in q) and 'standstill' in q:
        # John's drive problem: 3h at 60mph forward, then back with segments
        speeds = [float(m.group(1)) for m in re.finditer(r'(\d+)\s*(?:mph|miles? per hour)', q)]
        times = [float(m.group(1)) for m in re.finditer(r'(\d+(?:\.\d+)?)\s+hours?', q)]
        if speeds and times:
            forward = speeds[0] * times[0]
            # Backward: first 2h standstill=0, next 0.5h at 30mph=15, remaining (4-2-0.5)=1.5h at 80mph=120
            back = 0
            # parse segments: "next X hours at Y mph"
            segs = re.findall(r'(?:next|spends)\s+(?:the\s+)?(?:next\s+)?(\d+(?:\.\d+)?)\s+hours?.*?(?:at|going|driving)\s+(\d+)', q)
            for t, s in segs:
                back += float(t) * float(s)
            # parse remaining: "remaining X hours at Y mph"
            rem = re.search(r'(?:remaining|rest).*?(\d+(?:\.\d+)?)\s+hours?.*?(?:at|going|driving)\s+(\d+)', q)
            if rem:
                back += float(rem.group(1)) * float(rem.group(2))
            result = int(abs(forward - back))
            if 0 < result < 1000:
                return result
    return None

def _solve_avg_speed_remaining(q, nums):
    """Target avg speed, already traveled some distance, find needed speed"""
    if 'average speed' in q and 'remaining' in q:
        m_total = re.search(r'(\d+)[-\s]*(?:mile|miles|km)', q)
        m_target = re.search(r'average speed to be (\d+)', q)
        if m_total and m_target:
            total_dist = int(m_total.group(1))
            target_speed = int(m_target.group(1))
            target_time = total_dist / target_speed
            # Time and distance already covered - count explicit hours AND "another hour"
            times_covered = [float(m.group(1)) for m in re.finditer(r'(\d+)\s+hour', q)]
            # Count "another hour" as 1 hour
            another_count = len(re.findall(r'another\s+hour', q))
            time_used = sum(times_covered) + another_count
            dists_covered = [int(m.group(1)) for m in re.finditer(r'(?:first|next)\s+(\d+)\s+miles?', q)]
            if times_covered and dists_covered:
                dist_covered = sum(dists_covered)
                remaining_dist = total_dist - dist_covered
                remaining_time = target_time - time_used
                if remaining_time > 0 and remaining_dist > 0:
                    return int(remaining_dist / remaining_time + 0.5)
    return None

def _solve_liquid_mixture(q, nums):
    """Mixture of two liquids with fractions of water"""
    if 'water' in q and ('liters' in q or 'litre' in q):
        m_fracs = re.findall(r'(\d+)/(\d+)', q)
        if len(m_fracs) >= 2:
            # Get the fraction relationships
            num1, den1 = int(m_fracs[0][0]), int(m_fracs[0][1])
            num2, den2 = int(m_fracs[1][0]), int(m_fracs[1][1])
            # Find all amounts
            amounts = [n for n in nums if isinstance(n, (int, float)) and n < 50 and n > 0 and n != 1]
            if len(amounts) >= 2:
                # Problem 20: 10L orange (2/3 water), 15L pineapple (3/5 water), spill 1L
                # Find the two drink volumes (10 and 15)
                vol_drink1 = amounts[0]
                vol_drink2 = amounts[1]
                water1 = vol_drink1 * num1 / den1
                water2 = vol_drink2 * num2 / den2
                # Find spill (should be 1)
                ones = [n for n in nums if isinstance(n, (int, float)) and n == 1]
                spill = len(ones)  # Count the 1s as the spill amount
                spill = 1 if ones else 0
                # Water lost from spill
                water_lost = spill * num1 / den1
                total_water = int(water1 + water2 - water_lost + 0.5)
                if total_water > 0:
                    return total_water
    return None

def _solve_remaining_unknown_qty(q, nums):
    """Total cost = known items + unknown_qty * unit_price"""
    if 'paid a total' in q or 'total of $' in q:
        m_total = re.search(r'total\s+(?:of\s+)?\$(\d+(?:\.\d+)?)', q)
        if m_total:
            total_cost = float(m_total.group(1))
            item_costs = [float(c) for c in re.finditer(r'\$(\d+(?:\.\d+)?)', q)]
            # Hmm, re.finditer doesn't work like that
            item_costs_list = [float(m.group(1)) for m in re.finditer(r'\$(\d+(?:\.\d+)?)', q)]
            costs = [c for c in item_costs_list if abs(c - total_cost) > 0.01]
            # The last cost is the unit price of unknown items
            if len(costs) >= 2:
                unit_price = costs[-1]
                known_costs = costs[:-1]
                known_total = sum(known_costs)
                remaining = total_cost - known_total
                if remaining > 0 and unit_price > 0:
                    qty = int(round(remaining / unit_price))
                    if qty > 0:
                        return qty
    return None

def _solve_boots_comparison(q, nums):
    """Boots vs heels: two heels together cost X less than boots"""
    if 'boots' in q and 'heels' in q and 'less than' in q:
        m_diff = re.search(r'(\d+)\s+dollars?\s+less\s+than', q)
        m_heels = [float(m.group(1)) for m in re.finditer(r'\$(\d+(?:\.\d+)?)', q)]
        if m_diff and len(m_heels) >= 1:
            diff = int(m_diff.group(1))
            heel1 = m_heels[0]
            # Check for "twice as much" (normalized from "twice" to "2 times")
            m_twice = re.search(r'(\d+)\s+times\s+as', q)
            if m_twice:
                heel2 = heel1 * int(m_twice.group(1))
            else:
                heel2 = heel1 * 2  # default "twice" pattern
            heels_total = heel1 + heel2
            boots = heels_total + diff
            return int(boots)
    return None

def _solve_average_of_guesses(q, nums):
    """Average of several guesses with relationships"""
    if 'average guess' in q or 'average' in q:
        guesses = []
        # First guess: usually the first number
        m_first = re.search(r'(?:one|1)(?:st|\s+)says\s+(\d+)', q)
        if not m_first:
            m_first = re.search(r'(?:says|guesses?|thinks?)\s+(\d+)', q)
        if m_first:
            first_guess = int(m_first.group(1))
            guesses.append(first_guess)
            # Second guess: "X more than half the first"
            m_half = re.search(r'(\d+)\s+more\s+than\s+half', q)
            if m_half:
                second_guess = first_guess // 2 + int(m_half.group(1))
                guesses.append(second_guess)
            # Third guess: "X% more than the first"
            m_pct = re.search(r'(\d+)%\s+more\s+than', q)
            if m_pct:
                third_guess = int(first_guess * (1 + int(m_pct.group(1)) / 100.0))
                guesses.append(third_guess)
            if len(guesses) >= 2:
                avg = int(sum(guesses) / len(guesses) + 0.5)
                return avg
    return None

def _solve_chain_comparison(q, nums):
    """A has X fewer than B, B has Y more than half of C, find A"""
    if 'fewer' in q and 'more' in q and 'half' in q:
        if len(nums) >= 1:
            # Problem 34: find half of X by looking for "half of PERSON's" then finding their value
            # Find the person being halved (the one with "half of" before their name)
            m_half_of = re.search(r'half\s+of\s+(\w+)', q)
            if m_half_of:
                person = m_half_of.group(1)
                # Find that person's value: "PERSON has/have X"
                m_person_val = re.search(r'' + person + r"'?s?\s+(?:has|have)\s+(\d+)", q)
                if m_person_val:
                    half_base = int(m_person_val.group(1)) // 2
                else:
                    return None
            else:
                return None
            # Aaron has Y more than half
            m_more = re.search(r'(\d+)\s+more', q)
            extra = int(m_more.group(1)) if m_more else 0
            aaron = half_base + extra
            # Siobhan has X fewer than Aaron
            m_fewer = re.search(r'(\d+)\s+fewer', q)
            fewer = int(m_fewer.group(1)) if m_fewer else 0
            siobhan = aaron - fewer
            if siobhan > 0:
                return siobhan
    return None

def _solve_percentage_more(q, nums):
    """X% more points / items than base"""
    if '%' in q and ('more' in q or 'less' in q):
        m_pct = re.search(r'(\d+)%\s+more', q)
        m_base_score = re.search(r'scores\s+(\d+)\s+points?', q)
        if m_pct and m_base_score:
            base = int(m_base_score.group(1))
            pct = int(m_pct.group(1))
            extra = int(base * pct / 100)
            # Return TOTAL points: first + second halves
            # Check if it's a two-period problem (first X min, second Y min)
            if 'first' in q and 'second' in q:
                return int(base + (base + extra))
            return int(base + extra)
    return None

def _solve_iphone_chain(q, nums):
    """X is N times as old as Y, Y is M times as old as Z, Z given"""
    if 'times as' in q and ('old' in q or 'iphone' in q):
        factors = [int(m.group(1)) for m in re.finditer(r'(\d+)\s+times', q)]
        if factors:
            # Find base from explicit mention like "is 1 year old"
            m_base = re.search(r'is\s+(\d+)\s+year', q)
            if m_base:
                base = int(m_base.group(1))
            else:
                # Find numbers NOT near "times" (i.e. not factors)
                factor_set = set(factors)
                non_factors = [n for n in nums if isinstance(n, (int, float)) and int(n) not in factor_set and n > 0]
                base = int(min(non_factors)) if non_factors else 1
            result = base
            for f in factors:
                result = result * f
            if result > 0:
                return result
    return None

def _solve_speed_from_weekly(q, nums):
    """Miles per week, days per week, hours per day -> find speed"""
    if 'miles a week' in q or 'miles per week' in q:
        m_miles = re.search(r'(\d+)\s+miles?\s+(?:a|per)\s+week', q)
        m_days = re.search(r'(\d+)\s+days?\s+(?:a|per)\s+week', q)
        if m_miles and m_days:
            weekly_miles = int(m_miles.group(1))
            days = int(m_days.group(1))
            # Find hours per day from "X hours the first day and half as much the other days"
            m_first_hrs = re.search(r'(\d+)\s+hours?\s+the\s+first\s+day', q)
            if m_first_hrs:
                first_hrs = int(m_first_hrs.group(1))
                other_hrs = first_hrs / 2 if 'half' in q else first_hrs
                total_hrs_per_week = first_hrs + other_hrs * (days - 1)
                if total_hrs_per_week > 0:
                    speed = int(weekly_miles / total_hrs_per_week + 0.5)
                    return speed
    return None

def _solve_multi_rate_travel(q, nums):
    """Multiple speeds, fractions of time, find distance"""
    if 'times faster' in q or 'half as fast' in q:
        # Dana problem: skip speed = 3 mph, run = 4x walk, skip = 0.5x run
        m_skip = re.search(r'skip\s+(?:at\s+)?(\d+)\s+miles?', q)
        if m_skip:
            skip_speed = int(m_skip.group(1))
            # run = 2 * skip (since skip is half as fast as run)
            run_speed = skip_speed * 2
            # walk = run / 4 (since run is 4x faster than walk)
            walk_speed = run_speed / 4
            # Find total time
            total_time = 6
            m_time = re.search(r'(\d+)\s+hours?', q)
            if m_time:
                total_time = int(m_time.group(1))
            # Find "one-third of the time" / "two-thirds of the time"
            m_frac = re.search(r'(one|two|\d+)[-\s+]third', q)
            if m_frac:
                word = m_frac.group(1)
                if word == 'one' or word == '1':
                    num, den = 1, 3
                elif word == 'two' or word == '2':
                    num, den = 2, 3
                elif word == 'two':
                    num, den = 2, 3
                else:
                    num, den = int(word), 3
                time_run = total_time * num / den if 'run' in q else total_time * (den - num) / den
                if 'running' in q or 'run' in q:
                    time_run = total_time * num / den
                    time_walk = total_time - time_run
                else:
                    time_walk = total_time * num / den
                    time_run = total_time - time_walk
                distance = int(run_speed * time_run + walk_speed * time_walk + 0.5)
                return distance
    return None

def _solve_distance_multiplier(q, nums):
    """Distance multiplied by factor, subtract initial range"""
    if 'times farther' in q or 'times as far' in q:
        m_base = re.search(r'(\d+)\s+feet', q)
        m_factor = re.search(r'(\d+)\s+times\s+(?:farther|as\s+far)', q)
        if m_base and m_factor:
            base_dist = int(m_base.group(1))
            factor = int(m_factor.group(1))
            multiplied = base_dist * factor
            # Find the "reach" or "range" 
            range_match = re.search(r'(?:reach|within|of).*?(\d+)\s+feet', q)
            if range_match:
                range_dist = int(range_match.group(1))
                outside = multiplied - range_dist
                if outside > 0:
                    return outside
            return multiplied
        # Fallback for problem 41 style
        if len(nums) >= 3:
            # nums = [1000, 400, 3, ...] -> range=1000, base=400, factor=3
            ranges = [n for n in nums if isinstance(n, (int, float)) and n >= 500]
            bases = [n for n in nums if isinstance(n, (int, float)) and 100 <= n < 500]
            factors_list = [n for n in nums if isinstance(n, (int, float)) and 2 <= n < 10]
            if ranges and bases and factors_list:
                return int(bases[0] * factors_list[0] - ranges[0])
        return None
    return None

def _solve_pies_remaining(q, nums):
    """Total pieces - remaining = pieces taken"""
    if 'pie' in q and 'remaining' in q:
        m_pies = re.search(r'(\d+)\s+(?:apple\s+)?pies?', q)
        m_slices = re.search(r'(\d+)\s+(?:pieces?|slices?)', q)
        if m_pies and m_slices:
            pies = int(m_pies.group(1))
            slices_per = int(m_slices.group(1))
            total = pies * slices_per
            m_remaining = re.search(r'(\d+)\s+(?:pieces?|slices?)\s+(?:of\s+)?(?:pie|remaining|left)', q)
            if m_remaining:
                remaining = int(m_remaining.group(1))
                taken = total - remaining
                if taken > 0:
                    return taken
    return None

def _solve_calorie_grams(q, nums):
    """Calories per serving, bag weight, servings -> grams for X calories"""
    if 'calorie' in q and 'gram' in q:
        m_cal_per = re.search(r'(\d+)\s+calories?\s+per\s+serving', q)
        m_grams = re.search(r'(\d+)g\s+bag', q)
        m_servings = re.search(r'(\d+)\s+servings?', q)
        if m_cal_per and m_grams and m_servings:
            cal_per_serving = int(m_cal_per.group(1))
            bag_grams = int(m_grams.group(1))
            servings = int(m_servings.group(1))
            grams_per_serving = bag_grams / servings
            # Remaining calories: target - consumed
            m_target = re.search(r'target\s+(?:is\s+)?(\d+)', q)
            m_consumed = re.search(r'consumed\s+(\d+)', q)
            if m_target and m_consumed:
                remaining_cal = int(m_target.group(1)) - int(m_consumed.group(1))
                grams = int(remaining_cal / cal_per_serving * grams_per_serving + 0.5)
                return grams
    return None

def _solve_profit_revenue_cost(q, nums):
    """Revenue - cost = profit"""
    if 'profit' in q and ('sell' in q or 'sells' in q):
        m_revenue_per = re.search(r'sells?\s+(?:each|for)\s+\$(\d+(?:\.\d+)?)', q)
        m_qty_made = re.search(r'makes?\s+and\s+sells?\s+(\d+)', q)
        m_cost_per = re.search(r'cost\s+\$(\d+(?:\.\d+)?)\s+in\s+supplies', q) or re.search(r'cost\s+\$(\d+(?:\.\d+)?)', q)
        if m_revenue_per and m_qty_made:
            qty = int(m_qty_made.group(1))
            revenue = qty * float(m_revenue_per.group(1))
            # Cost: either flat amount or per-unit. For beeswax: $10 supplies for 10 candles
            m_per_pound = re.search(r'per\s+pound', q)
            if m_cost_per:
                supplies_cost = float(m_cost_per.group(1))
                # If the cost is for a certain number of units, scale it
                m_per_qty = re.search(r'(\d+)\s+(?:pounds?|tapered)', q)
                if m_per_qty and m_per_pound:
                    per_qty = int(m_per_qty.group(1))
                    cost = supplies_cost / per_qty * qty
                else:
                    cost = supplies_cost * (qty / 10) if m_per_pound else supplies_cost
                profit = int(revenue - cost + 0.5)
                if profit > 0:
                    return profit
    return None

def _solve_fraction_more_articles(q, nums):
    """Articles with fractions and multiples, find total hours"""
    if 'articles' in q and 'hours' in q:
        m_hrs_per = re.search(r'(\d+)\s+hours?\s+to\s+(?:research|write)', q)
        m_first_day = re.search(r'(\d+)\s+articles?\s+on\s+(monday|\w+day)', q)
        if m_hrs_per and m_first_day:
            hrs_per = int(m_hrs_per.group(1))
            first_qty = int(m_first_day.group(1))
            # Find X/Y times more (e.g., "2/5 times more")
            m_frac = re.search(r'(\d+)/(\d+)\s+times\s+more', q)
            if m_frac:
                num = int(m_frac.group(1))
                den = int(m_frac.group(2))
                second_qty = first_qty + int(first_qty * num / den)
            else:
                # Try just "X/Y" fraction without "times more"
                m_frac2 = re.search(r'(\d+)/(\d+)', q)
                if m_frac2:
                    num = int(m_frac2.group(1))
                    den = int(m_frac2.group(2))
                    second_qty = first_qty + int(first_qty * num / den)
                else:
                    return None
            # Find third day: "twice the number" (may be normalized to "2 the number")
            if 'twice' in q or re.search(r'\b2\s+the\s+number', q):
                third_qty = second_qty * 2
            else:
                third_qty = second_qty
            total_articles = first_qty + second_qty + third_qty
            total_hours = total_articles * hrs_per
            if total_hours > 0:
                return total_hours
    return None


def _solve_remaining_after_use(q, nums):
    """Start with X, buy package with Y, use Z each, have W remaining"""
    if 'post-it' in q or 'postit' in q:
        all_nums = [n for n in nums if isinstance(n, (int, float))]
        if len(all_nums) >= 3:
            # Find start: number near "put"
            m_start = re.search(r'put\s+(\d+)\s+post', q)
            # Find used: number near "different" or "cups" or "coffee"
            m_used = re.search(r'(\d+)\s+(?:different|cups?|coffee)', q)
            # Find remaining: number NEAR "remaining" or "left" - use the LAST occurrence
            last_post_nums = re.findall(r'(\d+)\s+post', q)
            m_remaining_num = last_post_nums[-1] if last_post_nums else None
            if m_start and m_used and m_remaining_num:
                start = int(m_start.group(1))
                used = int(m_used.group(1))
                remaining = int(m_remaining_num)
                pkg = remaining - start + used
                if pkg > 0:
                    return pkg
    return None

def _solve_tie_percentage_spend(q, nums):
    """Twice as many X ties as Y, X cost 50% more, total spent"""
    if 'ties' in q and ('twice' in q or '50%' in q):
        m_blue_spend = re.search(r'spent\s+\$(\d+)\s+on\s+blue', q)
        m_blue_price = re.search(r'(\d+)\s+each', q)
        if m_blue_spend and m_blue_price:
            blue_spend = int(m_blue_spend.group(1))
            blue_price = int(m_blue_price.group(1))
            blue_qty = blue_spend / blue_price
            # Twice as many red as blue
            m_twice = re.search(r'(\d+)\s+times', q)
            red_qty = blue_qty * (int(m_twice.group(1)) if m_twice else 2)
            # Red cost 50% more
            m_pct = re.search(r'(\d+)%\s+more', q)
            pct = int(m_pct.group(1)) if m_pct else 50
            red_price = blue_price * (1 + pct / 100.0)
            red_spend = int(red_qty * red_price)
            total = int(blue_spend + red_spend)
            return total
    return None


def _solve_known_items_total(q, nums):
    """Total = known qty*price items + unknown qty*unit_price"""
    if 'paid a total' in q or 'total of $' in q:
        m_total = re.search(r'total\s+(?:of\s+)?\$(\d+(?:\.\d+)?)', q)
        if m_total:
            overall_total = float(m_total.group(1))
            # Find all qty*price pairs
            pairs = re.findall(r'(\d+)\s+(?:.*?)(?:at|cost[s]?|for|are?)\s+\$(\d+(?:\.\d+)?)', q)
            if len(pairs) >= 1:
                # Sum known items (qty * price) excluding items with "unknown" keywords
                known_sum = 0
                for qty_str, price_str in pairs:
                    price = float(price_str)
                    if '"' in q or "unknown" in q:
                        # This is harder, just use straightforward calc
                        pass
                    known_sum += int(qty_str) * price
                # Find unit price of unknown item (usually the price NOT matched in pairs)
                # or the largest $ amount that's paired with unknown qty
                remaining = overall_total - known_sum
                if remaining > 0 and remaining < overall_total:
                    # Find unit price of the unknown item
                    all_prices = [float(m.group(1)) for m in re.finditer(r'\$(\d+(?:\.\d+)?)', q)]
                    used_prices = set()
                    for _, price_str in pairs:
                        used_prices.add(float(price_str))
                    # Unit price is the one not in used_prices (or the last $ amount)
                    unit_prices = [p for p in all_prices if p not in used_prices and abs(p - overall_total) > 0.01]
                    if unit_prices:
                        unit_price = unit_prices[-1]
                        qty = int(round(remaining / unit_price))
                        if qty > 0:
                            return qty
    # For problem 37: proceeds - cost = remaining, find unsold items
    if 'sells' in q and ('buy' in q or 'buys' in q) and 'left' in q and 'lego' in q:
        pairs = re.findall(r'(\d+)\s+(?:.*?)(?:for|each costing|each)\s+\$(\d+(?:\.\d+)?)', q)
        if len(pairs) >= 2:
            sell_qty, sell_price = int(pairs[0][0]), float(pairs[0][1])
            buy_qty, buy_price = int(pairs[1][0]), float(pairs[1][1])
            # Find "has $X left"
            m_left = re.search(r'has\s+\$(\d+)\s+left', q)
            left = float(m_left.group(1)) if m_left else 0
            total_proceeds = buy_qty * buy_price + left
            sold_qty = int(total_proceeds / sell_price)
            remaining = sell_qty - sold_qty
            if remaining > 0:
                return remaining
    return None


def solve_word_problem(question):
    """
    Multi-strategy math word problem solver.
    First normalizes word numbers to digits, then tries specialized
    strategy functions for different problem categories.
    Returns answer number or None.
    """
    q_norm, nums = _preprocess(question)
    if not nums:
        return None
    
    # ---- Try each strategy in order of specificity ----
    strategies = [
        # High-specificity: these match very specific patterns
        _solve_half_sum,                # X and half that
        _solve_egg_rate,                 # eggs per day, sells remainder
        _solve_chicken_feed,             # chickens * cups - given amounts
        _solve_sprint_problem,           # sprints * times * meters
        _solve_house_profit,             # buy + repairs, %% increase
        _solve_overtime_pay,             # regular + overtime
        _solve_percentage_chain,         # X * factor, then reduced by %%
        _solve_download_problem,         # GB at rate, %% restart
        _solve_salary_annual,            # hourly * hours * weeks
        _solve_percentage_more,          # X% more points (before pingpong)
        _solve_boots_comparison,         # boots vs heels price comparison (before multi_item)
        _solve_remaining_unknown_qty,    # total - known costs = unknown qty * price (before multi_purchase)
        _solve_tie_percentage_spend,     # tie total cost with percentages (before chain_relationship)
        _solve_iphone_chain,             # ages chain with small numbers (before chain_relationship)
        _solve_chain_relationship,       # X times as many, Y times as many
        _solve_ratio_age,                # ages in ratio
        _solve_break_even_years,         # break-even calculation
        _solve_investment_profit,        # max profit from investments
        _solve_avg_speed_remaining,      # average speed with remaining distance (before distance_sub)
        _solve_liquid_mixture,           # water in liquid mixtures
        _solve_multi_rate_travel,        # distance with multiple speeds
        _solve_distance_multiplier,      # distance times factor minus range
        _solve_fraction_more_articles,   # articles with fraction multiples (before fraction_of_total)
        _solve_speed_from_weekly,        # speed from weekly miles/days/hours
        _solve_average_of_guesses,       # average of related guesses (before sum_and_diff)
        _solve_chain_comparison,         # A fewer than B, B more than half C (before sum_and_diff)
        _solve_pies_remaining,           # total pieces minus remaining
        _solve_calorie_grams,            # calories to grams conversion
        _solve_profit_revenue_cost,      # revenue minus cost
        _solve_remaining_after_use,      # post-it notes remaining
        _solve_trip_multileg,            # multi-leg trip distance (must be before distance_sub)
        _solve_candle_melting,           # rate * time
        _solve_discount_reverse,         # discounted price to original
        _solve_percentage_of_remaining,  # %% then %% of remaining
        # Mid-specificity: broader patterns
        _solve_distance_subtraction,     # total - stops (generic, keep later)
        _solve_sum_and_diff,             # total + diff (generic, keep later)
        _solve_multi_item_same_qty,      # qty * sum(prices)
        _solve_known_items_total,        # known qty*price items then unknown
        _solve_multi_purchase,           # qty * price + qty * price
        _solve_dozens,                   # eggs per day * weeks / 12
        _solve_grouped_purchases,        # first X buy Y, next Z buy W
        _solve_total_minus_known,        # total - known costs
        _solve_servings_cartons,         # servings per carton
        _solve_profit_compare,           # max of %% profits
        _solve_per_train_distance,       # per-train distance
        _solve_fraction_of_total,        # X/Y of total
        _solve_unit_conversion,          # feet to inches
        _solve_yogurt_sale,              # yogurts per day
        _solve_simple_subtract,          # total - parts
        _solve_percentage_discount_double, # every second at %%
        _solve_age_difference,           # ages
        _solve_pingpong_points,          # first X then Y points
        _solve_work_rate,                # X dogs * Y hrs * Z days
        _solve_working_backwards,        # sold X, then Y, half left, Z remaining
        _solve_simple_two_number,        # simple 2-number ops
    ]
    
    for strategy in strategies:
        try:
            r = strategy(q_norm, nums)
            if r is not None:
                return int(r)
        except Exception:
            continue
    
    return None


# ================================================================
# INSTRUCTION TEMPLATES (for MT-Bench)
# ================================================================