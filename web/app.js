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
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');

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
  var badgeMarkers = [];
  var homeMarker = null;
  var gpsMarker = null;
  var lastState = null;

  var followBtn = document.getElementById('follow-btn');
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
    followBtn.className = on ? '' : 'off';
  }
  followBtn.addEventListener('click', function () { setFollow(!follow); });

  function emptyFC() { return { type: 'FeatureCollection', features: [] }; }
  function pt(lat, lon, props) {
    return { type: 'Feature', properties: props || {}, geometry: { type: 'Point', coordinates: [lon, lat] } };
  }
  function line(coords) {
    return { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } };
  }
  function routeLineFC(coords) {
    return { type: 'FeatureCollection', features: [line(coords.map(function (p) { return [p[1], p[0]]; }))] };
  }

  function setLayerVis(id, on) {
    if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
  }

  function ensureSources() {
    if (!map.getSource('route')) {
      map.addSource('route', { type: 'geojson', data: emptyFC() });
      map.addLayer({ id: 'route-glow', type: 'line', source: 'route',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': '#81d4fa',
          'line-width': ['interpolate', ['linear'], ['zoom'], 10, 4, 14, 10],
          'line-opacity': 0.45,
          'line-blur': 0.5
        } });
      map.addLayer({ id: 'route-line', type: 'line', source: 'route',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': '#29b6f6',
          'line-width': ['interpolate', ['linear'], ['zoom'], 10, 2, 14, 5],
          'line-opacity': 0.9
        } });
    }
    if (!map.getSource('segments')) {
      map.addSource('segments', { type: 'geojson', data: emptyFC() });
      map.addLayer({ id: 'segments-line', type: 'line', source: 'segments',
        layout: { 'line-cap': 'round' },
        paint: {
          'line-color': [
            'case',
            ['get', 'done'], '#2e7d32',
            ['get', 'skipped'], '#c62828',
            ['==', ['get', 'zone'], 1], '#e65100',
            ['==', ['get', 'zone'], 2], '#1565c0',
            ['==', ['get', 'zone'], 3], '#2e7d32',
            ['==', ['get', 'zone'], 4], '#6a1b9a',
            ['==', ['get', 'zone'], 5], '#c62828',
            ['==', ['get', 'zone'], 6], '#00838f',
            ['==', ['get', 'zone'], 7], '#f9a825',
            ['==', ['get', 'zone'], 8], '#5d4037',
            '#7b1fa2'
          ],
          'line-width': ['interpolate', ['linear'], ['zoom'], 10, 2, 14, 4],
          'line-opacity': 0.85
        } });
    }
    if (!map.getSource('site-pts')) {
      map.addSource('site-pts', { type: 'geojson', data: emptyFC() });
      map.addLayer({ id: 'site-begin', type: 'circle', source: 'site-pts',
        filter: ['==', ['get', 'kind'], 'begin'],
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 3, 14, 5],
          'circle-color': '#1565ff',
          'circle-stroke-color': '#fff',
          'circle-stroke-width': 1.2
        } });
      map.addLayer({ id: 'site-end', type: 'circle', source: 'site-pts',
        filter: ['==', ['get', 'kind'], 'end'],
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 3, 14, 5],
          'circle-color': '#e53935',
          'circle-stroke-color': '#fff',
          'circle-stroke-width': 1.2
        } });
    }
    if (!map.getSource('cross-pts')) {
      map.addSource('cross-pts', { type: 'geojson', data: emptyFC() });
      map.addLayer({ id: 'cross-pts', type: 'circle', source: 'cross-pts',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 2.5, 14, 4],
          'circle-color': '#00acc1',
          'circle-stroke-color': '#fff',
          'circle-stroke-width': 1
        } });
    }
    if (!map.getSource('install-pts')) {
      map.addSource('install-pts', { type: 'geojson', data: emptyFC() });
      map.addLayer({ id: 'install-pts', type: 'circle', source: 'install-pts',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 3, 14, 5],
          'circle-color': '#2e7d32',
          'circle-stroke-color': '#fff',
          'circle-stroke-width': 1.2
        } });
    }
    if (!map.getSource('trail')) {
      map.addSource('trail', { type: 'geojson', data: emptyFC() });
      map.addLayer({ id: 'trail-line', type: 'line', source: 'trail',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#e91e63', 'line-width': 3, 'line-opacity': 0.75 } });
    }
  }

  function applyMapMode(mode) {
    var drive = mode === 'drive';
    var segW = drive
      ? ['interpolate', ['linear'], ['zoom'], 10, 1.5, 14, 2.5]
      : ['interpolate', ['linear'], ['zoom'], 10, 2, 14, 4];
    var ptR = drive
      ? ['interpolate', ['linear'], ['zoom'], 10, 2.5, 14, 4]
      : ['interpolate', ['linear'], ['zoom'], 10, 3, 14, 5];
    var routeW = drive
      ? ['interpolate', ['linear'], ['zoom'], 10, 2, 14, 4]
      : ['interpolate', ['linear'], ['zoom'], 10, 2, 14, 5];
    var glowW = drive
      ? ['interpolate', ['linear'], ['zoom'], 10, 3, 14, 7]
      : ['interpolate', ['linear'], ['zoom'], 10, 4, 14, 10];
    if (map.getLayer('segments-line')) map.setPaintProperty('segments-line', 'line-width', segW);
    if (map.getLayer('site-begin')) map.setPaintProperty('site-begin', 'circle-radius', ptR);
    if (map.getLayer('site-end')) map.setPaintProperty('site-end', 'circle-radius', ptR);
    if (map.getLayer('route-line')) map.setPaintProperty('route-line', 'line-width', routeW);
    if (map.getLayer('route-glow')) map.setPaintProperty('route-glow', 'line-width', glowW);
  }

  function makeBadge(label, status, highlight) {
    var color = status === 'installed' ? '#2e7d32'
              : status === 'skipped' ? '#c62828'
              : status === 'picked_up' ? '#1565c0' : '#f39c12';
    var sz = highlight ? 22 : 17;
    var el = document.createElement('div');
    el.style.cssText =
      'width:' + sz + 'px;height:' + sz + 'px;border-radius:50%;background:' + color +
      ';color:#fff;font:700 ' + (highlight ? 12 : 10) + 'px system-ui,sans-serif;display:flex;' +
      'align-items:center;justify-content:center;border:2px solid #fff;' +
      'box-shadow:0 1px 4px rgba(0,0,0,.4);cursor:pointer;z-index:' + (highlight ? 5 : 2) + ';';
    el.textContent = label;
    return el;
  }

  function clearBadges() { badgeMarkers.forEach(function (m) { m.remove(); }); badgeMarkers = []; }

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
      hel.style.cssText = 'width:12px;height:12px;border-radius:2px;background:#1976d2;border:1.5px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.35);';
      homeMarker = new maplibregl.Marker({ element: hel }).setLngLat([state.home[1], state.home[0]]).addTo(map);
    }

    var mode = state.map_mode || (state.driving ? 'drive' : 'plan');
    applyMapMode(mode);

    var driving = !!state.driving;
    var showBadges = state.show_badges !== false;
    var targetUid = state.drive_target_uid;
    var segs = [], pts = [], crosses = [], installs = [];
    clearBadges();
    (state.stops || []).forEach(function (s, i) {
      var bLat = s.begin_lat, bLon = s.begin_lon, eLat = s.end_lat, eLon = s.end_lon;
      if (bLat == null || bLon == null || eLat == null || eLon == null) return;
      var done = !!s.installed, skipped = !!s.skipped;
      var z = s.route_zone != null ? Number(s.route_zone) : 0;
      segs.push({ type: 'Feature', properties: { done: done, skipped: skipped, zone: z },
                  geometry: { type: 'LineString', coordinates: [[bLon, bLat], [eLon, eLat]] } });
      pts.push(pt(bLat, bLon, { kind: 'begin', n: i + 1 }));
      pts.push(pt(eLat, eLon, { kind: 'end', n: i + 1 }));
      if (!driving && s.field_lat != null && s.field_lon != null) {
        installs.push(pt(s.field_lat, s.field_lon, { uid: s.uid }));
      }
      if (s.cross_lat != null && s.cross_lon != null && state.show_crossings !== false) {
        crosses.push(pt(s.cross_lat, s.cross_lon, { uid: s.uid, n: i + 1 }));
      }
      if (showBadges) {
        var status = done ? 'installed' : skipped ? 'skipped' : s.picked_up ? 'picked_up' : 'pending';
        var isTarget = driving && s.uid === targetUid;
        var badgeTxt = String(i + 1);
        if (s.route_zone != null && !driving) badgeTxt += ' Z' + s.route_zone;
        var el = makeBadge(badgeTxt, status, isTarget);
        el.addEventListener('click', function (ev) {
          ev.stopPropagation();
          window.location.href = 'tdstop://' + encodeURIComponent(s.uid);
        });
        var mLat = (s.cross_lat != null) ? s.cross_lat : s.lat;
        var mLon = (s.cross_lon != null) ? s.cross_lon : s.lon;
        if (mLat != null && mLon != null) {
          badgeMarkers.push(new maplibregl.Marker({ element: el, anchor: 'center' })
            .setLngLat([mLon, mLat]).addTo(map));
        }
      }
    });
    map.getSource('segments').setData({ type: 'FeatureCollection', features: segs });
    map.getSource('site-pts').setData({ type: 'FeatureCollection', features: pts });
    if (map.getSource('cross-pts')) map.getSource('cross-pts').setData({ type: 'FeatureCollection', features: crosses });
    if (map.getSource('install-pts')) map.getSource('install-pts').setData({ type: 'FeatureCollection', features: installs });

    if (!driving) {
      var poly = (state.route && state.route.polyline) || [];
      map.getSource('route').setData(poly.length ? routeLineFC(poly) : emptyFC());
    }

    var showGuide = state.show_guide !== false;
    var showSegs = state.show_segments !== false;
    setLayerVis('route-glow', showGuide);
    setLayerVis('route-line', showGuide);
    setLayerVis('segments-line', showSegs);
    setLayerVis('site-begin', true);
    setLayerVis('site-end', true);
    setLayerVis('cross-pts', !!(state.show_crossings && crosses.length && !driving));
    setLayerVis('install-pts', installs.length > 0);

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
    });
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
    if (g.trail && map.getSource('trail')) {
      map.getSource('trail').setData(g.trail.length ? routeLineFC(g.trail) : emptyFC());
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
  window.__tdSetDriveLeg = function (coords, active) {
    ensureSources();
    applyMapMode('drive');
    var on = active && coords && coords.length >= 2;
    setLayerVis('route-glow', on);
    setLayerVis('route-line', on);
    map.getSource('route').setData(on ? routeLineFC(coords) : emptyFC());
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
