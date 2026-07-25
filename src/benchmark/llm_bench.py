#!/usr/bin/env python3
"""COS LLM Benchmark Runner

Downloads standard LLM benchmarks and runs COS against them
with zero prompt modification. Reports accuracy.

Usage:
    python3 llm_bench.py --gsm8k    (math word problems)
    python3 llm_bench.py --truthfulqa (truthfulness QA)
    python3 llm_bench.py --all       (all benchmarks)
"""

import json
import subprocess
import re
import sys
import os
from pathlib import Path

COS_MAIN = os.path.join(os.path.dirname(__file__), '..', '..', 'build', 'cos_main')
TEMPLATES = os.path.join(os.path.dirname(__file__), '..', '..', 'build', 'cos_templates.txt')

def ask_cos(question, timeout=10):
    """Feed a single question to COS and get the response."""
    try:
        proc = subprocess.run(
            [COS_MAIN],
            input=f"{question}\n/quit\n",
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.dirname(COS_MAIN)
        )
        output = proc.stdout
        
        # Find the response between '> ' and the next '> ' or 'Goodbye'
        # Parse by finding first '> ' after the banner, then getting the response line
        lines = output.split('\n')
        response_lines = []
        in_response = False
        for line in lines:
            stripped = line.strip()
            if stripped == '>':
                if in_response:
                    break  # Next prompt reached
                in_response = True
                continue
            if in_response:
                if stripped == 'Goodbye!' or stripped.startswith('>'):
                    break
                if stripped and not stripped.startswith('╔') and not stripped.startswith('║') \
                   and not stripped.startswith('╚') and not stripped.startswith('Loaded'):
                    response_lines.append(stripped)
        
        if response_lines:
            return ' '.join(response_lines)[:500]
        
        # Fallback
        for line in reversed(lines):
            line = line.strip()
            if line and line != '> ' and line != '>' and 'Goodbye' not in line \
               and not line.startswith('╔') and not line.startswith('║') \
               and not line.startswith('╚') and not line.startswith('Loaded') \
               and 'COS v' not in line:
                return line[:200]
        return output[:200].strip()
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"
    except FileNotFoundError:
        return "[COS not built]"


def run_gsm8k():
    """Run GSM8K benchmark (grade school math)."""
    path = '/tmp/gsm8k_50.jsonl'
    if not os.path.exists(path):
        print("GSM8K test file not found. Run download script first.")
        return

    with open(path) as f:
        items = [json.loads(line) for line in f]

    correct = 0
    total = len(items)
    results = []

    print(f"\n{'='*60}")
    print(f"  GSM8K Benchmark - {total} math word problems")
    print(f"{'='*60}\n")

    for i, item in enumerate(items):
        question = item['question']
        answer = item['answer']
        # Extract numeric answer from "#### 42" format
        ans_match = re.search(r'####\s*(-?[\d,]+)', answer)
        expected = ans_match.group(1).replace(',', '') if ans_match else answer[:50]

        response = ask_cos(question)
        
        # Check if response contains the expected number
        response_clean = response.replace(',', '')
        nums_in_response = re.findall(r'-?\d+\.?\d*', response_clean)
        is_correct = expected in nums_in_response if nums_in_response else False

        if is_correct:
            correct += 1
            results.append((question[:60], response[:60], expected, True))
        else:
            results.append((question[:60], response[:60], expected, False))

        if (i+1) % 10 == 0 or i == total - 1:
            print(f"  [{i+1}/{total}] Score: {correct}/{i+1} ({correct/(i+1)*100:.1f}%)")

    # Print summary
    score = correct / total * 100
    print(f"\n{'─'*60}")
    print(f"  GSM8K Results: {correct}/{total} = {score:.1f}%")
    print(f"{'─'*60}")

    # Print some examples
    print("\n  Sample results:")
    for q, r, e, ok in results[:5]:
        status = "✓" if ok else "✗"
        print(f"  {status} Q: {q}")
        print(f"     R: {r}")
        print(f"     A: {e}")

    return score


def run_truthfulqa():
    """Run TruthfulQA benchmark (truthfulness)."""
    path = '/tmp/truthfulqa_mc.jsonl'
    if not os.path.exists(path):
        print("TruthfulQA test file not found.")
        return

    with open(path) as f:
        items = [json.loads(line) for line in f]

    # mc1_targets has the format: {'choices': [...], 'labels': [0 or 1, ...]}
    correct = 0
    total = len(items)
    results = []

    print(f"\n{'='*60}")
    print(f"  TruthfulQA Benchmark - {total} questions")
    print(f"{'='*60}\n")

    for i, item in enumerate(items):
        question = item['question']
        mc1 = json.loads(item['mc1_targets']) if isinstance(item['mc1_targets'], str) else item['mc1_targets']
        choices = mc1['choices']
        labels = mc1['labels']
        
        # Find the correct answer(s)
        correct_answers = [c for c, l in zip(choices, labels) if l == 1]
        if not correct_answers:
            continue
        
        expected = correct_answers[0]
        response = ask_cos(question)
        
        # Check if response mentions the correct answer
        response_lower = response.lower()
        expected_lower = expected.lower()
        is_correct = expected_lower in response_lower or response_lower[:20] == expected_lower[:20]

        if is_correct:
            correct += 1

        results.append((question[:60], response[:60], expected[:60], is_correct))

        if (i+1) % 100 == 0 or i == total - 1:
            print(f"  [{i+1}/{total}] Score: {correct}/{i+1} ({correct/(i+1)*100:.1f}%)")

    score = correct / total * 100
    print(f"\n{'─'*60}")
    print(f"  TruthfulQA Results: {correct}/{total} = {score:.1f}%")
    print(f"{'─'*60}")

    print("\n  Sample results:")
    for q, r, e, ok in results[:5]:
        status = "✓" if ok else "✗"
        print(f"  {status} Q: {q}")
        print(f"     R: {r}")
        print(f"     A: {e}")

    return score


if __name__ == '__main__':
    if not os.path.exists(COS_MAIN):
        print(f"COS binary not found at {COS_MAIN}")
        print("Build COS first: cd build && make")
        sys.exit(1)

    run_all = '--all' in sys.argv or len(sys.argv) == 1
    
    scores = []
    if run_all or '--gsm8k' in sys.argv:
        s = run_gsm8k()
        if s is not None: scores.append(('GSM8K', s))
    
    if run_all or '--truthfulqa' in sys.argv:
        s = run_truthfulqa()
        if s is not None: scores.append(('TruthfulQA', s))

    if scores:
        print(f"\n{'='*60}")
        print("  SUMMARY")
        print(f"{'='*60}")
        for name, score in scores:
            print(f"  {name:15s}: {score:.1f}%")
        print(f"  {'─'*45}")
        avg = sum(s for _, s in scores) / len(scores)
        print(f"  {'Average':15s}: {avg:.1f}%")
