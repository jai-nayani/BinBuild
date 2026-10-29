/* BinBuild PWA — capture loop: snap -> review -> confirm -> upload -> check -> identify -> Finished.
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
 * Uses the native camera input (capture="environment"), which works over plain
 * HTTP on the home network. Nothing here needs the service worker.
 *
 * "What can I build?" lists what the confirmed inventory can build (known sets
 * and pre-generated BrickGPT designs, from GET /api/builds/options), names
 * what is missing for the rest, and makes a step-by-step booklet for one that
 * fits (POST /api/builds), opened from the backend as a printable page.
 */

// Where the FastAPI backend lives. Default: the machine that served this page,
// port 8000. To point somewhere else, replace with e.g. 'http://192.168.1.23:8000'.
var BACKEND_URL = window.location.protocol + '//' + window.location.hostname + ':8000';

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
  var IDENTIFY_TIMEOUT_MS = 240000;
  var HEALTH_TIMEOUT_MS = 4000;
  var BUILD_TIMEOUT_MS = 30000;

  var slots = VIEWS.map(function () { return null; }); // confirmed { file, url } per view
  var pending = null;   // { file, url } under review, not yet in the batch
  var uploading = false;
  var batch = null;     // uploaded batch not yet identified: { id, ready, retake: [notice, ...] }
  var busy = false;     // a retake upload or an Identify call is running
  var uploaded = [];    // { batchId, photos, pieces } per batch identified this session

  function $(id) { return document.getElementById(id); }

  var cameraInput = $('camera-input');
  var galleryInput = $('gallery-input');
  var retakeInput = $('retake-input');
  var statusEl = $('status');
  var uploadBtn = $('upload-btn');
  var identifyBtn = $('identify-btn');
  var progressEl = $('upload-progress');

  function setStatus(msg, kind, el) {
    el = el || statusEl;
    el.textContent = msg;
    el.classList.toggle('error', kind === 'error');
    el.classList.toggle('ok', kind === 'ok');
  }

  function show(viewId) {
    ['capture-view', 'review-view', 'finished-view', 'build-view'].forEach(function (id) {
      $(id).classList.toggle('hidden', id !== viewId);
    });
    window.scrollTo(0, 0);
  }

  function nextSlot() { return slots.indexOf(null); } // -1 when the batch is full
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
      $('shot-hint').textContent = 'Upload the batch, or tap ✕ on a photo to retake it.';
    } else {
      $('shot-title').textContent = 'Batch ' + batchNo + ' · photo ' + (next + 1) + ' of 5: ' + VIEWS[next].label;
      $('shot-hint').textContent = VIEWS[next].hint;
    }
    var full = next === -1;
    $('snap-btn').classList.toggle('hidden', full || !!batch);
    $('gallery-btn').classList.toggle('hidden', full || !!batch);

    var thumbs = $('thumbs');
    thumbs.innerHTML = '';
    slots.forEach(function (photo, i) {
      var wrap = document.createElement('div');
      wrap.className = 'thumb' + (photo ? '' : ' empty') + (i === next && !batch ? ' next' : '') +
        (needsRetake(VIEWS[i].key) ? ' failed' : '');
      var tag = document.createElement('span');
      tag.className = 'tag';
      tag.textContent = VIEWS[i].key;
      if (photo) {
        var img = document.createElement('img');
        img.src = photo.url;
        img.alt = VIEWS[i].label;
        wrap.appendChild(img);
        if (!batch) { // once uploaded, photos change only through a retake
          var remove = document.createElement('button');
          remove.type = 'button';
          remove.textContent = '✕';
          remove.disabled = uploading;
          remove.setAttribute('aria-label', 'Retake the ' + VIEWS[i].label);
          remove.addEventListener('click', function () {
            URL.revokeObjectURL(photo.url);
            slots[i] = null;
            setStatus('Removed the ' + VIEWS[i].label + '. Take it again.');
            render();
          });
          wrap.appendChild(remove);
        }
      }
      wrap.appendChild(tag);
      thumbs.appendChild(wrap);
    });

    uploadBtn.classList.toggle('hidden', !!batch);
    uploadBtn.disabled = !full || uploading;
    uploadBtn.textContent = uploading ? 'Uploading…' : '⬆ Upload batch (' + filled() + '/5)';
    identifyBtn.classList.toggle('hidden', !(batch && batch.ready));
    identifyBtn.disabled = busy;
    identifyBtn.textContent = busy ? 'Identifying… (about a minute)' : '🔍 Identify pieces';
    $('finished-btn').disabled = uploading || busy || !!batch || uploaded.length === 0;
  }

  // --- snap + review ----------------------------------------------------------

  function onPicked(input) {
    var file = input.files && input.files[0];
    input.value = ''; // so picking the same file again still fires "change"
    if (!file) { return; } // camera cancelled: stay where we are
    if (file.type && file.type.indexOf('image/') !== 0) {
      setStatus('That file is not a photo (' + file.type + ').', 'error');
      return;
    }
    if (nextSlot() === -1 || batch) { return; }
    if (pending) { URL.revokeObjectURL(pending.url); }
    pending = { file: file, url: URL.createObjectURL(file) };
    var view = VIEWS[nextSlot()];
    $('review-title').textContent = 'Check the ' + view.label;
    $('review-img').src = pending.url;
    show('review-view');
  }

  cameraInput.addEventListener('change', function () { onPicked(cameraInput); });
  galleryInput.addEventListener('change', function () { onPicked(galleryInput); });

  $('use-btn').addEventListener('click', function () {
    if (!pending) { return; }
    var i = nextSlot();
    slots[i] = pending;
    pending = null;
    $('review-img').removeAttribute('src');
    setStatus(nextSlot() === -1
      ? 'All 5 photos taken. Upload the batch.'
      : 'Saved the ' + VIEWS[i].label + '. Next: ' + VIEWS[nextSlot()].label + '.');
    show('capture-view');
    render();
  });

  $('cancel-review-btn').addEventListener('click', function () {
    if (pending) { URL.revokeObjectURL(pending.url); }
    pending = null;
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
          setStatus('✓ Uploaded' + (body.duplicate ? ' (these 5 photos were already sent as ' + body.batch_id + ')' : '') +
            '. All 5 photos are clear. Tap Identify pieces before you sweep them aside.', 'ok');
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
          setStatus('✓ The ' + view + ' photo is clear now. All 5 photos are clear: tap Identify pieces.', 'ok');
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
    setStatus('Spark is looking at the pieces… this takes about a minute. Keep the pieces where they are.');
    render();
    post('/api/inventory/batch/' + encodeURIComponent(batch.id) + '/classify', null, IDENTIFY_TIMEOUT_MS,
      function (xhr, body, failure) {
        busy = false;
        if (!failure && xhr.status === 200 && body) {
          uploaded.push({ batchId: batch.id, photos: 5, pieces: body.pieces });
          slots.forEach(function (photo) { if (photo) { URL.revokeObjectURL(photo.url); } });
          slots = VIEWS.map(function () { return null; });
          batch = null;
          setStatus('✓ Found ' + body.pieces + ' pieces (' + countByFamily(body.detections) + '). They wait for your ' +
            'review: nothing goes into the inventory until you confirm. Sweep these pieces aside and snap the next handful.', 'ok');
        } else if (!failure && xhr.status === 422 && body && body.retake && body.retake.length) {
          batch.ready = false;
          batch.retake = body.retake;
          setStatus('Spark could not use ' + (body.retake.length === 1 ? 'one photo' : body.retake.length + ' photos') +
            '. Nothing was added. Retake it, then tap Identify pieces again.', 'error');
          openRetake();
        } else {
          setStatus('✗ Identify failed: ' + (failure || detailOf(xhr, body)) + ' Nothing was added. Tap Identify pieces to try again.', 'error');
        }
        render();
      });
  });

  // --- finished ---------------------------------------------------------------

  $('finished-btn').addEventListener('click', function () {
    var unsent = filled();
    if (unsent && !window.confirm(unsent + ' photo' + (unsent === 1 ? ' is' : 's are') +
        ' not uploaded yet and will stay here. Finish anyway?')) { return; }
    var n = uploaded.length;
    $('finished-summary').textContent = n + (n === 1 ? ' batch' : ' batches') + ' (' + (n * 5) +
      ' photos) checked and identified this session. Review and confirm them to add the pieces to your inventory.';
    var list = $('batch-list');
    list.innerHTML = '';
    uploaded.forEach(function (b, i) {
      var li = document.createElement('li');
      li.textContent = 'Batch ' + (i + 1) + ': ';
      var code = document.createElement('code');
      code.textContent = b.batchId;
      li.appendChild(code);
      li.appendChild(document.createTextNode(' (' + b.pieces + ' pieces found, waiting for review)'));
      list.appendChild(li);
    });
    show('finished-view');
  });

  $('back-btn').addEventListener('click', function () { show('capture-view'); render(); });

  // --- build -------------------------------------------------------------------

  var CHIP = {
    fit: '✓ You can build this', patched: '✓ You can build this (a few bricks swapped for smaller ones)',
    short: 'Not enough pieces yet', not_connected: "Can't be built: the design has a loose part",
  };

  function buildable(o) { return o.status === 'fit' || o.status === 'patched'; }

  function openBuilds() {
    var list = $('build-list');
    var buildStatus = $('build-status');
    show('build-view');
    list.innerHTML = '';
    $('build-inventory').textContent = 'Checking your inventory…';
    setStatus('', null, buildStatus);
    request('GET', '/api/builds/options', null, BUILD_TIMEOUT_MS, function (xhr, body, failure) {
      if (failure || xhr.status !== 200 || !body) {
        $('build-inventory').textContent = '';
        setStatus('✗ ' + (failure || detailOf(xhr, body)), 'error', buildStatus);
        return;
      }
      var inv = body.inventory;
      $('build-inventory').textContent = inv.total_pieces
        ? inv.total_pieces + ' confirmed pieces in your inventory: ' + inv.generator_ready +
          ' plain bricks BrickGPT can use, ' + inv.other + ' other pieces.'
        : 'No confirmed pieces yet: scan a batch, review it and confirm it first.';
      var yes = body.options.filter(buildable);
      var no = body.options.filter(function (o) { return !buildable(o); });
      if (!yes.length) {
        setStatus('Nothing fits your pieces yet. Each option below says what is missing.', null, buildStatus);
      }
      yes.forEach(function (o) { list.appendChild(optionCard(o)); });
      if (no.length) {
        var more = document.createElement('details');
        var label = document.createElement('summary');
        label.textContent = 'Not enough pieces yet (' + no.length + ')';
        more.appendChild(label);
        no.forEach(function (o) { more.appendChild(optionCard(o)); });
        list.appendChild(more);
      }
    });
  }

  function optionCard(o) {
    var card = document.createElement('div');
    card.className = 'option ' + (buildable(o) ? 'yes' : 'no');
    var title = document.createElement('h3');
    title.textContent = o.title + (o.kind === 'brickgpt' ? ' · BrickGPT design' : ' · set');
    var chip = document.createElement('span');
    chip.className = 'chip';
    chip.textContent = CHIP[o.status] || o.status;
    var text = document.createElement('p');
    text.textContent = o.message;
    card.appendChild(title);
    card.appendChild(chip);
    card.appendChild(text);
    if (buildable(o)) {
      var btn = document.createElement('button');
      btn.className = 'btn btn-primary';
      btn.textContent = '📖 Make the booklet';
      btn.addEventListener('click', function () { makeBooklet(o, btn); });
      card.appendChild(btn);
    }
    return card;
  }

  function makeBooklet(o, btn) {
    btn.disabled = true;
    btn.textContent = 'Making the booklet…';
    var ask = o.kind === 'set' ? { set: o.id } : { design: o.id };
    request('POST', '/api/builds', ask, BUILD_TIMEOUT_MS, function (xhr, body, failure) {
      if (!failure && xhr.status === 201 && body && body.booklet_url) {
        // A link, not window.open: phones block pop-ups opened after a network call.
        var link = document.createElement('a');
        link.className = 'btn btn-done';
        link.href = BACKEND_URL + body.booklet_url;
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = '📖 Open the booklet (' + body.steps + ' steps)';
        btn.replaceWith(link);
      } else {
        btn.disabled = false;
        btn.textContent = '📖 Make the booklet';
        setStatus('✗ ' + (failure || (body && body.message) || detailOf(xhr, body)), 'error', $('build-status'));
      }
    });
  }

  $('ask-build-btn').addEventListener('click', openBuilds);
  $('build-open-btn').addEventListener('click', openBuilds);
  $('build-back-btn').addEventListener('click', function () { show('capture-view'); render(); });

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
        text.textContent = 'Backend: connected (' + BACKEND_URL + ')';
      })
      .catch(function () {
        line.classList.add('down');
        text.textContent = 'Backend: not reachable at ' + BACKEND_URL + '. Uploads will fail until it is.';
      })
      .then(function () { clearTimeout(timer); });
  }

  $('backend-retry').addEventListener('click', checkBackend);

  render();
  checkBackend();
})();
