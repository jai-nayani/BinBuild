// Offline visual checks. Uses an already installed Playwright; installs nothing.
// Run with model keys unset and the same outbound-network sandbox as unittest.
'use strict';
const { chromium } = require('playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const repo = path.resolve(__dirname, '..');
const output = path.join(repo, 'data/ui-shots');
fs.mkdirSync(output, { recursive: true });
const fixture = JSON.parse(execFileSync(path.join(repo, '.venv/bin/python'), ['-c', `
import json, sys, tempfile
from pathlib import Path
from contextlib import closing
from PIL import Image
sys.path.insert(0, 'tests')
from backend import sample_bin, inventory_db, inventory_vocab, booklet, wonder_designer, wonder_design
from test_design_ideas import proposals
from test_full_loop import KIT_ITEMS
with tempfile.TemporaryDirectory() as tmp, closing(inventory_db.connect(Path(tmp) / 'test.db')) as conn:
    sample_bin.load(conn, Path(tmp) / 'data')
    review = inventory_db.batch_review(conn, sample_bin.BATCH_ID)
review['batch']['id'] = 'b1'
photo = sample_bin.SAMPLE_DIR / next(p['file'] for p in sample_bin.manifest()['photos'] if p['view'] == 'top')
with Image.open(photo) as image:
    width, height = image.size
review['count_photo'] = dict(url='/fake-photo.jpg', width=width, height=height)
review['photos_ready'] = True
owned = wonder_design.owned_from_items(KIT_ITEMS)
ideas = []
for n, idea in enumerate(proposals()):
    result = wonder_designer.Result(True, idea['title'], title=idea['title'], design=idea['design'])
    stored = wonder_designer.app_result(result, owned)
    ideas.append(dict(idea, id=str(n), pieces=stored['pieces'], cover=booklet.cover(stored['booklet'])))
    if n == 0:
        book = dict(stored, booklet_url='/api/builds/7/booklet', step_words='muse-spark')
        html = booklet.render_html(stored['booklet'])
vocab = dict(families=list(inventory_vocab.FAMILIES), colors=[dict(name=c, hex=booklet.HEX.get(c, '#888')) for c in inventory_vocab.COLORS],
             shapes=['brick', 'plate', 'tile', 'round brick'], generator_types=list(inventory_vocab.GENERATOR_TYPES))
print(json.dumps(dict(review=review, ideas=ideas, build=book, html=html, vocab=vocab,
                     photo=str(photo))))
`], { cwd: repo, encoding: 'utf8' }));

const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.json': 'application/json' };
const server = http.createServer((req, res) => {
  const file = path.join(repo, 'app', req.url === '/' ? 'index.html' : req.url.split('?')[0]);
  if (!file.startsWith(path.join(repo, 'app') + path.sep) || !fs.existsSync(file)) { res.writeHead(404).end(); return; }
  res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream');
  res.end(fs.readFileSync(file));
});
let browser;
const errors = [];
const shots = [];
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }

async function main() {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = 'http://127.0.0.1:' + server.address().port;
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, serviceWorkers: 'block' });
  let review, sample = false, jobStage, ideasReady = false;
  let samGate = deferred();
  let samSeen = deferred();
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) { await route.abort(); throw new Error('Unexpected outbound request'); }
    const p = url.pathname;
    const json = body => route.fulfill({ json: body });
    if (p === '/health') { return json({ status: 'ok' }); }
    if (p === '/fake-photo.jpg') { return route.fulfill({ contentType: 'image/jpeg', body: fs.readFileSync(fixture.photo) }); }
    if (p === '/api/inventory/sample') { sample = true; review = structuredClone(fixture.review); return json({ batch_id: 'b1' }); }
    if (p === '/api/inventory/vocab') { return json(fixture.vocab); }
    if (p === '/api/inventory/batch') { return route.fulfill({ status: 201, json: { batch_id: 'b1', ready: true, retake: [] } }); }
    if (p.endsWith('/classify')) {
      if (url.searchParams.get('segmenter') === 'stub') { return json({ pieces: 20, run: { calls: [{ seconds: 1.2 }, { seconds: 2.3 }] } }); }
      samSeen.resolve();
      await samGate.promise;
      review = structuredClone(fixture.review);
      review.batch.classifier = 'spark:offline-fake + sam-3.1-points';
      review.detections = review.detections.slice(0, 20);
      review.detections.forEach((d, i) => { d.status = 'proposed'; d.unsure = i < 2; });
      review.pieces = 20;
      return json({ pieces: 20, run: { sam_pass: { masks: 20, points: 20, sam: { seconds: 1.2 }, spark_tiles: { seconds: 4.5 } } } });
    }
    if (p.endsWith('/review')) { return json(review); }
    if (p.endsWith('/confirm')) { review.batch.status = 'confirmed'; return json({ pieces_added: review.pieces, summary: { total_pieces: review.pieces } }); }
    if (p === '/api/builds/options') {
      return json({ inventory: { total_pieces: sample ? 50 : 20 }, options: [], wonder: {
        enabled: true, busy: false, max_tries: 3, supported_pieces: sample ? 50 : 20,
        ideas: ideasReady ? fixture.ideas : [], inventory_key: 'fake-inventory', recent: [],
      } });
    }
    if (p === '/api/builds/wonder/ideas') { jobStage = 'designing'; return route.fulfill({ status: 202, json: { job_id: 'ideas' } }); }
    if (p === '/api/builds/wonder') { jobStage = 'writing'; return route.fulfill({ status: 202, json: { job_id: 'book' } }); }
    if (p.startsWith('/api/builds/wonder/jobs/')) {
      if (jobStage !== 'done') { return json({ state: 'running', stage: jobStage, message: jobStage === 'designing' ? 'Wonder is finding three ideas from these pieces.' : 'Muse Spark is writing the step words.' }); }
      ideasReady = true;
      return json({ state: 'done', stage: 'done', ideas: fixture.ideas, inventory_key: 'fake-inventory', message: '3 checked ideas from these pieces.', build: fixture.build });
    }
    if (p === '/api/builds/7/booklet') { return route.fulfill({ contentType: 'text/html', body: fixture.html }); }
    if (p.startsWith('/api/')) { throw new Error('Unhandled fake route: ' + p); }
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', e => errors.push(e.message));
  async function shot(name, selector) {
    if (selector) { await page.locator(selector).first().evaluate(e => e.scrollIntoView({ block: 'start' })); }
    await page.waitForTimeout(1600);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, name + ': horizontal overflow');
    await page.screenshot({ path: path.join(output, name + '.png') });
    shots.push(name);
  }
  await page.goto(origin);
  await page.locator('#start-btn').click();
  for (let i = 0; i < 5; i++) {
    await page.locator('#camera-input').setInputFiles(fixture.photo);
    await page.locator('#use-btn').click();
  }
  await shot('capture-before-pass');
  await page.locator('#upload-btn').click();
  await page.locator('#identify-btn').waitFor({ state: 'visible' });
  await shot('capture-after-pass');
  await page.locator('#identify-btn').click();
  await samSeen.promise;
  await shot('identify-midway', '#identify-tracker');
  samGate.resolve();
  await page.locator('#check-view').waitFor({ state: 'visible' });
  await page.locator('#check-outlines path').first().waitFor();
  await shot('identify-finished', '#check-identify-tracker');
  await shot('review-live-fake-masks', '#check-photo');
  await page.locator('#mask-toggle').click();
  await shot('review-dots', '#check-photo');
  await page.locator('#check-img').click();
  await shot('review-enlarged-dots', '#check-photo');
  await page.locator('#check-img').click();
  if (await page.locator('.checked-pieces').count()) { await shot('review-folded-list', '.checked-pieces'); }
  await page.locator('#confirm-btn').click();
  await page.locator('#confirmed-build-btn').click();
  await page.getByRole('button', { name: 'Find three ideas', exact: true }).click();
  await page.waitForTimeout(4200);
  await shot('ideas-tracker', '.wonder .model-tracker');
  jobStage = 'checking';
  await page.waitForTimeout(4200);
  await shot('ideas-checking', '.wonder .model-tracker');
  jobStage = 'done';
  await page.locator('.idea-card').first().waitFor({ timeout: 10000 });
  await shot('idea-cards-with-chips', '.idea-card');
  await page.getByRole('button', { name: 'Make this booklet', exact: true }).first().click();
  await page.waitForTimeout(4200);
  await shot('booklet-writing', '.wonder .model-tracker');
  jobStage = 'done';
  await page.getByRole('link', { name: /Open the booklet/ }).waitFor({ timeout: 10000 });
  await page.getByRole('link', { name: /Open the booklet/ }).click();
  await shot('booklet-full-screen');
  await page.locator('#booklet-back-btn').click();
  await page.goto(origin);
  await page.locator('#sample-link').click();
  await page.locator('#check-outlines path').first().waitFor();
  await shot('review-sample-masks', '#check-photo');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  assert.equal(await page.locator('#check-outlines path').first().evaluate(e => getComputedStyle(e).animationName), 'none');
  await shot('review-sample-reduced-motion', '#check-photo');
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(output, 'manifest.json'), JSON.stringify({ viewport: '390x844', models: 'fake replies only', shots, pageErrors: errors }, null, 2));
  console.log(JSON.stringify({ output, screenshots: shots.length, pageErrors: errors }));
  await context.close();
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (browser) { await browser.close(); }
  server.close();
});
