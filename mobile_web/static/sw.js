/* Service worker: app shell is network-first. Map tiles the phone already
 * loaded stay on the phone so Drop pin still has a map if the signal drops.
 * Job data is never cached here.
 */
var SHELL = 'td-mobile-shell-v8';
var TILES = 'td-mobile-tiles-v1';
var TILE_CAP = 500;
var SHELL_ASSETS = [
  '/style.css', '/manifest.webmanifest', '/icon.svg',
  '/vendor/maplibre-gl.js', '/vendor/maplibre-gl.css'
];

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(SHELL).then(function (c) { return c.addAll(SHELL_ASSETS).catch(function () {}); }));
  self.skipWaiting();
});

self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== SHELL && k !== TILES; }).map(function (k) { return caches.delete(k); }));
  }));
  self.clients.claim();
});

function isOsmTile(url) {
  return url.hostname === 'tile.openstreetmap.org';
}

function trimTiles(cache) {
  cache.keys().then(function (keys) {
    if (keys.length <= TILE_CAP) return;
    var extra = keys.length - TILE_CAP;
    return Promise.all(keys.slice(0, extra).map(function (k) { return cache.delete(k); }));
  }).catch(function () {});
}

function isAppCode(url) {
  // The HTML shell and the app logic must always come from the network so a
  // shipped fix reaches phones immediately (stale app.js caused old jobs to
  // auto-reopen). Everything else (css, fonts, map lib) is safe to cache.
  return url.pathname === '/'
    || url.pathname === '/index.html'
    || url.pathname.indexOf('/join/') === 0
    || url.pathname === '/app.js'
    || url.pathname === '/local.js';
}

self.addEventListener('fetch', function (e) {
  var url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;            // never cache mutations
  if (url.pathname.indexOf('/api/') === 0) return;    // always live
  if (isOsmTile(url)) {
    e.respondWith(caches.open(TILES).then(function (cache) {
      return cache.match(e.request).then(function (hit) {
        var net = fetch(e.request).then(function (resp) {
          if (resp && (resp.ok || resp.type === 'opaque')) {
            cache.put(e.request, resp.clone()).catch(function () {});
            trimTiles(cache);
          }
          return resp;
        }).catch(function () { return hit || new Response('', { status: 504 }); });
        return hit || net;
      });
    }));
    return;
  }

  if (isAppCode(url)) {
    // Network-first for app shell + logic; fall back to cache only when offline.
    e.respondWith(
      fetch(e.request).then(function (resp) {
        var copy = resp.clone();
        caches.open(SHELL).then(function (c) { c.put(e.request, copy).catch(function () {}); });
        return resp;
      }).catch(function () {
        return caches.match(e.request).then(function (hit) { return hit || caches.match('/index.html'); });
      })
    );
    return;
  }

  // Cache-first for static assets; network fallback otherwise.
  e.respondWith(
    caches.match(e.request).then(function (hit) {
      return hit || fetch(e.request).then(function (resp) {
        return resp;
      }).catch(function () { return caches.match('/index.html'); });
    })
  );
});
