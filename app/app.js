/* BinBuild PWA — hero, then the capture hub: snap -> review -> upload -> check -> identify -> Finished.
 *
 * The hero says what BinBuild is (scatter, identify, build) while a few loose
 * bricks snap together; "Get started" opens the capture hub. There the batch
 * is a 3-column grid of 6 panels: how to tip out one flat layer, then one
 * panel per photo. Tapping a photo panel opens the camera for that photo; the
 * batch still uploads in the fixed order. Once all 5 photos pass the check,
 * "Next" identifies the pieces.
 *
 * "Use sample images" (and, on the public demo, the offer after a refused
 * Identify) loads the sample bin instead: 5 photos of the kit with their
 * pieces already identified (pre-computed, no model call), straight into
 * "Check the pieces". "What can I build?" shows nothing but a scan prompt
 * until some pieces are confirmed into the inventory.
 *
 * Each batch is 5 photos of one handful: top view plus 4 sides. Every snap is
 * reviewed (retake or use) before it joins the batch; a full batch uploads to
 * POST /api/inventory/batch, which saves it, checks every photo and returns a
 * batch_id plus a "retake" list. A photo that fails the check (blurry, too
 * dark or bright, no pieces, not a camera photo, or — after Identify — not
 * real LEGO) opens a pop-up naming that view, with a Retake button that
 * replaces only that photo. Identify (Spark) runs only once all 5 are clear,
 * and nothing reaches the inventory until the batch is reviewed and confirmed.
 *
 * "Check the pieces" is that review: the top photo with a dot on every piece
 * Spark found, the pieces grouped by kind (fix or remove a whole row, or one
 * piece at a time), pieces Spark missed added by hand, then "Add to my
 * inventory" (confirm). Undo takes the last added batch back out. Finished
 * lists every batch on the backend, so a batch waiting for review can be
 * found again after a reload.
 *
 * Uses the native camera input (capture="environment"), which works over plain
 * HTTP on the home network. Nothing here needs the service worker.
 *
 * "What can I build?" (GET /api/builds/options) is a sideways carousel of
 * the manual builds that have a complete step-by-step booklet — nothing
 * else: no verified-only, waiting or unverified manual builds, and no
 * BrickGPT designs. Each card is the booklet's finished-model picture, the
 * build's name and its piece count. Tapping a card makes that build's
 * booklet (POST /api/builds) and opens it in the booklet view; Back returns
 * to the carousel on the same card.
 *
 * When the backend runs with BINBUILD_WONDER=1 (off by default), a
 * "Generate a new design" section precedes the carousel. One tap is
 * inventory-specific ideas (POST /api/builds/wonder/ideas): Wonder chooses
 * three alternatives, BinBuild checks each before showing its preview, and
 * a selection uses those same placements for its booklet. Sample and uploaded
 * pieces stay separate. Nothing is generated without a tap.
 *
 * A piece Spark flagged unsure (its "unsure" marker from the backend) also
 * gets "Retake this piece" in Check the pieces: one clean close-up of just
 * that piece, named again on its own (POST .../pieces/<id>/reclassify), and
 * its row updates where it sits — same piece, same dot on the top photo.
 */

// Where the FastAPI backend lives. On the home network the app is served on
// port 8080 and the backend runs on port 8000 of the same machine; the public
// deploy serves both from one URL, so there it is this page's own origin.
// To point somewhere else, replace with e.g. 'http://192.168.1.23:8000'.
var BACKEND_URL = window.location.port === '8080'
  ? window.location.protocol + '//' + window.location.hostname + ':8000'
  : window.location.origin;

// The public deploy needs a shared key for the steps that spend credits
// (Identify, Generate). Open the app once as .../#key=<the key>: it is kept on
// this device and taken out of the address bar. Nothing else needs it.
var ACCESS_KEY = (function () {
  var stored = null;
  try {
    var match = /(?:^#|&)key=([^&]+)/.exec(window.location.hash);
    if (match) {
      localStorage.setItem('binbuild.accessKey', decodeURIComponent(match[1]));
      history.replaceState(null, '', window.location.pathname + window.location.search);
    }
    stored = localStorage.getItem('binbuild.accessKey');
  } catch (err) { /* no storage: the free steps still work */ }
  return stored;
}());

(function () {
  'use strict';

  // Photo order is the API contract: the backend names files by this order.
  var VIEWS = [
    { key: 'top', label: 'top view', hint: 'Scatter a handful in one flat layer, no stacking. Hold the phone flat, straight above the pieces.' },
    { key: 'front', label: 'side 1 (front)', hint: 'Crouch low in front of the pieces and shoot across the table.' },
    { key: 'right', label: 'side 2 (right)', hint: 'Move a quarter turn round to the right side.' },
    { key: 'back', label: 'side 3 (back)', hint: 'Another quarter turn: shoot from the far side.' },
    { key: 'left', label: 'side 4 (left)', hint: 'Last one: the left side.' },
  ];
  var UPLOAD_TIMEOUT_MS = 120000;
  var IDENTIFY_TIMEOUT_MS = 115000;
  var HEALTH_TIMEOUT_MS = 4000;
  var BUILD_TIMEOUT_MS = 30000;
  var WONDER_POLL_MS = 4000;
  var inventorySource = 'uploaded';
  try { inventorySource = localStorage.getItem('binbuild.inventorySource') === 'sample' ? 'sample' : 'uploaded'; } catch (err) {}
  function setInventorySource(source) {
    inventorySource = source;
    try { localStorage.setItem('binbuild.inventorySource', source); } catch (err) {}
  }

  var slots = VIEWS.map(function () { return null; }); // confirmed { file, url } per view
  var pending = null;   // { file, url } under review, not yet in the batch
  var target = null;    // the view index a tapped panel asked for; otherwise the next empty one
  var uploading = false;
  var batch = null;     // uploaded batch not yet identified: { id, ready, retake: [notice, ...] }
  var busy = false;     // a retake upload or an Identify call is running
  var uploaded = [];    // { batchId, photos, pieces } per batch identified this session

  function $(id) { return document.getElementById(id); }

  var cameraInput = $('camera-input');
  var galleryInput = $('gallery-input');
  var retakeInput = $('retake-input');
  var pieceInput = $('piece-input');
  var statusEl = $('status');
  var uploadBtn = $('upload-btn');
  var identifyBtn = $('identify-btn');
  var progressEl = $('upload-progress');
  var identifyProgress = null;

  function renderTracker(host, steps) {
    host.innerHTML = '';
    host.classList.remove('hidden');
    var list = el('ol', 'model-tracker');
    steps.forEach(function (step) {
      var row = el('li', 'tracker-step ' + step.state);
      row.setAttribute('data-state', step.state);
      var mark = { waiting: '○', active: '●', done: '✓', failed: '×' }[step.state];
      row.appendChild(el('span', 'tracker-mark', mark));
      var text = el('span', 'tracker-copy');
      text.appendChild(el('span', 'tracker-label', step.label));
      text.appendChild(el('small', null, step.detail || (step.state === 'active' ? 'Working…' :
        step.state === 'waiting' ? 'Waiting' : step.state === 'failed' ? 'Could not finish' : 'Done')));
      row.appendChild(text);
      list.appendChild(row);
    });
    host.appendChild(list);
  }

  function identifyTracker() { renderTracker($('identify-tracker'), identifyProgress.steps); }
  function secondsText(value) { return typeof value === 'number' && isFinite(value) ? value + ' s' : ''; }
  function sparkAnswer(report) {
    var models = [];
    (report && report.answered_by || []).forEach(function (model) {
      var label = model === 'muse-spark-1.3' ? 'Muse Spark 1.3' : model === 'meta-models/muse-spark-open-1026'
        ? report.fallbacks ? 'Baseten backup' : 'Muse Spark Open (Baseten)' : model;
      if (models.indexOf(label) < 0) { models.push(label); }
    });
    return models.join(' + ');
  }
  function doneIdentify(index, detail) {
    identifyProgress.steps[index].state = 'done';
    identifyProgress.steps[index].detail = detail;
  }

  function setStatus(msg, kind, el) {
    el = el || statusEl;
    el.textContent = msg;
    el.classList.toggle('error', kind === 'error');
    el.classList.toggle('ok', kind === 'ok');
  }

  function show(viewId) {
    ['hero-view', 'capture-view', 'review-view', 'finished-view', 'check-view', 'build-view', 'booklet-view'].forEach(function (id) {
      $(id).classList.toggle('hidden', id !== viewId);
    });
    document.body.classList.toggle('on-hero', viewId === 'hero-view'); // the hero has no header bar
    document.body.classList.toggle('on-booklet', viewId === 'booklet-view');
    window.scrollTo(0, 0);
  }

  function nextSlot() { return slots.indexOf(null); } // -1 when the batch is full
  function slotFor() { return target !== null ? target : nextSlot(); } // where the next pick goes
  function filled() { return slots.filter(Boolean).length; }
  function viewIndex(key) { return VIEWS.map(function (v) { return v.key; }).indexOf(key); }
  function needsRetake(key) {
    return !!batch && batch.retake.some(function (r) { return r.view === key; });
  }

  function detailOf(xhr, body) {
    if (body && body.detail) { return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail); }
    return xhr.statusText || ('HTTP ' + xhr.status);
  }

  // body: FormData, a plain object (sent as JSON) or null.
  function request(method, path, body, timeout, onDone, onProgress) {
    var xhr = new XMLHttpRequest();
    xhr.open(method, BACKEND_URL + path);
    xhr.timeout = timeout;
    if (ACCESS_KEY) { xhr.setRequestHeader('X-BinBuild-Key', ACCESS_KEY); }
    if (onProgress) { xhr.upload.onprogress = onProgress; } // must be set before send()
    xhr.onload = function () {
      var body = null;
      try { body = JSON.parse(xhr.responseText); } catch (err) { /* not JSON */ }
      onDone(xhr, body);
    };
    xhr.onerror = function () { onDone(xhr, null, "couldn't reach the backend at " + BACKEND_URL + '.'); checkBackend(); };
    xhr.ontimeout = function () { onDone(xhr, null, 'no answer from the backend after ' + (timeout / 1000) + ' s.'); };
    if (body && !(body instanceof FormData)) {
      xhr.setRequestHeader('Content-Type', 'application/json');
      body = JSON.stringify(body);
    }
    xhr.send(body);
  }

  function post(path, form, timeout, onDone, onProgress) { request('POST', path, form, timeout, onDone, onProgress); }

  // --- render -----------------------------------------------------------------

  function render() {
    var next = nextSlot();
    var batchNo = uploaded.length + 1;
    if (batch) {
      $('shot-title').textContent = 'Batch ' + batchNo + (batch.ready ? ' · all 5 photos are clear' : ' · retake needed');
      $('shot-hint').textContent = batch.ready
        ? 'Keep the pieces where they are and tap Identify pieces.'
        : 'Retake the photo marked in red. Keep the pieces where they are.';
    } else if (next === -1) {
      $('shot-title').textContent = 'Batch ' + batchNo + ' · all 5 photos taken';
      $('shot-hint').textContent = 'Check them now, or tap a panel to take that photo again.';
    } else {
      $('shot-title').textContent = 'Batch ' + batchNo + ' · ' + filled() + ' of 5 photos';
      $('shot-hint').textContent = 'Tap a panel to take that photo. Next up: ' + VIEWS[next].label + '. ' + VIEWS[next].hint;
    }
    var full = next === -1;
    $('gallery-btn').classList.toggle('hidden', full || !!batch);

    // One panel per photo: empty, next up, taken, then after the check clear (green) or retake (red).
    VIEWS.forEach(function (v, i) {
      var photo = slots[i];
      var failed = needsRetake(v.key);
      var passed = !!batch && !!photo && !failed;
      var panel = $('panel-' + v.key);
      panel.classList.toggle('next', !batch && i === next);
      panel.classList.toggle('taken', !!photo && !batch);
      panel.classList.toggle('passed', passed);
      panel.classList.toggle('failed', failed);
      panel.classList.toggle('locked', !!batch && !failed); // once uploaded, a photo changes only through its retake
      panel.setAttribute('aria-disabled', !!batch && !failed ? 'true' : 'false');
      $('state-' + v.key).textContent = failed ? 'Retake' : passed ? 'Clear' : photo ? 'Taken'
        : !batch && i === next ? 'Next' : 'Tap to take';
      var thumb = $('thumb-' + v.key);
      if (photo) { thumb.src = photo.url; thumb.classList.remove('hidden'); } else { thumb.removeAttribute('src'); thumb.classList.add('hidden'); }
    });

    uploadBtn.classList.toggle('hidden', !!batch && batch.ready);
    uploadBtn.disabled = !full || uploading || !!batch;
    uploadBtn.textContent = uploading ? 'Checking the photos…' : 'Check my 5 photos';
    identifyBtn.classList.toggle('hidden', !(batch && batch.ready));
    identifyBtn.disabled = busy || !(batch && batch.ready); // Next: only once all 5 photos passed the check
    identifyBtn.textContent = busy ? 'Identifying…' : 'Next: identify the pieces';
    $('finished-btn').disabled = uploading || busy || !!batch;
  }

  VIEWS.forEach(function (v, i) {
    var panel = $('panel-' + v.key);
    panel.addEventListener('click', function (e) {
      if (batch) { // checked already: a red panel opens its retake, the others stay as they are
        e.preventDefault();
        if (needsRetake(v.key) && !busy) {
          batch.retake.sort(function (a, b) { return (b.view === v.key) - (a.view === v.key); });
          openRetake();
        }
        return;
      }
      if (uploading) { e.preventDefault(); return; }
      target = i; // the label opens the camera; the photo goes to this panel
    });
    panel.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); panel.click(); }
    });
  });

  $('panel-tip').addEventListener('click', function () {
    $('shot-hint').textContent = 'Tip out one handful in a single flat layer: nothing stacked or touching, on a plain, ' +
      'light table, in good light. Keep the pieces where they are until you tap Next.';
    $('panel-tip').classList.add('seen');
    $('state-tip').textContent = 'Got it';
  });

  $('gallery-btn').addEventListener('click', function () { target = null; });

  // --- snap + review ----------------------------------------------------------

  function onPicked(input) {
    var file = input.files && input.files[0];
    input.value = ''; // so picking the same file again still fires "change"
    if (!file) { return; } // camera cancelled: stay where we are
    if (file.type && file.type.indexOf('image/') !== 0) {
      setStatus('That file is not a photo (' + file.type + ').', 'error');
      return;
    }
    if (slotFor() === -1 || batch) { return; }
    if (pending) { URL.revokeObjectURL(pending.url); }
    pending = { file: file, url: URL.createObjectURL(file) };
    var view = VIEWS[slotFor()];
    $('review-title').textContent = 'Check the ' + view.label;
    $('review-img').src = pending.url;
    show('review-view');
  }

  cameraInput.addEventListener('change', function () { onPicked(cameraInput); });
  galleryInput.addEventListener('change', function () { onPicked(galleryInput); });

  $('use-btn').addEventListener('click', function () {
    if (!pending) { return; }
    var i = slotFor();
    if (slots[i]) { URL.revokeObjectURL(slots[i].url); } // a panel tapped again replaces its photo
    slots[i] = pending;
    pending = null;
    target = null;
    $('review-img').removeAttribute('src');
    setStatus(nextSlot() === -1
      ? 'All 5 photos taken. Check them.'
      : 'Saved the ' + VIEWS[i].label + '. Next: ' + VIEWS[nextSlot()].label + '.');
    show('capture-view');
    render();
  });

  $('cancel-review-btn').addEventListener('click', function () {
    if (pending) { URL.revokeObjectURL(pending.url); }
    pending = null;
    target = null;
    $('review-img').removeAttribute('src');
    show('capture-view');
    render();
  });

  // --- upload -------------------------------------------------------------------

  function fileName(i, file) {
    var ext = (file.name.match(/\.[A-Za-z0-9]+$/) || ['.jpg'])[0];
    return (i + 1) + '-' + VIEWS[i].key + ext;
  }

  function uploadBatch() {
    if (uploading || batch || nextSlot() !== -1) { return; }
    var form = new FormData();
    slots.forEach(function (photo, i) { form.append('photos', photo.file, fileName(i, photo.file)); });

    uploading = true;
    progressEl.value = 0;
    progressEl.classList.remove('hidden');
    setStatus('Uploading 5 photos to ' + BACKEND_URL + ' …');
    render();

    post('/api/inventory/batch', form, UPLOAD_TIMEOUT_MS, function (xhr, body, failure) {
      uploading = false;
      progressEl.classList.add('hidden');
      if (!failure && xhr.status >= 200 && xhr.status < 300 && body && body.batch_id) {
        batch = { id: body.batch_id, ready: body.ready !== false, retake: body.retake || [] };
        if (batch.ready) {
          setStatus('✓ All 5 photos are clear' + (body.duplicate ? ' (they were already sent as ' + body.batch_id + ')' : '') +
            '. Tap Next before you sweep them aside.', 'ok');
        } else {
          setStatus('Uploaded, but ' + batch.retake.length + (batch.retake.length === 1 ? ' photo needs' : ' photos need') +
            ' a retake before the pieces can be identified.', 'error');
          openRetake();
        }
      } else {
        setStatus('✗ Upload failed: ' + (failure || 'the backend answered HTTP ' + xhr.status + ': ' + detailOf(xhr, body) + '.') +
          ' Your 5 photos are kept, tap Upload to try again.', 'error');
      }
      render();
    }, function (e) {
      if (e.lengthComputable) {
        progressEl.value = Math.round((e.loaded / e.total) * 100);
        setStatus('Uploading… ' + progressEl.value + '% of ' + (e.total / 1048576).toFixed(1) + ' MB');
      }
    });
  }

  uploadBtn.addEventListener('click', uploadBatch);

  // --- retake pop-up --------------------------------------------------------------

  function openRetake(note) {
    var notice = batch.retake[0];
    var i = viewIndex(notice.view);
    var others = batch.retake.slice(1).map(function (r) { return 'the ' + r.view + ' photo'; });
    $('retake-count').textContent = batch.retake.length > 1 ? batch.retake.length + ' photos need a retake' : '';
    $('retake-title').textContent = 'The ' + notice.view + ' photo is unclear';
    var img = $('retake-img');
    if (i >= 0 && slots[i]) { img.src = slots[i].url; img.classList.remove('hidden'); } else { img.classList.add('hidden'); }
    $('retake-reason').textContent = (notice.reason_text + ' ' + notice.tip).trim();
    $('retake-text').textContent = 'Please retake just this photo. ' + (others.length
      ? 'After that: ' + others.join(', ') + '.'
      : 'Your other ' + (VIEWS.length - 1) + ' photos are fine.');
    $('retake-hint').textContent = i >= 0 ? 'How: ' + VIEWS[i].hint : '';
    $('retake-btn').textContent = busy ? 'Checking…' : '📷 Retake ' + notice.view + ' photo';
    setStatus(note ? note.text : '', note ? note.kind : null, $('retake-status'));
    $('retake-modal').classList.remove('hidden');
    $('retake-btn').focus();
  }

  function closeRetake() {
    $('retake-modal').classList.add('hidden');
    retakeInput.value = '';
  }

  retakeInput.addEventListener('change', function () {
    var file = retakeInput.files && retakeInput.files[0];
    retakeInput.value = '';
    if (!file || !batch || !batch.retake.length || busy) { return; }
    var view = batch.retake[0].view;
    var i = viewIndex(view);
    var form = new FormData();
    form.append('photo', file, fileName(i, file));
    busy = true;
    openRetake({ text: 'Checking the new ' + view + ' photo…' });
    post('/api/inventory/batch/' + encodeURIComponent(batch.id) + '/photos/' + view, form, UPLOAD_TIMEOUT_MS,
      function (xhr, body, failure) {
        busy = false;
        if (failure || xhr.status < 200 || xhr.status >= 300 || !body) {
          openRetake({ text: '✗ ' + (failure || 'The retake did not upload: ' + detailOf(xhr, body)) + ' Try again.', kind: 'error' });
          return;
        }
        if (slots[i]) { URL.revokeObjectURL(slots[i].url); }
        slots[i] = { file: file, url: URL.createObjectURL(file) };
        batch.ready = body.ready;
        batch.retake = body.retake || [];
        if (batch.ready) {
          closeRetake();
          setStatus('✓ The ' + view + ' photo is clear now. All 5 photos are clear: tap Next.', 'ok');
        } else if (body.passed) {
          openRetake({ text: '✓ The ' + view + ' photo is clear now. Next one:', kind: 'ok' });
        } else {
          openRetake({ text: 'Still unclear. Please try this photo once more.', kind: 'error' });
        }
        render();
      });
  });

  // --- identify ---------------------------------------------------------------------

  function countByFamily(detections) {
    var counts = {};
    (detections || []).forEach(function (d) {
      if (d.status !== 'rejected') { counts[d.family] = (counts[d.family] || 0) + d.count; }
    });
    return Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; })
      .map(function (f) { return counts[f] + ' ' + f + (counts[f] === 1 ? '' : 's'); }).join(', ');
  }

  identifyBtn.addEventListener('click', function () {
    if (!batch || !batch.ready || busy) { return; }
    busy = true;
    identifyProgress = { id: batch.id, steps: [
      { label: 'Muse Spark finds the pieces', state: 'active' },
      { label: 'SAM 3.1 cuts out each piece', state: 'waiting' },
      { label: 'Muse Spark checks each close-up', state: 'waiting' },
    ] };
    identifyTracker();
    setStatus('');
    render();
    var classify = '/api/inventory/batch/' + encodeURIComponent(batch.id) + '/classify';
    post(classify + '?segmenter=stub', null, IDENTIFY_TIMEOUT_MS,
      function (xhr, body, failure) {
        if (!failure && xhr.status === 200 && body) {
          var wholePhoto = body;
          var calls = body.run && body.run.calls || [];
          var seconds = calls.filter(function (call) { return typeof call.seconds === 'number'; });
          doneIdentify(0, body.run ? [typeof body.pieces === 'number' ? 'found ' + body.pieces + ' pieces' : '',
            seconds.length ? secondsText(Math.round(seconds.reduce(function (n, call) { return n + call.seconds; }, 0) * 10) / 10) : '',
            sparkAnswer(body.run.spark)]
            .filter(Boolean).join(' · ') : 'already identified');
          identifyProgress.steps[1].state = 'active';
          identifyTracker();
          post(classify + '?segmenter=sam', null, IDENTIFY_TIMEOUT_MS, function (samXhr, samBody, samFailure) {
            var result = wholePhoto;
            var note;
            if (!samFailure && samXhr.status === 200 && samBody) {
              result = samBody;
              var pass = samBody.run && samBody.run.sam_pass;
              identifyProgress.samPass = pass;
              doneIdentify(1, !samBody.run ? 'already identified' : pass ? [
                typeof pass.masks === 'number' && typeof pass.points === 'number' ? pass.masks + ' of ' + pass.points + ' cut out' : '',
                secondsText(pass.sam && pass.sam.seconds)].filter(Boolean).join(' · ') : '');
              doneIdentify(2, !samBody.run ? 'already identified' : [
                secondsText(pass && pass.spark_tiles && pass.spark_tiles.seconds), sparkAnswer(pass && pass.spark)]
                .filter(Boolean).join(' · '));
              note = pass
                ? 'SAM 3.1 cut out ' + pass.masks + ' of ' + pass.points + ' pieces' +
                  (secondsText(pass.sam && pass.sam.seconds) ? ' in ' + secondsText(pass.sam.seconds) : '') + '.'
                : 'The pieces are ready to check.';
            } else {
              identifyProgress.steps[1].state = 'failed';
              identifyProgress.steps[2].state = 'failed';
              note = "SAM 3.1 failed, so these are Spark's whole-photo pieces: " +
                (samFailure || detailOf(samXhr, samBody));
            }
            identifyTracker();
            busy = false;
            var found = batch.id;
            uploaded.push({ batchId: found, photos: 5, pieces: result.pieces });
            slots.forEach(function (photo) { if (photo) { URL.revokeObjectURL(photo.url); } });
            slots = VIEWS.map(function () { return null; });
            batch = null;
            setStatus(note, samFailure || samXhr.status !== 200 ? 'error' : 'ok');
            render();
            openReview(found, { text: note, kind: samFailure || samXhr.status !== 200 ? 'error' : 'ok' });
          });
          return;
        }
        busy = false;
        identifyProgress.steps[0].state = 'failed';
        identifyTracker();
        if (!failure && xhr.status === 422 && body && body.retake && body.retake.length) {
          batch.ready = false;
          batch.retake = body.retake;
          setStatus('Spark could not use ' + (body.retake.length === 1 ? 'one photo' : body.retake.length + ' photos') +
            '. Nothing was added. Retake it, then tap Next again.', 'error');
          openRetake();
        } else if (!failure && xhr.status === 401) {
          // the public demo: Identify spends credits, so it needs the access key
          setStatus('', null);
          offerSampleBin();
        } else {
          setStatus('✗ Identify failed: ' + (failure || detailOf(xhr, body)) + ' Nothing was added. Tap Next to try again.', 'error');
        }
        render();
      });
  });

  // No key on the public demo: offer the sample bin instead (its pieces are already identified).
  function offerSampleBin() {
    $('sample-offer').classList.remove('hidden');
    request('GET', '/api/inventory/sample', null, BUILD_TIMEOUT_MS, function (xhr, body) {
      var n = !xhr || xhr.status !== 200 || !body ? 0 : body.pieces;
      $('sample-bin-btn').textContent = n ? 'Use the sample bin (' + n + ' pieces)' : 'Use the sample bin';
    });
  }

  // The sample bin: 5 photos of the kit and their verified pieces, loaded as a batch ready for review.
  function loadSample() {
    var btn = $('sample-images-btn');
    btn.disabled = true;
    setStatus('Loading the sample images…');
    request('POST', '/api/inventory/sample', null, BUILD_TIMEOUT_MS, function (xhr, body, failure) {
      btn.disabled = false;
      if (failure || xhr.status !== 200 || !body || !body.batch_id) {
        setStatus('✗ Couldn’t load the sample images: ' + (failure || detailOf(xhr, body)), 'error');
        return;
      }
      setStatus('', null);
      openReview(body.batch_id, { text: '✓ These sample pieces are already identified. ' +
        'Use them to explore builds. Your own pieces stay separate.', kind: 'ok' });
    });
  }

  // --- check the pieces: review one batch, then confirm (or undo) ----------------

  var REVIEW_TIMEOUT_MS = 30000;
  var FAMILY_LABEL = {
    brick: 'Brick', plate: 'Plate (thin)', tile: 'Tile (smooth, no studs)', slope: 'Slope',
    wheel: 'Wheel or tyre', window_door: 'Window or door', technic: 'Technic part',
    minifig: 'Minifigure part', other: 'Something else', unknown: 'Not sure',
  };
  var MORE_SIZES = ['1x3', '2x3', '1x10', '1x12', '2x8', '2x10', '4x4', '4x6', '6x6'];
  var vocab = null;     // GET /api/inventory/vocab, loaded once
  var review = null;    // { id, data, photo, selected: group key, focus: detection id, open: { key: true } }
  var editing = null;   // { ids: [...], from: detection } or { addition: true }
  var reviewBusy = false;
  var pieceRetake = null;  // the unsure detection id a close-up is being taken for

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }
  function words(s) { return String(s || '').replace(/_/g, ' '); }
  function pieceLabel(d) { return [words(d.color), d.size, d.shape || words(d.family)].filter(Boolean).join(' '); }
  function colorHex(name) {
    var found = vocab ? vocab.colors.filter(function (c) { return c.name === name; })[0] : null;
    return found ? found.hex : '#b8b8b8';
  }
  function isGenerator(family, size, plain) {
    return family === 'brick' && plain && !!vocab && vocab.generator_types.indexOf(size) >= 0;
  }
  function groupKey(d) {
    return [d.status === 'rejected' ? 'removed' : 'kept', d.family, d.shape, d.size, d.color, d.plain, d.source].join('|');
  }
  function total(items) { return items.reduce(function (n, d) { return n + d.count; }, 0); }
  function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }
  function batchPath(suffix) { return '/api/inventory/batch/' + encodeURIComponent(review.id) + suffix; }

  function loadVocab(then) {
    if (vocab) { then(); return; }
    request('GET', '/api/inventory/vocab', null, REVIEW_TIMEOUT_MS, function (xhr, body) {
      if (xhr.status === 200 && body) { vocab = body; fillEditorOptions(); }
      then();
    });
  }

  function openReview(batchId, note) {
    var checkStatus = $('check-status');
    show('check-view');
    $('check-list').innerHTML = '';
    $('check-dots').innerHTML = '';
    $('confirmed-card').classList.add('hidden');
    setStatus(note ? note.text : 'Loading the pieces…', note ? note.kind : null, checkStatus);
    loadVocab(function () {
      request('GET', '/api/inventory/batch/' + encodeURIComponent(batchId) + '/review', null, REVIEW_TIMEOUT_MS,
        function (xhr, body, failure) {
          if (failure || xhr.status !== 200 || !body) {
            setStatus('✗ Could not load the pieces: ' + (failure || detailOf(xhr, body)), 'error', checkStatus);
            return;
          }
          var keep = review && review.id === batchId ? review : null;
          review = { id: batchId, data: body, photo: body.count_photo, selected: keep ? keep.selected : null,
                     focus: null, open: keep ? keep.open : {}, confirmedText: keep ? keep.confirmedText : '',
                     masks: keep ? keep.masks : true, expanded: keep ? keep.expanded : false,
                     checkedOpen: keep ? keep.checkedOpen : false };
          if (!note) { setStatus('', null, checkStatus); }
          var img = $('check-img');
          if (review.photo) { img.src = BACKEND_URL + review.photo.url; img.classList.remove('hidden'); } else { img.classList.add('hidden'); }
          renderReview();
        });
    });
  }

  function groupsOf(detections) {
    var byKey = {};
    var order = [];
    detections.forEach(function (d) {
      var key = groupKey(d);
      if (!byKey[key]) { byKey[key] = { key: key, first: d, items: [] }; order.push(byKey[key]); }
      byKey[key].items.push(d);
    });
    var families = Object.keys(FAMILY_LABEL);
    return order.sort(function (a, b) {
      return (b.first.generator_type ? 1 : 0) - (a.first.generator_type ? 1 : 0) ||
        families.indexOf(a.first.family) - families.indexOf(b.first.family) ||
        pieceLabel(a.first).localeCompare(pieceLabel(b.first));
    });
  }

  function select(key, focusId) {
    if (focusId === undefined && review.selected === key && review.focus === null) {
      review.selected = null; // tapping the selected row again clears the highlight
    } else {
      review.selected = key;
    }
    review.focus = focusId === undefined ? null : focusId;
    renderReview();
  }

  function renderReview() {
    var data = review.data;
    var confirmed = data.batch.status === 'confirmed';
    var kept = data.detections.filter(function (d) { return d.status !== 'rejected'; });
    var removed = data.detections.filter(function (d) { return d.status === 'rejected'; });
    var fixed = data.detections.filter(function (d) { return d.status === 'corrected' || d.source === 'manual'; }).length;

    var sample = (data.batch.classifier || '').indexOf('sample') === 0;
    setInventorySource(sample ? 'sample' : 'uploaded');
    $('check-title').textContent = (sample ? 'The sample bin: ' : '') +
      (confirmed ? (sample ? 'ready to explore' : 'These pieces are in your inventory')
        : (sample ? 'check the pieces' : 'Check the pieces'));
    $('check-intro').textContent = sample
      ? 'These sample pieces and recorded outlines are ready to explore. Your own pieces stay separate.'
      : confirmed
      ? 'This batch is added. To change a piece, undo it first.'
      : kept.length
        ? 'Tap a row to see those pieces on the photo. Fix anything that’s wrong, remove anything that isn’t a piece, then add them to your inventory.'
        : 'No pieces in this batch yet. Add the pieces Spark missed, or go back and identify it again.';
    $('check-summary').textContent = plural(data.pieces, 'piece', 'pieces') +
      (fixed ? ' · ' + fixed + (sample ? ' fixed in its earlier review' : ' fixed by you') : '') +
      (removed.length ? ' · ' + removed.length + ' removed' : '');
    renderDots(kept);
    var tracker = $('check-identify-tracker');
    tracker.classList.add('hidden');
    if (!sample && identifyProgress && identifyProgress.id === review.id) { renderTracker(tracker, identifyProgress.steps); }

    var list = $('check-list');
    list.innerHTML = '';
    var unsure = kept.filter(function (d) { return !sample && d.unsure; });
    var checked = kept.filter(function (d) { return sample || !d.unsure; });
    unsure.forEach(function (d) {
      list.appendChild(groupCard({ key: groupKey(d), first: d, items: [d] }, confirmed));
    });
    if (checked.length) {
      var folded = el('details', 'checked-pieces');
      if (review.checkedOpen) { folded.setAttribute('open', ''); }
      folded.appendChild(el('summary', null, sample
        ? '✓ ' + plural(total(checked), 'piece', 'pieces') + ', checked in the Oct 28 review'
        : '✓ ' + plural(total(checked), 'piece looks', 'pieces look') + ' right'));
      groupsOf(checked).forEach(function (g) { folded.appendChild(groupCard(g, confirmed)); });
      folded.addEventListener('toggle', function () { review.checkedOpen = folded.open; });
      list.appendChild(folded);
    }
    if (removed.length) {
      list.appendChild(el('p', 'section-label', 'Removed: not added to your inventory'));
      groupsOf(removed).forEach(function (g) { list.appendChild(groupCard(g, confirmed)); });
    }

    $('add-piece-btn').classList.toggle('hidden', confirmed);
    $('add-piece-btn').disabled = reviewBusy;
    var confirmBtn = $('confirm-btn');
    confirmBtn.parentNode.classList.toggle('hidden', confirmed);
    confirmBtn.disabled = reviewBusy || !data.photos_ready || data.pieces === 0;
    confirmBtn.textContent = reviewBusy ? 'Saving…' : sample ? '✓ Use these sample pieces' :
      '✓ Add ' + plural(data.pieces, 'piece', 'pieces') + ' to my inventory';
    $('confirmed-title').textContent = sample ? '✓ The sample is ready' : '✓ Added to your inventory';
    $('confirmed-next-btn').textContent = sample ? '📷 Try with my own pieces' : '📷 Scan the next handful';
    $('confirmed-build-btn').textContent = sample ? '🧱 Explore sample builds' : '🧱 What can I build?';
    $('undo-btn').textContent = sample ? '↺ Stop using these sample pieces' : '↺ Undo: take these pieces out again';
    $('check-back-btn').textContent = sample ? '← Back to the start' : '← Back to scanning';
    $('confirmed-card').classList.toggle('hidden', !confirmed);
    if (confirmed) {
      $('confirmed-text').textContent = sample ? 'Explore builds from these sample pieces. Your own pieces stay separate.' : review.confirmedText ||
        plural(data.pieces, 'piece', 'pieces') + ' from this batch are in your inventory.';
    }
  }

  function renderDots(kept) {
    var box = $('check-dots');
    var svg = $('check-outlines');
    var photo = review.photo;
    var outlined = kept.some(function (d) { return d.region && d.region.mask && d.region.mask.path; });
    var sample = (review.data.batch.classifier || '').indexOf('sample') === 0;
    var run = review.data.batch.run || {};
    var pass = run.sam_pass || (identifyProgress && identifyProgress.id === review.id && identifyProgress.samPass);
    var masks = kept.filter(function (d) { return d.region && d.region.mask && d.region.mask.path; }).length;
    var points = kept.filter(function (d) { return d.region && d.region.point; }).length;
    var counts = pass && typeof pass.masks === 'number' && typeof pass.points === 'number'
      ? pass.masks + ' of ' + pass.points : masks + ' of ' + points;
    var caption = outlined
      ? sample ? 'Recorded SAM 3.1 outlines (Oct 28). Each outline is one piece.'
        : 'Each outline is one piece, cut out by SAM 3.1 (' + counts + ')'
      : 'Each dot is one piece Spark found. Tap a dot or a row to see which is which.';
    $('check-model').classList.toggle('hidden', !outlined);
    $('check-model-label').textContent = sample ? '✂ Recorded SAM 3.1 outlines' : '✂ Cut out by SAM 3.1';
    $('mask-toggle').classList.toggle('hidden', !outlined);
    $('mask-toggle').textContent = review.masks ? 'Show dots' : 'Show SAM masks';
    $('mask-toggle').setAttribute('aria-pressed', review.masks ? 'true' : 'false');
    svg.classList.toggle('hidden', !review.masks);
    box.classList.toggle('hidden', outlined && review.masks);
    $('check-photo').classList.toggle('expanded', review.expanded);
    $('check-img').setAttribute('aria-expanded', review.expanded ? 'true' : 'false');
    box.innerHTML = '';
    svg.innerHTML = '';
    if (!photo) { $('check-caption').textContent = ''; return; }
    svg.setAttribute('viewBox', '0 0 ' + photo.width + ' ' + photo.height);
    var maskIndex = 0;
    kept.forEach(function (d) {
      var m = d.region && d.region.mask;
      if (!m || !m.path) { return; }
      // the path is in the mask's own pixels; its box is in the photo's
      var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.style.animationDelay = (maskIndex++ * (masks > 1 ? 1200 / (masks - 1) : 0)) + 'ms';
      path.setAttribute('d', m.path);
      path.setAttribute('transform', 'translate(' + m.box[0] + ' ' + m.box[1] + ') scale(' +
        ((m.box[2] - m.box[0]) / m.size[0]) + ' ' + ((m.box[3] - m.box[1]) / m.size[1]) + ')');
      var key = groupKey(d);
      if (review.focus === d.id || (review.focus === null && review.selected === key)) {
        path.setAttribute('class', 'on');
      } else if (review.selected) {
        path.setAttribute('class', 'dim');
      }
      svg.appendChild(path);
    });
    kept.forEach(function (d) {
      var point = d.region && d.region.point;
      if (!point) { return; }
      var key = groupKey(d);
      var dot = el('button', 'pin');
      dot.type = 'button';
      dot.style.left = (point[0] / photo.width * 100) + '%';
      dot.style.top = (point[1] / photo.height * 100) + '%';
      dot.style.background = colorHex(d.color);
      dot.setAttribute('aria-label', pieceLabel(d));
      if (review.focus === d.id) { dot.classList.add('focus'); } else if (review.selected === key) { dot.classList.add('on'); } else if (review.selected) { dot.classList.add('dim'); }
      if (d.region.mask && d.region.mask.path) { dot.classList.add('hollow'); } // let the outline show through
      dot.addEventListener('click', function () { select(key, d.id); });
      box.appendChild(dot);
    });
    var focus = kept.filter(function (d) { return d.id === review.focus; })[0];
    var group = kept.filter(function (d) { return groupKey(d) === review.selected; });
    if (focus) {
      caption = 'This one: ' + pieceLabel(focus);
    } else if (group.length) {
      var pointed = group.filter(function (d) { return d.region && d.region.point; }).length;
      caption = 'Showing ' + total(group) + '× ' + pieceLabel(group[0]) +
        (pointed < group.length ? ' (' + (group.length - pointed) + ' added by hand, not on the photo)' : '');
    }
    $('check-caption').textContent = caption;
  }

  $('mask-toggle').addEventListener('click', function () {
    if (!review) { return; }
    review.masks = !review.masks;
    renderDots(review.data.detections.filter(function (d) { return d.status !== 'rejected'; }));
  });
  function togglePhoto() {
    if (!review || !review.photo) { return; }
    review.expanded = !review.expanded;
    renderDots(review.data.detections.filter(function (d) { return d.status !== 'rejected'; }));
  }
  $('check-img').addEventListener('click', togglePhoto);
  $('check-img').addEventListener('keydown', function (event) {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); togglePhoto(); }
  });

  function smallButton(text, onClick) {
    var b = el('button', 'small', text);
    b.type = 'button';
    b.disabled = reviewBusy;
    b.addEventListener('click', function (e) { e.stopPropagation(); onClick(); });
    return b;
  }

  function ids(items) { return items.map(function (d) { return d.id; }); }

  function groupCard(g, readOnly) {
    var d = g.first;
    var sample = (review.data.batch.classifier || '').indexOf('sample') === 0;
    var removed = d.status === 'rejected';
    var many = g.items.length > 1;
    var card = el('div', 'piece-group' + (review.selected === g.key ? ' sel' : '') + (removed ? ' removed' : ''));
    var head = el('div', 'pg-head');
    var swatch = el('span', 'swatch');
    swatch.style.background = colorHex(d.color);
    head.appendChild(swatch);
    head.appendChild(el('span', null, total(g.items) + '× ' + pieceLabel(d)));
    if (d.status === 'corrected') { head.appendChild(el('span', 'badge fixed', 'fixed')); }
    if (d.source === 'manual') { head.appendChild(el('span', 'badge fixed', 'added by you')); }
    if (!sample && !removed && g.items.some(function (item) { return item.unsure; })) {
      head.appendChild(el('span', 'badge unsure', 'not sure'));
    }
    head.addEventListener('click', function () { select(g.key); });
    card.appendChild(head);
    if (readOnly) { return card; }

    var actions = el('div', 'pg-actions');
    if (removed) {
      actions.appendChild(smallButton('↩ Put back' + (many ? ' all ' + g.items.length : ''),
        function () { setPieces(ids(g.items), 'accepted'); }));
    } else {
      actions.appendChild(smallButton('Fix',
        function () { openEditor({ ids: ids(g.items), from: d }); }));
      if (!sample && !many && d.unsure) {
        actions.appendChild(smallButton('📷 Retake this piece', function () { startPieceRetake(d); }));
      }
    }
    if (many) {
      var oneByOne = smallButton(review.open[g.key] ? 'Hide ▴' : 'One by one ▾', function () {
        review.open[g.key] = !review.open[g.key];
        review.selected = g.key;
        renderReview();
      });
      oneByOne.className = 'text-action';
      actions.appendChild(oneByOne);
    }
    card.appendChild(actions);

    if (many && review.open[g.key]) {
      var rows = el('ul', 'pg-items');
      g.items.forEach(function (item, n) {
        var row = el('li', review.focus === item.id ? 'focus' : '');
        var who = el('span', 'who', 'Piece ' + (n + 1) + (item.region && item.region.point ? ' · show on photo' : ''));
        who.addEventListener('click', function () { select(g.key, item.id); });
        row.appendChild(who);
        if (removed) {
          row.appendChild(smallButton('↩ Put back', function () { setPieces([item.id], 'accepted'); }));
        } else {
          row.appendChild(smallButton('Fix', function () { openEditor({ ids: [item.id], from: item }); }));
          if (!sample && item.unsure) {
            row.appendChild(smallButton('📷 Retake this piece', function () { startPieceRetake(item); }));
          }
        }
        rows.appendChild(row);
      });
      card.appendChild(rows);
    }
    return card;
  }

  // Send a review change; onDone(ok, message) after the screen is updated.
  function sendReview(payload, onDone) {
    if (reviewBusy) { return; }
    reviewBusy = true;
    renderReview();
    request('POST', batchPath('/review'), payload, REVIEW_TIMEOUT_MS, function (xhr, body, failure) {
      reviewBusy = false;
      var ok = !failure && xhr.status === 200 && !!body;
      if (ok) {
        for (var k in body) { if (Object.prototype.hasOwnProperty.call(body, k)) { review.data[k] = body[k]; } }
      }
      renderReview();
      onDone(ok, ok ? '' : (failure || detailOf(xhr, body)));
    });
  }

  function setPieces(detectionIds, status) {
    var checkStatus = $('check-status');
    sendReview({ corrections: detectionIds.map(function (id) { return { detection_id: id, status: status }; }) },
      function (ok, message) {
        if (!ok) { setStatus('✗ Not saved: ' + message, 'error', checkStatus); return; }
        setStatus(status === 'rejected'
          ? '✓ Removed ' + plural(detectionIds.length, 'piece', 'pieces') + '. They won’t go into your inventory.'
          : '✓ Put back ' + plural(detectionIds.length, 'piece', 'pieces') + '.', 'ok', checkStatus);
      });
  }

  // --- clean close-up: name one unsure piece again, on its own ---

  function startPieceRetake(item) {
    if (reviewBusy) { return; }
    pieceRetake = item.id;
    review.focus = item.id; // keep its dot ringed while the camera is open
    renderReview();
    setStatus('Take one close-up of just this piece: ' + pieceLabel(item) + '.', null, $('check-status'));
    pieceInput.click();
  }

  pieceInput.addEventListener('change', function () {
    var file = pieceInput.files && pieceInput.files[0];
    pieceInput.value = ''; // so retaking the same piece again still fires "change"
    if (!file || pieceRetake === null || !review || reviewBusy) { pieceRetake = null; return; }
    var id = pieceRetake;
    pieceRetake = null;
    var form = new FormData();
    form.append('photo', file, 'close-up.jpg');
    reviewBusy = true;
    renderReview();
    setStatus('Naming that piece again…', null, $('check-status'));
    request('POST', batchPath('/pieces/' + encodeURIComponent(id) + '/reclassify'), form, IDENTIFY_TIMEOUT_MS,
      function (xhr, body, failure) {
        reviewBusy = false;
        if (failure || xhr.status !== 200 || !body) {
          renderReview();
          setStatus('✗ Not updated: ' + (failure || detailOf(xhr, body)), 'error', $('check-status'));
          return;
        }
        for (var k in body) { if (Object.prototype.hasOwnProperty.call(body, k)) { review.data[k] = body[k]; } }
        review.focus = id; // the same piece, still ringed on the photo
        renderReview();
        var updated = body.detection || {};
        setStatus('✓ Updated: ' + pieceLabel(updated) + '.', 'ok', $('check-status'));
      });
  });

  // --- fix / add dialog ---

  function fillEditorOptions() {
    var family = $('edit-family');
    var color = $('edit-color');
    family.innerHTML = '';
    color.innerHTML = '';
    vocab.families.forEach(function (f) {
      var o = el('option', null, FAMILY_LABEL[f] || words(f));
      o.value = f;
      family.appendChild(o);
    });
    vocab.colors.forEach(function (c) {
      var o = el('option', null, words(c.name));
      o.value = c.name;
      color.appendChild(o);
    });
    var shapes = $('shape-list');
    vocab.shapes.forEach(function (s) { var o = el('option'); o.value = s; shapes.appendChild(o); });
    var sizes = $('size-list');
    vocab.generator_types.concat(MORE_SIZES).forEach(function (s) { var o = el('option'); o.value = s; sizes.appendChild(o); });
  }

  function editorFields() {
    return {
      family: $('edit-family').value,
      shape: $('edit-shape').value.trim(),
      size: $('edit-size').value.trim().toLowerCase().replace(/\s+/g, '').replace('×', 'x') || null,
      color: $('edit-color').value,
      plain: $('edit-plain').checked,
    };
  }

  function updateEditorHint() {
    var f = editorFields();
    $('edit-swatch').style.background = colorHex(f.color);
  }

  function openEditor(opts) {
    if (!vocab) {
      setStatus('✗ Couldn’t load the piece names from the backend. Try again.', 'error', $('check-status'));
      loadVocab(function () {});
      return;
    }
    editing = opts;
    var d = opts.from || { family: 'brick', shape: 'brick', size: '1x2', color: 'unknown', plain: true };
    $('edit-title').textContent = opts.addition ? 'Add a piece Spark missed'
      : opts.ids.length > 1 ? 'Fix these ' + opts.ids.length + ' pieces' : 'Fix this piece';
    $('edit-now').textContent = opts.addition ? 'Pick what the piece is. It goes into this batch.'
      : 'Now it says: ' + pieceLabel(d) + (d.plain ? ' (plain)' : '') + '. Change what’s wrong.';
    $('edit-family').value = d.family;
    $('edit-shape').value = d.shape || '';
    $('edit-size').value = d.size || '';
    $('edit-color').value = d.color;
    $('edit-plain').checked = !!d.plain;
    $('edit-count').value = 1;
    $('edit-count-row').classList.toggle('hidden', !opts.addition);
    $('edit-remove-btn').classList.toggle('hidden', !!opts.addition);
    $('edit-remove-btn').disabled = reviewBusy;
    setStatus('', null, $('edit-status'));
    updateEditorHint();
    $('edit-modal').classList.remove('hidden');
    $('edit-family').focus();
  }

  function closeEditor() {
    editing = null;
    $('edit-modal').classList.add('hidden');
  }

  ['edit-family', 'edit-size', 'edit-color', 'edit-plain'].forEach(function (id) {
    $(id).addEventListener('input', updateEditorHint);
    $(id).addEventListener('change', updateEditorHint);
  });
  $('edit-cancel-btn').addEventListener('click', closeEditor);
  $('edit-remove-btn').addEventListener('click', function () {
    if (!editing || editing.addition || reviewBusy) { return; }
    var remove = editing.ids.slice();
    closeEditor();
    setPieces(remove, 'rejected');
  });
  $('edit-save-btn').addEventListener('click', function () {
    if (!editing || reviewBusy) { return; }
    var f = editorFields();
    var payload;
    if (editing.addition) {
      var count = parseInt($('edit-count').value, 10);
      if (!(count >= 1)) { setStatus('How many? At least 1.', 'error', $('edit-status')); return; }
      f.shape = f.shape || '';
      f.count = count;
      payload = { additions: [f] };
    } else {
      payload = { corrections: editing.ids.map(function (id) { return Object.assign({ detection_id: id }, f); }) };
    }
    var what = editing.addition ? 'Added ' + plural(f.count, 'piece', 'pieces') : 'Fixed ' + plural(editing.ids.length, 'piece', 'pieces');
    setStatus('Saving…', null, $('edit-status'));
    sendReview(payload, function (ok, message) {
      if (!ok) { setStatus('✗ Not saved: ' + message, 'error', $('edit-status')); return; }
      closeEditor();
      setStatus('✓ ' + what + ': ' + pieceLabel(f) + '.', 'ok', $('check-status'));
    });
  });

  $('add-piece-btn').addEventListener('click', function () { openEditor({ addition: true }); });

  // --- confirm / undo ---

  $('confirm-btn').addEventListener('click', function () {
    if (!review || reviewBusy) { return; }
    var checkStatus = $('check-status');
    // Pieces nobody changed are accepted as they are: a person has looked at the whole batch.
    var untouched = review.data.detections.filter(function (d) { return d.status === 'proposed'; });
    var addToInventory = function () {
      reviewBusy = true;
      renderReview();
      request('POST', batchPath('/confirm'), null, REVIEW_TIMEOUT_MS, function (xhr, body, failure) {
        reviewBusy = false;
        if (!failure && xhr.status === 200 && body) {
          var s = body.summary;
          review.confirmedText = plural(body.pieces_in_batch, 'piece', 'pieces') + ' from this batch are in your inventory. ' +
            'Your inventory now has ' + plural(s.total_pieces, 'piece', 'pieces') + '.';
          openReview(review.id, { text: '', kind: null });
          window.scrollTo(0, 0);
        } else {
          renderReview();
          setStatus('✗ Not added: ' + (failure || detailOf(xhr, body)), 'error', checkStatus);
        }
      });
    };
    if (!untouched.length) { addToInventory(); return; }
    sendReview({ corrections: untouched.map(function (d) { return { detection_id: d.id, status: 'accepted' }; }) },
      function (ok, message) {
        if (ok) { addToInventory(); } else { setStatus('✗ Not added: ' + message, 'error', checkStatus); }
      });
  });

  $('undo-btn').addEventListener('click', function () {
    if (!review || reviewBusy) { return; }
    if (inventorySource === 'sample') {
      setInventorySource('uploaded');
      show('hero-view');
      return;
    }
    reviewBusy = true;
    request('POST', '/api/inventory/undo-last-batch?batch_id=' + encodeURIComponent(review.id), null, REVIEW_TIMEOUT_MS,
      function (xhr, body, failure) {
        reviewBusy = false;
        if (!failure && xhr.status === 200 && body) {
          review.confirmedText = '';
          openReview(review.id, { text: '↺ Took ' + plural(body.pieces_removed, 'piece', 'pieces') +
            ' out of your inventory. Fix anything, then add them again.', kind: 'ok' });
        } else if (xhr.status === 409) {
          setStatus('✗ Only the last batch you added can be undone, and a newer batch was added after this one.', 'error', $('check-status'));
        } else {
          setStatus('✗ Undo failed: ' + (failure || detailOf(xhr, body)), 'error', $('check-status'));
        }
      });
  });

  $('confirmed-build-btn').addEventListener('click', function () { openBuilds(); });
  $('confirmed-next-btn').addEventListener('click', function () {
    var fromSample = inventorySource === 'sample';
    setInventorySource('uploaded');
    show('capture-view');
    setStatus(fromSample ? 'Scatter your own pieces in one flat layer, then take the five photos.' :
      'Sweep those pieces aside and snap the next handful.', 'ok');
    render();
  });
  $('check-back-btn').addEventListener('click', function () {
    show(inventorySource === 'sample' ? 'hero-view' : 'capture-view'); render();
  });

  // --- finished ---------------------------------------------------------------

  $('finished-btn').addEventListener('click', function () {
    var unsent = filled();
    if (unsent && !window.confirm(unsent + ' photo' + (unsent === 1 ? ' is' : 's are') +
        ' not uploaded yet and will stay here. Finish anyway?')) { return; }
    var n = uploaded.length;
    $('finished-summary').textContent = (n ? n + (n === 1 ? ' batch' : ' batches') + ' (' + (n * 5) +
      ' photos) identified this session. ' : '') + 'Check each batch’s pieces, then add them to your inventory.';
    loadBatches();
    show('finished-view');
  });

  function loadBatches() {
    var list = $('batch-list');
    list.innerHTML = '';
    list.appendChild(el('li', null, 'Loading your batches…'));
    request('GET', '/api/inventory/batches', null, REVIEW_TIMEOUT_MS, function (xhr, body, failure) {
      list.innerHTML = '';
      if (failure || xhr.status !== 200 || !body) {
        list.appendChild(el('li', null, '✗ Could not load your batches: ' + (failure || detailOf(xhr, body))));
        return;
      }
      if (!body.batches.length) { list.appendChild(el('li', null, 'No batches yet.')); }
      body.batches.forEach(function (b) {
        var li = el('li');
        li.appendChild(document.createTextNode('Batch '));
        li.appendChild(el('code', null, b.id));
        var state = b.status === 'confirmed' ? ': ' + plural(b.pieces, 'piece', 'pieces') + ' in your inventory'
          : b.status === 'classified' ? ': ' + plural(b.pieces, 'piece', 'pieces') + ' waiting for you to check'
          : ': not identified yet (' + b.photos_passed + ' of ' + b.photos + ' photos clear)';
        li.appendChild(document.createTextNode(state + ' '));
        if (b.status !== 'uploaded') {
          li.appendChild(smallButton(b.status === 'classified' ? 'Check the pieces' : 'See the pieces',
            function () { openReview(b.id); }));
        }
        list.appendChild(li);
      });
    });
  }

  $('back-btn').addEventListener('click', function () { show('capture-view'); render(); });

  // --- build -------------------------------------------------------------------

  function section(list, text) { list.appendChild(el('h3', 'build-section', text)); }

  // The carousel: only the manual builds the backend marks has_booklet (the
  // same marker that used to put a "Make the booklet" button on a build).
  // Cover, name, piece count — nothing else on a card.
  var buildCarousel = null;   // the carousel element, while the build view is up
  var carouselCards = {};     // build id -> its card, for the way back
  var manualReturn = null;    // { id, scrollLeft } of the card a booklet was opened from

  function setBookletFrame(url) {
    var frame = $('booklet-frame');
    frame.removeAttribute('srcdoc');
    frame.src = BACKEND_URL + url;
  }

  $('booklet-frame').addEventListener('load', function () {
    var frame = $('booklet-frame');
    try {
      var doc = frame.contentDocument;
      if (doc) {
        var title = doc.querySelector('header h1');
        if (title) { title.style.display = 'none'; }
        return;
      }
    } catch (err) { /* separate app/backend ports: embed the same booklet below */ }
    var url = frame.src;
    // The development app may use port 8080 with the API on 8000. Its CORS
    // response can be embedded locally so the top bar is still the only title.
    if (url.indexOf(BACKEND_URL + '/api/') !== 0) { return; }
    fetch(url).then(function (response) {
      if (!response.ok) { throw new Error('Booklet unavailable'); }
      return response.text();
    }).then(function (html) {
      if (frame.src === url) {
        frame.srcdoc = html.replace('</head>', '<style>header h1{display:none}</style></head>');
      }
    }).catch(function () { /* keep the original frame and its error, if any */ });
  });

  function carouselCard(o) {
    var card = el('button', 'build-card');
    card.type = 'button';
    card.setAttribute('data-build-id', o.id);
    var cover = el('span', 'build-cover');
    if (o.cover) { cover.innerHTML = o.cover; } // booklet.picture()'s finished model, from the backend
    card.appendChild(cover);
    card.appendChild(el('span', 'build-name', o.title));
    card.appendChild(el('span', 'build-pieces', plural(o.pieces, 'piece', 'pieces')));
    card.addEventListener('click', function () { openManual(o); });
    carouselCards[o.id] = card;
    return card;
  }

  function openManual(o) {
    manualReturn = { id: o.id, scrollLeft: buildCarousel ? buildCarousel.scrollLeft || 0 : 0 };
    setStatus('Making the booklet…', null, $('build-status'));
    var ask = { set: o.set || o.id, source: inventorySource };
    request('POST', '/api/builds', ask, BUILD_TIMEOUT_MS, function (xhr, body, failure) {
      if (!failure && xhr.status === 201 && body && body.booklet_url) {
        bookletChips(false);
        $('booklet-title').textContent = o.title;
        setBookletFrame(body.booklet_url);
        setStatus('', null, $('build-status'));
        show('booklet-view');
      } else {
        setStatus('✗ ' + (failure || (body && body.message) || detailOf(xhr, body)), 'error', $('build-status'));
      }
    });
  }

  $('booklet-back-btn').addEventListener('click', function () {
    show('build-view');
    if (buildCarousel && manualReturn) {
      buildCarousel.scrollLeft = manualReturn.scrollLeft; // back on the same card
      var card = carouselCards[manualReturn.id];
      if (card && card.focus) { card.focus(); }
    }
  });

  function openBuilds() {
    var list = $('build-list');
    var buildStatus = $('build-status');
    show('build-view');
    list.innerHTML = '';
    buildCarousel = null;
    carouselCards = {};
    $('build-inventory').textContent = 'Checking your inventory…';
    setStatus('', null, buildStatus);
    request('GET', '/api/builds/options?source=' + inventorySource, null, BUILD_TIMEOUT_MS, function (xhr, body, failure) {
      if (failure || xhr.status !== 200 || !body) {
        $('build-inventory').textContent = '';
        setStatus('✗ ' + (failure || detailOf(xhr, body)), 'error', buildStatus);
        return;
      }
      if (body.scan_first) { // no confirmed pieces yet: no catalog, only the way to get some
        $('build-inventory').textContent = body.scan_first;
        list.appendChild(el('button', 'btn btn-primary', '📷 Scan a handful')).addEventListener('click', function () {
          show('capture-view');
          render();
        });
        list.appendChild(el('button', 'btn btn-secondary', 'Use sample images')).addEventListener('click', function () {
          show('capture-view');
          render();
          loadSample();
        });
        return;
      }
      var inv = body.inventory;
      $('build-inventory').textContent = inv.total_pieces
        ? inv.total_pieces + (inventorySource === 'sample' ? ' sample pieces. Your own pieces are separate.' :
          ' confirmed pieces. These ideas will use only the pieces you have.')
        : 'No confirmed pieces yet: scan a batch, review it and confirm it first.';
      $('build-back-btn').textContent = inventorySource === 'sample' ? '← Back to the sample pieces' : '← Back to scanning';
      var bookletBuilds = body.options.filter(function (o) {
        return o.kind === 'manual' && o.has_booklet && o.status === 'fit';
      });
      buildCarousel = el('div', 'build-carousel');
      buildCarousel.id = 'build-carousel';
      bookletBuilds.forEach(function (o) { buildCarousel.appendChild(carouselCard(o)); });
      if (body.wonder && body.wonder.enabled) {
        list.appendChild(wonderSection(body.wonder, inv));
      }
      if (bookletBuilds.length) {
        if (body.wonder && body.wonder.enabled || inventorySource === 'sample') {
          section(list, inventorySource === 'sample' ? "From the sample kit's book" : 'Book designs that fit your pieces');
        }
        list.appendChild(buildCarousel);
      }
    });
  }

  // --- generate a new design (Muse Wonder, only when the backend turns it on) ---

  function wonderResult(r) {
    var box = el('div', 'option ' + (r.booklet_url ? 'yes' : 'no'));
    box.appendChild(el('h3', null, (r.title || 'New design') + ' · Muse Wonder'));
    box.appendChild(el('span', 'chip', r.booklet_url ? (inventorySource === 'sample'
      ? '✓ Checked: sample pieces, all held by studs' : '✓ Checked: only your pieces, all held by studs')
      : r.status === 'short' ? 'Not enough pieces' : 'No design passed the check'));
    box.appendChild(el('p', null, r.message));
    if (r.parts) {
      var parts = el('ul', 'wparts');
      r.parts.forEach(function (p) { parts.appendChild(el('li', null, p.qty + '× ' + p.label)); });
      box.appendChild(parts);
    }
    if (r.problems && r.problems.length) {
      box.appendChild(el('p', 'note', 'What the checker found in the last try: ' + r.problems.slice(0, 3).join(' · ')));
    }
    if (r.booklet_url) {
      var link = el('a', 'btn btn-done', '📖 Open the booklet' + (r.steps ? ' (' + r.steps + ' steps)' : ''));
      link.href = BACKEND_URL + r.booklet_url;
      link.addEventListener('click', function (event) {
        event.preventDefault();
        openWonderBooklet(r.title || 'New design', r.booklet_url, r.step_words);
      });
      box.appendChild(link);
    }
    if (r.tries && r.tries.length) {
      box.appendChild(el('p', 'note', r.tries.length + (r.tries.length === 1 ? ' try' : ' tries') + ', ' +
        Math.round(r.seconds) + ' s, $' + Number(r.usd).toFixed(2) + '.'));
    }
    return box;
  }

  function wonderSection(w, inv) {
    var wrap = el('div', 'wonder');
    section(wrap, inventorySource === 'sample' ? 'Three ideas from the sample pieces' : 'Three ideas from my pieces');
    wrap.appendChild(el('p', 'note', 'Muse Wonder looks at your pieces and invents three things to build. ' +
      'Every design is checked before you see it.'));
    var cards = el('div', 'idea-cards');
    var out = el('div', 'wresult');
    var status = el('p', 'status');
    var tracker = el('div', 'hidden');
    var find = el('button', 'btn btn-primary', 'Find three ideas');
    var supported = w.supported_pieces === undefined ? inv.total_pieces : w.supported_pieces;
    find.disabled = !supported || w.busy;
    if (supported < inv.total_pieces) {
      wrap.appendChild(el('p', 'note', 'Ideas use the ' + supported + ' pieces whose shapes we can check. ' +
        'The remaining pieces stay in your inventory.'));
    }
    var actionButtons = [find];

    function drawIdeas() {
      cards.innerHTML = '';
      actionButtons = [find];
      (w.ideas || []).slice(0, 3).forEach(function (idea) {
        var card = el('div', 'idea-card');
        var cover = el('div', 'build-cover');
        if (idea.cover) { cover.innerHTML = idea.cover; }
        card.appendChild(cover);
        card.appendChild(el('h4', null, idea.title));
        card.appendChild(el('span', 'badge model-chip', '✨ Designed by Muse Wonder · ✓ checked by BinBuild'));
        card.appendChild(el('p', null, idea.description));
        card.appendChild(el('p', 'note', idea.pieces + ' pieces · checked against these pieces'));
        var choose = el('button', 'btn btn-primary', 'Make this booklet');
        choose.disabled = w.busy;
        actionButtons.push(choose);
        choose.addEventListener('click', function () {
          runWonderJob('/api/builds/wonder', {
            idea_id: idea.id, inventory_key: w.inventory_key, source: inventorySource,
          }, choose, out, status, function (job) {
            if (job.build) { out.insertBefore(wonderResult(job.build), out.firstChild); }
          }, actionButtons, tracker);
        });
        card.appendChild(choose);
        cards.appendChild(card);
      });
      find.textContent = (w.ideas || []).length ? 'Find different ideas' : 'Find three ideas';
    }

    find.addEventListener('click', function () {
      runWonderJob('/api/builds/wonder/ideas', { source: inventorySource }, find, out, status, function (job) {
        w.ideas = job.ideas || [];
        w.inventory_key = job.inventory_key;
        drawIdeas();
      }, actionButtons, tracker);
    });
    if (w.busy) { setStatus('A design is already being prepared. Reopen this page when it finishes.', null, status); }
    drawIdeas();
    wrap.appendChild(cards);
    wrap.appendChild(find);
    wrap.appendChild(tracker);
    wrap.appendChild(status);
    wrap.appendChild(out);
    if (w.recent && w.recent.length) {
      var saved = el('details', 'saved-designs');
      saved.appendChild(el('summary', null, 'Saved designs for these pieces'));
      w.recent.forEach(function (r) { saved.appendChild(wonderResult(r)); });
      wrap.appendChild(saved);
    }
    return wrap;
  }

  function bookletChips(wonder, stepWords) {
    var chips = $('booklet-models');
    chips.innerHTML = '';
    chips.classList.toggle('hidden', !wonder);
    if (wonder) {
      chips.appendChild(el('span', 'badge model-chip', 'Designed by Muse Wonder'));
      if (stepWords === 'muse-spark') {
        chips.appendChild(el('span', 'badge model-chip', 'Steps written by Muse Spark'));
      }
    }
  }

  function openWonderBooklet(title, url, stepWords) {
    manualReturn = null;
    bookletChips(true, stepWords);
    $('booklet-title').textContent = title;
    setBookletFrame(url);
    show('booklet-view');
  }

  function runWonderJob(path, payload, btn, out, status, onDone, controls, tracker) {
    var failedPolls = 0;
    var ideas = path.indexOf('/ideas') >= 0;
    var steps = (ideas ? ['Muse Wonder designs', 'BinBuild checks each design'] :
      ['BinBuild checks it again', 'Muse Spark writes the steps', 'Booklet ready'])
      .map(function (label) { return { label: label, state: 'waiting' }; });
    function track(job) {
      var index = ideas ? { designing: 0, checking: 1 }[job.stage] : { checking: 0, writing: 1 }[job.stage];
      if (job.stage === 'done') {
        steps.forEach(function (step, n) {
          step.state = !ideas && n === 2 && !(job.build && job.build.booklet_url) ? 'failed' : 'done';
          if (!ideas && n === 1 && job.build && job.build.step_words !== 'muse-spark') {
            step.state = job.build.step_words === 'binbuild' ? 'failed' : 'waiting';
            step.detail = job.build.step_words === 'binbuild' ? 'Using BinBuild’s own step words' : 'Step writer not reported';
          }
        });
      } else if (job.stage === 'failed') {
        steps.forEach(function (step) { if (step.state === 'active') { step.state = 'failed'; } });
      } else if (index !== undefined) {
        steps.forEach(function (step, n) { step.state = n < index ? 'done' : n === index ? 'active' : 'waiting'; });
      }
      if (tracker) { renderTracker(tracker, steps); }
    }
    track({});
    var label = btn.textContent;
    btn.disabled = true;
    (controls || []).forEach(function (control) { control.disabled = true; });
    out.innerHTML = '';
    btn.textContent = 'Preparing…';
    setStatus('Starting…', null, status);
    function finish() {
      (controls || []).forEach(function (control) { control.disabled = false; });
      btn.disabled = false; btn.textContent = label;
    }
    function poll(jobId) {
      request('GET', '/api/builds/wonder/jobs/' + encodeURIComponent(jobId), null, BUILD_TIMEOUT_MS,
        function (xhr, body, failure) {
          if (xhr.status === 404) {
            finish();
            setStatus('✗ ' + (failure || detailOf(xhr, body)), 'error', status);
            return;
          }
          if (failure || xhr.status !== 200 || !body) {
            failedPolls += 1;
            if (failedPolls <= 3) {
              setTimeout(function () { poll(jobId); }, WONDER_POLL_MS);
            } else {
              finish();
              setStatus('Lost contact with the design job. It may still finish: reopen What can I build? ' +
                (path.indexOf('/ideas') >= 0 ? 'to recover your ideas.' :
                  'to see it under Saved designs for these pieces.'), 'error', status);
            }
            return;
          }
          failedPolls = 0;
          track(body);
          if (body.state === 'running') {
            setStatus(body.message || 'Wonder is checking the ideas…', null, status);
            setTimeout(function () { poll(jobId); }, WONDER_POLL_MS);
          } else if (body.state === 'done') {
            finish();
            setStatus(body.message || '', null, status);
            onDone(body);
          } else {
            finish();
            setStatus('✗ ' + (body.message || 'The design job could not be completed.'), 'error', status);
          }
        });
    }
    request('POST', path, payload, BUILD_TIMEOUT_MS, function (xhr, body, failure) {
      if (!failure && xhr.status === 202 && body && body.job_id) {
        setStatus(path.indexOf('/ideas') >= 0 ? 'Wonder is finding ideas from these pieces…' :
          'Preparing the booklet for this design…', null, status);
        setTimeout(function () { poll(body.job_id); }, WONDER_POLL_MS);
      } else {
        finish();
        if (!failure && xhr.status === 401) {
          setStatus('Designing a new model calls Muse Wonder, so the public demo needs the access key.', 'error', status);
          var example = el('a', 'btn btn-secondary', 'See a recorded Wonder design');
          example.href = BACKEND_URL + '/api/wonder/example';
          example.addEventListener('click', function (event) {
            event.preventDefault();
            openWonderBooklet('Recorded Wonder design', '/api/wonder/example');
          });
          out.appendChild(example);
        } else {
          setStatus('✗ ' + (failure || detailOf(xhr, body)), 'error', status);
        }
      }
    });
  }

  $('ask-build-btn').addEventListener('click', openBuilds);
  $('build-open-btn').addEventListener('click', openBuilds);
  $('sample-images-btn').addEventListener('click', loadSample);
  $('sample-bin-btn').addEventListener('click', loadSample);
  $('sample-link').addEventListener('click', function () { show('capture-view'); render(); loadSample(); });
  $('start-btn').addEventListener('click', function () { setInventorySource('uploaded'); show('capture-view'); render(); });
  $('home-btn').addEventListener('click', function () { show('hero-view'); });
  $('build-back-btn').addEventListener('click', function () {
    if (inventorySource === 'sample' && review) { openReview(review.id); }
    else { show('capture-view'); render(); }
  });

  // --- backend reachability ---------------------------------------------------

  function checkBackend() {
    var line = $('backend-line');
    var text = $('backend-text');
    line.classList.remove('up', 'down');
    text.textContent = 'Backend: checking ' + BACKEND_URL + ' …';
    var controller = window.AbortController ? new AbortController() : null;
    var timer = setTimeout(function () { if (controller) { controller.abort(); } }, HEALTH_TIMEOUT_MS);
    fetch(BACKEND_URL + '/health', controller ? { signal: controller.signal } : {})
      .then(function (res) {
        if (!res.ok) { throw new Error('HTTP ' + res.status); }
        line.classList.add('up');
        line.classList.add('hidden');
        text.textContent = 'Backend: connected (' + BACKEND_URL + ')';
      })
      .catch(function () {
        line.classList.add('down');
        line.classList.remove('hidden');
        text.textContent = 'Backend: not reachable at ' + BACKEND_URL + '. Uploads will fail until it is.';
      })
      .then(function () { clearTimeout(timer); });
  }

  $('backend-retry').addEventListener('click', checkBackend);

  render();
  checkBackend();
})();
