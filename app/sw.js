/* BinBuild service worker — keeps a copy of the app shell for offline loads.
 * Optional: the app works without it, and browsers only run it in a secure
 * context (HTTPS or localhost), never over plain HTTP on the home network.
 * Network first, so a freshly served app.js always wins over the cached one;
 * the cache is only the offline fallback. API calls are never cached. Both
 * the install and every fetch go to the server, past the browser's HTTP cache,
 * so a redeploy shows up on the next load.
 */
var CACHE_NAME = 'binbuild-v15';
var SHELL = [
  './',
  './index.html',
  './style.css',
  './app.js',
  './manifest.json',
  './icon.svg',
  './icon-192.png',
  './icon-512.png',
  './icon-maskable-512.png',
  './apple-touch-icon.png',
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      // straight from the server, never from the browser's HTTP cache (which may hold an old page)
      return cache.addAll(SHELL.map(function (url) { return new Request(url, { cache: 'reload' }); }));
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
  // Never touch API traffic — only the same-origin app shell. On the public
  // deploy the API shares the app's origin, so its paths are skipped by name.
  if (url.origin !== self.location.origin) { return; }
  if (url.pathname.indexOf('/api/') === 0 || url.pathname === '/health' ||
      url.pathname.indexOf('/docs') === 0 || url.pathname === '/openapi.json') { return; }
  var fresh = new Request(event.request.url, { cache: 'no-cache', credentials: 'same-origin' });
  event.respondWith(
    fetch(fresh).then(function (response) {
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
