/*
 * Offline California basemap — Protomaps v4 light palette (default OSM colors).
 * Street names from tile "name" + local Noto Sans glyphs (setup_maps.py).
 * Buildings + addr_housenumber at z15+ (re-run setup_maps.py for z16 tiles).
 */
function buildStyle(pmtilesUrl, baseUrl) {
  var root = baseUrl || '';
  var c = {
    earth: '#f4f3ee',
    water: '#a9d6f5',
    land: '#eceae2',
    building: '#ddd9d0',
    buildingLine: '#b8b4ac',
    road: '#c9c5bb',
    major: '#b0aaa0',
    hwy: '#f4a259',
    hwyCase: '#ffffff',
    label: '#3d3a36',
    addr: '#5c5850',
    halo: '#ffffff'
  };

  var namedRoad = ['all', ['has', 'name'], ['!=', ['get', 'name'], '']];
  var MAX_Z = 16;

  var labelLayout = {
    'symbol-placement': 'line',
    'text-font': ['Noto Sans Regular'],
    'text-field': ['get', 'name'],
    'text-max-angle': 30,
    'text-padding': 2,
    'text-rotation-alignment': 'map',
    'text-pitch-alignment': 'viewport',
    'symbol-spacing': 180,
    'text-optional': false
  };

  return {
    version: 8,
    glyphs: root + '/vendor/fonts/{fontstack}/{range}.pbf',
    sources: {
      ca: {
        type: 'vector',
        url: 'pmtiles://' + pmtilesUrl,
        attribution: '(c) OpenStreetMap contributors, Protomaps'
      }
    },
    layers: [
      { id: 'bg', type: 'background', paint: { 'background-color': c.earth } },
      { id: 'earth', type: 'fill', source: 'ca', 'source-layer': 'earth',
        paint: { 'fill-color': c.earth } },
      { id: 'landuse', type: 'fill', source: 'ca', 'source-layer': 'landuse',
        paint: { 'fill-color': c.land, 'fill-opacity': 0.6 } },
      { id: 'water', type: 'fill', source: 'ca', 'source-layer': 'water',
        paint: { 'fill-color': c.water } },

      { id: 'buildings-fill', type: 'fill', source: 'ca', 'source-layer': 'buildings',
        minzoom: 14, maxzoom: MAX_Z + 1,
        filter: ['in', ['get', 'kind'], ['literal', ['building', 'building_part']]],
        paint: {
          'fill-color': c.building,
          'fill-opacity': ['interpolate', ['linear'], ['zoom'], 14, 0.25, 15, 0.55, 16, 0.88]
        } },
      { id: 'buildings-outline', type: 'line', source: 'ca', 'source-layer': 'buildings',
        minzoom: 15, maxzoom: MAX_Z + 1,
        filter: ['==', ['get', 'kind'], 'building'],
        layout: { 'line-join': 'round' },
        paint: {
          'line-color': c.buildingLine,
          'line-width': ['interpolate', ['linear'], ['zoom'], 15, 0.35, 16, 1.1]
        } },

      { id: 'roads-all', type: 'line', source: 'ca', 'source-layer': 'roads',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': c.road,
          'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.4, 12, 1.2, 14, 2.8, 16, 4.5]
        } },
      { id: 'roads-major', type: 'line', source: 'ca', 'source-layer': 'roads',
        filter: ['in', ['get', 'kind'], ['literal', ['major_road', 'medium_road']]],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': c.major,
          'line-width': ['interpolate', ['linear'], ['zoom'], 8, 1.0, 12, 2.2, 14, 5.0, 16, 7.5]
        } },
      { id: 'hwy-case', type: 'line', source: 'ca', 'source-layer': 'roads',
        filter: ['==', ['get', 'kind'], 'highway'],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': c.hwyCase,
          'line-width': ['interpolate', ['linear'], ['zoom'], 6, 1.5, 12, 5.0, 14, 9.0, 16, 12]
        } },
      { id: 'hwy', type: 'line', source: 'ca', 'source-layer': 'roads',
        filter: ['==', ['get', 'kind'], 'highway'],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': c.hwy,
          'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.8, 12, 3.0, 14, 6.5, 16, 9]
        } },

      { id: 'road-label-hwy', type: 'symbol', source: 'ca', 'source-layer': 'roads',
        minzoom: 10, maxzoom: MAX_Z + 1,
        filter: ['all', namedRoad, ['==', ['get', 'kind'], 'highway']],
        layout: Object.assign({}, labelLayout, {
          'text-size': ['interpolate', ['linear'], ['zoom'], 10, 10, 12, 11, 14, 13, 16, 14],
          'symbol-spacing': 280
        }),
        paint: {
          'text-color': c.label,
          'text-halo-color': c.halo,
          'text-halo-width': 2
        } },
      { id: 'road-label-major', type: 'symbol', source: 'ca', 'source-layer': 'roads',
        minzoom: 11, maxzoom: MAX_Z + 1,
        filter: ['all', namedRoad,
          ['in', ['get', 'kind'], ['literal', ['major_road', 'medium_road']]]],
        layout: Object.assign({}, labelLayout, {
          'text-size': ['interpolate', ['linear'], ['zoom'], 11, 9, 12, 10, 14, 12, 16, 13],
          'symbol-spacing': 200
        }),
        paint: {
          'text-color': c.label,
          'text-halo-color': c.halo,
          'text-halo-width': 1.75
        } },
      { id: 'road-label-local', type: 'symbol', source: 'ca', 'source-layer': 'roads',
        minzoom: 11, maxzoom: MAX_Z + 1,
        filter: ['all', namedRoad,
          ['!', ['in', ['get', 'kind'], ['literal', ['highway', 'major_road', 'medium_road']]]]],
        layout: Object.assign({}, labelLayout, {
          'text-size': ['interpolate', ['linear'], ['zoom'], 11, 8, 12, 9, 14, 11, 16, 12],
          'symbol-spacing': ['interpolate', ['linear'], ['zoom'], 11, 200, 14, 120, 16, 90]
        }),
        paint: {
          'text-color': c.label,
          'text-halo-color': c.halo,
          'text-halo-width': 1.75
        } },

      { id: 'address-labels', type: 'symbol', source: 'ca', 'source-layer': 'buildings',
        minzoom: 15, maxzoom: MAX_Z + 1,
        filter: ['all',
          ['==', ['get', 'kind'], 'address'],
          ['has', 'addr_housenumber'],
          ['!=', ['get', 'addr_housenumber'], '']],
        layout: {
          'text-field': ['get', 'addr_housenumber'],
          'text-font': ['Noto Sans Regular'],
          'text-size': ['interpolate', ['linear'], ['zoom'], 15, 9, 16, 11],
          'text-anchor': 'center',
          'text-allow-overlap': false,
          'text-padding': 2
        },
        paint: {
          'text-color': c.addr,
          'text-halo-color': c.halo,
          'text-halo-width': 1.2
        } }
    ]
  };
}
