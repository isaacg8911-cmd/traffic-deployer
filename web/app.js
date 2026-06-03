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

  var map = new maplibregl.Map({
    container: 'map',
    style: buildStyle(pmtilesUrl, origin),
    center: [-117.9431, 33.7715],
    zoom: 11,
    maxZoom: MAX_ZOOM,
    attributionControl: { compact: true },
    fadeDuration: 0,
    refreshExpiredTiles: false
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

  var followBtn = document.getElementById('follow-btn');
  var zoomInBtn = document.getElementById('zoom-in');
  var zoomOutBtn = document.getElementById('zoom-out');
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
      map.zoomTo(Math.max(map.getZoom() - 1, 3), { duration: 200 });
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

  var STOP_STATUS_COLOR = [
    'case',
    ['==', ['get', 'status'], 'installed'], '#1b5e20',
    ['==', ['get', 'status'], 'skipped'], '#b71c1c',
    ['==', ['get', 'status'], 'picked_up'], '#0d47a1',
    '#c45f14'
  ];

  function fireStopClick(uid) {
    if (uid) window.location.href = 'tdstop://' + encodeURIComponent(uid);
  }

  function bindStopClicks() {
    if (map._stopClickBound) return;
    map._stopClickBound = true;
    function onPick(e) {
      var f = e.features && e.features[0];
      if (f && f.properties && f.properties.uid) {
        e.preventDefault();
        fireStopClick(f.properties.uid);
      }
    }
    map.on('click', 'stop-circle', onPick);
    map.on('click', 'site-begin', onPick);
    map.on('click', 'site-end', onPick);
    map.on('click', 'site-begin-label', onPick);
    map.on('click', 'site-end-label', onPick);
    ['stop-circle', 'site-begin', 'site-end', 'site-begin-label', 'site-end-label'].forEach(function (id) {
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
          'line-opacity': 0.88
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

  function applyMapMode() { /* route/trace layers removed */ }

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
    var msg = state.pick_prompt || '';
    if (picking && msg) {
      el.textContent = msg;
      el.style.display = 'block';
    } else {
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

  function applyData(state) {
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

    var mode = state.map_mode || (state.driving ? 'drive' : 'plan');
    applyMapMode(mode);

    var driving = !!state.driving;
    var picking = state.map_mode === 'pick';
    var showStops = state.show_badges !== false;
    var hiUid = state.highlight_uid || state.drive_target_uid;
    var pickOrder = state.pick_order || [];
    var pickIdx = {};
    pickOrder.forEach(function (uid, i) { pickIdx[uid] = i + 1; });
    var pickLetters = state.pick_letters || {};
    var segs = [], pts = [], stops = [], installs = [];
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
      segs.push({ type: 'Feature', properties: { seq: picking ? dotLabel : (s.seq || (i + 1)) },
                  geometry: { type: 'LineString', coordinates: coords } });
      pts.push(pt(bLat, bLon, { kind: 'begin', uid: s.uid, seq: dotLabel }));
      pts.push(pt(eLat, eLon, { kind: 'end', uid: s.uid, seq: dotLabel }));
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
    if (map.getSource('install-pts')) map.getSource('install-pts').setData({ type: 'FeatureCollection', features: installs });
    if (map.getSource('route')) map.getSource('route').setData(emptyFC());

    var showSegs = state.show_segments !== false;
    setLayerVis('route-casing', false);
    setLayerVis('route-line', false);
    setLayerVis('segments-line', showSegs);
    setLayerVis('site-begin', showSegs || picking);
    setLayerVis('site-end', showSegs || picking);
    setLayerVis('site-begin-label', showSegs || picking);
    setLayerVis('site-end-label', showSegs || picking);
    setLayerVis('stop-circle', showStops && stops.length > 0);
    setLayerVis('stop-label', showStops && stops.length > 0);
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
    var poly = (state.route && state.route.polyline) || [];
    poly.forEach(function (p) { b.extend([p[1], p[0]]); any = true; });
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
    updateCompass(g);
    if (g.lat == null) return;
    if (!gpsMarker) {
      var el = document.createElement('div');
      el.innerHTML =
        '<svg width="22" height="22" viewBox="0 0 30 30">' +
        '<circle cx="15" cy="15" r="7" fill="#1e88e5" stroke="#fff" stroke-width="2.5"/>' +
        '<polygon points="15,2 19,11 11,11" fill="#1e88e5" stroke="#fff" stroke-width="1"/></svg>';
      gpsMarker = new maplibregl.Marker({ element: el }).setLngLat([g.lon, g.lat]).addTo(map);
    } else {
      gpsMarker.setLngLat([g.lon, g.lat]);
    }
    if (g.heading != null) {
      var svg = gpsMarker.getElement().querySelector('svg');
      if (svg) svg.style.transform = 'rotate(' + g.heading + 'deg)';
    }
    if (follow) {
      map.easeTo({
        center: [g.lon, g.lat],
        duration: 320,
        zoom: Math.min(MAX_ZOOM, Math.max(map.getZoom(), FOLLOW_ZOOM))
      });
    }
  }

  function renderNav() { /* turn-by-turn banner removed — map + status bar only */ }

  map.on('click', function (e) { if (bridge) bridge.onMapClick(e.lngLat.lat, e.lngLat.lng); });

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
  window.__tdSetDriveLeg = function () { /* blue drive trace removed */ };

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
