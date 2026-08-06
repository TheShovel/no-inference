// Mini-IDE page logic. API_URL and the fetch helpers live in site.js.
const codeEl = document.getElementById('code');
const instEl = document.getElementById('instruction');
const fileEl = document.getElementById('filename');
const badgeEl = document.getElementById('langBadge');
const resEl = document.getElementById('result');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');

const EXT_LANG = { py:'python', py3:'python', js:'javascript', mjs:'javascript', cjs:'javascript',
  ts:'typescript', java:'java', c:'c', h:'c', cpp:'c++', cc:'c++', hpp:'c++', cs:'c#',
  go:'go', rs:'rust', rb:'ruby', php:'php', sql:'sql', sh:'bash', bash:'bash',
  html:'html', css:'css' };

function updateBadge() {
  const name = fileEl.value.trim();
  const ext = name.includes('.') ? name.split('.').pop().toLowerCase() : '';
  const lang = EXT_LANG[ext] || (ext ? '?' : 'python');
  badgeEl.textContent = lang;
  return lang;
}
fileEl.addEventListener('input', updateBadge);

// ── server status ────────────────────────────────────────────────────────
async function checkServer() {
  statusDot.className = 'status-dot off';
  statusText.textContent = 'Checking for local server...';
  try {
    if (await apiHealth()) {
      statusDot.className = 'status-dot on';
      statusText.textContent = 'Connected to server';
    } else {
      statusDot.className = 'status-dot demo';
      statusText.textContent = 'Server offline (set API_URL in site.js)';
    }
  } catch {
    statusDot.className = 'status-dot demo';
    statusText.textContent = 'Server offline (set API_URL in site.js)';
  }
}
checkServer();

// ── result rendering ─────────────────────────────────────────────────────
function outBlock(label, code, loadable) {
  const div = document.createElement('div');
  div.className = 'out-block';
  const head = document.createElement('div');
  head.className = 'out-head';
  const lbl = document.createElement('span');
  lbl.textContent = label;
  head.appendChild(lbl);
  const actions = document.createElement('span');
  actions.className = 'out-actions';
  const copy = document.createElement('button');
  copy.textContent = 'Copy';
  copy.onclick = () => {
    navigator.clipboard.writeText(code);
    copy.textContent = 'Copied';
    setTimeout(() => { copy.textContent = 'Copy'; }, 1200);
  };
  actions.appendChild(copy);
  if (loadable) {
    const use = document.createElement('button');
    use.textContent = 'Load into editor';
    use.onclick = () => { codeEl.value = code; updateBadge(); };
    actions.appendChild(use);
  }
  head.appendChild(actions);
  const pre = document.createElement('pre');
  pre.className = 'out-code';
  pre.textContent = code;
  div.appendChild(head);
  div.appendChild(pre);
  return div;
}

function notesList(notes) {
  if (!notes || !notes.length) return null;
  const ul = document.createElement('ul');
  ul.className = 'notes';
  notes.forEach(n => {
    const li = document.createElement('li');
    li.textContent = n;
    ul.appendChild(li);
  });
  return ul;
}

function errorBox(msg) {
  const d = document.createElement('div');
  d.className = 'error';
  d.textContent = msg;
  return d;
}

function metaGrid(rows) {
  const g = document.createElement('div');
  g.className = 'meta-grid';
  rows.forEach(([k, v]) => {
    const kk = document.createElement('span');
    kk.className = 'meta-k';
    kk.textContent = k + ':';
    const vv = document.createElement('span');
    vv.className = 'meta-v';
    vv.textContent = Array.isArray(v) ? (v.length ? v.join(', ') : '—') : String(v);
    g.appendChild(kk);
    g.appendChild(vv);
  });
  return g;
}

function showResult(parts) {
  resEl.innerHTML = '';
  parts.forEach(p => { if (p) resEl.appendChild(p); });
}

// ── actions ──────────────────────────────────────────────────────────────
async function run(action) {
  const code = codeEl.value;
  const instruction = instEl.value.trim();
  if (!code.trim() && action !== 'generate') {
    showResult([errorBox('The buffer is empty — paste some code first.')]);
    return;
  }
  if (!instruction && action === 'generate') {
    showResult([errorBox("Type what you want generated, e.g. 'write a python function that flattens a nested list'.")]);
    return;
  }
  const btns = document.querySelectorAll('.btn-row button');
  btns.forEach(b => { b.disabled = true; });
  try {
    if (action === 'analyze') {
      const d = await apiPost('/api/editor/analyze', { code, filename: fileEl.value });
      badgeEl.textContent = d.language;
      showResult([
        metaGrid([
          ['language', d.language], ['line count', d.line_count],
          ['indent', d.indent.kind + ' · ' + d.indent.unit],
          ['quote style', d.quote_style], ['type hints', d.type_hints ? 'yes' : 'no'],
          ['imports', d.imports], ['definitions', (d.definitions || []).map(x => x.join(' '))]
        ])
      ]);
    } else if (action === 'fill') {
      const d = await apiPost('/api/editor/fill', { code, instruction, filename: fileEl.value });
      if (d.language) badgeEl.textContent = d.language;
      const parts = [];
      if (d.edited) parts.push(outBlock('Edited buffer', d.edited, true));
      const nl = notesList(d.notes);
      if (nl) parts.push(nl);
      if (!d.changed && !(d.notes && d.notes.length)) {
        parts.push(errorBox('No fill-in marker found. Add `...`, a bare `pass`, or an empty { } where the body should go.'));
      }
      showResult(parts);
    } else if (action === 'transform') {
      if (!instruction) {
        showResult([errorBox("Type a transform instruction, e.g. 'convert this to javascript' or 'add error handling'.")]);
        return;
      }
      const d = await apiPost('/api/editor/transform', { query: instruction, code, filename: fileEl.value });
      if (d.language) badgeEl.textContent = d.language;
      const parts = [];
      if (d.changed) parts.push(outBlock('Transformed (' + d.op + ')', d.edited, d.op !== 'explain'));
      const nl = notesList(d.notes);
      if (nl) parts.push(nl);
      if (!d.changed && !(d.notes && d.notes.length)) {
        parts.push(errorBox('No changes were made.'));
      }
      showResult(parts);
    } else if (action === 'generate') {
      const d = await apiPost('/api/editor/generate', { query: instruction });
      const parts = [];
      if (d.code) parts.push(outBlock('Generated code (' + d.lang + ')', d.code, true));
      parts.push(outBlock('Full answer', d.markdown, false));
      showResult(parts);
    }
  } catch (e) {
    showResult([errorBox('Request failed: ' + e.message)]);
  } finally {
    btns.forEach(b => { b.disabled = false; });
  }
}

// ── example prompts ──────────────────────────────────────────────────────
const EXAMPLES = {
  fill: {
    filename: 'primes.py',
    code: 'def is_prime(n: int) -> bool:\n    """Return True if n is prime, False otherwise."""\n    ...\n',
    instruction: 'fill in the function body'
  },
  convert: {
    filename: 'tool.py',
    code: 'def count_words(text: str) -> int:\n    """Return the number of words in text."""\n    return len(text.split())\n',
    instruction: 'convert this to javascript'
  },
  errors: {
    filename: 'backup.py',
    code: 'import os\nimport shutil\nfrom datetime import datetime\n\n\ndef backup(source: str, dest_root: str = "backups") -> str:\n    dest = os.path.join(dest_root, datetime.now().strftime("%Y%m%d-%H%M%S"))\n    shutil.copytree(source, dest)\n    return dest\n',
    instruction: 'add error handling'
  }
};

function example(name) {
  const e = EXAMPLES[name];
  if (!e) return;
  fileEl.value = e.filename;
  codeEl.value = e.code;
  instEl.value = e.instruction;
  updateBadge();
  run(name === 'fill' ? 'fill' : 'transform');
}
