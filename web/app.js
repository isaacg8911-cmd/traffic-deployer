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

  var protocol = new pmtiles.Protocol();
  maplibregl.addProtocol('pmtiles', protocol.tile);

  var origin = window.location.origin;
  var pmtilesUrl = origin + '/data/california.pmtiles';
  var MAX_ZOOM = 15;
  var FOLLOW_ZOOM = 13;
  var FOLLOW_ZOOM_MIN = 8;

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
  var follow = true;
  var homeMarker = null;
  var gpsMarker = null;
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

  function setFollow(on) {
    follow = on;
    followBtn.textContent = on ? 'Following' : 'Follow Me';
    followBtn.className = 'hudBtn primary' + (on ? '' : ' off');
  }
  followBtn.addEventListener('click', function () { setFollow(!follow); });
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

  var PICK_CLICK_LAYERS = [
    'pick-target-circle', 'pick-target-label',
    'stop-circle', 'stop-label',
    'site-begin', 'site-end', 'site-begin-label', 'site-end-label'
  ];

  function pickLayerAtPoint(point) {
    var layers = PICK_CLICK_LAYERS.filter(function (id) { return map.getLayer(id); });
    if (!layers.length) return null;
    var features = map.queryRenderedFeatures(point, { layers: layers });
    for (var i = 0; i < features.length; i++) {
      var props = features[i].properties || {};
      var uid = props.uid;
      if (!uid) continue;
      var kind = props.kind;
      if (kind === 'begin' || kind === 'end') {
        return String(uid) + '|' + kind;
      }
      return String(uid);
    }
    return null;
  }

  function bindStopClicks() {
    if (map._stopClickBound) return;
    map._stopClickBound = true;
    function onPick(e) {
      var f = e.features && e.features[0];
      if (f && f.properties && f.properties.uid) {
        e.preventDefault();
        var kind = f.properties.kind;
        var payload = f.properties.uid;
        if (kind === 'begin' || kind === 'end') {
          payload = payload + '|' + kind;
        }
        fireStopClick(payload);
      }
    }
    map.on('click', 'stop-circle', onPick);
    map.on('click', 'site-begin', onPick);
    map.on('click', 'site-end', onPick);
    map.on('click', 'site-begin-label', onPick);
    map.on('click', 'site-end-label', onPick);
    map.on('click', 'pick-target-circle', onPick);
    map.on('click', 'pick-target-label', onPick);
    ['stop-circle', 'site-begin', 'site-end', 'site-begin-label', 'site-end-label',
      'pick-target-circle', 'pick-target-label'].forEach(function (id) {
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
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 5, 14, 8, 15, 9],
          'circle-color': '#1565c0',
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2,
          'circle-opacity': 0.95
        } });
      map.addLayer({ id: 'site-end', type: 'circle', source: 'site-pts',
        filter: ['==', ['get', 'kind'], 'end'],
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 5, 14, 8, 15, 9],
          'circle-color': '#c62828',
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2,
          'circle-opacity': 0.95
        } });
      var siteLabelLayout = {
        'text-field': ['get', 'seq'],
        'text-font': ['Noto Sans Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 10, 10, 14, 13, 15, 14],
        'text-allow-overlap': true,
        'text-ignore-placement': true
      };
      var siteLabelPaint = {
        'text-color': '#ffffff',
        'text-halo-color': 'rgba(15,39,68,0.45)',
        'text-halo-width': 1.2
      };
      map.addLayer({ id: 'site-begin-label', type: 'symbol', source: 'site-pts',
        filter: ['==', ['get', 'kind'], 'begin'],
        layout: siteLabelLayout,
        paint: siteLabelPaint });
      map.addLayer({ id: 'site-end-label', type: 'symbol', source: 'site-pts',
        filter: ['==', ['get', 'kind'], 'end'],
        layout: siteLabelLayout,
        paint: siteLabelPaint });
    }
    if (!map.getSource('stop-markers')) {
      map.addSource('stop-markers', { type: 'geojson', data: emptyFC() });
      map.addLayer({ id: 'stop-circle', type: 'circle', source: 'stop-markers',
        paint: {
          'circle-radius': [
            'case', ['boolean', ['get', 'highlight'], false],
            ['interpolate', ['linear'], ['zoom'], 10, 18, 14, 24, 15, 28],
            ['interpolate', ['linear'], ['zoom'], 10, 14, 14, 20, 15, 22]
          ],
          'circle-color': STOP_STATUS_COLOR,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 3,
          'circle-opacity': 0.96
        } });
      map.addLayer({ id: 'stop-label', type: 'symbol', source: 'stop-markers',
        layout: {
          'text-field': ['to-string', ['get', 'seq']],
          'text-font': ['Noto Sans Regular'],
          'text-size': [
            'case', ['boolean', ['get', 'highlight'], false],
            ['interpolate', ['linear'], ['zoom'], 10, 13, 14, 17, 15, 20],
            ['interpolate', ['linear'], ['zoom'], 10, 11, 14, 15, 15, 17]
          ],
          'text-allow-overlap': true,
          'text-ignore-placement': true
        },
        paint: {
          'text-color': '#ffffff',
          'text-halo-color': 'rgba(15,39,68,0.35)',
          'text-halo-width': 1.2
        } });
      bindStopClicks();
    }
    if (!map.getSource('pick-targets')) {
      map.addSource('pick-targets', { type: 'geojson', data: emptyFC() });
      map.addLayer({ id: 'pick-target-circle', type: 'circle', source: 'pick-targets',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 16, 14, 22, 15, 26],
          'circle-color': '#f57c00',
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 3,
          'circle-opacity': 0.96
        } });
      map.addLayer({ id: 'pick-target-label', type: 'symbol', source: 'pick-targets',
        layout: {
          'text-field': ['get', 'label'],
          'text-font': ['Noto Sans Regular'],
          'text-size': ['interpolate', ['linear'], ['zoom'], 10, 12, 14, 15, 15, 16],
          'text-allow-overlap': true,
          'text-ignore-placement': true
        },
        paint: {
          'text-color': '#ffffff',
          'text-halo-color': 'rgba(15,39,68,0.45)',
          'text-halo-width': 1.2
        } });
      bindStopClicks();
    }
    if (!map.getSource('install-pts')) {
      map.addSource('install-pts', { type: 'geojson', data: emptyFC() });
      map.addLayer({ id: 'install-pts', type: 'circle', source: 'install-pts',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 4, 14, 6],
          'circle-color': '#43a047',
          'circle-stroke-color': '#fff',
          'circle-stroke-width': 2
        } });
    }
  }

  function applyMapMode(mode, lean) {
    var drive = mode === 'drive';
    var pick = mode === 'pick';
    lean = !!lean;
    _leanDrive = lean;
    setBasemapLabels(!drive && !lean);
    LEAN_BASE_LAYERS.forEach(function (id) { setLayerVis(id, !lean); });
    var segW = drive
      ? ['interpolate', ['linear'], ['zoom'], 10, 1.5, 14, 2.5]
      : ['interpolate', ['linear'], ['zoom'], 10, 2, 14, 4];
    var ptR = drive
      ? ['interpolate', ['linear'], ['zoom'], 10, 2.5, 14, 4]
      : pick
        ? ['interpolate', ['linear'], ['zoom'], 10, 9, 14, 14, 15, 16]
        : ['interpolate', ['linear'], ['zoom'], 10, 5, 14, 8, 15, 9];
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
    return stopSeqLabel(s, i, false, {});
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
    var nextLeg = state.next_leg || null;
    var legPoly = (nextLeg && nextLeg.polyline) || [];
    var showNextLeg = !!state.show_guide && legPoly.length >= 2;
    if (map.getSource('route')) {
      map.getSource('route').setData(
        showNextLeg ? routeLineFC(legPoly, true) : emptyFC());
      setLayerVis('route-casing', false);
      setLayerVis('route-line', showNextLeg);
    }
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
    updatePickBanner(state);
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
        pts.push(pt(bLat, bLon, { kind: 'begin', uid: s.uid, seq: dotLabel }));
        pts.push(pt(eLat, eLon, { kind: 'end', uid: s.uid, seq: dotLabel }));
      }
      if (!driving && s.field_lat != null && s.field_lon != null) {
        installs.push(pt(s.field_lat, s.field_lon, { uid: s.uid }));
      }
      if (showStops || (picking && pickIdx[s.uid])) {
        var anchor = stopAnchor(s);
        if (anchor[0] != null && anchor[1] != null) {
          var seq = picking ? String(pickIdx[s.uid] || '') : stopSeqLabel(s, i, picking, pickIdx);
          if (picking && !pickIdx[s.uid]) {
            /* no anchor badge until site is picked */
          } else {
            stops.push(pt(anchor[0], anchor[1], {
              uid: s.uid,
              seq: seq,
              status: stopStatus(s),
              highlight: hiUid && s.uid === hiUid
            }));
          }
        }
      }
    });
    map.getSource('segments').setData({ type: 'FeatureCollection', features: segs });
    map.getSource('site-pts').setData({ type: 'FeatureCollection', features: pts });
    map.getSource('stop-markers').setData({ type: 'FeatureCollection', features: stops });
    if (map.getSource('pick-targets')) {
      map.getSource('pick-targets').setData({ type: 'FeatureCollection', features: pickTargets });
    }
    if (map.getSource('install-pts')) map.getSource('install-pts').setData({ type: 'FeatureCollection', features: installs });

    var showGuide = !!state.show_guide;
    var showSegs = state.show_segments !== false && !driving;
    var hasSites = (state.stops || []).length > 0;
    var nextLeg = state.next_leg || null;
    var legPoly = (nextLeg && nextLeg.polyline) || [];
    var showNextLeg = showGuide && legPoly.length >= 2;
    if (map.getSource('route')) {
      map.getSource('route').setData(
        showNextLeg ? routeLineFC(legPoly, true) : emptyFC());
      setLayerVis('route-casing', showNextLeg);
      setLayerVis('route-line', showNextLeg);
    }
    setLayerVis('segments-line', showSegs);
    setLayerVis('site-begin', hasSites);
    setLayerVis('site-end', hasSites);
    setLayerVis('site-begin-label', hasSites);
    setLayerVis('site-end-label', hasSites);
    setLayerVis('pick-target-circle', false);
    setLayerVis('pick-target-label', false);
    setLayerVis('stop-circle', (showStops || picking) && stops.length > 0);
    setLayerVis('stop-label', (showStops || picking) && stops.length > 0);
    setLayerVis('install-pts', installs.length > 0);
    updatePickBanner(state);

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
    if (follow) {
      map.jumpTo({ center: [g.lon, g.lat], zoom: map.getZoom() });
    }
  }

  function renderNav() { /* turn-by-turn banner removed — map + status bar only */ }

  map.on('click', function (e) {
    var payload = pickLayerAtPoint(e.point);
    if (payload) {
      fireStopClick(payload);
      return;
    }
    if (bridge) bridge.onMapClick(e.lngLat.lat, e.lngLat.lng);
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
        bridge.pushState.connect(safe(renderState, 'pushState'));
        bridge.pushGps.connect(safe(renderGps, 'pushGps'));
        bridge.pushNav.connect(safe(renderNav, 'pushNav'));
        bridge.flyTo.connect(function (lat, lon, zoom) {
          map.flyTo({ center: [lon, lat], zoom: zoom || map.getZoom(), duration: 800 });
        });
        bridge.setFollowSignal.connect(function (on) { setFollow(!!on); });
        window.__bridgeReady = true;
        bridge.onReady();
      });
    } catch (e) {
      window.__jsErrors.push('bridge init: ' + e);
    }
  }
  initBridge();

  window.__tdPushState = renderState;
  window.__tdPushGps = renderGps;
  window.__tdPushNav = renderNav;
  window.__tdFlyTo = function (lat, lon, zoom) {
    var z = zoom != null ? Math.min(MAX_ZOOM, zoom) : map.getZoom();
    map.flyTo({ center: [lon, lat], zoom: z, duration: 600 });
  };
  window.__tdSetFollow = setFollow;
  window.__tdFrameNextSite = frameNextSite;
  window.__tdSetDriveLeg = function (coords, active) {
    ensureSources();
    if (!lastState) return;
    var on = active && coords && coords.length >= 2;
    lastState.next_leg = on ? { polyline: coords } : null;
    lastState.show_guide = on;
    if (styleReady) applyData(lastState);
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
