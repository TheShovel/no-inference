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
- SQL: joins, group by, duplicates, create table, aggregates
- HTML: forms, tables, semantic elements, accessibility

Entries live in `data/knowledge/coding/*.json`. Matching is language-aware: a query that names a language ("reverse a linked list in c++") is scored so same-language entries win over different-language ones, and a mismatch detected after matching is corrected by synthesis.

### 3b. Code synthesizer

When no curated entry matches, `cos/code_gen.py` **synthesizes** complete, runnable code for common developer tasks. It detects the language (Python, JavaScript, TypeScript, Java, C++, C#, Go, Rust, SQL, bash) and the task (algorithms, regex, file/CSV/JSON I/O, HTTP, web scraping, SQL, git, system administration), then assembles the code from a template library with a task-specific explanation. Pure lookup, no inference. The synthesizer is what makes answers like "write sql to find duplicate rows in a table" or "how to kill a process in linux" deterministic and correct.

Code questions are **never** sent to the Wikipedia fallback (which returns unrelated articles for code topics; "read a csv with pandas" used to fetch the giant panda).

### 3c. Code & text transformer

`cos/code_transformer.py` edits content the user pasted into the query. It detects the requested modification and applies it deterministically:

- **Code**: add error handling (try/except or try/catch around function bodies), convert between Python and JavaScript (a best-effort mechanical transpiler), rename identifiers, add explanatory comments, optimize (loop → list comprehension / `map`), explain line by line, convert `for`/`while` loops.
- **Text**: politeness rewrites ("give me X or else" → "Could you please send me X. Thank you."), extractive summarization (keeps the most informative sentences, never invents content), and phrasebook translation (a curated set of phrases/templates in Spanish/French/German/Italian/Portuguese/Dutch; arbitrary text is refused honestly rather than machine-mangled).

Follow-ups like "add comments to the last code" or "convert it to javascript" operate on the previous edit.

### 3d. Iterative refinement (`cos/refine.py`)

Code the engine *generates* (not pasted code) is refined in place across turns: "add a contact form to the website", "change the accent color to green", "make it dark", "add error handling", "add compression to the backup script", "now do the same in rust". The layer finds the last generated artifact, detects the requested edit (HTML color/theme/sections/menu/title/hours, code error handling/docstrings/comments/optimization/new functions, language conversion), applies it deterministically, and never fabricates a change it can't apply.

### 3e. Website generator

"Create a website for a taco shop" is a code task, not a knowledge lookup. `code_gen` builds a single self-contained HTML file (responsive CSS, nav, hero, and sections) with content chosen by business type: nine curated types (taco, pizza, burger, sushi, coffee, bakery, ice cream, bar, restaurant) with real menu items, plus a clean generic layout. The agent stages it as a new file you approve before writing.

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

Coding knowledge lives in JSON files under `data/knowledge/coding/` (e.g.
`code_concepts.json` for explanations like hash maps and big-O, plus
language-specific files for CSS, JS, React, Python, SQL, HTML). Each
entry is the same question-answer shape as the general base:

```json
{
  "q": ["what is a hashmap", "explain what a hashmap is", "how does a hash table work"],
  "a": "Answer text that will be returned.",
  "lang": "python",
  "code": "Optional code block shown with the answer."
}
```

The `q` array should include as many natural variations as possible. New
files are picked up at startup (`/reload` in the chat TUI, or restart).

For *synthesized* code (tasks too numerous to hand-write), add a template
instead: give the task a key in `_TASK_PATTERNS` (detection regexes) and
an entry in `_CODE` (per-language templates) in `cos/code_gen.py`; see
the `backup_dir` or `web_page` entries for examples.
