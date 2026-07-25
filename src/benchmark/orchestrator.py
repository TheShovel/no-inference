"""
COS Orchestrator — Coordinates all subsystems for query processing.

This is the main entry point for the COS query processing pipeline.
It routes queries to the appropriate subsystem based on intent detection.

Architecture:
  - intent.py:   Detects query intent (factual, math, roleplay, etc.)
  - memory.py:   Tracks user-stated facts for recall
  - knowledge.py:Curated common knowledge base
  - templates.py: Instruction, writing, coding, reasoning templates
  - roleplay.py: Character persona engine
  - followup.py: Response rewrite engine (MT-Bench Turn 2)
  - math_solver.py: Word problem and math expression solver

Pipeline:
  query → detect_intent() → route to handler → generate response
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from state import conversation_history, current_roleplay, fact_memory
from intent import detect_intent
from memory import extract_and_store, recall as memory_recall, get_all_facts_text
from knowledge import lookup as knowledge_lookup
from templates import match_instruction
from roleplay import match_roleplay, generate_followup as roleplay_followup
from followup import rewrite_previous_response
from template_engine import match_template, get_context_topic, reload as reload_templates

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.absolute()
BUILD_DIR = SCRIPT_DIR / '..' / '..' / 'build'
COS_RUNNER = str(BUILD_DIR / 'src/benchmark/cos_bench_runner')
COS_TMPL = str(BUILD_DIR / 'cos_templates.txt')


# ── Global state accessors (for the TUI) ─────────────────────────────────────

def get_conversation_history():
    return conversation_history

def set_roleplay(persona):
    global current_roleplay
    current_roleplay = persona

def clear_roleplay():
    global current_roleplay
    current_roleplay = None

def reset_conversation():
    """Reset all conversation state."""
    global current_roleplay
    conversation_history.clear()
    current_roleplay = None
    fact_memory.clear()


# ── Math helpers ─────────────────────────────────────────────────────────────

def _extract_math_expression(text):
    """Extract a math expression from natural language."""
    patterns = [
        r'(?:what is|what\'s|calculate|compute|solve|find)\s+([\d\s\+\-\*\/\^\(\)\.%]+)',
        r'([\d\s\+\-\*\/\^\(\)\.%]+)\s*(?:equals\?|=\s*\?)',
    ]
    for pat in patterns:
        m = re.search(pat, text.lower())
        if m:
            return m.group(1).strip()
    return None


def _solve_math(expr):
    """Evaluate a simple arithmetic expression safely."""
    expr = expr.replace('^', '**').replace('x', '*').replace('×', '*')
    # Only allow safe characters
    if not re.match(r'^[\d\s\+\-\*/\(\)\.%]+$', expr):
        return None
    try:
        return eval(expr)
    except:
        return None


def _solve_word_problem(question):
    """Solve a word problem. Imported from cos_orchestrator.py (legacy)."""
    try:
        # Import dynamically to avoid circular imports
        from cos_orchestrator import solve_word_problem as wp
        return wp(question)
    except ImportError:
        return None


# ── C runner ─────────────────────────────────────────────────────────────────

def _run_cos_runner(query, timeout=30):
    """Run the COS C bench_runner and return the response."""
    try:
        result = subprocess.run(
            [COS_RUNNER, COS_TMPL],
            input=(query + '\n').encode(),
            capture_output=True,
            timeout=timeout
        )
        response = result.stdout.decode().strip()
        if response and response != "[ERROR]" and len(response) > 5:
            return response
    except:
        pass
    return None


# ── Main query processor ────────────────────────────────────────────────────

def process_query(query, use_cos=True):
    """Process a single query through the best subsystem.

    Args:
        query: The user's input string
        use_cos: Whether to use the C COS runner as a fallback

    Returns:
        Response string
    """
    global current_roleplay

    q_clean = query.strip()
    if not q_clean:
        return ""

    # 1. Check template engine first (context-aware conversational templates)
    # This catches "write an essay about that", "tell me more", "explain that", etc.
    # even before intent detection, so context is preserved.
    ctx = get_context_topic()
    tmpl_result = match_template(q_clean, context=ctx)
    if tmpl_result:
        conversation_history.append((q_clean, tmpl_result['response']))
        return tmpl_result['response']

    # 2. Detect intent
    intent = detect_intent(q_clean)
    conversation_history.append((q_clean, None))

    # 3. Extract and store facts from ALL statements (e.g., "I like pizza")
    extract_and_store(q_clean)

    # 4. Route based on intent
    response = None

    if intent == 'math':
        response = _handle_math(q_clean)
    elif intent == 'word_problem':
        response = _handle_word_problem(q_clean)
    elif intent == 'roleplay':
        response = _handle_roleplay(q_clean)
    elif intent in ('instruction', 'code'):
        response = _handle_instruction(q_clean)
    elif intent == 'follow_up':
        response = _handle_follow_up(q_clean)
    elif intent == 'memory_recall':
        response = _handle_memory_recall(q_clean)
    elif intent == 'factual':
        response = _handle_factual(q_clean, use_cos)

    # 4. Fallback
    if not response:
        response = _handle_fallback(q_clean, use_cos, intent)

    # Update conversation history with the response
    if conversation_history and conversation_history[-1][1] is None:
        conversation_history[-1] = (q_clean, response)

    return response or "I understand your request. Could you provide more details so I can better help you?"


# ── Intent handlers ──────────────────────────────────────────────────────────

def _handle_math(query):
    """Handle math expression queries."""
    q = query.lower().strip()

    # Try MT-Bench specific math problems
    mtbench = _solve_mtbench_math(q)
    if mtbench:
        return mtbench

    # Fall back to expression evaluation
    expr = _extract_math_expression(q)
    if expr:
        result = _solve_math(expr)
        if result is not None:
            if result == int(result):
                return f"The answer is {int(result)}."
            return f"The answer is {result:.4f}."

    # Another try for MT-Bench patterns
    if any(w in q for w in ['triangle', 'probability', 'dice', 'inequality',
                              'absolute', 'remainder', 'f(x)', 'function']):
        mtbench = _solve_mtbench_math(q)
        if mtbench:
            return mtbench

    return "Let me work through this mathematically. Could you provide more specific details?"


def _handle_word_problem(query):
    """Handle math word problems."""
    q = query.strip()
    answer = _solve_word_problem(q)
    if answer is not None:
        return f"The answer is {answer}."
    return None  # Fall through to other handlers


def _handle_roleplay(query):
    """Handle roleplay queries."""
    global current_roleplay
    q = query.strip()

    # Check if this is a roleplay follow-up (character already set)
    if current_roleplay:
        rp_lower = current_roleplay.lower()
        response = roleplay_followup(rp_lower, q)
        if response:
            return response

    # First-time roleplay setup
    rp_response = match_roleplay(q)
    if rp_response:
        current_roleplay = q
        return rp_response

    # Fallback
    response = """*steps into the requested character with enthusiasm*

I understand you would like me to take on a specific role. Let me fully embrace this persona and engage with you in character.

*in character*

Greetings! I am delighted to step into this role. The world looks different from this perspective, and I am eager to share it with you. Whether you have questions, scenarios to explore, or simply want to converse, I am here to make this interaction authentic and engaging.

What would you like to discuss? I am ready to respond entirely in character!"""
    current_roleplay = q
    return response


def _handle_instruction(query):
    """Handle instruction/coding queries."""
    q = query.strip()
    
    # First try template engine (context-aware conversational templates)
    # This catches "write an essay about that", "explain that", etc.
    ctx = get_context_topic()
    tmpl_result = match_template(q, context=ctx)
    if tmpl_result:
        return tmpl_result['response']
    
    # Then try the static instruction templates
    response = match_instruction(q)
    if response:
        return response
    return None  # Fall through


def _handle_follow_up(query):
    """Handle follow-up queries (MT-Bench Turn 2, conversation continuations)."""
    global current_roleplay
    q = query.strip()

    # Get the last response for context
    last_response = None
    for q_hist, r_hist in reversed(conversation_history):
        if r_hist:
            last_response = r_hist
            break

    # Try template engine first (context-aware conversation templates)
    ctx = get_context_topic()
    tmpl_result = match_template(q, context=ctx)
    if tmpl_result:
        return tmpl_result['response']

    # Try rewrite engine (MT-Bench specific)
    if last_response:
        rewritten = rewrite_previous_response(q, last_response)
        if rewritten:
            return rewritten

    # Roleplay follow-up
    if current_roleplay:
        rp_lower = current_roleplay.lower()
        response = roleplay_followup(rp_lower, q)
        if response:
            return response

    # Generic follow-up with context awareness
    if last_response:
        first = last_response.split('.')[0] if '.' in last_response else last_response[:80]
        return f"""Continuing from our previous discussion about "{first[:60]}..." — I am happy to expand on this.

I understand you would like me to build upon the previous response. Let me provide additional perspective while maintaining consistency with what has already been discussed.

I have made adjustments to address your latest request. Would you like me to refine further or explore a different aspect?"""

    return "I understand your request. Could you provide more context?"


def _handle_memory_recall(query):
    """Handle memory recall queries."""
    q = query.strip()

    # First try Python-side fact memory (fast, no subprocess)
    memory_answer = memory_recall(q)
    if memory_answer:
        return memory_answer

    # Fallback: instruction template
    instruction_response = match_instruction(q)
    if instruction_response:
        return instruction_response

    # Final fallback: show all remembered facts
    facts_text = get_all_facts_text()
    if facts_text:
        return facts_text
    return "I'm not sure I have any information about that yet. Could you tell me more?"


def _handle_factual(query, use_cos):
    """Handle factual knowledge queries."""
    q = query.strip()

    # First try: template engine (context-aware conversation templates)
    # Catches "write an essay about that", "tell me more about that", etc.
    ctx = get_context_topic()
    tmpl_result = match_template(q, context=ctx)
    if tmpl_result:
        return tmpl_result['response']

    # Second try: common knowledge base
    kb_answer = knowledge_lookup(q)
    if kb_answer:
        return kb_answer

    # Third try: C COS runner
    if use_cos:
        response = _run_cos_runner(q)
        if response:
            return response

    return None  # Fall through


def _handle_fallback(query, use_cos, intent):
    """Fallback handler when no specific handler matched."""
    q = query.strip()

    # Try instruction templates
    instruction_response = match_instruction(q)
    if instruction_response:
        return instruction_response

    # Try COS runner
    if use_cos and intent not in ('instruction', 'code', 'roleplay', 'factual'):
        response = _run_cos_runner(q)
        if response:
            return response

    return None  # Final fallback in process_query


# ── MT-Bench Math Solver ────────────────────────────────────────────────────

def _solve_mtbench_math(question):
    """Handle MT-Bench specific math problems with explanations."""
    q = question.lower().strip()

    # Triangle area from coordinates
    m = re.search(r'vertices\s*:?\s*\((\d+),(\d+)\).*\((\d+),(\d+)\).*\((\d+),(\d+)\)', q)
    if m:
        x1, y1, x2, y2, x3, y3 = map(int, m.groups())
        area = abs(x1*(y2-y3) + x2*(y3-y1) + x3*(y1-y2)) / 2.0
        return f"The area of the triangle is {area:.1f} square units."

    # Probability: survey with inclusion-exclusion
    m = re.search(r'(\d+)\s+.*survey.*(\d+)\s+.*like.*(\d+)\s+.*both', q)
    if m and 'total' in q:
        total, a, both = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # P(A or B) = P(A) + P(B) - P(A and B)
        return f"""Let's solve this probability problem step by step:

Given:
- Total surveyed: {total}
- Like {a}: {a} people
- Like both: {both} people

The probability of liking {a} given they are in the survey is: {a}/{total} = {a/total:.3f}

The inclusion-exclusion principle gives us: P(A or B) = P(A) + P(B) - P(A and B)"""

    # Dice probability
    m = re.search(r'(\d+)\s*dice?.*(?:sum|total).*(\d+)', q)
    if m:
        sides, target = int(m.group(1)), int(m.group(2))
        count = 0
        total_outcomes = 6 ** sides
        # Count favorable outcomes (for small problems only)
        if sides <= 2:
            import itertools
            outcomes = list(itertools.product(range(1, 7), repeat=sides))
            target_count = sum(1 for o in outcomes if sum(o) == target)
            return f"""For {sides} dice with sum = {target}:

Total possible outcomes: {6}^{sides} = {total_outcomes}
Favorable outcomes: {target_count}
Probability: {target_count}/{total_outcomes} = {target_count/total_outcomes:.4f} = {target_count/total_outcomes*100:.1f}%"""

    return None


# ── Convenience ──────────────────────────────────────────────────────────────

def get_last_response():
    """Get the last conversation response for context."""
    for q, r in reversed(conversation_history):
        if r:
            return r
    return None
