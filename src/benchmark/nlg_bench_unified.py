#!/usr/bin/env python3
"""
Unified NLG Benchmark Runner.
Runs GSM8K, TruthfulQA, MT-Bench through the universal NLG system
(cos.engine.process_query → naturalize → NLP pipeline).

Compares results with the legacy C-based benchmark.
"""

import json, re, sys, os, time
from pathlib import Path

# Ensure import paths
_SRC_BENCH = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.normpath(os.path.join(_SRC_BENCH, '..', '..', 'src'))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# ── Import the unified NLG engine ──────────────────────────────────────────
from cos.engine import process_query as nlg_process_query

# ── Import benchmark data loaders from legacy runner ───────────────────────
# (We reuse the same dataset loaders and scorers for fair comparison)
def load_gsm8k():
    with open('/tmp/gsm8k_50.jsonl') as f:
        return [json.loads(line) for line in f]

def load_truthfulqa():
    with open('/tmp/truthfulqa_mc.jsonl') as f:
        return [json.loads(line) for line in f]

def load_mtbench():
    with open('/tmp/mt_bench.jsonl') as f:
        return [json.loads(line) for line in f]


# ── Benchmark runner using unified NLG ─────────────────────────────────────

def run_benchmark(name, questions, expected_fn, scorer_fn):
    correct = 0
    total = len(questions)
    results = []

    sep = '=' * 60
    print(f"\n{sep}")
    print(f"  {name} Benchmark (Unified NLG)")
    print(sep)

    start_time = time.time()
    for i, q in enumerate(questions):
        response = nlg_process_query(q)
        expected = expected_fn(i)
        is_correct = scorer_fn(response, expected)

        if is_correct:
            correct += 1
        results.append((q, response, expected, is_correct))

        if (i+1) % 50 == 0 or i == total - 1 or i < 5:
            status = '✓' if is_correct else '✗'
            print(f"  {status} [{i+1}/{total}] acc={(correct/(i+1))*100:.1f}%")
            if i < 3:
                print(f"     Q: {q[:60]}")
                print(f"     A: {response[:80]}")
                print(f"     E: {str(expected)[:40]}")

    elapsed = time.time() - start_time
    score = correct / total * 100 if total > 0 else 0
    print(f"\n  {name}: {correct}/{total} = {score:.1f}% ({elapsed:.1f}s)")
    return score


# ── GSM8K ──────────────────────────────────────────────────────────────────

def run_gsm8k():
    items = load_gsm8k()
    def expected(i):
        item = items[i]
        ans = item['answer']
        m = re.search(r'####\s*(-?[\d,]+)', ans)
        return m.group(1).replace(',', '') if m else ''
    def scorer(response, expected):
        nums_raw = re.findall(r'-?\d+\.?\d*', response)
        nums = [n.rstrip('.') for n in nums_raw]
        if expected in nums:
            return True
        if expected and expected in response.replace(',', ''):
            return True
        return False
    questions = [item['question'].replace('\n', ' ') for item in items]
    return run_benchmark("GSM8K", questions, expected, scorer)


# ── TruthfulQA ─────────────────────────────────────────────────────────────

def run_truthfulqa():
    items = load_truthfulqa()
    def expected(i):
        item = items[i]
        mc1 = json.loads(item['mc1_targets']) if isinstance(item['mc1_targets'], str) else item['mc1_targets']
        correct = [c for c, l in zip(mc1['choices'], mc1['labels']) if l == 1]
        return correct[0] if correct else ''
    def scorer(response, expected):
        return expected.lower() in response.lower() if expected else False
    questions = [item['question'].replace('\n', ' ') for item in items]
    return run_benchmark("TruthfulQA", questions, expected, scorer)


# ── MT-Bench ───────────────────────────────────────────────────────────────

def run_mtbench():
    conversations = load_mtbench()
    total_turns = sum(len(c['turns']) for c in conversations)
    long_responses = 0
    total_len = 0
    sample_outputs = []

    print(f"\n{'='*60}")
    print(f"  MT-Bench (Unified NLG)")
    print(f"{'='*60}")

    start_time = time.time()
    for ci, conv in enumerate(conversations):
        for ti, turn in enumerate(conv['turns']):
            response = nlg_process_query(turn)
            total_len += len(response)
            if len(response) > 100:
                long_responses += 1
            if ci < 5 and ti < 2:
                sample_outputs.append((ci, ti, conv['category'], turn[:60], response[:80]))

    elapsed = time.time() - start_time
    score = long_responses / total_turns * 100 if total_turns > 0 else 0
    avg_len = total_len / total_turns if total_turns > 0 else 0

    print(f"  Total turns: {total_turns}")
    print(f"  Long responses (>100 chars): {long_responses}/{total_turns} = {score:.1f}%")
    print(f"  Avg response length: {avg_len:.0f} chars")
    print(f"  Time: {elapsed:.1f}s")

    print(f"\n  Sample outputs:")
    for ci, ti, cat, q, r in sample_outputs[:5]:
        print(f"  [{ci}.{ti}] ({cat}) Q: {q}")
        print(f"         R: {r}")
        print()

    return score


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    benchmarks = []
    if '--all' in sys.argv or len(sys.argv) == 1:
        benchmarks = ['gsm8k', 'truthfulqa', 'mtbench']
    else:
        for arg in sys.argv[1:]:
            if arg.startswith('--'):
                benchmarks.append(arg[2:])

    print(f"\n{'#'*70}")
    print(f"  UNIFIED NLG BENCHMARKS")
    print(f"  Engine: cos.engine.process_query → naturalize → NLG pipeline")
    print(f"  Data: /tmp/gsm8k_50.jsonl, /tmp/truthfulqa_mc.jsonl, /tmp/mt_bench.jsonl")
    print(f"{'#'*70}")

    results = []
    if 'gsm8k' in benchmarks:
        results.append(('GSM8K', run_gsm8k()))
    if 'truthfulqa' in benchmarks:
        results.append(('TruthfulQA', run_truthfulqa()))
    if 'mtbench' in benchmarks:
        results.append(('MT-Bench', run_mtbench()))

    if results:
        print(f"\n{'='*60}")
        print(f"  RESULTS SUMMARY")
        print(f"{'='*60}")
        for name, score in results:
            print(f"  {name:15s}: {score:.1f}%")
        avg = sum(s for _, s in results) / len(results)
        print(f"  {'Average':15s}: {avg:.1f}%")
        print(f"{'='*60}")
