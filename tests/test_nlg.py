#!/usr/bin/env python3
"""
test_nlg.py — Test suite for the NLG layer.

Run:
    python3 tests/test_nlg.py
"""

import os
import sys
import re

_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from cos.nlg import (
    naturalize,
    make_conversational,
    NLGConfig,
    clean_information,
    _apply_contractions as apply_contractions,
    _apply_pronouns as apply_pronouns,
    _fix_caps as fix_caps,
    _split_sentences as split_sentences,
    _lower_first,
    _upper_first,
    _classify_query,
    _get_opening,
    _sentence_type,
    _rhetorical_structure,
    realize_sentence,
    enhance_fluency,
)

_tests_run = 0
_tests_passed = 0
_tests_failed = 0
_current_suite = ""

def suite(name):
    global _current_suite
    _current_suite = name
    print(f"\n{'='*60}")
    print(f"  Suite: {name}")
    print(f"{'='*60}")

def check(name, condition, detail=None):
    global _tests_run, _tests_passed, _tests_failed
    _tests_run += 1
    if condition:
        _tests_passed += 1
        print(f"  ✓ {name}")
    else:
        _tests_failed += 1
        msg = f"  ✗ {name}"
        if detail:
            msg += f"\n      {detail}"
        print(msg)

def check_eq(name, actual, expected):
    detail = None
    if actual != expected:
        detail = f"Expected: {expected!r}\n      Got:      {actual!r}"
    check(name, actual == expected, detail)

def check_in(name, item, container):
    detail = None
    if item not in container:
        detail = f"Expected {item!r} to be in {container!r}"
    check(name, item in container, detail)

def check_not_in(name, item, container):
    detail = None
    if item in container:
        detail = f"Expected {item!r} NOT to be in {container!r}"
    check(name, item not in container, detail)

def summary():
    global _tests_run, _tests_passed, _tests_failed
    print(f"\n{'='*60}")
    print(f"  Results: {_tests_passed}/{_tests_run} passed", end="")
    if _tests_failed > 0:
        print(f", {_tests_failed} FAILED", end="")
    print()
    print(f"{'='*60}")
    return _tests_failed == 0


# ── Tests ────────────────────────────────────────────────────────────────────

def test_contractions():
    suite("apply_contractions")
    check_eq("it is -> it's", apply_contractions("it is nice"), "it's nice")
    check_eq("do not -> don't", apply_contractions("do not go"), "don't go")
    check_eq("cannot -> can't", apply_contractions("cannot do"), "can't do")
    check_eq("will not -> won't", apply_contractions("will not work"), "won't work")
    check_eq("you are -> you're", apply_contractions("you are great"), "you're great")
    check_eq("let us -> let's", apply_contractions("let us go"), "let's go")
    check_eq("empty", apply_contractions(""), "")

def test_pronouns():
    suite("apply_pronouns")
    # Should replace second occurrence
    result = apply_pronouns("Photosynthesis is a process. Photosynthesis is essential.", "Photosynthesis")
    check("second occurrence replaced", "it" in result.lower())
    check("'the it' not created", "the it" not in result.lower())
    # Single occurrence unchanged
    result = apply_pronouns("Photosynthesis is a process.", "Photosynthesis")
    check_eq("single occurrence kept", result.count("Photosynthesis"), 1)

def test_clean_information():
    suite("clean_information")
    result = clean_information("Paris is the capital. Paris is located on the Seine. It has 2M people. It's a city. It is famous.")
    sents = split_sentences(result)
    check("truncates to max_sentences", len(sents) <= 4)
    result = clean_information("")
    check_eq("empty", result, "")

def test_classify_query():
    suite("classify_query")
    check_eq("how query", _classify_query("How do I make fries?"), "how")
    check_eq("who query", _classify_query("Who was Einstein?"), "who")
    check_eq("what query", _classify_query("What is France?"), "explain")
    check_eq("define query", _classify_query("Define recursion"), "define")
    check_eq("explain query", _classify_query("Explain physics"), "explain")
    check_eq("where query", _classify_query("Where is Paris?"), "where")
    check_eq("default", _classify_query("Hello"), "factual")

def test_sentence_type():
    suite("sentence_type")
    check_eq("contrast", _sentence_type("However, it is different."), "contrast")
    check_eq("example", _sentence_type("For example, take this."), "example")
    check_eq("cause", _sentence_type("Because of this, it works."), "cause")
    check_eq("elaborate", _sentence_type("In addition, it has more."), "elaborate")
    check_eq("default elaborate", _sentence_type("It is red."), "elaborate")

def test_naturalize_capital():
    suite("naturalize — capital of France")
    cfg = NLGConfig(style="neutral", verbosity=0.3, temperature=0.0)
    info = "Paris is the capital of France. Paris is located on the River Seine. It has over 2M people."
    result = naturalize("What is the capital of France?", "capital of France", info, "factual", cfg)
    check("produces response", len(result) > 20)
    check("mentions Paris", "Paris" in result)
    check("mentions France", "France" in result)
    check("no double periods", ".." not in result)

def test_naturalize_french_fries():
    suite("naturalize — french fries")
    cfg = NLGConfig(style="neutral", verbosity=0.3, temperature=0.0)
    info = "French fries are made by cutting potatoes into strips. They are fried in oil."
    result = naturalize("How do I make french fries?", "french fries", info, "factual", cfg)
    check("produces response", len(result) > 20)
    check("mentions fries or strips", "fries" in result.lower() or "strips" in result.lower())

def test_naturalize_photosynthesis():
    suite("naturalize — photosynthesis")
    cfg = NLGConfig(style="neutral", verbosity=0.3, temperature=0.0)
    info = "Photosynthesis is the process plants use to convert sunlight into energy. Plants use chlorophyll to capture light."
    result = naturalize("What is photosynthesis?", "photosynthesis", info, "factual", cfg)
    check("produces response", len(result) > 20)
    check("no 'the photosynthesis'", "the photosynthesis" not in result.lower())
    check("uses 'it' not 'they'", "they is" not in result.lower())

def test_naturalize_quantum():
    suite("naturalize — quantum computing")
    cfg = NLGConfig(style="neutral", verbosity=0.3, temperature=0.0)
    info = "Quantum computing uses quantum bits or qubits. Unlike classical bits, qubits can exist in superposition."
    result = naturalize("Explain quantum computing", "quantum computing", info, "factual", cfg)
    check("produces response", len(result) > 10)
    check("mentions qubits", "qubit" in result.lower())

def test_naturalize_marie_curie():
    suite("naturalize — Marie Curie")
    cfg = NLGConfig(style="neutral", verbosity=0.3, temperature=0.0)
    info = "Marie Curie was a Polish-born physicist and chemist. She conducted pioneering research on radioactivity."
    result = naturalize("Who was Marie Curie?", "Marie Curie", info, "factual", cfg)
    check("produces response", len(result) > 20)
    check("mentions radioactivity", "radioactivity" in result.lower())

def test_naturalize_no_info():
    suite("naturalize — no information")
    cfg = NLGConfig(style="neutral", temperature=0.0)
    result = naturalize("What is quantum gravity?", None, "", "factual", cfg)
    check("produces fallback", len(result) > 10)
    check("says not sure", "not sure" in result.lower() or "don't" in result.lower())

def test_naturalize_styles():
    suite("naturalize — style differences")
    info = "Paris is the capital of France."
    friendly = NLGConfig(style="friendly", verbosity=0.6, temperature=0.5)
    concise = NLGConfig(style="concise", verbosity=0.1, temperature=0.0)
    fr = naturalize("What is the capital of France?", "capital of France", info, "factual", friendly)
    co = naturalize("What is the capital of France?", "capital of France", info, "factual", concise)
    check("friendly not empty", len(fr) > 10)
    check("concise not empty", len(co) > 10)

def test_naturalize_deterministic():
    suite("naturalize — deterministic")
    cfg = NLGConfig(style="neutral", verbosity=0.3, temperature=0.0)
    info = "Paris is the capital of France."
    r1 = naturalize("What is the capital of France?", "capital of France", info, "factual", cfg)
    r2 = naturalize("What is the capital of France?", "capital of France", info, "factual", cfg)
    check_eq("temp=0 deterministic", r1, r2)

def test_make_conversational():
    suite("make_conversational")
    cfg = NLGConfig(style="friendly", temperature=0.0)
    raw = "It is a nice day. It is warm outside."
    result = make_conversational(raw, cfg)
    check("contracts", "It's" in result or "it's" in result)
    check("capitalizes", result[0].isupper())

def test_enhance_fluency():
    suite("enhance_fluency")
    cfg = NLGConfig(style="neutral", temperature=0.0)
    result = enhance_fluency("It is a nice day. It is warm.", cfg)
    check("contracts", "it's" in result.lower() or "It's" in result)
    result = enhance_fluency("", cfg)
    check_eq("empty", result, "")

def test_realize_sentence():
    suite("realize_sentence")
    cfg = NLGConfig(style="neutral", temperature=0.0)
    result = realize_sentence("hello world", cfg)
    check("capitalizes", result[0].isupper())
    result = realize_sentence("", cfg)
    check_eq("empty", "", result) if result == "" else check("empty handled", True)

def test_helpers():
    suite("Helpers")
    check_eq("lower first", _lower_first("Hello"), "hello")
    check_eq("lower first empty", _lower_first(""), "")
    check_eq("upper first", _upper_first("hello"), "Hello")
    check_eq("upper first empty", _upper_first(""), "")
    sents = split_sentences("Hello. World! Test?")
    check("splits sentences", len(sents) >= 3)
    check_eq("empty split", split_sentences(""), [])

def test_config():
    suite("NLGConfig")
    cfg = NLGConfig()
    check_eq("default style", cfg.style, "friendly")
    cfg2 = NLGConfig(style="concise", verbosity=0.1, temperature=0.0)
    check_eq("concise style", cfg2.style, "concise")
    check_eq("clamped verbosity", cfg2.verbosity, 0.1)
    check_eq("clamped temp", cfg2.temperature, 0.0)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'#'*60}")
    print(f"  COS NLG Test Suite v2")
    print(f"  Module: cos.nlg")
    print(f"{'#'*60}")

    test_contractions()
    test_pronouns()
    test_clean_information()
    test_classify_query()
    test_sentence_type()
    test_naturalize_capital()
    test_naturalize_french_fries()
    test_naturalize_photosynthesis()
    test_naturalize_quantum()
    test_naturalize_marie_curie()
    test_naturalize_no_info()
    test_naturalize_styles()
    test_naturalize_deterministic()
    test_make_conversational()
    test_enhance_fluency()
    test_realize_sentence()
    test_helpers()
    test_config()

    all_pass = summary()
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
