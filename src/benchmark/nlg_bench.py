#!/usr/bin/env python3
"""
COS NLG Benchmark Suite — evaluates the symbolic NLG system on:
  1. Factual Accuracy — does NLG preserve information correctly?
  2. Essay Quality — content richness, structure, fluency  
  3. Determinism — correct behavior at temperature=0
  4. Performance — generation speed
  5. Style Differentiation — are styles meaningfully different?
  6. Artifact Detection — are there bad patterns?
"""

import os, sys, json, time, re, random
_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src')
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
# Also add parent of src in case
_PARENT = os.path.dirname(_SRC)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from cos.nlg import naturalize, generate_essay, NLGConfig, DEFAULT_CONFIG

# ── Test data ────────────────────────────────────────────────────────────────

TEST_CASES = [
    # (name, query, topic, information, key_facts_expected)
    ("France", "What is the capital of France?",
     "capital of France",
     "Paris is the capital of France. Paris is located on the River Seine. "
     "It has a population of over 2 million people. It is known for the Eiffel Tower.",
     ["Paris", "capital", "France", "River Seine", "Eiffel Tower"]),

    ("Fries", "How do I make french fries?",
     "french fries",
     "French fries are made by cutting potatoes into strips. "
     "They are fried in oil until golden brown. "
     "They are often served with salt and ketchup.",
     ["potatoes", "strips", "fried", "oil", "salt"]),

    ("Photosynthesis", "What is photosynthesis?",
     "photosynthesis",
     "Photosynthesis is the process plants use to convert sunlight into energy. "
     "Plants use chlorophyll to capture light energy. "
     "The process produces oxygen as a byproduct. "
     "Photosynthesis is essential for life on Earth.",
     ["sunlight", "energy", "chlorophyll", "oxygen", "plants"]),

    ("Marie Curie", "Who was Marie Curie?",
     "Marie Curie",
     "Marie Curie was a Polish-born physicist and chemist. "
     "She conducted pioneering research on radioactivity. "
     "She discovered two elements: polonium and radium. "
     "She won two Nobel Prizes in different sciences.",
     ["physicist", "chemist", "radioactivity", "polonium", "radium", "Nobel"]),

    ("Quantum", "Explain quantum computing",
     "quantum computing",
     "Quantum computing uses quantum bits or qubits. "
     "Unlike classical bits, qubits can exist in superposition. "
     "This allows quantum computers to solve certain problems much faster.",
     ["qubits", "quantum", "superposition", "classical"]),
]


def suite(name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")

def check(n, c, d=""):
    if c: print(f"  ✓ {n}")
    else: print(f"  ✗ {n}" + (f"\n      {d}" if d else ""))

# ═════════════════════════════════════════════════════════════════════════════
# 1. FACTUAL ACCURACY
# ═════════════════════════════════════════════════════════════════════════════

def bench_factual_accuracy():
    suite("1. Factual Accuracy — does NLG preserve key facts?")

    total = 0
    found = 0
    for name, query, topic, info, expected_facts in TEST_CASES:
        r = naturalize(query, topic, info, "factual", NLGConfig(style="neutral", temperature=0.0))
        r_lower = r.lower()
        for fact in expected_facts:
            total += 1
            if fact.lower() in r_lower:
                found += 1
            else:
                check(f"  {name}: MISSING '{fact}'", False)

    pct = (found / total * 100) if total else 0
    check(f"Fact preservation: {found}/{total} = {pct:.1f}%", pct >= 80, f"Only {pct:.1f}%")

    # Also test essay accuracy
    total_e = 0
    found_e = 0
    for name, query, topic, info, expected_facts in TEST_CASES:
        r = generate_essay(topic, info, NLGConfig(style="neutral", temperature=0.0))
        r_lower = r.lower()
        for fact in expected_facts:
            total_e += 1
            if fact.lower() in r_lower:
                found_e += 1

    pct_e = (found_e / total_e * 100) if total_e else 0
    check(f"Essay fact preservation: {found_e}/{total_e} = {pct_e:.1f}%", pct_e >= 70, f"Only {pct_e:.1f}%")

    return {"factual_accuracy": pct, "essay_accuracy": pct_e}


# ═════════════════════════════════════════════════════════════════════════════
# 2. DETERMINISM
# ═════════════════════════════════════════════════════════════════════════════

def bench_determinism():
    suite("2. Determinism — temperature=0 identical output?")

    deterministic = 0
    total = 0

    styles = ["friendly", "neutral", "concise"]
    for style in styles:
        cfg = NLGConfig(style=style, verbosity=0.4, temperature=0.0)
        for name, query, topic, info, _ in TEST_CASES:
            total += 1
            r1 = naturalize(query, topic, info, "factual", cfg)
            r2 = naturalize(query, topic, info, "factual", cfg)
            r3 = naturalize(query, topic, info, "factual", cfg)
            if r1 == r2 == r3:
                deterministic += 1
            else:
                check(f"  {name} ({style}): NOT deterministic", False)

    # Also test essays
    for style in styles:
        cfg = NLGConfig(style=style, verbosity=0.4, temperature=0.0)
        for name, _, topic, info, _ in TEST_CASES:
            total += 1
            r1 = generate_essay(topic, info, cfg)
            r2 = generate_essay(topic, info, cfg)
            if r1 == r2:
                deterministic += 1

    check(f"Deterministic: {deterministic}/{total}", deterministic == total, f"{total - deterministic} failures")
    return 100.0 * deterministic / total if total else 0


# ═════════════════════════════════════════════════════════════════════════════
# 3. STYLE DIFFERENTIATION
# ═════════════════════════════════════════════════════════════════════════════

def bench_style_diff():
    suite("3. Style Differentiation — are styles meaningfully different?")

    diff_count = 0
    total = 0
    for name, query, topic, info, _ in TEST_CASES:
        total += 1
        friendly = naturalize(query, topic, info, "factual", NLGConfig(style="friendly", verbosity=0.5, temperature=0.5))
        concise = naturalize(query, topic, info, "factual", NLGConfig(style="concise", verbosity=0.1, temperature=0.0))

        len_diff = abs(len(friendly) - len(concise))
        if len_diff > 20:
            diff_count += 1
        else:
            check(f"  {name}: friendly vs concise too similar (len diff={len_diff})", False)

    check(f"Style differentiation: {diff_count}/{total}", diff_count >= 3)
    return 100.0 * diff_count / total if total else 0


# ═════════════════════════════════════════════════════════════════════════════
# 4. CONTENT UNIQUENESS
# ═════════════════════════════════════════════════════════════════════════════

def bench_uniqueness():
    suite("4. Content Uniqueness — different outputs at same temp?")

    unique = 0
    total = 0
    for name, query, topic, info, _ in TEST_CASES:
        total += 1
        cfg = NLGConfig(style="friendly", verbosity=0.6, temperature=0.8)
        r1 = naturalize(query, topic, info, "factual", cfg)
        r2 = naturalize(query, topic, info, "factual", cfg)
        if r1 != r2:
            unique += 1

    check(f"Unique outputs at temp=0.8: {unique}/{total}", unique >= 3)
    return 100.0 * unique / total if total else 0


# ═════════════════════════════════════════════════════════════════════════════
# 5. PERFORMANCE
# ═════════════════════════════════════════════════════════════════════════════

def bench_performance():
    suite("5. Performance — generation speed")

    cfg = NLGConfig(style="neutral", temperature=0.0)

    # Warm up
    naturalize("test", "test", "test info.", "factual", cfg)

    times = []
    for name, query, topic, info, _ in TEST_CASES:
        start = time.time()
        naturalize(query, topic, info, "factual", cfg)
        elapsed = time.time() - start
        times.append(elapsed)

    avg = sum(times) / len(times)
    check(f"Avg response time: {avg*1000:.0f}ms", avg < 2.0, f"{avg*1000:.0f}ms avg")

    # Essay performance
    essay_times = []
    for name, _, topic, info, _ in TEST_CASES:
        start = time.time()
        generate_essay(topic, info, cfg)
        elapsed = time.time() - start
        essay_times.append(elapsed)

    essay_avg = sum(essay_times) / len(essay_times)
    check(f"Avg essay time: {essay_avg*1000:.0f}ms", essay_avg < 5.0, f"{essay_avg*1000:.0f}ms avg")

    return {"naturalize_ms": avg * 1000, "essay_ms": essay_avg * 1000}


# ═════════════════════════════════════════════════════════════════════════════
# 6. ARTIFACT DETECTION
# ═════════════════════════════════════════════════════════════════════════════

def bench_artifacts():
    suite("6. Artifact Detection — bad patterns in output?")

    bad_patterns = [
        "is she she", "and is she", "she can won", "the it", "it is she",
        "unlike unlike", "so so", "..", ",.", "the the", "a a",
        "they is", "they are are",
    ]

    found = 0
    total_checks = 0
    cfg = NLGConfig(style="friendly", verbosity=0.5, temperature=0.6)

    for name, query, topic, info, _ in TEST_CASES:
        r = naturalize(query, topic, info, "factual", cfg)
        r_lower = r.lower()
        for bp in bad_patterns:
            total_checks += 1
            if bp in r_lower:
                found += 1
                check(f"  {name}: artifact '{bp}' found", False, f"in: {r[:100]}...")

    check(f"Artifacts: {found}/{total_checks}", found == 0, f"{found} artifacts detected")
    return 100.0 - (100.0 * found / total_checks) if total_checks else 100


# ═════════════════════════════════════════════════════════════════════════════
# 7. PRONOUN ACCURACY
# ═════════════════════════════════════════════════════════════════════════════

def bench_pronouns():
    suite("7. Pronoun Accuracy — correct pronouns from source text?")

    from cos.nlg.models import build_entity

    tests = [
        ("Marie Curie", "Marie Curie was a physicist. She won the Nobel Prize.", "she"),
        ("Albert Einstein", "Einstein developed relativity. He was a genius.", "he"),
        ("Photosynthesis", "Photosynthesis converts sunlight. It produces oxygen.", "it"),
        ("french fries", "French fries are made from potatoes. They are fried.", "they"),
    ]

    correct = 0
    for name, source, expected in tests:
        e = build_entity(name, source)
        if e.pronoun == expected:
            correct += 1
        else:
            check(f"  {name}: expected '{expected}', got '{e.pronoun}'", False)

    check(f"Pronoun accuracy: {correct}/{len(tests)}", correct == len(tests))
    return 100.0 * correct / len(tests)


# ═════════════════════════════════════════════════════════════════════════════
# RUN ALL BENCHMARKS
# ═════════════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{'#'*70}")
    print(f"  COS NLG BENCHMARK SUITE")
    print(f"  {len(TEST_CASES)} test cases, {len(TEST_CASES[0][4])} fact types")
    print(f"{'#'*70}")

    results = {}
    results["factual"] = bench_factual_accuracy()
    results["determinism"] = bench_determinism()
    results["style_diff"] = bench_style_diff()
    results["uniqueness"] = bench_uniqueness()
    results["performance"] = bench_performance()
    results["artifacts"] = bench_artifacts()
    results["pronouns"] = bench_pronouns()

    print(f"\n{'='*60}")
    print(f"  BENCHMARK SUMMARY")
    print(f"{'='*60}")
    print(f"  Factual Accuracy (naturalize):  {results['factual']['factual_accuracy']:.1f}%")
    print(f"  Factual Accuracy (essay):        {results['factual']['essay_accuracy']:.1f}%")
    print(f"  Determinism:                      {results['determinism']:.0f}%")
    print(f"  Style Differentiation:            {results['style_diff']:.0f}%")
    print(f"  Output Uniqueness:                {results['uniqueness']:.0f}%")
    print(f"  Artifact-Free Rate:               {results['artifacts']:.1f}%")
    print(f"  Pronoun Accuracy:                 {results['pronouns']:.0f}%")
    print(f"  Avg naturalize time:              {results['performance']['naturalize_ms']:.0f}ms")
    print(f"  Avg essay time:                   {results['performance']['essay_ms']:.0f}ms")
    print(f"{'='*60}")
    print()

    # Overall score
    scores = [
        results['factual']['factual_accuracy'],
        results['determinism'],
        results['style_diff'],
        results['uniqueness'],
        results['artifacts'],
        results['pronouns'],
    ]
    overall = sum(scores) / len(scores)
    print(f"  OVERALL NLG SCORE: {overall:.1f}%")
    print(f"{'='*60}")

    return 0 if overall >= 70 else 1


if __name__ == '__main__':
    sys.exit(main())
