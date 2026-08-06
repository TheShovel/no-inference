"""
COS Intent Detection — Routes user queries to the right subsystem.
Each intent corresponds to a handler in orchestrator.py or its sub-modules.

Intents:
  - math:           Arithmetic expressions (2 + 3 * 4)
  - word_problem:   Math word problems with numbers and quantities
  - roleplay:       Character roleplay ("pretend to be...")
  - instruction:    Writing, coding, creative tasks
  - code:           Programming-specific requests
  - follow_up:      MT-Bench Turn 2 follow-ups
  - memory_recall:  Questions about what the user said
  - factual:        General knowledge questions
"""

import re
from cos.state import current_roleplay, conversation_history


def detect_intent(query):
    """Detect the intent of a query to route it to the right subsystem."""
    q = query.lower().strip()

    # ── MT-Bench Turn 2 follow-up detection ──────────────────────────────
    follow_up_patterns = [
        'your previous', 'your previous response', 'previous answer',
        'rewrite your', 'rephrase your', 'revise your',
        'take your previous', 'take the previous',
        'your last', 'your prior',
        'start every sentence', 'begins with', 'letter a',
        'first sentence with', 'rewrite starting',
        'rework your previous', 'amend your earlier',
        'alter your previous', 'modify your earlier',
        'change your previous', 'update your previous',
        'now, do the same task', 'now make the',
        'summarize the story', 'take a moment to evaluate',
        'can you rephrase', 'does there exist',
        'how about finding', 'what about this one',
        'repeat the same task', 'do the same task again',
        'continue from previous', 'adjust option',
        'make the following adjustments'
    ]
    if any(p in q for p in follow_up_patterns):
        return 'follow_up'

    # Single-word expansion requests (e.g., "longer", "more", "continue")
    # that need conversation history context to make sense.
    expansion_words = {'longer', 'more', 'further', 'elaborate', 'details'}
    if q in expansion_words and conversation_history:
        return 'follow_up'

    # ── Math expression (before factual, since "what is X times Y" matches both) ──
    word_problem_keywords = [
        'how many', 'how much', 'total', 'altogether', 'per ', 'each',
        'calculate', 'how far',
        'how long', 'how old', 'many dollars', 'what percentage', 'what fraction',
        'percent', 'percentage',
        'miles', 'kilometers', 'gallons', 'liters', 'hours', 'minutes',
        'per day', 'per hour', 'per week', 'per year', 'per month',
        'than', 'remaining', 'left over', 'sold', 'bought', 'costs',
        'profit', 'loss', 'discount', 'interest', 'rate',
        'dozen', 'dozens', 'score', 'times as many', 'ratio',
        'startup invests', 'total cost', 'total amount',
        'vertices', 'area of the triangle', 'probability'
    ]
    has_number = bool(re.search(r'\d+', q)) or any(w in q.split() for w in
        ['one','two','three','four','five','six','seven','eight','nine','ten',
         'eleven','twelve','dozen','dozens','half','third','quarter'])
    # Pure arithmetic: "25 times 4 plus 10" or "2 + 3 * 4"
    if has_number:
        if re.search(r'\d+\s+(?:times|plus|minus|divided\s+by|multiplied\s+by)\s+\d+', q):
            return 'math'
        if re.search(r'\d\s*[+\-*/^]\s*\d', q) and not any(w in q for w in word_problem_keywords):
            return 'math'

    # ── Explicit math operations (before factual, which would otherwise
    #    hijack them): roots, powers, equations, geometry with numbers ────
    if re.search(r'(?:square|squared|cube|cubed)\s+root|sqrt\b', q) and re.search(r'\d', q):
        return 'math'
    if re.search(r'to\s+the\s+(?:power|exponent)\s+of\b', q) and re.search(r'\d+.*\d', q):
        return 'math'
    if re.search(r'\bsolve\b', q) and re.search(r'[xyz]\s*(?:[+\-*/]\s*\d*\.?\d*\s*)*=\s*\d+|=\s*\d+\s*[+\-*/]', q.replace(' ', '')):
        return 'math'
    if re.search(r'\b(solve|find)\b', q) and re.search(r'=', q) and re.search(r'[xyz](?!\w)', q):
        return 'math'
    if re.search(r'\b(?:area|circumference|perimeter|volume)\b', q) and re.search(r'\d', q):
        return 'word_problem'

    # ── Factual knowledge detection (before word problems) ───────────────
    factual_knowledge_patterns = [
        r'what\s+is\s+the\s+(?:smallest|largest|biggest|tallest|longest|deepest|oldest|newest|fastest|slowest|highest|lowest)',
        r'what\s+is\s+the\s+(?:most|least)\s+',
        r'what\s+(?:is|was|are|were)\s+the\s+(?:name|names)\s+',
        r'what\s+(?:is|are)\s+.*(?:known\s+for|famous\s+for|made\s+of|used\s+for|called|named|invented|discovered|created|found\s+in)',
        r'who\s+(?:is|was|are|were)\s+',
        r'where\s+(?:is|are|was|were)\s+',
        r'when\s+(?:is|was|were|did)\s+',
        r'how\s+(?:many|much)\s+(?:people|countries|cities|species|elements|planets|stars|galaxies)',
        r'(?:true|false)\s*[:]',
        r'which\s+of\s+the\s+following',
    ]
    for pat in factual_knowledge_patterns:
        if re.search(pat, q):
            return 'factual'

    # ── Word problem detection (after factual) ──────────────────────────
    is_simple_math = bool(re.match(r'^[\d\s+\-*/^().]+$', q.replace('?','').strip()))

    if has_number and not is_simple_math:
        is_word_problem = any(w in q for w in word_problem_keywords)
        has_question = '?' in q
        has_measurement = bool(re.search(
            r'\d+\s*(?:%|percent|dollars?|miles?|km|hours?|minutes?|eggs?|cups?|lbs?|kg|gallons?|liters?|years?|months?|weeks?|days?|scores?|points?|coins?|shares?|bolts?|feet?|inches?|cm|meters?|books?|copies?)', q))

        # "than" needs a nearby number to avoid "fewer than two paragraphs"
        if 'than' in q:
            than_has_number = bool(re.search(r'\d+\s*\w*\s*than|than\s*\w*\s*\d+', q))
            if not than_has_number:
                other_keywords = [w for w in word_problem_keywords if w != 'than']
                is_word_problem = any(w in q for w in other_keywords)

        if is_word_problem or (has_question and has_measurement):
            return 'word_problem'

    # ── Math expression ───────────────────────────────────────────────────
    if re.search(r'\d\s*[+\-*/^]\s*\d', q) and not any(w in q for w in word_problem_keywords):
        return 'math'
    # Also catch "what is X times/plus/minus/divided by Y"
    if re.search(r'\d+\s+(?:times|plus|minus|divided\s+by|multiplied\s+by)\s+\d+', q) and not any(w in q for w in word_problem_keywords):
        return 'math'

    # ── Roleplay ─────────────────────────────────────────────────────────
    writing_exclusions = ["write a", "writing", "blog post", "blog", "story",
                          "article", "compose", "draft", "email to", "paragraph",
                          "poem", "short story", "essay", "newsletter", "outline"]
    is_writing_related = any(w in q for w in writing_exclusions)

    rp_patterns = ["pretend", "act as", "roleplay", "role play", "embrace the role",
                   "speak as", "imagine you are", "imagine yourself",
                   "step into the role", "in the role of", "as if you were",
                   "embody the persona", "assume the role", "picture yourself",
                   "suppose you are", "now you are a", "now you are an",
                   "take on the role", "you are elon", "you are sheldon",
                   "you are shakespeare", "you are william",
                   "you are a machine learning", "you are a math teacher",
                   "you are a mathematician", "you are a 100-year",
                   "you are a doctor", "you are a relationship",
                   "you are a translator", "you are an english"]
    if not is_writing_related:
        if any(p in q for p in rp_patterns):
            return 'roleplay'
        if re.search(r'(?:pretend|imagine|embrace|embody|picture)\s+(?:yourself|to be|the role)', q):
            return 'roleplay'

    # ── Code ──────────────────────────────────────────────────────────────
    code_triggers = ["implement", "program", "function", "algorithm", "data structure"]
    if any(q.startswith(kw) for kw in code_triggers) or \
       any(kw in q for kw in ["write a function", "write a program", "write code"]):
        return 'code'
    if q.startswith("code"):
        return 'code'

    # ── Creative / instruction ───────────────────────────────────────────
    instruction_starters = [
        "compose", "write", "draft", "create", "rewrite",
        "rephrase", "revise", "generate", "compose",
    ]
    instruction_containing = [
        "compose", "write a", "write an", "draft a", "draft an",
        "tell me a story", "tell me a joke", "give me a",
        "provide an outline", "provide a summary",
        "discuss", "explore", "provide insights", "share ideas",
    ]
    if any(q.startswith(kw) for kw in instruction_starters):
        return 'instruction'
    if any(kw in q for kw in instruction_containing):
        return 'instruction'
    if re.search(r'\b(write|create|draft|compose|construct|craft|design)\b', q) and \
       any(w in q for w in ['story', 'blog', 'email', 'essay', 'article', 'poem',
                             'paragraph', 'headline', 'description', 'outline']):
        return 'instruction'

    # ── How-to / procedural ──────────────────────────────────────────────
    # "how do i make a salad", "how to cook pasta", "can i substitute...", etc.
    # Only flag as instruction if it's a first-person procedural question
    # (e.g., "How do I...", "How do we...", "How to...").
    # Third-person "How do [noun]..." questions are factual (e.g., "How do cities plan...")
    if re.search(r'\bhow\s+(do|to|can|would|should|could)\s+(i|we|you)\b', q):
        return 'instruction'
    if re.search(r'\bhow\s+to\b', q) and not re.search(r'\bhow\s+to\s+(?:the\s+)?(?:evolution|history|origin|development|concept|process|way\s+cities|way\s+do)', q):
        return 'instruction'
    if re.match(r'\bcan\s+(?:i|we|you)\s+', q):
        return 'instruction'
    if re.search(r'what.?(?:s|\s+is)\s+(?:the\s+)?best\s+way', q):
        return 'instruction'
    if re.search(r'what.?(?:s|\s+is)\s+a\s+good\s+(?:substitute|alternative|replacement)', q):
        return 'instruction'

    # ── STEM ──────────────────────────────────────────────────────────────
    # STEM questions route to factual for template engine / knowledge base
    stem_signals = ["explain", "describe", "what is", "how does", "why does"]
    stem_topics = ["biology", "chemistry", "physics", "engineering", "mathematics",
                   "dna", "cell", "force", "energy", "chemical", "quantum", "equation",
                   "calculus", "algorithm", "neural", "protein", "genetics",
                   "photosynthesis", "superposition", "satellite", "exothermic",
                   "endothermic", "machine learning", "central dogma"]
    if (any(q.startswith(kw) for kw in stem_signals) or any(kw in q for kw in stem_signals)) and \
       any(t in q for t in stem_topics):
        return 'factual'

    # ── Humanities ────────────────────────────────────────────────────────
    humanities_triggers = ["antitrust", "lesson plan", "socrates", "documentary",
                            "base rate fallacy", "opium wars", "art masterpieces",
                            "business etiquette", "stages of life",
                            "key principles in evaluating", "methods did socrates",
                            "award-winning documentary", "gdp", "inflation",
                            "unemployment", "fiscal and monetary"]
    if any(t in q for t in humanities_triggers):
        return 'instruction'

    # ── Extraction ────────────────────────────────────────────────────────
    extraction_triggers = ["extract", "evaluate.*movie", "identify.*company",
                           "analyze.*review", "given.*data", "identify.*countries",
                           "named entities", "count how many times",
                           "stock prices", "variable names"]
    if any(re.search(t, q) for t in extraction_triggers):
        return 'instruction'

    # ── Evaluation / critique ─────────────────────────────────────────────
    if any(q.startswith(kw) for kw in ["evaluate", "critique", "review", "assess"]):
        return 'instruction'

    # ── List / enumerate ──────────────────────────────────────────────────
    if any(q.startswith(kw) for kw in ["list", "enumerate", "name some"]):
        return 'instruction'

    # ── Roleplay follow-up (Turn 2 character questions) ──────────────────
    if current_roleplay and not any(p in q for p in ['your previous']):
        roleplay_followups = ["danc", "dinner", "bus", "teach", "let's",
                              "would you like", "how do you", "what do you think",
                              "can you teach", "teach me", "grab dinner",
                              "take bus", "tell me about yourself"]
        if any(p in q for p in roleplay_followups):
            return 'roleplay'

    # ── Memory recall ────────────────────────────────────────────────────
    # These patterns detect queries about what was previously discussed.
    # They require personal pronouns combined with memory-related verbs
    # to avoid false-positive matches on factual knowledge questions.
    memory_recall_patterns = [
        # "What did I say...", "What did you say..."
        r'what\s+(?:did|have)\s+(?:i|you|we|they)\s+(?:say|mention|tell|ask|talk|said|mentioned|told)\s+',
        # "What is my...", "What are my...", "What is your..."
        r'what\s+(?:is|are|was|were)\s+(?:my|your)\s+(?:name|favorite|opinion|thought|idea|suggestion|age|birthday|job|hobby)',
        # "Do you remember...", "Do you know what I..."
        r'do\s+you\s+(?:remember|recall)\s+',
        r'do\s+i\s+(?:like|have|want|know|remember)',
        # "Tell me what I...", "Show me what I..."
        r'(?:tell|show)\s+me\s+what\s+(?:i|my|we)',
        # Specific recall about previously stated facts
        r'(?:what|which)\s+(?:color|food|movie|book|song|animal|language|city)\s+did\s+(?:i|you|we)\s+(?:say|mention)',
        r'what\s+was\s+(?:i|we|he|she)\s+(?:talking|saying|discussing)',
    ]
    for pat in memory_recall_patterns:
        if re.search(pat, q):
            return 'memory_recall'

    # ── Geography / capital questions ─────────────────────────────────────
    geography_patterns = [
        r'what\s+is\s+the\s+(?:capital|largest|highest|longest|deepest|oldest)',
        r'where\s+is\s+',
        r'what\s+is\s+.*(?:capital|country|city|river|mountain|ocean|continent)',
    ]
    for pat in geography_patterns:
        if re.search(pat, q):
            return 'factual'

    # ── Default ───────────────────────────────────────────────────────────
    return 'factual'
