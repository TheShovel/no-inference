#!/usr/bin/env python3
"""
COS Freeform Benchmark — LLM generates its own questions, we detect mistakes.

The LLM asks questions out of natural curiosity (no category restrictions).
We feed them through the full COS pipeline, have the LLM evaluate responses
with detailed mistake detection, then generate regression tests for bugs found.

Architecture:
  Phase 1: Free question generation (LLM asks whatever it wants)
  Phase 2: Response generation (full COS pipeline)
  Phase 3: Evaluation + structured mistake detection
  Phase 4: Pattern analysis + code module mapping
  Phase 5: Regression test generation

Usage:
    PYTHONPATH=src python -m src.benchmark.freeform_bench
    PYTHONPATH=src python -m src.benchmark.freeform_bench --questions 30
    PYTHONPATH=src python -m src.benchmark.freeform_bench --dry-run
    PYTHONPATH=src python -m src.benchmark.freeform_bench --no-tests
"""

import json
import os
import re
import sys
import time
import http.client
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Tuple

# ── Path setup ──────────────────────────────────────────────────────────────
_SRC_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# ── Config ──────────────────────────────────────────────────────────────────
OLLAMA_HOST = "http://localhost:11434"
JUDGE_MODEL = "gemma4:31b-cloud"

DIMENSIONS = ["naturalness", "informativeness", "coherence", "correctness", "conciseness"]

# Mistake types and the code modules they likely map to
MISTAKE_MODULE_MAP = {
    "grammar": "fluency.py, realize.py",
    "verb_agreement": "realize.py (is_plural_subject check), fluency.py",
    "pronoun_error": "fluency.py (apply_pronouns, _select_pronoun)",
    "capitalization": "fluency.py (fix_caps), essay.py",
    "awkward_phrasing": "realize.py (templates), combine.py",
    "template_artifact": "realize.py (_PATTERNS), essay.py (_TOPIC_SENTENCES)",
    "repetition": "fluency.py (filler dedup), essay.py (_deduplicate_facts)",
    "factual_error": "knowledge retrieval, parser.py",
    "missing_info": "parser.py (fact extraction), cleaner.py",
    "incomplete_sentence": "essay.py (_clean_fragments), parser.py",
    "word_choice": "realize.py (templates), fluency.py",
    "punctuation": "fluency.py (cleanup), realize.py",
    "flow_issue": "discourse.py, combine.py",
    # Multi-turn conversation mistakes
    "context_loss": "context_extraction.py, engine.py (_resolve_topic, _query_is_context_dependent)",
    "topic_drift": "engine.py (_handle_factual, _resolve_topic), knowledge.py",
    "inconsistent_response": "engine.py (process_query, conversation_history), memory.py",
}


# ═════════════════════════════════════════════════════════════════════════════
# Ollama API
# ═════════════════════════════════════════════════════════════════════════════

def _ollama(prompt: str, model: str = JUDGE_MODEL, timeout: int = 120,
            temperature: float = 0.7, num_predict: int = 512) -> Optional[str]:
    """Call Ollama and return the response text."""
    data = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "num_predict": num_predict,
        }
    }).encode("utf-8")

    try:
        conn = http.client.HTTPConnection("localhost", 11434, timeout=timeout)
        conn.request("POST", "/api/generate", body=data,
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()
        return json.loads(body).get("response", "").strip()
    except Exception as e:
        print(f"    [API Error] {model}: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _extract_json(raw: str) -> Optional[dict]:
    """Extract a JSON object from model response text."""
    if not raw:
        return None

    # Try direct parse
    try:
        result = json.loads(raw.strip())
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # Find JSON boundaries
    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        json_str = raw[brace_start:brace_end + 1]
        json_str = re.sub(r",\s*}", "}", json_str)
        json_str = re.sub(r",\s*]", "]", json_str)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    # Regex fallback for scores
    scores = {}
    for dim in DIMENSIONS:
        m = re.search(rf'"{dim}"\s*:\s*(\d+)', raw)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 10:
                scores[dim] = val

    if len(scores) >= 3:
        fb = re.search(r'"feedback"\s*:\s*"([^"]*)"', raw)
        scores["feedback"] = fb.group(1) if fb else ""
        return scores

    return None


# ═════════════════════════════════════════════════════════════════════════════
# Data Types
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class Mistake:
    """A specific mistake detected in a response."""
    mistake_type: str          # grammar, verb_agreement, etc.
    severity: str              # low, medium, high
    excerpt: str               # the problematic text
    description: str           # what's wrong
    suggested_fix: str         # how to fix it
    likely_module: str         # which code file to look at

@dataclass
class Judgment:
    """Full evaluation of a single response."""
    naturalness: int = 5
    informativeness: int = 5
    coherence: int = 5
    correctness: int = 5
    conciseness: int = 5
    mistakes: List[Mistake] = field(default_factory=list)
    raw_feedback: str = ""
    parse_error: bool = False

    @property
    def average(self) -> float:
        return (self.naturalness + self.informativeness + self.coherence +
                self.correctness + self.conciseness) / 5.0

    @property
    def high_severity_count(self) -> int:
        return sum(1 for m in self.mistakes if m.severity == "high")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["average"] = round(self.average, 2)
        d["high_severity_count"] = self.high_severity_count
        return d


@dataclass
class EvalCase:
    """A single query-response-evaluation case."""
    query: str
    response: str
    judgment: Optional[Judgment] = None
    time_taken: float = 0.0

    def to_dict(self) -> dict:
        d = {
            "query": self.query,
            "response": self.response[:8000],
            "time": round(self.time_taken, 2),
        }
        if self.judgment:
            d["scores"] = {
                "naturalness": self.judgment.naturalness,
                "informativeness": self.judgment.informativeness,
                "coherence": self.judgment.coherence,
                "correctness": self.judgment.correctness,
                "conciseness": self.judgment.conciseness,
                "average": round(self.judgment.average, 2),
            }
            d["mistakes"] = [asdict(m) for m in self.judgment.mistakes]
            d["raw_feedback"] = self.judgment.raw_feedback[:300]
        return d


@dataclass
class MultiTurnTurn:
    """A single turn within a multi-turn conversation."""
    query: str
    response: str
    judgment: Optional[Judgment] = None
    time_taken: float = 0.0

    def to_dict(self) -> dict:
        d = {
            "query": self.query,
            "response": self.response[:8000],
            "time": round(self.time_taken, 2),
        }
        if self.judgment:
            d["scores"] = {
                "naturalness": self.judgment.naturalness,
                "informativeness": self.judgment.informativeness,
                "coherence": self.judgment.coherence,
                "correctness": self.judgment.correctness,
                "conciseness": self.judgment.conciseness,
                "average": round(self.judgment.average, 2),
            }
            d["mistakes"] = [asdict(m) for m in self.judgment.mistakes]
            d["raw_feedback"] = self.judgment.raw_feedback[:300]
        return d


@dataclass
class MultiTurnCase:
    """A full multi-turn conversation scenario.

    The first turn establishes a topic; subsequent turns are follow-ups
    that may rely on conversation context (pronouns, "tell me more", etc.).
    """
    topic: str
    turns: List[MultiTurnTurn] = field(default_factory=list)

    @property
    def n_turns(self) -> int:
        return len(self.turns)

    @property
    def context_mistake_count(self) -> int:
        """Count mistakes that are specific to multi-turn context failures."""
        count = 0
        for turn in self.turns[1:]:  # skip the first turn (no context to use)
            if turn.judgment:
                for m in turn.judgment.mistakes:
                    if m.mistake_type in ("context_loss", "topic_drift",
                                          "inconsistent_response"):
                        count += 1
        return count

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "n_turns": self.n_turns,
            "context_mistake_count": self.context_mistake_count,
            "turns": [t.to_dict() for t in self.turns],
        }


# ═════════════════════════════════════════════════════════════════════════════
# Phase 1: Free Question Generation
# ═════════════════════════════════════════════════════════════════════════════

def generate_questions(n: int = 20, dry_run: bool = False) -> List[str]:
    """Ask the LLM to generate N questions about anything it's curious about.

    The LLM acts as a naturally curious person, not an adversarial tester.
    """
    if dry_run:
        return _dry_run_questions(n)

    print(f"\n  Phase 1: Generating {n} freeform questions...")

    # Generate in batches to avoid token limits
    batch_size = min(n, 10)
    all_questions = []
    used = set()

    batches = (n + batch_size - 1) // batch_size
    for batch_idx in range(batches):
        remaining = n - len(all_questions)
        count = min(batch_size, remaining)
        if count <= 0:
            break

        prompt = f"""You are a curious person exploring a knowledge assistant. Generate exactly {count} interesting questions you'd want to ask.

Rules:
- Ask about topics YOU find interesting (science, history, philosophy, everyday life, geography, art, technology, coding, anything)
- Vary the topics — don't cluster around one subject
- INCLUDE A MIX OF QUESTION TYPES:
  * Simple factual: "What causes...", "How does...", "Why is...", "Tell me about...", "Why do..."
  * Coding tasks: "How do I...", "How to implement...", "Write a function that..."
  * Complex multi-part prompts: "Write me an essay about X. Make sure it covers Y and Z.", "Create a HTML page about X with a Y style and Z layout.", "Make me a JavaScript function that does X, Y, and Z.", "Give me a detailed explanation of X including Y, Z, and W."
- Include AT LEAST 3 complex multi-part prompts (essays, HTML pages, detailed explanations with specific requirements)
- Ask like a real human, not a test
- Avoid questions already asked: {list(used) if used else "none yet"}
- Return ONLY the questions, one per line, no numbering or bullets"""

        response = _ollama(prompt, temperature=0.9, num_predict=800)
        if not response:
            continue

        for line in response.strip().split("\n"):
            q = line.strip()
            # Strip numbering, bullets, quotes
            q = re.sub(r"^[\d\.\)\-•\*]+\s*", "", q)
            q = q.strip("\"'`")
            q = q.strip()
            if len(q) > 10 and q not in used:
                all_questions.append(q)
                used.add(q)
                if len(all_questions) >= n:
                    break

        time.sleep(0.3)

    print(f"    Generated {len(all_questions)} questions")
    return all_questions[:n]


def _dry_run_questions(n: int) -> List[str]:
    """Return mock questions for testing without Ollama."""
    mocks = [
        "What causes aurora borealis?",
        "How do蜜蜂 communicate with each other?",
        "Why is the sky blue?",
        "What is the difference between TCP and UDP?",
        "How doesPhotosynthesis work?",
        "Tell me about the history of the printing press",
        "What are the health benefits of green tea?",
        "How do black holes form?",
        "What is the meaning of the word 'serendipity'?",
        "How doesGPS navigation work?",
        "What is the tallest mountain on Mars?",
        "How do airplanes fly?",
        "What is quantum entanglement?",
        "Why do we dream?",
        "How is chocolate made?",
        "What is the Great Wall of China made of?",
        "How do vaccines work?",
        "What causes tides in the ocean?",
        "What is the difference between AI and machine learning?",
        "How does the human immune system work?",
        "What is the deepest point in the ocean?",
        "How do magnets work?",
        "What is the golden ratio?",
        "How do volcanoes erupt?",
        "What is the speed of light?",
    ]
    return mocks[:n]


# ═════════════════════════════════════════════════════════════════════════════
# Phase 1b: Multi-Turn Conversation Scenario Generation
# ═════════════════════════════════════════════════════════════════════════════

# Follow-up templates that reference the previous topic via pronouns,
# "tell me more", or other context-dependent phrasing.
_FOLLOWUP_TEMPLATES = [
    "What are some fun facts about it?",
    "Tell me more about that.",
    "Can you elaborate on what you just said?",
    "What else should I know about it?",
    "How does that work?",
    "Why is that the case?",
    "What are the implications of that?",
    "Can you give me an example?",
    "What's the history behind it?",
    "How does it compare to other things like it?",
]


def generate_multi_turn_scenarios(n: int = 10, dry_run: bool = False) -> List[Tuple[str, List[str]]]:
    """Generate N multi-turn conversation scenarios.

    Each scenario is a (topic, [turn1, turn2, ...]) tuple where turn1
    establishes a topic and subsequent turns are context-dependent follow-ups.

    Returns a list of (topic, queries) tuples.
    """
    if dry_run:
        return _dry_run_multi_turn_scenarios(n)

    print(f"\n  Phase 1b: Generating {n} multi-turn scenarios...")

    all_scenarios = []
    used_topics = set()

    while len(all_scenarios) < n:
        # Use the LLM to generate a topic + follow-up pair
        prompt = f"""You are a curious person exploring a knowledge assistant. Generate a short multi-turn conversation scenario.

First, pick an interesting topic (a country, scientific concept, historical event, etc.).
Then, write 2-3 follow-up questions that a curious person would ask AFTER learning about that topic.
The follow-ups should reference the previous topic using pronouns ("it", "that"), 
"tell me more", or other natural context-dependent phrasing.

Format (one scenario per response, do not number):
TOPIC: <topic>
TURN 1: <initial question about the topic>
TURN 2: <follow-up that references the topic>
TURN 3: <optional second follow-up>

Avoid topics already used: {list(used_topics) if used_topics else "none yet"}"""

        response = _ollama(prompt, temperature=0.8, num_predict=1000)
        if not response:
            continue

        # Parse the response
        current_topic = None
        current_turns = []
        for line in response.strip().split("\n"):
            line = line.strip()
            if line.startswith("TOPIC:"):
                if current_topic and current_turns:
                    all_scenarios.append((current_topic, current_turns))
                    used_topics.add(current_topic)
                    if len(all_scenarios) >= n:
                        break
                current_topic = line.replace("TOPIC:", "").strip()
                current_turns = []
            elif line.startswith("TURN"):
                q = line.split(":", 1)[-1].strip()
                if q:
                    current_turns.append(q)

        # Don't forget the last one
        if current_topic and current_turns and len(all_scenarios) < n:
            if current_topic not in used_topics:
                all_scenarios.append((current_topic, current_turns))
                used_topics.add(current_topic)

        time.sleep(0.3)

    print(f"    Generated {len(all_scenarios)} multi-turn scenarios")
    return all_scenarios[:n]


def _dry_run_multi_turn_scenarios(n: int) -> List[Tuple[str, List[str]]]:
    """Return mock multi-turn scenarios for testing without Ollama.

    These scenarios mirror the kinds of context-dependent conversations
    that the benchmark is designed to catch.
    """
    mocks = [
        ("France", [
            "Tell me about France.",
            "What are some fun facts about it?",
            "Tell me more about that.",
        ]),
        ("Aurora Borealis", [
            "What causes the aurora borealis?",
            "How does that work?",
            "What colors can you see?",
        ]),
        ("Photosynthesis", [
            "How does photosynthesis work?",
            "Why is that important for life on Earth?",
            "Can you give me an example of where it happens?",
        ]),
        ("Roman Empire", [
            "How did the Roman Empire actually collapse?",
            "What were the main factors?",
            "How does that compare to other fallen empires?",
        ]),
        ("Quantum Entanglement", [
            "What is quantum entanglement?",
            "How does it differ from regular physics?",
            "What are the implications of that?",
        ]),
        ("Black Holes", [
            "How do black holes form?",
            "What happens to time near them?",
            "What else should I know about it?",
        ]),
        ("Vaccines", [
            "How do vaccines work?",
            "What are the different types?",
            "Can you elaborate on what you just said?",
        ]),
        ("Dreams", [
            "Why do we dream?",
            "What do those dreams actually mean?",
            "How does that relate to memory?",
        ]),
        ("Climate Change", [
            "What is climate change?",
            "What are the main causes?",
            "What can be done about it?",
        ]),
        ("The Great Wall of China", [
            "What is the Great Wall of China made of?",
            "How long is it?",
            "Why was it built?",
        ]),
        ("Bees", [
            "What would happen to the Earth's ecosystem if all the bees suddenly disappeared?",
            "How does that affect the food we eat?",
            "What can be done to help?",
        ]),
        ("The Voynich Manuscript", [
            "Tell me about the most mysterious unsolved codes or manuscripts in history.",
            "What are the main theories about it?",
            "How does that compare to other mysterious texts?",
        ]),
        ("Migratory Birds", [
            "How do migratory birds navigate thousands of miles without getting lost?",
            "What mechanisms do they use?",
            "How does that compare to human navigation?",
        ]),
        ("The Mandela Effect", [
            "Why do some people experience the mandela effect?",
            "What causes it?",
            "How does that relate to memory?",
        ]),
        ("Blue Color in Nature", [
            "Why is the color blue so rare in nature?",
            "What causes it?",
            "How does that work?",
        ]),
    ]
    return mocks[:n]


# ═════════════════════════════════════════════════════════════════════════════
# Phase 2: Response Generation
# ═════════════════════════════════════════════════════════════════════════════

def generate_responses(questions: List[str]) -> List[EvalCase]:
    """Feed each question through the full COS pipeline."""
    from cos.engine import process_query, reset_conversation

    # Pre-load knowledge base to avoid race conditions during processing
    try:
        from cos.knowledge import get_all_knowledge
        get_all_knowledge()  # Warms the KB cache
    except Exception:
        pass

    # Pre-load coding knowledge
    try:
        from cos.code_knowledge import _load_coding_knowledge
        _load_coding_knowledge()
    except Exception:
        pass

    print(f"\n  Phase 2: Generating {len(questions)} responses...")
    reset_conversation()

    cases = []
    for i, q in enumerate(questions):
        start = time.time()
        try:
            # Reset conversation before each question to prevent cross-query
            # contamination (conversation_history accumulating across questions)
            reset_conversation()
            response = process_query(q, use_cos=True)
        except Exception as e:
            response = f"[Error: {e}]"
        elapsed = time.time() - start

        cases.append(EvalCase(query=q, response=response or "[No response]", time_taken=elapsed))

        status = "OK" if response and len(response) > 20 else "SHORT"
        print(f"    [{i+1}/{len(questions)}] ({elapsed:.1f}s) [{status}] {q[:50]}...")

    return cases


# ═════════════════════════════════════════════════════════════════════════════
# Phase 2b: Multi-Turn Response Generation
# ═════════════════════════════════════════════════════════════════════════════

def generate_multi_turn_responses(scenarios: List[Tuple[str, List[str]]]) -> List[MultiTurnCase]:
    """Process multi-turn scenarios through the pipeline.

    Unlike single-turn responses, conversation state is NOT reset between
    turns within a scenario. This allows the engine to use conversation
    history for context-dependent follow-up queries.
    """
    from cos.engine import process_query, reset_conversation

    print(f"\n  Phase 2b: Generating {len(scenarios)} multi-turn conversations...")

    cases = []
    for i, (topic, queries) in enumerate(scenarios):
        # Reset conversation at the start of each scenario
        reset_conversation()

        turns = []
        for j, q in enumerate(queries):
            start = time.time()
            try:
                response = process_query(q, use_cos=True)
            except Exception as e:
                response = f"[Error: {e}]"
            elapsed = time.time() - start

            turns.append(MultiTurnTurn(
                query=q,
                response=response or "[No response]",
                time_taken=elapsed,
            ))

            status = "OK" if response and len(response) > 20 else "SHORT"
            print(f"    [{i+1}/{len(scenarios)}] turn {j+1} ({elapsed:.1f}s) [{status}] {q[:40]}...")

        cases.append(MultiTurnCase(topic=topic, turns=turns))

    return cases


# ═════════════════════════════════════════════════════════════════════════════
# Phase 3: Evaluation + Mistake Detection
# ═════════════════════════════════════════════════════════════════════════════

_EVAL_PROMPT = """You are an expert language quality evaluator. Analyze this AI assistant response carefully.

User asked: "{query}"
Assistant responded: "{response}"

Your job: Find SPECIFIC mistakes. Look for grammar errors, verb agreement issues, wrong pronouns, capitalization errors, awkward phrasing, template-like patterns, incomplete sentences, factual inaccuracies, or missing information.

Return ONLY valid JSON (no markdown, no code fences):
{{
  "naturalness": <1-10>,
  "informativeness": <1-10>,
  "coherence": <1-10>,
  "correctness": <1-10>,
  "conciseness": <1-10>,
  "feedback": "brief overall summary",
  "mistakes": [
    {{
      "type": "grammar|verb_agreement|pronoun_error|capitalization|awkward_phrasing|template_artifact|repetition|factual_error|missing_info|incomplete_sentence|word_choice|punctuation|flow_issue",
      "severity": "low|medium|high",
      "excerpt": "the exact problematic text from the response (keep it short, under 80 chars)",
      "description": "what's wrong",
      "fix": "how to fix it"
    }}
  ]
}}

If there are no mistakes, return an empty "mistakes" array.
Be specific — quote the exact text that has the issue."""


def evaluate_response(case: EvalCase, dry_run: bool = False) -> Judgment:
    """Evaluate a single response with detailed mistake detection."""
    if dry_run:
        _dry_run_judgment._current_response = case.response
        return _dry_run_judgment()

    if not case.response or len(case.response) < 10:
        return Judgment(parse_error=True, raw_feedback="[Response too short to evaluate]")

    prompt = _EVAL_PROMPT.format(
        query=case.query[:300],
        response=case.response[:8000],
    )

    raw = _ollama(prompt, temperature=0.2, num_predict=1500)
    if not raw:
        return Judgment(parse_error=True, raw_feedback="[No response from judge]")

    parsed = _extract_json(raw)
    if not parsed:
        return Judgment(parse_error=True, raw_feedback=f"[Parse error] {raw[:200]}")

    # Extract mistakes
    mistakes = []
    raw_mistakes = parsed.get("mistakes", [])
    if isinstance(raw_mistakes, list):
        for m in raw_mistakes:
            if isinstance(m, dict) and m.get("type") and m.get("excerpt"):
                mistake_type = m["type"].strip().lower()
                severity = m.get("severity", "medium").strip().lower()
                if severity not in ("low", "medium", "high"):
                    severity = "medium"
                likely_module = MISTAKE_MODULE_MAP.get(mistake_type, "unknown")
                mistakes.append(Mistake(
                    mistake_type=mistake_type,
                    severity=severity,
                    excerpt=m.get("excerpt", "")[:80],
                    description=m.get("description", ""),
                    suggested_fix=m.get("fix", ""),
                    likely_module=likely_module,
                ))

    return Judgment(
        naturalness=_clamp_score(parsed.get("naturalness", 5)),
        informativeness=_clamp_score(parsed.get("informativeness", 5)),
        coherence=_clamp_score(parsed.get("coherence", 5)),
        correctness=_clamp_score(parsed.get("correctness", 5)),
        conciseness=_clamp_score(parsed.get("conciseness", 5)),
        mistakes=mistakes,
        raw_feedback=parsed.get("feedback", ""),
    )


def _clamp_score(val) -> int:
    try:
        v = int(val)
        return max(1, min(10, v))
    except (TypeError, ValueError):
        return 5


def _dry_run_judgment() -> Judgment:
    """Mock judgment for testing.

    Instead of purely random scores, this evaluates the response text
    for common quality signals to produce a more realistic grade.
    """
    import random

    # Use the response text from the calling context (set by evaluate_response)
    response = getattr(_dry_run_judgment, "_current_response", "")

    # ── Quality heuristics ─────────────────────────────────────────────
    # Start from a reasonable baseline and adjust based on response quality
    naturalness = 9
    informativeness = 8
    coherence = 9
    correctness = 9
    conciseness = 8
    mistakes = []

    if not response or len(response) < 20:
        # Very short or empty response — poor quality
        naturalness = 3
        informativeness = 2
        coherence = 3
        correctness = 3
        conciseness = 5
        mistakes.append(Mistake(
            mistake_type="incomplete_sentence",
            severity="high",
            excerpt=response[:40] if response else "",
            description="Response is too short or empty",
            suggested_fix="Provide a more complete answer",
            likely_module="fallback.py",
        ))
    elif "[Error:" in response:
        naturalness = 2
        informativeness = 1
        coherence = 2
        correctness = 2
        conciseness = 3
        mistakes.append(Mistake(
            mistake_type="missing_info",
            severity="high",
            excerpt=response[:40],
            description="Response contains an error instead of an answer",
            suggested_fix="Fix the underlying processing error",
            likely_module="engine.py",
        ))
    elif any(phrase in response for phrase in [
        "I don't have enough information",
        "I'm still learning about that",
        "That's outside what I currently know",
        "I'm not confident I can give you an accurate answer",
    ]):
        naturalness = 4
        informativeness = 3
        coherence = 5
        correctness = 4
        conciseness = 5
        mistakes.append(Mistake(
            mistake_type="missing_info",
            severity="high",
            excerpt=response[:40],
            description="Response falls back to a generic non-answer",
            suggested_fix="Provide actual information instead of a fallback",
            likely_module="fallback.py",
        ))
    else:
        # Response has actual content — score based on quality signals
        # Informativeness: longer, more detailed responses score higher
        word_count = len(response.split())
        if word_count > 100:
            informativeness = 10
        elif word_count > 50:
            informativeness = 9
        elif word_count > 20:
            informativeness = 8
        else:
            informativeness = 6

        # Naturalness: check for common issues
        if "it's the primary means" in response or "human language is characterized" in response:
            naturalness = 4
            mistakes.append(Mistake(
                mistake_type="awkward_phrasing",
                severity="medium",
                excerpt="awkward phrasing detected",
                description="Response contains awkward or unnatural phrasing",
                suggested_fix="Rewrite for better flow",
                likely_module="realize.py",
            ))
        elif "The entire response" in response or "Entire response" in response:
            naturalness = 3
            correctness = 3
            mistakes.append(Mistake(
                mistake_type="template_artifact",
                severity="high",
                excerpt="The entire response",
                description="Response contains template artifacts",
                suggested_fix="Remove template artifacts",
                likely_module="realize.py",
            ))
        else:
            naturalness = 7
            # Small chance of a minor issue
            if random.random() < 0.2:
                naturalness = 6
                mistakes.append(Mistake(
                    mistake_type="word_choice",
                    severity="low",
                    excerpt=response[:40],
                    description="Minor word choice issue",
                    suggested_fix="Use more natural wording",
                    likely_module="fluency.py",
                ))

        # Correctness: check for known bad patterns
        if "Bees are winged insects" in response and "disappeared" in response:
            correctness = 3
            mistakes.append(Mistake(
                mistake_type="missing_info",
                severity="high",
                excerpt="Bees are winged insects",
                description="Defines bees instead of answering the ecosystem question",
                suggested_fix="Address the actual question about ecosystem impact",
                likely_module="knowledge.py",
            ))
        elif "In essence, a dream is" in response:
            correctness = 4
            mistakes.append(Mistake(
                mistake_type="missing_info",
                severity="high",
                excerpt="In essence, a dream is",
                description="Defines dreams instead of explaining why we dream",
                suggested_fix="Address the actual question about dream purpose",
                likely_module="knowledge.py",
            ))

        # Coherence: check for repetition
        words = response.split()
        if len(words) >= 5 and len(set(words)) <= 2:
            coherence = 2
            mistakes.append(Mistake(
                mistake_type="repetition",
                severity="high",
                excerpt=response[:40],
                description="Excessive repetition in response",
                suggested_fix="Remove redundant content",
                likely_module="fluency.py",
            ))
        else:
            coherence = 7

        # Conciseness: check for overly verbose responses
        if word_count > 500:
            conciseness = 4
        elif word_count > 300:
            conciseness = 5
        elif word_count > 50:
            conciseness = 8
        else:
            conciseness = 9

    # Add small random variation (0 to +1) for realism — keep scores stable
    naturalness = max(1, min(10, naturalness + random.randint(0, 1)))
    informativeness = max(1, min(10, informativeness + random.randint(0, 1)))
    coherence = max(1, min(10, coherence + random.randint(0, 1)))
    correctness = max(1, min(10, correctness + random.randint(0, 1)))
    conciseness = max(1, min(10, conciseness + random.randint(0, 1)))

    return Judgment(
        naturalness=naturalness,
        informativeness=informativeness,
        coherence=coherence,
        correctness=correctness,
        conciseness=conciseness,
        mistakes=mistakes,
        raw_feedback="Generally good response but has some minor issues." if not mistakes else "Response has some issues that need attention.",
    )


def run_evaluation(cases: List[EvalCase], dry_run: bool = False) -> List[EvalCase]:
    """Evaluate all responses."""
    print(f"\n  Phase 3: Evaluating {len(cases)} responses...")
    for i, case in enumerate(cases):
        case.judgment = evaluate_response(case, dry_run=dry_run)
        avg = case.judgment.average
        n_mistakes = len(case.judgment.mistakes)
        high = case.judgment.high_severity_count
        print(f"    [{i+1}/{len(cases)}] avg={avg:.1f} mistakes={n_mistakes} high={high} | {case.query[:45]}...")
        time.sleep(0.5)
    return cases


# ═════════════════════════════════════════════════════════════════════════════
# Phase 3b: Multi-Turn Evaluation
# ═════════════════════════════════════════════════════════════════════════════

_MULTI_TURN_EVAL_PROMPT = """You are an expert conversation quality evaluator. Analyze this multi-turn conversation carefully.

Conversation history:
{context}

Current turn:
User asked: "{query}"
Assistant responded: "{response}"

Your job: Evaluate the LAST response. Does it correctly use the conversation context?
Does it stay on topic? Does it address the user's follow-up question?

Look for: context_loss (follow-up doesn't use conversation context),
topic_drift (response drifts away from the conversation topic),
inconsistent_response (response contradicts previous turns),
plus the same mistake types as single-turn evaluation.

Return ONLY valid JSON (no markdown, no code fences):
{{
  "naturalness": <1-10>,
  "informativeness": <1-10>,
  "coherence": <1-10>,
  "correctness": <1-10>,
  "conciseness": <1-10>,
  "feedback": "brief overall summary",
  "mistakes": [
    {{
      "type": "grammar|verb_agreement|pronoun_error|capitalization|awkward_phrasing|template_artifact|repetition|factual_error|missing_info|incomplete_sentence|word_choice|punctuation|flow_issue|context_loss|topic_drift|inconsistent_response",
      "severity": "low|medium|high",
      "excerpt": "the exact problematic text from the response (keep it short, under 80 chars)",
      "description": "what's wrong",
      "fix": "how to fix it"
    }}
  ]
}}

If there are no mistakes, return an empty "mistakes" array.
Be specific — quote the exact text that has the issue."""


def _build_conversation_context(turns: List[MultiTurnTurn], current_idx: int) -> str:
    """Build a text representation of the conversation history up to current_idx."""
    lines = []
    for i in range(current_idx):
        turn = turns[i]
        lines.append(f"  Turn {i+1}: User asked: \"{turn.query}\"")
        lines.append(f"  Assistant responded: \"{turn.response[:300]}\"")
    return "\n".join(lines)


def evaluate_multi_turn_turn(case: MultiTurnCase, turn_idx: int,
                             dry_run: bool = False) -> Judgment:
    """Evaluate a single turn in a multi-turn conversation.

    For the first turn (turn_idx=0), this delegates to the standard
    single-turn evaluation. For follow-up turns, it uses the
    conversation-context-aware evaluation prompt.
    """
    turn = case.turns[turn_idx]

    if dry_run:
        _dry_run_judgment._current_response = turn.response
        return _dry_run_judgment()

    if not turn.response or len(turn.response) < 10:
        return Judgment(parse_error=True,
                        raw_feedback="[Response too short to evaluate]")

    if turn_idx == 0:
        # First turn: use standard single-turn evaluation
        single_case = EvalCase(query=turn.query, response=turn.response,
                               time_taken=turn.time_taken)
        return evaluate_response(single_case, dry_run=False)

    # Follow-up turn: use conversation-context-aware evaluation
    context = _build_conversation_context(case.turns, turn_idx)
    prompt = _MULTI_TURN_EVAL_PROMPT.format(
        context=context,
        query=turn.query[:200],
        response=turn.response[:600],
    )

    raw = _ollama(prompt, temperature=0.2, num_predict=800)
    if not raw:
        return Judgment(parse_error=True, raw_feedback="[No response from judge]")

    parsed = _extract_json(raw)
    if not parsed:
        return Judgment(parse_error=True,
                        raw_feedback=f"[Parse error] {raw[:200]}")

    # Extract mistakes (same logic as evaluate_response)
    mistakes = []
    raw_mistakes = parsed.get("mistakes", [])
    if isinstance(raw_mistakes, list):
        for m in raw_mistakes:
            if isinstance(m, dict) and m.get("type") and m.get("excerpt"):
                mistake_type = m["type"].strip().lower()
                severity = m.get("severity", "medium").strip().lower()
                if severity not in ("low", "medium", "high"):
                    severity = "medium"
                likely_module = MISTAKE_MODULE_MAP.get(mistake_type, "unknown")
                mistakes.append(Mistake(
                    mistake_type=mistake_type,
                    severity=severity,
                    excerpt=m.get("excerpt", "")[:80],
                    description=m.get("description", ""),
                    suggested_fix=m.get("fix", ""),
                    likely_module=likely_module,
                ))

    return Judgment(
        naturalness=_clamp_score(parsed.get("naturalness", 5)),
        informativeness=_clamp_score(parsed.get("informativeness", 5)),
        coherence=_clamp_score(parsed.get("coherence", 5)),
        correctness=_clamp_score(parsed.get("correctness", 5)),
        conciseness=_clamp_score(parsed.get("conciseness", 5)),
        mistakes=mistakes,
        raw_feedback=parsed.get("feedback", ""),
    )


def run_multi_turn_evaluation(cases: List[MultiTurnCase],
                              dry_run: bool = False) -> List[MultiTurnCase]:
    """Evaluate all turns in all multi-turn conversations."""
    print(f"\n  Phase 3b: Evaluating {len(cases)} multi-turn conversations...")
    for i, case in enumerate(cases):
        for j, turn in enumerate(case.turns):
            turn.judgment = evaluate_multi_turn_turn(case, j, dry_run=dry_run)
            avg = turn.judgment.average
            n_mistakes = len(turn.judgment.mistakes)
            high = turn.judgment.high_severity_count
            label = "follow-up" if j > 0 else "topic-establishing"
            print(f"    [{i+1}/{len(cases)}] turn {j+1} ({label}) avg={avg:.1f} "
                  f"mistakes={n_mistakes} high={high} | {turn.query[:40]}...")
            time.sleep(0.5)
    return cases


# ═════════════════════════════════════════════════════════════════════════════
# Phase 4: Analysis
# ═════════════════════════════════════════════════════════════════════════════

def analyze_results(cases: List[EvalCase]) -> Dict:
    """Aggregate mistakes by type, severity, and likely code module."""
    from collections import Counter

    all_mistakes = []
    for c in cases:
        if c.judgment:
            all_mistakes.extend(c.judgment.mistakes)

    # Count by type
    type_counts = Counter(m.mistake_type for m in all_mistakes)
    severity_counts = Counter(m.severity for m in all_mistakes)

    # Count by module
    module_counts = Counter()
    module_examples = {}
    for m in all_mistakes:
        mod = m.likely_module
        module_counts[mod] += 1
        if mod not in module_examples:
            module_examples[mod] = []
        if len(module_examples[mod]) < 3:
            module_examples[mod].append({
                "type": m.mistake_type,
                "excerpt": m.excerpt,
                "fix": m.suggested_fix,
            })

    # Per-type examples
    type_examples = {}
    for m in all_mistakes:
        if m.mistake_type not in type_examples:
            type_examples[m.mistake_type] = []
        if len(type_examples[m.mistake_type]) < 3:
            type_examples[m.mistake_type].append({
                "excerpt": m.excerpt,
                "description": m.description,
                "fix": m.suggested_fix,
                "severity": m.severity,
            })

    # Score distribution
    avgs = [c.judgment.average for c in cases if c.judgment]
    overall_avg = sum(avgs) / len(avgs) if avgs else 0

    # Worst cases
    worst = sorted(
        [c for c in cases if c.judgment],
        key=lambda c: c.judgment.average
    )[:5]

    # Dimension averages
    dim_avgs = {}
    for dim in DIMENSIONS:
        scores = [getattr(c.judgment, dim) for c in cases if c.judgment]
        dim_avgs[dim] = sum(scores) / len(scores) if scores else 0

    return {
        "overall_average": round(overall_avg, 2),
        "dimension_averages": {k: round(v, 2) for k, v in dim_avgs.items()},
        "total_cases": len(cases),
        "total_mistakes": len(all_mistakes),
        "severity_counts": dict(severity_counts),
        "type_counts": dict(type_counts.most_common()),
        "type_examples": type_examples,
        "module_counts": dict(module_counts.most_common()),
        "module_examples": module_examples,
        "worst_cases": [
            {
                "query": c.query,
                "score": round(c.judgment.average, 2),
                "mistakes": len(c.judgment.mistakes),
                "high_severity": c.judgment.high_severity_count,
                "feedback": c.judgment.raw_feedback[:200],
            }
            for c in worst
        ],
    }


def print_analysis(analysis: Dict):
    """Print human-readable analysis."""
    print(f"\n{'='*65}")
    print(f"  ANALYSIS RESULTS")
    print(f"{'='*65}")

    print(f"\n  Overall Score: {analysis['overall_average']}/10")
    print(f"  Total Mistakes: {analysis['total_mistakes']}")
    print(f"  Severity: {analysis['severity_counts']}")

    # Dimensions
    print(f"\n  {'─'*55}")
    print(f"  Dimension Averages:")
    for dim, score in analysis["dimension_averages"].items():
        bar = "\u2588" * int(score) + "\u2591" * (10 - int(score))
        print(f"    {dim:20s}  {score:5.2f}  {bar}")

    # Mistake types
    if analysis["type_counts"]:
        print(f"\n  {'─'*55}")
        print(f"  Mistake Types:")
        for mtype, count in sorted(analysis["type_counts"].items(), key=lambda x: -x[1]):
            bar = "\u2588" * min(count, 15) + "\u2591" * max(0, 15 - count)
            print(f"    {mtype:22s}  {count:2d}x  {bar}")

    # Code modules to fix
    if analysis["module_counts"]:
        print(f"\n  {'─'*55}")
        print(f"  Modules to Fix (by mistake count):")
        for mod, count in sorted(analysis["module_counts"].items(), key=lambda x: -x[1]):
            print(f"    {count:2d}x  {mod}")
            for ex in analysis["module_examples"].get(mod, [])[:2]:
                print(f"         [{ex['type']}] \"{ex['excerpt'][:60]}\"")
                print(f"         Fix: {ex['fix'][:70]}")

    # Worst cases
    if analysis["worst_cases"]:
        print(f"\n  {'─'*55}")
        print(f"  Worst Responses:")
        for w in analysis["worst_cases"]:
            print(f"\n    Q: {w['query'][:60]}")
            print(f"    Score: {w['score']}/10  Mistakes: {w['mistakes']} ({w['high_severity']} high)")
            if w["feedback"]:
                print(f"    Feedback: {w['feedback'][:100]}")


# ═════════════════════════════════════════════════════════════════════════════
# Phase 4b: Multi-Turn Analysis
# ═════════════════════════════════════════════════════════════════════════════

def analyze_multi_turn_results(cases: List[MultiTurnCase]) -> Dict:
    """Aggregate multi-turn conversation results.

    Focuses on context-aware metrics: how often follow-ups lose context,
    drift off-topic, or contradict prior turns.
    """
    from collections import Counter

    all_mistakes = []
    followup_mistakes = []
    context_mistakes = []

    for c in cases:
        for j, turn in enumerate(c.turns):
            if turn.judgment:
                all_mistakes.extend(turn.judgment.mistakes)
                if j > 0:  # follow-up turns only
                    followup_mistakes.extend(turn.judgment.mistakes)
                    for m in turn.judgment.mistakes:
                        if m.mistake_type in ("context_loss", "topic_drift",
                                              "inconsistent_response"):
                            context_mistakes.append(m)

    # Count by type
    type_counts = Counter(m.mistake_type for m in all_mistakes)
    severity_counts = Counter(m.severity for m in all_mistakes)

    # Context-specific counts
    context_type_counts = Counter(m.mistake_type for m in context_mistakes)

    # Count by module
    module_counts = Counter()
    module_examples = {}
    for m in context_mistakes:
        mod = m.likely_module
        module_counts[mod] += 1
        if mod not in module_examples:
            module_examples[mod] = []
        if len(module_examples[mod]) < 3:
            module_examples[mod].append({
                "type": m.mistake_type,
                "excerpt": m.excerpt,
                "fix": m.suggested_fix,
            })

    # Per-type examples (context mistakes only)
    type_examples = {}
    for m in context_mistakes:
        if m.mistake_type not in type_examples:
            type_examples[m.mistake_type] = []
        if len(type_examples[m.mistake_type]) < 3:
            type_examples[m.mistake_type].append({
                "excerpt": m.excerpt,
                "description": m.description,
                "fix": m.suggested_fix,
                "severity": m.severity,
            })

    # Score distribution (follow-up turns only)
    followup_avgs = [t.judgment.average for c in cases
                     for t in c.turns[1:] if t.judgment]
    overall_avg = sum(followup_avgs) / len(followup_avgs) if followup_avgs else 0

    # Worst follow-up cases
    followup_turns = [(c, t, j) for c in cases for j, t in enumerate(c.turns[1:], 1)
                      if t.judgment]
    worst = sorted(followup_turns, key=lambda x: x[1].judgment.average)[:5]

    # Dimension averages (follow-up turns)
    dim_avgs = {}
    for dim in DIMENSIONS:
        scores = [t.judgment.__dict__.get(dim, 5) for c in cases
                  for t in c.turns[1:] if t.judgment]
        dim_avgs[dim] = sum(scores) / len(scores) if scores else 0

    # Context failure rate
    total_followups = len(followup_turns)
    context_failure_rate = (len(context_mistakes) / total_followups * 100
                            if total_followups else 0)

    return {
        "overall_average": round(overall_avg, 2),
        "dimension_averages": {k: round(v, 2) for k, v in dim_avgs.items()},
        "total_cases": len(cases),
        "total_turns": sum(c.n_turns for c in cases),
        "total_followups": total_followups,
        "total_mistakes": len(all_mistakes),
        "followup_mistakes": len(followup_mistakes),
        "context_mistakes": len(context_mistakes),
        "context_failure_rate": round(context_failure_rate, 1),
        "severity_counts": dict(severity_counts),
        "type_counts": dict(type_counts.most_common()),
        "context_type_counts": dict(context_type_counts.most_common()),
        "type_examples": type_examples,
        "module_counts": dict(module_counts.most_common()),
        "module_examples": module_examples,
        "worst_cases": [
            {
                "topic": c.topic,
                "turn": j,
                "query": t.query,
                "score": round(t.judgment.average, 2),
                "mistakes": len(t.judgment.mistakes),
                "high_severity": t.judgment.high_severity_count,
                "feedback": t.judgment.raw_feedback[:200],
            }
            for c, t, j in worst
        ],
    }


def print_analysis_multi_turn(analysis: Dict):
    """Print human-readable multi-turn analysis."""
    print(f"\n{'='*65}")
    print(f"  MULTI-TURN ANALYSIS RESULTS")
    print(f"{'='*65}")

    print(f"\n  Follow-up Score: {analysis['overall_average']}/10")
    print(f"  Total Conversations: {analysis['total_cases']}")
    print(f"  Total Turns: {analysis['total_turns']}")
    print(f"  Follow-up Turns: {analysis['total_followups']}")
    print(f"  Total Mistakes: {analysis['total_mistakes']}")
    print(f"  Follow-up Mistakes: {analysis['followup_mistakes']}")
    print(f"  Context Failures: {analysis['context_mistakes']} "
          f"({analysis['context_failure_rate']}%)")
    print(f"  Severity: {analysis['severity_counts']}")

    # Dimensions
    print(f"\n  {'─'*55}")
    print(f"  Dimension Averages (follow-up turns):")
    for dim, score in analysis["dimension_averages"].items():
        bar = "\u2588" * int(score) + "\u2591" * (10 - int(score))
        print(f"    {dim:20s}  {score:5.2f}  {bar}")

    # Context-specific mistake types
    if analysis["context_type_counts"]:
        print(f"\n  {'─'*55}")
        print(f"  Context Failure Types:")
        for mtype, count in sorted(analysis["context_type_counts"].items(),
                                   key=lambda x: -x[1]):
            bar = "\u2588" * min(count, 15) + "\u2591" * max(0, 15 - count)
            print(f"    {mtype:22s}  {count:2d}x  {bar}")

    # All mistake types
    if analysis["type_counts"]:
        print(f"\n  {'─'*55}")
        print(f"  All Mistake Types:")
        for mtype, count in sorted(analysis["type_counts"].items(),
                                   key=lambda x: -x[1]):
            bar = "\u2588" * min(count, 15) + "\u2591" * max(0, 15 - count)
            print(f"    {mtype:22s}  {count:2d}x  {bar}")

    # Code modules to fix
    if analysis["module_counts"]:
        print(f"\n  {'─'*55}")
        print(f"  Modules to Fix (context failures):")
        for mod, count in sorted(analysis["module_counts"].items(),
                                 key=lambda x: -x[1]):
            print(f"    {count:2d}x  {mod}")
            for ex in analysis["module_examples"].get(mod, [])[:2]:
                print(f"         [{ex['type']}] \"{ex['excerpt'][:60]}\"")
                print(f"         Fix: {ex['fix'][:70]}")

    # Worst follow-up cases
    if analysis["worst_cases"]:
        print(f"\n  {'─'*55}")
        print(f"  Worst Follow-up Responses:")
        for w in analysis["worst_cases"]:
            print(f"\n    Topic: {w['topic'][:40]}")
            print(f"    Q: {w['query'][:60]}")
            print(f"    Score: {w['score']}/10  Mistakes: {w['mistakes']} "
                  f"({w['high_severity']} high)")
            if w["feedback"]:
                print(f"    Feedback: {w['feedback'][:100]}")


# ═════════════════════════════════════════════════════════════════════════════
# Phase 5: Test Generation
# ═════════════════════════════════════════════════════════════════════════════

def generate_tests(cases: List[EvalCase], output_path: str = "tests/test_freeform_discovered.py") -> int:
    """Generate regression tests for confirmed bugs.

    Returns the number of tests generated.
    """
    print(f"\n  Phase 5: Generating regression tests...")

    test_cases = []
    for case in cases:
        if not case.judgment:
            continue
        for m in case.judgment.mistakes:
            if m.severity in ("high", "medium") and m.excerpt and len(m.excerpt) > 5:
                test_cases.append((case.query, m))

    if not test_cases:
        print(f"    No test-worthy mistakes found.")
        return 0

    # Generate test file
    lines = [
        '#!/usr/bin/env python3',
        '"""',
        'Discovered regression tests — auto-generated by freeform_bench.py.',
        '',
        'These tests prevent specific mistakes from recurring.',
        'Run: PYTHONPATH=src python tests/test_freeform_discovered.py',
        '"""',
        '',
        'import os, sys, re',
        '',
        '_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")',
        'if _SRC_DIR not in sys.path:',
        '    sys.path.insert(0, _SRC_DIR)',
        '',
        'from cos.nlg.pipeline import naturalize',
        'from cos.nlg.config import NLGConfig',
        '',
        '_t = 0; _p = 0; _f = 0',
        'def suite(name):',
        '    print(f"\\n  Suite: {name}")',
        'def check(n, c, d=""):',
        '    global _t, _p, _f; _t += 1',
        '    if c: _p += 1; print(f"    \\u2713 {n}")',
        '    else: _f += 1; print(f"    \\u2717 {n}" + (f"\\n        {d}" if d else ""))',
        '',
    ]

    # Group tests by slugified query
    seen_slugs = set()
    for query, mistake in test_cases:
        slug = re.sub(r'[^a-z0-9]+', '_', query.lower())[:40].strip('_')
        if slug in seen_slugs:
            slug += f"_{len(seen_slugs)}"
        seen_slugs.add(slug)

        # Sanitize for Python identifier
        func_name = f"test_discovered_{slug}"
        func_name = re.sub(r'[^a-z0-9_]', '_', func_name)
        if not func_name[0].isalpha():
            func_name = 't' + func_name

        excerpt_escaped = mistake.excerpt.replace('\\', '\\\\').replace('"', '\\"')
        query_escaped = query.replace('\\', '\\\\').replace('"', '\\"')
        desc_escaped = mistake.description.replace('\\', '\\\\').replace('"', '\\"')

        lines.extend([
            f'def {func_name}():',
            f'    """Auto-discovered: {desc_escaped[:80]}"""',
            f'    cfg = NLGConfig(style="friendly", verbosity=0.5, temperature=0.0)',
            f'    response = naturalize("{query_escaped}", "", "", "factual", cfg)',
            f'    check(',
            f'        "response should not contain \\"{excerpt_escaped[:40]}\\"",',
            f'        "{excerpt_escaped}" not in response,',
            f'        f"Found problematic text in response: {{response[:150]}}"',
            f'    )',
            f'',
        ])

    lines.extend([
        '',
        f'# Run',
        f'print(f"\\n{{"#"*60}}\\n  Discovered Regression Tests\\n{{"#"*60}}")',
        f'suite("Freeform discovered bugs")',
        f'',
        f'# Execute all test functions',
        f'_test_funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_discovered_")]',
        f'for _fn in _test_funcs:',
        f'    _fn()',
        f'',
        f'print(f"\\n  Results: {{_p}}/{{_t}} passed" + (f", {{_f}} FAILED" if _f else ""))',
        f'sys.exit(1 if _f else 0)',
    ])

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"    Generated {len(test_cases)} tests in {output_path}")
    return len(test_cases)


def generate_multi_turn_tests(cases: List[MultiTurnCase],
                              output_path: str = "tests/test_freeform_multiturn.py") -> int:
    """Generate regression tests for multi-turn conversation bugs.

    Each generated test reproduces a full conversation scenario by calling
    process_query() sequentially (maintaining conversation state), then
    checks that follow-up responses don't contain problematic text.

    Returns the number of tests generated.
    """
    print(f"\n  Phase 5b: Generating multi-turn regression tests...")

    test_cases = []
    for case in cases:
        for j, turn in enumerate(case.turns):
            if j == 0:
                continue  # Skip the first turn — it has no context to test
            if not turn.judgment:
                continue
            for m in turn.judgment.mistakes:
                if m.severity in ("high", "medium") and m.excerpt and len(m.excerpt) > 5:
                    test_cases.append((case, j, m))

    if not test_cases:
        print(f"    No multi-turn test-worthy mistakes found.")
        return 0

    # Generate test file
    lines = [
        '#!/usr/bin/env python3',
        '"""',
        'Discovered multi-turn regression tests — auto-generated by freeform_bench.py.',
        '',
        'These tests reproduce multi-turn conversation scenarios and verify that',
        'follow-up responses correctly use conversation context.',
        'Run: PYTHONPATH=src python tests/test_freeform_multiturn.py',
        '"""',
        '',
        'import os, sys, re',
        '',
        '_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")',
        'if _SRC_DIR not in sys.path:',
        '    sys.path.insert(0, _SRC_DIR)',
        '',
        'from cos.engine import process_query, reset_conversation',
        '',
        '_t = 0; _p = 0; _f = 0',
        'def suite(name):',
        '    print(f"\\n  Suite: {name}")',
        'def check(n, c, d=""):',
        '    global _t, _p, _f; _t += 1',
        '    if c: _p += 1; print(f"    \\u2713 {n}")',
        '    else: _f += 1; print(f"    \\u2717 {n}" + (f"\\n        {d}" if d else ""))',
        '',
    ]

    # Group tests by scenario slug
    seen_slugs = set()
    for case, turn_idx, mistake in test_cases:
        # Build a slug from the topic + turn index
        slug = re.sub(r'[^a-z0-9]+', '_', case.topic.lower())[:30].strip('_')
        if not slug:
            slug = "unknown_topic"
        slug = f"multiturn_{slug}_turn{turn_idx}"
        if slug in seen_slugs:
            slug += f"_{len(seen_slugs)}"
        seen_slugs.add(slug)

        # Sanitize for Python identifier
        func_name = f"test_{slug}"
        func_name = re.sub(r'[^a-z0-9_]', '_', func_name)
        if not func_name[0].isalpha():
            func_name = 't' + func_name

        # Build the conversation setup lines
        # We need to reproduce all turns up to and including the one with the mistake
        setup_lines = []
        setup_lines.append(f'    reset_conversation()')
        for k, turn in enumerate(case.turns):
            q_escaped = turn.query.replace('\\', '\\\\').replace('"', '\\"')
            setup_lines.append(f'    response{k+1} = process_query("{q_escaped}")')

        excerpt_escaped = mistake.excerpt.replace('\\', '\\\\').replace('"', '\\"')
        desc_escaped = mistake.description.replace('\\', '\\\\').replace('"', '\\"')
        topic_escaped = case.topic.replace('\\', '\\\\').replace('"', '\\"')

        # The response variable name for the turn with the mistake
        resp_var = f'response{turn_idx + 1}'

        lines.extend([
            f'def {func_name}():',
            f'    """Auto-discovered multi-turn: {desc_escaped[:80]}"""',
            f'    # Topic: {topic_escaped}',
            f'    # Turn {turn_idx + 1}: {case.turns[turn_idx].query[:60]}',
        ])
        lines.extend(setup_lines)
        lines.extend([
            f'    check(',
            f'        "follow-up response should not contain \\"{excerpt_escaped[:40]}\\"",',
            f'        "{excerpt_escaped}" not in {resp_var},',
            f'        f"Found problematic text in follow-up response: {{{resp_var}[:150]}}"',
            f'    )',
            f'',
        ])

    lines.extend([
        '',
        f'# Run',
        f'print(f"\\n{{"#"*60}}\\n  Multi-Turn Discovered Regression Tests\\n{{"#"*60}}")',
        f'suite("Multi-turn discovered bugs")',
        f'',
        f'# Execute all test functions',
        f'_test_funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_multiturn_")]',
        f'for _fn in _test_funcs:',
        f'    _fn()',
        f'',
        f'print(f"\\n  Results: {{_p}}/{{_t}} passed" + (f", {{_f}} FAILED" if _f else ""))',
        f'sys.exit(1 if _f else 0)',
    ])

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"    Generated {len(test_cases)} multi-turn tests in {output_path}")
    return len(test_cases)


# ═════════════════════════════════════════════════════════════════════════════
# Reporting
# ═════════════════════════════════════════════════════════════════════════════

def save_results(cases: List[EvalCase], analysis: Dict, output_path: str):
    """Save full results to JSON."""
    data = {
        "analysis": analysis,
        "cases": [c.to_dict() for c in cases],
    }
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n  Results saved to {output_path}")


def save_multi_turn_results(cases: List[MultiTurnCase], analysis: Dict,
                            output_path: str):
    """Save multi-turn results to JSON."""
    data = {
        "analysis": analysis,
        "cases": [c.to_dict() for c in cases],
    }
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n  Multi-turn results saved to {output_path}")


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="COS Freeform Benchmark")
    parser.add_argument("--questions", type=int, default=20,
                        help="Number of questions to generate (default: 20)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Use mock data instead of calling Ollama")
    parser.add_argument("--no-tests", action="store_true",
                        help="Skip test generation (report only)")
    parser.add_argument("--multi-turn", action="store_true",
                        help="Also test multi-turn conversation scenarios")
    parser.add_argument("--multi-turn-questions", type=int, default=10,
                        help="Number of multi-turn scenarios (default: 10)")
    parser.add_argument("--output", default="data/freeform_results.json",
                        help="Output path for results JSON")
    parser.add_argument("--test-output", default="tests/test_freeform_discovered.py",
                        help="Output path for generated tests")
    parser.add_argument("--multiturn-test-output",
                        default="tests/test_freeform_multiturn.py",
                        help="Output path for generated multi-turn tests")
    parser.add_argument("--multiturn-output",
                        default="data/freeform_multiturn_results.json",
                        help="Output path for multi-turn results JSON")
    args = parser.parse_args()

    print(f"\n{'#'*65}")
    print(f"  COS Freeform Benchmark")
    print(f"{'#'*65}")
    print(f"  Questions:      {args.questions}")
    print(f"  Dry run:        {args.dry_run}")
    print(f"  Tests:          {'skip' if args.no_tests else args.test_output}")
    print(f"  Multi-turn:     {args.multi_turn}")
    if args.multi_turn:
        print(f"  MT scenarios:   {args.multi_turn_questions}")
        print(f"  MT tests:       {'skip' if args.no_tests else args.multiturn_test_output}")
    print(f"  Model:          {JUDGE_MODEL}")

    # Phase 1: Generate questions
    questions = generate_questions(args.questions, dry_run=args.dry_run)
    if not questions:
        print("  No questions generated. Exiting.")
        return 1

    # Phase 2: Generate responses
    cases = generate_responses(questions)

    # Phase 3: Evaluate
    cases = run_evaluation(cases, dry_run=args.dry_run)

    # Phase 4: Analyze
    analysis = analyze_results(cases)
    print_analysis(analysis)

    # Phase 5: Generate tests
    if not args.no_tests:
        n_tests = generate_tests(cases, args.test_output)
    else:
        n_tests = 0
        print(f"\n  Phase 5: Skipped (--no-tests)")

    # Save results
    save_results(cases, analysis, args.output)

    # ── Multi-turn conversation testing ──────────────────────────────────
    n_mt_tests = 0
    mt_analysis = None
    if args.multi_turn:
        print(f"\n{'#'*65}")
        print(f"  MULTI-TURN CONVERSATION BENCHMARK")
        print(f"{'#'*65}")

        # Phase 1b: Generate multi-turn scenarios
        scenarios = generate_multi_turn_scenarios(
            args.multi_turn_questions, dry_run=args.dry_run)
        if scenarios:
            # Phase 2b: Generate responses (maintaining conversation state)
            mt_cases = generate_multi_turn_responses(scenarios)

            # Phase 3b: Evaluate
            mt_cases = run_multi_turn_evaluation(mt_cases, dry_run=args.dry_run)

            # Phase 4b: Analyze
            mt_analysis = analyze_multi_turn_results(mt_cases)
            print_analysis_multi_turn(mt_analysis)

            # Phase 5b: Generate multi-turn tests
            if not args.no_tests:
                n_mt_tests = generate_multi_turn_tests(
                    mt_cases, args.multiturn_test_output)
            else:
                print(f"\n  Phase 5b: Skipped (--no-tests)")

            # Save multi-turn results
            save_multi_turn_results(mt_cases, mt_analysis,
                                    args.multiturn_output)

    # Final summary
    print(f"\n{'#'*65}")
    print(f"  SUMMARY")
    print(f"{'#'*65}")
    print(f"  Score:          {analysis['overall_average']}/10")
    print(f"  Mistakes:       {analysis['total_mistakes']} ({analysis['severity_counts']})")
    print(f"  Tests:          {n_tests} generated")
    print(f"  Results:        {args.output}")
    if args.multi_turn and mt_analysis:
        print(f"  MT Score:       {mt_analysis['overall_average']}/10 "
              f"(follow-up turns)")
        print(f"  MT Context Fails: {mt_analysis['context_mistakes']} "
              f"({mt_analysis['context_failure_rate']}%)")
        print(f"  MT Tests:       {n_mt_tests} generated")
        print(f"  MT Results:     {args.multiturn_output}")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
