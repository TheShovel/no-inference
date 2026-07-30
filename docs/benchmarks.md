# Benchmarks

COS includes a benchmarking framework in `src/benchmark/` that evaluates response quality across multiple dimensions. There are five benchmark scripts plus an orchestrator that runs them all.

## Benchmark types

### NLG Quality Benchmark

`nlg_quality_bench.py` evaluates the NLG pipeline on factual queries where the correct answer is known. It tests:

- **Fact Preservation.** Does the response preserve the facts from the source information?
- **Coherence.** Is the response well-structured and readable?
- **Numerical Precision.** Are numbers and units preserved correctly?
- **Temperature Variety.** At higher temperature settings, does the system produce varied phrasings?

Each dimension is scored as a percentage (0-100%). The test uses predefined query/information pairs with ground truth expectations.

### Freeform Benchmark

`freeform_bench.py` runs COS against a set of open-ended questions and captures the responses for human or LLM evaluation. It tests across categories:

- General knowledge
- Science and technology
- History and culture
- Advice and recommendations
- Creative writing
- Math and logic
- Opinion and philosophy

Results are saved to `data/freeform_results.json`.

### Adversarial Benchmark

`adversarial_bench.py` tests the system against edge cases:

- Empty queries
- Gibberish input
- Extremely long queries
- Ambiguous pronouns
- False premises (pseudoscience, non-existent concepts)
- Swear words and offensive content
- Cross-lingual queries
- Repeated characters
- Injection attempts

Each test case is scored pass/fail based on whether the system handled it gracefully.

### LLM Judge Evaluation

`llm_eval.py` uses Ollama-hosted LLMs as judges to score COS responses on five dimensions:

- **Naturalness** (1-10). Sounds like natural human speech
- **Informativeness** (1-10). Contains meaningful facts and content
- **Coherence** (1-10). Logically structured and easy to follow
- **Correctness** (1-10). Factually accurate
- **Overall** (1-10). Combined quality

Judges evaluate pre-defined response pairs plus COS-generated responses. Scores are averaged across all test cases.

Requires Ollama running on `localhost:11434`.

### NLG Improvement Benchmark

`nlg_improve.py` is a diagnostic tool that runs the NLG pipeline on sample queries and shows per-pass output for debugging and improvement.

## Running benchmarks

```bash
# Run from the project root
cd src

# Run all benchmarks
python3 -m benchmark.orchestrator

# Run individual benchmarks
python3 -m benchmark.nlg_quality_bench --verbose
python3 -m benchmark.freeform_bench --questions 50
python3 -m benchmark.adversarial_bench
python3 -m benchmark.llm_eval                 # Requires Ollama
```

## Current results

### NLG Quality (deterministic, temperature=0.0)

| Metric                | Score |
|-----------------------|-------|
| Fact Preservation     | 99.1% |
| Coherence             | 90.0% |
| Numerical Precision   | 97.4% |
| Temperature Variety   | 70.0% |
| Overall               | 97.4% |

99.1% fact preservation means that in nearly all test cases, the NLG pipeline preserved the factual content of the source information without distortion. The 70% temperature variety score reflects that at higher temperature settings, the system produces different phrasings while maintaining factual accuracy.

### LLM Judge (gemma4:31b, 22 test cases)

| Metric            | Score (out of 10) |
|-------------------|-------------------|
| Naturalness       | 4.2               |
| Informativeness   | 6.1               |
| Coherence         | 6.1               |
| Correctness       | 9.3               |
| Overall           | 6.8               |

The 9.3 correctness score confirms that the system's responses are factually accurate. The lower naturalness score (4.2) reflects that the NLG pipeline, while functional, does not yet reach the fluency of human-written text or large language model output. This is an expected tradeoff of the symbolic approach.

> We prefer a robot that tells the truth awkwardly over one that lies fluently.

![no-inference rat](https://raw.githubusercontent.com/TheShovel/no-inference/gh-pages/logo.png)

  "at least i don't hallucinate"

## Shell runner

`run_bench.sh` runs the freeform benchmark and captures output:

```bash
sh run_bench.sh
```

Results are written to `/tmp/bench_output.txt`.
