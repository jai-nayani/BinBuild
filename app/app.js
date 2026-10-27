/* BinBuild PWA shell — capture loop state.
 * Scaffold only: photos are kept in memory, nothing is uploaded yet.
 * Confirm / Finished show a placeholder until the FastAPI backend is wired
 * up in the Oct 26-27 spike.
 */
(function () {
  'use strict';

  var photos = [];          // { id, file, url, name } in the current batch
  var confirmedBatches = 0; // batches confirmed this session
  var nextId = 1;

  var statusEl = document.getElementById('status');
  var thumbsEl = document.getElementById('thumbs');
  var batchCountEl = document.getElementById('batch-count');
  var confirmBtn = document.getElementById('confirm-btn');
  var finishedBtn = document.getElementById('finished-btn');
  var cameraInput = document.getElementById('camera-input');
  var galleryInput = document.getElementById('gallery-input');

  function setStatus(msg, isError) {
    statusEl.textContent = msg;
    statusEl.classList.toggle('error', !!isError);
  }

  function render() {
    thumbsEl.innerHTML = '';
    photos.forEach(function (photo, index) {
      var wrap = document.createElement('div');
      wrap.className = 'thumb';
      var img = document.createElement('img');
      img.src = photo.url;
      img.alt = photo.name;
      var tag = document.createElement('span');
      tag.className = 'tag';
      tag.textContent = 'photo ' + (index + 1);
      var remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = '✕';
      remove.setAttribute('aria-label', 'Remove ' + photo.name);
      remove.addEventListener('click', function () {
        URL.revokeObjectURL(photo.url);
        photos.splice(index, 1);
        setStatus('Photo removed from this batch.');
        render();
      });
      wrap.appendChild(img);
      wrap.appendChild(tag);
      wrap.appendChild(remove);
      thumbsEl.appendChild(wrap);
    });
    batchCountEl.textContent = '(' + photos.length + (photos.length === 1 ? ' photo)' : ' photos)');
    confirmBtn.disabled = photos.length === 0;
    finishedBtn.disabled = confirmedBatches === 0 && photos.length === 0;
  }

  function addFiles(fileList) {
    var added = 0;
    Array.prototype.forEach.call(fileList, function (file) {
      if (!file.type || file.type.indexOf('image/') !== 0) { return; }
      photos.push({
        id: nextId++,
        file: file,
        url: URL.createObjectURL(file),
        name: file.name || ('photo-' + nextId),
      });
      added++;
    });
    if (added > 0) {
      setStatus(added + (added === 1 ? ' photo' : ' photos') + ' added to this batch. Review, then confirm.');
    } else {
      setStatus('No image files selected.', true);
    }
    render();
  }

  cameraInput.addEventListener('change', function () {
    addFiles(cameraInput.files);
    cameraInput.value = '';
  });

  galleryInput.addEventListener('change', function () {
    addFiles(galleryInput.files);
    galleryInput.value = '';
  });

  confirmBtn.addEventListener('click', function () {
    if (photos.length === 0) { return; }
    console.log('[BinBuild] Confirm batch (placeholder):', photos.length, 'photos — backend not wired yet.');
    confirmedBatches++;
    photos.forEach(function (photo) { URL.revokeObjectURL(photo.url); });
    photos = [];
    setStatus('Batch ' + confirmedBatches + ' confirmed (placeholder — nothing sent yet). Sweep the pieces aside and snap the next handful.');
    render();
  });

  finishedBtn.addEventListener('click', function () {
    document.getElementById('capture-view').classList.add('hidden');
    document.getElementById('finished-view').classList.remove('hidden');
    document.getElementById('finished-summary').textContent =
      confirmedBatches + (confirmedBatches === 1 ? ' batch' : ' batches') +
      ' confirmed this session. The full inventory summary will appear here once the backend is wired up.';
    window.scrollTo(0, 0);
  });

  document.getElementById('back-btn').addEventListener('click', function () {
    document.getElementById('finished-view').classList.add('hidden');
    document.getElementById('capture-view').classList.remove('hidden');
  });

  document.getElementById('ask-build-btn').addEventListener('click', function () {
    console.log('[BinBuild] Ask for a build (placeholder): generation lands in the Oct 26-27 spike.');
    setStatus('Build generation is not wired up yet — it lands in the Oct 26-27 spike.');
    alert('Build generation is not wired up yet — it lands in the Oct 26-27 spike.');
  });

  render();
})();
