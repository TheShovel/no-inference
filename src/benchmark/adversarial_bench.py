#!/usr/bin/env python3
"""
Adversarial Benchmark — Uses the cloud LLM to act as a random user testing COS.

The LLM plays the role of a curious person trying to use the app for real tasks.
It asks questions, we feed them through COS, and the LLM evaluates the response.

This reveals real-world gaps that the predefined benchmark doesn't catch.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse

_SRC_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from cos.engine import process_query

OLLAMA_HOST = "http://localhost:11434"
CLOUD_MODEL = "gemma4:31b-cloud"

def _ollama(prompt, model=CLOUD_MODEL, timeout=60):
    """Call Ollama and return the response text."""
    url = f"{OLLAMA_HOST}/api/generate"
    data = json.dumps({
        "model": model, "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.8, "num_predict": 256}
    }).encode()
    try:
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode()).get("response", "").strip()
    except Exception as e:
        return f"[Error: {e}]"

def generate_question(category, used_topics):
    """Ask the LLM to generate a realistic user question in a category."""
    prompt = f"""You are a normal person using a helpful AI assistant. Generate ONE realistic question a real person might ask in the category "{category}".

Rules:
- Ask like a real human, not a benchmark
- Don't use topics that have been asked before: {used_topics}
- The question should be something someone would actually type
- Just output the question, nothing else"""

    response = _ollama(prompt)
    # Clean up common prefixes
    for prefix in ['Question:', 'question:', '"', "'"]:
        if response.startswith(prefix):
            response = response[len(prefix):].strip()
    return response.strip().strip('"').strip("'")

def evaluate_response(query, response):
    """Ask the LLM to rate how well COS answered."""
    if not response or len(response) < 10:
        return None, 0
    
    prompt = f"""Rate this response 1-10. Query: "{query}" Response: "{response[:400]}"

JSON only (no markdown): {{"score":<1-10>,"issue":""}}"""
    
    result = _ollama(prompt, timeout=30)
    # Strip any markdown code fences
    import re
    m = re.search(r'\{[^}]+\}', result)
    if m:
        result = m.group(0)
    try:
        data = json.loads(result)
        return data.get("issue", ""), data.get("score", 5)
    except:
        # Fallback: check for a number in the response
        import re as _re
        nums = _re.findall(r'\b([0-9]|10)\b', result[:50])
        if nums:
            return "evaluation issue", int(nums[0])
        return "evaluation issue", 5

def run_benchmark(questions_per_category=5):
    """Run the full adversarial benchmark."""
    categories = [
        "cooking and recipes",
        "home improvement and DIY",
        "health and wellness",
        "technology and computers",
        "science and nature",
        "history and geography",
        "practical life skills",
        "definitions and explanations",
        "math and numbers",
        "general knowledge",
    ]
    
    all_questions = []
    used_topics = set()
    
    print(f"\n{'='*70}")
    print(f"  COS ADVERSARIAL BENCHMARK")
    print(f"  LLM simulates {len(categories) * questions_per_category} real user queries")
    print(f"{'='*70}")
    
    for cat in categories:
        print(f"\n  --- {cat.upper()} ---")
        for i in range(questions_per_category):
            # Generate question
            q = generate_question(cat, used_topics)
            if not q or len(q) < 5:
                continue
            used_topics.add(q[:30])
            
            # Process through COS
            start = time.time()
            cos_response = process_query(q, use_cos=True)
            elapsed = time.time() - start
            
            # Evaluate
            issue, score = evaluate_response(q, cos_response)
            
            status = "GOOD" if score >= 7 else ("WEAK" if score >= 4 else "FAIL")
            print(f"  [{status}] ({score}/10) {q[:60]}")
            if issue:
                print(f"           issue: {issue[:80]}")
            if score < 5:
                print(f"           COS: {cos_response[:100]}")
            
            all_questions.append({
                "category": cat,
                "query": q,
                "response": cos_response,
                "score": score,
                "issue": issue,
                "time": round(elapsed, 2)
            })
            
            time.sleep(0.5)  # Rate limit
    
    # Results
    print(f"\n{'='*70}")
    print(f"  RESULTS")
    print(f"{'='*70}")
    
    scores = [q["score"] for q in all_questions if q["score"] > 0]
    avg = sum(scores) / len(scores) if scores else 0
    passed = sum(1 for s in scores if s >= 7)
    weak = sum(1 for s in scores if 4 <= s < 7)
    failed = sum(1 for s in scores if s < 4)
    
    print(f"\n  Overall Score: {avg:.1f}/10")
    print(f"  Passed: {passed}  Weak: {weak}  Failed: {failed}  Total: {len(scores)}")
    
    # Category breakdown
    print(f"\n  {'─'*60}")
    print(f"  Category Breakdown:")
    print(f"  {'─'*60}")
    for cat in categories:
        cat_scores = [q["score"] for q in all_questions if q["category"] == cat and q["score"] > 0]
        cat_avg = sum(cat_scores) / len(cat_scores) if cat_scores else 0
        bar = '█' * int(cat_avg) + '░' * (10 - int(cat_avg))
        print(f"    {cat:30s} {cat_avg:4.1f}  {bar}")
    
    # Top failures
    print(f"\n  {'─'*60}")
    print(f"  Worst Responses:")
    print(f"  {'─'*60}")
    failures = sorted([q for q in all_questions if q["score"] < 5], key=lambda x: x["score"])[:5]
    for q in failures:
        print(f"\n    Q: {q['query']}")
        print(f"    Score: {q['score']}/10  Issue: {q['issue'][:120]}")
        print(f"    COS: {q['response'][:150]}")
    
    # Save
    path = "data/adversarial_results.json"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump({
            "overall_score": round(avg, 2),
            "total": len(scores),
            "passed": passed,
            "weak": weak,
            "failed": failed,
            "results": all_questions,
        }, f, indent=2)
    print(f"\n  Results saved to {path}")
    return all_questions

if __name__ == '__main__':
    run_benchmark(questions_per_category=4)
