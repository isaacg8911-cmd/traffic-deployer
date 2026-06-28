/* Service worker: cache the app shell only (online-first for data and tiles).
 * Job data, map-state, and tiles are always fetched fresh from the network.
 */
var SHELL = 'td-mobile-shell-v3';
var SHELL_ASSETS = [
  '/', '/index.html', '/app.js?v=4', '/style.css',
  '/manifest.webmanifest', '/icon.svg',
  '/vendor/maplibre-gl.js', '/vendor/maplibre-gl.css'
];

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(SHELL).then(function (c) { return c.addAll(SHELL_ASSETS).catch(function () {}); }));
  self.skipWaiting();
});

self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== SHELL; }).map(function (k) { return caches.delete(k); }));
  }));
  self.clients.claim();
});

self.addEventListener('fetch', function (e) {
  var url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;            // never cache mutations
  if (url.pathname.indexOf('/api/') === 0) return;    // always live
  if (url.hostname.indexOf('tile.') === 0) return;    // tiles always live

  // Cache-first for shell assets; network fallback otherwise.
  e.respondWith(
    caches.match(e.request).then(function (hit) {
      return hit || fetch(e.request).then(function (resp) {
        return resp;
      }).catch(function () { return caches.match('/'); });
    })
  );
});
