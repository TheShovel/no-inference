#!/usr/bin/env python3
"""Regression battery for the text/code editor.

Each case is (query, [required_substrings], [forbidden_substrings]).
The response must contain every required substring (case-insensitive) and
none of the forbidden ones.

Run with:  python3 tests/test_editor.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import cos.engine as engine
from cos.engine import process_query, reset_conversation

# Offline: no network or Stack API
engine._search_wikipedia = lambda query: (None, None)
engine._search_wikipedia_full = lambda query: (None, None)
import cos.code_knowledge as code_knowledge
code_knowledge._search_stack = lambda query, max_files=2: []

FALLBACK_PHRASES = [
    "i do not have enough specific information",
    "i'm not sure about that",
]

# (query, [required], [forbidden])
CASES = [
    # ── Email editing ────────────────────────────────────────────────────
    ("edit this email to fix any problems: hi i wanted to ask you about the meeting. i think we should reschedule it. please let me no.",
     ["hi i wanted to ask", "please let me know"], ["let me no"]),
    ("rewrite this email to be more professional: hey u, the meeting is moved to 3pm. pls confirm",
     ["the meeting is moved to 3pm"], []),
    # ── Text editing ─────────────────────────────────────────────────────
    ("can you fix the typos in this text: teh cat sat on teh mat and it was very happy",
     ["the cat sat on the mat"], ["teh"]),
    ("fix the spelling in this sentence: i dont no what to say about it",
     ["i don't know what to say"], ["dont"]),
    ("fix the typos in this paragraph: the recieve date was wrong and i am very happy about the results",
     ["the receive date"], ["recieve"]),
    ("clean up this text: hello   world",
     ["hello world"], []),
    ("fix the mistakes in this sentence: your going to love this",
     ["you're going to love this"], ["your going"]),
    ("correct the typos in this text: the product is usefull and we are very happy",
     ["useful"], ["usefull"]),
    ("fix the grammar in this sentence: a apple and an orange",
     ["an apple and an orange"], ["a apple"]),
    ("fix the punctuation in this text: hello ,world . how are you",
     ["hello, world. how are you"], []),
    # ── Code editing ─────────────────────────────────────────────────────
    ("fix this code: def add(a b): return a+b",
     ["def add(a, b)"], ["def add(a b)"]),
    ("fix this python script: for i in range(5): prnit(i)",
     ["print(i)"], ["prnit"]),
    ("fix this python code: def add(a b): prnit(a+b)",
     ["def add(a, b): print(a+b)"], ["print(a+b):"]),
    ("make it more formal: hey u, pls send the file asap",
     ["hello you", "please"], ["pls"]),
    ("fix the bugs in this function: def calc(x y): prnit(x+y)",
     ["def calc(x, y): print(x+y)"], ["prnit", "def calc(x y)"]),
    ("edit this javascript function: function add(a b) { retunr a+b }",
     ["function add", "return a+b"], ["retunr"]),
    ("fix this code: x = 5 and prnit(x)",
     ["print(x)"], ["prnit"]),
    # ── No content → ask for it ──────────────────────────────────────────
    ("edit this email", ["paste"]),
    ("fix this code", ["paste"]),
    # ── More phrasings ────────────────────────────────────────────────────
    ("check the grammar of this email: i dont no what to say", ["I don't know what to say"], ["dont"]),
    ("check for errors in this text: teh cat sat down", ["The cat sat down"], ["teh"]),
    ("make this sound better: so basically its good i guess", ["so basically it's good"], ["its good"]),
    ("improve this paragraph: the product is good and we like it", ["The product is good"], []),
    # multi-line content
    ("fix this email: line one has teh typo\nline two is fine\nline three has anoter typo",
     ["line one has the typo", "line three has another typo"], ["teh", "anoter"]),
    # json
    ("fix this json: {\"name\": \"cos\", \"age\": 3,}", ["\"age\": 3"], [",}"]),
    ("is this json valid: {\"a\": 1, \"b\": 2}", ["Valid JSON"], []),
    ("is this json valid: {\"a\": }", ["Invalid JSON"], []),
    # css
    ("fix this css: a {\n  color: blue\n  margin-top: 16 px\n}", ["color: blue;", "margin-top: 16px;"], ["16 px"]),
    # homophone wave 6 e2e
    ("fix the mistakes in this text: i here that you are coming", ["I hear that"], ["here that"]),
    ("fix the typos in this text: i herd the news yesterday", ["I heard the news"], ["herd the news"]),
    ("fix this text: the capitol of france is paris", ["capital of"], ["capitol of"]),
    ("fix the errors in this sentence: that was a soul purpose decision", ["sole purpose"], ["soul purpose"]),
    ("fix this text: in due coarse, the report will arrive", ["In due course"], ["due coarse"]),
    ("fix the spelling in this text: she has a flare for design", ["flair for design"], ["flare for"]),
    ("fix this: he wanted to show his metal", ["show his mettle"], ["show his metal"]),
    ("fix this text: a horde of treasure was found", ["hoard of treasure"], ["horde of treasure"]),
    ("fix the mistakes: we must queue the music", ["cue the music"], ["queue the music"]),
    ("fix this text: that is a false profit", ["false prophet"], ["false profit"]),
    ("fix this: the team moral was low after the defeat", ["team morale was low"], ["moral was low"]),
    ("fix the typos: he gave a strait answer", ["straight answer"], ["strait answer"]),
    ("fix this text: the aircraft hanger was huge", ["aircraft hangar"], ["aircraft hanger"]),
    ("fix this: the motion censor triggered", ["motion sensor"], ["motion censor"]),
    ("fix this text: the troop of actors performed", ["troupe of actors"], ["troop of actors"]),
    ("fix the spelling: she was unphased by the news", ["unfazed"], ["unphased"]),
    ("fix this: one in the same, everytime we meet", ["one and the same", "Every time"], ["one in the same", "everytime"]),
    # grammar wave 7 e2e
    ("fix the typos in this text: i suppose to go and he had went home", ["I supposed to go", "had gone home"], ["had went"]),
    ("fix this: the the cat sat on the mat", ["The cat sat on the mat"], ["the the"]),
    ("fix the grammar in this sentence: between you and I", ["between you and me"], ["and I"]),
    ("fix this text: me and my friend went to the store", ["My friend and I went to the store"], ["me and my friend"]),
    ("fix the spelling: i will defiantly be there", ["I will definitely be there"], ["defiantly"]),
    ("fix this text: in regards to your email, irregardless of the cost", ["Regarding your email", "regardless of the cost"], ["in regards to", "irregardless"]),
    ("fix this python code: x = 5\nif x <> 3:\n    prnit(x)", ["if x != 3:", "print(x)"], ["<>", "prnit"]),
    ("fix this text: i didnt knew the answer and he learn me nothing", ["I didn't know the answer", "teach me nothing"], ["didnt knew", "learn me"]),
    ("fix this text: i could care less about it", ["I couldn't care less"], ["could care less"]),
    ("fix this code: doucment.getElementById('x')", ["document.getElementById('x')"], ["doucment"]),
    ("fix the typos in this text: everyday life is busy", ["everyday life"], []),
    # text metrics
    ("how many words in this text: hello world foo bar", ["4 words"], []),
    ("count the sentences: one. two. three.", ["3 sentences"], []),
    ("how many characters in this text: abcdef", ["6 characters"], []),
    ("how long is this text: hello there my friend", ["reading"], []),
    ("how many words are there", [], ["That text has"]),
    ("count the words in this email: the cat sat", ["3 words"], []),
    # homophone wave 9 e2e
    ("fix this text: he needs to lose wait", ["lose weight"], ["lose wait"]),
    ("fix this: a pare of shoes and a hole new world", ["pair of shoes", "whole new world"], ["pare of", "a hole new"]),
    ("fix the spelling: the poll vault champion took a pole", ["pole vault", "took a poll"], ["poll vault", "took a pole"]),
    ("fix this text: two weaks from now", ["Two weeks from now"], ["weaks from now"]),
    # homophone wave 10 e2e + html
    ("fix this text: can you advice me on this and device a clever plan", ["Can you advise me", "Devise a clever plan"], ["advice me", "device a clever"]),
    ("fix this text: im going to lay on the bed, please set down", ["lie on the bed", "please sit down"], ["lay on", "set down"]),
    ("fix this html: <div><p>hello</p>", ["</div>"], []),
    ("check this html: <div><p>hello</p>", ["</div>"], []),
    ("fix the typos in this text: the device is new and we advise you", ["the device is new", "we advise you"], []),
    ("fix this text: the news had an affect on me and a teem player", ["an effect on me", "a team player"], ["affect on", "teem player"]),
    ("make it a question: she is ready", ["Is she ready?"], ["she is ready"]),
    ("fix this text: breath deeply, gorilla warfare is coming", ["Breathe deeply, guerrilla warfare"], ["breath deeply", "gorilla warfare"]),
    ("make it past tense: she walks to school every day", ["She walked to school"], ["walks to school"]),
    ("make it negative: he can swim", ["He cannot swim"], ["can swim"]),
    ("make it past tense: they go home and she is happy", ["They went home", "She was happy"], ["they go home", "she is happy"]),
    ("make it present tense: she walked home every day", ["She walks home"], ["walked home"]),
    ("make it more exciting: great job. keep it up.", ["great job! keep it up!"], ["job. keep"]),
    ("fix this text: its been a long day and two much coffee", ["It's been a long day", "Too much coffee"], ["its been", "two much"]),
    ("fix this text: the whether report was clear", ["The weather report"], ["whether report"]),
    # negative guards through the full pipeline
    ("fix the typos in this text: come here and sit down with a herd of cattle", ["come here", "herd of cattle"], []),
    ("fix this text: the school principal gave a speech about the guiding principle", ["the school principal", "guiding principle"], []),
    ("fix this text: i loathe spinach and get bored easily", ["loathe spinach", "bored easily"], []),
    # py2->3
    ("fix this code: for i in xrange(10): print i", ["range(10)"], ["xrange"]),
    ("please fix the following code: def add(a b): return a+b", ["def add(a, b)"], ["def add(a b)"]),
    # ── Must NOT hijack questions ────────────────────────────────────────
    ("how do i fix this code error", [], ["here's your code with these fixes"]),
    ("what is the best way to edit photos", [], ["here's the edited version"]),
    ("can you fix my computer", [], ["here's the edited version"]),
]


def _edited_block(response):
    """Extract just the edited text from the response, so forbidden words in
    the "Changes made" list (which legitimately quotes the typos) don't count."""
    import re
    # text form: "\n> <edited>\n\nChanges made:" (line-start blockquote; a bare
    # "> " would also match the "->" arrows in the changes list)
    m = re.search(r'\n> (.*?)\n\nChanges made:', response, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r'```[a-z]*\n(.*?)\n```', response, re.DOTALL)
    if m:
        return m.group(1)
    return response


def main():
    reset_conversation()
    passed = failed = 0
    failures = []
    for query, required, *rest in CASES:
        forbidden = rest[0] if rest else FALLBACK_PHRASES
        response = process_query(query)
        edited = _edited_block(response)
        low = edited.lower()
        missing = [k for k in required if k.lower() not in low]
        bad = [f for f in forbidden if f.lower() in low]
        if missing or bad:
            failed += 1
            failures.append((query, missing, bad, response[:260]))
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
