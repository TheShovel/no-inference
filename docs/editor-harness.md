# Editor Harness: fill-in / completion API

`cos.code_editor` is the integration point for editor plugins, IDEs, or any
tool that wants to *fill code in* rather than chat about it. It reads the
current buffer (language, imports, definitions, indentation, quote style)
and produces an insertion that fits it, deterministically and offline.

Two reference harnesses ship with the repo:

* `examples/harness_cli.py`: a scriptable JSON backend (stdin/stdout +
  `--json`); the fastest way to try the fill-in API and a good backend for
  plugins.
* `cos.cli`: an **opencode-style agent**; a terminal tool that opens a
  file, understands the task, shows a diff, and applies the edit. This is
  the reference for anyone building a coding-agent CLI on top of COS. It
  ships as a console script (`cos` after `pip install -e .`), as a
  module (`python3 -m cos.cli` when installed), and directly from a source
  checkout (`python3 src/cos/cli.py`).

Try the agent right now:

```sh
# install the tool once (provides the `cos` command):
pip install -e .

cos                                     # interactive session
cos "complete the function" --file tool.py --yes
cos "convert this code to javascript" --file tool.py
cos "write a function that flattens a nested list" --file tool.py

# or, from a source checkout without installing:
python3 src/cos/cli.py "complete the function" --file tool.py --yes
```

## The three entry points

```python
from cos.code_editor import analyze_buffer, complete_buffer, fill_in

# 1. Understand the buffer before deciding what to ask
ctx = analyze_buffer(code, filename="tool.py")
# -> {'language': 'python', 'imports': ['os', 'json'],
#     'definitions': [('function', 'unique')],
#     'indent': {'kind': 'spaces', 'unit': 4}, ...}

# 2. Fill in a function body
res = complete_buffer(
    code="def reverse_string(s: str) -> str:\n    ...\n",
    instruction="",          # optional; may live in a '# TODO:' comment
    cursor_pos=None,         # optional 0-based line index
    filename="tool.py",
)
# res['text']  -> "    return s[::-1]"      <- exact text to insert
# res['notes'] -> ["Recognized 'reverse_string' as the 'reverse_string'
#                   task and reused the curated implementation for python."]
# res['context'] -> the buffer analysis (imports/defs/indent)

# 3. Chat-style answer (used by process_query)
answer = fill_in("complete this function: def add(a, b):\n    ...")
```

## What `complete_buffer` fills

1. **A function whose name matches a known recipe:** `reverse_string`,
   `is_prime`, `fibonacci`, `dedup`, `transpose`, `slugify`, `caesar_shift`,
   `generate_password`, `shuffle`, `memoize`, `retry`, `pretty_json`,
   `count_words`, `chunk`, `flatten`, `binary_search`, `palindrome`,
   `anagram`, `merge_sorted`, `gcd`, `factorial`, `fizzbuzz`, `sort`, …
   the body is taken from the curated `code_gen` templates for the buffer's
   language, *renamed to your function and your parameter names*, and
   re-indented to your scope.
2. **Instruction recipes that read the buffer:** a `# TODO: ...` comment,
   a docstring, or `instruction=` can say *what* to do; the buffer says
   *what with*: `"move the task at index from TODO to DONE"` →
   `task = TODO.pop(index); DONE.append(task)` when `TODO = []` and
   `DONE = []` exist; `"average of rows[*][key]"` → a comprehension over
   `rows`; `"group rows by X and sum Y per group"` → a grouped dict;
   `"reduce the total by the given percent"` → `total() * (1 - p/100)`
   reusing the `total()` defined in the buffer; `"Read a CSV file into a
   list of dicts"` → `csv.DictReader`.
3. **Name-verb recipes over module-level state:** `add_task(text)` →
   `TODO.append(text)` when the buffer defines `TODO = []`; `itemCount()`
   → `cart.length` when it defines `const cart = [];`;
   `count_remaining()` → `len(TODO)`; `clear_finished()` → `DONE.clear()`;
   `is_*` / `has_*` → membership tests.
4. **Name-prefix recipes:** `total_revenue(orders)` → `return sum(orders)`
   (with an honest “assumes orders is a list of numbers” comment);
   `count_items`, `avg_price`, `max_*`, `min_*`, `top_n(rows, key, n)` →
   a descending sort slice, …
5. **An instruction routed to a curated task:** when the instruction
   clearly names a known task and the template's parameter count matches
   the signature (mismatches are refused rather than emitted broken).
6. **Short inline recipes:** “return a greeting”, “sum of a and b”,
   “max of the two”, “length of the list”, …
7. **An honest scaffold otherwise:** `return False` / `return 0` /
   `return ""` / `pass  # TODO: implement` with a note explaining that the
   logic couldn't be inferred from the signature alone. Never fabricated.

## Markers it recognizes

* a line that is exactly `...`
* a bare `pass` inside a function body (Python)
* an empty `{ }` / `{};` block (braced languages)
* a `# ...` / `// ...` comment
* a `throw new Error("TODO")` stub (JS/TS), which is valid syntax so
  stubbed modules still compile

Any of these marks a fill-in point, including several in one buffer (each
fill resolves the first remaining one).

## Context awareness (the “reads the script it is in” part)

* **Indentation:** insertion is re-indented to the enclosing scope + one
  level, using the buffer's unit (spaces or tabs).
* **Parameter names:** template bodies are rewritten to use your signature's
  parameter names (`def slugify(title)` produces `title.lower()`, not the
  template's `text`).
* **Imports:** `notes` flags modules the body uses that the file doesn't
  import yet (`re`, `random`, `json`, `collections`, …).
* **Language:** from the filename extension first, then the code's syntax.
* **Definitions:** `ctx['definitions']` lists what's already in the file.

## Building a harness

The contract for any editor plugin is three steps:

1. **Ask**: give `complete_buffer` the buffer text, the cursor line
   (0-based), an optional instruction, and the filename.
2. **Read**: `res['text']` is the exact insertion (already indented);
   `res['replace_line']` is the 0-based line index whose content it replaces
   (the marker line). `res['notes']` are human-readable assumptions.
3. **Apply**: replace the marker line's contents with `res['text']`.

### Reference CLI

```sh
# fill the first '...' marker, show the insertion
python3 examples/harness_cli.py tool.py

# fill at a specific line (editor-style 1-based) with an instruction
python3 examples/harness_cli.py tool.py --cursor 7 \
    --instruction "return the sum of the two numbers"

# machine-readable output for a plugin
python3 examples/harness_cli.py tool.py --json

# feed the buffer on stdin (no temp file needed from an editor)
cat tool.py | python3 examples/harness_cli.py - --filename tool.py --json

# apply the edit in place (demo of an editor applying the insertion)
python3 examples/harness_cli.py tool.py --apply
```

Exit codes: `0` = filled, `1` = nothing to fill, `2` = usage error.

### JSON output contract (what a plugin consumes)

```json
{
  "ok": true,
  "language": "python",
  "text": "    return s[::-1]",
  "notes": ["Recognized 'reverse_string' as the 'reverse_string' task ..."],
  "replace_line": 1,
  "context": null,
  "edited": "def reverse_string(s: str) -> str:\n    return s[::-1]\n"
}
```

`replace_line` is 0-based; `text` replaces that line. `edited` is the whole
buffer with the insertion applied (handy for previews). With
`--context`, `context` holds the full `analyze_buffer` result.

### The opencode-style agent (`cos`)

The agent reads the file it is pointed at, routes the task, shows a diff,
and applies the edit after approval, the loop every coding agent needs,
without any LLM:

1. **fill-in tasks** (`"complete the function"`) → `complete_buffer` on the
   open buffer (markers auto-detected);
2. **code transforms** (`"convert this code to javascript"`) →
   `transform_code` on the open buffer;
3. **code tasks** (`"write a function that flattens a nested list"`) →
   `generate_code`, offered as a pending append;
4. **whole artifacts with no file open** (`"create a website for a taco
   shop"`) → staged as a **new file**: a `dev/null` diff and a
   `create taco-shop.html? [y/N]` prompt. `y` writes it to the working
   directory; `/undo` deletes it again. Existing files are never
   overwritten, and knowledge answers with example code blocks are never
   turned into files.
5. **iterative refinement** (`"add a contact form"`, `"change the accent
   color to green"`, `"make it dark"`, `"add error handling"`, `"now do
   the same in rust"`) → edits the last generated artifact in place (see
   `cos.refine`);
6. **questions** (`"what is a binary search"`) → `process_query` chat
   answer (never appended as code);
7. **everything else** → `process_query` chat answer.

It ships three ways: a console script (`cos` after `pip install -e .`), a
launcher (`bin/cos`, symlink it into your PATH to get `cos` in any
project directory), and the module itself (`python3 src/cos/cli.py`).

### The terminal UI (`cos` with no arguments)

Running `cos` interactively opens a full-screen TUI (raw terminal + ANSI,
no dependencies):

* **Scrollable task log:** every task, diff, and note is logged;
  `PageUp`/`PageDown` scroll, colors mark added/removed lines, notes,
  and status.
* **File picker:** `Tab` lists source files in the working directory;
  arrows select, Enter opens, Esc cancels. `/open <name>` + Tab completes
  a partial name.
* **Input line:** arrows move the cursor, `Ctrl-W` deletes a word,
  `Ctrl-U` deletes to the start, `Up`/`Down` recall past tasks.
* **Inline approval:** after a task stages an edit the prompt becomes
  `apply this edit? [y/N]`; `y` applies, `n`/Enter keeps the edit pending
  for `/apply`.
* **Auto-target:** with no file open, a fill task picks the most likely
  source file in the working directory (the one with a marker).

REPL commands work in the TUI too: `/open <file>`, `/context` (shows the
analyzed buffer), `/diff`, `/apply`, `/undo`, `/files`, `/help`, `/quit`.
Force the plain prompt loop with `--repl`, or disable the TUI entirely
with `COS_NO_TUI=1`. One-shot mode:

```sh
cos "complete the function" --file tool.py --yes
```

When no file is given, the agent looks for a source file with a fill-in
marker in the working directory before falling back to a chat answer.

## Wiring into `process_query`

The engine already routes fill-in requests automatically:

```
complete this function: def is_prime(n):
    ...

fill in the body: ```python
def fibonacci(n):
    pass
```
```

…and follows up on the last code (`complete the last code`). Queries that
transform pasted code (`convert this code from python to javascript: …`,
`explain this code: …`) are *not* hijacked: the fill-in detector requires
an empty-body marker.

### Iterative refinement (`cos.refine`)

After the engine generates an artifact, follow-ups edit *that artifact*
instead of falling into the factual handler (which used to return
knowledge-article garbage for "add a contact form"):

* **HTML**: `change the accent color to green`, `make it dark`, `add a
  contact form`, `add a section about catering`, `add carnitas to the
  menu`, `change the name to Taqueria Rosa`, `change the hours`, `remove
  the hours section`;
* **Code**: `add error handling`, `add a docstring`, `add comments`, `make
  it faster`, `add compression to the backup script`, `add a function that
  validates an email address`, `now do the same in rust` (language
  conversion reuses the transformer on the artifact).

The refinement layer finds the last generated fenced block (or code the
user pasted), filters by artifact kind (HTML edits edit the *website*, not
a fibonacci function generated in between), applies a deterministic edit,
and reports exactly what changed. Requests it can't apply are answered
honestly rather than fabricated.

## Determinism

Every insertion is produced by rules over the signature, the function name,
and the curated `code_gen` templates. No sampling, no network. The same
buffer + instruction always yields the same text.
