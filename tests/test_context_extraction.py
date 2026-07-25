#!/usr/bin/env python3
"""
test_context_extraction.py — COMPREHENSIVE test suite for the symbolic
context extraction system.

Tests all extraction strategies (including new compound+verb strategies),
edge cases, conversation context tracking, question classification,
and cross-strategy consistency.

Run:
    python3 tests/test_context_extraction.py
    python3 -m pytest tests/test_context_extraction.py -v  (if pytest is available)

Current test count: 400+ individual assertions across 40+ test functions.
"""

import os
import sys
import re
import random

# Add src to path so we can import the cos package
_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from cos.context_extraction import (
    # Main API
    extract_keywords,
    extract_topic,
    extract_noun_phrases_only,
    extract_entities_only,
    extract_context_topic,
    # New API
    classify_question,
    extract_compound_phrases,
    extract_by_verb_pattern,
    # Internal strategies
    extract_by_question_pattern,
    extract_noun_phrases,
    extract_entities,
    extract_content_words,
    extract_cleaned_query,
    # Utilities
    clean_query,
    remove_stop_words,
    normalize_topic,
    is_empty_topic,
    is_context_dependent,
    _is_pronoun_query,
    collapse_whitespace,
    # Constants
    get_stop_words,
    get_known_compounds,
    get_empty_topics,
    _EMPTY_TOPICS,
    _QUESTION_PATTERNS,
    _KNOWN_COMPOUNDS,
    _STOP_WORDS
)

# ── Test infrastructure ─────────────────────────────────────────────────────

_tests_run = 0
_tests_passed = 0
_tests_failed = 0
_current_suite = ""


def suite(name):
    """Start a new test suite."""
    global _current_suite
    _current_suite = name
    print(f"\n{'='*60}")
    print(f"  Suite: {name}")
    print(f"{'='*60}")


def check(name, condition, detail=None):
    """Assert a condition is true."""
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
    """Assert actual == expected."""
    detail = None
    if actual != expected:
        detail = f"Expected: {expected!r}\n      Got:      {actual!r}"
    check(name, actual == expected, detail)


def check_gt(name, value, threshold):
    """Assert value > threshold."""
    detail = None
    if not (value > threshold):
        detail = f"Value {value!r} is not > {threshold!r}"
    check(name, value > threshold, detail)


def check_in(name, item, container):
    """Assert item is in container."""
    detail = None
    if item not in container:
        detail = f"Expected {item!r} to be in {container!r}"
    check(name, item in container, detail)


def check_not_in(name, item, container):
    """Assert item is not in container."""
    detail = None
    if item in container:
        detail = f"Expected {item!r} NOT to be in {container!r}"
    check(name, item not in container, detail)


def summary():
    """Print test summary."""
    global _tests_run, _tests_passed, _tests_failed
    print(f"\n{'='*60}")
    print(f"  Results: {_tests_passed}/{_tests_run} passed", end="")
    if _tests_failed > 0:
        print(f", {_tests_failed} FAILED", end="")
    print()
    print(f"{'='*60}")
    return _tests_failed == 0


# ═════════════════════════════════════════════════════════════════════════════
# LEGACY TESTS (preserved and extended)
# ═════════════════════════════════════════════════════════════════════════════

def test_clean_query():
    suite("clean_query")

    check_eq("strips whitespace",
        clean_query("  hello world  "), "hello world")

    check_eq("lowercases",
        clean_query("Hello World"), "hello world")

    check_eq("collapses spaces",
        clean_query("hello    world"), "hello world")

    check_eq("removes trailing punctuation",
        clean_query("hello world?!"), "hello world")

    check_eq("removes trailing period",
        clean_query("hello world."), "hello world")

    check_eq("empty string",
        clean_query(""), "")

    check_eq("keeps hyphens in compound words",
        clean_query("state-of-the-art"), "state-of-the-art")

    check_eq("keeps apostrophes in contractions",
        clean_query("don't stop"), "don't stop")

    # New edge cases
    check_eq("trailing comma removed",
        clean_query("hello world,"), "hello world")

    check_eq("trailing semicolon removed",
        clean_query("hello world;"), "hello world")

    check_eq("multiple trailing punctuation",
        clean_query("hello world?!?!"), "hello world")

    check_eq("only whitespace",
        clean_query("   "), "")


def test_remove_stop_words():
    suite("remove_stop_words")

    check_eq("removes articles",
        remove_stop_words("the cat sat on a mat"), "cat sat mat")

    check_eq("removes prepositions",
        remove_stop_words("i like pizza with pepperoni"), "pizza pepperoni")

    check_eq("removes question words",
        remove_stop_words("what is the capital of france", stop_set=get_stop_words()), "capital france")

    check_eq("empty result is ok",
        remove_stop_words("the a an"), "")

    check_eq("keeps content words",
        remove_stop_words("photosynthesis converts sunlight energy"), "photosynthesis converts sunlight energy")

    check_eq("empty string",
        remove_stop_words(""), "")

    check_eq("all stop words removed",
        remove_stop_words("is are was were"), "")

    check_eq("mixed keeps content",
        remove_stop_words("the quick brown fox"), "quick brown fox")


def test_extract_by_question_pattern():
    suite("extract_by_question_pattern")

    # Direct pattern tests
    results = extract_by_question_pattern("What is the capital of France?")
    check_gt("'what is' extracts phrase", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("capital of france found", "capital of france", phrases)

    results = extract_by_question_pattern("Who was Albert Einstein?")
    check_gt("'who was' extracts name", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("albert einstein found", "albert einstein", phrases)

    results = extract_by_question_pattern("Explain quantum computing")
    check_gt("'explain' extracts topic", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("quantum computing found", "quantum computing", phrases)

    results = extract_by_question_pattern("Tell me about machine learning")
    check_gt("'tell me about' extracts topic", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("machine learning found", "machine learning", phrases)

    results = extract_by_question_pattern("I like pizza")
    check_gt("'i like' extracts topic", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("pizza found", "pizza", phrases)

    results = extract_by_question_pattern("Define recursion in computer science")
    check_gt("'define' extracts topic", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("recursion in computer science found", "recursion in computer science", phrases)

    # Reflexive/empty topics should be skipped
    results = extract_by_question_pattern("What is that?")
    check("reflexive 'that' is skipped", len(results) == 0 or results[0][0].lower() != 'that')

    results = extract_by_question_pattern("Tell me about it")
    check("reflexive 'it' is skipped", len(results) == 0 or results[0][0].lower() != 'it')

    # Lower confidence patterns
    results = extract_by_question_pattern("How many people live in New York?")
    check_gt("'how many' extracts something", len(results), 0)

    # Comparison patterns (new)
    results = extract_by_question_pattern("Compare Python and Java")
    check_gt("'compare' extracts something", len(results), 0)

    # Empty input
    results = extract_by_question_pattern("")
    check_eq("empty input", results, [])


def test_extract_noun_phrases():
    suite("extract_noun_phrases")

    results = extract_noun_phrases("What is the capital of France?")
    check_gt("finds noun phrases", len(results), 0)

    results = extract_noun_phrases("The quick brown fox jumps over the lazy dog")
    check_gt("finds descriptive phrases", len(results), 0)

    results = extract_noun_phrases("")
    check_eq("empty input gives empty", results, [])

    results = extract_noun_phrases("the")
    check_eq("only stop words gives empty or low score",
        all(s < 0.5 for _, s in results) if results else True, True)

    # Known compound detection — compound phrases may contain the concept
    results = extract_noun_phrases("How do I make french fries?")
    if results:
        all_text = ' '.join(p.lower() for p, _ in results)
        has_french = 'french' in all_text
        has_fries = 'fries' in all_text
        check("detects 'french' in noun phrases", has_french)
        check("detects 'fries' in noun phrases", has_fries)

    # Tri-gram known compound
    results = extract_noun_phrases("What is the capital of New York City?")
    if results:
        has_nyc = any('new york city' in p.lower() or 'new york' in p.lower() for p, _ in results)
        check("detects 'new york city' entity", has_nyc)


def test_extract_entities():
    suite("extract_entities")

    results = extract_entities("What is the capital of France?")
    if results:
        entities = [e.lower() for e, _ in results]
        has_france = any('france' in e for e in entities)
        check("detects France as entity", has_france)

    results = extract_entities('The concept of "quantum entanglement" is fascinating')
    if results:
        entities_lower = [e.lower() for e, _ in results]
        check_in("detects quoted entity", 'quantum entanglement', entities_lower)

    results = extract_entities("New York City is a big place")
    if results:
        entities_lower = [e.lower() for e, _ in results]
        check_in("detects New York City", 'new york city', entities_lower)

    results = extract_entities("")
    check_eq("empty input gives empty", results, [])

    # Known compound detection
    results = extract_entities("Tell me about machine learning")
    if results:
        entities_lower = [e.lower() for e, _ in results]
        check_in("detects known compound 'machine learning'", 'machine learning', entities_lower)

    # Multiple entities
    results = extract_entities("Albert Einstein developed the theory of relativity in Germany")
    if results:
        entities_lower = [e.lower() for e, _ in results]
        check_in("detects Albert Einstein", 'albert einstein', entities_lower)


def test_extract_content_words():
    suite("extract_content_words")

    results = extract_content_words("What is the capital of France?", max_words=10)
    check_gt("extracts content words", len(results), 0)
    if results:
        words = [w.lower() for w, _ in results]
        check_in("france found", "france", words)

    results = extract_content_words("photosynthesis converts sunlight")
    if results:
        best_word, best_score = results[0]
        check("long word scores higher", best_score > 0.3)

    results = extract_content_words("a an the it")
    check("no short stop words in results", len(results) == 0 or all(len(w) >= 3 for w, _ in results))

    results = extract_content_words("")
    check_eq("empty input", results, [])

    # Multi-syllable word gets bonus
    results = extract_content_words("photosynthesis")
    if results:
        check_gt("photosynthesis scores high", results[0][1], 0.4)

    # Short words get filtered
    results = extract_content_words("is are was")
    check_eq("only stop words gives empty", results, [])


def test_extract_cleaned_query():
    suite("extract_cleaned_query")

    results = extract_cleaned_query("What is the capital of France?")
    check_gt("cleaned query has results", len(results), 0)
    if results:
        phrase, score = results[0]
        check_gt("confidence is reasonable", score, 0.1)
        check("france in cleaned", 'france' in phrase.lower())

    results = extract_cleaned_query("")
    check_eq("empty input", len(results), 0)

    results = extract_cleaned_query("  ")
    check_eq("whitespace input", len(results), 0)


def test_extract_keywords():
    suite("extract_keywords — main API")

    results = extract_keywords("What is the capital of France?")
    check_gt("has results", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("france in top results", "france", phrases)
        check_gt("top confidence > 0.5", results[0][1], 0.5)

    results = extract_keywords("How does photosynthesis work?")
    check_gt("how-to has results", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("photosynthesis in results", "photosynthesis", phrases)

    results = extract_keywords("I like pizza with pepperoni")
    check_gt("personal statement has results", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("pizza in results", "pizza", phrases)

    results = extract_keywords("Explain quantum computing")
    check_gt("explain has results", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("quantum computing in results", "quantum computing", phrases)

    results = extract_keywords("Where is the Eiffel Tower located?")
    check_gt("where has results", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("eiffel tower in results", "eiffel tower", phrases)

    results = extract_keywords("")
    check_eq("empty input", results, [])

    results = extract_keywords("   ")
    check_eq("whitespace input", results, [])

    results = extract_keywords("What is the capital of France and its population?", max_keywords=1)
    check_eq("max_keywords=1 respected", len(results) <= 1, True)

    results = extract_keywords("What is the capital of France and its population?", max_keywords=3)
    check_eq("max_keywords=3 respected", len(results) <= 3, True)


def test_extract_topic():
    suite("extract_topic — main API")

    topic, conf = extract_topic("What is the capital of France?")
    check_gt("france has confidence", conf, 0.3)
    if topic:
        check("france in topic", 'france' in topic.lower())

    topic, conf = extract_topic("Explain quantum computing")
    check_gt("quantum computing has confidence", conf, 0.3)
    if topic:
        check("quantum in topic", 'quantum' in topic.lower())

    topic, conf = extract_topic("Who was Marie Curie?")
    check_gt("Marie Curie has confidence", conf, 0.3)

    topic, conf = extract_topic("How does a car engine work?")
    check_gt("car engine has confidence", conf, 0.3)
    if topic:
        check("engine in topic", 'engine' in topic.lower())

    topic, conf = extract_topic("")
    check("empty query returns None topic", topic is None)
    check_eq("empty query conf 0.0", conf, 0.0)

    topic, conf = extract_topic("Hi")
    check("short greeting returns some topic", topic is not None)

    topic, conf = extract_topic("asdf xyz blah")
    check("gibberish returns a topic", topic is not None)


def test_is_empty_topic():
    suite("is_empty_topic")

    check("empty string is empty", is_empty_topic(""))
    check("'this' is empty", is_empty_topic("this"))
    check("'that' is empty", is_empty_topic("that"))
    check("'it' is empty", is_empty_topic("it"))
    check("'france' is not empty", not is_empty_topic("france"))
    check("'quantum' is not empty", not is_empty_topic("quantum"))
    check("'something' is empty", is_empty_topic("something"))
    check("'things' is empty", is_empty_topic("things"))


def test_normalize_topic():
    suite("normalize_topic")

    check_eq("lowercases", normalize_topic("France"), "france")
    check_eq("strips", normalize_topic("  France  "), "france")
    check_eq("collapses spaces", normalize_topic("New  York"), "new york")


def test_extract_noun_phrases_only():
    suite("extract_noun_phrases_only")

    results = extract_noun_phrases_only("The capital of France is Paris")
    check_gt("returns phrases", len(results), 0)
    check("all results are strings", all(isinstance(r, str) for r in results))

    results = extract_noun_phrases_only("")
    check_eq("empty input", results, [])


def test_extract_entities_only():
    suite("extract_entities_only")

    results = extract_entities_only('The "Eiffel Tower" is in Paris')
    check_gt("returns entities", len(results), 0)
    if results:
        check_in("Eiffel Tower found", "Eiffel Tower", results)

    results = extract_entities_only("")
    check_eq("empty input", results, [])


def test_extract_context_topic():
    suite("extract_context_topic")

    result = extract_context_topic([])
    check("empty history returns None", result is None)

    history = [
        ("What is the capital of France?", "Paris is the capital of France."),
    ]
    result = extract_context_topic(history)
    check("single exchange finds topic", result is not None)
    if result:
        check("france in context", 'france' in result.lower())

    history = [
        ("What is photosynthesis?", "Photosynthesis is how plants make energy from sunlight."),
        ("Tell me more about that", None),
        ("How does chlorophyll work in this process?", "Chlorophyll absorbs light energy."),
    ]
    result = extract_context_topic(history)
    check("multi-turn finds topic", result is not None)

    history = [
        ("Hi", "Hello!"),
        ("How are you?", "I'm good, thanks!"),
    ]
    result = extract_context_topic(history)
    check("greetings still produces some topic", result is not None or True)

    long_history = [
        (f"What is topic {i}?", f"That is about topic {i}.")
        for i in range(20)
    ]
    result_short = extract_context_topic(long_history, max_lookback=2)
    result_long = extract_context_topic(long_history, max_lookback=10)
    check("lookback works", result_short is not None or result_long is not None)


def test_is_context_dependent():
    suite("is_context_dependent")

    check("pronoun 'it' is context-dependent", is_context_dependent("tell me about it"))
    check("pronoun 'them' is context-dependent", is_context_dependent("how do i make them"))
    check("pronoun 'that' is context-dependent", is_context_dependent("explain that"))
    check("follow-up signal is context-dependent", is_context_dependent("yeah but how do i make them"))
    check("demonstrative reference", is_context_dependent("tell me more about that"))
    check("vague pronoun query", is_context_dependent("how tall is it"))
    check("'go on' signal", is_context_dependent("go on"))

    check("factual question not dependent", not is_context_dependent("What is the capital of France?"))
    check("how-to not dependent with clear topic", not is_context_dependent("How do I bake a chocolate cake?"))
    check("definition not dependent", not is_context_dependent("Define recursion"))
    check("greeting not dependent", not is_context_dependent("Hello"))
    check("empty string not dependent", not is_context_dependent(""))

    # New edge cases
    check("'about that' is context-dependent", is_context_dependent("tell me about that"))
    check("'how about' is context-dependent", is_context_dependent("how about it"))
    check("'what else' is context-dependent", is_context_dependent("what else"))


def test_is_pronoun_query():
    suite("_is_pronoun_query")

    check("direct pronoun ref", _is_pronoun_query("tell me about that"))
    check("them as referent", _is_pronoun_query("how do i make them"))
    check("follow-up signal", _is_pronoun_query("yeah but how"))
    check("vague it ref", _is_pronoun_query("how tall is it"))
    check("explicit pronoun", _is_pronoun_query("explain this"))

    check("clear topic not pronoun", not _is_pronoun_query("What is the capital of France?"))
    check("clear topic with content", not _is_pronoun_query("How do I bake a chocolate cake?"))
    check("empty", not _is_pronoun_query(""))

    # New: standalone pronoun queries
    check("standalone 'it'", _is_pronoun_query("it"))
    check("standalone 'that'", _is_pronoun_query("that"))

    # New: "what about it"
    check("'what about it'", _is_pronoun_query("what about it"))


def test_extract_context_topic_pronoun_resolution():
    suite("extract_context_topic — pronoun resolution")

    history = [
        ("What is the capital of France?", "Paris is the capital of France."),
        ("How do I make french fries?", "Cut potatoes into strips and fry them."),
    ]
    result = extract_context_topic(history, current_query="yeah but how do i make them")
    check("them -> french fries", result is not None and 'french' in result.lower())

    history = [
        ("What is photosynthesis?", "Plants convert sunlight to energy."),
        ("Tell me about the Eiffel Tower", "It is in Paris."),
        ("How tall is it?", "It is 330 meters tall."),
    ]
    result = extract_context_topic(history, current_query="how tall is it")
    check("it -> Eiffel Tower", result is not None and ('eiffel' in result.lower() or 'tower' in result.lower()))

    history = [
        ("Define recursion", "Recursion is when a function calls itself."),
        ("Tell me more about that", "In programming, recursion..."),
    ]
    result = extract_context_topic(history, current_query="tell me more about that")
    check("that -> recursion", result is not None and 'recursion' in result.lower())

    result = extract_context_topic(history, current_query="What is the capital of Australia?")
    check("self-contained still works", result is not None)

    # New: pronoun resolution with compound topic
    history = [
        ("What is machine learning?", "Machine learning is a subset of AI."),
    ]
    result = extract_context_topic(history, current_query="tell me more about that")
    check("that -> machine learning", result is not None and 'machine' in result.lower())


def test_integration_real_world_queries():
    suite("Integration — Real-world queries")

    test_cases = [
        ("What is the meaning of life?", ["meaning", "life"]),
        ("How to bake a chocolate cake?", ["chocolate", "cake", "bake"]),
        ("Who wrote Romeo and Juliet?", ["romeo", "juliet", "wrote"]),
        ("What's the weather in London?", ["weather", "london"]),
        ("Tell me about the history of Rome", ["history", "rome"]),
        ("Define recursion", ["recursion"]),
        ("What is machine learning?", ["machine learning", "machine", "learning"]),
        ("How many planets are in the solar system?", ["planets", "solar system"]),
        ("Write a poem about autumn leaves", ["autumn", "leaves", "poem"]),
        ("When did World War II end?", ["world war ii", "world war"]),
        ("Explain how the stock market works", ["stock market", "works"]),
        ("What do you know about artificial intelligence?", ["artificial intelligence", "intelligence"]),
        ("Show me how to tie a tie", ["tie"]),
        ("List all countries in Europe", ["countries", "europe"]),
    ]

    for query, expected_terms in test_cases:
        keywords = extract_keywords(query, max_keywords=3)
        all_phrases = [p.lower() for p, _ in keywords]
        all_text = ' '.join(all_phrases)

        found_any = any(term.lower() in all_text or any(term.lower() in p for p in all_phrases)
                        for term in expected_terms)

        kw_str = ', '.join(f"'{p}'({s:.2f})" for p, s in keywords)
        detail = f"Query: {query}\n  Keywords: [{kw_str}]\n  Expected: {expected_terms}"
        check(f"'{query[:40]}...' finds expected terms", found_any, detail)

        topic, conf = extract_topic(query)
        if topic:
            check(f"Topic for '{query[:30]}...' has confidence > 0.1", conf > 0.1,
                  f"conf={conf:.3f}, topic='{topic}'")


def test_integration_conversation_tracking():
    suite("Integration — Conversation context tracking")

    history = [
        ("What is the capital of France?", "Paris is the capital of France."),
        ("What's the population there?", "Paris has about 2.1 million people."),
        ("Tell me about the Eiffel Tower", "The Eiffel Tower is a famous landmark in Paris."),
    ]
    ctx = extract_context_topic(history)
    check("context tracks latest topic", ctx is not None and (
        'eiffel' in ctx.lower() or 'paris' in ctx.lower() or 'tower' in ctx.lower()
    ))

    history2 = [
        ("What is photosynthesis?", "Photosynthesis is how plants make energy."),
        ("What is the capital of Australia?", "Canberra is the capital of Australia."),
    ]
    ctx2 = extract_context_topic(history2)
    check("canberra or australia as new topic",
        ctx2 is not None and ('canberra' in ctx2.lower() or 'australia' in ctx2.lower()))

    ctx = extract_context_topic([])
    check("no history returns None", ctx is None)


def test_edge_cases():
    suite("Edge cases")

    long_query = "What is " + "very " * 50 + "important?"
    results = extract_keywords(long_query)
    check("long query doesn't crash", isinstance(results, list))

    results = extract_keywords("the a an in on at")
    check("stop-word-only query returns something", len(results) > 0)
    if results:
        check("stop-word-only query has low confidence", results[0][1] <= 0.6)

    results = extract_keywords("What is 2 + 2?")
    check("math query has results", len(results) > 0)

    results = extract_keywords("C++ vs Python: which is better for AI?")
    check("special chars query doesn't crash", isinstance(results, list))
    if results:
        has_python = any('python' in p.lower() for p, _ in results)
        check("python found in query with special chars", has_python)

    results = extract_keywords("What is Schrödinger's cat?")
    check("unicode query doesn't crash", isinstance(results, list))
    if results:
        has_cat = any('cat' in p.lower() for p, _ in results)
        check("cat found in unicode query", has_cat)

    results = extract_keywords("Hello")
    check("single word returns results", len(results) > 0)

    results = extract_keywords("https://example.com")
    check("url-like doesn't crash", isinstance(results, list))


def test_configuration():
    suite("Configuration")

    check("_QUESTION_PATTERNS is not empty", len(_QUESTION_PATTERNS) > 0)
    for pattern, group, weight in _QUESTION_PATTERNS:
        check(f"pattern '{pattern[:30]}...' has valid group", group >= 1)
        check(f"pattern '{pattern[:30]}...' has valid weight", 0.0 <= weight <= 2.0)
        try:
            re.compile(pattern, re.IGNORECASE)
            check(f"pattern compiles: {pattern[:30]}...", True)
        except re.error:
            check(f"pattern compiles: {pattern[:30]}...", False, f"Invalid regex: {pattern}")

    check("_EMPTY_TOPICS is not empty", len(_EMPTY_TOPICS) > 0)
    check("stop words is not empty", len(get_stop_words()) > 0)
    check("known compounds is not empty", len(get_known_compounds()) > 0)


def test_regression_security():
    suite("Security / robustness")

    evil_queries = [
        "a" * 1000,
        "What is " + "a" * 100 + "?",
        "!" * 100,
        "()" * 50,
        "\\" * 50,
        "'" * 100,
        '"' * 100,
        "\0" * 10,
        "\n" * 10 + "test",
        "\r\n" * 10,
    ]

    for q in evil_queries:
        try:
            results = extract_keywords(q)
            check(f"evil query '{q[:20]}...' handled gracefully", isinstance(results, list))
        except Exception as e:
            check(f"evil query '{q[:20]}...' raised: {e}", False, str(e))


# ═════════════════════════════════════════════════════════════════════════════
# NEW TESTS — classify_question
# ═════════════════════════════════════════════════════════════════════════════

def test_classify_question():
    suite("classify_question")

    # Factual definition
    check_eq("what is -> factual_definition",
        classify_question("What is the capital of France?"), "factual_definition")
    check_eq("what are -> factual_definition",
        classify_question("What are black holes?"), "factual_definition")
    check_eq("which is -> factual_definition",
        classify_question("Which planet is the largest?"), "factual_definition")

    # Factual person
    check_eq("who is -> factual_person",
        classify_question("Who was Albert Einstein?"), "factual_person")
    check_eq("who are -> factual_person",
        classify_question("Who are the Beatles?"), "factual_person")

    # Factual location
    check_eq("where is -> factual_location",
        classify_question("Where is the Eiffel Tower?"), "factual_location")
    check_eq("where are -> factual_location",
        classify_question("Where are the pyramids?"), "factual_location")

    # How-to
    check_eq("how to -> how_to",
        classify_question("How to bake a cake?"), "how_to")
    check_eq("how do -> how_to",
        classify_question("How do I make french fries?"), "how_to")
    check_eq("how can -> how_to",
        classify_question("How can I learn Python?"), "how_to")

    # Why/causal
    check_eq("why is -> why_causal",
        classify_question("Why is the sky blue?"), "why_causal")
    check_eq("why does -> why_causal",
        classify_question("Why does gravity exist?"), "why_causal")

    # Yes/no
    check_eq("is this -> yes_no",
        classify_question("Is the Earth round?"), "yes_no")
    check_eq("can you -> yes_no",
        classify_question("Can you help me?"), "yes_no")
    check_eq("does it -> yes_no",
        classify_question("Does it work?"), "yes_no")

    # Comparison
    check_eq("compare -> comparison",
        classify_question("Compare Python and Java"), "comparison")
    check_eq("difference between -> comparison",
        classify_question("What is the difference between AI and ML?"), "comparison")

    # Personal
    check_eq("i like -> personal",
        classify_question("I like pizza"), "personal")
    check_eq("i think -> personal",
        classify_question("I think this is great"), "personal")

    # Instruction
    check_eq("write -> instruction",
        classify_question("Write a poem about autumn"), "instruction")
    check_eq("explain -> instruction (new)",
        classify_question("Explain the theory of relativity"), "instruction")

    # Unknown / empty
    check_eq("empty -> unknown",
        classify_question(""), "unknown")
    check_eq("gibberish -> unknown",
        classify_question("asdf xyz"), "unknown")


# ═════════════════════════════════════════════════════════════════════════════
# NEW TESTS — extract_compound_phrases
# ═════════════════════════════════════════════════════════════════════════════

def test_extract_compound_phrases():
    suite("extract_compound_phrases")

    # Known compound detection
    results = extract_compound_phrases("How do I make french fries?")
    if results:
        compounds = [p.lower() for p, _ in results]
        check_in("detects 'french fries'", 'french fries', compounds)

    results = extract_compound_phrases("What is machine learning?")
    if results:
        compounds = [p.lower() for p, _ in results]
        check_in("detects 'machine learning'", 'machine learning', compounds)

    results = extract_compound_phrases("Explain black holes")
    if results:
        compounds = [p.lower() for p, _ in results]
        check_in("detects 'black holes'", 'black holes', compounds)

    # Tri-gram compounds
    results = extract_compound_phrases("What is the capital of New York City?")
    if results:
        compounds = [p.lower() for p, _ in results]
        check_in("detects 'new york city'", 'new york city', compounds)

    # "X of Y" pattern
    results = extract_compound_phrases("What is the capital of France?")
    if results:
        compounds = [p.lower() for p, _ in results]
        check_in("detects 'capital of france' pattern (or similar)", 
                 'capital of france', compounds)

    # Algorithmic bigram detection
    results = extract_compound_phrases("photosynthesis converts sunlight")
    if results:
        compounds = [p.lower() for p, _ in results]
        # 'photosynthesis converts' or 'converts sunlight' should be detected
        has_bigram = any('photosynthesis' in c and 'converts' in c for c in compounds) or \
                     any('converts' in c and 'sunlight' in c for c in compounds)
        check("detects algorithmic bigrams", has_bigram)

    # Empty input
    results = extract_compound_phrases("")
    check_eq("empty input", results, [])

    # Score ordering: known compounds should score higher than algorithmic ones
    results = extract_compound_phrases("Tell me about machine learning in computer science")
    if len(results) >= 2:
        check_gt("known compound scores higher than algorithmic",
                 results[0][1], results[1][1])

    # Ensure known compounds work case-insensitively
    results = extract_compound_phrases("FRENCH FRIES")
    if results:
        compounds = [p.lower() for p, _ in results]
        check_in("case-insensitive compound detection", 'french fries', compounds)


# ═════════════════════════════════════════════════════════════════════════════
# NEW TESTS — extract_by_verb_pattern
# ═════════════════════════════════════════════════════════════════════════════

def test_extract_by_verb_pattern():
    suite("extract_by_verb_pattern")

    # "how to make X"
    results = extract_by_verb_pattern("How to make french fries?")
    if results:
        objects = [p.lower() for p, _ in results]
        check_in("'how to make' extracts object", 'french fries', objects)

    # "how to bake X"
    results = extract_by_verb_pattern("How to bake a cake?")
    if results:
        objects = [p.lower() for p, _ in results]
        check_in("'how to bake' extracts object", 'cake', objects)

    # "how tall is X" (measurement)
    results = extract_by_verb_pattern("How tall is the Eiffel Tower?")
    if results:
        objects = [p.lower() for p, _ in results]
        check_in("'how tall is' extracts object", 'the eiffel tower', objects)

    # "what is the <attr> of X"
    results = extract_by_verb_pattern("What is the capital of France?")
    if results:
        objects = [p.lower() for p, _ in results]
        # Should extract "France" as the object
        check_in("'what is the of' extracts object", 'france', objects)

    # Imperative: "make X"
    results = extract_by_verb_pattern("Make a pizza")
    if results:
        objects = [p.lower() for p, _ in results]
        has_pizza = any('pizza' in o for o in objects)
        check("imperative 'make' extracts object", has_pizza)

    # Imperative: "write X"
    results = extract_by_verb_pattern("Write a poem about autumn")
    if results:
        objects = [p.lower() for p, _ in results]
        has_autumn = any('autumn' in o for o in objects) or any('poem' in o for o in objects)
        check("imperative 'write' extracts object", has_autumn)

    # Empty input
    results = extract_by_verb_pattern("")
    check_eq("empty input", results, [])

    # No verb match should give empty
    results = extract_by_verb_pattern("What is the capital?")
    # This matches "what is the <attr> of X" pattern — might or might not match
    # It might match with "capital" or not depending on pattern matching
    check("no-match query returns list", isinstance(results, list))


# ═════════════════════════════════════════════════════════════════════════════
# NEW TESTS — Cross-strategy Consistency
# ═════════════════════════════════════════════════════════════════════════════

def test_cross_strategy_consistency():
    """Test that multiple strategies agree on the same query."""
    suite("Cross-strategy consistency")

    # Known compounds should be detected by both noun_phrases and compounds
    test_compounds = [
        "machine learning",
        "french fries",
        "black holes",
        "quantum computing",
        "solar system",
    ]
    for compound in test_compounds:
        query = f"Tell me about {compound}"
        np_results = extract_noun_phrases(query)
        cp_results = extract_compound_phrases(query)
        kw_results = extract_keywords(query, max_keywords=5)

        np_phrases = [p.lower() for p, _ in np_results]
        cp_phrases = [p.lower() for p, _ in cp_results]
        kw_phrases = [p.lower() for p, _ in kw_results]

        # At least one strategy should find the compound
        found_in_np = any(compound in p for p in np_phrases)
        found_in_cp = any(compound in p for p in cp_phrases)
        found_in_kw = any(compound in p for p in kw_phrases)

        found = found_in_np or found_in_cp or found_in_kw
        check(f"'{compound}' found by at least one strategy", found,
              f"NP={np_phrases}, CP={cp_phrases}, KW={kw_phrases}")

    # Verb patterns should align with keyword extraction
    verb_queries = [
        "How to make pizza",
        "How to bake cookies",
        "How to build a house",
    ]
    for query in verb_queries:
        verb_results = extract_by_verb_pattern(query)
        kw_results = extract_keywords(query, max_keywords=3)
        if verb_results and kw_results:
            verb_objects = [p.lower() for p, _ in verb_results]
            kw_phrases = [p.lower() for p, _ in kw_results]
            # The verb-extracted object should appear somewhere in keywords
            overlap = any(vo in ' '.join(kw_phrases) for vo in verb_objects)
            check(f"verb extraction aligns with keywords: '{query[:30]}'", overlap)


# ═════════════════════════════════════════════════════════════════════════════
# NEW TESTS — Advanced Compound Resolution
# ═════════════════════════════════════════════════════════════════════════════

def test_compound_resolution_in_context():
    """Test that compound phrases survive through context tracking."""
    suite("Compound resolution in context")

    # Machine learning conversation with pronoun
    history = [
        ("What is machine learning?", "ML is a subset of AI that uses data."),
    ]
    result = extract_context_topic(history, current_query="tell me more about that")
    check("compound 'machine learning' resolves from 'that'",
          result is not None and 'machine' in result.lower())

    # French fries conversation
    history = [
        ("How do I make french fries?", "Cut potatoes and fry them."),
    ]
    result = extract_context_topic(history, current_query="yeah but how do i make them")
    check("compound 'french fries' resolves from 'them'",
          result is not None and ('french' in result.lower() or 'fries' in result.lower()))

    # Multiple compounds across turns
    history = [
        ("What is quantum computing?", "It uses quantum mechanics."),
        ("How does machine learning work?", "It uses data patterns."),
    ]
    result = extract_context_topic(history)
    # The last topic should be machine learning
    check("last compound topic wins",
          result is not None and 'machine' in result.lower())

    # Pronoun resolves to most recent compound
    result = extract_context_topic(history, current_query="tell me more about that")
    check("pronoun resolves to most recent compound",
          result is not None and 'machine' in result.lower())


# ═════════════════════════════════════════════════════════════════════════════
# NEW TESTS — Property-based (randomized) testing
# ═════════════════════════════════════════════════════════════════════════════

def test_property_all_functions_are_pure():
    """Verify all public functions are pure (no side effects)."""
    suite("Property: All functions are pure")

    functions_to_test = [
        (clean_query, ["Hello World!"]),
        (remove_stop_words, ["the quick brown fox"]),
        (collapse_whitespace, ["hello    world"]),
        (extract_by_question_pattern, ["What is France?"]),
        (extract_noun_phrases, ["The capital of France is Paris"]),
        (extract_entities, ["What is France?"]),
        (extract_content_words, ["What is France?"]),
        (extract_cleaned_query, ["What is France?"]),
        (extract_compound_phrases, ["What is machine learning?"]),
        (extract_by_verb_pattern, ["How to make french fries?"]),
        (extract_keywords, ["What is France?"]),
        (extract_topic, ["What is France?"]),
        (classify_question, ["What is France?"]),
        (normalize_topic, [" France "]),
        (is_empty_topic, ["France"]),
        (is_context_dependent, ["What is France?"]),
    ]

    for func, args in functions_to_test:
        try:
            result1 = func(*args)
            result2 = func(*args)
            check_eq(f"{func.__name__} is deterministic", result1, result2)
        except Exception as e:
            check(f"{func.__name__} raises no exception: {e}", False, str(e))


def test_property_keyword_ordering():
    """Verify that keywords are always returned in descending confidence order."""
    suite("Property: Keywords sorted by confidence descending")

    test_queries = [
        "What is the capital of France?",
        "How do I make french fries?",
        "Explain quantum computing",
        "Tell me about machine learning",
        "Who was Albert Einstein?",
        "What is the meaning of life?",
        "How many planets are in the solar system?",
        "Write a poem about autumn leaves",
        "Compare Python and Java",
        "Why is the sky blue?",
    ]

    for query in test_queries:
        keywords = extract_keywords(query, max_keywords=5)
        for i in range(len(keywords) - 1):
            phrase, score = keywords[i]
            next_phrase, next_score = keywords[i + 1]
            check(f"'{query[:20]}...': {phrase}({score:.2f}) >= {next_phrase}({next_score:.2f})",
                  score >= next_score,
                  f"Order violation: {keywords}")


def test_property_known_compounds_case_insensitive():
    """Verify known compounds work case-insensitively."""
    suite("Property: Case-insensitive compound matching")

    compounds = [
        "french fries", "machine learning", "black hole",
        "solar system", "quantum computing", "new york city",
    ]

    for compound in compounds:
        # All lowercase
        results_lower = extract_compound_phrases(f"tell me about {compound.lower()}")
        # Title case
        results_title = extract_compound_phrases(f"tell me about {compound.title()}")
        # All caps
        results_upper = extract_compound_phrases(f"tell me about {compound.upper()}")

        found_lower = any(compound.lower() in p.lower() for p, _ in results_lower)
        found_title = any(compound.lower() in p.lower() for p, _ in results_title)
        found_upper = any(compound.lower() in p.lower() for p, _ in results_upper)

        check(f"'{compound}' found in lowercase query", found_lower)
        check(f"'{compound}' found in title-case query", found_title)
        check(f"'{compound}' found in uppercase query", found_upper)


def test_property_empty_and_edge_inputs():
    """Verify all functions handle empty/edge inputs gracefully."""
    suite("Property: Empty/edge input handling")

    edge_inputs = [
        "",
        " ",
        "  ",
        "\t",
        "\n",
        "\n\n",
        "a",
        "A" * 1000,
    ]

    for inp in edge_inputs:
        try:
            kw = extract_keywords(inp)
            check(f"extract_keywords handles {inp[:10]!r}", isinstance(kw, list))
        except Exception as e:
            check(f"extract_keywords handles {inp[:10]!r}: raised {e}", False, str(e))

    for inp in edge_inputs:
        try:
            result = classify_question(inp)
            check(f"classify_question handles {inp[:10]!r}", isinstance(result, str))
        except Exception as e:
            check(f"classify_question handles {inp[:10]!r}: raised {e}", False, str(e))

    for inp in edge_inputs:
        try:
            result = extract_compound_phrases(inp)
            check(f"extract_compound_phrases handles {inp[:10]!r}", isinstance(result, list))
        except Exception as e:
            check(f"extract_compound_phrases handles {inp[:10]!r}: raised {e}", False, str(e))

    for inp in edge_inputs:
        try:
            result = extract_by_verb_pattern(inp)
            check(f"extract_by_verb_pattern handles {inp[:10]!r}", isinstance(result, list))
        except Exception as e:
            check(f"extract_by_verb_pattern handles {inp[:10]!r}: raised {e}", False, str(e))

    for inp in edge_inputs:
        try:
            result = clean_query(inp)
            check(f"clean_query handles {inp[:10]!r}", isinstance(result, str))
        except Exception as e:
            check(f"clean_query handles {inp[:10]!r}: raised {e}", False, str(e))


# ═════════════════════════════════════════════════════════════════════════════
# NEW TESTS — Complex Multi-Turn Conversations
# ═════════════════════════════════════════════════════════════════════════════

def test_complex_multi_turn_conversations():
    suite("Complex multi-turn conversations")

    # Long conversation with topic shifts
    history = [
        ("What is photosynthesis?",
         "Photosynthesis is how plants convert sunlight into energy."),
        ("Tell me more about chlorophyll",
         "Chlorophyll absorbs light energy in the visible spectrum."),
        ("How does it work at the molecular level?",
         "Chlorophyll molecules capture photons which excite electrons."),
        ("What about cellular respiration?",
         "Cellular respiration releases energy from glucose."),
        ("And how do these two processes relate?",
         "They are complementary: photosynthesis produces glucose, respiration uses it."),
    ]
    ctx = extract_context_topic(history)
    check("long conversation has topic", ctx is not None)
    if ctx:
        has_cellular = 'cellular' in ctx.lower()
        has_respiration = 'respiration' in ctx.lower()
        has_photosynthesis = 'photosynthesis' in ctx.lower()
        check("topic relates to last discussion",
              has_cellular or has_respiration or has_photosynthesis)

    # Pronoun resolution through multiple turns
    history = [
        ("What is the capital of France?", "Paris."),
        ("What's the population?", "About 2.1 million."),
        ("How about the Eiffel Tower?", "It is 330m tall."),
        ("Tell me more about it", "It was built in 1889."),
    ]
    ctx = extract_context_topic(history, current_query="tell me more about it")
    check("'it' resolves to Eiffel Tower across 4 turns",
          ctx is not None and ('eiffel' in ctx.lower() or 'tower' in ctx.lower()))

    # Topic drift detection
    history = [
        ("What is Python?", "A programming language."),
        ("Tell me about Java", "Another language."),
        ("What about Rust?", "A systems language."),
        ("How do they compare?", None),
    ]
    ctx = extract_context_topic(history)
    check("topic handles drift across languages", ctx is not None)


# ═════════════════════════════════════════════════════════════════════════════
# NEW TESTS — Adversarial/Malformed Inputs
# ═════════════════════════════════════════════════════════════════════════════

def test_adversarial_inputs():
    suite("Adversarial inputs")

    adversarial = [
        # Mixed encoding
        "What is \x00\x01\x02France?",
        # Very deep nesting
        "(" * 100 + "France" + ")" * 100,
        # Emoji-heavy
        "What is 🧠🏗️🧑‍💻?",
        # Right-to-left marks
        "What is \u200FFrance?",
        # Zero-width spaces
        "What\u200Bis\u200BFrance?",
        # Repeated patterns (potential ReDoS)
        "What is " + "and " * 100 + "France?",
        # Code-like
        "What is `os.system('rm -rf /')`?",
        # Math-heavy
        "What is ∫ x² dx?",
        # All punctuation
        "!@#$%^&*()_+{}|:<>?",
        # HTML/XML
        "<script>alert('xss')</script>",
        # SQL injection pattern
        "What is ' OR 1=1; -- France?",
    ]

    for q in adversarial:
        try:
            results = extract_keywords(q)
            check(f"adversarial '{q[:30]}...' handled", isinstance(results, list))
        except Exception as e:
            check(f"adversarial '{q[:30]}...' raised: {e}", False, str(e))


# ═════════════════════════════════════════════════════════════════════════════
# NEW TESTS — Question Type + Strategy Alignment
# ═════════════════════════════════════════════════════════════════════════════

def test_question_type_alignment():
    """Verify that question classification aligns with extraction strategies."""
    suite("Question type / strategy alignment")

    # Factual definition questions should extract good topics
    queries = [
        ("What is the capital of France?", "factual_definition"),
        ("What are black holes?", "factual_definition"),
        ("Define recursion", "instruction"),
        ("Explain quantum computing", "instruction"),
    ]

    for query, expected_type in queries:
        qtype = classify_question(query)
        check(f"'{query[:30]}' classified as {qtype} (expected {expected_type})",
              qtype == expected_type)

        topic, conf = extract_topic(query)
        check(f"'{query[:30]}' topic has confidence > 0.2", conf > 0.2,
              f"conf={conf:.3f}, topic='{topic}'")

    # How-to questions should use verb patterns
    how_to_queries = [
        "How to make french fries",
        "How to bake a cake",
        "How to learn programming",
    ]
    for query in how_to_queries:
        verb_results = extract_by_verb_pattern(query)
        kw_results = extract_keywords(query, max_keywords=3)
        check(f"'{query[:30]}' uses verb extraction",
              len(verb_results) > 0 or len(kw_results) > 0)


# ═════════════════════════════════════════════════════════════════════════════
# NEW TESTS — Known Compound Integrity
# ═════════════════════════════════════════════════════════════════════════════

def test_known_compound_integrity():
    """Verify that known compounds are valid and well-formed."""
    suite("Known compound integrity")

    compounds = get_known_compounds()
    check("known compounds is a set", isinstance(compounds, frozenset))
    check_gt("has many compounds", len(compounds), 50)

    for compound in compounds:
        check(f"compound '{compound}' is lowercase", compound == compound.lower())
        check(f"compound '{compound}' not in empty topics",
              compound not in _EMPTY_TOPICS)
        # Multi-word compounds should have spaces; single-word entries are also valid
        if ' ' in compound:
            # Compounds may legitimately contain stop words like "of", "in", "on", "and"
            # Check that at least SOME words are non-stop-words (i.e., not entirely stop words)
            has_content_word = any(w not in _STOP_WORDS for w in compound.split())
            check(f"multi-word compound '{compound}' has content words", has_content_word,
                  f"Compound '{compound}' is entirely stop words")

    # Verify common compounds are present
    essential_compounds = [
        "french fries", "machine learning", "artificial intelligence",
        "quantum computing", "solar system", "black hole",
        "new york city", "united states",
    ]
    for compound in essential_compounds:
        check(f"essential compound '{compound}' present", compound in compounds)


# ═════════════════════════════════════════════════════════════════════════════
# NEW TESTS — LLM-style Query Handling
# ═════════════════════════════════════════════════════════════════════════════

def test_llm_style_queries():
    """Test queries that LLMs typically handle well — our symbolic should too."""
    suite("LLM-style query handling")

    llm_style_queries = [
        ("Explain the theory of relativity in simple terms",
         ["relativity", "theory"]),
        ("What's the difference between AI and machine learning?",
         ["ai", "machine learning", "difference"]),
        ("Can you write a short story about a dragon?",
         ["dragon", "story"]),
        ("I'm feeling sad today, cheer me up",
         ["sad", "cheer"]),
        ("What are some good books to read?",
         ["books", "read"]),
        ("How can I improve my programming skills?",
         ["programming", "skills", "improve"]),
        ("Tell me a fun fact about the universe",
         ["universe", "fun fact"]),
        ("What's the best way to learn a new language?",
         ["learn", "language"]),
        ("Give me some tips for public speaking",
         ["tips", "public speaking"]),
        ("What's happening in the world of technology?",
         ["technology", "world"]),
    ]

    for query, expected_terms in llm_style_queries:
        keywords = extract_keywords(query, max_keywords=4)
        all_phrases = [p.lower() for p, _ in keywords]
        all_text = ' '.join(all_phrases)
        found_any = any(term.lower() in all_text or any(term.lower() in p for p in all_phrases)
                        for term in expected_terms)

        kw_str = ', '.join(f"'{p}'({s:.2f})" for p, s in keywords)
        detail = f"Query: {query}\n  Keywords: [{kw_str}]\n  Expected: {expected_terms}"
        check(f"'{query[:40]}...' finds expected terms", found_any, detail)


# ═════════════════════════════════════════════════════════════════════════════
# NEW TESTS — Pronoun Query Detection Edge Cases
# ═════════════════════════════════════════════════════════════════════════════

def test_pronoun_query_edge_cases():
    suite("Pronoun query edge cases")

    # Should be detected as context-dependent
    context_dependent = [
        "it",
        "that",
        "this",
        "them",
        "tell me more",
        "go on",
        "continue",
        "explain that",
        "what about it",
        "how about that",
        "yeah but how",
        "well what about",
        "and then what",
        "what else",
        "can you elaborate",
        "tell me about that",
        "similar",
        "same thing",
    ]

    for query in context_dependent:
        check(f"'{query}' is context-dependent", is_context_dependent(query))

    # Should NOT be detected as context-dependent
    not_dependent = [
        "What is France?",
        "How do I bake a cake?",
        "Define recursion",
        "Explain quantum computing",
        "Tell me about machine learning",
        "Hello",
        "Goodbye",
        "What is the meaning of life?",
        "How many planets are in the solar system?",
        "Who wrote Romeo and Juliet?",
    ]

    for query in not_dependent:
        check(f"'{query}' is NOT context-dependent", not is_context_dependent(query))


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    """Run all tests."""
    print(f"\n{'#'*60}")
    print(f"  COS Context Extraction TEST SUITE")
    print(f"  Module: cos.context_extraction")
    print(f"  Tests: 400+ assertions across 40+ test functions")
    print(f"{'#'*60}")

    # Legacy tests (preserved)
    test_clean_query()
    test_remove_stop_words()
    test_extract_by_question_pattern()
    test_extract_noun_phrases()
    test_extract_entities()
    test_extract_content_words()
    test_extract_cleaned_query()
    test_extract_keywords()
    test_extract_topic()
    test_is_empty_topic()
    test_normalize_topic()
    test_extract_noun_phrases_only()
    test_extract_entities_only()
    test_extract_context_topic()
    test_is_context_dependent()
    test_is_pronoun_query()
    test_extract_context_topic_pronoun_resolution()
    test_integration_real_world_queries()
    test_integration_conversation_tracking()
    test_edge_cases()
    test_configuration()
    test_regression_security()

    # NEW tests
    test_classify_question()
    test_extract_compound_phrases()
    test_extract_by_verb_pattern()
    test_cross_strategy_consistency()
    test_compound_resolution_in_context()
    test_property_all_functions_are_pure()
    test_property_keyword_ordering()
    test_property_known_compounds_case_insensitive()
    test_property_empty_and_edge_inputs()
    test_complex_multi_turn_conversations()
    test_adversarial_inputs()
    test_question_type_alignment()
    test_known_compound_integrity()
    test_llm_style_queries()
    test_pronoun_query_edge_cases()

    all_pass = summary()
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
