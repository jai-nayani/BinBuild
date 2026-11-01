// Runs the real app/app.js against a small fake page built from app/index.html
// and plays one batch with failed photos through the retake pop-up.
//
//   node tests/retake_popup_harness.js '<scenario json>'
//
// Scenario: {"notices": {view: retake notice}, "fail": [views that fail, in order]}.
// Prints JSON: for every pop-up shown, what the pop-up itself shows (its title,
// its own Retake button, the photo in it, the "How:" hint) and which view the
// retake was uploaded as. The pop-up's parts are found inside #retake-modal,
// not by id, so an id that also exists elsewhere on the page cannot hide a
// stale label. Used by tests/test_retake_popup.py; no network, no browser.

'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const APP = path.join(__dirname, '..', 'app');
const scenario = JSON.parse(process.argv[2]);

// --- the page: every element of index.html, nested as written ----------------

const VOID = new Set(['input', 'img', 'br', 'hr', 'meta', 'link', 'source', 'area', 'base', 'col', 'wbr']);

class El {
  constructor(tag, attrs) {
    this.tagName = tag.toUpperCase();
    this.attrs = attrs;
    this.id = attrs.id || '';
    this.children = [];
    this.parentNode = null;
    this.listeners = {};
    this.textContent = '';
    this.value = '';
    this.files = null;
    this.disabled = false;
    this.style = {};
    this.dataset = {};
    this.src = attrs.src || '';
    const classes = new Set((attrs.class || '').split(/\s+/).filter(Boolean));
    this.classList = {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      toggle: (c, on) => { const want = on === undefined ? !classes.has(c) : !!on; if (want) { classes.add(c); } else { classes.delete(c); } return want; },
      contains: (c) => classes.has(c),
    };
  }
  set innerHTML(_) { this.children = []; this.textContent = ''; }
  get innerHTML() { return ''; }
  appendChild(c) { if (c && typeof c === 'object') { c.parentNode = this; this.children.push(c); } return c; }
  insertBefore(c) { return this.appendChild(c); }
  removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; if (k === 'src') { this.src = ''; } }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  dispatch(type) { (this.listeners[type] || []).forEach((fn) => fn.call(this, { type, target: this, preventDefault() {} })); }
  click() { this.dispatch('click'); }
  focus() {}
  blur() {}
  scrollIntoView() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
  closest() { return null; }
  get hiddenByClass() { return this.classList.contains('hidden'); }
}

function parsePage(html) {
  const root = new El('html', {});
  const stack = [root];
  const body = html.replace(/<!--[\s\S]*?-->/g, '').replace(/<(script|style)\b[\s\S]*?<\/\1>/gi, '');
  const tag = /<(\/?)([a-zA-Z][a-zA-Z0-9-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>/g;
  let m;
  let last = 0;
  while ((m = tag.exec(body))) {
    const text = body.slice(last, m.index).trim();
    if (text) { stack[stack.length - 1].textContent += text; }
    last = tag.lastIndex;
    const name = m[2].toLowerCase();
    if (m[1]) {
      const at = stack.map((e) => e.tagName.toLowerCase()).lastIndexOf(name);
      if (at > 0) { stack.length = at; }
      continue;
    }
    const attrs = {};
    m[3].replace(/([a-zA-Z_:][-a-zA-Z0-9_:.]*)(?:\s*=\s*("([^"]*)"|'([^']*)'|[^\s"'>]+))?/g, (_, k, __, dq, sq) => {
      attrs[k.toLowerCase()] = dq !== undefined ? dq : sq !== undefined ? sq : '';
    });
    const el = new El(name, attrs);
    stack[stack.length - 1].appendChild(el);
    if (!VOID.has(name) && !/\/\s*$/.test(m[3])) { stack.push(el); }
  }
  return root;
}

function walk(el, fn) { fn(el); el.children.forEach((c) => walk(c, fn)); }
function find(el, test) { let hit = null; walk(el, (e) => { if (!hit && test(e)) { hit = e; } }); return hit; }

const root = parsePage(fs.readFileSync(path.join(APP, 'index.html'), 'utf8'));
const byId = (id) => find(root, (e) => e.id === id); // the first in document order, as a browser does

const document = {
  getElementById: byId,
  createElement: (t) => new El(t, {}),
  createElementNS: (_, t) => new El(t, {}),
  createTextNode: (t) => ({ textContent: String(t) }),
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
  body: root,
};

// --- the backend: answers the upload and each retake from the scenario -------

const notices = scenario.notices;
let failing = scenario.fail.slice();
const uploads = [];

class FakeXHR {
  constructor() { this.upload = {}; this.status = 0; this.responseText = ''; }
  open(method, url) { this.method = method; this.url = url; }
  setRequestHeader() {}
  send(body) {
    const p = this.url.replace(/^https?:\/\/[^/]+/, '');
    uploads.push({ method: this.method, path: p, files: body && body.entries ? body.entries.map((e) => e[2]) : [] });
    let reply;
    const retakeMatch = p.match(/^\/api\/inventory\/batch\/([^/]+)\/photos\/([^/?]+)$/);
    if (p === '/api/inventory/batch') {
      reply = [201, { batch_id: 'b1', ready: failing.length === 0, retake: failing.map((v) => notices[v]) }];
    } else if (retakeMatch) {
      const view = decodeURIComponent(retakeMatch[2]);
      failing = failing.filter((v) => v !== view);
      reply = [200, { batch_id: 'b1', view, passed: true, ready: failing.length === 0, retake: failing.map((v) => notices[v]) }];
    } else {
      reply = [404, { detail: 'not in this scenario' }];
    }
    this.status = reply[0];
    this.responseText = JSON.stringify(reply[1]);
    this.onload();
  }
}

class FakeFormData {
  constructor() { this.entries = []; }
  append(name, file, filename) { this.entries.push([name, file, filename]); }
}

const sandbox = {
  window: { location: { protocol: 'http:', hostname: 'phone.test' }, scrollTo() {}, confirm: () => true },
  document,
  navigator: {},
  console: { log() {}, warn() {}, error: (...a) => process.stderr.write(a.join(' ') + '\n') },
  XMLHttpRequest: FakeXHR,
  FormData: FakeFormData,
  URL: { createObjectURL: (f) => 'blob:' + f.name, revokeObjectURL() {} },
  fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok' }) }),
  setTimeout: () => 0,
  clearTimeout() {},
  setInterval: () => 0,
  clearInterval() {},
  encodeURIComponent,
  JSON,
  Math,
  Date,
};
sandbox.window.document = document;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(APP, 'app.js'), 'utf8'), sandbox, { filename: 'app.js' });

// --- play: 5 photos, upload, then each retake the pop-up asks for -------------

const VIEWS = ['top', 'front', 'right', 'back', 'left'];
const pick = (input, name) => { input.files = [{ name, type: 'image/jpeg' }]; input.dispatch('change'); };

VIEWS.forEach((v) => { pick(byId('camera-input'), 'shot-' + v + '.jpg'); byId('use-btn').click(); });
byId('upload-btn').click();

const modal = byId('retake-modal');
const inModal = (test) => find(modal, test);
const popups = [];
for (let k = 0; k < VIEWS.length + 1 && !modal.classList.contains('hidden'); k++) {
  const button = inModal((e) => e.tagName === 'LABEL' && e.attrs.for === 'retake-input');
  const shown = {
    title: inModal((e) => e.tagName === 'H2').textContent,
    button: button.textContent,
    image: (inModal((e) => e.tagName === 'IMG').src || '').replace(/^blob:shot-|\.jpg$/g, ''),
    hint: inModal((e) => e.id === 'retake-hint').textContent,
  };
  const before = uploads.length;
  pick(byId(button.attrs.for), 'retake-' + k + '.jpg');
  const sent = uploads.slice(before).find((u) => u.path.indexOf('/photos/') > 0);
  shown.uploaded_as = sent ? sent.path.split('/').pop() : null;
  shown.file_name = sent ? sent.files[0] : null;
  popups.push(shown);
}

const ids = [];
walk(root, (e) => { if (e.id) { ids.push(e.id); } });
process.stdout.write(JSON.stringify({
  popups,
  batch_upload: uploads[0] && uploads[0].files,
  modal_open_at_end: !modal.classList.contains('hidden'),
  duplicate_ids: ids.filter((id, i) => ids.indexOf(id) !== i),
}));
