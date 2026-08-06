"""
COS Web API — Zero-dependency HTTP server using only Python stdlib.

JSON API only: the demo pages (landing, chat, code editor) live on the
gh-pages branch of the website and talk to this server over HTTP.

Endpoints:
  GET  /                       API index (JSON endpoint list)
  POST /api/query              Single-shot query (no conversation history)
  POST /api/conversations      Create a new conversation
  GET  /api/conversations      List all conversations
  POST /api/conversations/{id}/query  Query within a conversation
  GET  /api/conversations/{id}        Get conversation history
  DELETE /api/conversations/{id}      Delete a conversation
  POST /api/editor/analyze     Analyze a buffer (language/imports/definitions)
  POST /api/editor/fill        Fill in a marker in a buffer (complete_buffer)
  POST /api/editor/generate    Generate code from a query (generate_code)
  POST /api/editor/transform   Apply a code transformation to a buffer
  GET  /api/status             System status
  GET  /health                 Health check
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


# ── API Only ────────────────────────────────────────────────────────────────
# The demo pages (landing, chat, code editor) live on the gh-pages branch of
# the website. This server is the API backend those pages talk to; it serves
# JSON only.

def _detect_buffer_transform(query: str):
    """Detect a transform op from the instruction alone (code not pasted).

    The mini-IDE applies transforms to the buffer, so the code lives in the
    textarea rather than inside the query. Returns (op, params) or (None, {}).
    Mirrors the phrasing rules of cos.code_transformer.detect_code_transform
    minus the requirement that code be embedded in the query.
    """
    q = re.sub(r'\s+', ' ', query.strip().lower())
    if len(q) < 4:
        return None, {}
    _LANGS = {'python', 'javascript', 'js', 'typescript', 'ts', 'java', 'c++',
              'cpp', 'c#', 'csharp', 'go', 'golang', 'rust', 'ruby', 'php',
              'swift', 'kotlin', 'scala', 'sql', 'bash', 'html', 'css', 'c'}
    # convert / translate / port / rewrite ... to <language>
    m = re.search(r'\b(?:convert|translate|port|rewrite|migrate|change)\s+'
                  r'(?:this|the|that|it)?\s*(?:code|script|program|function)?'
                  r'\s*(?:from\s+\S+)?\s*(?:to|into|in)\s+'
                  r'([a-z#+.\s]+?)\s*$', q)
    if m:
        dst = m.group(1).strip().rstrip('?!.')
        if re.sub(r'\s+', '', dst.lower()) in _LANGS:
            return 'convert_lang', {'dst': dst}
    # add / implement error handling
    if (re.search(r'\b(?:add|include|implement|insert)\s+(?:error|exception)'
                  r'\s+handling\b', q)
            or re.search(r'\b(?:make|wrap)\s+(?:it|this|that|the\s+code|'
                         r'this\s+code)\s*(?:more\s+)?(?:error\s+)?'
                         r'(?:safe|robust)\b', q)):
        return 'add_errors', {}
    # rename an identifier
    m = re.search(r'\b(?:rename|change)\s+(?:the\s+)?(?:variable|function|'
                  r'class|method|parameter|argument|name)\s+'
                  r'([A-Za-z_]\w*)\s+(?:to|into)\s+([A-Za-z_]\w*)\b', q)
    if not m:
        m = re.search(r'\brename\s+([A-Za-z_]\w*)\s+(?:to|into)\s+'
                      r'([A-Za-z_]\w*)\b', q)
    if not m:
        # "change foo to bar" without a noun — only when both sides look
        # like identifiers (not pronouns/colors/function words)
        m = re.search(r'\bchange\s+([A-Za-z_]\w*)\s+(?:to|into)\s+'
                      r'([A-Za-z_]\w*)\b', q)
        if m:
            from cos.code_transformer import _IDENTIFIER_STOPWORDS
            if not _IDENTIFIER_STOPWORDS.isdisjoint({m.group(1), m.group(2)}):
                m = None
    if m:
        return 'rename', {'old': m.group(1), 'new': m.group(2)}
    # add comments / document
    if (re.search(r'\b(?:add|write|insert)\s+(?:some\s+|more\s+)?comments?\b', q)
            or re.search(r'\b(?:document|comment)\s+(?:this|the)\s+'
                         r'(?:code|script)\b', q)):
        return 'add_comments', {}
    # make faster / optimize
    if (re.search(r'\b(?:make|speed\s+up)\s+(?:this|the|it|that)\s*'
                  r'(?:code|script|function|program)?\s*(?:faster|quicker|'
                  r'more\s+efficient|efficient)\b', q)
            or re.search(r'\boptimize\s+(?:this|the)\s+(?:code|script|'
                         r'function|program)\b', q)):
        return 'make_faster', {}
    # loop conversion
    m = re.search(r'\b(?:convert|change|rewrite|turn)\s+(?:the\s+|this\s+)?'
                  r'(for\s+loop|while\s+loop)\s+(?:to|into)\s+(?:a\s+)?'
                  r'(for\s+loop|while\s+loop)\b', q)
    if m:
        return 'loop_convert', {'from': m.group(1), 'to': m.group(2)}
    # explain
    if (re.search(r'\bexplain\s+(?:this|the|that)\s+(?:code|script|'
                  r'function|program)\b', q)
            or re.search(r'\bwhat\s+does\s+(?:this|the|that)\s+'
                         r'(?:code|script)\s+do\b', q)):
        return 'explain', {}
    return None, {}


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
    """Count KB entries for status without loading the full compiled KB.

    Loading the 45k compiled patterns costs ~120 MB; a cheap JSON parse
    gives the same count for the status line.
    """
    global _KB_SIZE
    try:
        from cos.knowledge import count_knowledge_entries
        _KB_SIZE = count_knowledge_entries()
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
        """Quiet logging — only log client/server errors.

        Defensive about arg types: some error paths pass an HTTPStatus enum
        (Python 3.11+) or an int, neither of which has .startswith.
        """
        try:
            code = getattr(args[0], 'value', args[0]) if args else None
            if code is not None and str(code).startswith(('4', '5')):
                super().log_message(format, *args)
        except (TypeError, AttributeError):
            pass

    def do_HEAD(self):
        """HEAD: same status as GET, headers only (uptime monitors)."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        ok = (path in ('', '/', '/health', '/api/status')
              or path.startswith('/api/conversations'))
        self.send_response(200 if ok else 404)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', '0')
        self.end_headers()

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

        # API index (the demo frontend lives on the gh-pages site)
        if path in ('', '/') and method == 'GET':
            return self._handle_index()

        # API endpoints
        if path in ('/api/query', '/query') and method == 'POST':
            return self._handle_single_query()
        if path == '/api/conversations' and method == 'POST':
            return self._handle_create_conversation()
        if path == '/api/conversations' and method == 'GET':
            return self._handle_list_conversations()

        # Editor endpoints (buffer-aware coding demo)
        if path == '/api/editor/analyze' and method == 'POST':
            return self._handle_editor_analyze()
        if path == '/api/editor/fill' and method == 'POST':
            return self._handle_editor_fill()
        if path == '/api/editor/generate' and method == 'POST':
            return self._handle_editor_generate()
        if path == '/api/editor/transform' and method == 'POST':
            return self._handle_editor_transform()

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

    def _handle_index(self):
        """JSON index so the server root is discoverable (frontend on gh-pages)."""
        _json_response(self, {
            "service": "cos-api",
            "frontend": "https://theshovel.github.io/no-inference/",
            "endpoints": [
                "GET /health",
                "GET /api/status",
                "POST /api/query",
                "POST /api/conversations",
                "GET /api/conversations",
                "POST /api/conversations/{id}/query",
                "GET /api/conversations/{id}",
                "DELETE /api/conversations/{id}",
                "POST /api/editor/analyze",
                "POST /api/editor/fill",
                "POST /api/editor/generate",
                "POST /api/editor/transform",
            ],
        })

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

    # ── Editor endpoints (buffer-aware coding demo) ─────────────────────

    def _handle_editor_analyze(self):
        """Describe a buffer: language, imports, definitions, style."""
        data = _parse_json_body(self)
        code = (data or {}).get('code', '') if isinstance(data, dict) else ''
        filename = (data or {}).get('filename', '') if isinstance(data, dict) else ''
        if not code.strip():
            return _error_response(self, 400, "Buffer cannot be empty")
        from cos.code_editor import analyze_buffer
        result = analyze_buffer(code, filename)
        result["ok"] = True
        _json_response(self, result)

    def _handle_editor_fill(self):
        """Fill in a marker in the buffer (complete_buffer)."""
        data = _parse_json_body(self)
        if not isinstance(data, dict):
            return _error_response(self, 400, "Invalid JSON body")
        code = data.get('code', '')
        if not code.strip():
            return _error_response(self, 400, "Buffer cannot be empty")
        instruction = data.get('instruction', '') or ''
        filename = data.get('filename', '') or ''
        cursor = data.get('cursor_pos')
        if not isinstance(cursor, int):
            cursor = None
        from cos.code_editor import complete_buffer
        res = complete_buffer(code, instruction, cursor, filename)

        # Preview: apply the insertion to the marker line in the buffer.
        edited = None
        if res['changed'] and res['replace_line'] is not None and res['text']:
            lines = code.split('\n')
            rl = res['replace_line']
            if 0 <= rl < len(lines):
                lines[rl] = res['text']
                edited = '\n'.join(lines)

        message = 'Filled in the marker.' if res['changed'] else (
            res['notes'][0] if res.get('notes') else 'No fill-in marker found.')
        _json_response(self, {
            'ok': bool(res['changed']),
            'language': res['lang'],
            'text': res['text'],
            'notes': res.get('notes', []),
            'changed': bool(res['changed']),
            'replace_line': res['replace_line'],
            'edited': edited,
            'context': res.get('context'),
            'message': message,
        })

    def _handle_editor_generate(self):
        """Generate code from a query (generate_code)."""
        data = _parse_json_body(self)
        query = (data or {}).get('query', '') if isinstance(data, dict) else ''
        query = (query or '').strip()
        if not query:
            return _error_response(self, 400, "Query cannot be empty")
        from cos.code_gen import generate_code
        markdown = generate_code(query)
        if not markdown:
            return _json_response(self, {
                'ok': False,
                'error': ("I couldn't map that request to a code task. Try a "
                          "concrete task like 'write a python function that "
                          "flattens a nested list'."),
            })
        m = re.search(r'```(\w+)\n(.*?)```', markdown, re.DOTALL)
        _json_response(self, {
            'ok': True,
            'markdown': markdown,
            'code': m.group(2) if m else '',
            'lang': m.group(1) if m else '',
        })

    def _handle_editor_transform(self):
        """Apply a code transformation to the buffer.

        The instruction may embed the code (classic transform query) or
        reference the buffer alone ("convert this to javascript") — either
        way the buffer wins as the code being edited.
        """
        data = _parse_json_body(self)
        if not isinstance(data, dict):
            return _error_response(self, 400, "Invalid JSON body")
        query = (data.get('query', '') or '').strip()
        code = data.get('code', '')
        filename = data.get('filename', '') or ''
        if not query:
            return _error_response(self, 400, "Instruction cannot be empty")
        if not code.strip():
            return _error_response(self, 400, "Buffer cannot be empty")

        from cos.code_editor import detect_lang as _buffer_lang
        from cos.code_transformer import detect_code_transform, transform_code

        op, params = None, {}
        try:
            ct = detect_code_transform(query)
            if ct:
                op, params, _qcode, _qlang = ct
            else:
                op, params = _detect_buffer_transform(query)
        except Exception:
            op, params = None, {}

        if op is None:
            return _json_response(self, {
                'ok': False,
                'error': ("That instruction isn't a transform I recognize. Try "
                          "'convert this to javascript', 'add error handling', "
                          "'add comments', 'rename x to y', 'make it faster', "
                          "'convert the for loop to a while loop', or 'explain "
                          "this code'."),
            })

        lang = _buffer_lang(code, filename)
        edited, notes = transform_code(op, params, code, lang)
        _json_response(self, {
            'ok': True,
            'op': op,
            'edited': edited,
            'notes': notes,
            'language': lang,
            'changed': edited != code,
        })


# ── Entry Point ──────────────────────────────────────────────────────────────

def main():
    """Run the API server using stdlib http.server."""
    port = int(os.environ.get("COS_API_PORT", os.environ.get("PORT", "8000")))
    host = os.environ.get("COS_API_HOST", "0.0.0.0")

    _load_kb_size()
    print(f"  Loaded {_KB_SIZE} knowledge entries from data/knowledge/")

    server = HTTPServer((host, port), COSAPIHandler)
    print(f"  API server:  http://{host}:{port}")
    print(f"  Health:      http://{host}:{port}/health")
    print(f"  Status:      http://{host}:{port}/api/status")
    print(f"  Chat query:  http://{host}:{port}/api/query")
    print("  Frontend:    https://theshovel.github.io/no-inference/ (gh-pages)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        server.server_close()


if __name__ == "__main__":
    main()
