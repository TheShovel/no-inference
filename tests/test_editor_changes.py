#!/usr/bin/env python3
"""Tests for change/refinement requests — asking the AI to modify previously
edited (or inline) content: \"make it shorter\", \"make it more formal\",
\"change hello to hi\", \"add a greeting\", etc.

Run with:  python3 tests/test_editor_changes.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import cos.engine as engine
import cos.code_knowledge as code_knowledge
from cos.engine import process_query, reset_conversation
from cos.text_editor import set_last_edit

engine._search_wikipedia = lambda query: (None, None)
engine._search_wikipedia_full = lambda query: (None, None)
code_knowledge._search_stack = lambda query, max_files=2: []

FALLBACK = ["i do not have enough specific information", "i'm not sure about that"]

# (query, [required], [forbidden])
CASES = [
    # ── No content yet (must run first, before the sequence fills state) ──
    ("make it shorter", ["paste some text or code first"], []),
    ("change please to kindly", ["paste some text or code first"], []),

    # ── Sequence: fix email, then iterate changes ────────────────────────
    ("fix this email: hi u, i am gonna send the report tmrw. please let me no if its ok. thanks!",
     ["Hi u, I am gonna send the report tmrw. Please let me know if it's ok. Thanks!"], ["let me no"]),
    ("make it shorter", ["Changes made"], []),
    ("make it more formal", ["you", "going to", "tomorrow"], ["u,", "gonna", "tmrw"]),
    ("change please to kindly", ["kindly let me know"], ["please let me know"]),
    ("uppercase it", ["I AM GOING TO SEND"], ["i am going to send"]),
    ("lowercase it", ["i am going to send"], ["I AM GOING"]),
    ("add a greeting", ["Hello,", "Changes made"], []),
    ("remove the greeting", ["Changes made"], ["Hello,"]),
    ("add a closing", ["Best regards,"], []),
    ("remove the closing", ["Changes made"], ["Best regards,"]),
    ("remove exclamation marks", ["thank you"], ["!"]),
    ("turn it into bullet points", ["- "], []),

    # ── Inline changes ───────────────────────────────────────────────────
    ("make this more formal: hey u, pls send the report asap",
     ["hello you, please send the report as soon as possible"], ["pls", "asap"]),
    ("make this shorter: this is a very long sentence that really just goes on and on about nothing in particular and it is quite tedious",
     ["goes on"], ["very", "really", "quite"]),
    ("make this uppercase: hello world", ["HELLO WORLD"], ["hello world"]),
    ("change hello to hi: hello there", ["hi there"], ["hello there"]),
    ("rename x to y: def add(x, x2): return x + x2", ["def add(y, x2): return y + x2"], ["def add(x"]),

    # ── More change instructions ─────────────────────────────────────────
    ("add punctuation: hello there this is a test it has no punctuation", ["punctuation."], []),
    ("spell out the numbers: i have 3 cats and 12 dogs", ["three cats and twelve dogs"], ["3 cats", "12 dogs"]),
    ("spell out the numbers: pi is 3.14 and i paid 1,000 dollars in 2024", ["3.14", "1,000", "2024"], ["three.14", "one,000"]),
    ("make it longer: i don't think it's a good idea", ["I do not think it is a good idea"], ["don't", "it's"]),
    ("remove question marks: really? ok?", ["really ok"], ["?"]),
    ("add a subject line: this is my message to you", ["Subject: this is my message to you"], []),
    ("remove the last sentence: first one. second one. third one.", ["first one. second one."], ["third one"]),
    ("remove the first sentence: first one. second one. third one.", ["second one. third one."], ["first one"]),
    ("remove the first paragraph: first para.\n\nsecond para.\n\nthird para.", ["second para.\n\nthird para."], ["first para"]),
    ("make it one paragraph: line one\nline two\nline three", ["line one line two line three"], ["\n"]),

    # ── New wave: titles, quotes, tone, swaps, chaining ───────────────────
    ("add a title: hello there this is my note", ["Title: hello there this is my note"], []),
    ("remove the quotes: \"hello world\"", ["hello world"], ["\""]),
    ("put it in quotes: hello world", ["“hello world”"], []),
    ("soften the tone: STOP SHOUTING!!! this is really bad!!!", ["Stop shouting. This is really bad."], ["!", "STOP"]),
    ("make it less angry: I AM SO MAD at this!!!", ["I am so mad at this."], ["!", "AM SO MAD"]),
    ("swap cat and dog: the cat chased the dog", ["the dog chased the cat"], ["the cat chased"]),
    ("swap i and you: you and i should meet", ["I and you should meet"], ["you and I"]),
    ("swap the first and second word: first second third", ["second first third"], ["first second third"]),
    ("make it shorter and more formal: hey u, pls send the report asap tmrw", ["hello you", "please", "tomorrow"], ["pls", "asap", "tmrw"]),
    ("make it sound more professional: hey u, pls confirm", ["please"], ["pls"]),
    ("make it friendlier: please do not hesitate to contact me", ["don't hesitate"], ["do not hesitate"]),
    ("replace all hello with hi: hello hello world", ["hi hi world"], ["hello hello"]),
    ("change the word cat to dog: the cat sat on the mat", ["the dog sat"], ["cat sat"]),
    ("remove the first sentence and the last sentence: first one. second one. third one. fourth one.", ["second one. third one."], ["first one", "fourth one"]),
    ("remove the first and last paragraph: para one.\n\npara two.\n\npara three.", ["para two."], ["para one", "para three"]),
    ("add a greeting and a closing: thanks for everything", ["Hello,", "Best regards,"], []),
    ("remove the greeting and the closing: Hello,\n\nthanks for everything\n\nBest regards,", ["thanks for everything"], ["Hello,", "Best regards,"]),
    ("condense this: this is a very long sentence that goes on and on", ["goes on"], ["very"]),
    ("expand this: it's i.e. fine, e.g. good", ["that is", "for example"], ["i.e.", "e.g."]),
    ("trim it down: this is very very long", ["this is long"], ["very"]),
    ("remove the subject line: Subject: hello\n\nbody text", ["body text"], ["Subject: hello"]),
    ("remove the title: Title: my note\n\nbody text", ["body text"], ["Title: my note"]),
    ("remove the bullet points: - first point\n- second point", ["first point second point."], []),
    ("remove duplicate words: the the cat sat on the the mat", ["the cat sat on the mat"], ["the the"]),
    ("put each sentence on its own line: first one. second one. third one.", ["first one.\nsecond one."], []),
    ("make it a paragraph: - one\n- two\n- three", ["one two three."], []),
    ("sort the list: banana\napple\ncherry", ["apple\nbanana\ncherry"], []),
    ("alphabetize this: zebra, apple, mango", ["apple, mango, zebra"], []),
    ("reverse the sentences: first one. second one. third one.", ["third one. second one. first one."], []),
    ("put the last sentence first: one. two. three.", ["three. two. one."], []),
    ("remove the numbers: order 3 items in 2 days", ["order items in days"], []),
    ("remove the punctuation: hello, world! how are you?", ["hello world how are you"], []),
    ("add a date: this is my report", ["Date:"], []),
    ("remove the date: Date: August 2, 2026\n\nreport body", ["report body"], ["Date:"]),
    ("swap the first and last word: the quick brown fox", ["fox quick brown the"], ["the quick brown fox"]),
    ("swap the first and last sentence: one. two. three.", ["three. two. one."], []),
    ("make it double-spaced: line one\nline two", ["line one\n\nline two"], []),
    ("make it single-spaced: line one\n\nline two\n\nline three", ["line one\nline two"], []),
    ("make this text shorter: this is a very long sentence that goes on and on", ["goes on"], ["very"]),
    ("shorten this text: this is a very long sentence", ["this is a long sentence"], ["very"]),
    ("rewrite it to be more formal: hey u, pls send it", ["hello you", "please"], ["pls"]),
    ("rewrite this email to be more casual: please do not hesitate to contact me", ["don't hesitate"], ["do not hesitate"]),
    ("make it into a list: first point. second point. third point.", ["- first point."], []),
    ("remove the first 2 sentences: one. two. three. four.", ["three. four."], ["one. two."]),
    ("remove the last three lines: a\nb\nc\nd\ne", ["a\nb"], []),
    ("remove the first word: the quick brown fox", ["quick brown fox"], ["the quick"]),
    ("remove the emojis: hello 😀 world 🎉", ["hello world"], []),
    ("put it in parentheses: hello world", ["(hello world)"], []),
    ("remove the parentheses: (hello world)", ["hello world"], ["("]),
    ("make it a question: she is ready", ["Is she ready?"], ["she is ready"]),
    ("turn it into a question: they went home", ["Did they go home?"], ["they went home"]),
    ("make this a question: he likes pizza", ["Does he like pizza?"], ["he likes pizza"]),
    ("remove empty lines: a\n\n\nb\n\nc", ["a\nb\nc"], []),
    ("make it past tense: she likes pizza and they go home", ["She liked pizza", "They went home"], ["likes", "go home"]),
    ("put it in the past tense: he is running to school", ["He was running"], ["is running"]),
    ("make it negative: she likes pizza", ["She doesn't like pizza"], ["likes pizza"]),
    ("make it negative: they went home", ["They didn't go home"], ["went home"]),
    ("make it negative: she is ready", ["She is not ready"], ["is ready"]),
    ("make it negative: the report is ready", ["simple statements"], ["don't report"]),
    ("make it past tense and make it a question: she likes pizza", ["Did she like pizza?"], ["lik pizza"]),
    ("make it negative and make it a question: he can swim", ["Can he not swim?"], ["Do he"]),
    ("make it past tense: she liked pizza", ["already reads as past"], []),
    ("make it negative: she liked pizza", ["she didn't like pizza"], ["didn't liked"]),
    ("make it present tense: she walked home and they went home", ["She walks home", "They go home"], ["walked", "went home"]),
    ("put it in the present tense: he was running", ["He is running"], ["was running"]),
    ("make it more exciting: hello there. how are you.", ["hello there! how are you!"], [". how"]),
    ("add exclamation marks: the project is done", ["is done!"], ["is done."]),
    ("add a period: hello there this is a test", ["test."], []),

    # ── Must NOT hijack normal questions ─────────────────────────────────
    ("how do I make it shorter", [], ["Changes made"]),
    ("make it rain", [], ["Changes made"]),
    ("change the subject", [], ["Changes made"]),
    ("what is a greeting", [], ["Changes made"]),
    ("swap the tires on my car", [], ["Changes made"]),
    ("how do I make it less angry", [], ["Changes made"]),
    ("how do I make it shorter and more formal", [], ["Changes made"]),
]


def main():
    import re as _re
    reset_conversation()
    set_last_edit(None, '')
    passed = failed = 0
    failures = []
    for query, required, *rest in CASES:
        forbidden = rest[0] if rest else FALLBACK
        response = process_query(query)
        low = response.lower()
        missing = [r for r in required if r.lower() not in low]
        # forbidden: word-boundary AND case-sensitive (an uppercase reply must
        # not match the lowercase forbidden form, and "you" must not match "u")
        bad = [f for f in forbidden if _re.search(r'\b' + _re.escape(f) + r'\b', response)]
        if missing or bad:
            failed += 1
            failures.append((query, missing, bad, response[:220]))
        else:
            passed += 1

    print(f"Results: {passed}/{passed + failed} passed")
    if failures:
        print("\nFAILURES:")
        for query, missing, bad, snippet in failures:
            print(f"  Q: {query}")
            if missing:
                print(f"     missing: {missing}")
            if bad:
                print(f"     forbidden hit: {bad}")
            print(f"     response: {snippet}")
        sys.exit(1)


if __name__ == '__main__':
    main()
