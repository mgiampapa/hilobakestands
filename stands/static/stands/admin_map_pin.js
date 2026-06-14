/* Drag-a-pin map for the Stand admin form.
   Dragging the pin (or clicking the map) fills latitude/longitude and marks
   coords_source = admin, which protects the point from the geocoder. */
window.addEventListener('load', function () {
  const latIn = document.getElementById('id_latitude');
  const lngIn = document.getElementById('id_longitude');
  const srcIn = document.getElementById('id_coords_source');
  if (!latIn || !lngIn || typeof L === 'undefined') return;

  const wrap = document.createElement('div');
  const note = document.createElement('p');
  note.className = 'help';
  note.textContent = 'Drag the pin (or click the map) to set the exact spot — ' +
                     'useful on large parcels where the address is vague.';
  const mapDiv = document.createElement('div');
  mapDiv.style.cssText =
    'height:340px;max-width:720px;margin:6px 0 12px;border-radius:8px;';
  wrap.appendChild(note);
  wrap.appendChild(mapDiv);
  const row = lngIn.closest('.form-row, .field-longitude') || lngIn.parentElement;
  row.insertAdjacentElement('afterend', wrap);

  const HILO = [19.7074, -155.0885];
  const has = latIn.value !== '' && lngIn.value !== '';
  const start = has ? [parseFloat(latIn.value), parseFloat(lngIn.value)] : HILO;

  const map = L.map(mapDiv).setView(start, has ? 16 : 12);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    referrerPolicy: 'origin',  // OSM 403s referrer-less tile requests
    attribution: '© OpenStreetMap contributors'
  }).addTo(map);
  const pin = L.marker(start, { draggable: true }).addTo(map);

  function setCoords(latlng) {
    latIn.value = latlng.lat.toFixed(6);
    lngIn.value = latlng.lng.toFixed(6);
    if (srcIn) srcIn.value = 'admin';
  }
  pin.on('dragend', function () { setCoords(pin.getLatLng()); });
  map.on('click', function (e) { pin.setLatLng(e.latlng); setCoords(e.latlng); });

  // Typing coordinates by hand moves the pin too.
  function syncFromInputs() {
    const lat = parseFloat(latIn.value), lng = parseFloat(lngIn.value);
    if (!isNaN(lat) && !isNaN(lng)) {
      pin.setLatLng([lat, lng]);
      map.panTo([lat, lng]);
    }
  }
  latIn.addEventListener('change', syncFromInputs);
  lngIn.addEventListener('change', syncFromInputs);
});
