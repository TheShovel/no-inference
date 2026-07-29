"""
COS Web API — Zero-dependency HTTP server using only Python stdlib.

Endpoints:
  POST /api/query          Single-shot query (no conversation history)
  POST /api/conversations  Create a new conversation
  GET  /api/conversations  List all conversations
  POST /api/conversations/{id}/query  Query within a conversation
  GET  /api/conversations/{id}        Get conversation history
  DELETE /api/conversations/{id}      Delete a conversation
  GET  /api/status         System status
  GET  /health             Health check
"""

import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# ── COS Engine Imports ──────────────────────────────────────────────────────

_SRC_DIR = Path(__file__).parent.parent.resolve()
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from cos.engine import process_query, reset_conversation, get_conversation_history


# ── Inline HTML Chat Interface ────────────────────────────────────────────────

_CHAT_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>COS Chat</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0d1117; color: #e6edf3; height: 100vh; display: flex; flex-direction: column; }
  #chat { flex: 1; overflow-y: auto; padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; scroll-behavior: smooth; }
  .msg { max-width: 80%; padding: 12px 16px; border-radius: 12px; line-height: 1.6; font-size: 14px; white-space: pre-wrap; word-wrap: break-word; }
  .msg.user { align-self: flex-end; background: #1f6feb; color: #fff; border-bottom-right-radius: 4px; }
  .msg.bot { align-self: flex-start; background: #161b22; color: #e6edf3; border: 1px solid #21262d; border-bottom-left-radius: 4px; }
  .msg.bot.loading { opacity: 0.6; }
  .msg.bot.loading::after { content: "..."; animation: dots 1.5s steps(4) infinite; }
  @keyframes dots { 0% { content: ""; } 25% { content: "."; } 50% { content: ".."; } 75% { content: "..."; } }
  .input-area { padding: 16px 24px; border-top: 1px solid #21262d; background: #0d1117; }
  .input-row { display: flex; gap: 8px; max-width: 900px; margin: 0 auto; }
  .input-row input { flex: 1; padding: 10px 14px; border: 1px solid #30363d; border-radius: 8px; background: #161b22; color: #e6edf3; font-size: 14px; outline: none; }
  .input-row input:focus { border-color: #58a6ff; }
  .input-row input::placeholder { color: #484f58; }
  .input-row button { padding: 10px 20px; border: none; border-radius: 8px; background: #238636; color: #fff; font-size: 14px; font-weight: 500; cursor: pointer; transition: background .15s; }
  .input-row button:hover { background: #2ea043; }
  .input-row button:disabled { opacity: 0.5; cursor: not-allowed; }
  .welcome { text-align: center; padding: 40px 20px; color: #8b949e; }
  .welcome h2 { font-size: 22px; color: #e6edf3; margin-bottom: 8px; }
  .welcome p { font-size: 14px; }
  .welcome .examples { margin-top: 16px; display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
  .welcome .examples button { padding: 6px 14px; border: 1px solid #30363d; border-radius: 20px; background: #161b22; color: #8b949e; font-size: 12px; cursor: pointer; transition: all .15s; }
  .welcome .examples button:hover { border-color: #58a6ff; color: #58a6ff; }
  @media (max-width: 600px) { .msg { max-width: 90%; } #chat { padding: 12px; } .input-area { padding: 12px; } }
</style>
</head>
<body>
<div id="chat">
  <div class="welcome" id="welcome">
    <h2>How can I help you?</h2>
    <p>Ask me anything — I use knowledge lookup, Wikipedia, and symbolic reasoning.</p>
    <div class="examples">
      <button onclick="ask('What is the capital of France?')">Capital of France</button>
      <button onclick="ask('How do fungi communicate underground?')">Fungi communication</button>
      <button onclick="ask('What would happen if all plants disappeared?')">Plants disappear</button>
      <button onclick="ask('Write a Python function to sort a list')">Python sort</button>
      <button onclick="ask('Tell me about the Roman Empire')">Roman Empire</button>
    </div>
  </div>
</div>
<div class="input-area">
  <div class="input-row">
    <input id="input" type="text" placeholder="Type your message..." autofocus>
    <button id="sendBtn" onclick="send()">Send</button>
  </div>
</div>
<script>
  let convId = null;
  const chat = document.getElementById("chat");
  const input = document.getElementById("input");
  const sendBtn = document.getElementById("sendBtn");

  function scrollBottom() { requestAnimationFrame(() => { chat.scrollTop = chat.scrollHeight; }); }

  function addMessage(text, role) {
    const el = document.createElement("div");
    el.className = "msg " + role;
    el.textContent = text;
    chat.appendChild(el);
    scrollBottom();
    return el;
  }

  function addLoading() {
    const el = document.createElement("div");
    el.className = "msg bot loading";
    el.textContent = "Thinking";
    chat.appendChild(el);
    scrollBottom();
    return el;
  }

  function hideWelcome() {
    const w = document.getElementById("welcome");
    if (w) w.style.display = "none";
  }

  async function ask(q) {
    input.value = q;
    await send();
  }

  async function send() {
    const q = input.value.trim();
    if (!q) return;
    input.value = "";
    hideWelcome();
    addMessage(q, "user");
    const loader = addLoading();
    sendBtn.disabled = true;
    try {
      if (!convId) {
        const r = await fetch("/api/conversations", { method: "POST" });
        const c = await r.json();
        convId = c.id;
      }
      const r = await fetch("/api/conversations/" + convId + "/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q })
      });
      const d = await r.json();
      loader.className = "msg bot";
      loader.textContent = d.response || "[no response]";
    } catch (e) {
      loader.className = "msg bot";
      loader.textContent = "[Error: " + e.message + "]";
    }
    sendBtn.disabled = false;
    input.focus();
    scrollBottom();
  }

  input.addEventListener("keydown", e => { if (e.key === "Enter") send(); });
</script>
</body>
</html>'''

# ── In-Memory Conversation Store ─────────────────────────────────────────────

_CONVERSATIONS: dict = {}  # id -> {created_at, updated_at, turns, _created_ts}
_START_TIME = time.time()
_KB_SIZE = 0
_CONVERSATION_TTL = 7 * 24 * 3600  # 7 days in seconds


def _cleanup_expired():
    """Remove conversations older than 7 days."""
    now = time.time()
    expired = [cid for cid, c in _CONVERSATIONS.items()
               if now - c.get("_created_ts", 0) > _CONVERSATION_TTL]
    for cid in expired:
        del _CONVERSATIONS[cid]
    return len(expired)


def _load_kb_size():
    """Count KB entries for status."""
    global _KB_SIZE
    try:
        from cos.knowledge import get_all_knowledge
        _KB_SIZE = len(get_all_knowledge())
    except Exception:
        _KB_SIZE = 0


def _json_response(handler, data, status=200):
    """Send a JSON response."""
    body = json.dumps(data, indent=2).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.end_headers()
    handler.wfile.write(body)


def _error_response(handler, status, message):
    _json_response(handler, {"error": message}, status)


def _read_body(handler) -> str:
    """Read the request body as text."""
    length = int(handler.headers.get('Content-Length', 0))
    if length > 0:
        return handler.rfile.read(length).decode('utf-8')
    return ''


def _parse_json_body(handler):
    """Parse the request body as JSON, returning a dict or None."""
    try:
        body = _read_body(handler)
        if body:
            return json.loads(body)
    except (json.JSONDecodeError, ValueError):
        pass
    return None


# ── Request Handler ──────────────────────────────────────────────────────────

class COSAPIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the COS API."""

    def log_message(self, format, *args):
        """Quiet logging — only log errors."""
        if args and args[0].startswith('40'):
            super().log_message(format, *args)

    def _route(self):
        """Parse the path and route to the appropriate handler."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        method = self.command

        # CORS preflight
        if method == 'OPTIONS':
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            return

        # Public endpoints
        if path == '/health' and method == 'GET':
            return self._handle_health()
        if path == '/api/status' and method == 'GET':
            return self._handle_status()

        # Serve chat interface at root
        if path in ('', '/') and method == 'GET':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(_CHAT_HTML)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(_CHAT_HTML.encode('utf-8'))
            return

        # API endpoints
        if path in ('/api/query', '/query') and method == 'POST':
            return self._handle_single_query()
        if path == '/api/conversations' and method == 'POST':
            return self._handle_create_conversation()
        if path == '/api/conversations' and method == 'GET':
            return self._handle_list_conversations()

        # /api/conversations/{id} routes
        conv_match = re.match(r'^/api/conversations/([a-zA-Z0-9\-]+)$', path)
        conv_query_match = re.match(r'^/api/conversations/([a-zA-Z0-9\-]+)/query$', path)

        if conv_query_match and method == 'POST':
            return self._handle_conversation_query(conv_query_match.group(1))
        if conv_match and method == 'GET':
            return self._handle_get_conversation(conv_match.group(1))
        if conv_match and method == 'DELETE':
            return self._handle_delete_conversation(conv_match.group(1))

        # 404
        _error_response(self, 404, f"Not found: {method} {path}")

    def do_GET(self):
        self._route()

    def do_POST(self):
        self._route()

    def do_DELETE(self):
        self._route()

    def do_OPTIONS(self):
        self._route()

    # ── Handlers ────────────────────────────────────────────────────────────

    def _handle_health(self):
        _json_response(self, {"status": "ok"})

    def _handle_status(self):
        total_turns = sum(len(c["turns"]) for c in _CONVERSATIONS.values())
        _json_response(self, {
            "status": "ok",
            "version": "1.0.0",
            "uptime_seconds": round(time.time() - _START_TIME, 1),
            "kb_entries": _KB_SIZE or 0,
            "conversations_active": len(_CONVERSATIONS),
            "conversations_total": total_turns,
        })

    def _handle_single_query(self):
        """Process a single query with no conversation history."""
        data = _parse_json_body(self)
        if not data or not data.get('query', '').strip():
            return _error_response(self, 400, "Query cannot be empty")

        query = data['query'].strip()
        debug = data.get('debug', False)

        saved_history = list(get_conversation_history())
        start_t = time.time()
        try:
            reset_conversation()
            response = process_query(query, use_cos=True)
        except Exception as e:
            response = f"[Error: {e}]"
        elapsed = round(time.time() - start_t, 3)

        # Restore original conversation state
        from cos.state import conversation_history as _ch
        _ch.clear()
        _ch.extend(saved_history)

        result = {
            "response": response or "[No response]",
            "timing": elapsed,
        }
        if debug:
            result["intent"] = None
        _json_response(self, result)

    def _handle_create_conversation(self):
        """Create a new conversation."""
        _cleanup_expired()
        data = _parse_json_body(self)

        conv_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        title = data.get('title', f"Conversation {conv_id}") if data and isinstance(data, dict) else f"Conversation {conv_id}"

        _CONVERSATIONS[conv_id] = {
            "id": conv_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "turns": [],
            "_created_ts": time.time(),
        }

        _json_response(self, {
            "id": conv_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "turn_count": 0,
            "turns": [],
        }, 201)

    def _handle_list_conversations(self):
        """List all conversations, most recent first."""
        _cleanup_expired()
        params = parse_qs(urlparse(self.path).query)
        try:
            limit = int(params.get('limit', [50])[0])
        except (ValueError, IndexError):
            limit = 50

        convs = list(_CONVERSATIONS.values())
        convs.sort(key=lambda c: c["updated_at"], reverse=True)
        convs = convs[:limit]

        result = []
        for c in convs:
            result.append({
                "id": c["id"],
                "title": c["title"],
                "created_at": c["created_at"],
                "updated_at": c["updated_at"],
                "turn_count": len(c["turns"]),
                "turns": c["turns"][-5:],
            })
        _json_response(self, result)

    def _handle_get_conversation(self, conv_id):
        """Get a conversation by ID."""
        _cleanup_expired()
        conv = _CONVERSATIONS.get(conv_id)
        if not conv:
            return _error_response(self, 404, "Conversation not found")

        _json_response(self, {
            "id": conv["id"],
            "title": conv["title"],
            "created_at": conv["created_at"],
            "updated_at": conv["updated_at"],
            "turn_count": len(conv["turns"]),
            "turns": conv["turns"],
        })

    def _handle_delete_conversation(self, conv_id):
        """Delete a conversation."""
        _cleanup_expired()
        if conv_id not in _CONVERSATIONS:
            return _error_response(self, 404, "Conversation not found")
        del _CONVERSATIONS[conv_id]
        _json_response(self, {"status": "deleted", "id": conv_id})

    def _handle_conversation_query(self, conv_id):
        """Query within a conversation."""
        _cleanup_expired()
        conv = _CONVERSATIONS.get(conv_id)
        if not conv:
            return _error_response(self, 404, "Conversation not found")

        data = _parse_json_body(self)
        if not data or not data.get('query', '').strip():
            return _error_response(self, 400, "Query cannot be empty")

        query = data['query'].strip()

        from cos.state import conversation_history as _ch

        # Restore this conversation's history into the engine
        reset_conversation()
        for turn in conv["turns"]:
            _ch.append((turn["query"], turn["response"]))

        # Process the query
        start_t = time.time()
        try:
            response = process_query(query, use_cos=True)
        except Exception as e:
            response = f"[Error: {e}]"
        elapsed = round(time.time() - start_t, 3)

        # Save turn
        now = datetime.now(timezone.utc).isoformat()
        turn = {
            "query": query,
            "response": response or "[No response]",
            "timing": elapsed,
            "timestamp": now,
        }
        conv["turns"].append(turn)
        conv["updated_at"] = now

        _json_response(self, {
            "response": response or "[No response]",
            "timing": elapsed,
        })


# ── Entry Point ──────────────────────────────────────────────────────────────

def main():
    """Run the API server using stdlib http.server."""
    port = int(os.environ.get("COS_API_PORT", os.environ.get("PORT", "8000")))
    host = os.environ.get("COS_API_HOST", "0.0.0.0")

    _load_kb_size()
    print(f"  Loaded {_KB_SIZE} knowledge entries from data/knowledge/")

    server = HTTPServer((host, port), COSAPIHandler)
    print(f"  Chat UI:    http://{host}:{port}")
    print(f"  API:        http://{host}:{port}/api/query")
    print(f"  Status:     http://{host}:{port}/api/status")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        server.server_close()


if __name__ == "__main__":
    main()
