// Shared config + helpers for the no-inference website.
//
// The website (this branch) is a static frontend. All real answers come
// from the API server. Point API_URL at your server:
//   - Railway deploy (default), or
//   - http://localhost:8000  when running `python3 -m api.server` locally
//     from the src/ directory of the main branch.
const API_URL = 'https://no-inference-production.up.railway.app';

// Collapse/expand a Win95 window body.
function toggleMinimize(btn) {
  const body = btn.closest('.window').querySelector('.window-body');
  body.style.display = body.style.display === 'none' ? '' : 'none';
}

// Health check used by the status dots.
async function apiHealth() {
  const resp = await fetch(API_URL + '/health', { signal: AbortSignal.timeout(4000) });
  return resp.ok;
}

async function apiGet(path) {
  const resp = await fetch(API_URL + path, { signal: AbortSignal.timeout(15000) });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || ('API error ' + resp.status));
  return data;
}

async function apiPost(path, body) {
  const resp = await fetch(API_URL + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
    signal: AbortSignal.timeout(60000)  // first engine call loads modules
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || ('API error ' + resp.status));
  return data;
}
