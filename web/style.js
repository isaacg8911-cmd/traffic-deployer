/*
 * Offline California basemap — Protomaps v4 light palette.
 * Street names on roads layer; no house-number clutter (addresses removed).
 * Lean: optional labels, no buildings at field zoom, paths unlabeled.
 */
function buildStyle(pmtilesUrl, baseUrl) {
  var root = baseUrl || '';
  var c = {
    earth: '#f4f3ee',
    water: '#a9d6f5',
    land: '#eceae2',
    building: '#ddd9d0',
    buildingLine: '#b8b4ac',
    road: '#b8b2a8',
    major: '#9a948a',
    hwy: '#f4a259',
    hwyCase: '#ffffff',
    label: '#2a2724',
    halo: '#ffffff'
  };

  var namedRoad = ['all', ['has', 'name'], ['!=', ['get', 'name'], '']];
  var MAX_Z = 15;
  var localKinds = ['minor_road', 'other'];

  var labelLayout = {
    'symbol-placement': 'line',
    'text-font': ['Noto Sans Regular'],
    'text-field': ['get', 'name'],
    'text-max-angle': 30,
    'text-padding': 2,
    'text-rotation-alignment': 'map',
    'text-pitch-alignment': 'viewport',
    'symbol-spacing': 160,
    'text-optional': true
  };

  return {
    version: 8,
    glyphs: root + '/vendor/fonts/{fontstack}/{range}.pbf',
    sources: {
      ca: {
        type: 'vector',
        url: 'pmtiles://' + pmtilesUrl,
        maxzoom: MAX_Z,
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

      { id: 'roads-all', type: 'line', source: 'ca', 'source-layer': 'roads',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': c.road,
          'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.5, 12, 1.4, 14, 3.0, 15, 4.5]
        } },
      { id: 'roads-major', type: 'line', source: 'ca', 'source-layer': 'roads',
        filter: ['in', ['get', 'kind'], ['literal', ['major_road', 'medium_road']]],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': c.major,
          'line-width': ['interpolate', ['linear'], ['zoom'], 8, 1.0, 12, 2.4, 14, 5.5, 15, 7.5]
        } },
      { id: 'hwy-case', type: 'line', source: 'ca', 'source-layer': 'roads',
        filter: ['==', ['get', 'kind'], 'highway'],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': c.hwyCase,
          'line-width': ['interpolate', ['linear'], ['zoom'], 6, 1.5, 12, 5.0, 14, 9.0, 15, 12]
        } },
      { id: 'hwy', type: 'line', source: 'ca', 'source-layer': 'roads',
        filter: ['==', ['get', 'kind'], 'highway'],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': c.hwy,
          'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.8, 12, 3.0, 14, 6.5, 15, 9]
        } },

      { id: 'road-label-hwy', type: 'symbol', source: 'ca', 'source-layer': 'roads',
        minzoom: 9, maxzoom: MAX_Z + 1,
        filter: ['all', namedRoad, ['==', ['get', 'kind'], 'highway']],
        layout: Object.assign({}, labelLayout, {
          'text-size': ['interpolate', ['linear'], ['zoom'], 9, 10, 11, 11, 13, 13, 15, 14],
          'symbol-spacing': 260
        }),
        paint: {
          'text-color': c.label,
          'text-halo-color': c.halo,
          'text-halo-width': 2.2
        } },
      { id: 'road-label-major', type: 'symbol', source: 'ca', 'source-layer': 'roads',
        minzoom: 10, maxzoom: MAX_Z + 1,
        filter: ['all', namedRoad,
          ['in', ['get', 'kind'], ['literal', ['major_road', 'medium_road']]]],
        layout: Object.assign({}, labelLayout, {
          'text-size': ['interpolate', ['linear'], ['zoom'], 10, 10, 12, 11, 13, 13, 15, 14],
          'symbol-spacing': 180
        }),
        paint: {
          'text-color': c.label,
          'text-halo-color': c.halo,
          'text-halo-width': 2
        } },
      { id: 'road-label-local', type: 'symbol', source: 'ca', 'source-layer': 'roads',
        minzoom: 12, maxzoom: MAX_Z + 1,
        filter: ['all', namedRoad,
          ['in', ['get', 'kind'], ['literal', localKinds]]],
        layout: Object.assign({}, labelLayout, {
          'text-size': ['interpolate', ['linear'], ['zoom'], 12, 10, 13, 11, 14, 12, 15, 13],
          'symbol-spacing': ['interpolate', ['linear'], ['zoom'], 12, 200, 13, 140, 14, 110, 15, 95]
        }),
        paint: {
          'text-color': c.label,
          'text-halo-color': c.halo,
          'text-halo-width': 1.6
        } }
    ]
  };
}
