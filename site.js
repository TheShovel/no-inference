// Shared config + helpers for the no-inference website.
//
// The website (this branch) is a static frontend. All real answers come
// from the API server. The default points at the deployed API; override
// it per-page with a ?api= query param (e.g. chat.html?api=http://localhost:8000)
// or by editing DEFAULT_API_URL below.
const DEFAULT_API_URL = 'https://no-inference-production.up.railway.app';
const API_URL = new URLSearchParams(location.search).get('api') || DEFAULT_API_URL;

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
