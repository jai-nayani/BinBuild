/* BinBuild PWA — capture loop: snap -> review -> confirm -> upload -> Finished.
 *
 * Each batch is 5 photos of one handful: top view plus 4 sides. Every snap is
 * reviewed (retake or use) before it joins the batch; a full batch uploads to
 * POST /api/inventory/batch, which saves it on disk and returns a batch_id.
 *
 * Uses the native camera input (capture="environment"), which works over plain
 * HTTP on the home network. Nothing here needs the service worker.
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
  var HEALTH_TIMEOUT_MS = 4000;

  var slots = VIEWS.map(function () { return null; }); // confirmed { file, url } per view
  var pending = null;   // { file, url } under review, not yet in the batch
  var uploading = false;
  var uploaded = [];    // { batchId, photos } per batch the backend accepted

  function $(id) { return document.getElementById(id); }

  var cameraInput = $('camera-input');
  var galleryInput = $('gallery-input');
  var statusEl = $('status');
  var uploadBtn = $('upload-btn');
  var progressEl = $('upload-progress');

  function setStatus(msg, kind) {
    statusEl.textContent = msg;
    statusEl.classList.toggle('error', kind === 'error');
    statusEl.classList.toggle('ok', kind === 'ok');
  }

  function show(viewId) {
    ['capture-view', 'review-view', 'finished-view'].forEach(function (id) {
      $(id).classList.toggle('hidden', id !== viewId);
    });
    window.scrollTo(0, 0);
  }

  function nextSlot() { return slots.indexOf(null); } // -1 when the batch is full
  function filled() { return slots.filter(Boolean).length; }

  // --- render -----------------------------------------------------------------

  function render() {
    var next = nextSlot();
    var batchNo = uploaded.length + 1;
    if (next === -1) {
      $('shot-title').textContent = 'Batch ' + batchNo + ' · all 5 photos taken';
      $('shot-hint').textContent = 'Upload the batch, or tap ✕ on a photo to retake it.';
    } else {
      $('shot-title').textContent = 'Batch ' + batchNo + ' · photo ' + (next + 1) + ' of 5: ' + VIEWS[next].label;
      $('shot-hint').textContent = VIEWS[next].hint;
    }
    var full = next === -1;
    $('snap-btn').classList.toggle('hidden', full);
    $('gallery-btn').classList.toggle('hidden', full);

    var thumbs = $('thumbs');
    thumbs.innerHTML = '';
    slots.forEach(function (photo, i) {
      var wrap = document.createElement('div');
      wrap.className = 'thumb' + (photo ? '' : ' empty') + (i === next ? ' next' : '');
      var tag = document.createElement('span');
      tag.className = 'tag';
      tag.textContent = VIEWS[i].key;
      if (photo) {
        var img = document.createElement('img');
        img.src = photo.url;
        img.alt = VIEWS[i].label;
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
        wrap.appendChild(img);
        wrap.appendChild(remove);
      }
      wrap.appendChild(tag);
      thumbs.appendChild(wrap);
    });

    uploadBtn.disabled = !full || uploading;
    uploadBtn.textContent = uploading ? 'Uploading…' : '⬆ Upload batch (' + filled() + '/5)';
    $('finished-btn').disabled = uploading || uploaded.length === 0;
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
    if (nextSlot() === -1) { return; }
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

  function uploadBatch() {
    if (uploading || nextSlot() !== -1) { return; }
    var form = new FormData();
    slots.forEach(function (photo, i) {
      var ext = (photo.file.name.match(/\.[A-Za-z0-9]+$/) || ['.jpg'])[0];
      form.append('photos', photo.file, (i + 1) + '-' + VIEWS[i].key + ext);
    });

    uploading = true;
    progressEl.value = 0;
    progressEl.classList.remove('hidden');
    setStatus('Uploading 5 photos to ' + BACKEND_URL + ' …');
    render();

    var xhr = new XMLHttpRequest();
    xhr.open('POST', BACKEND_URL + '/api/inventory/batch');
    xhr.timeout = UPLOAD_TIMEOUT_MS;
    xhr.upload.onprogress = function (e) {
      if (e.lengthComputable) {
        progressEl.value = Math.round((e.loaded / e.total) * 100);
        setStatus('Uploading… ' + progressEl.value + '% of ' + (e.total / 1048576).toFixed(1) + ' MB');
      }
    };
    xhr.onload = function () {
      var body = null;
      try { body = JSON.parse(xhr.responseText); } catch (err) { /* not JSON */ }
      if (xhr.status >= 200 && xhr.status < 300 && body && body.batch_id) {
        done(true, body);
      } else {
        var detail = body && body.detail ? (typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)) : xhr.statusText;
        done(false, 'the backend answered HTTP ' + xhr.status + (detail ? ': ' + detail : '') + '.');
      }
    };
    xhr.onerror = function () {
      done(false, "couldn't reach the backend at " + BACKEND_URL +
        '. Is it running (with --host 0.0.0.0), and is this phone on the same Wi-Fi?');
      checkBackend();
    };
    xhr.ontimeout = function () {
      done(false, 'no answer from the backend after ' + (UPLOAD_TIMEOUT_MS / 1000) + ' s.');
    };
    xhr.send(form);
  }

  function done(ok, result) {
    uploading = false;
    progressEl.classList.add('hidden');
    if (ok) {
      uploaded.push({ batchId: result.batch_id, photos: result.photos_saved });
      slots.forEach(function (photo) { URL.revokeObjectURL(photo.url); });
      slots = VIEWS.map(function () { return null; });
      setStatus('✓ Batch ' + uploaded.length + ' uploaded: ' + result.photos_saved +
        ' photos saved as ' + result.batch_id + '. Sweep these pieces aside and snap the next handful.', 'ok');
    } else {
      setStatus('✗ Upload failed: ' + result + ' Your 5 photos are kept, tap Upload to try again.', 'error');
    }
    render();
  }

  uploadBtn.addEventListener('click', uploadBatch);

  // --- finished ---------------------------------------------------------------

  $('finished-btn').addEventListener('click', function () {
    var unsent = filled();
    if (unsent && !window.confirm(unsent + ' photo' + (unsent === 1 ? ' is' : 's are') +
        ' not uploaded yet and will stay here. Finish anyway?')) { return; }
    var n = uploaded.length;
    $('finished-summary').textContent = n + (n === 1 ? ' batch' : ' batches') + ' (' + (n * 5) +
      ' photos) uploaded this session. Identifying the pieces is the next spike.';
    var list = $('batch-list');
    list.innerHTML = '';
    uploaded.forEach(function (b, i) {
      var li = document.createElement('li');
      li.textContent = 'Batch ' + (i + 1) + ': ';
      var code = document.createElement('code');
      code.textContent = b.batchId;
      li.appendChild(code);
      li.appendChild(document.createTextNode(' (' + b.photos + ' photos)'));
      list.appendChild(li);
    });
    show('finished-view');
  });

  $('back-btn').addEventListener('click', function () { show('capture-view'); render(); });

  $('ask-build-btn').addEventListener('click', function () {
    window.alert('Build generation is not wired up yet — it comes after inventory review.');
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
