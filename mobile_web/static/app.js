/* Traffic Deployer phone — laptop workflow on a mobile screen.
 * Online when the server is up; otherwise saves on this phone and as a .tdjob.json file.
 */
(function () {
  'use strict';

  var DIRECTIONS = ['n', 'e', 's', 'w', 'ne', 'nw', 'se', 'sw'];
  var LS_KEY = 'td_mobile_job';
  var LS_HOME = 'td_mobile_home';
  var TABS = ['setup', 'route', 'install', 'pickup', 'audit'];
  var MAP_TABS = { route: 1, install: 1, pickup: 1 };
  var CA = { minLat: 32.0, maxLat: 42.5, minLon: -125.0, maxLon: -114.0 };
  var L = window.TDLocal;

  var state = {
    jobId: null, token: null, data: null, job: null,
    tab: 'route', current: 0, pinMode: false, tileUrl: null,
    publicMode: false, canCreate: true, shareUrl: null,
    reorderMode: false, busy: false, localOnly: false, pending: [],
    driving: false, geoWatch: null, myLat: null, myLon: null, myAcc: null,
    homeLat: null, homeLon: null, homeLabel: '',
    phase: 'wait', formUid: null, filledUid: null, grabLock: null, formSnapshot: null,
    pendingFix: null, choices: [], matchNote: '', grabbing: false, matching: false
  };
  var map = null, mapReady = false, meMarker = null, pinMarker = null;

  var $ = function (id) { return document.getElementById(id); };

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

  function isLocalId(id) { return !id || String(id).indexOf('local-') === 0; }

  function api(path, opts) {
    opts = opts || {};
    opts.headers = headers(opts.headers);
    return fetch(path, opts).then(function (r) {
      if (!r.ok) {
        return r.json().catch(function () { return { detail: 'Request failed' }; })
          .then(function (j) {
            var err = new Error(j.detail || ('HTTP ' + r.status));
            err.status = r.status;
            throw err;
          });
      }
      var ct = r.headers.get('content-type') || '';
      return ct.indexOf('application/json') >= 0 ? r.json() : r;
    });
  }

  function markLocal(reason) {
    state.localOnly = true;
    updateSaveUi(reason || 'Saved on this phone — server unreachable.');
  }

  function markOnline() {
    state.localOnly = false;
    updateSaveUi('');
  }

  function updateSaveUi(banner) {
    var pill = $('savePill');
    var bar = $('saveBanner');
    if (!state.jobId) {
      pill.textContent = '—';
      pill.className = 'pill save-off';
      bar.classList.add('hidden');
      return;
    }
    if (state.localOnly || isLocalId(state.jobId)) {
      pill.textContent = 'This phone';
      pill.className = 'pill save-local';
      $('saveBannerText').textContent = banner ||
        'Saved on this phone. Download a job file so you can pick up later.';
      bar.classList.remove('hidden');
    } else {
      pill.textContent = 'Saved';
      pill.className = 'pill save-ok';
      bar.classList.add('hidden');
    }
  }

  function persist() {
    if (!state.job) return Promise.resolve();
    var rec = {
      jobId: state.jobId,
      token: state.token || '',
      localOnly: state.localOnly || isLocalId(state.jobId),
      job: state.job,
      pending: state.pending || [],
      updated: Date.now()
    };
    saveSession();
    return L.saveSnapshot(rec);
  }

  function applyJob(job, mapState) {
    state.job = job;
    state.data = mapState || L.buildMapState(job);
    renderAll();
    persist();
  }

  function saveSession() {
    if (state.jobId) {
      try {
        localStorage.setItem(LS_KEY, JSON.stringify({
          jobId: state.jobId, token: state.token || '', localOnly: state.localOnly
        }));
      } catch (e) {}
    }
  }
  function loadSession() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch (e) { return null; }
  }
  function clearSession() { try { localStorage.removeItem(LS_KEY); } catch (e) {} }

  function downloadJobFile() {
    if (!state.job) { toast('Nothing to download yet.'); return; }
    var pack = L.pack(state.job);
    var name = 'TD_job_' + (state.jobId || 'local') + '.tdjob.json';
    L.downloadNamed(name, JSON.stringify(pack, null, 2), 'application/json');
    toast('Job file saved — re-upload it to pick up later');
  }

  function downloadCsv() {
    if (!state.job) return;
    L.downloadNamed('IG_TFC_' + (state.jobId || 'local') + '.csv', L.toCsv(state.job.stops), 'text/csv');
  }

  // ----------------------------------------------------------------- map
  function initMap() {
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
    map.addSource('route', { type: 'geojson', data: fc() });
    map.addSource('home', { type: 'geojson', data: fc() });

    map.addLayer({
      id: 'route-line', type: 'line', source: 'route',
      paint: { 'line-color': '#1976d2', 'line-width': 4, 'line-opacity': 0.8 }
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
      paint: { 'circle-radius': 6, 'circle-color': '#9c27b0', 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' }
    });

    map.on('click', 'stop-dot', function (e) {
      if (state.pinMode || state.grabbing || state.matching) return;
      var f = e.features && e.features[0];
      if (!f) return;
      var uid = f.properties.uid;
      var idx = (state.data.stops || []).findIndex(function (s) { return s.uid === uid; });
      if (idx >= 0) openSiteForm(idx, false);
    });
  }

  function renderMap() {
    if (!mapReady || !state.data) return;
    var d = state.data;
    var hi = null;
    if (state.phase === 'form' && state.formUid) hi = state.formUid;
    else if (state.phase === 'choose' && state.choices && state.choices[0]) hi = state.choices[0].uid;
    var feats = (d.stops || []).map(function (s) {
      var a = s.anchor || (s.lat != null ? [s.lat, s.lon] : null);
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
    (state.data.stops || []).forEach(function (s) { if (s.anchor) pts.push([s.anchor[1], s.anchor[0]]); });
    if (state.data.home) pts.push([state.data.home[1], state.data.home[0]]);
    if (!pts.length) return;
    var b = pts.reduce(function (bb, p) { return bb.extend(p); }, new maplibregl.LngLatBounds(pts[0], pts[0]));
    map.fitBounds(b, { padding: 50, maxZoom: 15, duration: 500 });
  }

  function flyToStop(s) {
    if (!mapReady || !s || !s.anchor) return;
    map.flyTo({ center: [s.anchor[1], s.anchor[0]], zoom: 16, duration: 500 });
  }

  // ----------------------------------------------------------------- online / local mutations
  function refreshFromServer() {
    if (!state.jobId || isLocalId(state.jobId) || state.localOnly) {
      if (state.job) applyJob(state.job);
      return Promise.resolve();
    }
    return api('/api/jobs/' + state.jobId + '/tdjob').then(function (pack) {
      var data = L.unpack(pack);
      data.id = state.jobId;
      applyJob(data);
      markOnline();
    }).catch(function () {
      return api('/api/jobs/' + state.jobId + '/map-state').then(function (st) {
        var job = L.jobFromMapState(st, { jobId: state.jobId });
        applyJob(job, st);
      });
    });
  }

  function withServer(fn, localFn) {
    if (state.localOnly || isLocalId(state.jobId) || !state.token) {
      return Promise.resolve(localFn());
    }
    return fn().catch(function (e) {
      markLocal(e.message || 'Saved on this phone — server unreachable.');
      return localFn();
    });
  }

  function queue(op) {
    state.pending = state.pending || [];
    state.pending.push(op);
  }

  function patchStop(uid, patch) {
    return withServer(function () {
      return api('/api/jobs/' + state.jobId + '/stops/' + encodeURIComponent(uid), {
        method: 'PATCH', headers: { 'content-type': 'application/json' }, body: JSON.stringify(patch)
      }).then(function (res) {
        var raw = L.findStop(state.job, uid);
        if (raw && res.stop) L.mergePublicStop(raw, res.stop);
        else if (raw) L.applyStopPatch(raw, patch);
        applyJob(state.job, res.state);
        return res;
      });
    }, function () {
      var raw = L.findStop(state.job, uid);
      if (raw) L.applyStopPatch(raw, patch);
      queue({ op: 'patch', uid: uid, body: patch });
      applyJob(state.job);
      return { state: state.data };
    });
  }

  function grabLocal(uid, lat, lon, source, accuracy) {
    var raw = L.findStop(state.job, uid);
    if (raw) L.applyGrab(raw, lat, lon, source, accuracy);
    queue({ op: 'grab', uid: uid, body: { lat: lat, lon: lon, source: source, accuracy: accuracy } });
    applyJob(state.job);
  }

  function saveGrab(uid, lat, lon, source, accuracy) {
    if (!(lat > CA.minLat && lat < CA.maxLat && lon > CA.minLon && lon < CA.maxLon)) {
      toast('Location looks outside California.');
      return Promise.resolve(false);
    }
    var raw = L.findStop(state.job, uid);
    if (!raw) return Promise.resolve(false);
    return withServer(function () {
      return api('/api/jobs/' + state.jobId + '/stops/' + encodeURIComponent(uid) + '/grab', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ lat: lat, lon: lon, source: source, accuracy: accuracy })
      }).then(function (res) {
        var stop = L.findStop(state.job, uid);
        if (stop && res.stop) L.mergePublicStop(stop, res.stop);
        else grabLocal(uid, lat, lon, source, accuracy);
        applyJob(state.job, res.state);
        disablePinMode();
        return true;
      });
    }, function () {
      grabLocal(uid, lat, lon, source, accuracy);
      disablePinMode();
      return true;
    }).then(function (ok) { return ok !== false; }).catch(function () { return false; });
  }

  function clearGrabRemote(uid) {
    return withServer(function () {
      return api('/api/jobs/' + state.jobId + '/stops/' + encodeURIComponent(uid) + '/grab', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ clear: true })
      }).then(function (res) {
        var stop = L.findStop(state.job, uid);
        if (stop && res.stop) L.mergePublicStop(stop, res.stop);
        else if (stop) L.clearGrab(stop);
        applyJob(state.job, res.state);
      });
    }, function () {
      var stop = L.findStop(state.job, uid);
      if (stop) L.clearGrab(stop);
      queue({ op: 'grab', uid: uid, body: { clear: true } });
      applyJob(state.job);
    });
  }

  function moveStop(uid, dir) {
    if (state.busy) return;
    state.busy = true;
    withServer(function () {
      return api('/api/jobs/' + state.jobId + '/stops/' + encodeURIComponent(uid) + '/move', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ dir: dir })
      }).then(function (res) {
        L.moveStop(state.job, uid, dir);
        applyJob(state.job, res.state);
      });
    }, function () {
      L.moveStop(state.job, uid, dir);
      queue({ op: 'move', uid: uid, dir: dir });
      applyJob(state.job);
    }).catch(function (e) { toast(e.message); })
      .finally(function () { state.busy = false; });
  }

  function pushToServer() {
    if (!state.job) return;
    var pack = L.pack(state.job);
    $('setupMsg').textContent = 'Saving to server…';
    fetch('/api/jobs/restore', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(pack)
    }).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || 'Save failed'); return j; });
    }).then(function (res) {
      state.jobId = res.job_id;
      state.token = res.token;
      state.pending = [];
      var data = L.unpack(pack);
      data.id = res.job_id;
      applyJob(data, res.state);
      markOnline();
      toast('Saved on server');
      $('setupMsg').textContent = 'Saved on server · job ' + res.job_id;
      $('setupMsg').className = 'msg ok';
    }).catch(function (e) {
      markLocal(e.message);
      $('setupMsg').textContent = e.message + ' — job file still on this phone.';
      $('setupMsg').className = 'msg err';
    });
  }

  // ----------------------------------------------------------------- rendering
  function renderAll() {
    if (!state.data) return;
    var c = state.data.counts || {};
    $('progressPill').textContent = (c.installed || 0) + '/' + (c.total || 0) + ' done';
    renderMap();
    renderSetup();
    renderRoute();
    renderInstall();
    renderPickup();
    renderAudit();
    renderDriveBanner();
    updateSaveUi();
  }

  function renderSetup() {
    if (!state.job) return;
    var c = state.data.counts || {};
    var miles = (state.data.route && state.data.route.miles) || 0;
    $('setupMeta').textContent = (state.job.label || 'Field job') + ' · ' + (c.total || 0) + ' sites';
    var files = (state.job.active_files || []).join(', ') || 'Imported job';
    $('setupFiles').textContent = files + (miles ? (' · ' + miles.toFixed(1) + ' mi') : ' · not routed yet');
    var filesDone = (state.job.stops || []).length > 0;
    var routed = miles > 0.05;
    var installing = (c.installed || 0) + (c.skipped || 0) > 0;
    var auditReady = installing && (c.pending || 0) === 0;
    var steps = {
      files: filesDone, route: routed, drive: state.driving,
      install: installing, audit: auditReady
    };
    var current = 'audit';
    ['files', 'route', 'drive', 'install', 'audit'].some(function (id) {
      if (!steps[id]) { current = id; return true; }
      return false;
    });
    Array.prototype.forEach.call(document.querySelectorAll('#jobWorkflow li'), function (li) {
      var id = li.getAttribute('data-step');
      li.className = steps[id] ? 'done' : (id === current ? 'current' : '');
    });
  }

  function renderRoute() {
    var ul = $('stopList'); ul.innerHTML = '';
    var route = (state.data && state.data.route) || {};
    var miles = route.miles || 0;
    $('routeMiles').textContent = route.stale ? 'order changed — re-trace' : (miles ? (miles.toFixed(1) + ' mi') : 'not routed');
    if (state.reorderMode) {
      $('btnRetrace').classList.toggle('active', !!route.stale);
      $('reorderHint').textContent = route.stale
        ? 'Order changed — tap Re-trace line to redraw the drive path.'
        : 'Tap ▲ / ▼ to set your own order, then Re-trace line.';
    }
    var stops = (state.data && state.data.stops) || [];
    var last = stops.length - 1;
    stops.forEach(function (s, i) {
      var li = document.createElement('li');
      li.className = s.status + (state.phase === 'form' && i === state.current ? ' current' : '') + (state.reorderMode ? ' reordering' : '');
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
        li.onclick = function () { openSiteForm(i, false); };
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

  function retraceRoute() {
    if (state.busy) return;
    if (state.localOnly || isLocalId(state.jobId)) {
      toast('Connect to the server to re-trace the street line.');
      return;
    }
    state.busy = true;
    $('btnRetrace').disabled = true; $('btnRetrace').textContent = 'Re-tracing…';
    api('/api/jobs/' + state.jobId + '/retrace', { method: 'POST' }).then(function (res) {
      if (res.state && res.state.route) state.job.route = res.state.route;
      applyJob(state.job, res.state); fitToStops();
      toast(res.traced ? 'Line re-traced for your order' : 'Order saved (line unchanged)');
    }).catch(function (e) { toast(e.message); markLocal(e.message); }).finally(function () {
      state.busy = false;
      $('btnRetrace').disabled = false; $('btnRetrace').textContent = 'Re-trace line';
    });
  }

  function formatM(m) {
    if (m == null || !isFinite(m)) return '';
    if (m < 300) return Math.round(m * 3.28084) + ' ft';
    return (m / 1609.344).toFixed(1) + ' mi';
  }

  function rawStop(uid) {
    return L.findStop(state.job, uid);
  }

  function takeSnapshot(uid) {
    var s = rawStop(uid);
    if (!s) return null;
    return {
      street: s.street || '', direction: s.direction || '', serial: s.serial || '',
      notes: s.notes || '', lanes: s.lanes || 2
    };
  }

  function enterWait() {
    state.phase = 'wait';
    state.formUid = null;
    state.grabLock = null;
    state.formSnapshot = null;
    state.filledUid = null;
    state.choices = [];
    state.pendingFix = null;
    disablePinMode();
    renderInstall();
    renderMap();
  }

  function openSiteForm(idx, locked) {
    var stops = (state.data && state.data.stops) || [];
    if (idx < 0 || idx >= stops.length) return;
    var s = stops[idx];
    state.phase = 'form';
    state.current = idx;
    state.formUid = s.uid;
    state.grabLock = locked ? s.uid : null;
    state.formSnapshot = takeSnapshot(s.uid);
    state.choices = [];
    disablePinMode();
    if (state.tab !== 'install') setTab('install');
    else renderInstall();
    flyToStop(s);
    renderMap();
  }

  function renderInstall() {
    var stops = (state.data && state.data.stops) || [];
    var c = (state.data && state.data.counts) || {};
    var waiting = state.phase !== 'form';
    var grabWait = $('grabWait');
    var siteForm = $('siteForm');
    if (grabWait) grabWait.classList.toggle('hidden', !waiting);
    if (siteForm) siteForm.classList.toggle('hidden', waiting);
    var done = (c.installed || 0) + '/' + (c.total || 0);
    if (waiting) {
      $('installWaitTitle').textContent = stops.length ? ('At the site · ' + done + ' installed') : 'No sites yet';
      $('installWaitSub').textContent = state.phase === 'choose'
        ? 'Tap the site you are standing at.'
        : 'Grab GPS. The app links it to the site you are standing at.';
      $('grabInfo').textContent = state.matchNote || (stops.length ? 'Waiting for the next GPS grab.' : '');
      $('grabInfo').className = state.phase === 'choose' ? 'msg' : (state.matchNote ? 'msg err' : 'msg');
      renderChoices();
      return;
    }
    if (!stops.length || state.current >= stops.length) {
      $('installTitle').textContent = 'No site.';
      return;
    }
    var s = stops[state.current];
    var focus = document.activeElement;
    var keep = focus && siteForm && siteForm.contains(focus);
    $('installTitle').textContent = 'Site ' + s.id;
    $('installSub').textContent = esc(s.street) + ' · ' + done + ' installed';
    $('btnWrong').textContent = state.grabLock === s.uid ? 'Wrong site' : 'Cancel';
    if (s.field_lat != null) {
      var src = s.field_source === 'manual' ? 'Pin' : 'GPS';
      $('grabSaved').textContent = src + ' saved · ' + s.field_lat.toFixed(5) + ', ' + s.field_lon.toFixed(5);
      $('grabSaved').className = 'msg ok';
    } else {
      $('grabSaved').textContent = 'No GPS on this site yet.';
      $('grabSaved').className = 'msg';
    }
    if (keep || state.filledUid === s.uid) return;
    state.filledUid = s.uid;
    $('fStreet').value = s.street && s.street.indexOf('Site ') !== 0 ? s.street : '';
    $('fLanes').value = s.lanes || 2;
    $('fSerial').value = s.serial || '';
    $('fNotes').value = s.notes || '';
    fillDir(s.direction);
  }

  function renderChoices() {
    var ul = $('matchChoices');
    if (!ul) return;
    ul.innerHTML = '';
    var show = state.phase === 'choose' && state.choices && state.choices.length;
    ul.classList.toggle('hidden', !show);
    if (!show) return;
    state.choices.forEach(function (opt) {
      var li = document.createElement('li');
      li.innerHTML = '<span class="grow"><b>Site ' + esc(opt.id) + '</b>' +
        '<span class="sub">' + esc(opt.street || '') + ' · ' + formatM(opt.distance_m) + '</span></span>';
      li.onclick = function () { commitMatch(opt.uid); };
      ul.appendChild(li);
    });
  }

  function fillDir(val) {
    var sel = $('fDir');
    if (!sel.options.length) {
      var blank = document.createElement('option');
      blank.value = ''; blank.textContent = '—';
      sel.appendChild(blank);
      DIRECTIONS.forEach(function (d) {
        var o = document.createElement('option'); o.value = d; o.textContent = d.toUpperCase(); sel.appendChild(o);
      });
    }
    var v = String(val || '').toLowerCase();
    if (v && !Array.prototype.some.call(sel.options, function (o) { return o.value === v; })) {
      var extra = document.createElement('option');
      extra.value = v; extra.textContent = v.toUpperCase();
      sel.appendChild(extra);
    }
    sel.value = v && Array.prototype.some.call(sel.options, function (o) { return o.value === v; }) ? v : '';
  }

  function renderPickup() {
    var ul = $('pickupList'); ul.innerHTML = '';
    var installed = ((state.data && state.data.stops) || []).filter(function (s) { return s.installed; });
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
    var a;
    try { a = L.audit((state.job && state.job.stops) || []); }
    catch (e) { a = { ok: true, missing: [], count: 0 }; }
    $('auditSummary').textContent = a.ok
      ? ('Ready · ' + a.count + ' sites complete')
      : (a.missing.length + ' issue(s) to fix');
    var ul = $('auditList'); ul.innerHTML = '';
    (a.missing.length ? a.missing : ['All required fields present.']).forEach(function (m) {
      var li = document.createElement('li');
      li.innerHTML = '<span class="grow"><span class="sub">' + esc(m) + '</span></span>';
      ul.appendChild(li);
    });
    var q = '?token=' + encodeURIComponent(state.token || '');
    var xls = $('btnExportXlsx');
    if (state.token && !isLocalId(state.jobId) && !state.localOnly) {
      xls.href = '/api/jobs/' + state.jobId + '/export.xlsx' + q;
      xls.classList.remove('hidden');
    } else {
      xls.href = '#';
      xls.onclick = function (ev) { ev.preventDefault(); toast('Excel export needs the server. CSV works offline.'); };
    }
    $('jobMeta').textContent = (state.localOnly || isLocalId(state.jobId))
      ? ('On this phone · ' + (state.jobId || ''))
      : ('Job ' + state.jobId);
    if (state.token && !isLocalId(state.jobId) && !state.localOnly) loadShare();
    else $('shareWrap').classList.add('hidden');
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

  function flushForm() {
    if (state.phase !== 'form' || !state.formUid) return Promise.resolve();
    var street = $('fStreet').value.trim();
    var patch = {
      lanes: parseInt($('fLanes').value, 10) || 2,
      serial: $('fSerial').value.trim(),
      notes: $('fNotes').value.trim()
    };
    if (street) patch.street = street;
    if ($('fDir').value) patch.direction = $('fDir').value;
    return patchStop(state.formUid, patch);
  }

  function matchMessage(match, accuracy) {
    var near = match.nearest;
    var who = near ? ('Site ' + near.id + (near.street ? ' · ' + near.street : '')) : 'a site';
    var dist = near ? formatM(near.distance_m) : '';
    if (match.status === 'done') {
      var word = near && near.skipped && !near.installed ? 'was skipped' : 'is already installed';
      return who + ' ' + word + (dist ? ' (' + dist + ')' : '') + '. Drive to the next site and grab again.';
    }
    if (match.status === 'none') {
      if (!near) return 'No sites to match.';
      if (match.reason === 'empty') return 'All sites are installed or skipped.';
      return 'No unfinished site close enough. Nearest is ' + who + (dist ? ', ' + dist + ' away' : '') + '.';
    }
    if (match.reason === 'ambiguous') return 'Two sites are close. Tap the one you are at.';
    if (match.reason === 'fuzzy') {
      var acc = (accuracy != null && isFinite(accuracy)) ? Math.round(accuracy * 3.28084) + ' ft' : '';
      return 'GPS is fuzzy' + (acc ? ' (±' + acc + ')' : '') + '. Tap the site you are at.';
    }
    if (match.reason === 'already_near') {
      var done = match.nearby_done;
      var doneTxt = done ? ('Site ' + done.id + ' nearby is already done. ') : '';
      return doneTxt + 'Tap the unfinished site you are at.';
    }
    return 'Nearest is ' + who + (dist ? ', ' + dist : '') + '. Tap it to use that site.';
  }

  function grabGps() {
    if (state.grabbing || state.matching || state.phase === 'form') return;
    if (!navigator.geolocation) {
      toast('No geolocation on this device — use Drop pin.');
      enablePinMode();
      return;
    }
    state.grabbing = true;
    $('btnGrab').disabled = true;
    $('grabInfo').textContent = 'Getting GPS…';
    $('grabInfo').className = 'msg';
    navigator.geolocation.getCurrentPosition(function (pos) {
      state.grabbing = false;
      $('btnGrab').disabled = false;
      state.myLat = pos.coords.latitude;
      state.myLon = pos.coords.longitude;
      state.myAcc = pos.coords.accuracy;
      resolveFix(pos.coords.latitude, pos.coords.longitude, 'phone_gps', pos.coords.accuracy);
    }, function () {
      state.grabbing = false;
      $('btnGrab').disabled = false;
      state.matchNote = 'GPS denied or failed. Tap Drop pin and pick the spot on the map.';
      renderInstall();
      enablePinMode();
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
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
    pinMarker.on('dragend', function () {
      var ll = pinMarker.getLngLat();
      if (state.phase === 'form' && state.formUid) {
        saveGrab(state.formUid, ll.lat, ll.lng, 'manual', null);
      } else {
        resolveFix(ll.lat, ll.lng, 'manual', null);
      }
    });
    $('mapHint').textContent = 'Pin set — drag to adjust';
    resolveFix(lat, lon, 'manual', null);
  }

  function resolveFix(lat, lon, source, accuracy) {
    if (!(lat > CA.minLat && lat < CA.maxLat && lon > CA.minLon && lon < CA.maxLon)) {
      toast('Location looks outside California.');
      return;
    }
    var match = L.matchSite((state.job && state.job.stops) || [], lat, lon, accuracy);
    state.pendingFix = { lat: lat, lon: lon, source: source, accuracy: accuracy };
    state.choices = match.status === 'choose' ? (match.options || []) : [];
    state.matchNote = match.status === 'bind' ? '' : matchMessage(match, accuracy);
    if (match.status === 'bind') {
      commitMatch(match.uid);
      return;
    }
    state.phase = match.status === 'choose' ? 'choose' : 'wait';
    if (state.tab !== 'install') setTab('install');
    else renderInstall();
    renderMap();
    var focusUid = (match.nearest && match.nearest.uid) || null;
    if (focusUid && match.status !== 'done') {
      var hit = ((state.data && state.data.stops) || []).filter(function (s) { return s.uid === focusUid; })[0];
      if (hit) flyToStop(hit);
    }
  }

  function commitMatch(uid) {
    if (state.matching || !state.pendingFix || !uid) return;
    var stops = (state.data && state.data.stops) || [];
    var idx = -1;
    for (var i = 0; i < stops.length; i++) if (stops[i].uid === uid) { idx = i; break; }
    if (idx < 0) return;
    var fix = state.pendingFix;
    state.matching = true;
    state.matchNote = '';
    saveGrab(uid, fix.lat, fix.lon, fix.source, fix.accuracy).then(function (ok) {
      if (!ok) {
        enterWait();
        toast('Could not save that GPS. Grab again.');
        return;
      }
      openSiteForm(idx, true);
    }).catch(function (e) {
      enterWait();
      toast(e.message || 'Could not save that GPS.');
    }).finally(function () { state.matching = false; });
  }

  function commitInstall(installed) {
    if (state.phase !== 'form' || !state.formUid || state.busy) return;
    if (installed && (!$('fSerial').value.trim() || !$('fDir').value)) {
      toast('Enter direction and serial number, then Install.');
      return;
    }
    var uid = state.formUid;
    var s = rawStop(uid);
    var label = s ? s.id : '';
    state.busy = true;
    flushForm().then(function () {
      return patchStop(uid, installed ? { installed: true } : { skipped: true });
    }).then(function () {
      toast((installed ? 'Installed' : 'Skipped') + ' Site ' + label);
      state.matchNote = '';
      enterWait();
    }).catch(function (e) { toast(e.message); }).finally(function () { state.busy = false; });
  }

  function cancelSite() {
    if (state.phase !== 'form' || !state.formUid) { enterWait(); return; }
    var uid = state.formUid;
    var snap = state.formSnapshot;
    var clear = state.grabLock === uid;
    var chain = snap ? patchStop(uid, {
      street: snap.street, direction: snap.direction, serial: snap.serial,
      notes: snap.notes, lanes: snap.lanes
    }) : Promise.resolve();
    chain.then(function () {
      if (clear) return clearGrabRemote(uid);
    }).then(function () {
      state.matchNote = '';
      enterWait();
      toast(clear ? 'GPS cleared. Grab again at the site.' : 'Back to Grab GPS.');
    }).catch(function (e) { toast(e.message); });
  }

  function buildRoute() {
    if (state.localOnly || isLocalId(state.jobId) || !state.token) {
      toast('Connect and tap Save to server, then Build route can trace streets.');
      return;
    }
    $('btnBuildRoute').disabled = true; $('btnBuildRoute').textContent = 'Building…';
    api('/api/jobs/' + state.jobId + '/route', { method: 'POST' }).then(function (res) {
      if (state.reorderMode) setReorderMode(false);
      if (res.state && res.state.route) state.job.route = res.state.route;
      if (res.state && res.state.stops) {
        state.job.stops = res.state.stops.map(function (s) {
          var raw = L.findStop(state.job, s.uid) || L.copyStop(s);
          L.mergePublicStop(raw, s);
          return raw;
        }).filter(Boolean);
      }
      applyJob(state.job, res.state); fitToStops();
      toast(res.graph ? 'Route built on streets' : 'Route built (straight-line — no road map on server)');
    }).catch(function (e) { toast(e.message); markLocal(e.message); }).finally(function () {
      $('btnBuildRoute').disabled = false; $('btnBuildRoute').textContent = 'Build route';
    });
  }

  // ----------------------------------------------------------------- drive (Follow GPS)
  function setDrive(on) {
    state.driving = !!on;
    $('btnDrive').classList.toggle('active', state.driving);
    $('btnDrive').textContent = state.driving ? 'Following…' : 'Follow GPS';
    $('driveBanner').classList.toggle('hidden', !state.driving);
    if (state.driving) {
      startWatch();
      renderDriveBanner();
      setTab('route');
    } else {
      stopWatch();
    }
  }

  function startWatch() {
    if (!navigator.geolocation) { toast('No GPS on this device.'); setDrive(false); return; }
    stopWatch();
    state.geoWatch = navigator.geolocation.watchPosition(function (pos) {
      state.myLat = pos.coords.latitude;
      state.myLon = pos.coords.longitude;
      if (meMarker) meMarker.remove();
      if (mapReady) {
        meMarker = new maplibregl.Marker({ color: '#2196f3' }).setLngLat([state.myLon, state.myLat]).addTo(map);
        map.easeTo({ center: [state.myLon, state.myLat], zoom: Math.max(map.getZoom(), 15), duration: 600 });
      }
      renderDriveBanner();
    }, function () { toast('Could not follow GPS.'); }, { enableHighAccuracy: true, maximumAge: 2000 });
  }
  function stopWatch() {
    if (state.geoWatch != null && navigator.geolocation) {
      navigator.geolocation.clearWatch(state.geoWatch);
    }
    state.geoWatch = null;
  }

  function renderDriveBanner() {
    if (!state.driving) return;
    $('driveSub').textContent = 'Grab GPS when you stop. The app picks the site.';
    if (state.myLat == null || !state.job) {
      $('driveNext').textContent = 'Follow GPS';
      return;
    }
    var match = L.matchSite(state.job.stops || [], state.myLat, state.myLon, state.myAcc);
    var near = match.nearest;
    if (match.status === 'bind' || match.status === 'choose') {
      $('driveNext').textContent = 'Nearest: Site ' + near.id + ' · ' + formatM(near.distance_m);
    } else if (match.status === 'done' && near) {
      $('driveNext').textContent = 'Site ' + near.id + ' already done';
    } else if (match.reason === 'empty') {
      $('driveNext').textContent = 'All sites done';
      $('driveSub').textContent = 'Open Audit to export.';
    } else {
      $('driveNext').textContent = near ? ('Nearest unfinished is ' + formatM(near.distance_m)) : 'No site nearby';
    }
  }

  function arrivedInstall() {
    setDrive(false);
    enterWait();
    setTab('install');
    grabGps();
  }

  // ----------------------------------------------------------------- tabs
  function setTab(tab) {
    state.tab = tab;
    TABS.forEach(function (t) {
      $(t + 'Screen').classList.toggle('hidden', t !== tab);
    });
    Array.prototype.forEach.call(document.querySelectorAll('#tabbar button'), function (b) {
      b.classList.toggle('active', b.dataset.tab === tab);
    });
    var showMap = !!MAP_TABS[tab];
    $('mapWrap').classList.toggle('hidden', !showMap);
    document.body.classList.toggle('has-map', showMap);
    if (showMap && map) setTimeout(function () { map.resize(); }, 60);
    if (tab === 'install') renderInstall();
    if (tab === 'audit') renderAudit();
    if (tab === 'setup') renderSetup();
  }

  // ----------------------------------------------------------------- job load
  function openFromJob(jobId, token, job, mapState, localOnly) {
    state.jobId = jobId;
    state.token = token || '';
    state.localOnly = !!localOnly || isLocalId(jobId);
    state.pending = [];
    job.id = jobId;
    applyJob(job, mapState);
    showApp();
    fitToStops();
    updateSaveUi();
  }

  function openJob(jobId, token) {
    state.jobId = jobId; state.token = token; saveSession();
    return api('/api/jobs/' + jobId).then(function (res) {
      return api('/api/jobs/' + jobId + '/tdjob').catch(function () { return null; })
        .then(function (pack) {
          var job = pack ? L.unpack(pack) : L.jobFromMapState(res.state, { jobId: jobId, label: (res.job && res.job.label) });
          job.id = jobId;
          if (res.job) {
            job.label = res.job.label || job.label;
            job.active_files = res.job.active_files || job.active_files;
            job.home_label = res.job.home_label || job.home_label;
          }
          openFromJob(jobId, token, job, res.state, false);
          markOnline();
        });
    });
  }

  function openLocalRecord(rec) {
    if (!rec || !rec.job) throw new Error('Saved job is empty.');
    state.pending = rec.pending || [];
    openFromJob(rec.jobId, rec.token || '', rec.job, L.buildMapState(rec.job), true);
    markLocal('Opened from this phone.');
  }

  function openTdjobData(data) {
    var id = L.localJobId();
    var job = {
      id: id,
      label: data.label,
      home: data.home,
      home_label: data.home_label,
      active_files: data.active_files,
      stops: data.stops,
      route: data.route
    };
    openFromJob(id, '', job, L.buildMapState(job), true);
    markLocal('Opened from job file. Tap Save to server when you have a signal.');
    toast('Job loaded from file');
  }

  function showApp() {
    $('startScreen').classList.add('hidden');
    $('tabbar').classList.remove('hidden');
    state.phase = 'wait';
    state.matchNote = '';
    setTab('install');
  }
  function showStart() {
    stopWatch();
    state.driving = false;
    $('startScreen').classList.remove('hidden');
    $('tabbar').classList.add('hidden');
    $('mapWrap').classList.add('hidden');
    $('saveBanner').classList.add('hidden');
    document.body.classList.remove('has-map');
    TABS.forEach(function (t) { $(t + 'Screen').classList.add('hidden'); });
    refreshLastHomeBtn();
    listPhoneJobs();
  }

  function closeRememberedJob(msg) {
    var id = state.jobId;
    clearSession();
    if (id) L.deleteSnapshot(id);
    state.jobId = null; state.token = null; state.data = null; state.job = null;
    state.reorderMode = false; state.localOnly = false; state.pending = [];
    showStart();
    if (msg) {
      $('startMsg').textContent = msg;
      $('startMsg').className = 'msg ok';
    }
  }

  function setFileLabel(inputId, labelId, emptyText) {
    var input = $(inputId), el = $(labelId);
    if (!input || !el) return;
    var names = [];
    for (var i = 0; i < input.files.length; i++) names.push(input.files[i].name);
    el.textContent = names.length ? names.join(', ') : emptyText;
    var wrap = input.closest ? input.closest('.file-btn') : input.parentNode;
    if (wrap && wrap.classList) wrap.classList.toggle('has-file', names.length > 0);
  }

  function loadSavedHome() {
    try { return JSON.parse(localStorage.getItem(LS_HOME) || 'null'); } catch (e) { return null; }
  }
  function persistHome() {
    if (state.homeLat == null) return;
    try {
      localStorage.setItem(LS_HOME, JSON.stringify({
        lat: state.homeLat, lon: state.homeLon, label: state.homeLabel || ''
      }));
    } catch (e) {}
    refreshLastHomeBtn();
  }
  function applyHome(lat, lon, label) {
    state.homeLat = lat; state.homeLon = lon; state.homeLabel = label || '';
    $('homeStatus').textContent = (label || 'Start set') + ' · ' + lat.toFixed(5) + ', ' + lon.toFixed(5);
    $('homeStatus').className = 'msg ok';
    if (label && !$('homeAddr').value.trim()) $('homeAddr').value = label;
    persistHome();
  }
  function refreshLastHomeBtn() {
    var saved = loadSavedHome();
    var btn = $('btnLastHome');
    if (!btn) return;
    if (saved && saved.lat != null) {
      btn.classList.remove('hidden');
      btn.textContent = 'Use last start' + (saved.label ? ' · ' + String(saved.label).slice(0, 40) : '');
    } else {
      btn.classList.add('hidden');
    }
  }
  function pickHomeCandidate(c) {
    applyHome(c.lat, c.lon, c.label);
    $('homeCands').classList.add('hidden');
    $('homeCands').innerHTML = '';
    toast('Start: ' + (c.label || 'saved'));
  }
  function searchHome() {
    var q = $('homeAddr').value.trim();
    if (!q) {
      $('homeStatus').textContent = 'Type a start address (street, city, CA zip).';
      $('homeStatus').className = 'msg err';
      return;
    }
    $('homeStatus').textContent = 'Searching…'; $('homeStatus').className = 'msg';
    fetch('/api/geocode?q=' + encodeURIComponent(q)).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) throw new Error(j.detail || 'Search failed');
        return j;
      });
    }).then(function (res) {
      var cands = res.candidates || [];
      if (!cands.length) {
        $('homeStatus').textContent = 'No California match — try street, city, CA zip.';
        $('homeStatus').className = 'msg err';
        $('homeCands').classList.add('hidden');
        return;
      }
      if (cands.length === 1) { pickHomeCandidate(cands[0]); return; }
      var ul = $('homeCands'); ul.innerHTML = ''; ul.classList.remove('hidden');
      cands.forEach(function (c) {
        var li = document.createElement('li');
        li.innerHTML = '<span class="grow"><b>' + esc(c.label) + '</b><span class="sub">tap to use as start</span></span>';
        li.onclick = function () { pickHomeCandidate(c); };
        ul.appendChild(li);
      });
      $('homeStatus').textContent = cands.length + ' matches — tap one.';
      $('homeStatus').className = 'msg';
    }).catch(function (e) {
      $('homeStatus').textContent = e.message || 'Address search needs a signal.';
      $('homeStatus').className = 'msg err';
    });
  }
  function homeFromGps() {
    if (!navigator.geolocation) {
      $('homeStatus').textContent = 'No GPS — type an address instead.';
      $('homeStatus').className = 'msg err';
      return;
    }
    $('homeStatus').textContent = 'Getting GPS…'; $('homeStatus').className = 'msg';
    navigator.geolocation.getCurrentPosition(function (pos) {
      var lat = pos.coords.latitude, lon = pos.coords.longitude;
      if (!(lat > CA.minLat && lat < CA.maxLat && lon > CA.minLon && lon < CA.maxLon)) {
        $('homeStatus').textContent = 'GPS is outside California — type a CA start address.';
        $('homeStatus').className = 'msg err';
        return;
      }
      applyHome(lat, lon, 'Phone GPS');
      toast('Start set from GPS');
    }, function () {
      $('homeStatus').textContent = 'GPS denied — type a start address.';
      $('homeStatus').className = 'msg err';
    }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 });
  }

  function importJob() {
    var ex = $('impExcel').files, es = $('impEst').files;
    if (!ex.length || !es.length) {
      $('startMsg').textContent = 'Pick Excel/CSV and at least one .EST — tap the file boxes above.';
      $('startMsg').className = 'msg err';
      return;
    }
    var fd = new FormData();
    for (var i = 0; i < ex.length; i++) fd.append('excel', ex[i]);
    for (var j = 0; j < es.length; j++) fd.append('est', es[j]);
    if (state.homeLat != null && state.homeLon != null) {
      fd.append('home_lat', String(state.homeLat));
      fd.append('home_lon', String(state.homeLon));
      fd.append('home_label', state.homeLabel || $('homeAddr').value.trim() || 'Field start');
    }
    $('startMsg').textContent = 'Importing…'; $('startMsg').className = 'msg';
    fetch('/api/jobs/import', { method: 'POST', body: fd }).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || 'Import failed'); return j; });
    }).then(function (res) { return openJob(res.job_id, res.token); })
      .catch(function (e) { $('startMsg').textContent = e.message; $('startMsg').className = 'msg err'; });
  }

  function resumeFile() {
    var f = $('impTdjob').files && $('impTdjob').files[0];
    if (!f) { $('startMsg').textContent = 'Pick a .tdjob.json file first.'; $('startMsg').className = 'msg err'; return; }
    $('startMsg').textContent = 'Opening job file…';
    L.parseFile(f).then(function (data) {
      // Try the server first so the crew share-link still works; fall back to this phone.
      return fetch('/api/jobs/restore', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify(L.pack({
          label: data.label, home: data.home, home_label: data.home_label,
          active_files: data.active_files, stops: data.stops, route: data.route
        }))
      }).then(function (r) {
        return r.json().then(function (j) {
          if (r.ok) return openJob(j.job_id, j.token);
          openTdjobData(data);
        });
      }).catch(function () { openTdjobData(data); });
    }).catch(function (e) {
      $('startMsg').textContent = e.message || 'Could not open that job file.';
      $('startMsg').className = 'msg err';
    });
  }

  function listPhoneJobs() {
    L.listSnapshots().then(function (rows) {
      var ul = $('phoneJobs'); ul.innerHTML = '';
      rows.sort(function (a, b) { return (b.updated || 0) - (a.updated || 0); });
      if (!rows.length) { $('phoneJobsWrap').classList.add('hidden'); return; }
      $('phoneJobsWrap').classList.remove('hidden');
      rows.forEach(function (rec) {
        var n = ((rec.job && rec.job.stops) || []).length;
        var li = document.createElement('li');
        li.innerHTML = '<span class="grow"><b>' + esc((rec.job && rec.job.label) || rec.jobId) + '</b>' +
          '<span class="sub">' + n + ' sites · tap to resume</span></span>';
        li.onclick = function () { openLocalRecord(rec); };
        ul.appendChild(li);
      });
    });
  }

  function locateMe() {
    if (!navigator.geolocation) { toast('No geolocation on this device.'); return; }
    navigator.geolocation.getCurrentPosition(function (pos) {
      var lat = pos.coords.latitude, lon = pos.coords.longitude;
      state.myLat = lat; state.myLon = lon;
      if (meMarker) meMarker.remove();
      meMarker = new maplibregl.Marker({ color: '#2196f3' }).setLngLat([lon, lat]).addTo(map);
      map.flyTo({ center: [lon, lat], zoom: 15 });
    }, function () { toast('Could not get your location.'); }, { enableHighAccuracy: true, timeout: 10000 });
  }

  // ----------------------------------------------------------------- wire up
  function wire() {
    $('btnImport').onclick = importJob;
    $('btnResumeFile').onclick = resumeFile;
    $('btnSearchHome').onclick = searchHome;
    $('btnHomeGps').onclick = homeFromGps;
    $('btnLastHome').onclick = function () {
      var saved = loadSavedHome();
      if (saved && saved.lat != null) applyHome(saved.lat, saved.lon, saved.label || '');
    };
    $('homeAddr').addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { ev.preventDefault(); searchHome(); }
    });
    $('impExcel').addEventListener('change', function () {
      setFileLabel('impExcel', 'excelNames', 'Tap to choose — .xlsx .xls .csv');
    });
    $('impEst').addEventListener('change', function () {
      setFileLabel('impEst', 'estNames', 'Tap to choose — .EST');
    });
    $('impTdjob').addEventListener('change', function () {
      setFileLabel('impTdjob', 'tdjobName', 'Tap to choose a downloaded job');
      if ($('impTdjob').files.length) resumeFile();
    });
    refreshLastHomeBtn();
    $('btnOpen').onclick = function () {
      openJob($('openId').value.trim(), $('openToken').value.trim()).catch(function (e) {
        $('startMsg').textContent = e.message; $('startMsg').className = 'msg err';
      });
    };
    $('btnBuildRoute').onclick = buildRoute;
    $('btnDrive').onclick = function () { setDrive(!state.driving); };
    $('btnStopDrive').onclick = function () { setDrive(false); };
    $('btnArrived').onclick = arrivedInstall;
    $('btnReorder').onclick = function () { setReorderMode(!state.reorderMode); };
    $('btnRetrace').onclick = retraceRoute;
    $('btnGrab').onclick = grabGps;
    $('btnDropPin').onclick = function () {
      if (state.phase === 'form') return;
      if (state.pinMode) disablePinMode(); else enablePinMode();
    };
    $('btnInstall').onclick = function () { commitInstall(true); };
    $('btnSkip').onclick = function () { commitInstall(false); };
    $('btnWrong').onclick = cancelSite;
    $('btnLocate').onclick = locateMe;
    $('btnCloseJob').onclick = function () { closeRememberedJob('Job closed on this phone. Download a job file first if you still need it.'); };
    $('btnClearSavedJob').onclick = function () { closeRememberedJob('Remembered job cleared on this phone.'); };
    $('btnCopyShare').onclick = copyShare;
    $('btnDlSetup').onclick = downloadJobFile;
    $('btnDlAudit').onclick = downloadJobFile;
    $('btnBannerDl').onclick = downloadJobFile;
    $('btnLocalCsv').onclick = downloadCsv;
    $('btnPushServer').onclick = pushToServer;
    Array.prototype.forEach.call(document.querySelectorAll('#tabbar button'), function (b) {
      b.onclick = function () {
        if (state.tab === 'install' && state.phase === 'form') flushForm();
        setTab(b.dataset.tab);
      };
    });
    ['fStreet', 'fDir', 'fLanes', 'fSerial', 'fNotes'].forEach(function (id) {
      $(id).addEventListener('change', function () { flushForm(); });
    });
    window.addEventListener('online', function () {
      if (state.job && (state.localOnly || isLocalId(state.jobId))) {
        toast('Back online — tap Setup → Save to server');
      }
    });
  }

  function shareTarget() {
    var m = location.pathname.match(/\/join\/([A-Za-z0-9_-]+)/);
    if (!m) return null;
    var token = new URLSearchParams(location.search).get('token') || '';
    return { jobId: m[1], token: token };
  }

  function applyPublicMode(isPublic, canCreate) {
    state.publicMode = !!isPublic;
    state.canCreate = !!canCreate;
    if (isPublic) document.body.classList.add('public-mode');
    if (isPublic && canCreate) document.body.classList.add('public-open');
  }

  function finishBoot() {
    var share = shareTarget();
    if (share && share.jobId) {
      $('startMsg').textContent = 'Opening shared job…';
      openJob(share.jobId, share.token).then(function () {
        try { history.replaceState({}, '', '/'); } catch (e) {}
      }).catch(function (e) {
        clearSession(); showStart();
        $('startMsg').textContent = e.message || 'This share link is invalid or expired.';
        $('startMsg').className = 'msg err';
      });
    } else if (state.publicMode && !state.canCreate) {
      clearSession();
      showStart();
    } else {
      var sess = loadSession();
      if (sess && sess.jobId) {
        L.loadSnapshot(sess.jobId).then(function (rec) {
          if (rec && rec.job && (sess.localOnly || isLocalId(sess.jobId))) {
            openLocalRecord(rec);
            return;
          }
          openJob(sess.jobId, sess.token).catch(function () {
            if (rec && rec.job) openLocalRecord(rec);
            else { clearSession(); showStart(); }
          });
        });
      } else {
        showStart();
      }
    }
  }

  function boot() {
    if (!L) { console.error('local.js failed to load'); }
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
