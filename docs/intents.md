# Intent Detection System

COS classifies every query into one of eight intents before routing it to a handler. The intent system in `cos/intent.py` uses regex patterns and keyword matching, ordered by priority to handle overlapping patterns correctly.

## Intent priorities

The detection function checks intents in this order:

### 1. Follow-up (Turn 2)

Checked first to catch MT-Bench follow-up queries like "rewrite your previous response", "start every sentence with letter a", "summarize the story", etc. Also catches single-word expansion commands ("longer", "more", "elaborate") when conversation history exists.

**Patterns:** `rephrase your`, `rewrite your`, `start every sentence`, `previous answer`, `do the same task again`, single-word expansions

### 2. Math

Pure arithmetic expressions. Checked before factual because "what is X times Y" matches both intent patterns.

**Patterns:** `\d+\s+(?:times|plus|minus)`, `\d\s*[+\-*/^]\s*\d`, checked against word problem keywords to avoid false positives

### 3. Factual (partial)

A subset of factual patterns checked early to catch superlatives and entity questions that might otherwise look like word problems.

**Patterns:** `what is the (largest|smallest|tallest|...)`, `who is`, `where is`, `when did`, `true/false:`, `which of the following`

### 4. Word problem

Math problems embedded in natural language with units, quantities, and context.

**Detection criteria:**
- Query contains numbers (digits or spelled out)
- Query contains word problem keywords (how many, total, per, each, miles, hours, sold, bought, costs, profit, etc.)
- Not a simple arithmetic expression (checked first)

**Keywords:** how many, how much, total, per, each, calculate, percent, miles, gallons, hours, sold, bought, costs, profit, discount, dozen, ratio, vertices, probability, etc.

### 5. Math (second pass)

A second check for simple arithmetic if the word problem check did not match. Catches expressions that might have been missed by the first check.

### 6. Roleplay

Checked before instruction to prevent character requests from being routed as creative writing tasks.

**Patterns:** `pretend`, `act as`, `roleplay`, `imagine you are`, `step into the role`, `speak as`, `now you are a`, `you are (known character name)`

Excludes queries containing writing-related keywords like "write a", "poem", "essay", "story" to avoid false positives (e.g. "write a story about a pirate" is instruction, not roleplay).

### 7. Code

Programming-specific requests.

**Patterns:** `implement`, `program`, `function`, `algorithm`, `write a function`, `write a program`, `write code`

### 8. Instruction

Creative, writing, and procedural tasks.

**Patterns:**
- Direct starters: `compose`, `write a`, `draft`, `create`, `rewrite`, `generate`
- Containing: `tell me a story`, `give me a`, `provide an outline`
- How-to: `how do I`, `how to`, `how can I`, `can I`
- Evaluation: `evaluate`, `critique`, `review`, `assess`
- Lists: `list`, `enumerate`, `name some`
- Humanities: specific triggers like `socrates`, `gdp`, `inflation`
- Extraction: `extract`, `analyze`, `identify`

### 9. Memory recall

Questions about what the user previously said.

**Patterns:** `what did I say`, `what is my favorite`, `do you remember`, `tell me what I`, `what was I talking about`

### 10. Factual (default)

If nothing else matches, the query is treated as a factual question. This catches general knowledge questions, geography, STEM topics, and any query that does not fit the other categories.

**Patterns:** geography (capitals, countries, cities), STEM (explain, what is, how does), and any remaining query

## Adding a new intent

Intents are detected purely by pattern matching in `detect_intent()`. To add a new intent:

1. Add detection logic in `cos/intent.py` at the appropriate priority level
2. Add a handler function in `cos/engine.py`
3. Add routing in `process_query()` after the `detect_intent()` call
4. Update the TUI help text in `src/cos_tui.py`
5. Add intent-specific patterns to the API documentation if needed

## Intent dispatch in engine.py

The routing in `process_query()` follows the detection result:

```python
intent = detect_intent(q_clean)

if intent == 'math':
    response = _handle_math(q_clean)
elif intent == 'word_problem':
    response = _handle_word_problem(q_clean)
elif intent == 'roleplay':
    response = _handle_roleplay(q_clean)
elif intent in ('instruction', 'code'):
    response = _handle_instruction(q_clean)
elif intent == 'follow_up':
    response = _handle_follow_up(q_clean)
elif intent == 'memory_recall':
    response = _handle_memory_recall(q_clean)
elif intent == 'factual':
    response = _handle_factual(q_clean, use_cos)
```

After routing, the response goes through a quality check that rejects template artifacts, placeholder text, garbled output, excessive "refers to" repetition, and disambiguation page markers. If rejected, the system falls back to Wikipedia retrieval with the NLG pipeline.

```
  /\_/\
 ( o.o )
  > ^ <
  "intent confirmed: pet the cat"
```

This intent is not yet implemented but we are accepting pull requests.
