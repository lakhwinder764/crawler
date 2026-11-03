const TILES = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png";
const TILE_ATTR = '&copy; OpenStreetMap &copy; CARTO';
const COLOURS = {
  Sports: "#2563eb",
  Social: "#e11d48",
  Fitness: "#059669",
  Run: "#0d9488",
  Art: "#c026d3",
  "Book Club": "#7c3aed",
  Professional: "#0f172a",
  "Bar Crawl": "#ea580c",
};

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function pinIcon(category) {
  const colour = COLOURS[category] || "#1a73e8";
  const svg = '<svg viewBox="0 0 24 36" width="28" height="40" aria-hidden="true">'
    + '<path fill="' + colour + '" stroke="#ffffff" stroke-width="1.5" d="M12 1C6 1 1.5 5.6 1.5 11.5 1.5 20 12 35 12 35s10.5-15 10.5-23.5C22.5 5.6 18 1 12 1z"/>'
    + '<circle cx="12" cy="11.5" r="4.2" fill="#ffffff"/></svg>';
  return L.divIcon({
    className: "pin-wrap",
    html: svg,
    iconSize: [28, 40],
    iconAnchor: [14, 40],
    popupAnchor: [0, -36],
  });
}

function addTiles(map) {
  L.tileLayer(TILES, { attribution: TILE_ATTR, subdomains: "abcd", maxZoom: 20 }).addTo(map);
}

function kilometres(aLat, aLng, bLat, bLng) {
  const radius = 6371;
  const p1 = aLat * Math.PI / 180;
  const p2 = bLat * Math.PI / 180;
  const dLat = (bLat - aLat) * Math.PI / 180;
  const dLng = (bLng - aLng) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dLng / 2) ** 2;
  return 2 * radius * Math.asin(Math.sqrt(a));
}

function placeMarkers(map, clubs) {
  const markers = {};
  const bounds = [];
  clubs.forEach((club) => {
    if (club.lat == null || club.lng == null) return;
    const marker = L.marker([club.lat, club.lng], { icon: pinIcon(club.category) }).addTo(map);
    const place = [club.suburb, club.city].filter(Boolean).join(", ");
    marker.bindPopup(
      "<strong>" + escapeHtml(club.name) + "</strong>"
      + (place ? "<br>" + escapeHtml(place) : "")
      + "<br><a href='/clubs/" + encodeURIComponent(club.id) + "'>View club</a>"
    );
    markers[club.id] = marker;
    bounds.push([club.lat, club.lng]);
  });
  if (bounds.length) map.fitBounds(bounds, { padding: [36, 36], maxZoom: 13 });
  return markers;
}

function followUser(map, onMove) {
  const status = document.querySelector("#live-status");
  let marker = null;
  let accuracy = null;
  if (!navigator.geolocation) {
    if (status) status.textContent = "This browser cannot share your location.";
    return;
  }
  if (status) status.textContent = "Finding you…";
  navigator.geolocation.watchPosition((position) => {
    const here = [position.coords.latitude, position.coords.longitude];
    if (!marker) {
      marker = L.circleMarker(here, {
        radius: 9,
        color: "#ffffff",
        weight: 3,
        fillColor: "#4f46e5",
        fillOpacity: 1,
      }).addTo(map);
      marker.bindPopup("You are here");
      accuracy = L.circle(here, {
        radius: position.coords.accuracy,
        color: "#4f46e5",
        weight: 1,
        fillColor: "#4f46e5",
        fillOpacity: 0.12,
      }).addTo(map);
    } else {
      marker.setLatLng(here);
      accuracy.setLatLng(here);
      accuracy.setRadius(position.coords.accuracy);
    }
    map.panTo(here);
    if (status) status.textContent = "Live location is on";
    if (onMove) onMove(position.coords.latitude, position.coords.longitude);
  }, () => {
    if (status) status.textContent = "Location access is needed to follow you.";
    window.alert("Location access is needed to find clubs near you.");
  }, { enableHighAccuracy: true, maximumAge: 5000 });
}

const directoryMap = document.querySelector("#directory-map");
const directoryData = document.querySelector("#directory-data");
if (directoryMap && directoryData) {
  const clubs = JSON.parse(directoryData.textContent);
  const map = L.map(directoryMap, { zoomControl: true, scrollWheelZoom: true }).setView([-33.8688, 151.2093], 11);
  addTiles(map);
  const markers = placeMarkers(map, clubs);
  document.querySelectorAll(".card[data-id]").forEach((card) => {
    card.addEventListener("mouseenter", () => {
      const marker = markers[card.dataset.id];
      if (!marker) return;
      map.panTo(marker.getLatLng());
      marker.openPopup();
    });
  });
  const latField = document.querySelector("input[name='lat']");
  const lngField = document.querySelector("input[name='lng']");
  if (latField && lngField && latField.value && lngField.value) {
    const here = [Number(latField.value), Number(lngField.value)];
    L.circleMarker(here, {
      radius: 9,
      color: "#ffffff",
      weight: 3,
      fillColor: "#4f46e5",
      fillOpacity: 1,
    }).addTo(map).bindPopup("You are here");
    L.circle(here, { radius: 1200, color: "#4f46e5", weight: 1, fillOpacity: 0.08 }).addTo(map);
    map.setView(here, 13);
    const status = document.querySelector("#live-status");
    if (status) status.textContent = "Centred on your location";
  }
}

const fullMap = document.querySelector("#club-map");
const fullData = document.querySelector("#club-data");
if (fullMap && fullData) {
  const clubs = JSON.parse(fullData.textContent);
  const map = L.map(fullMap).setView([-33.8688, 151.2093], 11);
  addTiles(map);
  const markers = placeMarkers(map, clubs);
  if (location.hash && markers[location.hash.slice(1)]) {
    const club = clubs.find((item) => item.id === location.hash.slice(1));
    map.setView([club.lat, club.lng], 14);
    markers[club.id].openPopup();
  }
  const button = document.querySelector("#map-near-me");
  if (button) {
    button.addEventListener("click", () => {
      followUser(map, (lat, lng) => {
        const list = document.querySelector("#nearby-list");
        list.innerHTML = "";
        clubs
          .map((club) => ({ club, distance: kilometres(lat, lng, club.lat, club.lng) }))
          .sort((left, right) => left.distance - right.distance)
          .slice(0, 8)
          .forEach((item) => {
            const li = document.createElement("li");
            const link = document.createElement("a");
            link.href = "/clubs/" + item.club.id;
            link.textContent = item.club.name;
            const distance = document.createElement("span");
            distance.textContent = item.distance.toFixed(1) + " km";
            li.append(link, distance);
            li.addEventListener("click", (event) => {
              if (event.target === link) return;
              map.setView([item.club.lat, item.club.lng], 14);
              markers[item.club.id].openPopup();
            });
            list.appendChild(li);
          });
      });
    });
  }
}

const pinMap = document.querySelector("#club-pin-map");
if (pinMap) {
  const lat = Number(pinMap.dataset.lat);
  const lng = Number(pinMap.dataset.lng);
  const map = L.map(pinMap, { scrollWheelZoom: false }).setView([lat, lng], 14);
  addTiles(map);
  L.marker([lat, lng], { icon: pinIcon("") }).addTo(map).bindPopup(escapeHtml(pinMap.dataset.name));
}
