/* Traffic Deployer phone — local snapshot + portable .tdjob.json.
 * If the server cannot save, work stays on this phone and can be downloaded
 * as a file to re-upload later (same idea as the laptop's local shift file).
 */
(function (global) {
  'use strict';

  var FORMAT = 'traffic-deployer-job';
  var VERSION = 1;
  var DB_NAME = 'td_field';
  var STORE = 'jobs';
  var CSV_COLS = [
    'Date', 'ExactTime', 'MapDay', 'Site', 'Street', 'Serial', 'Directions', 'Lanes',
    'Notes', 'LAT', 'LON', 'Installed', 'Skipped', 'Picked up'
  ];

  function now() { return Date.now() / 1000; }

  function copyStop(raw) {
    if (!raw || typeof raw !== 'object') return null;
    var s = {
      id: String(raw.id || ''),
      uid: String(raw.uid || ''),
      sheet: raw.sheet || '',
      street: raw.street || ('Site ' + (raw.id || '')),
      begin_lat: raw.begin_lat, begin_lon: raw.begin_lon,
      end_lat: raw.end_lat, end_lon: raw.end_lon,
      lat: raw.lat, lon: raw.lon,
      cross_lat: raw.cross_lat, cross_lon: raw.cross_lon, cross_side: raw.cross_side,
      street_warning: raw.street_warning || '',
      field_lat: raw.field_lat, field_lon: raw.field_lon,
      field_coord_source: raw.field_coord_source || raw.field_source || '',
      field_accuracy_m: raw.field_accuracy_m,
      serial: String(raw.serial || ''),
      lanes: parseInt(raw.lanes, 10) || 2,
      direction: String(raw.direction || ''),
      direction_source: raw.direction_source || '',
      notes: String(raw.notes || ''),
      installed: !!raw.installed,
      skipped: !!raw.skipped,
      picked_up: !!raw.picked_up,
      date: raw.date || '',
      exact_time: raw.exact_time || ''
    };
    if (!s.uid || !s.id) return null;
    return s;
  }

  function pack(job) {
    job = job || {};
    var home = job.home;
    var route = job.route || {};
    return {
      format: FORMAT,
      version: VERSION,
      exported_at: now(),
      source_job_id: String(job.id || job.source_job_id || ''),
      label: String(job.label || 'Field job'),
      home: home && home.length >= 2 ? [Number(home[0]), Number(home[1])] : null,
      home_label: String(job.home_label || ''),
      active_files: (job.active_files || []).slice(),
      route: {
        polyline: (route.polyline || []).slice(),
        miles: Number(route.miles || 0),
        graph: !!route.graph,
        stale: !!route.stale
      },
      stops: (job.stops || []).map(copyStop).filter(Boolean)
    };
  }

  function unpack(payload) {
    if (!payload || typeof payload !== 'object') throw new Error('Job file must be a JSON object.');
    if (payload.format !== FORMAT) throw new Error('Not a Traffic Deployer job file.');
    if (Number(payload.version) !== VERSION) throw new Error('Unsupported job file version.');
    var stops = (payload.stops || []).map(copyStop).filter(Boolean);
    if (!stops.length) throw new Error('Job file has no stops.');
    var home = payload.home;
    return {
      label: String(payload.label || 'Restored job'),
      home: home && home.length >= 2 ? [Number(home[0]), Number(home[1])] : null,
      home_label: String(payload.home_label || ''),
      active_files: payload.active_files || [],
      stops: stops,
      route: {
        polyline: (payload.route && payload.route.polyline) || [],
        miles: Number((payload.route && payload.route.miles) || 0),
        graph: !!(payload.route && payload.route.graph),
        stale: !!(payload.route && payload.route.stale)
      },
      source_job_id: String(payload.source_job_id || '')
    };
  }

  function stopStatus(s) {
    if (s.picked_up) return 'picked_up';
    if (s.installed) return 'installed';
    if (s.skipped) return 'skipped';
    return 'pending';
  }

  function stopAnchor(s) {
    if (s.field_lat != null && s.field_lon != null) return [s.field_lat, s.field_lon];
    if (s.cross_lat != null && s.cross_lon != null) return [s.cross_lat, s.cross_lon];
    if (s.lat != null && s.lon != null) return [s.lat, s.lon];
    return null;
  }

  function streetLabel(s) {
    var st = String(s.street || '').trim();
    if (!st || st.toLowerCase() === 'nan') return 'Site ' + (s.id || '');
    return st;
  }

  function publicStop(s, seq) {
    var a = stopAnchor(s);
    return {
      uid: s.uid, id: s.id, street: streetLabel(s), sheet: s.sheet || '',
      status: stopStatus(s),
      installed: !!s.installed, skipped: !!s.skipped, picked_up: !!s.picked_up,
      serial: s.serial || '', lanes: s.lanes || 2, direction: s.direction || '',
      notes: s.notes || '',
      begin_lat: s.begin_lat, begin_lon: s.begin_lon,
      end_lat: s.end_lat, end_lon: s.end_lon,
      cross_lat: s.cross_lat, cross_lon: s.cross_lon, cross_side: s.cross_side,
      field_lat: s.field_lat, field_lon: s.field_lon,
      field_source: s.field_coord_source || s.field_source || '',
      lat: s.lat, lon: s.lon, anchor: a, seq: seq
    };
  }

  function progressCounts(stops) {
    var total = stops.length, installed = 0, skipped = 0, picked = 0, pending = 0;
    stops.forEach(function (s) {
      if (s.installed) installed++;
      if (s.skipped) skipped++;
      if (s.picked_up) picked++;
      if (!s.installed && !s.skipped) pending++;
    });
    return { total: total, installed: installed, skipped: skipped, picked_up: picked, pending: pending };
  }

  function buildMapState(job) {
    var stops = job.stops || [];
    var seqStops = stops.map(function (s, i) { return publicStop(s, i + 1); });
    var hi = null;
    for (var i = 0; i < stops.length; i++) {
      if (!stops[i].installed && !stops[i].skipped) { hi = stops[i].uid; break; }
    }
    var route = job.route || {};
    return {
      home: job.home || null,
      stops: seqStops,
      route: {
        polyline: route.polyline || [],
        miles: Number(route.miles || 0),
        graph: !!route.graph,
        stale: !!route.stale
      },
      highlight_uid: hi,
      counts: progressCounts(stops),
      label: job.label || '',
      active_files: job.active_files || [],
      home_label: job.home_label || ''
    };
  }

  function pad2(n) { return (n < 10 ? '0' : '') + n; }
  function stampNow() {
    var d = new Date();
    return {
      date: d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()),
      exact: pad2(d.getHours()) + ':' + pad2(d.getMinutes())
    };
  }

  function applyStopPatch(stop, patch) {
    if (!stop || !patch) return stop;
    ['street', 'direction', 'notes', 'serial'].forEach(function (k) {
      if (patch[k] != null) stop[k] = String(patch[k]).slice(0, 300);
    });
    if (patch.lanes != null) {
      var n = parseInt(patch.lanes, 10);
      if (!isNaN(n)) stop.lanes = Math.max(1, Math.min(20, n));
    }
    ['installed', 'skipped', 'picked_up'].forEach(function (k) {
      if (patch[k] != null) stop[k] = !!patch[k];
    });
    if (patch.installed && !stop.date) {
      var t = stampNow();
      stop.date = t.date;
      stop.exact_time = t.exact;
    }
    return stop;
  }

  function applyGrab(stop, lat, lon, source, accuracy) {
    stop.field_lat = lat;
    stop.field_lon = lon;
    stop.field_coord_source = (source === 'manual') ? 'manual' : 'phone_gps';
    if (accuracy != null) stop.field_accuracy_m = Math.round(Number(accuracy) * 10) / 10;
    return stop;
  }

  function findStop(job, uid) {
    var stops = (job && job.stops) || [];
    for (var i = 0; i < stops.length; i++) if (stops[i].uid === uid) return stops[i];
    return null;
  }

  function moveStop(job, uid, dir) {
    var stops = job.stops || [];
    var idx = -1;
    for (var i = 0; i < stops.length; i++) if (stops[i].uid === uid) { idx = i; break; }
    if (idx < 0) return 'not_found';
    var swap = dir === 'up' ? idx - 1 : idx + 1;
    if (swap < 0 || swap >= stops.length) return 'edge';
    var tmp = stops[idx];
    stops[idx] = stops[swap];
    stops[swap] = tmp;
    job.route = job.route || {};
    job.route.stale = true;
    return 'moved';
  }

  function jobFromMapState(state, meta) {
    meta = meta || {};
    var stops = ((state && state.stops) || []).map(copyStop).filter(Boolean);
    return {
      id: meta.jobId || '',
      label: meta.label || (state && state.label) || 'Field job',
      home: (state && state.home) || null,
      home_label: meta.home_label || (state && state.home_label) || '',
      active_files: meta.active_files || (state && state.active_files) || [],
      stops: stops,
      route: (state && state.route) || { polyline: [], miles: 0, graph: false }
    };
  }

  function mergePublicStop(raw, pub) {
    if (!raw || !pub) return;
    applyStopPatch(raw, {
      street: pub.street, direction: pub.direction, notes: pub.notes,
      serial: pub.serial, lanes: pub.lanes,
      installed: pub.installed, skipped: pub.skipped, picked_up: pub.picked_up
    });
    if (Object.prototype.hasOwnProperty.call(pub, 'field_lat')) {
      raw.field_lat = pub.field_lat;
      raw.field_lon = pub.field_lon;
      raw.field_coord_source = pub.field_lat == null ? '' : (pub.field_source || raw.field_coord_source || '');
      if (pub.field_lat == null) raw.field_accuracy_m = null;
    }
  }

  function audit(stops) {
    var done = (stops || []).filter(function (s) { return s.installed || s.skipped; });
    var missing = [];
    done.forEach(function (s) {
      if (!s.installed) return;
      if (!String(s.serial || '').trim()) missing.push('Site ' + s.id + ': missing Serial #');
      var street = String(s.street || '').trim();
      if (!street || street.toLowerCase() === 'nan' || street.indexOf('Site ') === 0) {
        missing.push('Site ' + s.id + ': missing Street name');
      }
    });
    return { ok: missing.length === 0, missing: missing, count: done.length };
  }

  function csvEscape(v) {
    var s = (v == null ? '' : String(v));
    if (/[",\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
    return s;
  }

  function toCsv(stops) {
    var lines = [CSV_COLS.join(',')];
    (stops || []).forEach(function (s) {
      var lat = s.field_lat != null ? s.field_lat : s.lat;
      var lon = s.field_lon != null ? s.field_lon : s.lon;
      var row = [
        s.date || '', s.exact_time || '', s.sheet || '', s.id || '', s.street || '',
        s.serial || '', s.direction || '', s.lanes || '', s.notes || '',
        lat, lon,
        s.installed ? 'x' : '', s.skipped ? 'x' : '', s.picked_up ? 'x' : ''
      ];
      lines.push(row.map(csvEscape).join(','));
    });
    return lines.join('\n');
  }

  function haversineMi(lat1, lon1, lat2, lon2) {
    var R = 3958.8;
    var toR = Math.PI / 180;
    var dLat = (lat2 - lat1) * toR, dLon = (lon2 - lon1) * toR;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(lat1 * toR) * Math.cos(lat2 * toR) *
      Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  // Keep in sync with mobile_web/site_match.py
  var AUTO_M = 80;
  var CONFIRM_M = 200;
  var AMBIGUOUS_GAP_M = 35;
  var DONE_CLOSER_M = 10;
  var FUZZY_ACCURACY_M = 65;

  function finiteNum(v) {
    var n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  function havM(lat1, lon1, lat2, lon2) {
    var R = 6371000;
    var toR = Math.PI / 180;
    var dLat = (lat2 - lat1) * toR, dLon = (lon2 - lon1) * toR;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(lat1 * toR) * Math.cos(lat2 * toR) *
      Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function localXY(lat, lon, lat0, lon0) {
    var mLat = 111320.0;
    var mLon = 111320.0 * Math.cos(lat0 * Math.PI / 180);
    return [(lon - lon0) * mLon, (lat - lat0) * mLat];
  }

  function segmentDistanceM(plat, plon, aLat, aLon, bLat, bLon) {
    var a = localXY(aLat, aLon, aLat, aLon);
    var b = localXY(bLat, bLon, aLat, aLon);
    var p = localXY(plat, plon, aLat, aLon);
    var abx = b[0] - a[0], aby = b[1] - a[1];
    var apx = p[0] - a[0], apy = p[1] - a[1];
    var ab2 = abx * abx + aby * aby;
    if (ab2 < 1e-6) return havM(plat, plon, aLat, aLon);
    var t = (apx * abx + apy * aby) / ab2;
    if (t < 0) t = 0;
    if (t > 1) t = 1;
    var cx = a[0] + t * abx, cy = a[1] + t * aby;
    var dx = p[0] - cx, dy = p[1] - cy;
    return Math.sqrt(dx * dx + dy * dy);
  }

  function siteSegment(stop) {
    var blat = finiteNum(stop.begin_lat), blon = finiteNum(stop.begin_lon);
    if (blat == null || blon == null) {
      blat = finiteNum(stop.lat); blon = finiteNum(stop.lon);
    }
    if (blat == null || blon == null) return null;
    var elat = finiteNum(stop.end_lat), elon = finiteNum(stop.end_lon);
    if (elat == null || elon == null) { elat = blat; elon = blon; }
    return [blat, blon, elat, elon];
  }

  function packMatch(row) {
    return {
      uid: row.uid, id: row.id, street: row.street, distance_m: row.distance_m,
      installed: row.installed, skipped: row.skipped
    };
  }

  function matchSite(stops, lat, lon, accuracy) {
    var ranked = [];
    (stops || []).forEach(function (stop) {
      var seg = siteSegment(stop);
      if (!seg) return;
      var distance = segmentDistanceM(lat, lon, seg[0], seg[1], seg[2], seg[3]);
      ranked.push({
        uid: stop.uid, id: stop.id, street: String(stop.street || ''),
        distance_m: Math.round(distance * 10) / 10,
        installed: !!stop.installed, skipped: !!stop.skipped,
        done: !!(stop.installed || stop.skipped)
      });
    });
    ranked.sort(function (a, b) { return a.distance_m - b.distance_m; });
    var pending = ranked.filter(function (r) { return !r.done; });
    var finished = ranked.filter(function (r) { return r.done; });
    var empty = { status: 'none', reason: 'empty', options: [], nearest: null, nearby_done: null };
    if (!ranked.length) return empty;
    var nearestDone = finished[0] || null;
    var nearestPending = pending[0] || null;
    var forceChoose = false;
    if (nearestDone && nearestDone.distance_m <= AUTO_M) {
      var pendingDist = nearestPending ? nearestPending.distance_m : 1e12;
      if (pendingDist > nearestDone.distance_m + DONE_CLOSER_M) {
        var donePack = packMatch(nearestDone);
        return {
          status: 'done', reason: 'already', uid: nearestDone.uid,
          distance_m: nearestDone.distance_m, options: [], nearest: donePack, nearby_done: donePack
        };
      }
      forceChoose = true;
    }
    if (!nearestPending || nearestPending.distance_m > CONFIRM_M) {
      var near = nearestPending ? packMatch(nearestPending) : (nearestDone ? packMatch(nearestDone) : null);
      return {
        status: 'none', reason: nearestPending ? 'far' : 'empty', options: [],
        nearest: near, nearby_done: nearestDone ? packMatch(nearestDone) : null
      };
    }
    var options = pending.filter(function (r) { return r.distance_m <= CONFIRM_M; })
      .slice(0, 3).map(packMatch);
    var second = pending.length > 1 ? pending[1].distance_m : 1e12;
    var gap = second - nearestPending.distance_m;
    var acc = finiteNum(accuracy);
    if (acc != null && acc < 0) acc = null;
    var fuzzy = acc != null && acc > FUZZY_ACCURACY_M;
    var ambiguous = gap < AMBIGUOUS_GAP_M && second <= CONFIRM_M;
    var closeEnough = nearestPending.distance_m <= AUTO_M;
    var packed = packMatch(nearestPending);
    var nearby = nearestDone ? packMatch(nearestDone) : null;
    if (closeEnough && !ambiguous && !fuzzy && !forceChoose) {
      return {
        status: 'bind', reason: 'clear', uid: nearestPending.uid,
        distance_m: nearestPending.distance_m, options: options, nearest: packed, nearby_done: nearby
      };
    }
    var reason = ambiguous ? 'ambiguous' : (fuzzy ? 'fuzzy' : (forceChoose ? 'already_near' : 'confirm'));
    return {
      status: 'choose', reason: reason, uid: nearestPending.uid,
      distance_m: nearestPending.distance_m, options: options, nearest: packed, nearby_done: nearby
    };
  }

  function clearGrab(stop) {
    if (!stop) return stop;
    stop.field_lat = null;
    stop.field_lon = null;
    stop.field_coord_source = '';
    stop.field_accuracy_m = null;
    return stop;
  }

  function localJobId() {
    return 'local-' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
  }

  // ----- IndexedDB (falls back to localStorage) -----
  var LS_PREFIX = 'td_job_';

  function idb() {
    return new Promise(function (resolve, reject) {
      if (!global.indexedDB) { reject(new Error('no idb')); return; }
      var req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: 'jobId' });
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }

  function saveSnapshot(rec) {
    rec.updated = Date.now();
    return idb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, 'readwrite');
        tx.objectStore(STORE).put(rec);
        tx.oncomplete = function () { resolve(rec); };
        tx.onerror = function () { reject(tx.error); };
      });
    }).catch(function () {
      try { localStorage.setItem(LS_PREFIX + rec.jobId, JSON.stringify(rec)); } catch (e) {}
      return rec;
    });
  }

  function loadSnapshot(jobId) {
    return idb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, 'readonly');
        var req = tx.objectStore(STORE).get(jobId);
        req.onsuccess = function () { resolve(req.result || null); };
        req.onerror = function () { reject(req.error); };
      });
    }).catch(function () {
      try { return JSON.parse(localStorage.getItem(LS_PREFIX + jobId) || 'null'); } catch (e) { return null; }
    });
  }

  function listSnapshots() {
    return idb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, 'readonly');
        var req = tx.objectStore(STORE).getAll();
        req.onsuccess = function () { resolve(req.result || []); };
        req.onerror = function () { reject(req.error); };
      });
    }).catch(function () {
      var out = [];
      try {
        for (var i = 0; i < localStorage.length; i++) {
          var k = localStorage.key(i);
          if (k && k.indexOf(LS_PREFIX) === 0) {
            var v = JSON.parse(localStorage.getItem(k) || 'null');
            if (v) out.push(v);
          }
        }
      } catch (e) {}
      return out;
    });
  }

  function deleteSnapshot(jobId) {
    return idb().then(function (db) {
      return new Promise(function (resolve) {
        var tx = db.transaction(STORE, 'readwrite');
        tx.objectStore(STORE).delete(jobId);
        tx.oncomplete = function () { resolve(); };
        tx.onerror = function () { resolve(); };
      });
    }).catch(function () {
      try { localStorage.removeItem(LS_PREFIX + jobId); } catch (e) {}
    });
  }

  function downloadNamed(filename, text, mime) {
    var blob = new Blob([text], { type: mime || 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(url); a.remove(); }, 500);
  }

  function parseFile(file) {
    return new Promise(function (resolve, reject) {
      var r = new FileReader();
      r.onload = function () {
        try { resolve(unpack(JSON.parse(String(r.result || '')))); }
        catch (e) { reject(e); }
      };
      r.onerror = function () { reject(new Error('Could not read that file.')); };
      r.readAsText(file);
    });
  }

  global.TDLocal = {
    FORMAT: FORMAT, VERSION: VERSION,
    pack: pack, unpack: unpack,
    buildMapState: buildMapState,
    applyStopPatch: applyStopPatch,
    applyGrab: applyGrab,
    findStop: findStop,
    moveStop: moveStop,
    jobFromMapState: jobFromMapState,
    mergePublicStop: mergePublicStop,
    copyStop: copyStop,
    audit: audit,
    toCsv: toCsv,
    haversineMi: haversineMi,
    matchSite: matchSite,
    clearGrab: clearGrab,
    localJobId: localJobId,
    saveSnapshot: saveSnapshot,
    loadSnapshot: loadSnapshot,
    listSnapshots: listSnapshots,
    deleteSnapshot: deleteSnapshot,
    downloadNamed: downloadNamed,
    parseFile: parseFile
  };
})(typeof window !== 'undefined' ? window : globalThis);
