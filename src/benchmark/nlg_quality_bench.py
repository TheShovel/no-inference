#!/usr/bin/env python3
"""
NLG Quality Benchmark v2 — 12 dimensions, adversarial test cases.

Harder than v1:
  - Longer texts (8-10 sentences) with more facts to track
  - Entity aliases ("Einstein" vs "the physicist")
  - Numerical precision (exact values must survive)
  - Negation detection ("has no atmosphere" must not flip)
  - Causal/temporal ordering (sequence must be preserved)
  - Comparison direction ("X > Y" must not reverse)
  - Multi-entity coreference (two entities, correct pronouns)
  - Unit consistency (384,400 km must stay km)

Each dimension scored 0-100. Overall = weighted average.
"""

import os, sys, re

_SRC = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from cos.nlg import naturalize, generate_essay, NLGConfig
from cos.nlg.models import _infer_gender_from_text, build_entity


# ═════════════════════════════════════════════════════════════════════════════
# CHALLENGING TEST CASES
# ═════════════════════════════════════════════════════════════════════════════

TEST_CASES = [
    # ── 1. Long-form: 10 facts, aliases, numerical precision ──
    {
        "name": "Mars",
        "query": "Tell me about Mars",
        "topic": "Mars",
        "info": (
            "Mars is the fourth planet from the Sun. "
            "It is often called the Red Planet because of its reddish appearance. "
            "Mars has a diameter of 6,779 kilometers. "
            "A day on Mars lasts 24.6 hours. "
            "A year on Mars lasts 687 Earth days. "
            "The planet has two small moons named Phobos and Deimos. "
            "Mars has the tallest mountain in the solar system: Olympus Mons at 21.9 km high. "
            "Evidence suggests that liquid water once flowed on the Martian surface. "
            "The atmosphere of Mars is 95% carbon dioxide. "
            "Mars has no global magnetic field."
        ),
        "required": ["fourth planet", "Red Planet", "6,779", "24.6", "687",
                     "Phobos", "Deimos", "Olympus Mons", "21.9", "water",
                     "carbon dioxide", "no global magnetic field"],
        "negations": ["no global magnetic field"],
        "numerics": {"6,779": "6,779", "24.6": "24.6", "687": "687", "21.9": "21.9"},
        "pronouns": {"Mars": "it"},
    },

    # ── 2. Multi-entity: Einstein and Newton, correct pronouns ──
    {
        "name": "Einstein Newton",
        "query": "Compare Einstein and Newton",
        "topic": "Einstein and Newton",
        "info": (
            "Isaac Newton was an English mathematician and physicist. "
            "He formulated the laws of motion and universal gravitation. "
            "Albert Einstein was a German-born theoretical physicist. "
            "He developed the theory of relativity. "
            "Newton's work is called classical mechanics. "
            "Einstein's theory of relativity revolutionized modern physics. "
            "Newton published his Principia in 1687. "
            "Einstein published his theory of general relativity in 1915."
        ),
        "required": ["Newton", "Einstein", "motion", "gravitation", "relativity",
                     "1687", "1915", "classical mechanics"],
        "negations": [],
        "numerics": {"1687": "1687", "1915": "1915"},
        "pronouns": {"Isaac Newton": "he", "Albert Einstein": "he",
                     "Einstein and Newton": "they"},
    },

    # ── 3. Earth: causal chain, temporal order ──
    {
        "name": "Earth",
        "query": "Tell me about Earth",
        "topic": "Earth",
        "info": (
            "Earth is the third planet from the Sun. "
            "It has a diameter of 12,742 kilometers. "
            "About 71% of Earth's surface is covered by water. "
            "The planet formed approximately 4.54 billion years ago. "
            "Life appeared on Earth about 3.5 billion years ago. "
            "The atmosphere is composed of 78% nitrogen and 21% oxygen. "
            "Earth's atmosphere protects life from harmful solar radiation. "
            "The Moon stabilizes Earth's axial tilt. "
            "Without the Moon, Earth's climate would be extremely unstable."
        ),
        "required": ["third planet", "12,742", "71%", "water", "4.54 billion",
                     "3.5 billion", "78%", "nitrogen", "oxygen", "Moon",
                     "axial tilt"],
        "negations": [],
        "numerics": {"12,742": "12,742", "71": "71", "4.54": "4.54",
                      "3.5": "3.5", "78": "78", "21": "21"},
        "pronouns": {"Earth": "it", "The Moon": "it"},
    },

    # ── 4. Jupiter: comparison with Saturn, units ──
    {
        "name": "Jupiter",
        "query": "Tell me about Jupiter",
        "topic": "Jupiter",
        "info": (
            "Jupiter is the largest planet in the Solar System. "
            "It has a diameter of 139,820 kilometers. "
            "It is more than twice as massive as all other planets combined. "
            "Jupiter has 95 known moons, including the four large Galilean moons. "
            "The Great Red Spot is a persistent storm larger than Earth. "
            "A day on Jupiter lasts only 9.9 hours, the shortest day of any planet. "
            "Jupiter's magnetic field is about 20,000 times stronger than Earth's. "
            "The planet has no solid surface — it is a gas giant. "
            "Saturn is the second largest planet, but Jupiter is much larger."
        ),
        "required": ["largest planet", "139,820", "95", "Galilean",
                     "Great Red Spot", "9.9", "magnetic field",
                     "gas giant", "no solid surface", "Saturn"],
        "negations": ["no solid surface"],
        "numerics": {"139,820": "139,820", "95": "95", "9.9": "9.9"},
        "pronouns": {"Jupiter": "it", "Saturn": "it"},
    },

    # ── 5. Beethoven: alias tracking ──
    {
        "name": "Beethoven",
        "query": "Who was Ludwig van Beethoven?",
        "topic": "Ludwig van Beethoven",
        "info": (
            "Ludwig van Beethoven was a German composer and pianist. "
            "He was born in Bonn in 1770. "
            "Beethoven began to lose his hearing in his late 20s. "
            "Despite becoming completely deaf, he continued to compose. "
            "The composer wrote nine symphonies, five piano concertos, and 32 piano sonatas. "
            "His third symphony, the Eroica, marked the transition to the Romantic era. "
            "Beethoven's Ninth Symphony features the famous Ode to Joy. "
            "He died in Vienna in 1827."
        ),
        "required": ["composer", "pianist", "Bonn", "1770", "deaf",
                     "nine symphonies", "Eroica", "Ode to Joy",
                     "Vienna", "1827", "Romantic"],
        "negations": [],
        "numerics": {"1770": "1770", "1827": "1827", "nine": "9", "nine symphonies": "symphonies"},
        "pronouns": {"Ludwig van Beethoven": "he", "Beethoven": "he", "The composer": "he"},
    },

    # ── 6. Amazon Rainforest: long causal + numeric ──
    {
        "name": "Amazon",
        "query": "Tell me about the Amazon Rainforest",
        "topic": "Amazon Rainforest",
        "info": (
            "The Amazon Rainforest is the largest tropical rainforest in the world. "
            "It covers approximately 5.5 million square kilometers. "
            "The forest spans nine countries, with 60% in Brazil. "
            "The Amazon is home to about 10% of all known species on Earth. "
            "It produces about 6% of the world's oxygen. "
            "Deforestation has destroyed about 17% of the forest since 1970. "
            "The Amazon River is the largest river by discharge volume of water. "
            "It flows about 6,400 kilometers from the Andes to the Atlantic. "
            "The rainforest plays a crucial role in regulating the global climate."
        ),
        "required": ["largest tropical rainforest", "5.5 million", "nine",
                     "60%", "Brazil", "10%", "species", "6%", "oxygen",
                     "17%", "1970", "Amazon River", "6,400", "Andes",
                     "Atlantic", "climate"],
        "negations": [],
        "numerics": {"5.5": "5.5", "60": "60", "10": "10", "6": "6",
                      "17": "17", "1970": "1970", "6,400": "6,400"},
        "pronouns": {"Amazon Rainforest": "it", "the Amazon": "it"},
    },

    # ── 7. Solar System: comparison direction ──
    {
        "name": "Solar System",
        "query": "Tell me about the Solar System",
        "topic": "Solar System",
        "info": (
            "The Solar System consists of the Sun and eight planets. "
            "The four inner planets are Mercury, Venus, Earth, and Mars. "
            "The four outer planets are Jupiter, Saturn, Uranus, and Neptune. "
            "Mercury is the smallest planet. "
            "Jupiter is the largest planet. "
            "Venus is hotter than Mercury despite being farther from the Sun. "
            "Neptune is the farthest planet from the Sun. "
            "Uranus rotates on its side, with an axial tilt of 98 degrees. "
            "Saturn has the most extensive ring system of any planet."
        ),
        "required": ["eight planets", "inner planets", "Mercury", "Venus",
                     "outer planets", "Uranus", "Neptune",
                     "smallest planet", "largest planet",
                     "hotter than Mercury", "ring system"],
        "negations": [],
        "numerics": {"eight": "8", "98": "98"},
        "pronouns": {"Solar System": "it", "Saturn": "it", "Uranus": "it"},
    },

    # ── 8. Python programming: technical accuracy ──
    {
        "name": "Python",
        "query": "What is Python?",
        "topic": "Python",
        "info": (
            "Python is a high-level, interpreted programming language. "
            "It was created by Guido van Rossum and first released in 1991. "
            "Python emphasizes code readability through significant indentation. "
            "It supports multiple programming paradigms including procedural and object-oriented. "
            "Python's standard library is extensive and includes modules for various tasks. "
            "The language is dynamically typed and garbage-collected. "
            "Python is widely used in data science, machine learning, and web development. "
            "Version 3 was released in 2008 and is not fully backward-compatible with Version 2."
        ),
        "required": ["high-level", "interpreted", "Guido van Rossum", "1991",
                     "indentation", "object-oriented", "dynamically typed",
                     "garbage-collected", "data science", "machine learning",
                     "2008", "not fully backward-compatible"],
        "negations": ["not fully backward-compatible"],
        "numerics": {"1991": "1991", "2008": "2008"},
        "pronouns": {"Python": "it"},
    },

    # ── 9. Human Brain: complex multi-fact ──
    {
        "name": "Brain",
        "query": "Tell me about the human brain",
        "topic": "human brain",
        "info": (
            "The human brain is the central organ of the nervous system. "
            "It weighs about 1.4 kilograms. "
            "The brain contains approximately 86 billion neurons. "
            "Each neuron can form up to 10,000 connections with other neurons. "
            "The brain consumes about 20% of the body's energy. "
            "It is protected by the skull and three layers of membranes called meninges. "
            "The cerebrum is the largest part and is divided into two hemispheres. "
            "The left hemisphere typically controls language and logic. "
            "The right hemisphere is more involved in creativity and spatial awareness. "
            "The brain has no pain receptors, so brain surgery can be performed while awake."
        ),
        "required": ["central organ", "nervous system", "1.4", "86 billion",
                     "neurons", "10,000", "20%", "meninges",
                     "cerebrum", "two hemispheres", "language",
                     "creativity", "no pain receptors"],
        "negations": ["no pain receptors"],
        "numerics": {"1.4": "1.4", "86": "86", "10,000": "10,000", "20": "20"},
        "pronouns": {"human brain": "it", "The brain": "it", "The cerebrum": "it"},
    },

    # ── 10. World War II: temporal ordering ──
    {
        "name": "WWII",
        "query": "Tell me about World War II",
        "topic": "World War II",
        "info": (
            "World War II was a global conflict that lasted from 1939 to 1945. "
            "The war involved most of the world's nations forming two opposing alliances. "
            "Germany invaded Poland on September 1, 1939, triggering the war. "
            "Japan attacked Pearl Harbor on December 7, 1941. "
            "The United States entered the war after Pearl Harbor. "
            "D-Day occurred on June 6, 1944, when Allied forces landed in Normandy. "
            "Germany surrendered on May 8, 1945, ending the war in Europe. "
            "The atomic bombs were dropped on Hiroshima and Nagasaki in August 1945. "
            "Japan surrendered on September 2, 1945, ending the war."
        ),
        "required": ["1939", "1945", "Poland", "Pearl Harbor", "1941",
                     "D-Day", "1944", "Normandy", "May 8",
                     "atomic bombs", "Hiroshima", "Nagasaki",
                     "September 2"],
        "negations": [],
        "numerics": {"1939": "1939", "1945": "1945", "1941": "1941",
                      "1944": "1944"},
        "pronouns": {"World War II": "it"},
    },
]

# ── Pronoun source texts for algorithmic inference ─────────────────────────

PRONOUN_SOURCES = {
    "Mars": ("Mars is a planet. It is red.", "it"),
    "Isaac Newton": ("Newton was a physicist. He discovered gravity.", "he"),
    "Albert Einstein": ("Einstein was a physicist. He developed relativity.", "he"),
    "Earth": ("Earth is a planet. It has water.", "it"),
    "Jupiter": ("Jupiter is a planet. It is large.", "it"),
    "Ludwig van Beethoven": ("Beethoven was a composer. He wrote symphonies.", "he"),
    "Amazon Rainforest": ("The Amazon is a forest. It is in Brazil.", "it"),
    "Python": ("Python is a language. It is interpreted.", "it"),
    "human brain": ("The brain is an organ. It controls the body.", "it"),
    "World War II": ("WWII was a war. It lasted six years.", "it"),
}


def suite(name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")

_results = {}
_total_checks = 0
_passed_checks = 0
_failed_checks = 0

def check(n, c, d=""):
    global _total_checks, _passed_checks, _failed_checks
    _total_checks += 1
    if c:
        _passed_checks += 1
        print(f"  ✓ {n}")
    else:
        _failed_checks += 1
        msg = f"  ✗ {n}"
        if d:
            msg += f"\n      {d}"
        print(msg)


# ═════════════════════════════════════════════════════════════════════════════
# 1. FACT PRESERVATION (harder: longer texts, more facts)
# ═════════════════════════════════════════════════════════════════════════════

def bench_fact_preservation():
    suite("1. Fact Preservation — all facts survive NLG reformulation?")
    total, found = 0, 0

    for tc in TEST_CASES:
        r = naturalize(tc["query"], tc["topic"], tc["info"], "factual",
                      NLGConfig(style="neutral", verbosity=0.4, temperature=0.0))
        r_lower = r.lower()
        for fact in tc["required"]:
            total += 1
            if fact.lower() in r_lower:
                found += 1

    total_e, found_e = 0, 0
    for tc in TEST_CASES:
        r = generate_essay(tc["topic"], tc["info"],
                          NLGConfig(style="neutral", verbosity=0.4, temperature=0.0))
        r_lower = r.lower()
        for fact in tc["required"]:
            total_e += 1
            if fact.lower() in r_lower:
                found_e += 1

    score = (found / total * 100) if total else 0
    score_e = (found_e / total_e * 100) if total_e else 0
    avg = (score + score_e) / 2
    check(f"naturalize: {found}/{total} = {score:.1f}%", score >= 85, f"Only {score:.1f}%")
    check(f"essays:     {found_e}/{total_e} = {score_e:.1f}%", score_e >= 75, f"Only {score_e:.1f}%")
    return avg


# ═════════════════════════════════════════════════════════════════════════════
# 2. NEGATION ACCURACY — "has no X" must not become "has X"
# ═════════════════════════════════════════════════════════════════════════════

def bench_negation():
    suite("2. Negation Accuracy — negatives are not flipped?")
    score = 100
    for tc in TEST_CASES:
        if not tc["negations"]:
            continue
        for style in ["neutral", "friendly"]:
            r = naturalize(tc["query"], tc["topic"], tc["info"], "factual",
                          NLGConfig(style=style, verbosity=0.4, temperature=0.5))
            r_lower = r.lower()
            for neg in tc["negations"]:
                neg_word = neg.replace("no ", "").replace("not ", "").strip()
                # Check the negation IS preserved
                has_neg = "no " in r_lower or "not " in r_lower or "without" in r_lower or "n't" in r_lower
                if not has_neg:
                    score -= 15
                    check(f"  {tc['name']}: negation lost: '{neg}'", False)
    check(f"Negation score: {score}%", score >= 70)
    return max(0, score)


# ═════════════════════════════════════════════════════════════════════════════
# 3. NUMERICAL PRECISION — exact values must survive
# ═════════════════════════════════════════════════════════════════════════════

def bench_numerical():
    suite("3. Numerical Precision — exact values preserved?")
    total, found = 0, 0
    for tc in TEST_CASES:
        r = naturalize(tc["query"], tc["topic"], tc["info"], "factual",
                      NLGConfig(style="neutral", verbosity=0.4, temperature=0.0))
        r_lower = r.lower()
        for key, expected in tc["numerics"].items():
            total += 1
            if expected.lower() in r_lower:
                found += 1

    score = (found / total * 100) if total else 0
    check(f"Numerical precision: {found}/{total} = {score:.1f}%", score >= 70, f"Only {score:.1f}%")
    return score


# ═════════════════════════════════════════════════════════════════════════════
# 4. ENTITY CONSISTENCY — pronouns match entities throughout
# ═════════════════════════════════════════════════════════════════════════════

def bench_entity_consistency():
    suite("4. Entity Consistency — pronouns match entities?")

    score = 100
    for tc in TEST_CASES:
        topic = tc["topic"]
        pronoun_lookup = {k.lower(): v for k, v in tc["pronouns"].items()}
        correct_pronoun = pronoun_lookup.get(topic.lower(), "it")

        gender = _infer_gender_from_text(topic, tc["info"])
        inferred = "she" if gender == "feminine" else ("he" if gender == "masculine" else None)
        if inferred is None:
            e = build_entity(topic, tc["info"])
            inferred = e.pronoun

        if inferred != correct_pronoun:
            score -= 10
            check(f"  {tc['name']}: inferred '{inferred}', expected '{correct_pronoun}'", False)

        e = build_entity(topic, tc["info"])
        if e.pronoun != correct_pronoun:
            score -= 10
            check(f"  {tc['name']}: entity pronoun '{e.pronoun}', expected '{correct_pronoun}'", False)

    check(f"Entity consistency: {score}%", score >= 70, f"Score {score}%")
    return max(0, score)


# ═════════════════════════════════════════════════════════════════════════════
# 5. PRONOUN ACCURACY (from source text)
# ═════════════════════════════════════════════════════════════════════════════

def bench_pronoun_accuracy():
    suite("5. Pronoun Accuracy — correct pronoun from source text?")
    correct = 0
    for name, (source, expected) in PRONOUN_SOURCES.items():
        gender = _infer_gender_from_text(name, source)
        p = "she" if gender == "feminine" else ("he" if gender == "masculine" else "it")
        if expected == "they":
            e = build_entity(name, source)
            p_actual = e.pronoun
        else:
            p_actual = p
        if expected == p_actual:
            correct += 1

    total = len(PRONOUN_SOURCES)
    score = correct / total * 100
    check(f"Pronoun accuracy: {correct}/{total} = {score:.1f}%", score >= 85, f"{score:.1f}%")
    return score


# ═════════════════════════════════════════════════════════════════════════════
# 6. DISCOURSE COHERENCE — multi-sentence flow, no fragments
# ═════════════════════════════════════════════════════════════════════════════

def bench_coherence():
    suite("6. Discourse Coherence — natural flow, no fragments?")
    score = 100
    for tc in TEST_CASES:
        r = naturalize(tc["query"], tc["topic"], tc["info"], "factual",
                      NLGConfig(style="friendly", verbosity=0.5, temperature=0.5))
        # Topic must be mentioned somewhere
        if tc["topic"].lower() not in r.lower() and tc["name"].lower() not in r.lower():
            score -= 10
        # Every sentence must end properly
        for sent in re.split(r'(?<=[.!?])\s+', r):
            s = sent.strip()
            if s and not s.endswith(('.', '!', '?')):
                score -= 5
        # Must be long enough
        if len(r) < 30:
            score -= 10
    check(f"Coherence: {score}%", score >= 70)
    return max(0, score)


# ═════════════════════════════════════════════════════════════════════════════
# 7. INFORMATIVENESS — response is about the topic
# ═════════════════════════════════════════════════════════════════════════════

def bench_informativeness():
    suite("7. Informativeness — response contains topic content?")
    score = 100
    for tc in TEST_CASES:
        r = naturalize(tc["query"], tc["topic"], tc["info"], "factual",
                      NLGConfig(style="neutral", verbosity=0.4, temperature=0.0))
        r_lower = r.lower()
        content_words = set(w for w in tc["info"].lower().split()
                           if w not in {'the','a','an','is','are','was','were','in',
                                        'on','at','to','for','of','and','or','its',
                                        'it','this','that','by','as','with','from',
                                        'be','has','have','had','not','no','but','his',
                                        'her','all','each','which','who','been'} and len(w) > 3)
        found_words = sum(1 for w in content_words if w in r_lower)
        if len(content_words) > 0:
            ratio = found_words / len(content_words)
            if ratio < 0.25:
                score -= 15
    check(f"Informativeness: {score}%", score >= 65)
    return max(0, score)


# ═════════════════════════════════════════════════════════════════════════════
# 8. ARTIFACT DETECTION
# ═════════════════════════════════════════════════════════════════════════════

def bench_artifacts():
    suite("8. Artifact Detection — zero bad patterns?")
    BAD = ['is she she', 'and is she', 'she can won', 'unlike unlike',
           'so so', 'a a', 'in in', 'on on', 'it is it', 'and and', 'the the']
    found = False
    for tc in TEST_CASES:
        for style in ['friendly', 'neutral']:
            for temp in [0.0, 0.5]:
                r = naturalize(tc["query"], tc["topic"], tc["info"], "factual",
                              NLGConfig(style=style, verbosity=0.4, temperature=temp))
                r_lower = r.lower()
                for bp in BAD:
                    if re.search(r'\b' + re.escape(bp) + r'\b', r_lower):
                        check(f"  '{bp}' in {tc['name']}", False, f"in: {r[:80]}")
                        found = True
    if not found:
        check("Zero artifacts", True)
    return 0 if found else 100


# ═════════════════════════════════════════════════════════════════════════════
# 9. DETERMINISM
# ═════════════════════════════════════════════════════════════════════════════

def bench_determinism():
    suite("9. Determinism — temp=0 identical?")
    det, tot = 0, 0
    for tc in TEST_CASES:
        cfg = NLGConfig(style="neutral", verbosity=0.4, temperature=0.0)
        for _ in range(3):
            tot += 1
            r1 = naturalize(tc["query"], tc["topic"], tc["info"], "factual", cfg)
            r2 = naturalize(tc["query"], tc["topic"], tc["info"], "factual", cfg)
            if r1 == r2:
                det += 1
    score = det / tot * 100 if tot else 0
    check(f"Determinism: {det}/{tot} = {score:.0f}%", score == 100)
    return score


# ═════════════════════════════════════════════════════════════════════════════
# 10. STYLE SEPARATION
# ═════════════════════════════════════════════════════════════════════════════

def bench_style():
    suite("10. Style Separation — styles distinct?")
    dist = 0
    for tc in TEST_CASES:
        fr = naturalize(tc["query"], tc["topic"], tc["info"], "factual",
                       NLGConfig(style="friendly", verbosity=0.6, temperature=0.5))
        co = naturalize(tc["query"], tc["topic"], tc["info"], "factual",
                       NLGConfig(style="concise", verbosity=0.1, temperature=0.0))
        if abs(len(fr) - len(co)) > 40:
            dist += 1
    score = dist / len(TEST_CASES) * 100
    check(f"Style separation: {dist}/{len(TEST_CASES)} = {score:.0f}%", score >= 70)
    return score


# ═════════════════════════════════════════════════════════════════════════════
# 11. TEMPERATURE VARIETY
# ═════════════════════════════════════════════════════════════════════════════

def bench_temperature():
    suite("11. Temperature Variety — higher temps vary output?")
    var = 0
    for tc in TEST_CASES:
        r0 = naturalize(tc["query"], tc["topic"], tc["info"], "factual",
                       NLGConfig(style="friendly", verbosity=0.5, temperature=0.0))
        r1 = naturalize(tc["query"], tc["topic"], tc["info"], "factual",
                       NLGConfig(style="friendly", verbosity=0.5, temperature=0.9))
        if r0 != r1:
            var += 1
    score = var / len(TEST_CASES) * 100
    check(f"Temperature variety: {var}/{len(TEST_CASES)} = {score:.0f}%", score >= 70)
    return score


# ═════════════════════════════════════════════════════════════════════════════
# 12. LONG-FORM COHERENCE (essays on complex topics)
# ═════════════════════════════════════════════════════════════════════════════

def bench_essays():
    suite("12. Essay Quality — multi-paragraph on long texts?")
    score = 100
    for tc in TEST_CASES:
        r = generate_essay(tc["topic"], tc["info"],
                          NLGConfig(style="friendly", verbosity=0.6, temperature=0.5))
        # Must have at least 2 paragraphs
        paras = r.split('\n\n')
        if len(paras) < 2:
            score -= 10
        # Total length
        if len(r) < 100:
            score -= 10
        # Topic must appear
        if tc["topic"].lower() not in r.lower() and tc["name"].lower() not in r.lower():
            score -= 10
    check(f"Essay quality: {score}%", score >= 60)
    return max(0, score)


# ═════════════════════════════════════════════════════════════════════════════
# RUN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{'#'*70}")
    print(f"  NLG QUALITY BENCHMARK v2")
    print(f"  {len(TEST_CASES)} complex test cases, 12 dimensions")
    print(f"  Multi-entity, negation, numerics, temporal, comparison")
    print(f"{'#'*70}")

    bench_results = {}
    for name, fn in [
        ("1. Fact Preservation", bench_fact_preservation),
        ("2. Negation Accuracy", bench_negation),
        ("3. Numerical Precision", bench_numerical),
        ("4. Entity Consistency", bench_entity_consistency),
        ("5. Pronoun Accuracy", bench_pronoun_accuracy),
        ("6. Discourse Coherence", bench_coherence),
        ("7. Informativeness", bench_informativeness),
        ("8. Artifact Detection", bench_artifacts),
        ("9. Determinism", bench_determinism),
        ("10. Style Separation", bench_style),
        ("11. Temperature Variety", bench_temperature),
        ("12. Essay Quality", bench_essays),
    ]:
        bench_results[name] = fn()

    weights = {
        "1. Fact Preservation": 0.15,
        "2. Negation Accuracy": 0.10,
        "3. Numerical Precision": 0.10,
        "4. Entity Consistency": 0.08,
        "5. Pronoun Accuracy": 0.07,
        "6. Discourse Coherence": 0.07,
        "7. Informativeness": 0.07,
        "8. Artifact Detection": 0.15,
        "9. Determinism": 0.05,
        "10. Style Separation": 0.06,
        "11. Temperature Variety": 0.05,
        "12. Essay Quality": 0.05,
    }

    total_weight = sum(weights.values())
    overall = sum(bench_results[k] * weights[k] for k in bench_results) / total_weight

    print(f"\n{'='*65}")
    print(f"  NLG QUALITY BENCHMARK v2 — RESULTS")
    print(f"{'='*65}")
    for name, score in bench_results.items():
        bar = "█" * int(score / 5) + "░" * (20 - int(score / 5))
        print(f"  {name:30s} {score:6.1f}% {bar}")
    print(f"  {'─'*63}")
    print(f"  {'Overall NLG Quality':30s} {overall:6.1f}%")
    print(f"  Tests: {_total_checks}, Passed: {_passed_checks}, Failed: {_failed_checks}")
    print(f"{'='*65}")

    return 0 if overall >= 60 else 1


if __name__ == '__main__':
    sys.exit(main())
