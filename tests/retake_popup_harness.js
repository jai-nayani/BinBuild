// Runs the real app/app.js against a small fake page built from app/index.html
// and plays one batch with failed photos through the retake pop-up.
//
//   node tests/retake_popup_harness.js '<scenario json>'
//
// Scenario: {"notices": {view: retake notice}, "fail": [views that fail, in order],
//            optional: "order": [views, tapped on the capture grid in this order before each photo],
//            "tap_failed": a failed view whose red panel is tapped after the check,
//            "identify": HTTP status for Identify (Next) once all 5 are clear, e.g. 401,
//            "use_sample": tap "Use sample images" at the end,
//            "open_builds": open "What can I build?" at the end, on an empty bin, then tap its sample button}.
// Prints JSON: for every pop-up shown, what the pop-up itself shows (its title,
// its own Retake button, the photo in it, the "How:" hint) and which view the
// retake was uploaded as. The pop-up's parts are found inside #retake-modal,
// not by id, so an id that also exists elsewhere on the page cannot hide a
// stale label. Also "ui": the hero, each grid panel's state and whether Next
// is enabled along the way, and the sample-bin offer; "requests": every call
// the app made. Used by tests/test_retake_popup.py and tests/test_hero_ui.py;
// no network, no browser.

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
    this.scrollLeft = 0;
    this._innerHTML = '';
    this.src = attrs.src || '';
    const classes = new Set((attrs.class || '').split(/\s+/).filter(Boolean));
    this.classSet = classes;
    this.classList = {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      toggle: (c, on) => { const want = on === undefined ? !classes.has(c) : !!on; if (want) { classes.add(c); } else { classes.delete(c); } return want; },
      contains: (c) => classes.has(c),
    };
  }
  set innerHTML(v) { this.children = []; this.textContent = ''; this._innerHTML = String(v || ''); }
  get innerHTML() { return this._innerHTML; }
  appendChild(c) { if (c && typeof c === 'object') { c.parentNode = this; this.children.push(c); } return c; }
  insertBefore(c) { return this.appendChild(c); }
  removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; if (k === 'src') { this.src = ''; } }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  dispatch(type) { (this.listeners[type] || []).forEach((fn) => fn.call(this, { type, target: this, preventDefault() {}, stopPropagation() {} })); }
  click() { this.dispatch('click'); }
  focus() { this.focused = true; }
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
let wonderPoll = 0;
const timers = [];

class FakeXHR {
  constructor() { this.upload = {}; this.status = 0; this.responseText = ''; }
  open(method, url) { this.method = method; this.url = url; }
  setRequestHeader() {}
  send(body) {
    const p = this.url.replace(/^https?:\/\/[^/]+/, '');
    uploads.push({ method: this.method, path: p, status: byId('status').textContent,
                   files: body && body.entries ? body.entries.map((e) => e[2]) : [],
                   sources: body && body.entries ? body.entries.map((e) => e[1].name) : [],
                   json: typeof body === 'string' ? body : null });
    let reply;
    const retakeMatch = p.match(/^\/api\/inventory\/batch\/([^/]+)\/photos\/([^/?]+)$/);
    const reclassifyMatch = p.match(/^\/api\/inventory\/batch\/([^/]+)\/pieces\/(\d+)\/reclassify$/);
    if (reclassifyMatch && scenario.reclassify_reply) {
      reply = [200, scenario.reclassify_reply];
    } else if (p === '/api/builds/options' && scenario.build_options) {
      reply = [200, scenario.build_options];
    } else if (p === '/api/builds/wonder' && this.method === 'POST' && scenario.wonder_job) {
      reply = scenario.wonder_job.post || [202, { job_id: 'job-1' }];
    } else if (/^\/api\/builds\/wonder\/jobs\//.test(p) && scenario.wonder_job) {
      reply = scenario.wonder_job.polls[wonderPoll++] || [500, { detail: 'unexpected poll' }];
    } else if (p === '/api/builds' && this.method === 'POST') {
      reply = [201, scenario.build_reply || { booklet_url: '/api/builds/7/booklet', steps: 5 }];
    } else if (p === '/api/inventory/batch') {
      reply = [201, { batch_id: 'b1', ready: failing.length === 0, retake: failing.map((v) => notices[v]) }];
    } else if (/\/classify\?segmenter=stub$/.test(p) && scenario.identify_flow) {
      reply = [200, { pieces: 2, detections: [] }];
    } else if (/\/classify\?segmenter=sam$/.test(p) && scenario.identify_flow) {
      reply = scenario.identify_flow.sam_status
        ? [scenario.identify_flow.sam_status, { detail: 'SAM service unavailable' }]
        : [200, { pieces: 2, detections: [], run: { sam_pass: { masks: 2, points: 2, sam: { seconds: 1.2 } } } }];
    } else if (/\/classify(?:\?.*)?$/.test(p) && scenario.identify) {
      reply = [scenario.identify, { detail: 'this calls a paid API, so on the public demo it needs the access key' }];
    } else if (p === '/api/inventory/summary') {
      reply = [200, { total_pieces: 50 }];
    } else if (p === '/api/inventory/sample') {
      reply = this.method === 'POST' ? [200, { batch_id: 'sample1', sample: true, loaded_now: true }]
        : [200, { batch_id: 'sample1', photos: 5, pieces: 50, loaded: false }];
    } else if (p === '/api/inventory/vocab') {
      reply = [200, scenario.vocab || { families: [], colors: [], shapes: [], generator_types: [] }];
    } else if (p === '/api/inventory/batch/sample1/review' && this.method === 'POST') {
      reply = [200, scenario.review_reply || { batch: { id: 'sample1', status: 'classified' },
                      detections: [], pieces: 50, photos_ready: true }];
    } else if (p === '/api/inventory/batch/b1/review' && scenario.identify_flow) {
      reply = [200, scenario.identify_flow.review || { batch: { id: 'b1', status: 'classified' },
                      detections: [], pieces: 2, photos_ready: true, count_photo: null }];
    } else if (p === '/api/inventory/batch/sample1/review') {
      reply = [200, scenario.review || { batch: { id: 'sample1', status: 'classified', classifier: 'sample: the kit batch, pre-computed' },
                      detections: [], pieces: 50, photos_ready: true, count_photo: null }];
    } else if (p === '/api/builds/options') {   // an empty bin: the backend sends no catalog, only scan_first
      reply = [200, { inventory: { total_pieces: 0, generator_ready: 0, other: 0 }, options: [],
                      scan_first: 'Nothing in your bin yet.' }];
    } else if (retakeMatch) {
      const view = decodeURIComponent(retakeMatch[2]);
      failing = failing.filter((v) => v !== view);
      reply = [200, { batch_id: 'b1', view, passed: true, ready: failing.length === 0, retake: failing.map((v) => notices[v]) }];
    } else {
      reply = [404, { detail: 'not in this scenario' }];
    }
    this.status = reply[0];
    this.responseText = JSON.stringify(reply[1]);
    if (this.status === 0) { this.onerror(); return; }
    this.onload();
  }
}

class FakeFormData {
  constructor() { this.entries = []; }
  append(name, file, filename) { this.entries.push([name, file, filename]); }
}

const sandbox = {
  // the home-network setup: the app on port 8080, the backend on port 8000
  window: { location: { protocol: 'http:', hostname: 'phone.test', port: '8080', origin: 'http://phone.test:8080',
                        hash: '', pathname: '/', search: '' }, scrollTo() {}, confirm: () => true },
  document,
  navigator: {},
  console: { log() {}, warn() {}, error: (...a) => process.stderr.write(a.join(' ') + '\n') },
  XMLHttpRequest: FakeXHR,
  FormData: FakeFormData,
  URL: { createObjectURL: (f) => 'blob:' + f.name, revokeObjectURL() {} },
  fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'ok' }) }),
  setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
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

const shown = (id) => !byId(id).classList.contains('hidden');
const visible = () => ['hero-view', 'capture-view', 'review-view', 'finished-view', 'check-view', 'build-view', 'booklet-view']
  .filter(shown);
const panels = () => Object.fromEntries(VIEWS.map((v) => [v,
  ['next', 'taken', 'passed', 'failed', 'locked'].filter((c) => byId('panel-' + v).classSet.has(c))]));
const ui = { hero_at_start: shown('hero-view'), capture_at_start: shown('capture-view') };
byId('start-btn').click();
ui.capture_after_start = shown('capture-view');
ui.hero_after_start = shown('hero-view');
ui.panels_at_start = panels();

(scenario.order || VIEWS).forEach((v) => {
  if (scenario.order) { byId('panel-' + v).click(); }
  pick(byId('camera-input'), 'shot-' + v + '.jpg');
  byId('use-btn').click();
});
ui.panels_before_upload = panels();
ui.next_enabled_before_upload = !byId('identify-btn').disabled;
byId('upload-btn').click();
ui.panels_after_upload = panels();
ui.next_enabled_after_upload = !byId('identify-btn').disabled;

const modal = byId('retake-modal');
if (scenario.tap_failed) {
  modal.classList.add('hidden');   // the user dismisses the first pop-up, then taps a red panel
  byId('panel-' + scenario.tap_failed).click();
  ui.tapped_failed_opens = modal.classList.contains('hidden') ? null
    : find(modal, (e) => e.tagName === 'H2').textContent;
}
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

ui.panels_at_end = panels();
ui.next_enabled_at_end = !byId('identify-btn').disabled;
if (scenario.identify) {
  byId('identify-btn').click();
  ui.sample_offer = { shown: shown('sample-offer'), button: byId('sample-bin-btn').textContent };
  byId('sample-bin-btn').click();
  ui.view_after_sample = visible();
  ui.check_title_after_sample = byId('check-title').textContent;
}
if (scenario.identify_flow) {
  byId('identify-btn').click();
  ui.identify_flow = { view: visible(), status: byId('check-status').textContent,
                       caption: byId('check-caption').textContent,
                       requests: uploads.filter((u) => /\/classify\?/.test(u.path))
                         .map((u) => ({ path: u.path, status: u.status })) };
}
const textsOf = (rootEl) => { const out = []; walk(rootEl, (e) => { if (e.textContent) { out.push(e.textContent); } }); return out; };
const buttonsIn = (rootEl) => { const out = []; walk(rootEl, (e) => { if (e.tagName === 'BUTTON') { out.push(e); } }); return out; };
const reviewSnapshot = () => ({
  view: visible(),
  status: byId('check-status').textContent,
  caption: byId('check-caption').textContent,
  groups: byId('check-list').children.map((g) => ({
    texts: textsOf(g), buttons: buttonsIn(g).map((b) => b.textContent),
  })),
  dots: byId('check-dots').children.map((d) => ({
    left: d.style.left, top: d.style.top,
    classes: ['on', 'focus', 'dim', 'hollow'].filter((c) => d.classList.contains(c)),
  })),
});

if (scenario.use_sample) {
  const before = uploads.length;
  byId('sample-images-btn').click();
  ui.view_after_use_sample = visible();
  ui.check_title_after_use_sample = byId('check-title').textContent;
  ui.use_sample_requests = uploads.slice(before).map((u) => u.method + ' ' + u.path);
}
if (scenario.review_actions) {
  ui.review_before = reviewSnapshot();
  const before = uploads.length;
  const retakes = buttonsIn(byId('check-list')).filter((b) => b.textContent === '📷 Retake this piece');
  ui.retake_buttons_before = retakes.length;
  if (retakes.length) {
    retakes[0].click();
    pick(byId('piece-input'), 'close-up.jpg');
  }
  ui.review_after_retake = reviewSnapshot();
  // the actions that were already there still work after a close-up update
  const click = (text) => { const b = buttonsIn(byId('check-list')).filter((x) => x.textContent.indexOf(text) === 0)[0]
                             || (byId('add-piece-btn').textContent.indexOf(text) === 0 ? byId('add-piece-btn') : null);
                            if (b) { b.click(); } return !!b; };
  ui.fix_opened = click('✎ Fix');
  ui.edit_modal_after_fix = !byId('edit-modal').classList.contains('hidden');
  byId('edit-save-btn').click();
  ui.remove_clicked = click('✕ Remove');
  ui.put_back_clicked = click('↩ Put back');
  ui.add_opened = click('＋ Add a piece');
  ui.edit_modal_after_add = !byId('edit-modal').classList.contains('hidden');
  if (ui.add_opened) { byId('edit-count').value = '1'; byId('edit-save-btn').click(); }
  ui.review_after_actions = reviewSnapshot();
  ui.review_requests = uploads.slice(before).map((u) => ({ method: u.method, path: u.path, json: u.json, files: u.files }));
}
if (scenario.open_builds) {
  byId('build-open-btn').click();
  const list = byId('build-list').children;
  const carousel = byId('build-carousel');
  ui.builds = {
    view: visible(), inventory_text: byId('build-inventory').textContent,
    list_order: list.map((e) => ({ tag: e.tagName, className: e.className || '', text: e.textContent })),
    catalog_entries: list.filter((e) => /\b(option|mrow|chapter|build-section)\b/.test(e.className || '')).length,
    buttons: list.filter((e) => e.tagName === 'BUTTON').map((e) => e.textContent),
    carousel: carousel ? {
      cards: carousel.children.map((c) => ({
        id: c.attrs['data-build-id'], classes: [c.className || ''],
        texts: c.children.map((x) => x.textContent), cover: c.children[0] ? c.children[0].innerHTML : '',
        child_classes: c.children.map((x) => x.className || ''),
      })),
      list_texts: textsOf(byId('build-list')),
    } : null,
  };
  if (scenario.wonder_job) {
    const wonder = find(byId('build-list'), (e) => e.className === 'wonder');
    const pick = find(wonder, (e) => e.tagName === 'SELECT');
    pick.value = scenario.wonder_job.target || 'a simple house';
    const button = buttonsIn(wonder).find((b) => b.textContent === '✨ Generate a new design');
    const status = find(wonder, (e) => e.className === 'status');
    let nextTimer = timers.length;
    button.click();
    const progress = [];
    for (let i = 0; i < 12 && nextTimer < timers.length; i++) {
      const timer = timers[nextTimer++];
      const before = status.textContent;
      timer.fn();
      progress.push({ delay: timer.ms, before, after: status.textContent });
    }
    const links = [];
    walk(wonder, (e) => { if (e.tagName === 'A') { links.push(e); } });
    ui.wonder = { progress, status: status.textContent, button_disabled: button.disabled,
                  text: textsOf(wonder), links: links.map((e) => ({ text: e.textContent, href: e.href })) };
    if (scenario.wonder_job.open_link && links.length) {
      links[0].click();
      ui.wonder.booklet = { view: visible(), title: byId('booklet-title').textContent, frame: byId('booklet-frame').src };
      byId('booklet-back-btn').click();
      ui.wonder.after_back = visible();
    }
  }
  if (scenario.tap_card !== undefined && carousel) {
    carousel.scrollLeft = scenario.carousel_scroll || 0;
    carousel.children[scenario.tap_card].click();
    ui.booklet = { view: visible(), title: byId('booklet-title').textContent, frame: byId('booklet-frame').src,
                   requests: uploads.slice(-1).map((u) => u.method + ' ' + u.path + ' ' + (u.json || '')) };
    byId('booklet-back-btn').click();
    ui.after_booklet_back = { view: visible(), scroll_left: carousel.scrollLeft,
                              focused_card: carousel.children[scenario.tap_card].focused ? carousel.children[scenario.tap_card].attrs['data-build-id'] : null };
  }
  const sampleButton = list.filter((e) => e.tagName === 'BUTTON' && e.textContent === 'Use sample images')[0];
  if (sampleButton) {
    const before = uploads.length;
    sampleButton.click();
    ui.prompt_sample_view = visible();
    ui.prompt_sample_requests = uploads.slice(before).map((u) => u.method + ' ' + u.path);
  }
}

const ids = [];
walk(root, (e) => { if (e.id) { ids.push(e.id); } });
process.stdout.write(JSON.stringify({
  popups,
  batch_upload: uploads.find((u) => u.path === '/api/inventory/batch').files,
  batch_sources: uploads.find((u) => u.path === '/api/inventory/batch').sources,
  modal_open_at_end: !modal.classList.contains('hidden'),
  duplicate_ids: ids.filter((id, i) => ids.indexOf(id) !== i),
  ui,
  requests: uploads.map((u) => u.method + ' ' + u.path),
}));
