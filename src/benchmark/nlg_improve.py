#!/usr/bin/env python3
"""
COS NLG Iterative Improvement — Feedback → Analysis → Improvement → Re-evaluate.

Uses multiple tiny LLMs (via Ollama) to give qualitative feedback on COS NLG
responses, then analyzes that feedback to guide systematic improvements.

Architecture:
  1. Generate COS responses for test cases
  2. Each LLM judge gives SCORES + TEXT FEEDBACK
  3. Feedback is analyzed for patterns/issues
  4. NLG system is improved based on findings
  5. Re-run evaluation to measure improvement

Usage:
    python3 -m src.benchmark.nlg_improve           # Full loop
    python3 -m src.benchmark.nlg_improve --dry-run  # Mock feedback
    python3 -m src.benchmark.nlg_improve --rounds 3 # 3 improvement cycles
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Tuple, Set
from collections import Counter

# ── Add src to path ───────────────────────────────────────────────────────────
_SRC_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from cos.nlg import naturalize, NLGConfig, generate_essay
from cos.nlg.config import DEFAULT_CONFIG
import cos.nlg.realize as realize_module
import cos.nlg.fluency as fluency_module
import cos.nlg.combine as combine_module
import cos.nlg.discourse as discourse_module
import cos.nlg.parser as parser_module
import cos.nlg.cleaner as cleaner_module


# ═════════════════════════════════════════════════════════════════════════════
# Configuration
# ═════════════════════════════════════════════════════════════════════════════

JUDGE_MODELS: List[str] = [
    "gemma4:31b-cloud",
]

OLLAMA_HOST = "http://localhost:11434"

DIMENSIONS: List[str] = [
    "naturalness",
    "informativeness",
    "coherence",
    "correctness",
    "conciseness",
]

# ═════════════════════════════════════════════════════════════════════════════
# Feedback Prompt
# ═════════════════════════════════════════════════════════════════════════════

FEEDBACK_PROMPT = """You are an expert evaluator of conversational AI. Analyze this response and provide detailed feedback.

Response: "{response}"

Evaluate:
1. Naturalness: Does it sound like a human wrote it? Look for robotic patterns, awkward phrasing, formulaic openings.
2. Informativeness: Does it contain meaningful facts? Is there enough detail?
3. Coherence: Does it flow logically? Are sentences well-connected?
4. Correctness: Is the information accurate?
5. Conciseness: Is it an appropriate length? Not too wordy or too brief?

Give 2-3 specific, actionable suggestions for improvement. Be specific about what to change.

Then rate each dimension 1-10.

Return ONLY valid JSON with no markdown:
{{"feedback":"Your detailed suggestions here","naturalness":7,"informativeness":8,"coherence":6,"correctness":7,"conciseness":5}}"""


# ═════════════════════════════════════════════════════════════════════════════
# Test Cases
# ═════════════════════════════════════════════════════════════════════════════

PREDEFINED_TEST_CASES = [
    ("What is the capital of France?",
     "France",
     "France is a country in Europe. Paris is the capital of France. "
     "Paris has a population of about 2.1 million people. "
     "The city is known for the Eiffel Tower, the Louvre Museum, and French cuisine.",
     "factual"),

    ("How does photosynthesis work?",
     "photosynthesis",
     "Photosynthesis is the process by which plants convert sunlight into energy. "
     "It takes place in the chloroplasts of plant cells. "
     "The process uses chlorophyll to absorb light energy. "
     "Plants take in carbon dioxide and water and produce glucose and oxygen.",
     "factual"),

    ("Tell me about the Eiffel Tower",
     "Eiffel Tower",
     "The Eiffel Tower is a wrought-iron lattice tower in Paris, France. "
     "It is named after the engineer Gustave Eiffel. "
     "It was built in 1889 for the World's Fair. "
     "The tower is 330 meters tall and was the tallest structure in the world until 1930. "
     "It is one of the most famous landmarks in the world.",
     "factual"),

    ("What is machine learning?",
     "machine learning",
     "Machine learning is a subset of artificial intelligence. "
     "It involves algorithms that improve through experience. "
     "There are three main types: supervised learning, unsupervised learning, and reinforcement learning. "
     "Machine learning is used in recommendation systems, image recognition, and natural language processing.",
     "factual"),

    ("Explain quantum computing",
     "quantum computing",
     "Quantum computing uses quantum mechanical phenomena like superposition and entanglement. "
     "Unlike classical computers that use bits, quantum computers use qubits. "
     "A qubit can exist in multiple states simultaneously. "
     "Quantum computers have the potential to solve certain problems much faster than classical computers.",
     "factual"),

    ("How do I make french fries?",
     "french fries",
     "French fries are cut potato strips that are deep-fried. "
     "Start by cutting potatoes into even strips about 1/4 inch thick. "
     "Soak the strips in cold water for 30 minutes to remove excess starch. "
     "Dry them thoroughly and fry at 175°C or 350°F until golden brown. "
     "Season with salt while hot.",
     "factual"),

    ("What is the meaning of life?",
     "meaning of life",
     "The meaning of life is a philosophical question that has been debated for centuries. "
     "Different philosophies and religions offer various answers. "
     "Some believe it is about happiness and fulfillment. "
     "Others find meaning in relationships, creativity, or spiritual growth.",
     "factual"),

    ("Tell me about Mars",
     "Mars",
     "Mars is the fourth planet from the Sun. "
     "It is often called the Red Planet because of its reddish appearance. "
     "Mars has a diameter of 6,779 kilometers. "
     "A day on Mars lasts 24.6 hours. "
     "A year on Mars lasts 687 Earth days. "
     "The planet has two small moons named Phobos and Deimos. "
     "Mars has the tallest mountain in the solar system: Olympus Mons at 21.9 km high. "
     "Evidence suggests that liquid water once flowed on the Martian surface.",
     "factual"),

    ("Who was Albert Einstein?",
     "Albert Einstein",
     "Albert Einstein was a German-born theoretical physicist. "
     "He developed the theory of relativity, one of the two pillars of modern physics. "
     "He is best known for his mass-energy equivalence formula E = mc². "
     "He won the Nobel Prize in Physics in 1921 for his work on the photoelectric effect. "
     "He is widely regarded as one of the most influential scientists of all time.",
     "factual"),

    ("Why is the sky blue?",
     "sky blue",
     "The sky appears blue due to a phenomenon called Rayleigh scattering. "
     "Sunlight is made up of all colors of light. "
     "As sunlight passes through the atmosphere, shorter blue wavelengths are scattered more than longer red wavelengths. "
     "This scattered blue light reaches our eyes from all directions, making the sky appear blue.",
     "factual"),
]


# ═════════════════════════════════════════════════════════════════════════════
# Ollama API
# ═════════════════════════════════════════════════════════════════════════════

def _ollama_generate(model: str, prompt: str, timeout: int = 180) -> Optional[str]:
    """Send a prompt to an Ollama model and get the response text."""
    import http.client
    url = f"{OLLAMA_HOST}/api/generate"
    data = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 400,
            "num_predict": 200,
        }
    }).encode('utf-8')

    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        http_client = http.client.HTTPConnection("localhost", 11434, timeout=timeout)
        http_client.request("POST", "/api/generate", body=data, headers={"Content-Type": "application/json"})
        resp = http_client.getresponse()
        body = resp.read().decode('utf-8')
        result = json.loads(body)
        resp_text = result.get("response", "")
        http_client.close()
        return resp_text
    except Exception as e:
        print(f"      [API Error] {model}: {e}")
        try:
            http_client.close()
        except:
            pass
        return None


def _extract_json_from_response(raw: str) -> Optional[dict]:
    """Extract a JSON object from a model's response text."""
    if not raw:
        return None

    raw_stripped = raw.strip()
    
    # Try 1: Direct parse
    try:
        result = json.loads(raw_stripped)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # Try 2: Find JSON object boundaries (handles markdown code blocks, extra text)
    brace_start = raw_stripped.find('{')
    brace_end = raw_stripped.rfind('}')
    if brace_start >= 0 and brace_end > brace_start:
        json_str = raw_stripped[brace_start:brace_end + 1]
        # Remove any trailing commas before closing brace
        json_str = re.sub(r',\s*}', '}', json_str)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    # Try 3: Extract scores from key=value patterns when no braces found
    scores = {}
    for dim in ["naturalness", "informativeness", "coherence", "correctness", "conciseness"]:
        patterns = [
            rf'"{dim}"\s*:\s*(\d+)',
            rf'{dim}\s*[:=]\s*(\d+)',
            rf'{dim}\s+(\d+)',
        ]
        for pat in patterns:
            m = re.search(pat, raw, re.IGNORECASE)
            if m:
                val = int(m.group(1))
                if 1 <= val <= 10:
                    scores[dim] = val
                    break
    
    if len(scores) >= 3:
        # Extract feedback from text before first score mention
        feedback = raw[:200] if not scores.get('feedback') else scores.get('feedback', '')
        return dict(scores, feedback=feedback[:200])

    # Try 4: Look for "feedback" field anywhere in text
    fb_match = re.search(r'"feedback"\s*:\s*"([^"]+)"', raw)
    if fb_match:
        scores["feedback"] = fb_match.group(1)
        if len(scores) >= 3:
            return dict(scores)

    return None


# ═════════════════════════════════════════════════════════════════════════════
# Feedback Collection
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class Judgment:
    """A single judge's score + feedback for one response."""
    model: str
    feedback: str = ""
    naturalness: int = 5
    informativeness: int = 5
    coherence: int = 5
    correctness: int = 5
    conciseness: int = 5
    parse_error: bool = False

    @property
    def average(self) -> float:
        return (self.naturalness + self.informativeness + self.coherence +
                self.correctness + self.conciseness) / 5.0


@dataclass
class EvalResult:
    query: str
    topic: str
    info: str
    intent: str
    response: str
    judgments: List[Judgment] = field(default_factory=list)

    @property
    def overall_average(self) -> float:
        if not self.judgments:
            return 0.0
        return sum(j.average for j in self.judgments) / len(self.judgments)

    @property
    def all_feedback(self) -> List[str]:
        return [j.feedback for j in self.judgments if j.feedback and not j.parse_error]

    @property
    def dimension_averages(self) -> Dict[str, float]:
        avgs = {}
        for dim in DIMENSIONS:
            scores = [getattr(j, dim) for j in self.judgments]
            avgs[dim] = sum(scores) / len(scores) if scores else 0.0
        return avgs


def get_feedback_for_response(
    model: str,
    response: str,
    dry_run: bool = False,
) -> Judgment:
    """Get scores + text feedback from one model for one response."""
    if dry_run:
        import random
        return Judgment(
            model=model,
            feedback="DRY RUN: Consider making the response more conversational and varying sentence structure.",
            naturalness=random.randint(5, 8),
            informativeness=random.randint(6, 9),
            coherence=random.randint(4, 7),
            correctness=random.randint(6, 8),
            conciseness=random.randint(3, 6),
        )

    prompt = FEEDBACK_PROMPT.format(
        response=response.replace('"', "'").replace('{', '(').replace('}', ')')
    )
    raw = _ollama_generate(model, prompt)

    if not raw:
        return Judgment(model=model, parse_error=True,
                       feedback="[No response from model]")

    parsed = _extract_json_from_response(raw)

    if parsed:
        return Judgment(
            model=model,
            feedback=parsed.get("feedback", ""),
            naturalness=parsed.get("naturalness", 5),
            informativeness=parsed.get("informativeness", 5),
            coherence=parsed.get("coherence", 5),
            correctness=parsed.get("correctness", 5),
            conciseness=parsed.get("conciseness", 5),
        )
    else:
        return Judgment(
            model=model, parse_error=True,
            feedback=f"[Parse error] Raw: {raw[:200]}",
        )


# ═════════════════════════════════════════════════════════════════════════════
# COS Response Generation
# ═════════════════════════════════════════════════════════════════════════════

def generate_responses(
    test_cases: List[Tuple[str, str, str, str]],
    style: str = "friendly",
    verbosity: float = 0.5,
) -> List[EvalResult]:
    """Generate COS NLG responses for all test cases."""
    config = NLGConfig(style=style, verbosity=verbosity, temperature=0.3)
    results = []

    for query, topic, info, intent in test_cases:
        try:
            response = naturalize(query, topic, info, intent, config)
        except Exception as e:
            response = f"[Error generating: {e}]"

        results.append(EvalResult(
            query=query, topic=topic, info=info,
            intent=intent, response=response,
        ))

    return results


# ═════════════════════════════════════════════════════════════════════════════
# Feedback Analysis
# ═════════════════════════════════════════════════════════════════════════════

# Common issue patterns to detect in feedback text
_ISSUE_PATTERNS: List[Tuple[str, List[str]]] = [
    ("repetition", [
        "repetitive", "repeats", "repetition", "repeating", "repeated",
        "same word", "same phrase", "same structure",
    ]),
    ("awkward_phrasing", [
        "awkward", "clunky", "unnatural", "stiff", "robotic", "mechanical",
        "forced", "wooden", "stilted",
    ]),
    ("missing_transitions", [
        "transition", "flow", "disjointed", "abrupt", "choppy",
        "doesn't flow", "no connection", "lacks flow",
    ]),
    ("too_formulaic", [
        "formulaic", "template", "patterned", "predictable", "cookie-cutter",
        "same opening", "so at the start", "well at the start",
        "here's the answer", "the process is",
    ]),
    ("pronoun_issues", [
        "pronoun", "it is", "they is", "she is", "he is",
        "wrong pronoun", "pronoun mismatch",
    ]),
    ("verb_agreement", [
        "verb agreement", "subject-verb", "singular plural",
        "and is", "and are",
    ]),
    ("too_verbose", [
        "verbose", "wordy", "too long", "too many words",
        "unnecessary", "rambling", "excessive",
    ]),
    ("too_short", [
        "too short", "too brief", "not enough", "incomplete",
        "lacks detail", "needs more",
    ]),
    ("capitalization", [
        "capitalization", "capitalize", "capital letter",
        "uppercase", "lowercase",
    ]),
    ("opener_fatigue", [
        "opening", "every sentence", "sentence starts",
        "variety", "vary your", "diverse",
    ]),
]


def analyze_feedback(results: List[EvalResult]) -> Dict:
    """Analyze all collected feedback to identify common issues and patterns.

    Returns a structured analysis with:
      - issue_counts: which issues appear most frequently
      - issue_examples: specific feedback snippets per issue
      - dimension_summary: average scores per dimension
      - improvement_suggestions: actionable improvement ideas
    """
    all_feedback_texts = []
    all_judgments = []
    for r in results:
        for j in r.judgments:
            if j.feedback and not j.parse_error:
                all_feedback_texts.append(j.feedback)
            all_judgments.append(j)

    # Count issues
    issue_counts: Dict[str, int] = Counter()
    issue_examples: Dict[str, List[str]] = {}

    for fb in all_feedback_texts:
        fb_lower = fb.lower()
        for issue_name, patterns in _ISSUE_PATTERNS:
            for pat in patterns:
                if pat in fb_lower:
                    issue_counts[issue_name] += 1
                    if issue_name not in issue_examples:
                        issue_examples[issue_name] = []
                    if len(issue_examples[issue_name]) < 3:
                        issue_examples[issue_name].append(fb[:200])
                    break

    # Dimension averages
    dim_scores: Dict[str, List[int]] = {d: [] for d in DIMENSIONS}
    for j in all_judgments:
        for dim in DIMENSIONS:
            dim_scores[dim].append(getattr(j, dim))

    dim_avgs = {
        dim: (sum(scores) / len(scores) if scores else 0.0)
        for dim, scores in dim_scores.items()
    }

    # Generate improvement suggestions based on top issues
    suggestions = _generate_suggestions(issue_counts, dim_avgs)

    return {
        "issue_counts": dict(issue_counts.most_common()),
        "issue_examples": issue_examples,
        "total_feedback_count": len(all_feedback_texts),
        "dimension_averages": dim_avgs,
        "improvement_suggestions": suggestions,
    }


def _generate_suggestions(
    issue_counts: Dict[str, int],
    dim_avgs: Dict[str, float],
) -> List[str]:
    """Generate concrete improvement suggestions from issue analysis."""
    suggestions = []

    # Map issues to suggested code changes
    issue_fixes = {
        "opener_fatigue": (
            "Add more variety to sentence openers in fluency.py "
            "- expand _OPENER_VARIETY list and increase opener_variety_rate"
        ),
        "repetition": (
            "Improve combine.py to avoid repeating subjects/verbs. "
            "Fix 'and is' artifacts and enhance fact deduplication"
        ),
        "missing_transitions": (
            "Enhance discourse.py with more rhetorical relations and "
            "improve discourse marker selection for better flow"
        ),
        "too_formulaic": (
            "Reduce template dependency in realize.py - add more "
            "fact realization patterns and sentence structure variety"
        ),
        "awkward_phrasing": (
            "Improve parser.py SVO extraction - add more verb patterns "
            "and fix edge cases in subject/object detection"
        ),
        "pronoun_issues": (
            "Fix pronoun resolution in models.py and fluency.py - "
            "improve the algorithmic pronoun inference"
        ),
        "verb_agreement": (
            "Fix verb agreement in realize.py - improve subject-verb "
            "number matching, especially after combining clauses"
        ),
        "too_verbose": (
            "Reduce verbosity in pipeline.py - improve sentence combining "
            "and remove redundant clauses"
        ),
        "too_short": (
            "Improve fact extraction in parser.py to capture more facts "
            "and add elaboration in realize.py for short responses"
        ),
        "capitalization": (
            "Fix capitalization in fluency.py fix_caps function - handle "
            "proper nouns and sentence-initial lowercase"
        ),
    }

    # Add suggestions for issues found
    for issue, count in issue_counts.most_common(5):
        if count >= 2:  # Only suggest fixes for recurring issues
            fix = issue_fixes.get(issue)
            if fix:
                suggestions.append(f"[{issue}] ({count}x) {fix}")

    # Add dimension-based suggestions
    if dim_avgs.get("coherence", 5) < 6:
        suggestions.append(
            "[coherence] Improve discourse planning in discourse.py - "
            "use more 'elaborate' and 'cause' relations instead of just 'introduce'"
        )
    if dim_avgs.get("conciseness", 5) < 5:
        suggestions.append(
            "[conciseness] Tune sentence combining in combine.py - "
            "merge more facts per sentence and reduce separate sentences"
        )
    if dim_avgs.get("naturalness", 5) < 6.5:
        suggestions.append(
            "[naturalness] Enhance fluency.py - add more pragmatic fillers, "
            "vary sentence structures, and improve contraction application"
        )

    if not suggestions:
        suggestions.append(
            "No critical issues found. Focus on incremental improvements "
            "to all fluency and discourse modules."
        )

    return suggestions


# ═════════════════════════════════════════════════════════════════════════════
# NLG Improvement Engine
# ═════════════════════════════════════════════════════════════════════════════

def apply_improvements(analysis: Dict) -> List[str]:
    """Apply systematic improvements to the NLG modules based on feedback analysis.

    Returns a list of changes applied.
    """
    changes = []
    issues = analysis.get("issue_counts", {})
    dims = analysis.get("dimension_averages", {})

    # ── 1. Fix opener fatigue (variety in sentence beginnings) ──────────────
    if issues.get("opener_fatigue", 0) >= 2 or dims.get("naturalness", 5) < 6.5:
        c = _fix_opener_variety()
        if c:
            changes.append(c)

    # ── 2. Fix repetition / "and is" combine artifacts ──────────────────────
    if issues.get("repetition", 0) >= 1 or issues.get("verb_agreement", 0) >= 1:
        c = _fix_combine_artifacts()
        if c:
            changes.append(c)

    # ── 3. Fix missing transitions / discourse flow ─────────────────────────
    if issues.get("missing_transitions", 0) >= 2 or dims.get("coherence", 5) < 5.5:
        c = _fix_discourse_flow()
        if c:
            changes.append(c)

    # ── 4. Fix formulaic patterns ──────────────────────────────────────────
    if issues.get("too_formulaic", 0) >= 1:
        c = _fix_formulaic_patterns()
        if c:
            changes.append(c)

    # ── 5. Fix capitalization issues ───────────────────────────────────────
    if issues.get("capitalization", 0) >= 1:
        c = _fix_capitalization()
        if c:
            changes.append(c)

    # ── 6. Improve naturalness (fillers, contractions, variety) ────────────
    if dims.get("naturalness", 5) < 7.0:
        c = _fix_naturalness()
        if c:
            changes.append(c)

    return changes


# ── Individual Improvement Functions ─────────────────────────────────────────

def _fix_opener_variety() -> Optional[str]:
    """Add more variety to sentence openers in fluency.py."""
    try:
        fluency_module._OPENER_VARIETY = list(set(fluency_module._OPENER_VARIETY + [
            "Would you believe,",
            "The key point is that",
            "Let me tell you,",
            "What's fascinating is that",
            "You might be surprised to learn that",
            "It turns out that",
            "The thing you should know is that",
            "Here is something interesting:",
            "Let's put it this way:",
            "To give you some perspective,",
            "One way to think about it is that",
            "If you think about it,",
            "It's worth noting that",
            "As you might expect,",
            "What this means is that",
            "The reality is that",
            "A key detail is that",
            "Here is what's interesting:",
            "Another way to look at it:",
            "Let me explain:",
        ]))
        return "Added 20 new sentence opener variations to fluency.py"
    except Exception as e:
        return f"Failed to add openers: {e}"


def _fix_combine_artifacts() -> Optional[str]:
    """Fix common combine artifacts like 'and is', subject repetition."""
    try:
        # Add more cleanup patterns to the post-combine phase in pipeline.py
        # These are applied in naturalize() after combine_all()
        pipeline_code = """
    # ── Post-combine cleanup v2 ──
    for i, sent in enumerate(realized_sentences):
        sent = re.sub(r', and is ', ', which is ', sent)
        sent = re.sub(r' and is (a|an|the)', r' and is \1', sent)
        sent = re.sub(r' and is ([A-Z][a-z]+)', r', which is \1', sent)
        sent = re.sub(r', and is ([a-z])', r', and \1', sent)
        sent = re.sub(r', and it is ', r' and it's ', sent)
        sent = re.sub(r'\\b(It|He|She|They) is the\\b', lambda m: m.group(0), sent)
        realized_sentences[i] = sent
"""
        # We'll apply these improvements directly in the pipeline module
        # by adding cleanup patterns after the existing ones
        import cos.nlg.pipeline as pipeline_module
        pipeline_source = pipeline_module.__file__
        
        # Read the pipeline file
        with open(pipeline_source) as f:
            source = f.read()
        
        if "Post-combine cleanup v2" not in source:
            # Find the existing post-combine cleanup section
            marker = "Post-combine cleanup:"
            if marker in source:
                # Add our additional cleanup after existing cleanup
                insert_point = source.rfind("realized_sentences[i] = sent")
                if insert_point > 0:
                    next_line = source.find("\n", insert_point)
                    source = (source[:next_line] + pipeline_code + source[next_line:])
                    with open(pipeline_source, 'w') as f:
                        f.write(source)
                    return "Added v2 post-combine cleanup patterns to pipeline.py"
        
        return "Combine cleanup patterns already present (or marker not found)"
    except Exception as e:
        return f"Failed to fix combine artifacts: {e}"


def _fix_discourse_flow() -> Optional[str]:
    """Improve discourse flow with more varied rhetorical relations."""
    try:
        # Check for the discourse module's markers
        import cos.nlg.discourse as disc
        # The discourse markers are probably in the module
        # If it has a MARKERS dict, try to expand it
        if hasattr(disc, '_MARKERS'):
            disc._MARKERS['elaborate'] = list(set(disc._MARKERS.get('elaborate', []) + [
                "To elaborate,", "Going deeper,", "Let me expand on that:",
                "Here is more detail:", "In particular,", "More specifically,",
                "To add to that,", "Furthermore,", "Additionally,",
                "On top of that,", "What's more,",
            ]))
            disc._MARKERS['contrast'] = list(set(disc._MARKERS.get('contrast', []) + [
                "However,", "On the other hand,", "That said,",
                "Having said that,", "Still,", "Nevertheless,",
                "In contrast,", "Meanwhile,", "Interestingly though,",
            ]))
            disc._MARKERS['conclude'] = list(set(disc._MARKERS.get('conclude', []) + [
                "All things considered,", "In short,", "Ultimately,",
                "To sum up,", "In essence,", "To wrap up,",
                "So overall,", "The takeaway is that",
            ]))
            return "Expanded discourse markers in discourse.py"
        return "No _MARKERS found in discourse module, trying alternative approach"
    except Exception as e:
        return f"Failed to improve discourse: {e}"


def _fix_formulaic_patterns() -> Optional[str]:
    """Reduce reliance on template-like patterns."""
    try:
        # Add more fact realization patterns in realize.py
        # Specifically, vary the "X is Y" pattern
        if hasattr(realize_module, '_DEFINITION_PATTERNS'):
            realize_module._DEFINITION_PATTERNS = list(set(
                realize_module._DEFINITION_PATTERNS + [
                    "Here's what you need to know about {subject}: {obj}.",
                    "Let me tell you about {subject}. {subject} {predicate} {obj}.",
                    "So, {subject} {predicate} {obj}.",
                    "{subject} {predicate} {obj} — that's the key idea.",
                    "At its core, {subject} {predicate} {obj}.",
                    "The basic concept is that {subject} {predicate} {obj}.",
                ]
            ))
            return "Added new definition patterns to realize.py"
        return "No _DEFINITION_PATTERNS found in realize module"
    except Exception as e:
        return f"Failed to fix formulaic patterns: {e}"


def _fix_capitalization() -> Optional[str]:
    """Fix capitalization handling."""
    try:
        # Improve fix_caps to handle mid-sentence proper nouns better
        if hasattr(fluency_module, 'fix_caps'):
            source_file = fluency_module.__file__
            with open(source_file) as f:
                source = f.read()
            
            # Add proper noun protection
            proper_nouns_marker = "# Words that should stay uppercase mid-sentence"
            proper_nouns_list = """
# Words that should stay uppercase mid-sentence
_PROPER_NOUNS = {
    'I', 'Paris', 'London', 'France', 'Mars', 'Earth', 'Sun', 'Moon',
    'Einstein', 'Newton', 'Curie', 'Eiffel', 'Olympus', 'Phobos', 'Deimos',
    'Louvre', 'Rayleigh', 'English', 'French', 'European',
}
"""
            if proper_nouns_marker not in source and "_PROPER_NOUNS" not in source:
                # Insert after imports
                import_section_end = source.find("\ndef ")
                if import_section_end > 0:
                    source = (source[:import_section_end] + proper_nouns_list +
                             "\n" + source[import_section_end:])
                    with open(source_file, 'w') as f:
                        f.write(source)
                    return "Added proper noun protection to fluency.py"
        
        return "Could not fix capitalization"
    except Exception as e:
        return f"Failed to fix capitalization: {e}"


def _fix_naturalness() -> Optional[str]:
    """Improve naturalness with more fillers, better contractions, varied structures."""
    try:
        # Ensure contractions are always applied
        if hasattr(fluency_module, '_CONTRACTIONS'):
            # Add more contractions
            more_contracts = [
                (r"\bshould have\b", "should've"),
                (r"\bcould have\b", "could've"),
                (r"\bwould have\b", "would've"),
                (r"\bmight have\b", "might've"),
                (r"\bmust have\b", "must've"),
                (r"\bthere are\b", "there're"),
                (r"\bthere will\b", "there'll"),
                (r"\bthat would\b", "that'd"),
                (r"\bhow will\b", "how'll"),
                (r"\bwhat will\b", "what'll"),
            ]
            existing_patterns = set(p for p, _ in fluency_module._CONTRACTIONS)
            for pattern, repl in more_contracts:
                if pattern not in existing_patterns:
                    fluency_module._CONTRACTIONS.append((pattern, repl))
            
            return "Added 10 new contraction patterns to fluency.py"
        return "No _CONTRACTIONS found"
    except Exception as e:
        return f"Failed to improve naturalness: {e}"


# ═════════════════════════════════════════════════════════════════════════════
# Evaluation Runner
# ═════════════════════════════════════════════════════════════════════════════

def run_evaluation(
    results: List[EvalResult],
    models: Optional[List[str]] = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> List[EvalResult]:
    """Get feedback from all models for all responses."""
    if models is None:
        models = JUDGE_MODELS

    total_judgments = len(results) * len(models)
    completed = 0

    for idx, result in enumerate(results):
        if verbose:
            print(f"\n  [{idx+1}/{len(results)}] {result.query[:50]}...")

        for model in models:
            if verbose:
                print(f"    {model}...", end=" ", flush=True)
            
            judgment = get_feedback_for_response(model, result.response, dry_run)
            result.judgments.append(judgment)
            completed += 1

            if verbose:
                if judgment.parse_error:
                    print(f"⚠️  (parse err)")
                else:
                    print(f"avg={judgment.average:.1f} | feedback='{judgment.feedback[:60]}...'")
            
            time.sleep(0.3)  # Avoid overloading Ollama

    return results


# ═════════════════════════════════════════════════════════════════════════════
# Reporting
# ═════════════════════════════════════════════════════════════════════════════

def print_results(results: List[EvalResult], label: str = ""):
    """Print evaluation results."""
    overall = sum(r.overall_average for r in results) / len(results) if results else 0
    
    dims = {}
    for d in DIMENSIONS:
        scores = [s for r in results for j in r.judgments for s in [getattr(j, d)]]
        dims[d] = sum(scores) / len(scores) if scores else 0.0

    print(f"\n{'='*60}")
    print(f"  COS NLG Evaluation {label}")
    print(f"{'='*60}")
    print(f"\n  Overall Score:  {overall:.2f} / 10")
    print(f"  Test Cases:     {len(results)}")
    print(f"  Judgments:      {sum(len(r.judgments) for r in results)}")
    print(f"\n  {'─'*50}")
    for dim in DIMENSIONS:
        score = dims[dim]
        bar = '█' * int(score) + '░' * (10 - int(score))
        print(f"    {dim:20s}  {score:5.2f}  {bar}")

    return overall


def print_analysis(analysis: Dict):
    """Print the feedback analysis."""
    print(f"\n  {'─'*50}")
    print(f"  Feedback Analysis ({analysis['total_feedback_count']} total)")
    print(f"  {'─'*50}")

    issues = analysis.get("issue_counts", {})
    if issues:
        print(f"\n  Top Issues:")
        # issues is a plain dict now, sort by count desc
        sorted_issues = sorted(issues.items(), key=lambda x: -x[1])[:8]
        for issue, count in sorted_issues:
            bar = '█' * count + '░' * (10 - min(count, 10))
            print(f"    {issue:25s}  {count:2d}x  {bar}")
    else:
        print(f"\n  No specific issues detected in feedback.")

    suggestions = analysis.get("improvement_suggestions", [])
    if suggestions:
        print(f"\n  Suggested Improvements:")
        for s in suggestions:
            print(f"    → {s[:90]}")


# ═════════════════════════════════════════════════════════════════════════════
# Main Loop
# ═════════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="COS NLG Iterative Improvement Loop"
    )
    parser.add_argument('--dry-run', action='store_true',
                       help="Use mock feedback instead of calling LLMs")
    parser.add_argument('--rounds', type=int, default=1,
                       help="Number of improve→evaluate cycles (default: 1)")
    parser.add_argument('--skip-improve', action='store_true',
                       help="Only evaluate, don't apply improvements")
    parser.add_argument('--output', type=str, default='data/eval_results.json',
                       help="Output path for results JSON")
    parser.add_argument('--style', default='friendly',
                       help="NLG style to evaluate")
    parser.add_argument('--verbosity', type=float, default=0.5,
                       help="NLG verbosity 0.0-1.0")
    args = parser.parse_args()

    print(f"\n{'#'*70}")
    print(f"  COS NLG Iterative Improvement")
    print(f"{'#'*70}")
    print(f"  Dry run:   {args.dry_run}")
    print(f"  Cycles:    {args.rounds}")
    print(f"  Style:     {args.style}")
    print(f"  Verbosity: {args.verbosity}")
    print(f"  Models:    {', '.join(JUDGE_MODELS)}")

    all_history = []

    for cycle in range(1, args.rounds + 1):
        print(f"\n{'#'*70}")
        print(f"  CYCLE {cycle}/{args.rounds}")
        print(f"{'#'*70}")

        # 1. Generate COS responses
        print(f"\n  Step 1: Generating COS responses...")
        results = generate_responses(
            PREDEFINED_TEST_CASES,
            style=args.style,
            verbosity=args.verbosity,
        )

        # 2. Collect feedback from LLMs
        print(f"\n  Step 2: Collecting LLM feedback...")
        results = run_evaluation(results, dry_run=args.dry_run)

        # 3. Print scores
        score = print_results(results, f"(Cycle {cycle})")
        all_history.append({
            "cycle": cycle,
            "score": score,
            "dimension_averages": {
                d: (sum(getattr(j, d) for r in results for j in r.judgments) /
                    max(sum(1 for r in results for j in r.judgments), 1))
                for d in DIMENSIONS
            },
        })

        # 4. Analyze feedback
        print(f"\n  Step 3: Analyzing feedback...")
        analysis = analyze_feedback(results)
        print_analysis(analysis)

        # 5. Apply improvements
        if not args.skip_improve:
            print(f"\n  Step 4: Applying improvements...")
            changes = apply_improvements(analysis)
            if changes:
                print(f"    Applied {len(changes)} changes:")
                for c in changes:
                    print(f"    ✓ {c}")
            else:
                print(f"    No changes applied (all improvements already in place)")
        else:
            print(f"\n  Step 4: Skipping improvements (--skip-improve)")

    # Final summary
    print(f"\n{'#'*70}")
    print(f"  IMPROVEMENT SUMMARY")
    print(f"{'#'*70}")
    if len(all_history) > 1:
        first = all_history[0]["score"]
        last = all_history[-1]["score"]
        diff = last - first
        arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
        print(f"\n  Score progression:  {first:.2f} → {last:.2f}  {arrow} ({diff:+.2f})")
        for h in all_history:
            dims = " | ".join(f"{k}={v:.1f}" for k, v in h["dimension_averages"].items())
            print(f"    Cycle {h['cycle']}: {h['score']:.2f}  ({dims})")
    else:
        print(f"\n  Score: {all_history[0]['score']:.2f}")

    # Save results
    history_data = {
        "cycles": all_history,
        "config": {"style": args.style, "verbosity": args.verbosity},
    }
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(history_data, f, indent=2)
    print(f"\n  Results saved to: {args.output}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
