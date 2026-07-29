# no-inference

**Proof of concept / research project.** Not production-ready software.

This is not the best this system could be. We know where the gaps are. The pattern matcher could cover more ground, the knowledge base could be thousands of entries deep, the NLG pipeline could produce more natural prose, and the math solver could handle calculus. But building that takes data, testing, and server time we do not have. If this project had the resources to run continuous evaluation and iterate on the knowledge base at scale, it would compete with chatbot services that cost millions to run. As it stands, it is a demonstration that the approach works. We think that is worth something.

```
  /\_/\
 ( o.o )
  > ^ <
```

A purely symbolic conversational engine that answers questions, writes essays, solves math problems, roleplays characters, and holds conversations.

## How it works in one sentence

no-inference detects what kind of question you asked, then routes it to a specialized handler that retrieves or generates an answer from curated knowledge bases, Wikipedia, templates, or symbolic logic.

## Quick start

```bash
# Just run it. Works with the Python standard library.

cd src
python3 cos_tui.py
```

Type questions, get answers. Type `/help` for commands. The cat is not included but we think it adds character.

> "The best way to have a good conversation is to not use a neural network." -- Ancient proverb, probably

## Requirements

- Python 3.8 or later
- Internet connection (optional, used for live Wikipedia lookups, weather, time, dictionary)

Optional for LLM judge evaluations:
- Ollama running locally (for `src/benchmark/llm_eval.py` only)

## Installation

```bash
cd no-inference
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-api.txt   # Only needed for the API server
```

That is it. The TUI and all query processing work with zero pip packages. The TUI uses only the Python standard library.

To run the API server:

```bash
cd src
python3 -m api.server
```

## Usage

### Text interface (TUI)

```bash
cd src
python3 cos_tui.py
```

Commands inside the TUI:

- `/help`. Show help
- `/debug`. Toggle routing decisions display
- `/verbose`. Toggle full reasoning output
- `/status`. Show benchmark scores
- `/history`. Show last 10 conversation turns
- `/reset`. Clear conversation memory
- `/reload`. Reload patterns, aliases, templates from disk
- `/quit`. Exit

### API server

```bash
cd src
python3 -m api.server
```

Listens on `http://localhost:8080`. Endpoints:

- `GET /health`. Health check
- `GET /status`. System status
- `POST /query`. Single query `{"query": "..."}`
- `POST /conversation`. Create a conversation `{"query": "..."}`
- `GET /conversation/<id>`. Get conversation history
- `POST /conversation/<id>/query`. Continue a conversation `{"query": "..."}`
- `DELETE /conversation/<id>`. Delete a conversation

### Benchmarking

```bash
cd src
python3 -m benchmark.freeform_bench --questions 20
python3 -m benchmark.adversarial_bench
python3 -m benchmark.nlg_quality_bench
python3 -m benchmark.llm_eval          # Requires Ollama
python3 -m benchmark.orchestrator      # Run all benchmarks
```

## How it works

no-inference uses a detection and routing pipeline. Every query is classified by intent, then sent to a specialized handler that retrieves or assembles a response from its knowledge sources.

Every query goes through a detection and routing pipeline:

```
query -> intent detection -> handler -> optional knowledge retrieval -> response assembly
```

The system maintains:

- **Intent detection.** Regex-based routing that classifies queries into math, word problems, roleplay, instruction, follow-up, memory recall, and factual categories
- **Knowledge base.** Curated JSON files with question-answer pairs across science, history, technology, coding, and everyday life
- **Wikipedia integration.** On-the-fly retrieval with an NLG pipeline that strips formatting artifacts and produces clean, conversational text
- **Template engine.** Context-aware template matching with topic extraction from conversation history
- **Pattern matcher.** Social and emotional response patterns for greetings, farewells, feelings, and chit-chat
- **Fact memory.** Extracts and stores user-stated facts ("I like pizza") for later recall ("What do I like?")
- **Math solver.** Multi-strategy solver covering arithmetic, distance-rate-time, percentages, and probability
- **Roleplay engine.** Character personas with in-character responses and follow-up handling
- **NLG pipeline.** A five-pass natural language generation system that takes raw retrieved information and produces natural, varied conversational responses
- **External API layer.** Free public API integrations for weather, time, dictionary, exchange rates, and jokes
- **False premise detection.** Identifies pseudoscience and non-existent concepts before they reach the knowledge base

## Why does it work well?

**Traceable.** Every response comes from a known source. A knowledge base entry, a Wikipedia page, a template file, or a handler. What it retrieves is what you get.

**Deterministic.** The same query always produces the same response (when temperature is 0). This makes debugging, testing, and auditing straightforward.

**Fast.** Responses come back in milliseconds to seconds depending on whether a Wikipedia fetch is needed.

**Transparent.** Every response can be traced back to its source. A knowledge base entry, a Wikipedia page, a template file, or a handler.

**Private.** Everything runs locally. Your queries stay on your machine. Unless you ask about the weather, in which case a polite request is sent to a free API. No data is sold, stored, or used to train anything. We could not afford the GPUs anyway.

**Maintainable.** Adding new knowledge means adding a JSON file. Adding new conversation patterns means adding a JSON file. Adding new personas means adding a few lines of Python.

## Project structure

```
no-inference/
  src/
    cos/                    Core engine
      __init__.py           Package entry point
      engine.py             Main orchestrator and all handlers
      state.py              Shared conversation state
      intent.py             Query intent classification
      memory.py             Fact memory extraction and recall
      knowledge.py          Curated knowledge base lookup
      templates.py          Instruction, coding, reasoning templates
      template_engine.py    Context-aware template system
      pattern_matcher.py    Social/emotional response patterns
      roleplay.py           Character persona engine
      followup.py           Response rewrite engine
      math_solver.py        Word problem and arithmetic solver
      context_extraction.py Multi-strategy keyword and topic extraction
      poem.py               Template-based poem generator
      code_knowledge.py     Programming knowledge base
      external_apis.py      Free public API integrations
      prompt_templates.py   Prompt template matching system
      nlg/                 Natural language generation pipeline
    api/                    HTTP API server
    benchmark/              Benchmarking and evaluation
    cos_tui.py              Text user interface
    generate_kb.py          Knowledge base generator from Wikipedia
  data/
    aliases.json            Topic name aliases
    knowledge/              Curated knowledge by subject
      general/              General knowledge entries
      generated/            Wikipedia-generated entries
      templates/            Context-aware response templates
      ...                   Subject-specific directories
    patterns/               Social and emotional response patterns
    prompt_templates/       Instruction templates for essays, code, etc.
    cache/                  Wikipedia response cache
  docs/                     Documentation
  tests/                    Test suite
```

## Documentation

- [Architecture](docs/architecture.md). Full system architecture and data flow
- [Intent System](docs/intents.md). How queries are classified and routed
- [NLG Pipeline](docs/nlg.md). Natural language generation from retrieved information
- [Knowledge Base](docs/knowledge.md). Curated knowledge, Wikipedia integration, and code lookup
- [Benchmarks](docs/benchmarks.md). Evaluation methodology and results
- [Data Formats](docs/data.md). How to add patterns, templates, knowledge entries, and personas

## Benchmark results

**NLG Quality (deterministic)**

| Metric                | Score |
|-----------------------|-------|
| Fact Preservation     | 99.1% |
| Coherence             | 90.0% |
| Numerical Precision   | 97.4% |
| Temperature Variety   | 70.0% |
| Overall               | 97.4% |

**LLM Judge (gemma4:31b, 22 cases)**

| Metric            | Score (out of 10) |
|-------------------|-------------------|
| Naturalness       | 4.2               |
| Informativeness   | 6.1               |
| Coherence         | 6.1               |
| Correctness       | 9.3               |
| Overall           | 6.8               |

## License

AGPL-3.0. See [LICENSE](LICENSE).

## Credits and research inspiration

This project builds on ideas from the following research papers and systems:

- **ELIZA** (Weizenbaum, 1966). The original conversational AI system that proved natural dialogue can be simulated with simple pattern matching and template responses. The pattern-based architecture of no-inference follows the same design philosophy. [DOI: 10.1145/365153.365168](https://doi.org/10.1145/365153.365168)
- **Reading Wikipedia to Answer Open-Domain Questions** (Chen et al., 2017). DrQA established the paradigm of using Wikipedia as a knowledge source for open-domain question answering. no-inference follows the same retrieval approach using symbolic extraction to retrieve and present information from Wikipedia articles. [arXiv:1704.00051](https://arxiv.org/abs/1704.00051)
- **Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena** (Zheng et al., 2023). The multi-turn evaluation framework and LLM-as-a-judge methodology that no-inference uses for benchmarking response quality. [arXiv:2306.05685](https://arxiv.org/abs/2306.05685)
- **Microplanning with Communicative Intentions: The SPUD System** (Stone et al., 2003). The template-based NLG approach where sentences are constructed from discourse plans with communicative goals. no-inference's NLG pipeline (fact extraction, discourse structuring, realization) follows this paradigm. [DOI: 10.1111/1467-8640.t01-1-00256](https://doi.org/10.1111/1467-8640.t01-1-00256)
- **CYC: A Large-Scale Investment in Knowledge Infrastructure** (Lenat, 1995). The foundational work on curated symbolic knowledge bases for AI. no-inference's hand-authored knowledge base follows the same principle of encoding knowledge as discrete, human-readable facts. [DOI: 10.1145/219717.219745](https://doi.org/10.1145/219717.219745)
- **The Elements of AIML Style** (Wallace, 2003). The ALICE/AIML framework defined how modular chatbot personas can be built from pattern-template rules. no-inference's roleplay engine and pattern matcher are direct descendants of this approach.
- **Chat-80: An Efficient Easily Adaptable System for Interpreting Natural Language Queries** (Warren & Pereira, 1982). An early demonstration that natural language query processing can be done entirely with symbolic methods. [DOI: 10.3115/981564.981571](https://doi.org/10.3115/981564.981571)

---

```
  /\_/\
 ( o.o )
  > ^ <
"u dun with teh docs?"
```

Yes. Yes we are.

## Contributing

This project lives on community effort. If you want to help, here are ways to contribute:

- Add knowledge base entries. Pick a subject you know about and write question-answer pairs in a JSON file. See [Data Formats](docs/data.md) for the format.
- Add conversation patterns. Write regex patterns and responses for things the system does not handle well yet.
- Improve the NLG pipeline. The five-pass system works but the sentences could be more natural.
- Add more Wikipedia-generated entries using `src/generate_kb.py`.
- Fix bugs, clean up code, write tests.

We welcome pull requests. We especially welcome pull requests that add data. The code is simple. The data is what makes it smart.

Please contribute. This project needs you more than it needs another architecture diagram.

```
  /\_/\
 ( o.o )
  > ^ <
  "pls send pr"
```
