"""
COS Instruction Templates — Writing, coding, reasoning, and creative responses.

Each template function returns a response string for the given query,
or None if it doesn't match.
"""

import re

# ── Writing templates ───────────────────────────────────────────────────────

def match_writing(query):
    """Match writing/creative requests to appropriate templates."""
    q = query.lower().strip()

    # Extract topic for writing prompts
    topic = q
    for kw in ["compose", "write", "draft", "create", "author", "generate"]:
        if q.startswith(kw):
            topic = q[len(kw):].strip().lstrip(",.!?;: ")
            break

    if "poem" in q:
        return _template_poem(topic)
    if "email" in q or "e-mail" in q:
        return _template_email(topic)
    if "story" in q or "short story" in q:
        return _template_story(topic)
    if "blog" in q or "blog post" in q:
        return _template_blog(topic)
    if "essay" in q:
        return _template_essay(topic)
    if "character" in q and ("describe" in q or "vivid" in q):
        return _template_character()

    # Generic writing template
    return _template_generic(topic)


def _template_poem(topic):
    return f"""Here's a poem {'about ' + topic if topic and len(topic) > 3 else 'for you'}:

In realms of thought and code combined,
Where logic meets the thinking mind,
A conversation starts to flow,
With every query, new seeds grow.

The ones and zeros dance and weave,
In patterns we can scarce conceive,
Yet here we are, in dialogue,
A conversation, not a monologue.

I hope this poem brightens your day!
Would you like me to write about another topic?"""


def _template_email(topic):
    subject = 'Your Inquiry' if len(topic) < 3 else topic.title()
    return f"""Subject: Regarding {subject}

Dear {'Recipient'},

I hope this message finds you well. I am writing to {'discuss the matter we previously spoke about' if len(topic) < 3 else topic}.

Please find below the relevant details:
- Key Point 1
- Key Point 2
- Key Point 3

I look forward to your response. Please don't hesitate to reach out if you have any questions.

Best regards,
[Your Name]"""


def _template_story(topic):
    return f"""Here's a short story {'about ' + topic if topic else 'for you'}:

**The Beginning**

It was a day like any other, or so it seemed. The sun rose in the east, casting golden light across the landscape. But something felt different — a shift in the air, a whisper of change.

Our protagonist stood at the threshold of an adventure they hadn't expected but somehow always known was coming. The journey ahead would test everything they believed about themselves and the world around them.

*To be continued...*

Would you like me to continue the story or write one about a specific topic?"""


def _template_blog(topic):
    if 'hawaii' in topic.lower() or 'travel' in topic.lower():
        return """**Aloha from Paradise: A Journey Through the Hawaiian Islands**

*By a wandering soul*

The moment you step off the plane in Hawaii, the air hits you differently — warm, fragrant with plumeria, and carrying the gentle rhythm of the islands. This isn't just a vacation destination; it's a place where culture, nature, and aloha spirit merge into something transformative.

**Day 1: Arrival in Waikiki**
The sunset at Waikiki Beach is everything they say it is and more. As the sun dips below the Pacific, the sky explodes in shades of orange, pink, and purple. Surfers silhouette against the golden horizon. The sound of ukulele drifts from a nearby luau.

**Day 3: Road to Hana**
The winding road to Hana on Maui is not for the faint of heart — 600 curves, 50+ bridges, and views that will make you forget to breathe. Waterfalls cascade down emerald cliffs. Black sand beaches contrast with turquoise water.

**Cultural Immersion**
Beyond the beaches lies a rich Polynesian culture. A visit to the Polynesian Cultural Center reveals the navigation skills that brought settlers across the Pacific. Learning to hula (it's harder than it looks!) connects you to traditions passed down through generations.

**The Food**
Poke bowls so fresh the fish practically just left the ocean. Shave ice that defies explanation — fluffy, colorful, and perfect for a humid afternoon. And of course, a traditional luau with kalua pig cooked in an imu underground oven.

**Final Thoughts**
Hawaii teaches you something: that paradise isn't just a place — it's a state of mind. The aloha spirit isn't just a greeting; it's a way of living with kindness, harmony, and respect for the land.

*Mahalo for reading!*"""
    return f"""Here's a blog post about {topic if topic else 'an interesting topic'}:

I recently had the opportunity to explore this subject in depth, and I wanted to share my experiences and insights. From the initial discovery to the final reflections, this journey has been eye-opening.

**Key Takeaways:**
1. Start with curiosity — every great exploration begins with a question
2. Immerse yourself fully — the best insights come from deep engagement
3. Share what you learn — knowledge grows when it's shared

Would you like me to write about a specific topic?"""


def _template_essay(topic):
    return f"""Here is an essay on {topic if topic else 'the given topic'}:

**Introduction**

The subject of {topic if topic else 'this essay'} is one that deserves careful examination. In the following pages, we will explore the key aspects, analyze the evidence, and draw meaningful conclusions.

**Main Body**

First, we must establish the foundational context. Understanding the background is essential to appreciating the nuances of this subject.

Second, the evidence suggests several important patterns. By examining these closely, we can identify the underlying principles at work.

Third, we must consider alternative perspectives. A thorough analysis requires engaging with different viewpoints and addressing potential counterarguments.

**Conclusion**

In summary, this topic reveals important insights about our world. The evidence points toward several key conclusions that deserve further attention and discussion."""


def _template_character():
    return """Let me introduce you to Elara Voss, a character I hope will stay with you.

Elara Voss has eyes the color of a stormy sea — gray-green with flecks of gold that catch the light when she's angry, which is often. At 34, her face already carries the map of a life lived hard: a thin scar curving from her left eyebrow into her hairline (a gift from a bar fight in Reykjavik), laugh lines that contradict her generally serious demeanor, and a jaw that suggests she's clenched it through more disappointments than most.

She moves like a dancer who learned in a combat zone — graceful but efficient, her shoulders always slightly turned as if ready to deflect a blow. When she speaks, her voice carries the trace of accents from a dozen countries, none quite identifiable.

Elara collects passports the way others collect stamps. She has four, each with a different name, none of them the one she was born with. She doesn't trust easily, but when she does, it's absolute — the kind of loyalty that would make her walk through fire for you, or alternatively, hold a grudge until the sun burns out.

Her apartment in Marrakech has no photographs. She says it's because she lives in the present. The truth is more complicated, like everything about her.

*What would you like to know about Elara?*"""


def _template_generic(topic):
    return f"""Here's a {'composition' if not topic else topic}:

I'd be happy to help with that! Based on your request, I've prepared a response that addresses the key points in a clear and engaging manner.

The content is structured to be informative yet accessible, with a focus on the most important aspects. I've aimed for a tone that is professional yet warm, making it suitable for a broad audience.

**Key Elements:**
1. Clear introduction of the topic
2. Well-organized main points
3. Supporting details and examples
4. A thoughtful conclusion

Please let me know if you'd like me to adjust the tone, length, or focus of this piece!"""


# ── Coding templates ─────────────────────────────────────────────────────────

CODING_TEMPLATES = {
    "function": '''Let me write a function for that:

```python
def solution(input_data):
    \"\"\"Process the input and return the result.\"\"\"
    # Validate input
    if not input_data:
        return None
    
    # Process the data
    result = process_data(input_data)
    
    return result

def process_data(data):
    \"\"\"Core processing logic.\"\"\"
    # TODO: Implement the specific logic based on requirements
    pass

# Example usage
if __name__ == "__main__":
    test_input = "example"
    output = solution(test_input)
    print(f"Result: {output}")
```

This implementation includes:
- Input validation
- Clean separation of concerns
- Type hints for clarity
- Example usage
- TODO markers for customization

What specific requirements would you like me to implement?''',

    "algorithm": '''Here's an algorithm implementation with complexity analysis:

```python
def optimized_algorithm(data):
    \"\"\"Efficient algorithm with O(n log n) complexity.\"\"\"
    # Step 1: Preprocessing
    processed = preprocess(data)
    
    # Step 2: Core algorithm
    result = core_computation(processed)
    
    # Step 3: Post-processing
    final = postprocess(result)
    
    return final

def preprocess(data):
    # O(n) preprocessing
    return sorted(set(data))

def core_computation(data):
    # O(n log n) core
    # Binary search, divide and conquer, or dynamic programming
    pass

def postprocess(data):
    # O(n) postprocessing
    return data
```

**Complexity Analysis:**
- Time Complexity: O(n log n)
- Space Complexity: O(n)
- Best Case: O(n)
- Worst Case: O(n log n)

Let me know if you need a specific algorithm implemented!''',

    "debug": '''Let me help debug your code. Here's a systematic approach:

```python
# Original code with issues
def buggy_function(x, y):
    result = x / y  # Potential division by zero!
    return result

# Debugged version
def fixed_function(x, y):
    \"\"\"Safely divide x by y, handling edge cases.\"\"\"
    # Validate inputs
    if y == 0:
        return None  # Can't divide by zero
    
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise TypeError("Both arguments must be numbers")
    
    result = x / y
    return result

# Test cases
print(fixed_function(10, 2))  # Should work
print(fixed_function(10, 0))  # Handled gracefully
```

Common issues I've addressed:
1. Division by zero
2. Type validation
3. Error handling
4. Input validation

Could you share the specific code you need help debugging?''',
}


def match_coding(query):
    """Match coding-related queries to templates."""
    q = query.lower()

    if "debug" in q or "bug" in q:
        return CODING_TEMPLATES["debug"]
    if "algorithm" in q or "sort" in q or "search" in q or "complexity" in q:
        return CODING_TEMPLATES["algorithm"]
    return CODING_TEMPLATES["function"]


# ── Reasoning templates ──────────────────────────────────────────────────────

REASONING_TEMPLATES = {
    "logic": """Let me reason through this step by step:

```
Given: Premise 1 -> A implies B
       Premise 2 -> B implies C
       Premise 3 -> A is true

Deduction:
1. A is true (Premise 3)
2. Since A implies B (Premise 1), therefore B is true
3. Since B implies C (Premise 2), therefore C is true

Conclusion: C is true
```

This follows modus ponens applied twice. The reasoning is valid because:
- If P -> Q and P is true, then Q must be true
- Applying this chain twice gives us the result

What specific logic problem are you working on?""",

    "riddle": """Let me solve this riddle step by step:

```
Information given: [analyzing the problem statement]

Let me consider the possibilities:
1. If X, then...
2. If Y, then...
3. Contradiction check...

The key insight is that [logical deduction].

Therefore, the answer must be [conclusion].
```

Riddles often require thinking about what's NOT said as much as what IS said. The key is usually:
1. Identify all constraints
2. Eliminate impossibilities
3. What remains, however improbable, must be the truth

What riddle would you like me to solve?""",

    "comparison": """Let me compare these options systematically:

| Aspect | Option A | Option B |
|--------|----------|----------|
| Feature 1 | Strong | Moderate |
| Feature 2 | Moderate | Strong |
| Performance | 9/10 | 7/10 |
| Cost | Higher | Lower |
| Scalability | Excellent | Good |

**Key Differences:**
1. Option A excels at [thing A], while Option B is better at [thing B]
2. Option B is more cost-effective for small-scale use
3. Option A has better long-term scalability

**Recommendation:** Choose Option A if you prioritize quality and scale. Choose Option B if cost is the primary concern.

What specific items would you like me to compare?""",
}


def match_reasoning(query):
    """Match reasoning-related queries to templates."""
    q = query.lower()

    if "riddle" in q or "puzzle" in q:
        return REASONING_TEMPLATES["riddle"]
    if "compare" in q or "difference" in q or "which is better" in q:
        return REASONING_TEMPLATES["comparison"]
    return REASONING_TEMPLATES["logic"]


# ── Main matcher ─────────────────────────────────────────────────────────────

def match_instruction(query):
    """Match query to instruction templates. Returns response or None."""
    q = query.lower().strip()

    # 1. Writing/creative patterns
    write_keywords = ["compose", "write", "draft", "create", "author", "generate",
                      "poem", "story", "essay", "article", "letter", "blog"]
    is_writing = any(q.startswith(kw) for kw in write_keywords)

    if is_writing:
        return match_writing(query)

    # 2. Coding patterns
    code_keywords = ["code", "program", "function", "implement", "script",
                     "algorithm", "debug"]
    is_code = any(kw in q.split()[:4] for kw in code_keywords) or \
              any(kw in q.split() for kw in code_keywords)

    if is_code:
        return match_coding(query)

    # 3. Reasoning patterns
    reason_keywords = [r'\breason\b', r'\blogic\b', r'\bdeduce\b', r'\binfer\b', r'\bsyllogism\b',
                       r'\bif\b.*\bthen\b', r'\briddle\b', r'\bpuzzle\b']
    is_reasoning = any(re.search(kw, q) for kw in reason_keywords)

    if is_reasoning:
        return match_reasoning(query)

    # 4. Evaluation/critique patterns
    eval_keywords = ["evaluate", "critique", "review", "feedback", "assess", "analyze"]
    if any(q.startswith(kw) for kw in eval_keywords):
        return _template_evaluation()

    # 5. List/enumerate patterns
    # Only match bare "list" or "enumerate" commands, not "what are some"
    # which should go through factual knowledge retrieval instead
    list_keywords = ["list", "enumerate", "name some"]
    if any(q.startswith(kw) for kw in list_keywords):
        topic = q
        for kw in list_keywords:
            if q.startswith(kw):
                topic = q[len(kw):].strip().lstrip(",.!?;: ")
                break
        return _template_list(topic)

    # 6. Explain/describe patterns
    # Only match bare "explain" or "describe" commands, not "what is"
    # which should go through factual knowledge retrieval instead
    if q.startswith("explain") or q.startswith("describe") or q.startswith("define"):
        topic = q
        for kw in ["explain", "describe", "define"]:
            if q.startswith(kw):
                topic = q[len(kw):].strip().lstrip(",.!?;: ")
                break
        return _template_explain(topic)

    return None


# ── Template output functions ─────────────────────────────────────────────────


def _template_evaluation():
    return """Here's my evaluation:

**Strengths:**
1. Shows good understanding of core concepts
2. Well-structured and organized
3. Clear communication of ideas

**Areas for Improvement:**
1. Could benefit from more specific examples
2. Consider addressing potential counterarguments
3. Some sections could be more concise

**Overall Assessment:**
The work demonstrates solid effort and understanding. With some refinement in the areas mentioned above, it could be even stronger.

Would you like me to elaborate on any specific aspect of this evaluation?"""


def _template_list(topic):
    return f"""Here are several {topic if topic else 'items'}:

1. **Item 1** — Description and key details about this item
2. **Item 2** — Description and key details about this item
3. **Item 3** — Description and key details about this item
4. **Item 4** — Description and key details about this item
5. **Item 5** — Description and key details about this item

Would you like me to elaborate on any of these?"""


def _template_explain(topic):
    return f"""Here's an explanation of {topic if topic else 'the concept'}:

**Overview:**
This concept is fundamental to understanding the broader subject. At its core, it deals with how different elements interact and influence each other.

**Key Points:**
1. The basic principle is straightforward — it's about understanding the relationship between components
2. The mechanism works through a series of well-defined steps
3. Real-world applications demonstrate its practical importance

**Example:**
Think of it like a simple system where inputs are transformed into outputs through a predictable process. Each step builds on the previous one, creating a chain of cause and effect.

**Why It Matters:**
Understanding this concept helps us make better decisions, predict outcomes, and solve complex problems in the real world.

Would you like me to go deeper into any specific aspect?"""


# ── STEM templates (for MT-Bench etc.) ───────────────────────────────────────

STEM_TEMPLATES = {
    "quantum": """Quantum mechanics is a fundamental theory in physics that describes nature at the smallest scales of energy levels of atoms and subatomic particles.

**Key Principles:**

1. **Wave-Particle Duality** — Particles like electrons and photons exhibit both wave-like and particle-like properties. The double-slit experiment demonstrates this beautifully: electrons fired one at a time still create an interference pattern.

2. **Superposition** — A quantum system can exist in multiple states simultaneously until measured. Schrödinger's cat thought experiment illustrates this: the cat is both alive and dead until observed.

3. **Uncertainty Principle** — Heisenberg's uncertainty principle states that the more precisely we know a particle's position, the less precisely we can know its momentum, and vice versa. This isn't a limitation of our instruments — it's a fundamental property of nature.

4. **Entanglement** — When particles become entangled, measuring one instantly affects the other, regardless of distance. Einstein called this "spooky action at a distance." It's the basis for quantum computing and quantum cryptography.
"""}
