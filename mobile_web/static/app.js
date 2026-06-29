/* Traffic Deployer Mobile — lean field runner.
 * Online-first PWA. Talks to the FastAPI backend; renders an online MapLibre map.
 */
(function () {
  'use strict';

  var DIRECTIONS = ['n', 'e', 's', 'w', 'ne', 'nw', 'se', 'sw'];
  var LS_KEY = 'td_mobile_job';

  var state = { jobId: null, token: null, data: null, tab: 'route', current: 0, pinMode: false, tileUrl: null, publicMode: false, shareUrl: null, reorderMode: false, busy: false };
  var map = null, mapReady = false, meMarker = null, pinMarker = null;

  var $ = function (id) { return document.getElementById(id); };

  // ----------------------------------------------------------------- helpers
  function toast(msg) {
    var t = $('toast');
    t.textContent = msg; t.classList.remove('hidden');
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { t.classList.add('hidden'); }, 2600);
  }

  function headers(extra) {
    var h = { 'x-job-token': state.token || '' };
    if (extra) for (var k in extra) h[k] = extra[k];
    return h;
  }

  function api(path, opts) {
    opts = opts || {};
    opts.headers = headers(opts.headers);
    return fetch(path, opts).then(function (r) {
      if (!r.ok) {
        return r.json().catch(function () { return { detail: 'Request failed' }; })
          .then(function (j) { throw new Error(j.detail || ('HTTP ' + r.status)); });
      }
      var ct = r.headers.get('content-type') || '';
      return ct.indexOf('application/json') >= 0 ? r.json() : r;
    });
  }

  function saveSession() {
    if (state.jobId) localStorage.setItem(LS_KEY, JSON.stringify({ jobId: state.jobId, token: state.token }));
  }
  function loadSession() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (e) { return null; }
  }
  function clearSession() { localStorage.removeItem(LS_KEY); }
  function closeRememberedJob(msg) {
    clearSession();
    state.jobId = null;
    state.token = null;
    state.data = null;
    state.reorderMode = false;
    showStart();
    if (msg) {
      $('startMsg').textContent = msg;
      $('startMsg').className = 'msg ok';
    }
  }

  // ----------------------------------------------------------------- map
  function initMap() {
    if (typeof maplibregl === 'undefined') {
      console.warn('MapLibre not loaded — map disabled; job flow still works.');
      return;
    }
    if (map) return;
    map = new maplibregl.Map({
      container: 'map',
      style: {
        version: 8,
        sources: {
          base: {
            type: 'raster',
            tiles: [state.tileUrl || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '(c) OpenStreetMap contributors'
          }
        },
        layers: [{ id: 'base', type: 'raster', source: 'base' }]
      },
      center: [-117.92, 33.79], zoom: 11, attributionControl: { compact: true }
    });
    map.on('load', function () {
      mapReady = true;
      addLayers();
      renderMap();
    });
    map.on('click', function (e) {
      if (state.pinMode) dropPinAt(e.lngLat.lat, e.lngLat.lng);
    });
  }

  function fc(features) { return { type: 'FeatureCollection', features: features || [] }; }

  function addLayers() {
    map.addSource('stops', { type: 'geojson', data: fc() });
    map.addSource('site-pts', { type: 'geojson', data: fc() });
    map.addSource('route', { type: 'geojson', data: fc() });
    map.addSource('home', { type: 'geojson', data: fc() });

    map.addLayer({
      id: 'route-line', type: 'line', source: 'route',
      paint: { 'line-color': '#1976d2', 'line-width': 4, 'line-opacity': 0.8 }
    });
    // Begin (blue) / end (red) markers — fine, crisp dots that sit on the street.
    map.addLayer({
      id: 'site-begin', type: 'circle', source: 'site-pts',
      filter: ['==', ['get', 'kind'], 'begin'],
      paint: {
        'circle-radius': [
          'interpolate', ['linear'], ['zoom'],
          11, ['case', ['boolean', ['get', 'selected'], false], 5, 3.5],
          16, ['case', ['boolean', ['get', 'selected'], false], 8, 6]
        ],
        'circle-color': '#1565c0',
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': ['case', ['boolean', ['get', 'selected'], false], 2.5, 1.5]
      }
    });
    map.addLayer({
      id: 'site-end', type: 'circle', source: 'site-pts',
      filter: ['==', ['get', 'kind'], 'end'],
      paint: {
        'circle-radius': [
          'interpolate', ['linear'], ['zoom'],
          11, ['case', ['boolean', ['get', 'selected'], false], 5, 3.5],
          16, ['case', ['boolean', ['get', 'selected'], false], 8, 6]
        ],
        'circle-color': '#c62828',
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': ['case', ['boolean', ['get', 'selected'], false], 2.5, 1.5]
      }
    });
    map.addLayer({
      id: 'stop-dot', type: 'circle', source: 'stops',
      paint: {
        'circle-radius': ['case', ['==', ['get', 'highlight'], true], 11, 7],
        'circle-color': [
          'match', ['get', 'status'],
          'installed', '#2e7d32',
          'skipped', '#c62828',
          'picked_up', '#1565c0',
          '#e65100'
        ],
        'circle-stroke-width': ['case', ['==', ['get', 'highlight'], true], 3, 1.5],
        'circle-stroke-color': '#ffffff'
      }
    });
    map.addLayer({
      id: 'stop-label', type: 'symbol', source: 'stops',
      layout: { 'text-field': ['get', 'seq'], 'text-size': 11, 'text-offset': [0, -1.1] },
      paint: { 'text-color': '#0b1320', 'text-halo-color': '#fff', 'text-halo-width': 1.5 }
    });
    map.addLayer({
      id: 'home-dot', type: 'circle', source: 'home',
      paint: { 'circle-radius': 6, 'circle-color': '#0f2744', 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' }
    });

    function onSitePointClick(e, side) {
      if (state.pinMode || state.tab !== 'route') return;
      var f = e.features && e.features[0];
      if (!f || !f.properties || !f.properties.uid) return;
      setCrossSide(f.properties.uid, side);
    }

    map.on('click', 'site-begin', function (e) { onSitePointClick(e, 'begin'); });
    map.on('click', 'site-end', function (e) { onSitePointClick(e, 'end'); });
    ['site-begin', 'site-end'].forEach(function (id) {
      map.on('mouseenter', id, function () { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', id, function () { map.getCanvas().style.cursor = ''; });
    });

    map.on('click', 'stop-dot', function (e) {
      var f = e.features && e.features[0];
      if (!f) return;
      var uid = f.properties.uid;
      var idx = (state.data.stops || []).findIndex(function (s) { return s.uid === uid; });
      if (idx >= 0) { state.current = idx; setTab('install'); }
    });
  }

  function stopAnchor(s) {
    if (s.cross_lat != null && s.cross_lon != null) return [s.cross_lat, s.cross_lon];
    if (s.anchor && s.anchor.length >= 2) return [s.anchor[0], s.anchor[1]];
    if (s.lat != null && s.lon != null) return [s.lat, s.lon];
    return null;
  }

  function setCrossSide(uid, side) {
    if (state.busy || side !== 'begin' && side !== 'end') return;
    state.busy = true;
    patchStop(uid, { cross_side: side }).then(function () {
      toast('Drive-to ' + (side === 'begin' ? 'begin (blue)' : 'end (red)') + ' set');
    }).catch(function (e) { toast(e.message); })
      .finally(function () { state.busy = false; });
  }

  function renderMap() {
    if (!mapReady || !state.data) return;
    var d = state.data, hi = d.highlight_uid;
    var siteFeats = [];
    (d.stops || []).forEach(function (s) {
      var bLat = s.begin_lat, bLon = s.begin_lon, eLat = s.end_lat, eLon = s.end_lon;
      if (bLat == null || bLon == null || eLat == null || eLon == null) return;
      var selBegin = s.cross_side === 'begin';
      var selEnd = s.cross_side === 'end';
      siteFeats.push({
        type: 'Feature',
        properties: { uid: s.uid, kind: 'begin', id: s.id, selected: selBegin },
        geometry: { type: 'Point', coordinates: [bLon, bLat] }
      });
      siteFeats.push({
        type: 'Feature',
        properties: { uid: s.uid, kind: 'end', id: s.id, selected: selEnd },
        geometry: { type: 'Point', coordinates: [eLon, eLat] }
      });
    });
    map.getSource('site-pts').setData(fc(siteFeats));

    var feats = (d.stops || []).map(function (s) {
      var a = stopAnchor(s);
      if (!a) return null;
      return {
        type: 'Feature',
        properties: { uid: s.uid, seq: String(s.seq || ''), status: s.status, highlight: s.uid === hi },
        geometry: { type: 'Point', coordinates: [a[1], a[0]] }
      };
    }).filter(Boolean);
    map.getSource('stops').setData(fc(feats));

    var poly = (d.route && d.route.polyline) || [];
    var routeFeat = poly.length >= 2
      ? [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: poly.map(function (p) { return [p[1], p[0]]; }) } }]
      : [];
    map.getSource('route').setData(fc(routeFeat));

    if (d.home) {
      map.getSource('home').setData(fc([{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [d.home[1], d.home[0]] } }]));
    }
  }

  function fitToStops() {
    if (!mapReady || !state.data) return;
    var pts = [];
    (state.data.stops || []).forEach(function (s) {
      if (s.begin_lat != null && s.begin_lon != null) pts.push([s.begin_lon, s.begin_lat]);
      if (s.end_lat != null && s.end_lon != null) pts.push([s.end_lon, s.end_lat]);
      var a = stopAnchor(s);
      if (a) pts.push([a[1], a[0]]);
    });
    if (state.data.home) pts.push([state.data.home[1], state.data.home[0]]);
    if (!pts.length) return;
    var b = pts.reduce(function (bb, p) { return bb.extend(p); }, new maplibregl.LngLatBounds(pts[0], pts[0]));
    map.fitBounds(b, { padding: 50, maxZoom: 15, duration: 500 });
  }

  function flyToStop(s) {
    if (!mapReady || !s || !s.anchor) return;
    map.flyTo({ center: [s.anchor[1], s.anchor[0]], zoom: 16, duration: 500 });
  }

  // ----------------------------------------------------------------- data sync
  function applyState(st) { state.data = st; renderAll(); }

  function refresh() {
    return api('/api/jobs/' + state.jobId + '/map-state').then(applyState);
  }

  // ----------------------------------------------------------------- rendering
  function renderAll() {
    if (!state.data) return;
    var c = state.data.counts || {};
    $('progressPill').textContent = (c.installed || 0) + '/' + (c.total || 0) + ' done';
    renderMap();
    renderRoute();
    renderInstall();
    renderPickup();
    // Audit pulls /audit + /share (+ QR image) over the network. Only refresh it
    // while the tab is open so install/grab/move/pickup don't spam the server or
    // flicker the share/QR block. setTab('audit') refreshes it on entry.
    if (state.tab === 'audit') renderAudit();
  }

  function renderRoute() {
    var ul = $('stopList'); ul.innerHTML = '';
    var route = state.data.route || {};
    var miles = route.miles || 0;
    $('routeMiles').textContent = route.stale ? 'order changed — re-trace' : (miles ? (miles.toFixed(1) + ' mi') : 'not routed');
    if (state.reorderMode) {
      $('btnRetrace').classList.toggle('active', !!route.stale);
      $('reorderHint').textContent = route.stale
        ? 'Order changed — tap Re-trace line to redraw the drive path.'
        : 'Tap ▲ / ▼ to set order. On the map, tap blue (begin) or red (end) for drive-to.';
    }
    var stops = state.data.stops || [];
    var last = stops.length - 1;
    stops.forEach(function (s, i) {
      var li = document.createElement('li');
      li.className = s.status + (i === state.current ? ' current' : '') + (state.reorderMode ? ' reordering' : '');
      var label = '<span class="grow"><b>' + (s.seq || (i + 1)) + '. Site ' + s.id + '</b>' +
        '<span class="sub">' + esc(s.street) + (s.sheet ? ' · ' + esc(s.sheet) : '') + '</span></span>';
      if (state.reorderMode) {
        li.innerHTML = label +
          '<span class="reorder-btns">' +
          '<button class="rbtn" data-dir="up"' + (i === 0 ? ' disabled' : '') + ' aria-label="Move up">▲</button>' +
          '<button class="rbtn" data-dir="down"' + (i === last ? ' disabled' : '') + ' aria-label="Move down">▼</button>' +
          '</span>';
        var ups = li.querySelectorAll('.rbtn');
        Array.prototype.forEach.call(ups, function (btn) {
          btn.onclick = function (ev) {
            ev.stopPropagation();
            if (btn.disabled) return;
            moveStop(s.uid, btn.dataset.dir);
          };
        });
      } else {
        li.innerHTML = '<span class="dot"></span>' + label;
        li.onclick = function () { state.current = i; setTab('install'); };
      }
      ul.appendChild(li);
    });
  }

  function setReorderMode(on) {
    state.reorderMode = !!on;
    $('btnReorder').textContent = state.reorderMode ? 'Done reordering' : 'Reorder stops';
    $('btnReorder').classList.toggle('active', state.reorderMode);
    $('btnRetrace').classList.toggle('hidden', !state.reorderMode);
    $('reorderHint').classList.toggle('hidden', !state.reorderMode);
    renderRoute();
  }

  function moveStop(uid, dir) {
    if (state.busy) return;
    state.busy = true;
    api('/api/jobs/' + state.jobId + '/stops/' + encodeURIComponent(uid) + '/move', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ dir: dir })
    }).then(function (res) {
      applyState(res.state);
    }).catch(function (e) { toast(e.message); })
      .finally(function () { state.busy = false; });
  }

  function retraceRoute() {
    if (state.busy) return;
    state.busy = true;
    $('btnRetrace').disabled = true; $('btnRetrace').textContent = 'Re-tracing…';
    api('/api/jobs/' + state.jobId + '/retrace', { method: 'POST' }).then(function (res) {
      applyState(res.state); fitToStops();
      toast(res.traced ? 'Line re-traced for your order' : 'Order saved (line unchanged)');
    }).catch(function (e) { toast(e.message); }).finally(function () {
      state.busy = false;
      $('btnRetrace').disabled = false; $('btnRetrace').textContent = 'Re-trace line';
    });
  }

  function renderInstall() {
    var stops = state.data.stops || [];
    if (!stops.length) { $('installTitle').textContent = 'No stops yet.'; return; }
    if (state.current >= stops.length) state.current = 0;
    var s = stops[state.current];
    var c = state.data.counts || {};
    $('installTitle').textContent = 'Stop ' + (state.current + 1) + '/' + stops.length + ' · Site ' + s.id;
    $('installSub').textContent = esc(s.street) + ' · ' + (c.installed || 0) + '/' + (c.total || 0) + ' installed';
    $('fStreet').value = s.street && s.street.indexOf('Site ') !== 0 ? s.street : '';
    $('fLanes').value = s.lanes || 2;
    $('fSerial').value = s.serial || '';
    $('fNotes').value = s.notes || '';
    fillDir(s.direction);
    if (s.field_lat != null) {
      var src = s.field_source === 'manual' ? 'Pin' : 'Phone GPS';
      $('grabInfo').textContent = src + ': ' + s.field_lat.toFixed(5) + ', ' + s.field_lon.toFixed(5);
      $('grabInfo').className = 'msg ok';
    } else {
      $('grabInfo').textContent = 'No location captured yet.';
      $('grabInfo').className = 'msg';
    }
    // Only recenter when the user is actually on the Install tab — otherwise a
    // background state refresh (reorder, pickup, autosave) would yank the map
    // away from the route overview the user is looking at.
    if (state.tab === 'install') flyToStop(s);
  }

  function fillDir(val) {
    var sel = $('fDir');
    if (!sel.options.length) {
      DIRECTIONS.forEach(function (d) { var o = document.createElement('option'); o.value = d; o.textContent = d.toUpperCase(); sel.appendChild(o); });
    }
    sel.value = (val || 'n').toLowerCase();
  }

  function renderPickup() {
    var ul = $('pickupList'); ul.innerHTML = '';
    var installed = (state.data.stops || []).filter(function (s) { return s.installed; });
    var done = installed.filter(function (s) { return s.picked_up; }).length;
    $('pickupProg').textContent = 'Pickup: ' + done + '/' + installed.length + ' done';
    installed.forEach(function (s) {
      var li = document.createElement('li');
      li.className = s.picked_up ? 'picked_up' : 'installed';
      li.innerHTML = '<span class="dot"></span><span class="grow"><b>Site ' + s.id + '</b>' +
        '<span class="sub">' + esc(s.street) + (s.picked_up ? ' · picked up' : ' · tap to pick up') + '</span></span>';
      li.onclick = function () {
        if (s.picked_up) { flyToStop(s); return; }
        patchStop(s.uid, { picked_up: true }).then(function () { toast('Picked up Site ' + s.id); });
      };
      ul.appendChild(li);
    });
  }

  function renderAudit() {
    api('/api/jobs/' + state.jobId + '/audit').then(function (a) {
      $('auditSummary').textContent = a.ok
        ? ('Ready · ' + a.count + ' sites complete')
        : (a.missing.length + ' issue(s) to fix');
      var ul = $('auditList'); ul.innerHTML = '';
      (a.missing.length ? a.missing : ['All required fields present.']).forEach(function (m) {
        var li = document.createElement('li');
        li.innerHTML = '<span class="grow"><span class="sub">' + esc(m) + '</span></span>';
        ul.appendChild(li);
      });
    }).catch(function () {});
    var q = '?token=' + encodeURIComponent(state.token);
    $('btnExportCsv').href = '/api/jobs/' + state.jobId + '/export.csv' + q;
    $('btnExportXlsx').href = '/api/jobs/' + state.jobId + '/export.xlsx' + q;
    $('jobMeta').textContent = 'Job ' + state.jobId;
    loadShare();
  }

  function loadShare() {
    api('/api/jobs/' + state.jobId + '/share').then(function (s) {
      state.shareUrl = s.share_url;
      $('shareLink').value = s.share_url;
      $('shareQr').src = '/api/jobs/' + state.jobId + '/share.svg' + '?token=' + encodeURIComponent(state.token);
      $('shareWrap').classList.remove('hidden');
    }).catch(function () { $('shareWrap').classList.add('hidden'); });
  }

  function copyShare() {
    var link = state.shareUrl || $('shareLink').value;
    if (!link) return;
    var done = function () { toast('Share link copied'); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(link).then(done, function () { selectShare(); });
    } else { selectShare(); }
  }
  function selectShare() { var el = $('shareLink'); el.removeAttribute('readonly'); el.select(); try { document.execCommand('copy'); toast('Share link copied'); } catch (e) {} el.setAttribute('readonly', 'readonly'); }

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }); }

  // ----------------------------------------------------------------- actions
  function patchStop(uid, patch) {
    return api('/api/jobs/' + state.jobId + '/stops/' + encodeURIComponent(uid), {
      method: 'PATCH', headers: { 'content-type': 'application/json' }, body: JSON.stringify(patch)
    }).then(function (res) { applyState(res.state); return res; });
  }

  function flushForm() {
    var stops = state.data.stops || [];
    if (!stops.length || state.current >= stops.length) return Promise.resolve();
    var s = stops[state.current];
    return patchStop(s.uid, {
      street: $('fStreet').value.trim(),
      direction: $('fDir').value,
      lanes: parseInt($('fLanes').value, 10) || 2,
      serial: $('fSerial').value.trim(),
      notes: $('fNotes').value.trim()
    });
  }

  function grabGps() {
    if (!navigator.geolocation) { toast('No geolocation on this device — use Drop pin.'); return; }
    $('grabInfo').textContent = 'Getting GPS…'; $('grabInfo').className = 'msg';
    navigator.geolocation.getCurrentPosition(function (pos) {
      saveGrab(pos.coords.latitude, pos.coords.longitude, 'phone_gps', pos.coords.accuracy);
    }, function (err) {
      $('grabInfo').textContent = 'GPS denied/failed — tap Drop pin and pick on the map.';
      $('grabInfo').className = 'msg err';
      enablePinMode();
    }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 });
  }

  function saveGrab(lat, lon, source, accuracy) {
    var stops = state.data.stops || [];
    var s = stops[state.current];
    api('/api/jobs/' + state.jobId + '/stops/' + encodeURIComponent(s.uid) + '/grab', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ lat: lat, lon: lon, source: source, accuracy: accuracy })
    }).then(function (res) {
      applyState(res.state);
      disablePinMode();
      toast('Location saved for Site ' + s.id);
    }).catch(function (e) { toast(e.message); });
  }

  function enablePinMode() {
    state.pinMode = true;
    $('mapHint').textContent = 'Tap the map to drop a pin for this site';
    $('mapHint').classList.remove('hidden');
  }
  function disablePinMode() {
    state.pinMode = false;
    $('mapHint').classList.add('hidden');
    if (pinMarker) { pinMarker.remove(); pinMarker = null; }
  }
  function dropPinAt(lat, lon) {
    if (pinMarker) pinMarker.remove();
    pinMarker = new maplibregl.Marker({ color: '#e65100', draggable: true })
      .setLngLat([lon, lat]).addTo(map);
    pinMarker.on('dragend', function () { var ll = pinMarker.getLngLat(); pinMarker._ll = ll; });
    pinMarker._ll = { lat: lat, lng: lon };
    $('mapHint').textContent = 'Pin set — drag to adjust, then INSTALL saves it';
    saveGrab(lat, lon, 'manual', null);
  }

  function commitInstall(installed) {
    var stops = state.data.stops || [];
    if (!stops.length) return;
    var s = stops[state.current];
    flushForm().then(function () {
      return patchStop(s.uid, installed ? { installed: true } : { skipped: true });
    }).then(function () {
      toast((installed ? 'Installed' : 'Skipped') + ' Site ' + s.id);
      var next = nextPending();
      if (next >= 0) { state.current = next; renderInstall(); }
    }).catch(function (e) { toast(e.message); });
  }

  function nextPending() {
    var stops = state.data.stops || [];
    for (var i = state.current + 1; i < stops.length; i++) if (!stops[i].installed && !stops[i].skipped) return i;
    for (var j = 0; j < stops.length; j++) if (!stops[j].installed && !stops[j].skipped) return j;
    return -1;
  }

  function buildRoute() {
    $('btnBuildRoute').disabled = true; $('btnBuildRoute').textContent = 'Building…';
    api('/api/jobs/' + state.jobId + '/route', { method: 'POST' }).then(function (res) {
      if (state.reorderMode) setReorderMode(false);
      applyState(res.state); fitToStops();
      toast(res.graph ? 'Route built on streets' : 'Route built (straight-line — no road map on server)');
    }).catch(function (e) { toast(e.message); }).finally(function () {
      $('btnBuildRoute').disabled = false; $('btnBuildRoute').textContent = 'Build route';
    });
  }

  // ----------------------------------------------------------------- tabs
  var MAP_TABS = { route: 1, install: 1, pickup: 1 };
  function setTab(tab) {
    state.tab = tab;
    ['route', 'install', 'pickup', 'audit'].forEach(function (t) {
      $(t + 'Screen').classList.toggle('hidden', t !== tab);
    });
    Array.prototype.forEach.call(document.querySelectorAll('#tabbar button'), function (b) {
      b.classList.toggle('active', b.dataset.tab === tab);
    });
    var showMap = !!MAP_TABS[tab];
    $('mapWrap').classList.toggle('hidden', !showMap);
    document.body.classList.toggle('has-map', showMap);
    if (showMap && map) setTimeout(function () { map.resize(); }, 60);
    var hint = $('mapHint');
    if (hint) {
      if (state.tab === 'route' && !state.pinMode) {
        hint.textContent = 'Blue = begin, red = end — tap to set drive-to';
        hint.classList.remove('hidden');
      } else if (!state.pinMode) {
        hint.classList.add('hidden');
      }
    }
    if (tab === 'install') renderInstall();
    if (tab === 'audit') renderAudit();
  }

  // ----------------------------------------------------------------- job load
  function openJob(jobId, token) {
    state.jobId = jobId; state.token = token; saveSession();
    return api('/api/jobs/' + jobId).then(function (res) {
      applyState(res.state);
      showApp();
      fitToStops();
    });
  }

  function showApp() {
    $('startScreen').classList.add('hidden');
    $('tabbar').classList.remove('hidden');
    setTab('route');
  }
  function showStart() {
    $('startScreen').classList.remove('hidden');
    $('tabbar').classList.add('hidden');
    $('mapWrap').classList.add('hidden');
    document.body.classList.remove('has-map');
    ['route', 'install', 'pickup', 'audit'].forEach(function (t) { $(t + 'Screen').classList.add('hidden'); });
  }

  function importJob() {
    var ex = $('impExcel').files, es = $('impEst').files;
    if (!ex.length || !es.length) { $('startMsg').textContent = 'Pick at least one Excel/CSV and one .EST'; $('startMsg').className = 'msg err'; return; }
    var fd = new FormData();
    for (var i = 0; i < ex.length; i++) fd.append('excel', ex[i]);
    for (var j = 0; j < es.length; j++) fd.append('est', es[j]);
    $('startMsg').textContent = 'Importing…'; $('startMsg').className = 'msg';
    fetch('/api/jobs/import', { method: 'POST', body: fd }).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || 'Import failed'); return j; });
    }).then(function (res) { return openJob(res.job_id, res.token); })
      .catch(function (e) { $('startMsg').textContent = e.message; $('startMsg').className = 'msg err'; });
  }

  function locateMe() {
    if (!navigator.geolocation) { toast('No geolocation on this device.'); return; }
    navigator.geolocation.getCurrentPosition(function (pos) {
      var lat = pos.coords.latitude, lon = pos.coords.longitude;
      if (meMarker) meMarker.remove();
      meMarker = new maplibregl.Marker({ color: '#2196f3' }).setLngLat([lon, lat]).addTo(map);
      map.flyTo({ center: [lon, lat], zoom: 15 });
    }, function () { toast('Could not get your location.'); }, { enableHighAccuracy: true, timeout: 10000 });
  }

  // ----------------------------------------------------------------- wire up
  function wire() {
    $('btnImport').onclick = importJob;
    $('btnOpen').onclick = function () { openJob($('openId').value.trim(), $('openToken').value.trim()).catch(function (e) { $('startMsg').textContent = e.message; $('startMsg').className = 'msg err'; }); };
    $('btnBuildRoute').onclick = buildRoute;
    $('btnReorder').onclick = function () { setReorderMode(!state.reorderMode); };
    $('btnRetrace').onclick = retraceRoute;
    $('btnGrab').onclick = grabGps;
    $('btnDropPin').onclick = function () { if (state.pinMode) disablePinMode(); else enablePinMode(); };
    $('btnInstall').onclick = function () { commitInstall(true); };
    $('btnSkip').onclick = function () { commitInstall(false); };
    $('btnPrev').onclick = function () { if (state.current > 0) { flushForm(); state.current--; renderInstall(); } };
    $('btnNext').onclick = function () { var st = state.data.stops || []; if (state.current < st.length - 1) { flushForm(); state.current++; renderInstall(); } };
    $('btnLocate').onclick = locateMe;
    $('btnCloseJob').onclick = function () { closeRememberedJob('Remembered job cleared on this phone. Use a share link to reopen a job.'); };
    $('btnClearSavedJob').onclick = function () { closeRememberedJob('Remembered job cleared on this phone.'); };
    $('btnCopyShare').onclick = copyShare;
    Array.prototype.forEach.call(document.querySelectorAll('#tabbar button'), function (b) {
      b.onclick = function () { if (state.tab === 'install') flushForm(); setTab(b.dataset.tab); };
    });
    // Autosave install form fields on change (debounced).
    ['fStreet', 'fDir', 'fLanes', 'fSerial', 'fNotes'].forEach(function (id) {
      var el = $(id);
      el.addEventListener('change', function () { flushForm(); });
    });
  }

  function shareTarget() {
    // Share link form: /join/<job_id>?token=<secret>
    var m = location.pathname.match(/\/join\/([A-Za-z0-9_-]+)/);
    if (!m) return null;
    var token = new URLSearchParams(location.search).get('token') || '';
    return { jobId: m[1], token: token };
  }

  function applyPublicMode(isPublic, canCreate) {
    state.publicMode = !!isPublic;
    state.canCreate = !!canCreate;
    if (isPublic) document.body.classList.add('public-mode');
    // Open-uploads deploy: public tunnel but the phone may still create/import.
    if (isPublic && canCreate) document.body.classList.add('public-open');
  }

  function finishBoot() {
    var share = shareTarget();
    if (share && share.jobId) {
      $('startMsg').textContent = 'Opening shared job…';
      openJob(share.jobId, share.token).then(function () {
        // Clean the URL so the token is not left in the address bar / history.
        try { history.replaceState({}, '', '/'); } catch (e) {}
      }).catch(function (e) {
        clearSession(); showStart();
        $('startMsg').textContent = e.message || 'This share link is invalid or expired.';
        $('startMsg').className = 'msg err';
      });
    } else if (state.publicMode && !state.canCreate) {
      // Share-only crew phone (no open uploads): links are explicit, so the bare
      // public URL must not surprise a shared phone by reopening an old job.
      clearSession();
      showStart();
    } else {
      // Local mode, OR an open-uploads operator phone on a public host. This is
      // the operator's own device: reopen the remembered job so switching apps,
      // locking the screen, or a reload during a shift never loses the day's
      // work. All edits already persist to the server in real time, so reopening
      // simply re-fetches the live job state.
      var sess = loadSession();
      if (sess && sess.jobId) {
        openJob(sess.jobId, sess.token).catch(function () { clearSession(); showStart(); });
      } else {
        showStart();
      }
    }
  }

  function boot() {
    wire();
    api('/api/config').then(function (cfg) {
      state.tileUrl = cfg.tile_url; applyPublicMode(cfg.public_mode, cfg.can_create); initMap(); finishBoot();
    }).catch(function () { initMap(); finishBoot(); });
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(function () {});
    }
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
