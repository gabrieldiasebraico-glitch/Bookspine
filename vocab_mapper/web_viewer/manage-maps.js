const mapSearchInput = document.getElementById("mapSearch");
const mapStatusFilter = document.getElementById("mapStatusFilter");
const manageMapTable = document.getElementById("manageMapTable");
const selectedMapTitle = document.getElementById("selectedMapTitle");
const selectedMapStatus = document.getElementById("selectedMapStatus");
const bookNameInput = document.getElementById("bookNameInput");
const mapNameInput = document.getElementById("mapNameInput");
const renameMapButton = document.getElementById("renameMap");
const excludeMapButton = document.getElementById("excludeMap");
const duplicateMapButton = document.getElementById("duplicateMap");
const exportFormatSelect = document.getElementById("exportFormat");
const exportMapButton = document.getElementById("exportMap");
const mapMetadata = document.getElementById("mapMetadata");
const manageStatus = document.getElementById("manageStatus");

const manageState = {
  maps: [],
  selectedId: "",
};

function setManageStatus(text, isError = false) {
  manageStatus.textContent = text;
  manageStatus.classList.toggle("error", isError);
}

async function loadMaps(preferredId = manageState.selectedId) {
  const response = await fetch("/api/manage/maps");
  const payload = await response.json();
  manageState.maps = payload.maps || [];
  if (preferredId && manageState.maps.some((map) => map.id === preferredId)) {
    manageState.selectedId = preferredId;
  } else {
    manageState.selectedId = filteredMaps()[0]?.id || manageState.maps[0]?.id || "";
  }
  renderMapTable();
  renderSelectedMap();
}

function filteredMaps() {
  const query = mapSearchInput.value.trim().toLowerCase();
  const status = mapStatusFilter.value;
  return manageState.maps.filter((map) => {
    if (status === "active" && map.excluded) return false;
    if (status === "excluded" && !map.excluded) return false;
    if (!query) return true;
    return [
      map.book,
      map.mapType,
      map.metric,
      map.group,
      map.csvPath,
      map.metadataPath,
    ].some((value) => String(value || "").toLowerCase().includes(query));
  });
}

function renderMapTable() {
  const maps = filteredMaps();
  if (!maps.length) {
    manageMapTable.innerHTML = `<tbody><tr><td>No maps match the current filter.</td></tr></tbody>`;
    return;
  }
  const rows = maps.map((map) => `
    <tr class="${map.id === manageState.selectedId ? "selected" : ""}">
      <td><button type="button" data-map-id="${escapeHtml(map.id)}">${escapeHtml(map.book)}</button></td>
      <td>${escapeHtml(map.mapType || map.metric)}</td>
      <td>${escapeHtml(map.excluded ? "Excluded" : "Active")}</td>
    </tr>
  `).join("");
  manageMapTable.innerHTML = `
    <thead>
      <tr><th>Book</th><th>Map</th><th>Status</th></tr>
    </thead>
    <tbody>${rows}</tbody>
  `;
}

function selectedMap() {
  return manageState.maps.find((map) => map.id === manageState.selectedId) || null;
}

function renderSelectedMap() {
  const map = selectedMap();
  const hasMap = Boolean(map);
  for (const control of [bookNameInput, mapNameInput, renameMapButton, excludeMapButton, duplicateMapButton, exportFormatSelect, exportMapButton]) {
    control.disabled = !hasMap;
  }
  if (!map) {
    selectedMapTitle.textContent = "No map selected";
    selectedMapStatus.textContent = "";
    bookNameInput.value = "";
    mapNameInput.value = "";
    mapMetadata.innerHTML = "";
    return;
  }

  selectedMapTitle.textContent = `${map.book} / ${map.mapType || map.metric}`;
  selectedMapStatus.textContent = map.excluded ? "Excluded" : "Active";
  selectedMapStatus.classList.toggle("excluded", Boolean(map.excluded));
  bookNameInput.value = map.book || "";
  mapNameInput.value = map.mapType || map.metric || "";
  excludeMapButton.textContent = map.excluded ? "Restore" : "Exclude";
  mapMetadata.innerHTML = definitionList([
    ["Metric", map.metric],
    ["Group", map.group],
    ["CSV", map.csvPath],
    ["Metadata", map.metadataPath],
    ["Image", map.imagePath || "Unavailable"],
  ]);
}

async function postMapAction(action, body = {}) {
  const map = selectedMap();
  if (!map) return null;
  const response = await fetch(`/api/manage/maps/${encodeURIComponent(map.id)}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "Map action failed.");
  }
  manageState.maps = payload.maps || manageState.maps;
  manageState.selectedId = payload.map?.id || map.id;
  renderMapTable();
  renderSelectedMap();
  return payload.map || null;
}

function definitionList(items) {
  return items.map(([label, value]) => `
    <dt>${escapeHtml(label)}</dt>
    <dd>${escapeHtml(value || "")}</dd>
  `).join("");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

manageMapTable.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-map-id]");
  if (!button) return;
  manageState.selectedId = button.dataset.mapId;
  renderMapTable();
  renderSelectedMap();
});

for (const control of [mapSearchInput, mapStatusFilter]) {
  control.addEventListener("input", () => {
    const maps = filteredMaps();
    if (!maps.some((map) => map.id === manageState.selectedId)) {
      manageState.selectedId = maps[0]?.id || "";
    }
    renderMapTable();
    renderSelectedMap();
  });
}

renameMapButton.addEventListener("click", async () => {
  try {
    await postMapAction("rename", {
      book: bookNameInput.value,
      mapType: mapNameInput.value,
    });
    setManageStatus("Map renamed.");
  } catch (error) {
    setManageStatus(error.message || "Rename failed.", true);
  }
});

excludeMapButton.addEventListener("click", async () => {
  const map = selectedMap();
  if (!map) return;
  try {
    await postMapAction("exclude", { excluded: !map.excluded });
    setManageStatus(map.excluded ? "Map restored." : "Map excluded.");
  } catch (error) {
    setManageStatus(error.message || "Status update failed.", true);
  }
});

duplicateMapButton.addEventListener("click", async () => {
  try {
    await postMapAction("duplicate", {});
    setManageStatus("Map duplicated.");
  } catch (error) {
    setManageStatus(error.message || "Duplicate failed.", true);
  }
});

exportMapButton.addEventListener("click", () => {
  const map = selectedMap();
  if (!map) return;
  const format = encodeURIComponent(exportFormatSelect.value);
  window.location.href = `/api/manage/maps/${encodeURIComponent(map.id)}/export?format=${format}`;
  setManageStatus("Export started.");
});

loadMaps().catch((error) => {
  setManageStatus(error.message || "Map list unavailable.", true);
});
