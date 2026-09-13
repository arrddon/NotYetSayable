import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export function mountMap(host: HTMLElement, initial: { lng: number; lat: number } | null,
  onChange: (pin: { lng: number; lat: number }) => void) {
  const map = L.map(host).setView(initial ? [initial.lat, initial.lng] : [20, 0], initial ? 8 : 2);
  const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>', maxZoom: 19,
  }).addTo(map);
  let marker: L.CircleMarker | undefined;
  function setPin(pin: { lat: number; lng: number }) {
    if (marker) marker.setLatLng(pin);
    else marker = L.circleMarker(pin, { radius: 8, color: '#111', fillColor: '#111', fillOpacity: 1 }).addTo(map);
  }
  if (initial) setPin(initial);
  map.on('click', (event: L.LeafletMouseEvent) => {
    const latlng = event.latlng.wrap();
    const pin = { lng: Number(latlng.lng.toFixed(6)), lat: Number(latlng.lat.toFixed(6)) };
    if (pin.lat < -90 || pin.lat > 90) return;
    setPin(pin); onChange(pin);
  });
  tiles.on('tileerror', () => {
    const message = document.getElementById('map-message');
    if (message) message.textContent = 'Map unavailable. Check your connection or enter coordinates.';
  });
  return { destroy: () => map.remove(), setPin };
}
