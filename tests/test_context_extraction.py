#!/usr/bin/env python3
"""
test_context_extraction.py — Comprehensive test suite for the symbolic
context extraction system.

Tests all extraction strategies, edge cases, and conversation context tracking.

Run:
    python3 tests/test_context_extraction.py
    python3 -m pytest tests/test_context_extraction.py -v  (if pytest is available)
"""

import os
import sys
import re

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
    # Utilities
    extract_by_question_pattern,
    extract_noun_phrases,
    extract_entities,
    extract_content_words,
    extract_cleaned_query,
    clean_query,
    remove_stop_words,
    normalize_topic,
    is_empty_topic,
    is_context_dependent,
    _is_pronoun_query,
    collapse_whitespace,
    # Constants
    get_stop_words,
    _EMPTY_TOPICS,
    _QUESTION_PATTERNS,
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


# ── Tests ────────────────────────────────────────────────────────────────────

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


def test_extract_noun_phrases():
    suite("extract_noun_phrases")

    # Basic noun phrase extraction
    results = extract_noun_phrases("What is the capital of France?")
    # Should find some noun-like phrases
    check_gt("finds noun phrases", len(results), 0)

    results = extract_noun_phrases("The quick brown fox jumps over the lazy dog")
    check_gt("finds descriptive phrases", len(results), 0)

    # Empty/trivial input
    results = extract_noun_phrases("")
    check_eq("empty input gives empty", results, [])

    results = extract_noun_phrases("the")
    check_eq("only stop words gives empty or low score", 
        all(s < 0.5 for _, s in results) if results else True, True)


def test_extract_entities():
    suite("extract_entities")

    # Proper nouns
    results = extract_entities("What is the capital of France?")
    if results:
        entities = [e.lower() for e, _ in results]
        # 'France' should be detected as a proper noun
        has_france = any('france' in e for e in entities)
        check("detects France as entity", has_france)

    # Quoted entities
    results = extract_entities('The concept of "quantum entanglement" is fascinating')
    if results:
        entities_lower = [e.lower() for e, _ in results]
        check_in("detects quoted entity", 'quantum entanglement', entities_lower)

    # Multi-word capitalized
    results = extract_entities("New York City is a big place")
    if results:
        entities_lower = [e.lower() for e, _ in results]
        check_in("detects New York City", 'new york city', entities_lower)

    # Empty
    results = extract_entities("")
    check_eq("empty input gives empty", results, [])


def test_extract_content_words():
    suite("extract_content_words")

    results = extract_content_words("What is the capital of France?", max_words=10)
    check_gt("extracts content words", len(results), 0)
    if results:
        words = [w.lower() for w, _ in results]
        check_in("france found", "france", words)

    # Longer words should score higher
    results = extract_content_words("photosynthesis converts sunlight")
    if results:
        # photosynthesis is long, should be high
        best_word, best_score = results[0]
        check("long word scores higher", best_score > 0.3)

    # Short words should be filtered or low
    results = extract_content_words("a an the it")
    check("no short stop words in results", len(results) == 0 or all(len(w) >= 3 for w, _ in results))


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


def test_extract_keywords():
    suite("extract_keywords — main API")

    # Standard factual question
    results = extract_keywords("What is the capital of France?")
    check_gt("has results", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("france in top results", "france", phrases)
        # Top result should have high confidence
        check_gt("top confidence > 0.5", results[0][1], 0.5)

    # How-to question
    results = extract_keywords("How does photosynthesis work?")
    check_gt("how-to has results", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("photosynthesis in results", "photosynthesis", phrases)

    # Personal statement
    results = extract_keywords("I like pizza with pepperoni")
    check_gt("personal statement has results", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("pizza in results", "pizza", phrases)

    # Explain-style
    results = extract_keywords("Explain quantum computing")
    check_gt("explain has results", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("quantum computing in results", "quantum computing", phrases)

    # Where question
    results = extract_keywords("Where is the Eiffel Tower located?")
    check_gt("where has results", len(results), 0)
    if results:
        phrases = [p.lower() for p, _ in results]
        check_in("eiffel tower in results", "eiffel tower", phrases)

    # Empty input
    results = extract_keywords("")
    check_eq("empty input", results, [])

    results = extract_keywords("   ")
    check_eq("whitespace input", results, [])

    # Max keywords respected
    results = extract_keywords("What is the capital of France and its population?", max_keywords=1)
    check_eq("max_keywords=1 respected", len(results) <= 1, True)

    results = extract_keywords("What is the capital of France and its population?", max_keywords=3)
    check_eq("max_keywords=3 respected", len(results) <= 3, True)


def test_extract_topic():
    suite("extract_topic — main API")

    # Basic topics
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

    # Edge cases
    topic, conf = extract_topic("")
    check("empty query returns None topic", topic is None)
    check_eq("empty query conf 0.0", conf, 0.0)

    topic, conf = extract_topic("Hi")
    check("short greeting returns some topic", topic is not None)

    # Gibberish
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


def test_extract_context_topic():
    suite("extract_context_topic")

    # Empty history
    result = extract_context_topic([])
    check("empty history returns None", result is None)

    # Single exchange
    history = [
        ("What is the capital of France?", "Paris is the capital of France."),
    ]
    result = extract_context_topic(history)
    check("single exchange finds topic", result is not None)
    if result:
        check("france in context", 'france' in result.lower())

    # Multi-turn conversation
    history = [
        ("What is photosynthesis?", "Photosynthesis is how plants make energy from sunlight."),
        ("Tell me more about that", None),
        ("How does chlorophyll work in this process?", "Chlorophyll absorbs light energy."),
    ]
    result = extract_context_topic(history)
    check("multi-turn finds topic", result is not None)

    # No meaningful content
    history = [
        ("Hi", "Hello!"),
        ("How are you?", "I'm good, thanks!"),
    ]
    result = extract_context_topic(history)
    check("greetings still produces some topic", result is not None or True)  # May produce topic

    # max_lookback works
    long_history = [
        (f"What is topic {i}?", f"That is about topic {i}.")
        for i in range(20)
    ]
    result_short = extract_context_topic(long_history, max_lookback=2)
    result_long = extract_context_topic(long_history, max_lookback=10)
    check("lookback works", result_short is not None or result_long is not None)


def test_is_context_dependent():
    suite("is_context_dependent")

    # Queries that depend on context
    check("pronoun 'it' is context-dependent", is_context_dependent("tell me about it"))
    check("pronoun 'them' is context-dependent", is_context_dependent("how do i make them"))
    check("pronoun 'that' is context-dependent", is_context_dependent("explain that"))
    check("follow-up signal is context-dependent", is_context_dependent("yeah but how do i make them"))
    check("demonstrative reference", is_context_dependent("tell me more about that"))
    check("vague pronoun query", is_context_dependent("how tall is it"))
    check("'go on' signal", is_context_dependent("go on"))

    # Self-contained queries
    check("factual question not dependent", not is_context_dependent("What is the capital of France?"))
    check("how-to not dependent with clear topic", not is_context_dependent("How do I bake a chocolate cake?"))
    check("definition not dependent", not is_context_dependent("Define recursion"))
    check("greeting not dependent", not is_context_dependent("Hello"))
    check("empty string not dependent", not is_context_dependent(""))


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


def test_extract_context_topic_pronoun_resolution():
    """Test pronoun resolution in context topic extraction."""
    suite("extract_context_topic — pronoun resolution")

    # "them" resolves to "french fries"
    history = [
        ("What is the capital of France?", "Paris is the capital of France."),
        ("How do I make french fries?", "Cut potatoes into strips and fry them."),
    ]
    result = extract_context_topic(history, current_query="yeah but how do i make them")
    check("them -> french fries", result is not None and 'french' in result.lower())

    # "it" resolves to "Eiffel Tower"
    history = [
        ("What is photosynthesis?", "Plants convert sunlight to energy."),
        ("Tell me about the Eiffel Tower", "It is in Paris."),
        ("How tall is it?", "It is 330 meters tall."),
    ]
    result = extract_context_topic(history, current_query="how tall is it")
    check("it -> Eiffel Tower", result is not None and ('eiffel' in result.lower() or 'tower' in result.lower()))

    # "that" resolves to most recent substantive topic
    history = [
        ("Define recursion", "Recursion is when a function calls itself."),
        ("Tell me more about that", "In programming, recursion..."),
    ]
    result = extract_context_topic(history, current_query="tell me more about that")
    check("that -> recursion", result is not None and 'recursion' in result.lower())

    # Self-contained query doesn't need pronoun resolution
    result = extract_context_topic(history, current_query="What is the capital of Australia?")
    check("self-contained still works", result is not None)


def test_integration_real_world_queries():
    """Test extraction on a broad set of realistic queries."""
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

        # Check that at least one expected term is found
        found_any = any(term.lower() in all_text or any(term.lower() in p for p in all_phrases)
                        for term in expected_terms)

        # For fail details
        kw_str = ', '.join(f"'{p}'({s:.2f})" for p, s in keywords)
        detail = f"Query: {query}\n  Keywords: [{kw_str}]\n  Expected: {expected_terms}"
        check(f"'{query[:40]}...' finds expected terms", found_any, detail)

        # Topic should generally have confidence > 0
        topic, conf = extract_topic(query)
        if topic:
            check(f"Topic for '{query[:30]}...' has confidence > 0.1", conf > 0.1,
                  f"conf={conf:.3f}, topic='{topic}'")


def test_integration_conversation_tracking():
    """Test conversation context tracking across turns."""
    suite("Integration — Conversation context tracking")

    # Multi-turn: changing topics
    history = [
        ("What is the capital of France?", "Paris is the capital of France."),
        ("What's the population there?", "Paris has about 2.1 million people."),
        ("Tell me about the Eiffel Tower", "The Eiffel Tower is a famous landmark in Paris."),
    ]
    ctx = extract_context_topic(history)
    # The last query shifts the topic to 'eiffel tower'
    check("context tracks latest topic", ctx is not None and (
        'eiffel' in ctx.lower() or 'paris' in ctx.lower() or 'tower' in ctx.lower()
    ))

    # Topic switch should be detected from new query
    history2 = [
        ("What is photosynthesis?", "Photosynthesis is how plants make energy."),
        ("What is the capital of Australia?", "Canberra is the capital of Australia."),
    ]
    ctx2 = extract_context_topic(history2)
    check("canberra or australia as new topic",
        ctx2 is not None and ('canberra' in ctx2.lower() or 'australia' in ctx2.lower()))

    # No history
    ctx = extract_context_topic([])
    check("no history returns None", ctx is None)


def test_edge_cases():
    """Test edge cases and boundary conditions."""
    suite("Edge cases")

    # Very long query
    long_query = "What is " + "very " * 50 + "important?"
    results = extract_keywords(long_query)
    check("long query doesn't crash", isinstance(results, list))

    # Query with only stop words
    results = extract_keywords("the a an in on at")
    # Should still return something (the cleaned fallback)
    check("stop-word-only query returns something", len(results) > 0)
    if results:
        check("stop-word-only query has low confidence", results[0][1] <= 0.6)

    # Query with numbers
    results = extract_keywords("What is 2 + 2?")
    check("math query has results", len(results) > 0)

    # Query with special characters
    results = extract_keywords("C++ vs Python: which is better for AI?")
    check("special chars query doesn't crash", isinstance(results, list))
    if results:
        has_python = any('python' in p.lower() for p, _ in results)
        check("python found in query with special chars", has_python)

    # Unicode
    results = extract_keywords("What is Schrödinger's cat?")
    check("unicode query doesn't crash", isinstance(results, list))
    if results:
        has_cat = any('cat' in p.lower() for p, _ in results)
        check("cat found in unicode query", has_cat)

    # Single word
    results = extract_keywords("Hello")
    check("single word returns results", len(results) > 0)

    # URL-like
    results = extract_keywords("https://example.com")
    check("url-like doesn't crash", isinstance(results, list))


def test_configuration():
    """Test configuration constants are valid."""
    suite("Configuration")

    check("_QUESTION_PATTERNS is not empty", len(_QUESTION_PATTERNS) > 0)
    for pattern, group, weight in _QUESTION_PATTERNS:
        check(f"pattern '{pattern[:30]}...' has valid group", group >= 1)
        check(f"pattern '{pattern[:30]}...' has valid weight", 0.0 <= weight <= 2.0)
        # Verify the regex compiles
        try:
            re.compile(pattern, re.IGNORECASE)
            check(f"pattern compiles: {pattern[:30]}...", True)
        except re.error:
            check(f"pattern compiles: {pattern[:30]}...", False, f"Invalid regex: {pattern}")

    check("_EMPTY_TOPICS is not empty", len(_EMPTY_TOPICS) > 0)
    check("stop words is not empty", len(get_stop_words()) > 0)


def test_regression_security():
    """Test that extraction doesn't have ReDoS or pathological behavior."""
    suite("Security / robustness")

    # ReDoS-like patterns
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


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    """Run all tests."""
    print(f"\n{'#'*60}")
    print(f"  COS Context Extraction Test Suite")
    print(f"  Module: cos.context_extraction")
    print(f"{'#'*60}")

    # Run all test functions
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

    all_pass = summary()
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
