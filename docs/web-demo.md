# Website + API: the gh-pages demos and the API server

The project is split in two halves that talk over HTTP:

- **The website** lives on the **`gh-pages` branch** — a static site
  (plain HTML/CSS/JS, no build step) hosted on GitHub Pages. It has a
  landing page, a **chat demo** (`chat.html`), and a **code editor demo**
  (`editor.html`).
- **The API** lives on `main` in `src/api/server.py` — a zero-dependency
  stdlib HTTP server that serves **JSON only**. The website's pages call
  it for every answer; the engine itself never runs in the browser.

```
browser ──> gh-pages site (static pages)
                 │  fetch()
                 ▼
        API server (src/api/server.py)
                 │
                 ▼
        cos engine (deterministic, offline)
```

## The website (`gh-pages` branch)

| File          | What it is                                        |
|---------------|---------------------------------------------------|
| `index.html`  | Landing page; "Demos" window links to the two demos |
| `chat.html`   | Chat demo — conversation with memory               |
| `editor.html` | Mini-IDE — fill in, generate, transform, analyze   |
| `site.js`     | Shared `API_URL` + `apiHealth`/`apiPost`/`apiGet`  |
| `script.js`   | Chat logic (used by `index.html` and `chat.html`)  |
| `editor.js`   | Mini-IDE logic                                     |
| `style.css`   | Win95 desktop theme shared by all pages            |

### Pointing the site at your server

`site.js` holds the one line to change:

```js
const API_URL = 'https://no-inference-production.up.railway.app';
```

Point it at any running API server — the Railway deploy, or locally:

```js
const API_URL = 'http://localhost:8000';
```

Then serve the static files any way you like (GitHub Pages, or
`python3 -m http.server` in the branch directory). Every page shows a
status dot that pings `/health` on load, so it's obvious when the API is
offline: the chat falls back to a small scripted demo mode, the editor
shows an error.

## The API (`main` branch, `src/api/server.py`)

Run it from the `src/` directory:

```bash
cd src
python3 -m api.server     # port via COS_API_PORT / PORT, default 8000
```

### What the chat pages call

- `GET /health` — liveness, used by the status dots
- `POST /query` (alias: `POST /api/query`) — single-shot chat
  `{"query": "..."}` → `{"response": "...", "timing": ...}`
- `POST /api/conversations`, `POST/GET/DELETE /api/conversations/{id}` —
  conversation memory (the site currently uses single-shot `/query`)

### What the editor page calls (all `POST`, JSON)

- `POST /api/editor/analyze` — `{"code", "filename"}` → language,
  imports, definitions, indent, quote style, type hints
- `POST /api/editor/fill` — `{"code", "instruction", "filename"}` →
  `complete_buffer` result plus `edited` (full-buffer preview with the
  insertion applied to the marker line)
- `POST /api/editor/generate` — `{"query"}` → full markdown answer plus
  the fenced code block extracted as `code`/`lang`
- `POST /api/editor/transform` — `{"query", "code", "filename"}` →
  applies a transformation to the buffer. The instruction can name the
  operation without pasting code ("convert this to javascript", "add
  error handling", "rename total to sum", "add comments", "make it
  faster", "convert the for loop to a while loop", "explain this code"),
  or embed the code in the query. Unknown instructions return
  `"ok": false` — the engine never guesses.

### The editor flow (what `editor.js` does)

1. Send the buffer text + filename + instruction to the endpoint.
2. Read `edited` (or `code`) and `notes` from the response.
3. Offer "Copy" and "Load into editor" so the visitor can keep the result.

Nothing is ever written to disk by the API — it's a preview service.

### Index and CORS

- `GET /` returns a small JSON index listing the endpoints (the frontend
  lives elsewhere, so the root is discoverable instead of a dead 404).
- Every JSON response carries `Access-Control-Allow-Origin: *` and the
  server answers OPTIONS preflights, so the gh-pages site can call it
  cross-origin.

## Keeping it cheap

- Engine modules (`cos.code_editor`, `cos.code_gen`,
  `cos.code_transformer`) are imported *inside* the handlers, so the
  server never pays for the coding machinery unless an editor call
  arrives.
- The knowledge base is never loaded at startup; `/api/status` reads a
  cheap entry count.

First editor call in a fresh process is slower (module import + regex
compilation), subsequent calls are fast.
