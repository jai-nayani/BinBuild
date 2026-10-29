/* BinBuild service worker — keeps a copy of the app shell for offline loads.
 * Optional: the app works without it, and browsers only run it in a secure
 * context (HTTPS or localhost), never over plain HTTP on the home network.
 * Network first, so a freshly served app.js always wins over the cached one;
 * the cache is only the offline fallback. API calls are never cached.
 */
var CACHE_NAME = 'binbuild-v7';
var SHELL = [
  './',
  './index.html',
  './app.js',
  './manifest.json',
  './icon.svg',
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(SHELL);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (key) {
        return key !== CACHE_NAME;
      }).map(function (key) {
        return caches.delete(key);
      }));
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function (event) {
  if (event.request.method !== 'GET') { return; }
  var url = new URL(event.request.url);
  // Never touch API traffic — only the same-origin app shell.
  if (url.origin !== self.location.origin) { return; }
  event.respondWith(
    fetch(event.request).then(function (response) {
      if (response.ok) {
        var copy = response.clone();
        caches.open(CACHE_NAME).then(function (cache) { cache.put(event.request, copy); });
      }
      return response;
    }).catch(function () {
      return caches.match(event.request);
    })
  );
});
