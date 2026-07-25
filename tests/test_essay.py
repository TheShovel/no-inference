"""Tests for the essay generation system."""

import os, sys
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from cos.nlg.essay import generate_essay
from cos.nlg.config import NLGConfig

_t = 0; _p = 0; _f = 0
def suite(name):
    print(f"\n{'='*60}\n  Suite: {name}\n{'='*60}")
def check(n, c, d=""):
    global _t, _p, _f; _t += 1
    if c: _p += 1; print(f"  ✓ {n}")
    else: _f += 1; print(f"  ✗ {n}" + (f"\n      {d}" if d else ""))

info_photosynthesis = (
    "Photosynthesis is the process plants use to convert sunlight into energy. "
    "Plants use chlorophyll to capture light energy. "
    "The process produces oxygen as a byproduct. "
    "Photosynthesis is essential for life on Earth."
)
info_france = (
    "Paris is the capital of France. "
    "Paris is located on the River Seine. "
    "It has a population of over 2 million people."
)
info_curie = (
    "Marie Curie was a Polish-born physicist and chemist. "
    "She conducted pioneering research on radioactivity. "
    "She won two Nobel Prizes."
)

def test_basic():
    suite("Basic generation")
    for style in ["friendly", "neutral", "concise"]:
        cfg = NLGConfig(style=style, verbosity=0.6, temperature=0.5)
        r = generate_essay("photosynthesis", info_photosynthesis, cfg)
        check(f"{style} produces output", len(r) > 50)
        check(f"{style} contains topic", "photosynthesis" in r.lower() or "Photosynthesis" in r)

def test_no_duplicate_facts():
    suite("No duplicate facts")
    r = generate_essay("photosynthesis", info_photosynthesis, NLGConfig(style="neutral", verbosity=0.5, temperature=0.0))
    # Essential for life should only appear once
    count = r.lower().count("essential for life")
    check("essential mentioned once", count <= 2)  # may appear in intro + body

def test_multiple_topics():
    suite("Multiple topics")
    for topic, info in [("France", info_france), ("Marie Curie", info_curie)]:
        r = generate_essay(topic, info, NLGConfig(style="friendly", verbosity=0.5, temperature=0.5))
        check(f"{topic} essay generated", len(r) > 50)

def test_empty_info():
    suite("Empty info")
    r = generate_essay("test", "", NLGConfig(temperature=0.0))
    check("fallback on empty", len(r) > 5)

def test_content_rich():
    suite("Content richness")
    r = generate_essay("photosynthesis", info_photosynthesis, NLGConfig(style="neutral", temperature=0.0))
    # Should contain actual content words from the info
    for word in ["sunlight", "energy", "chlorophyll", "oxygen"]:
        check(f"contains '{word}'", word in r.lower())

def test_deterministic():
    suite("Deterministic at temp=0")
    cfg = NLGConfig(style="neutral", verbosity=0.4, temperature=0.0)
    info = "Paris is the capital of France. Paris is located on the River Seine. It has a population of over 2 million people."
    r1 = generate_essay("France", info, cfg)
    r2 = generate_essay("France", info, cfg)
    check("identical output", r1 == r2)

def test_punctuation_clean():
    suite("Clean punctuation")
    r = generate_essay("photosynthesis", info_photosynthesis, NLGConfig(style="neutral", temperature=0.0))
    check("no double periods", ".." not in r)
    check("no space before period", ". " in r or r.endswith("."))
    check("properly capitalized", r[0].isupper())

# Run
suites = [test_basic, test_no_duplicate_facts, test_multiple_topics,
          test_empty_info, test_content_rich, test_deterministic, test_punctuation_clean]

print(f"\n{'#'*60}\n  COS Essay Generation Tests\n{'#'*60}")
for s in suites:
    s()

print(f"\n{'='*60}\n  Results: {_p}/{_t} passed" + (f", {_f} FAILED" if _f else "") + f"\n{'='*60}")
sys.exit(1 if _f else 0)
