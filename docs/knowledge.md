# Knowledge Base

COS uses multiple knowledge sources to answer factual questions. Each source is checked in order until a match is found.

## Knowledge source hierarchy

When answering a factual question, COS checks these sources in order:

### 1. Curated knowledge base

Flat JSON files in `data/knowledge/` organized by subject. Each file contains an array of entries:

```json
[
  {
    "q": ["what is photosynthesis", "photosynthesis explained", "how does photosynthesis work"],
    "a": "Photosynthesis is the process by which plants convert sunlight into chemical energy."
  }
]
```

Subjects include biology, science, history, philosophy, psychology, technology, arts, astronomy, nature, geography, health, food, animals, architecture, urban topics, language, physics, daily life, coding (CSS, JavaScript, React, Python), and general knowledge.

The lookup function in `cos/knowledge.py` normalizes queries and finds the best matching entry using simple text comparison. The knowledge base is loaded once and cached in memory.

### 2. Wikipedia (live retrieval)

When the curated knowledge base has no match, COS fetches from Wikipedia's REST API. The retrieval pipeline:

1. **Topic extraction.** `cos/context_extraction.py` extracts the main noun phrase from the query
2. **Search.** Wikipedia search API finds the best article
3. **Summary.** Fetch the article summary (first paragraph)
4. **Full article.** If the summary is too short, fetch the full article
5. **Multi-source.** If the first article is insufficient, fetch additional related articles
6. **Rich content.** Fall back to full-page fetch with section filtering

Results are cached in `data/cache/` to avoid repeated network calls for the same topic.

Topic resolution handles:
- Aliases (e.g. "USA" -> "United States", "AI" -> "Artificial intelligence")
- Multi-word topics
- Pronoun resolution from conversation history ("What about that?" -> previous topic)
- Variant search (adding "mathematics", "science", "biology" suffixes for ambiguous terms)

### 3. Code knowledge base

A specialized knowledge base in `cos/code_knowledge.py` for programming questions. It detects the programming language from the query and looks up curated entries for common topics:

- CSS: centering divs, grid, flexbox, responsive design, navbar
- JavaScript: fetch API, promises, debounce, arrow functions, map/filter/reduce
- React: useState, useEffect, custom hooks, localStorage, window resize
- Python: list comprehensions, decorators, lambda, generators, exception handling
- HTML: forms, tables, semantic elements, accessibility

The code knowledge base also generates code examples with explanations for each topic.

### 4. Wikipedia knowledge base generator

`src/generate_kb.py` automatically generates knowledge base entries from Wikipedia for a list of popular topics. It:

1. Searches Wikipedia for the topic
2. Fetches the article summary
3. Generates natural question variations
4. Saves the entry as a JSON file in `data/knowledge/generated/`

Usage:

```bash
python3 src/generate_kb.py --topics "Machine learning, Quantum computing, CRISPR"
python3 src/generate_kb.py --file topics.txt
python3 src/generate_kb.py --all  # Generates from 250+ popular topics
```

### 5. False premise detection

Before any knowledge lookup, the system checks for false premises and non-existent concepts. `cos/engine.py` contains `_detect_false_premise()` which identifies:

- Pseudoscientific concepts (homeopathy curing specific diseases, perpetual motion machines)
- Non-existent technologies (time machines, teleportation devices)
- Conspiracy theories (flat earth, chemtrails)
- Misunderstood phenomena (quantum healing, mystical energy fields)
- Fictional entities presented as real (lightsaber physics, vampires, dragons)

When detected, the system returns a gentle correction explaining why the premise is problematic instead of treating it as a real question.

## Adding knowledge

> Fun fact: this whole knowledge base takes up less space than one single LLM checkpoint. And it does not need a datacenter to run.

![no-inference rat](https://raw.githubusercontent.com/TheShovel/no-inference/gh-pages/logo.png)

  "i contains multitudes"
  "(about 2 MB of them)"

### Add curated knowledge entries

Create or edit a JSON file in `data/knowledge/`. Each entry:

```json
{
  "q": ["question1", "question2", "question3"],
  "a": "Answer text that will be returned."
}
```

The `q` array should include as many natural variations of the question as possible. The more variations, the more likely the system will find a match.

Files are loaded at startup. Run `/reload` in the TUI or restart the server to pick up changes.

### Add Wikipedia-generated entries

Use the generator script:

```bash
python3 src/generate_kb.py --topics "Your Topic Here"
```

This fetches the Wikipedia summary and creates a properly formatted entry.

### Add coding knowledge

Edit `cos/code_knowledge.py` and add entries to the `_CODING_KB` dictionary. The format is:

```python
'topic_key': {
    'lang': 'python',
    'patterns': ['pattern1', 'pattern2'],
    'response': 'Answer text',
    'example': '```python\ncode example\n```'
}
```

Patterns are regex strings that will be matched against the query to find the right entry.
