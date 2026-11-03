function storeKey(kind) {
  return "acf-" + kind;
}

function readSaved(kind) {
  try {
    return JSON.parse(localStorage.getItem(storeKey(kind)) || "[]");
  } catch (error) {
    return [];
  }
}

function writeSaved(kind, values) {
  localStorage.setItem(storeKey(kind), JSON.stringify(values));
}

document.querySelectorAll("[data-save]").forEach((button) => {
  const kind = button.dataset.save;
  const id = button.dataset.id;
  const saved = readSaved(kind);
  if (saved.includes(id)) button.textContent = "Saved";
  button.addEventListener("click", () => {
    const current = readSaved(kind);
    if (current.includes(id)) {
      writeSaved(kind, current.filter((item) => item !== id));
      button.textContent = button.dataset.save === "follow" ? "Follow" : button.dataset.save === "event" ? "Bookmark" : "Save";
    } else {
      current.push(id);
      writeSaved(kind, current);
      button.textContent = "Saved";
    }
  });
});

const nearMe = document.querySelector("#near-me");
if (nearMe) {
  nearMe.addEventListener("click", () => {
    navigator.geolocation.getCurrentPosition((position) => {
      const form = nearMe.closest("form");
      form.lat.value = position.coords.latitude;
      form.lng.value = position.coords.longitude;
      if (!form.distance.value) form.distance.value = "10";
      form.submit();
    }, () => {
      window.alert("Location access is needed to find clubs near you.");
    });
  });
}

const savedRoot = document.querySelector("#saved-lists");
if (savedRoot) {
  const favourites = readSaved("favourite");
  const follows = readSaved("follow");
  const events = readSaved("event");
  const ids = Array.from(new Set(favourites.concat(follows, events.map((item) => item.split(":")[0]))));
  fetch("/api/clubs?ids=" + encodeURIComponent(ids.join(",")))
    .then((response) => response.json())
    .then((clubs) => {
      const byId = Object.fromEntries(clubs.map((club) => [club.id, club]));
      fillList("favourite", favourites, byId);
      fillList("follow", follows, byId);
      const eventList = savedRoot.querySelector('[data-list="event"]');
      events.forEach((key) => {
        const [clubId, eventId] = key.split(":");
        const club = byId[clubId];
        if (!club) return;
        const event = (club.events || []).find((item) => item.id === eventId);
        const li = document.createElement("li");
        li.textContent = club.name + (event ? " — " + event.title : "");
        eventList.appendChild(li);
      });
      if (!eventList.children.length) eventList.textContent = "None yet.";
    });
}

function fillList(kind, ids, byId) {
  const list = document.querySelector('[data-list="' + kind + '"]');
  ids.forEach((id) => {
    const club = byId[id];
    if (!club) return;
    const li = document.createElement("li");
    const link = document.createElement("a");
    link.href = "/clubs/" + club.id;
    link.textContent = club.name;
    li.appendChild(link);
    list.appendChild(li);
  });
  if (!list.children.length) list.textContent = "None yet.";
}
