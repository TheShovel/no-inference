# ![no-inference logo](https://raw.githubusercontent.com/TheShovel/no-inference/gh-pages/logo.png) no-inference

**Proof of concept / research project.**

> **Warning** This is not the best this system could be. We know where the gaps are. The pattern matcher could cover more ground, the knowledge base could be thousands of entries deep, the NLG pipeline could produce more natural prose, and the math solver could handle calculus. But building that takes data, testing, and server time we do not have. If this project had the resources to run continuous evaluation and iterate on the knowledge base at scale, it would compete with chatbot services that cost millions to run. As it stands, it is a demonstration that the approach works. We think that is worth something.

A purely symbolic conversational engine that answers questions, writes essays, solves math problems, roleplays characters, and holds conversations, plus an **opencode-style coding agent** (`cos`) that fills in, edits, generates, and iteratively refines code. No neural network, no sampling, no network required.

## How it works in one sentence

no-inference detects what kind of question you asked, then routes it to a specialized handler that retrieves or generates an answer from curated knowledge bases, Wikipedia, templates, or symbolic logic. Coding requests get a second routing layer: fill-in, transformation, generation, and iterative refinement, all deterministic.

## Quick start

Two interfaces ship with the repo:

**The coding agent (recommended):** a full-screen terminal UI for working on files, like a small `opencode`:

```bash
python3 src/cos/cli.py          # interactive TUI
# or install it once and use it from any project directory:
pip install -e .                # provides the `cos` command
ln -s "$PWD/bin/cos" ~/.local/bin/cos   # or symlink the launcher
```

**The chat interface:** the classic question-answer TUI:

```bash
cd src
python3 cos_tui.py
```

Both work with only the Python standard library and need no internet by default.

## Requirements

- Python 3.10 or later
- Internet connection (optional, used for live Wikipedia lookups, weather, time, dictionary; everything else is fully offline)

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

### The coding agent (`cos`)

An opencode-style deterministic agent with a full-screen terminal UI. It
reads the file it is pointed at, understands the task, shows a diff, and
applies the edit. See [Try the agent CLI](#try-the-agent-cli) below.

### Chat interface (`src/cos_tui.py`)

```bash
cd src
python3 cos_tui.py
```

Type questions, get answers. Commands inside the chat TUI:

- `/help`. Show help
- `/debug`. Toggle routing decisions display
- `/verbose`. Toggle full reasoning output
- `/status`. Show benchmark scores
- `/history`. Show last 10 conversation turns
- `/reset`. Clear conversation memory
- `/reload`. Reload patterns, aliases, templates from disk
- `/quit`. Exit

### Website (gh-pages) + API server

The demo website is a **static site on the `gh-pages` branch** (landing
page, `chat.html` chat demo, `editor.html` mini-IDE) that talks to the
engine over HTTP. The API server on `main` serves the JSON backend:

```bash
cd src
python3 -m api.server     # JSON API only, port via COS_API_PORT / PORT
```

- `GET /`. JSON index of endpoints
- `GET /health`. Health check (the site's status dots ping this)
- `GET /api/status`. System status
- `POST /api/query` (alias `/query`). Single query `{"query": "..."}`
- `POST /api/conversations`. Create a conversation
- `GET /api/conversations`. List conversations
- `GET /api/conversations/<id>`. Get conversation history
- `POST /api/conversations/<id>/query`. Continue a conversation `{"query": "..."}`
- `DELETE /api/conversations/<id>`. Delete a conversation
- `POST /api/editor/analyze`. Buffer analysis `{"code", "filename"}`
- `POST /api/editor/fill`. Fill in a marker `{"code", "instruction", "filename"}`
- `POST /api/editor/generate`. Generate code `{"query"}`
- `POST /api/editor/transform`. Transform the buffer `{"query", "code", "filename"}`

The site pages live on the `gh-pages` branch (GitHub Pages); see
[docs/web-demo.md](docs/web-demo.md) for how the two halves talk to each
other and how to point the site at a local server (`API_URL` in
`site.js`).

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
- **Code synthesizer.** A deterministic template engine (`cos/code_gen.py`) that detects the language and task of a coding question and assembles complete, runnable code: algorithms, regex, file/CSV/JSON I/O, HTTP, SQL, git, sysadmin commands, scripts, and full websites, across Python, JS/TS, Java, C++, C#, Go, Rust, SQL, and bash. Code questions never fall back to Wikipedia
- **Code transformer.** (`cos/code_transformer.py`) edits pasted code on request: convert language, add error handling, rename, comment, optimize, explain, loop conversion
- **Fill-in harness.** (`cos/code_editor.py`) reads a buffer (language, imports, definitions, indentation) and fills empty function bodies: from the signature, the function name, module-level state, or a TODO comment/docstring
- **Iterative refinement.** (`cos/refine.py`) follows up on generated artifacts: `add a contact form`, `change the accent color to green`, `add error handling`, `now do the same in rust` edit the last thing the engine produced, in place
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

**Safe.** This system cannot hallucinate or lie. Every response comes from a known source, a knowledge base entry, a Wikipedia page, a template file, or a handler. It only returns real, factual information. This is a huge safety improvement compared to classic LLMs that can generate false or misleading content with full confidence.

**Traceable.** Every response comes from a known source. A knowledge base entry, a Wikipedia page, a template file, or a handler. What it retrieves is what you get.

**Deterministic.** The same query always produces the same response (when temperature is 0). This makes debugging, testing, and auditing straightforward.

**Fast.** Responses come back in milliseconds to seconds depending on whether a Wikipedia fetch is needed.

**Transparent.** Every response can be traced back to its source. A knowledge base entry, a Wikipedia page, a template file, or a handler.

**Private.** Everything runs locally. Your queries stay on your machine. Unless you ask about the weather, in which case a polite request is sent to a free API. No data is sold, stored, or used to train anything. We could not afford the GPUs anyway.

**Maintainable.** Adding new knowledge means adding a JSON file. Adding new conversation patterns means adding a JSON file. Adding new personas means adding a few lines of Python.

## Project structure

```
no-inference/
  bin/
    cos                     Launcher: run the agent from any project directory
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
      code_knowledge.py     Programming knowledge base + code-topic routing
      code_gen.py           Deterministic code synthesizer (~90 tasks, 9 languages)
      code_transformer.py   Code/text transformations (convert, rename, errors, …)
      code_editor.py        Buffer-aware fill-in / completion API (the harness)
      refine.py             Iterative refinement: edit the last generated artifact
      text_editor.py        Text editing, change requests, summaries, translations
      cli.py                The opencode-style agent CLI (console script `cos`)
      tui.py                Dependency-free full-screen terminal UI for the agent
      external_apis.py      Free public API integrations
      prompt_templates.py   Prompt template matching system
      nlg/                  Natural language generation pipeline
    api/                    HTTP API server
    benchmark/              Benchmarking and evaluation
    cos_tui.py              Classic chat text interface
    generate_kb.py          Knowledge base generator from Wikipedia
  examples/
    harness_cli.py          Scriptable JSON fill-in backend (for editor plugins)
    workbench/              Fixture scripts used by tests and demos (todo app,
                            shopping cart, TS utilities, data processor)
  data/
    aliases.json            Topic name aliases
    knowledge/              Curated knowledge by subject
      general/              General knowledge entries
      generated/            Wikipedia-generated entries
      templates/            Context-aware response templates
      coding/               Coding concepts, git, SQL, deployment, …
      ...                   Subject-specific directories
    patterns/               Social and emotional response patterns
    prompt_templates/       Instruction templates for essays, code, etc.
    cache/                  Wikipedia response cache
  docs/                     Documentation
  tests/                    Test suite (19 suites, run `python3 tests/run_all.py`)
```

## Testing

```bash
python3 tests/run_all.py          # all 19 suites (~15 min)
python3 tests/test_refine.py      # make→edit→refine loops
python3 tests/test_workbench_recipes.py  # buffer-aware fill-in on real scripts
python3 tests/test_tui.py          # agent TUI + launcher
python3 tests/test_code_editor.py  # harness API + agent CLI
python3 tests/test_api_server.py    # JSON API the website talks to
```

The suites cover the regression set (465), coding answers (136), code
synthesis and routing (145), code/text transforms (29), practical knowledge
(192), the editor e2e suites (1044), stress (86), NLG, context extraction
(960), the harness (60), workbench recipes (39), the TUI/launcher (47),
iterative refinement (41), freeform discovery (31), and the API server
suite (48); 3,445 checks in total, all deterministic and offline.

## Documentation

- [Architecture](docs/architecture.md). Full system architecture and data flow
- [Intent System](docs/intents.md). How queries are classified and routed
- [NLG Pipeline](docs/nlg.md). Natural language generation from retrieved information
- [Knowledge Base](docs/knowledge.md). Curated knowledge, Wikipedia integration, and code lookup
- [Benchmarks](docs/benchmarks.md). Evaluation methodology and results
- [Data Formats](docs/data.md). How to add patterns, templates, knowledge entries, and personas
- [Editor Harness](docs/editor-harness.md). Fill-in / completion API, the JSON backend CLI, and the opencode-style agent CLI
- [Website + API](docs/web-demo.md). The gh-pages demo site (chat + mini-IDE) and the JSON API server it talks to

## Try the agent CLI

`cos` is a real tool in this repo: an opencode-style deterministic coding
agent with a full-screen terminal UI. It opens a file, understands the
task, shows a diff, and applies the edit. Launch it from **any project
directory**:

```sh
# install once (adds the `cos` command to your PATH):
mkdir -p ~/.local/bin
ln -s "$PWD/bin/cos" ~/.local/bin/cos
# (or: pip install -e ., which provides the same `cos` command)

cos                                     # full-screen TUI
cos "complete the function" --file tool.py --yes
cos "convert this code to javascript" --file tool.py
cos "what is a binary search"          # chat answers for questions

# from a source checkout without installing:
python3 src/cos/cli.py                  # also launches the TUI
```

In the TUI: `Tab` picks a file, `PageUp/PageDown` scroll the log,
`Ctrl-W/Ctrl-U` edit the input, `Up/Down` recall past tasks, and edits are
confirmed inline before applying. If the terminal isn't interactive, `cos`
falls back to the plain prompt loop automatically.

### Make → edit → refine

The agent keeps editing whatever it just produced. Follow-ups like `add a
contact form to the website`, `change the accent color to green`, `make it
dark`, `add error handling to the function`, `add a docstring`, `add
compression to the backup script`, or `now do the same in rust` edit the
last generated artifact in place (never a fresh regeneration, and never a
knowledge-article non-answer). It works for HTML pages, functions, and
scripts, in chat and in the TUI.

### Files are real

When a task generates a whole artifact (`create a website for a taco
shop`, `write a function that flattens a nested list`) with no file open,
`cos` stages it as a **new file**: you get a diff and `create
taco-shop.html? [y/N]`. Say `y` and the file is written to the working
directory; `/undo` deletes it again. Existing files are never overwritten
without opening them first, and knowledge answers with example code
blocks are never turned into files.

## Benchmark results

**NLG Quality (deterministic)**

| Metric                | Score |
|-----------------------|-------|
| Fact Preservation     | 99.1% |
| Coherence             | 90.0% |
| Numerical Precision   | 97.4% |
| Temperature Variety   | 70.0% |
| Overall               | 97.4% |

**LLM Judge (gemma4:31b-cloud, 10 cases, 2 rounds per case)**

| Metric            | Score (out of 10) |
|-------------------|-------------------|
| Naturalness       | 8.6               |
| Informativeness   | 8.3               |
| Coherence         | 9.5               |
| Correctness       | 10.0              |
| Conciseness       | 9.9               |
| Overall           | 9.2               |

Run it yourself: `python3 -m src.benchmark.llm_eval` (requires Ollama with
`gemma4:31b-cloud`; results land in `data/eval_results.json`).

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

![no-inference rat](https://raw.githubusercontent.com/TheShovel/no-inference/gh-pages/logo.png)

"u dun with teh docs?"

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

![no-inference rat](https://raw.githubusercontent.com/TheShovel/no-inference/gh-pages/logo.png)

  "pls send pr"
