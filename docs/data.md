# Data Formats

COS stores all its extensible content as JSON files. You can add new patterns, templates, knowledge entries, and personas without writing any Python code.

## Patterns (social/emotional responses)

Location: `data/patterns/*.json`

These files define responses for greetings, feelings, small talk, and other social interactions. Each file contains categories with regex patterns and response text.

### Format

```json
{
  "category_name": {
    "patterns": [
      "regex pattern 1",
      "regex pattern 2"
    ],
    "response": "Response text (or list for random choice)"
  }
}
```

### Example

```json
{
  "greetings": {
    "patterns": [
      "\\\\bhi\\\\b",
      "\\\\bhello\\\\b",
      "\\\\bhey\\\\b"
    ],
    "response": "Hello! How can I help you today?"
  },
  "thanks": {
    "patterns": [
      "\\\\bthank you\\\\b",
      "\\\\bthanks\\\\b",
      "\\\\bthx\\\\b"
    ],
    "response": [
      "You're welcome!",
      "Happy to help!",
      "Anytime!"
    ]
  }
}
```

Notes:
- Patterns are standard Python regex strings. Remember that JSON requires backslashes to be escaped, so `\b` becomes `\\\\b`.
- If `response` is a list, one item is chosen randomly on each match.
- Files are loaded in alphabetical order. Categories within a file are checked in definition order.
- First match wins across all files and categories.
- Categories starting with `_` are ignored (can be used for notes).

### Built-in pattern categories

The default `social_patterns.json` includes: greetings, farewells, thanks, apologies, happiness, sadness, tiredness, boredom, anxiety, curiosity, anger, gratitude, confusion, loneliness, self_doubt, motivation, celebration, idk, nonsense, meta_help, waiting, small_talk, time_queries, weather_queries, how_are_you, what_are_you, good_news, bad_news, jokes, compliments, insults, agreement, disagreement, self_intro, praise_system, praise_user, how_you_feeling, hunger, thirst, exercise, health, love, heartbreak, age_queries, philosophical, future, past_nostalgia, hobbies, work, school, weekend, travel, pets, music, movies, gaming, books, nature, food_talk, sleep, morning, coffee_tea, flirting, privacy, capabilities, meaning_of_life, truth, questions_about_self, emergency, crisis.

## Knowledge base entries

Location: `data/knowledge/**/*.json`

These files define question-answer pairs for factual queries. Each file contains an array of entries.

### Format

```json
[
  {
    "q": [
      "question variation 1",
      "question variation 2"
    ],
    "a": "Answer text"
  }
]
```

### Example

```json
[
  {
    "q": [
      "what is photosynthesis",
      "photosynthesis explained",
      "how does photosynthesis work",
      "photosynthesis process",
      "explain photosynthesis"
    ],
    "a": "Photosynthesis is the process by which plants, algae, and some bacteria convert sunlight, carbon dioxide, and water into glucose and oxygen. It takes place in the chloroplasts of plant cells, specifically using the pigment chlorophyll to capture light energy."
  }
]
```

Notes:
- The `q` array should include as many natural question variations as possible.
- Answers should be self-contained and informative.
- Files are organized by subject directory (biology, science, history, etc.).
- Multiple files in the same directory are all loaded.
- The lookup function in `cos/knowledge.py` normalizes both the query and the questions for matching.

## Prompt templates (instruction responses)

Location: `data/prompt_templates/*.json`

These files define templates for generating responses to instruction-type queries (essays, code, explanations, etc.).

### Format

```json
[
  {
    "id": "unique_template_id",
    "patterns": ["regex patterns with named groups"],
    "slots": {"slot_name": "regex_group_name"},
    "response_type": "essay|html_page|explanation|code_function|list|...",
    "weight": 0.5
  }
]
```

### Example

```json
[
  {
    "id": "write_essay",
    "patterns": [
      "write (?:a|an) essay (?:about|on|regarding) (?P<topic>.+)",
      "essay about (?P<topic>.+)"
    ],
    "slots": {"topic": "topic"},
    "response_type": "essay",
    "weight": 0.9
  }
]
```

The `response_type` determines which handler generates the content:

- `essay`. Multi-paragraph essay with title and conclusion
- `html_page`. HTML document with CSS
- `explanation`. Structured explanation with examples
- `code_function`. Code implementation with documentation
- `list`. Bulleted or numbered list
- `poem`. Rhymed or free verse poem
- `story`. Narrative with characters and plot
- `email`. Formatted email message
- `blog`. Blog post with sections

## Context-aware templates

Location: `data/knowledge/templates/**/*.json`

These templates generate conversational responses that reference previous conversation context.

### Format

```json
[
  {
    "triggers": ["trigger phrase 1", "trigger phrase 2"],
    "context_role": "topic",
    "template": "Response with {context} placeholder",
    "fallback": "Response when no context available",
    "style": ["casual"],
    "response_length": "medium"
  }
]
```

### Example

```json
[
  {
    "triggers": ["tell me more about that", "tell me more", "elaborate"],
    "context_role": "topic",
    "template": "Sure, let me tell you more about {context}. It's a fascinating subject with many interesting aspects.",
    "fallback": "Sorry, I don't have enough context to elaborate. Could you ask a specific question?",
    "style": ["casual"],
    "response_length": "medium"
  }
]
```

The `{context}` placeholder is replaced with the last discussed topic extracted from conversation history. If no context is available and `context_role` is set, the fallback text is used. If `context_role` is null or missing, the template is always eligible for matching.

Triggers are matched as word-boundary regexes. Longer triggers are matched first (more specific patterns take priority over shorter ones).

## Aliases

Location: `data/aliases.json`

Maps common abbreviations and alternative names to canonical forms for Wikipedia lookup.

### Format

```json
{
  "abbreviation": "Canonical Name",
  "another_alias": "Canonical Name"
}
```

### Example

```json
{
  "usa": "United States",
  "uk": "United Kingdom",
  "ai": "Artificial intelligence",
  "ml": "Machine learning",
  "dna": "DNA",
  "ww2": "World War II",
  "european union": "European Union"
}
```

## Personas (roleplay characters)

Location: `cos/roleplay.py` (Python code, not data files)

Personas are currently defined in Python. Each persona has:

```python
_register('persona_name', [
    'keyword1', 'keyword2', 'keyword3',
], '''Introduction response text.''')
```

The keywords are matched against the user query to determine which persona to activate. The introduction is the first response in character. Follow-up responses are generated by the default follow-up handler or a persona-specific handler if provided.

To add a new persona, add a `_register()` call in `cos/roleplay.py`.

## Reloading data at runtime

In the TUI, type `/reload` to reload all patterns, aliases, templates, and knowledge base files from disk without restarting. This allows you to edit data files and see changes immediately.

```
  /\_/\
 ( o.o )
  > ^ <
  "i can haz new persona?"
```

Yes. Yes you can.
