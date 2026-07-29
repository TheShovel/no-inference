# NLG Pipeline

The Natural Language Generation pipeline takes raw retrieved information (typically from Wikipedia or the knowledge base) and transforms it into natural, conversational responses. It lives in `src/cos/nlg/` and is a purely symbolic multi-pass system.

## Five-pass pipeline

### Pass 1: Cleaner (`cleaner.py`)

Removes noise from raw information before processing:

- Strips pronunciation guides (e.g. `/fəˈnetɪk/`)
- Strips Wikipedia formatting artifacts (section headers, "See also", "References")
- Normalizes whitespace
- Removes empty parentheticals
- Strips trailing fragments and orphaned words
- Handles truncation gracefully

### Pass 2: Parser (`parser.py`)

Extracts structured facts and entities from cleaned text:

- **Fact extraction.** Identifies subject-relation-object triples from sentences
- **Entity extraction.** Pulls out named entities (people, places, dates, numbers)
- **Type classification.** Each fact is tagged with a type: definition, property, relation, event, example, comparison

Returns a list of `Fact` objects with `subject`, `relation`, `object`, `type`, and `source_sentence` fields.

### Pass 3: Discourse (`discourse.py`)

Builds a discourse tree from the extracted facts:

- Groups related facts into discourse units
- Detects rhetorical relations between units (elaboration, contrast, cause-effect, sequence)
- Builds a tree structure representing the flow of information
- Supports flattening the tree back to a linear sequence

The discourse tree structure allows the system to order information logically instead of just concatenating sentences.

### Pass 4: Realizer (`realize.py`, `combine.py`, `reference.py`)

Generates varied sentences from the discourse tree:

- **Realization.** Each fact is rendered as a complete sentence based on its type. Definitions get "X is..." patterns, properties get "X has..." patterns, events get "X happened..." patterns
- **Combination.** Related sentences are joined through coordination ("and", "but", "or") and relative clauses ("which", "that") at a configurable rate
- **Reference.** Pronouns and definite references are selected based on discourse proximity and salience. Repeated entities are replaced with "it", "they", "this", etc.

### Pass 5: Fluency (`fluency.py`, `lexical.py`)

Applies surface-level polish:

- **Contractions.** "do not" -> "don't", "it is" -> "it's" (configurable rate per style profile)
- **Capitalization.** Fixes sentence-start capitalization and proper noun casing
- **Predicate variety.** Varies reporting verbs ("explains", "describes", "covers") at low rate
- **Fillers.** Inserts discourse markers ("Well,", "Actually,", "You see,") at low rate

## Configuration

The NLG pipeline is controlled by `NLGConfig`:

```python
from cos.nlg import NLGConfig

config = NLGConfig(
    style="friendly",    # "friendly", "neutral", "concise"
    verbosity=0.5,       # 0.0 (concise) to 1.0 (expansive)
    temperature=0.5      # 0.0 (deterministic) to 1.0 (maximum variety)
)
```

Each style profile defines rates for different linguistic features:

| Feature           | friendly | neutral | concise |
|--------------------|----------|---------|---------|
| contraction_rate   | 0.9      | 0.7     | 0.5     |
| filler_rate        | 0.02     | 0.02    | 0.0     |
| hedge_rate         | 0.0      | 0.0     | 0.0     |
| sentence_variation | 0.3      | 0.3     | 0.0     |
| combine_rate       | 0.10     | 0.25    | 0.0     |

Rates are scaled by verbosity so higher verbosity produces more varied language.

## Essay generation

The `essay.py` module generates structured multi-paragraph essays from retrieved information:

- Title derived from the topic
- Introduction from the first substantive paragraph
- Body from remaining paragraphs
- Brief conclusion if enough content exists

Used by the instruction handler for "write an essay about X" queries.

## Fallback responses

When no information can be retrieved, `fallback.py` generates a natural "I don't know" response. It varies by query type so it does not sound like a broken record:

- For "who" questions: "I don't have information about that specific person..."
- For "how" questions: "I don't have information about how to do that..."
- For general questions: "I could not find enough information about that specific topic..."

> If you ask it "what is the meaning of life?" it will give you an answer from its patterns file. That answer is not guaranteed to be profound.

## Known limitations

The poem generator produces results that range from charming to baffling. Real output from a production run:

```
Oh cats, so domestic and retractable,
A mammals for me and you.
```

We are not entirely sure what happened here either. The cat seems to have retractable claws and also retractable domestication. Pull requests that fix the poem templates are welcome.

## Query response pipeline for factual queries

The full flow for a factual query like "What is the capital of France?":

1. Intent detection -> factual
2. Knowledge base lookup (check `data/knowledge/` for matching entries)
3. Template engine check (for context-dependent templates)
4. Wikipedia search with topic resolution
5. Wikipedia full article retrieval (if summary is insufficient)
6. NLG naturalize() pipeline: clean -> parse -> discourse -> realize -> fluency
7. Response

Each step falls through to the next if the previous one produces no result. The system also retries with alternative topic variations and alias expansions to improve coverage.
