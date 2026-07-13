/*
 * Map canvas controller.
 *
 * Python -> JS : pushState(json)  redraw site segments + route + origin + theme
 *                pushGps(json)    move live GPS dot + extend the trail
 *                pushNav(json)    (unused — map-only driving)
 *                flyTo(lat,lon,z) recenter
 * JS -> Python : onMapClick(lat,lon), onStopClick(uid), onReady()
 */
(function () {
  'use strict';

  // errorOnMissingTile: missing z>N tiles must error so MapLibre overzooms z15
  // instead of painting an empty MVT (map whitens at max zoom).
  var protocol = new pmtiles.Protocol({ errorOnMissingTile: true });
  maplibregl.addProtocol('pmtiles', protocol.tile);

  var origin = window.location.origin;
  var pmtilesUrl = origin + '/data/california.pmtiles';
  var MAX_ZOOM = 16;
  var FOLLOW_ZOOM = 13;
  var FOLLOW_ZOOM_MIN = 8;
  var SITE_CLICK_ZOOM = 15;
  // D6: fan overlapping site dots so badges stay readable.
  var COLLOC_THRESHOLD_M = 28;
  var COLLOC_FAN_RADIUS_M = 22;
  // D1: sites, GPS, and pins only — no route/segment/drive-leg polylines.
  var SHOW_TRACE_LINES = false;

  var map = new maplibregl.Map({
    container: 'map',
    style: buildStyle(pmtilesUrl, origin),
    center: [-117.9431, 33.7715],
    zoom: 11,
    maxZoom: MAX_ZOOM,
    renderWorldCopies: false,
    attributionControl: { compact: true },
    fadeDuration: 0,
    refreshExpiredTiles: false,
    maxTileCacheSize: 64
  });
  window._map = map;
  window.__mapLoaded = false;
  window.__styleData = false;
  window.__bridgeReady = false;
  window.__dbg = { pushes: 0, lastStops: 0, applied: 0, segCount: -1 };

  var styleReady = false;
  var pendingState = null;
  map.on('load', function () {
    window.__mapLoaded = true;
    styleReady = true;
    ensureSources();
    if (pendingState) { var p = pendingState; pendingState = null; renderState(p); }
  });
  map.on('styledata', function () { window.__styleData = true; });
  window.__jsErrors = [];
  window.addEventListener('error', function (e) { window.__jsErrors.push(String(e.message)); });
  map.on('error', function (e) {
    window.__jsErrors.push('map: ' + (e && e.error && e.error.message ? e.error.message : 'unknown'));
  });

  var bridge = null;
  // D7: camera follow is opt-in — GPS marker always updates; pan freely without re-lock.
  var follow = false;
  var recenterPending = false;
  var lastGps = null;
  var homeMarker = null;
  var gpsMarker = null;
  var fieldPinMarker = null;
  var lastState = null;
  var _lastHomeKey = '';
  var _leanDrive = false;
  var LEAN_BASE_LAYERS = ['landuse', 'roads-all', 'roads-major'];

  var followBtn = document.getElementById('follow-btn');
  var zoomInBtn = document.getElementById('zoom-in');
  var zoomOutBtn = document.getElementById('zoom-out');
  var nextSiteBtn = document.getElementById('next-site-btn');
  var compassNeedle = document.getElementById('compass-needle');
  var compassReadout = document.getElementById('compass-readout');
  var compassMode = document.getElementById('compass-mode');

  var CARDINALS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  function cardinal(deg) {
    if (deg == null || isNaN(deg)) return '—';
    return CARDINALS[Math.round(((deg % 360) + 360) % 360 / 45) % 8];
  }

  function updateCompass(g) {
    if (!compassNeedle) return;
    var h = g.heading;
    if (h == null || isNaN(h)) {
      compassNeedle.style.transform = 'rotate(0deg)';
      compassReadout.textContent = '—°';
      compassMode.textContent = 'No heading — drive briefly, then stop';
      return;
    }
    compassNeedle.style.transform = 'rotate(' + h + 'deg)';
    compassReadout.textContent = Math.round(h) + '° ' + cardinal(h);
    var mode = g.heading_mode || '';
    if (mode === 'locked') {
      compassMode.textContent = 'Stopped — locked (install direction)';
    } else if (mode === 'moving') {
      compassMode.textContent = 'Moving — live course';
    } else {
      compassMode.textContent = 'Slow/stop — averaged heading';
    }
  }

  function recenterOnGps(g, animate) {
    if (!g || g.lat == null) return;
    var z = Math.max(map.getZoom(), FOLLOW_ZOOM);
    if (animate === false) {
      map.jumpTo({ center: [g.lon, g.lat], zoom: z });
    } else {
      map.flyTo({ center: [g.lon, g.lat], zoom: z, duration: 550 });
    }
    recenterPending = false;
  }

  function setFollow(on, fromPython) {
    follow = !!on;
    followBtn.textContent = follow ? 'Following' : 'Follow Me';
    followBtn.className = 'hudBtn primary' + (follow ? '' : ' off');
    if (follow) {
      recenterPending = true;
      if (lastGps) recenterOnGps(lastGps, true);
    } else {
      recenterPending = false;
    }
    if (!fromPython && bridge && typeof bridge.onFollowToggled === 'function') {
      try { bridge.onFollowToggled(follow); } catch (e) { /* QWebChannel optional */ }
    }
  }
  followBtn.addEventListener('click', function () { setFollow(!follow, false); });
  map.on('dragstart', function () {
    if (follow) setFollow(false, false);
  });
  if (zoomInBtn) {
    zoomInBtn.addEventListener('click', function () {
      map.zoomTo(Math.min(map.getZoom() + 1, MAX_ZOOM), { duration: 200 });
    });
  }
  if (zoomOutBtn) {
    zoomOutBtn.addEventListener('click', function () {
      map.zoomTo(Math.max(map.getZoom() - 1, FOLLOW_ZOOM_MIN), { duration: 200 });
    });
  }

  function nextDriveStop(state) {
    if (!state || !state.stops || !state.stops.length) return null;
    var uid = state.drive_target_uid || state.highlight_uid;
    if (uid) {
      for (var i = 0; i < state.stops.length; i++) {
        if (state.stops[i].uid === uid) return state.stops[i];
      }
    }
    for (var j = 0; j < state.stops.length; j++) {
      var s = state.stops[j];
      if (!s.installed && !s.skipped) return s;
    }
    return state.stops[0];
  }

  function frameNextSite() {
    if (!lastState) return;
    var target = nextDriveStop(lastState);
    var anchor = target ? stopAnchor(target) : null;
    if (!anchor) return;
    var b = new maplibregl.LngLatBounds();
    b.extend([anchor[1], anchor[0]]);
    if (_gpsDisplay && _gpsDisplay.lat != null) {
      b.extend([_gpsDisplay.lon, _gpsDisplay.lat]);
    } else if (lastState.home) {
      b.extend([lastState.home[1], lastState.home[0]]);
    }
    map.fitBounds(b, {
      padding: { top: 80, bottom: 140, left: 80, right: 120 },
      duration: 650,
      maxZoom: FOLLOW_ZOOM,
      linear: false
    });
  }

  if (nextSiteBtn) {
    nextSiteBtn.addEventListener('click', frameNextSite);
  }

  function fieldPinColor(source) {
    return source === 'manual' ? '#e65100' : '#1565c0';
  }

  function clearFieldPinMarker() {
    if (fieldPinMarker) { fieldPinMarker.remove(); fieldPinMarker = null; }
  }

  function placeFieldPin(lat, lon, opts) {
    opts = opts || {};
    var src = opts.source || 'gps';
    var draggable = !!opts.draggable;
    if (fieldPinMarker) {
      var same = fieldPinMarker._tdLat === lat && fieldPinMarker._tdLon === lon &&
        fieldPinMarker._tdSource === src && fieldPinMarker._tdDraggable === draggable;
      if (same) return;
      fieldPinMarker.remove();
      fieldPinMarker = null;
    }
    if (!draggable) return;
    fieldPinMarker = new maplibregl.Marker({
      color: fieldPinColor(src),
      draggable: true,
      scale: 1.15
    }).setLngLat([lon, lat]).addTo(map);
    fieldPinMarker._tdLat = lat;
    fieldPinMarker._tdLon = lon;
    fieldPinMarker._tdSource = src;
    fieldPinMarker._tdDraggable = true;
    fieldPinMarker._tdUid = opts.uid || '';
    fieldPinMarker._tdSiteId = opts.siteId != null ? String(opts.siteId) : '';
    fieldPinMarker.on('dragend', function () {
      var ll = fieldPinMarker.getLngLat();
      fieldPinMarker._tdLat = ll.lat;
      fieldPinMarker._tdLon = ll.lng;
    });
    var el = fieldPinMarker.getElement();
    if (el && !el._tdClickBound) {
      el._tdClickBound = true;
      el.style.cursor = 'pointer';
      el.addEventListener('click', function (ev) {
        ev.stopPropagation();
        var uid = fieldPinMarker._tdUid;
        if (!uid) return;
        var payload = 'install|' + uid;
        showSiteInfoToast(payload);
        fireStopClick(payload);
      });
    }
  }

  function syncFieldPinFromState(state) {
    if (!state || !state.on_install || !state.current_uid) {
      if (!state || state.map_mode !== 'manual_grab') clearFieldPinMarker();
      return;
    }
    var stop = null;
    (state.stops || []).forEach(function (s) {
      if (s.uid === state.current_uid) stop = s;
    });
    if (!stop || stop.field_lat == null || stop.field_lon == null) {
      if (state.map_mode !== 'manual_grab') clearFieldPinMarker();
      return;
    }
    var src = stop.field_coord_source || stop.field_source || 'gps';
    var draggable = state.map_mode === 'manual_grab';
    if (!draggable) {
      clearFieldPinMarker();
      return;
    }
    placeFieldPin(stop.field_lat, stop.field_lon, {
      source: src,
      draggable: true,
      uid: stop.uid,
      siteId: stop.id
    });
  }

  function emptyFC() { return { type: 'FeatureCollection', features: [] }; }
  function pt(lat, lon, props) {
    return { type: 'Feature', properties: props || {}, geometry: { type: 'Point', coordinates: [lon, lat] } };
  }
  function line(coords) {
    return { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } };
  }
  function routeLineFC(coords, onRoads) {
    var ring = coords.map(function (p) { return [p[1], p[0]]; });
    return {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        properties: { on_roads: onRoads !== false },
        geometry: { type: 'LineString', coordinates: ring }
      }]
    };
  }

  function setLayerVis(id, on) {
    if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
  }

  var BASE_LABEL_LAYERS = ['road-label-hwy', 'road-label-major', 'road-label-local'];

  function setBasemapLabels(on) {
    BASE_LABEL_LAYERS.forEach(function (id) { setLayerVis(id, on); });
  }

  var STOP_STATUS_COLOR = [
    'case',
    ['==', ['get', 'status'], 'installed'], '#1b5e20',
    ['==', ['get', 'status'], 'skipped'], '#b71c1c',
    ['==', ['get', 'status'], 'picked_up'], '#0d47a1',
    '#c45f14'
  ];

  // White numerals centered inside colored dots — high contrast in sunlight.
  // Dot radii sit just above road line width (~3–7px); hit pad keeps taps easy.
  var DOT_R = ['interpolate', ['linear'], ['zoom'], 10, 6, 14, 8, 16, 10];
  var DOT_R_HI = ['interpolate', ['linear'], ['zoom'], 10, 8, 14, 10, 16, 12];
  var DOT_LABEL_FONT = ['Noto Sans Regular'];
  var DOT_LABEL_LAYOUT = {
    'text-font': DOT_LABEL_FONT,
    'text-size': ['interpolate', ['linear'], ['zoom'], 10, 8, 14, 9, 16, 10],
    'text-allow-overlap': true,
    'text-ignore-placement': true,
    'text-anchor': 'center'
  };
  var DOT_LABEL_PAINT = {
    'text-color': '#ffffff',
    'text-halo-color': 'rgba(15, 39, 68, 0.9)',
    'text-halo-width': 1.5
  };

  // Legacy alias — road pick labels on pale halos.
  var MAP_LABEL_PAINT = {
    'text-color': '#0f2744',
    'text-halo-color': '#ffffff',
    'text-halo-width': 2
  };

  function fireStopClick(payload) {
    if (!payload) return;
    if (bridge && typeof bridge.onStopClick === 'function') {
      try {
        bridge.onStopClick(payload);
        return;
      } catch (e) { /* fall through to tdstop:// */ }
    }
    window.location.href = 'tdstop://' + encodeURIComponent(payload);
  }

  // Empty-map clicks must reach Python even when QWebChannel never connected
  // (work-laptop case): fall back to the tdmap:// scheme the page intercepts.
  function fireMapClick(lat, lon) {
    if (bridge && typeof bridge.onMapClick === 'function') {
      try {
        bridge.onMapClick(lat, lon);
        return;
      } catch (e) { /* fall through to tdmap:// */ }
    }
    window.location.href = 'tdmap://point?lat=' +
      encodeURIComponent(lat) + '&lon=' + encodeURIComponent(lon);
  }

  var PICK_CLICK_LAYERS = [
    'pick-target-circle', 'pick-target-label',
    'stop-circle', 'stop-label',
    'site-begin', 'site-end', 'site-begin-label', 'site-end-label',
    'install-pts', 'install-pts-label'
  ];
  // Hit tolerance (px) so small begin/end dots are easy to tap on a touch /
  // high-DPI work laptop. A bare 1px hit test made the dots feel un-clickable.
  function pickHitPad() {
    var dpr = (window.devicePixelRatio && window.devicePixelRatio > 1) ? window.devicePixelRatio : 1;
    return Math.round(14 + (dpr - 1) * 8);
  }

  function haversineM(lat1, lon1, lat2, lon2) {
    var R = 6371000;
    var p = Math.PI / 180;
    var a = 0.5 - Math.cos((lat2 - lat1) * p) / 2 +
      Math.cos(lat1 * p) * Math.cos(lat2 * p) * (1 - Math.cos((lon2 - lon1) * p)) / 2;
    return 2 * R * Math.asin(Math.sqrt(a));
  }

  function offsetMeters(lat, lon, bearingDeg, distM) {
    var br = bearingDeg * Math.PI / 180;
    var latRad = lat * Math.PI / 180;
    var cosLat = Math.cos(latRad);
    if (Math.abs(cosLat) < 1e-6) cosLat = 1e-6;
    var dLat = (distM * Math.cos(br)) / 111320;
    var dLon = (distM * Math.sin(br)) / (111320 * cosLat);
    return [lat + dLat, lon + dLon];
  }

  /** D6: spread collocated map dots in a small fan so circles do not stack. */
  function spreadCollocated(items, thresholdM, radiusM) {
    if (!items || items.length < 2) return;
    thresholdM = thresholdM || COLLOC_THRESHOLD_M;
    radiusM = radiusM || COLLOC_FAN_RADIUS_M;
    var n = items.length;
    var parent = items.map(function (_, i) { return i; });
    function find(a) {
      while (parent[a] !== a) {
        parent[a] = parent[parent[a]];
        a = parent[a];
      }
      return a;
    }
    function unite(a, b) {
      parent[find(a)] = find(b);
    }
    for (var i = 0; i < n; i++) {
      for (var j = i + 1; j < n; j++) {
        if (haversineM(items[i].lat, items[i].lon, items[j].lat, items[j].lon) <= thresholdM) {
          unite(i, j);
        }
      }
    }
    var groups = {};
    for (var k = 0; k < n; k++) {
      var root = find(k);
      if (!groups[root]) groups[root] = [];
      groups[root].push(k);
    }
    Object.keys(groups).forEach(function (key) {
      var idxs = groups[key];
      if (idxs.length < 2) return;
      var cLat = 0;
      var cLon = 0;
      idxs.forEach(function (ix) {
        cLat += items[ix].lat;
        cLon += items[ix].lon;
      });
      cLat /= idxs.length;
      cLon /= idxs.length;
      if (idxs.length === 2) {
        var half = radiusM * 0.55;
        var o0 = offsetMeters(cLat, cLon, 135, half);
        var o1 = offsetMeters(cLat, cLon, 315, half);
        items[idxs[0]].lat = o0[0];
        items[idxs[0]].lon = o0[1];
        items[idxs[1]].lat = o1[0];
        items[idxs[1]].lon = o1[1];
        return;
      }
      var step = 360 / idxs.length;
      idxs.forEach(function (ix, pos) {
        var o = offsetMeters(cLat, cLon, pos * step, radiusM);
        items[ix].lat = o[0];
        items[ix].lon = o[1];
      });
    });
  }

  /** When layer hit-test misses, snap to nearest unpicked begin/end (mirrors Python). */
  function nearestPickAt(lat, lon, maxM) {
    if (!lastState || lastState.map_mode !== 'pick') return null;
    maxM = maxM || 750;
    var stops = lastState.stops || [];
    var pickOrder = lastState.pick_order || [];
    var picked = {};
    pickOrder.forEach(function (u) { picked[u] = true; });
    var bestUid = null, bestSide = null, bestD = maxM;
    stops.forEach(function (s) {
      var uid = s.uid != null ? String(s.uid) : '';
      if (!uid || picked[uid]) return;
      [
        ['begin_lat', 'begin_lon', 'begin'],
        ['end_lat', 'end_lon', 'end']
      ].forEach(function (row) {
        var la = s[row[0]], lo = s[row[1]];
        if (la == null || lo == null) return;
        var d = haversineM(lat, lon, la, lo);
        if (d < bestD) {
          bestD = d;
          bestUid = uid;
          bestSide = row[2];
        }
      });
    });
    if (!bestUid) return null;
    return bestSide ? (bestUid + '|' + bestSide) : bestUid;
  }

  function pickLayerAtPoint(point) {
    var layers = PICK_CLICK_LAYERS.filter(function (id) { return map.getLayer(id); });
    if (!layers.length) return null;
    var pad = pickHitPad();
    var box = [
      [point.x - pad, point.y - pad],
      [point.x + pad, point.y + pad]
    ];
    var features;
    try {
      features = map.queryRenderedFeatures(box, { layers: layers });
    } catch (e) {
      features = map.queryRenderedFeatures(point, { layers: layers });
    }
    if (!features || !features.length) return null;
    // Among everything under the padded box, take the dot closest to the click.
    var best = null, bestD = Infinity;
    for (var i = 0; i < features.length; i++) {
      var props = features[i].properties || {};
      if (!props.uid) continue;
      var d = 0;
      var g = features[i].geometry;
      if (g && g.type === 'Point' && g.coordinates) {
        var sp = map.project([g.coordinates[0], g.coordinates[1]]);
        var dx = sp.x - point.x, dy = sp.y - point.y;
        d = dx * dx + dy * dy;
      }
      if (d < bestD) { bestD = d; best = props; }
    }
    if (!best) return null;
    var kind = best.kind;
    if (kind === 'install') {
      return 'install|' + String(best.uid);
    }
    if (kind === 'begin' || kind === 'end') {
      return String(best.uid) + '|' + kind;
    }
    return String(best.uid);
  }

  function bindStopClicks() {
    if (map._stopClickBound) return;
    map._stopClickBound = true;
    // Clicks are routed through the single map-level handler (pickLayerAtPoint),
    // which uses a padded hit box. Here we only set the hover cursor.
    ['stop-circle', 'site-begin', 'site-end', 'site-begin-label', 'site-end-label',
      'pick-target-circle', 'pick-target-label', 'install-pts', 'install-pts-label'].forEach(function (id) {
      map.on('mouseenter', id, function () { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', id, function () { map.getCanvas().style.cursor = ''; });
    });
  }

  function ensureSources() {
    if (!map.getSource('route')) {
      map.addSource('route', { type: 'geojson', data: emptyFC() });
      map.addLayer({ id: 'route-casing', type: 'line', source: 'route',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': [
            'case', ['boolean', ['get', 'on_roads'], true], '#0f2744', '#b45309'
          ],
          'line-width': ['interpolate', ['linear'], ['zoom'], 10, 5, 14, 12],
          'line-opacity': 0.55
        } });
      map.addLayer({ id: 'route-line', type: 'line', source: 'route',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': [
            'case', ['boolean', ['get', 'on_roads'], true], '#1e88e5', '#f59e0b'
          ],
          'line-width': ['interpolate', ['linear'], ['zoom'], 10, 3, 14, 7],
          'line-opacity': 0.95
        } });
    }
    if (!map.getSource('segments')) {
      map.addSource('segments', { type: 'geojson', data: emptyFC() });
      map.addLayer({ id: 'segments-line', type: 'line', source: 'segments',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': '#5e35b1',
          'line-width': ['interpolate', ['linear'], ['zoom'], 10, 2, 14, 3.5, 15, 4.5],
          'line-opacity': 0.88,
          'line-dasharray': [3, 2]
        } });
    }
    if (!map.getSource('site-pts')) {
      map.addSource('site-pts', { type: 'geojson', data: emptyFC() });
      map.addLayer({ id: 'site-begin', type: 'circle', source: 'site-pts',
        filter: ['==', ['get', 'kind'], 'begin'],
        paint: {
          'circle-radius': DOT_R,
          'circle-color': '#1565c0',
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 1.5,
          'circle-opacity': 0.95
        } });
      map.addLayer({ id: 'site-end', type: 'circle', source: 'site-pts',
        filter: ['==', ['get', 'kind'], 'end'],
        paint: {
          'circle-radius': DOT_R,
          'circle-color': '#c62828',
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 1.5,
          'circle-opacity': 0.95
        } });
      var siteLabelLayout = Object.assign({}, DOT_LABEL_LAYOUT, {
        'text-field': ['to-string', ['get', 'seq']]
      });
      map.addLayer({ id: 'site-begin-label', type: 'symbol', source: 'site-pts',
        filter: ['==', ['get', 'kind'], 'begin'],
        layout: siteLabelLayout,
        paint: DOT_LABEL_PAINT });
      map.addLayer({ id: 'site-end-label', type: 'symbol', source: 'site-pts',
        filter: ['==', ['get', 'kind'], 'end'],
        layout: siteLabelLayout,
        paint: DOT_LABEL_PAINT });
    }
    if (!map.getSource('stop-markers')) {
      map.addSource('stop-markers', { type: 'geojson', data: emptyFC() });
      map.addLayer({ id: 'stop-circle', type: 'circle', source: 'stop-markers',
        paint: {
          'circle-radius': [
            'case', ['boolean', ['get', 'highlight'], false],
            DOT_R_HI,
            DOT_R
          ],
          'circle-color': STOP_STATUS_COLOR,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 1.5,
          'circle-opacity': 0.96
        } });
      map.addLayer({ id: 'stop-label', type: 'symbol', source: 'stop-markers',
        layout: Object.assign({}, DOT_LABEL_LAYOUT, {
          'text-field': ['to-string', ['get', 'seq']],
          'text-size': [
            'case', ['boolean', ['get', 'highlight'], false],
            ['interpolate', ['linear'], ['zoom'], 10, 9, 14, 10, 16, 11],
            ['interpolate', ['linear'], ['zoom'], 10, 8, 14, 9, 16, 10]
          ]
        }),
        paint: DOT_LABEL_PAINT });
      bindStopClicks();
    }
    if (!map.getSource('pick-targets')) {
      map.addSource('pick-targets', { type: 'geojson', data: emptyFC() });
      map.addLayer({ id: 'pick-target-circle', type: 'circle', source: 'pick-targets',
        paint: {
          'circle-radius': DOT_R,
          'circle-color': '#f57c00',
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 1.5,
          'circle-opacity': 0.96
        } });
      map.addLayer({ id: 'pick-target-label', type: 'symbol', source: 'pick-targets',
        layout: {
          'text-field': ['get', 'label'],
          'text-font': ['Noto Sans Regular'],
          'text-size': ['interpolate', ['linear'], ['zoom'], 10, 8, 14, 9, 16, 10],
          'text-allow-overlap': true,
          'text-ignore-placement': true
        },
        paint: MAP_LABEL_PAINT });
      bindStopClicks();
    }
    if (!map.getSource('install-pts')) {
      map.addSource('install-pts', { type: 'geojson', data: emptyFC() });
      map.addLayer({ id: 'install-pts', type: 'circle', source: 'install-pts',
        paint: {
          'circle-radius': DOT_R,
          'circle-color': [
            'case',
            ['==', ['get', 'source'], 'manual'], '#e65100',
            '#1565c0'
          ],
          'circle-stroke-color': '#fff',
          'circle-stroke-width': 1.5
        } });
      map.addLayer({ id: 'install-pts-label', type: 'symbol', source: 'install-pts',
        layout: Object.assign({}, DOT_LABEL_LAYOUT, {
          'text-field': ['to-string', ['get', 'seq']]
        }),
        paint: DOT_LABEL_PAINT });
      bindStopClicks();
    }
  }

  function applyMapMode(mode, lean) {
    var drive = mode === 'drive';
    lean = !!lean;
    _leanDrive = lean;
    setBasemapLabels(!drive && !lean);
    LEAN_BASE_LAYERS.forEach(function (id) { setLayerVis(id, !lean); });
    var segW = drive
      ? ['interpolate', ['linear'], ['zoom'], 10, 1.5, 14, 2.5]
      : ['interpolate', ['linear'], ['zoom'], 10, 2, 14, 4];
    var ptR = drive
      ? ['interpolate', ['linear'], ['zoom'], 10, 5, 14, 7]
      : DOT_R;
    var casingW = drive
      ? ['interpolate', ['linear'], ['zoom'], 10, 5, 14, 11]
      : ['interpolate', ['linear'], ['zoom'], 10, 5, 14, 12];
    var lineW = drive
      ? ['interpolate', ['linear'], ['zoom'], 10, 3, 14, 7]
      : ['interpolate', ['linear'], ['zoom'], 10, 3, 14, 7];
    if (map.getLayer('segments-line')) map.setPaintProperty('segments-line', 'line-width', segW);
    if (map.getLayer('site-begin')) map.setPaintProperty('site-begin', 'circle-radius', ptR);
    if (map.getLayer('site-end')) map.setPaintProperty('site-end', 'circle-radius', ptR);
    if (map.getLayer('route-casing')) map.setPaintProperty('route-casing', 'line-width', casingW);
    if (map.getLayer('route-line')) map.setPaintProperty('route-line', 'line-width', lineW);
  }

  function stopStatus(s) {
    if (s.installed) return 'installed';
    if (s.skipped) return 'skipped';
    if (s.picked_up) return 'picked_up';
    return 'pending';
  }

  function stopAnchor(s) {
    if (s.cross_lat != null && s.cross_lon != null) return [s.cross_lat, s.cross_lon];
    return [s.lat, s.lon];
  }

  function siteLetterFromIndex(i) {
    var n = i;
    var letters = '';
    while (true) {
      letters = String.fromCharCode(65 + (n % 26)) + letters;
      n = Math.floor(n / 26) - 1;
      if (n < 0) break;
    }
    return letters;
  }

  // Map badges use route sequence (drive order), not Excel site #.
  function stopSeqLabel(s, i, picking, pickIdx) {
    var seq = s.seq != null ? s.seq : (pickIdx[s.uid] || 0);
    if (picking && !seq) return '+';
    if (!seq) return String(i + 1);
    return String(seq);
  }

  function siteDotLabel(s, i, picking, pickLetters) {
    if (picking) {
      return (pickLetters && pickLetters[s.uid]) || siteLetterFromIndex(i);
    }
    if (s.seq != null) return String(s.seq);
    return String((i != null ? i : 0) + 1);
  }

  function siteIdLabel(s, i) {
    if (s.id != null && String(s.id).trim() !== '') return String(s.id);
    if (s.seq != null) return String(s.seq);
    return String((i != null ? i : 0) + 1);
  }

  var _siteToastTimer = null;
  function showSiteInfoToast(payload) {
    var el = document.getElementById('site-toast');
    if (!el || !lastState || !lastState.stops) return;
    var uid = payload, side = null, isInstall = false;
    if (String(payload).indexOf('|') >= 0) {
      var parts = String(payload).split('|');
      if (parts[0] === 'install') {
        isInstall = true;
        uid = parts[1];
      } else {
        uid = parts[0];
        side = parts[1];
      }
    }
    var stop = null, idx = -1;
    for (var i = 0; i < lastState.stops.length; i++) {
      if (lastState.stops[i].uid === uid) { stop = lastState.stops[i]; idx = i; break; }
    }
    if (!stop) return;
    var seq = stop.seq != null ? stop.seq : (idx + 1);
    var siteId = siteIdLabel(stop, idx);
    var street = String(stop.street || '').trim();
    if (!street || street.toLowerCase() === 'nan') street = '';
    var txt = isInstall
      ? ('Site ' + siteId + ' — GPS grab pin')
      : ('Stop ' + seq + ' · Site ' + siteId);
    if (street) txt += ' — ' + street;
    if (side === 'begin' || side === 'end') {
      txt += ' (' + (side === 'begin' ? 'Begin' : 'End') + ')';
    }
    el.textContent = txt;
    el.style.display = 'block';
    if (_siteToastTimer) clearTimeout(_siteToastTimer);
    _siteToastTimer = setTimeout(function () { el.style.display = 'none'; }, 6000);
  }

  function updatePickBanner(state) {
    var el = document.getElementById('pick-banner');
    if (!el) return;
    var picking = state.map_mode === 'pick';
    var manualGrab = state.map_mode === 'manual_grab';
    var msg = state.pick_prompt || '';
    document.body.classList.toggle('td-manual-grab', manualGrab);
    if ((picking || manualGrab) && msg) {
      var waiting = state.pick_waiting || '';
      el.textContent = waiting ? (msg + ' — ' + waiting) : msg;
      el.style.display = 'block';
    } else {
      document.body.classList.remove('td-manual-grab');
      el.style.display = 'none';
      el.textContent = '';
    }
  }

  function updateDriveBanner(state) {
    var el = document.getElementById('drive-banner');
    if (!el) return;
    var txt = state.drive_banner || '';
    if (state.driving && txt) {
      el.textContent = txt;
      el.style.display = 'block';
    } else {
      el.style.display = 'none';
      el.textContent = '';
    }
  }

  function resolveRouteLine(state) {
    if (!SHOW_TRACE_LINES) return null;
    var mode = state.map_mode || (state.driving ? 'drive' : 'plan');
    if (mode === 'pick' || mode === 'preview' || mode === 'manual_grab') {
      return null;
    }
    var nextLeg = state.next_leg || null;
    var legPoly = (nextLeg && nextLeg.polyline) || [];
    var tourPoly = (state.route && state.route.polyline) || [];
    var onRoads = !!(state.route && state.route.graph);
    if (state.show_guide && legPoly.length >= 2) {
      return { coords: legPoly, onRoads: true };
    }
    if (tourPoly.length >= 2) {
      return { coords: tourPoly, onRoads: onRoads };
    }
    if (legPoly.length >= 2) {
      return { coords: legPoly, onRoads: onRoads };
    }
    return null;
  }

  function paintRouteLayer(state) {
    if (map.getSource('route')) {
      map.getSource('route').setData(emptyFC());
      setLayerVis('route-casing', false);
      setLayerVis('route-line', false);
    }
  }

  function renderState(state) {
    lastState = state;
    window.__dbg.pushes++;
    window.__dbg.lastStops = (state.stops || []).length;
    if (!styleReady) { pendingState = state; return; }
    ensureSources();
    applyData(state);
  }

  function applyLeanDriveData(state) {
    if (homeMarker) { homeMarker.remove(); homeMarker = null; }
    applyMapMode('drive', true);
    paintRouteLayer(state);
    var empty = emptyFC();
    if (map.getSource('segments')) map.getSource('segments').setData(empty);
    if (map.getSource('site-pts')) map.getSource('site-pts').setData(empty);
    if (map.getSource('stop-markers')) map.getSource('stop-markers').setData(empty);
    if (map.getSource('pick-targets')) map.getSource('pick-targets').setData(empty);
    if (map.getSource('install-pts')) map.getSource('install-pts').setData(empty);
    setLayerVis('segments-line', false);
    setLayerVis('site-begin', false);
    setLayerVis('site-end', false);
    setLayerVis('site-begin-label', false);
    setLayerVis('site-end-label', false);
    setLayerVis('pick-target-circle', false);
    setLayerVis('pick-target-label', false);
    setLayerVis('stop-circle', false);
    setLayerVis('stop-label', false);
    setLayerVis('install-pts', false);
    setLayerVis('install-pts-label', false);
    updatePickBanner(state);
    updateDriveBanner(state);
    window.__dbg.applied++;
  }

  function applyData(state) {
    var lean = !!state.lean_drive;
    var homeKey = state.home ? state.home[0] + ',' + state.home[1] : '';
    if (lean) {
      applyLeanDriveData(state);
      return;
    }
    if (homeMarker) { homeMarker.remove(); homeMarker = null; }
    if (state.home) {
      var hel = document.createElement('div');
      hel.innerHTML =
        '<svg width="28" height="36" viewBox="0 0 28 36">' +
        '<path d="M14 0C7 0 2 6 2 13c0 9 12 23 12 23s12-14 12-23C26 6 21 0 14 0z" fill="#0f2744" stroke="#fff" stroke-width="1.5"/>' +
        '<circle cx="14" cy="13" r="5" fill="#fff"/></svg>';
      homeMarker = new maplibregl.Marker({ element: hel, anchor: 'bottom' })
        .setLngLat([state.home[1], state.home[0]]).addTo(map);
    }
    _lastHomeKey = homeKey;

    var mode = state.map_mode || (state.driving ? 'drive' : 'plan');
    applyMapMode(mode, false);

    var driving = !!state.driving;
    var picking = state.map_mode === 'pick';
    var showStops = state.show_badges !== false;
    var hiUid = state.highlight_uid || state.drive_target_uid;
    var pickOrder = state.pick_order || [];
    var pickIdx = {};
    pickOrder.forEach(function (uid, i) { pickIdx[uid] = i + 1; });
    var pickLetters = state.pick_letters || {};
    var segs = [], pts = [], stops = [], installs = [], pickTargets = [];
    var fanAnchors = {};
    function registerFanAnchor(lat, lon, applyFn) {
      if (lat == null || lon == null) return;
      var key = lat.toFixed(6) + ',' + lon.toFixed(6);
      if (!fanAnchors[key]) fanAnchors[key] = { lat: lat, lon: lon, applies: [] };
      fanAnchors[key].applies.push(applyFn);
    }
    (state.stops || []).forEach(function (s, i) {
      var bLat = s.begin_lat, bLon = s.begin_lon, eLat = s.end_lat, eLon = s.end_lon;
      if (bLat == null || bLon == null || eLat == null || eLon == null) return;
      var path = s.segment_path;
      var coords;
      if (path && path.length >= 2) {
        coords = path.map(function (p) { return [p[1], p[0]]; });
      } else {
        coords = [[bLon, bLat], [eLon, eLat]];
      }
      var dotLabel = siteDotLabel(s, i, picking, pickLetters);
      var alreadyPicked = picking && pickIdx[s.uid];
      segs.push({ type: 'Feature', properties: { seq: picking ? dotLabel : (s.seq || (i + 1)) },
                  geometry: { type: 'LineString', coordinates: coords } });
      if (!alreadyPicked) {
        var ptProps = { kind: 'begin', uid: s.uid, seq: dotLabel, site_id: siteIdLabel(s, i) };
        registerFanAnchor(bLat, bLon, function (la, lo) {
          pts.push(pt(la, lo, ptProps));
        });
        var endProps = Object.assign({}, ptProps, { kind: 'end' });
        registerFanAnchor(eLat, eLon, function (la, lo) {
          pts.push(pt(la, lo, endProps));
        });
        if (picking) {
          registerFanAnchor(bLat, bLon, function (la, lo) {
            pickTargets.push(pt(la, lo, { kind: 'begin', uid: s.uid, label: dotLabel }));
          });
          registerFanAnchor(eLat, eLon, function (la, lo) {
            pickTargets.push(pt(la, lo, { kind: 'end', uid: s.uid, label: dotLabel }));
          });
        }
      }
      if (s.field_lat != null && s.field_lon != null) {
        var fsrc = s.field_coord_source || s.field_source || 'gps';
        var hideForDrag = state.map_mode === 'manual_grab' &&
          state.current_uid && s.uid === state.current_uid && state.on_install;
        if (!hideForDrag) {
          var installSeq = picking ? dotLabel : stopSeqLabel(s, i, picking, pickIdx);
          registerFanAnchor(s.field_lat, s.field_lon, function (la, lo) {
            installs.push(pt(la, lo, {
              uid: s.uid,
              source: fsrc,
              seq: installSeq,
              site_id: siteIdLabel(s, i),
              kind: 'install'
            }));
          });
        }
      }
      if (showStops || (picking && pickIdx[s.uid])) {
        var anchor = stopAnchor(s);
        if (anchor[0] != null && anchor[1] != null) {
          var seq = picking ? String(pickIdx[s.uid] || '') : stopSeqLabel(s, i, picking, pickIdx);
          if (picking && !pickIdx[s.uid]) {
            /* no anchor badge until site is picked */
          } else {
            var badgeLabel = seq;
            var stopProps = {
              uid: s.uid,
              seq: badgeLabel,
              site_id: siteIdLabel(s, i),
              status: stopStatus(s),
              highlight: hiUid && s.uid === hiUid
            };
            registerFanAnchor(anchor[0], anchor[1], function (la, lo) {
              stops.push(pt(la, lo, stopProps));
            });
          }
        }
      }
    });
    var anchorList = Object.keys(fanAnchors).map(function (k) { return fanAnchors[k]; });
    spreadCollocated(anchorList, COLLOC_THRESHOLD_M, COLLOC_FAN_RADIUS_M);
    anchorList.forEach(function (anchor) {
      anchor.applies.forEach(function (fn) { fn(anchor.lat, anchor.lon); });
    });
    map.getSource('segments').setData({ type: 'FeatureCollection', features: segs });
    map.getSource('site-pts').setData({ type: 'FeatureCollection', features: pts });
    map.getSource('stop-markers').setData({ type: 'FeatureCollection', features: stops });
    if (map.getSource('pick-targets')) {
      map.getSource('pick-targets').setData({ type: 'FeatureCollection', features: pickTargets });
    }
    if (map.getSource('install-pts')) map.getSource('install-pts').setData({ type: 'FeatureCollection', features: installs });

    var hasSites = (state.stops || []).length > 0;
    paintRouteLayer(state);
    setLayerVis('segments-line', false);
    setLayerVis('site-begin', hasSites);
    setLayerVis('site-end', hasSites);
    setLayerVis('site-begin-label', hasSites);
    setLayerVis('site-end-label', hasSites);
    var showPickTargets = picking && pickTargets.length > 0;
    setLayerVis('pick-target-circle', showPickTargets);
    setLayerVis('pick-target-label', showPickTargets);
    setLayerVis('stop-circle', (showStops || picking) && stops.length > 0);
    setLayerVis('stop-label', (showStops || picking) && stops.length > 0);
    setLayerVis('install-pts', installs.length > 0);
    setLayerVis('install-pts-label', installs.length > 0);
    syncFieldPinFromState(state);
    updatePickBanner(state);
    updateDriveBanner(state);

    window.__dbg.applied++;
    window.__dbg.segCount = segs.length;
    if (state.fit) fitToData(state);
  }

  function fitToData(state) {
    var b = new maplibregl.LngLatBounds();
    var any = false;
    (state.stops || []).forEach(function (s) {
      if (s.begin_lat != null) { b.extend([s.begin_lon, s.begin_lat]); any = true; }
      if (s.end_lat != null) { b.extend([s.end_lon, s.end_lat]); any = true; }
      var a = stopAnchor(s);
      if (a[0] != null) { b.extend([a[1], a[0]]); any = true; }
    });
    var nextLeg = state.next_leg || null;
    var legPoly = (nextLeg && nextLeg.polyline) || [];
    legPoly.forEach(function (p) { b.extend([p[1], p[0]]); any = true; });
    if (!legPoly.length) {
      var poly = (state.route && state.route.polyline) || [];
      poly.forEach(function (p) { b.extend([p[1], p[0]]); any = true; });
    }
    if (state.home) { b.extend([state.home[1], state.home[0]]); any = true; }
    if (!any || b.isEmpty()) return;
    requestAnimationFrame(function () {
      map.resize();
      map.fitBounds(b, { padding: 80, duration: 500, maxZoom: FOLLOW_ZOOM, linear: false });
    });
  }
  window.__fit = function () { if (lastState) fitToData(lastState); };

  function renderGps(g) {
    if (!g) return;
    if (!_leanDrive) updateCompass(g);
    if (g.lat == null) return;
    lastGps = g;
    if (!gpsMarker) {
      var el = document.createElement('div');
      el.style.width = '12px';
      el.style.height = '12px';
      el.style.borderRadius = '50%';
      el.style.background = '#43a047';
      el.style.border = '2px solid #fff';
      el.style.boxShadow = '0 0 2px rgba(0,0,0,0.35)';
      gpsMarker = new maplibregl.Marker({ element: el, anchor: 'center' })
        .setLngLat([g.lon, g.lat]).addTo(map);
    } else {
      gpsMarker.setLngLat([g.lon, g.lat]);
    }
    // D7: recenter only when Follow was explicitly turned on — not every GPS tick.
    if (follow && recenterPending) recenterOnGps(g, true);
  }

  function renderNav() { /* turn-by-turn banner removed — map + status bar only */ }

  map.on('click', function (e) {
    if (lastState && lastState.map_mode === 'manual_grab') {
      var siteId = '';
      if (lastState.current_uid && lastState.stops) {
        for (var mi = 0; mi < lastState.stops.length; mi++) {
          if (lastState.stops[mi].uid === lastState.current_uid) {
            siteId = siteIdLabel(lastState.stops[mi], mi);
            break;
          }
        }
      }
      placeFieldPin(e.lngLat.lat, e.lngLat.lng, {
        source: 'manual',
        draggable: true,
        uid: lastState.current_uid || '',
        siteId: siteId
      });
      fireMapClick(e.lngLat.lat, e.lngLat.lng);
      return;
    }
    var payload = pickLayerAtPoint(e.point);
    if (!payload && lastState && lastState.map_mode === 'pick') {
      payload = nearestPickAt(e.lngLat.lat, e.lngLat.lng);
    }
    if (payload) {
      showSiteInfoToast(payload);
      fireStopClick(payload);
      return;
    }
    fireMapClick(e.lngLat.lat, e.lngLat.lng);
  });

  function safe(fn, tag) {
    return function (j) {
      try { fn(JSON.parse(j)); }
      catch (e) { window.__jsErrors.push(tag + ': ' + e); }
    };
  }

  function initBridge(tries) {
    tries = tries || 0;
    if (typeof QWebChannel === 'undefined' || typeof qt === 'undefined' || !qt.webChannelTransport) {
      if (tries > 200) { window.__jsErrors.push('bridge: qt.webChannelTransport never appeared'); return; }
      return setTimeout(function () { initBridge(tries + 1); }, 50);
    }
    try {
      new QWebChannel(qt.webChannelTransport, function (channel) {
        bridge = channel.objects.bridge;
        // State / GPS / nav / flyTo / follow all arrive Python->JS via the
        // window.__td* hooks below (runJavaScript), NOT QWebChannel signals.
        // The bridge object exists only for the JS->Python direction
        // (onReady / onMapClick / onStopClick / onFollowToggled slots). Do not
        // connect to signals it doesn't define — that throws and aborts init,
        // which used to leave clicks stranded on slower machines.
        window.__bridgeReady = true;
        if (bridge && typeof bridge.onReady === 'function') {
          bridge.onReady();
        }
      });
    } catch (e) {
      window.__jsErrors.push('bridge init: ' + e);
    }
  }
  initBridge();

  // Test seams: exercise the exact JS->Python click paths headlessly.
  window.__fireStopClick = function (payload) { fireStopClick(payload); };
  window.__fireMapClick = function (lat, lon) { fireMapClick(lat, lon); };

  window.__tdPushState = renderState;
  window.__tdPushGps = renderGps;
  window.__tdPushNav = renderNav;
  window.__tdFlyTo = function (lat, lon, zoom) {
    var z = zoom != null ? Math.min(MAX_ZOOM, zoom) : map.getZoom();
    map.flyTo({ center: [lon, lat], zoom: z, duration: 600 });
  };
  window.__tdSetFollow = function (on) { setFollow(!!on, true); };
  window.__tdSetFieldPin = function (lat, lon, source, draggable) {
    var uid = '';
    var siteId = '';
    if (lastState && lastState.current_uid) {
      uid = lastState.current_uid;
      (lastState.stops || []).forEach(function (s, i) {
        if (s.uid === uid) siteId = siteIdLabel(s, i);
      });
    }
    placeFieldPin(lat, lon, {
      source: source || 'gps',
      draggable: !!draggable,
      uid: uid,
      siteId: siteId
    });
  };
  window.__tdClearFieldPin = function () { clearFieldPinMarker(); };
  window.__tdConfirmDropPin = function () {
    if (!fieldPinMarker) return null;
    return { lat: fieldPinMarker._tdLat, lon: fieldPinMarker._tdLon };
  };
  window.__tdFrameNextSite = frameNextSite;
  window.__spreadCollocated = spreadCollocated;
  window.__tdZoomToSite = function (lat, lon, zoom) {
    var z = zoom != null ? Math.min(MAX_ZOOM, zoom) : SITE_CLICK_ZOOM;
    map.flyTo({ center: [lon, lat], zoom: z, duration: 550 });
  };
  window.__tdSetDriveLeg = function (coords, active) {
    ensureSources();
    if (!lastState) return;
    lastState.next_leg = null;
    lastState.show_guide = false;
    if (styleReady) paintRouteLayer(lastState);
  };

  window.__tdSetDriveHighlight = function (uid) {
    if (!lastState) return;
    lastState.highlight_uid = uid || null;
    lastState.drive_target_uid = uid || null;
    if (styleReady) applyData(lastState);
  };

  window.__tdRefresh = function () {
    if (window._map) window._map.resize();
    if (lastState) {
      if (styleReady) applyData(lastState);
      else pendingState = lastState;
      fitToData(lastState);
    }
  };
  window.__jsInject = true;
})();
