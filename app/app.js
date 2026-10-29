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
    ['capture-view', 'review-view', 'finished-view', 'check-view', 'build-view'].forEach(function (id) {
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
    $('finished-btn').disabled = uploading || busy || !!batch;
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
          var found = batch.id;
          uploaded.push({ batchId: batch.id, photos: 5, pieces: body.pieces });
          slots.forEach(function (photo) { if (photo) { URL.revokeObjectURL(photo.url); } });
          slots = VIEWS.map(function () { return null; });
          batch = null;
          setStatus('✓ Found ' + body.pieces + ' pieces (' + countByFamily(body.detections) + '). Check them and add them ' +
            'to your inventory (Finished lists every batch), then sweep these pieces aside and snap the next handful.', 'ok');
          render();
          openReview(found, { text: '✓ Spark found ' + body.pieces + ' pieces. Check them, then add them to your inventory.', kind: 'ok' });
          return;
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
                     focus: null, open: keep ? keep.open : {}, confirmedText: keep ? keep.confirmedText : '' };
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
    var gen = total(kept.filter(function (d) { return d.generator_type; }));
    var fixed = data.detections.filter(function (d) { return d.status === 'corrected' || d.source === 'manual'; }).length;

    $('check-title').textContent = confirmed ? 'These pieces are in your inventory' : 'Check the pieces';
    $('check-intro').textContent = confirmed
      ? 'This batch is added. To change a piece, undo it first.'
      : kept.length
        ? 'Tap a row to see those pieces on the photo. Fix anything that’s wrong, remove anything that isn’t a piece, then add them to your inventory.'
        : 'No pieces in this batch yet. Add the pieces Spark missed, or go back and identify it again.';
    $('check-summary').textContent = plural(data.pieces, 'piece', 'pieces') + ' · ' +
      plural(gen, 'plain brick', 'plain bricks') + ' BrickGPT can use' +
      (fixed ? ' · ' + fixed + ' fixed by you' : '') + (removed.length ? ' · ' + removed.length + ' removed' : '');
    renderDots(kept);

    var list = $('check-list');
    list.innerHTML = '';
    groupsOf(kept).forEach(function (g) { list.appendChild(groupCard(g, confirmed)); });
    if (removed.length) {
      list.appendChild(el('p', 'section-label', 'Removed: not added to your inventory'));
      groupsOf(removed).forEach(function (g) { list.appendChild(groupCard(g, confirmed)); });
    }

    $('add-piece-btn').classList.toggle('hidden', confirmed);
    $('add-piece-btn').disabled = reviewBusy;
    var confirmBtn = $('confirm-btn');
    confirmBtn.parentNode.classList.toggle('hidden', confirmed);
    confirmBtn.disabled = reviewBusy || !data.photos_ready || data.pieces === 0;
    confirmBtn.textContent = reviewBusy ? 'Saving…' : '✓ Add ' + plural(data.pieces, 'piece', 'pieces') + ' to my inventory';
    $('confirmed-card').classList.toggle('hidden', !confirmed);
    if (confirmed) {
      $('confirmed-text').textContent = review.confirmedText ||
        plural(data.pieces, 'piece', 'pieces') + ' from this batch are in your inventory.';
    }
  }

  function renderDots(kept) {
    var box = $('check-dots');
    var svg = $('check-outlines');
    var photo = review.photo;
    var outlined = kept.some(function (d) { return d.region && d.region.mask && d.region.mask.path; });
    var caption = outlined
      ? 'Each outline is one piece, cut out by SAM. Tap a dot or a row to see which is which.'
      : 'Each dot is one piece Spark found. Tap a dot or a row to see which is which.';
    box.innerHTML = '';
    svg.innerHTML = '';
    if (!photo) { $('check-caption').textContent = ''; return; }
    svg.setAttribute('viewBox', '0 0 ' + photo.width + ' ' + photo.height);
    kept.forEach(function (d) {
      var m = d.region && d.region.mask;
      if (!m || !m.path) { return; }
      // the path is in the mask's own pixels; its box is in the photo's
      var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
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
    var removed = d.status === 'rejected';
    var many = g.items.length > 1;
    var card = el('div', 'piece-group' + (review.selected === g.key ? ' sel' : '') + (removed ? ' removed' : ''));
    var head = el('div', 'pg-head');
    var swatch = el('span', 'swatch');
    swatch.style.background = colorHex(d.color);
    head.appendChild(swatch);
    head.appendChild(el('span', null, total(g.items) + '× ' + pieceLabel(d)));
    if (d.generator_type) { head.appendChild(el('span', 'badge gen', 'BrickGPT brick')); }
    if (d.status === 'corrected') { head.appendChild(el('span', 'badge fixed', 'fixed')); }
    if (d.source === 'manual') { head.appendChild(el('span', 'badge fixed', 'added by you')); }
    head.addEventListener('click', function () { select(g.key); });
    card.appendChild(head);
    if (readOnly) { return card; }

    var actions = el('div', 'pg-actions');
    if (removed) {
      actions.appendChild(smallButton('↩ Put back' + (many ? ' all ' + g.items.length : ''),
        function () { setPieces(ids(g.items), 'accepted'); }));
    } else {
      actions.appendChild(smallButton('✎ Fix' + (many ? ' all ' + g.items.length : ''),
        function () { openEditor({ ids: ids(g.items), from: d }); }));
      actions.appendChild(smallButton('✕ Remove' + (many ? ' all ' + g.items.length : ''),
        function () { setPieces(ids(g.items), 'rejected'); }));
    }
    if (many) {
      actions.appendChild(smallButton(review.open[g.key] ? 'Hide ▴' : 'One by one ▾', function () {
        review.open[g.key] = !review.open[g.key];
        review.selected = g.key;
        renderReview();
      }));
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
          row.appendChild(smallButton('✎ Fix', function () { openEditor({ ids: [item.id], from: item }); }));
          row.appendChild(smallButton('✕ Remove', function () { setPieces([item.id], 'rejected'); }));
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
    $('edit-generator').textContent = isGenerator(f.family, f.size, f.plain)
      ? '✓ A plain ' + f.size + ' brick: BrickGPT can build with it.'
      : 'BrickGPT can’t build with this one (it only uses plain bricks: 1x1, 1x2, 1x4, 1x6, 1x8, 2x2, 2x4, 2x6). It still goes into your inventory.';
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
            'Your inventory now has ' + plural(s.total_pieces, 'piece', 'pieces') + ': ' +
            plural(s.generator_ready.total, 'plain brick', 'plain bricks') + ' BrickGPT can use, ' +
            (s.total_pieces - s.generator_ready.total) + ' other pieces.';
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
    show('capture-view');
    setStatus('Sweep those pieces aside and snap the next handful.', 'ok');
    render();
  });
  $('check-back-btn').addEventListener('click', function () { show('capture-view'); render(); });

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
