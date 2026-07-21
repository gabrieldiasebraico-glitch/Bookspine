const canvas = document.getElementById("viewerCanvas");
const ctx = canvas.getContext("2d", { alpha: false });
const bookSelect = document.getElementById("bookSelect");
const mapTypeSelect = document.getElementById("mapTypeSelect");
const statusEl = document.getElementById("status");
const fontSizeInput = document.getElementById("fontSize");
const fontSizeValue = document.getElementById("fontSizeValue");
const panelSizeInput = document.getElementById("panelSize");
const panelSizeValue = document.getElementById("panelSizeValue");
const showWordsInput = document.getElementById("showWords");
const showStructureInput = document.getElementById("showStructure");
const classDiscriminationInput = document.getElementById("classDiscrimination");
const mapInfoEl = document.getElementById("mapInfo");
const toggleSummaryButton = document.getElementById("toggleSummary");

const MIN_MAP_WIDTH = 280;
const LEFT_PANEL_RATIO = 0.5;
const MIN_PANEL_WIDTH = 210;
const MAP_TOP_GAP = 12;
const RIGHT_MAP_GAP = 44;
const BRACKET_SPACING = 88;
const BRACKET_RIGHT_PADDING = 28;
const NAV_BAR_WIDTH = 18;
const NAV_BAR_GAP = 8;

const state = {
  maps: [],
  books: [],
  map: null,
  viewportStart: 0,
  zoom: 1,
  fontSize: 12,
  panelSize: 300,
  data: null,
  overview: null,
  summary: null,
  summaryVisible: false,
  loading: false,
  loadingMaps: true,
  abort: null,
  overviewAbort: null,
  summaryAbort: null,
  dragging: false,
  navigating: false,
  resizingPanel: false,
  lastY: 0,
};

function layout() {
  const width = canvas.clientWidth;
  const canvasHeight = canvas.clientHeight;
  const topGap = canvasHeight > 180 ? MAP_TOP_GAP : 6;
  const height = Math.max(1, canvasHeight - topGap);
  const minMapWidth = width < 760 ? 180 : MIN_MAP_WIDTH;
  const navSpace = NAV_BAR_WIDTH + NAV_BAR_GAP * 2;
  const panelUpper = Math.max(80, Math.floor((width - minMapWidth - navSpace) / (1 + LEFT_PANEL_RATIO)));
  const panelWidth = Math.max(80, Math.min(state.panelSize, panelUpper));
  const leftPanelWidth = Math.max(52, Math.round(panelWidth * LEFT_PANEL_RATIO));
  const mapLeft = leftPanelWidth;
  const navLeft = width - NAV_BAR_GAP - NAV_BAR_WIDTH;
  const navRight = navLeft + NAV_BAR_WIDTH;
  const mapRight = Math.max(mapLeft + 80, width - panelWidth - navSpace);
  const rightAvailable = Math.max(1, width - mapRight);
  const desiredStructureWidth = RIGHT_MAP_GAP + BRACKET_SPACING * 2 + BRACKET_RIGHT_PADDING;
  const structureScale = Math.min(1, rightAvailable / desiredStructureWidth);
  const rightGap = Math.max(24, Math.round(RIGHT_MAP_GAP * structureScale));
  const bracketSpacing = Math.max(52, Math.round(BRACKET_SPACING * structureScale));
  const sentenceX = mapRight + rightGap;
  const paragraphX = sentenceX + bracketSpacing;
  const chapterX = paragraphX + bracketSpacing;
  return {
    width,
    canvasHeight,
    height,
    topGap,
    mapTop: topGap,
    mapBottom: canvasHeight,
    panelWidth,
    leftPanelWidth,
    mapLeft,
    mapRight,
    mapWidth: mapRight - mapLeft,
    navLeft,
    navRight,
    navWidth: NAV_BAR_WIDTH,
    axisLabelX: Math.max(38, mapLeft - 38),
    axisTickX: Math.max(48, mapLeft - 28),
    sentenceX,
    paragraphX,
    chapterX,
  };
}

function resizeCanvas() {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.floor(canvas.clientWidth * ratio);
  const height = Math.floor(canvas.clientHeight * ratio);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  syncPanelControl();
  clampViewport();
  scheduleOverviewFetch();
  scheduleFetch();
}

function syncPanelControl() {
  const minMapWidth = canvas.clientWidth < 760 ? 180 : MIN_MAP_WIDTH;
  const navSpace = NAV_BAR_WIDTH + NAV_BAR_GAP * 2;
  const maxPanelWidth = Math.max(80, Math.floor((canvas.clientWidth - minMapWidth - navSpace) / (1 + LEFT_PANEL_RATIO)));
  const minPanelWidth = Math.min(MIN_PANEL_WIDTH, maxPanelWidth);
  state.panelSize = Math.max(minPanelWidth, Math.min(state.panelSize, maxPanelWidth));
  panelSizeInput.min = String(minPanelWidth);
  panelSizeInput.max = String(maxPanelWidth);
  panelSizeInput.value = String(Math.round(state.panelSize));
  panelSizeValue.value = String(Math.round(state.panelSize));
}

function fitMap() {
  if (!state.map) return;
  const box = layout();
  state.zoom = Math.max(0.001, box.height / Math.max(1, state.map.totalRows));
  state.viewportStart = 0;
  scheduleFetch();
}

function actualSizeMap() {
  if (!state.map) return;
  const box = layout();
  const centerRow = state.viewportStart + (box.height / state.zoom) / 2;
  state.zoom = 1;
  state.viewportStart = centerRow - box.height / 2;
  clampViewport();
  scheduleFetch();
}

function clampViewport() {
  if (!state.map) return;
  const box = layout();
  const visibleRows = box.height / state.zoom;
  const maxStart = Math.max(0, state.map.totalRows - visibleRows);
  state.viewportStart = Math.max(0, Math.min(state.viewportStart, maxStart));
}

function visibleRange() {
  const box = layout();
  const start = Math.floor(state.viewportStart);
  const end = Math.ceil(state.viewportStart + box.height / state.zoom);
  return {
    start: Math.max(0, start),
    end: Math.min(state.map ? state.map.totalRows : 1, end),
  };
}

function setStatus(text) {
  statusEl.textContent = text;
}

async function loadMaps(preferredMapId = "") {
  state.loadingMaps = true;
  setStatus("Scanning maps...");
  const response = await fetch("/api/maps");
  const payload = await response.json();
  state.maps = payload.maps || [];
  state.books = uniqueBooks(state.maps);
  state.loadingMaps = false;
  bookSelect.innerHTML = "";
  for (const book of state.books) {
    const option = document.createElement("option");
    option.value = book;
    option.textContent = book;
    bookSelect.appendChild(option);
  }
  if (state.maps.length === 0) {
    setStatus("No map metadata found.");
    draw();
    return;
  }
  const preferred = state.maps.find((map) => map.id === preferredMapId);
  const current = state.maps.find((map) => map.id === state.map?.id);
  const selected = preferred || current || state.maps[0];
  selectBook(selected.book || selected.title, selected.id);
}

function uniqueBooks(maps) {
  return [...new Set(maps.map((map) => map.book || map.title))].sort((a, b) => a.localeCompare(b));
}

function mapsForBook(book) {
  return state.maps
    .filter((map) => (map.book || map.title) === book)
    .sort((a, b) => (a.mapType || a.metric).localeCompare(b.mapType || b.metric));
}

function selectBook(book, preferredMapId = "") {
  bookSelect.value = book;
  const maps = mapsForBook(book);
  mapTypeSelect.innerHTML = "";
  for (const map of maps) {
    const option = document.createElement("option");
    option.value = map.id;
    option.textContent = map.mapType || map.metric;
    mapTypeSelect.appendChild(option);
  }
  const selected = maps.find((map) => map.id === preferredMapId) || maps[0] || null;
  if (selected) {
    mapTypeSelect.value = selected.id;
    selectMap(selected.id);
  }
}

function selectMap(id) {
  state.map = state.maps.find((item) => item.id === id) || null;
  state.data = null;
  state.overview = null;
  state.summary = null;
  renderSummary();
  fetchSummary();
  scheduleOverviewFetch();
  fitMap();
}

let fetchTimer = 0;
let overviewFetchTimer = 0;
function scheduleFetch() {
  clearTimeout(fetchTimer);
  fetchTimer = window.setTimeout(fetchViewport, 40);
  draw();
}

function scheduleOverviewFetch() {
  clearTimeout(overviewFetchTimer);
  overviewFetchTimer = window.setTimeout(fetchOverview, 80);
}

async function fetchViewport() {
  if (!state.map) return;
  clampViewport();
  const box = layout();
  const range = visibleRange();
  const limit = Math.min(5000, Math.max(300, Math.ceil(box.height * 1.5)));
  if (state.abort) state.abort.abort();
  state.abort = new AbortController();
  state.loading = true;
  try {
    const classDiscrimination = classDiscriminationInput.checked ? "1" : "0";
    const url = `/api/maps/${state.map.id}/viewport?start=${range.start}&end=${range.end}&limit=${limit}&classDiscrimination=${classDiscrimination}`;
    const response = await fetch(url, { signal: state.abort.signal });
    state.data = await response.json();
    const shown = Math.max(0, range.end - range.start).toLocaleString();
    const total = state.map.totalRows.toLocaleString();
    setStatus(`${shown} of ${total} word rows`);
  } catch (error) {
    if (error.name !== "AbortError") {
      setStatus("Could not load viewport.");
      console.error(error);
    }
  } finally {
    state.loading = false;
    draw();
  }
}

async function fetchOverview() {
  if (!state.map) return;
  const box = layout();
  const limit = Math.min(5000, Math.max(80, Math.ceil(box.height)));
  if (state.overviewAbort) state.overviewAbort.abort();
  state.overviewAbort = new AbortController();
  try {
    const classDiscrimination = classDiscriminationInput.checked ? "1" : "0";
    const url = `/api/maps/${state.map.id}/viewport?start=0&end=${state.map.totalRows}&limit=${limit}&classDiscrimination=${classDiscrimination}`;
    const response = await fetch(url, { signal: state.overviewAbort.signal });
    state.overview = await response.json();
  } catch (error) {
    if (error.name !== "AbortError") console.error(error);
  } finally {
    draw();
  }
}

async function fetchSummary() {
  if (!state.map) return;
  if (state.summaryAbort) state.summaryAbort.abort();
  state.summaryAbort = new AbortController();
  try {
    const classDiscrimination = classDiscriminationInput.checked ? "1" : "0";
    const response = await fetch(`/api/maps/${state.map.id}/summary?classDiscrimination=${classDiscrimination}`, {
      signal: state.summaryAbort.signal,
    });
    state.summary = await response.json();
    renderSummary();
  } catch (error) {
    if (error.name !== "AbortError") {
      mapInfoEl.textContent = "Could not load map information.";
      console.error(error);
    }
  }
}

function yFor(row) {
  return layout().mapTop + (row - state.viewportStart) * state.zoom;
}

function choosePowerInterval(minPixels) {
  const raw = Math.max(1, minPixels / state.zoom);
  return 10 ** Math.ceil(Math.log10(raw));
}

function chooseTickInterval(minPixels) {
  if (state.zoom < 0.25) return choosePowerInterval(minPixels);
  const raw = Math.max(1, minPixels / state.zoom);
  const power = 10 ** Math.floor(Math.log10(raw));
  for (const multiplier of [1, 2, 5, 10]) {
    const interval = multiplier * power;
    if (interval >= raw) return interval;
  }
  return power * 10;
}

function draw() {
  const box = layout();
  ctx.clearRect(0, 0, box.width, box.canvasHeight);
  ctx.fillStyle = "#101112";
  ctx.fillRect(0, 0, box.width, box.canvasHeight);

  ctx.fillStyle = "#050505";
  ctx.fillRect(box.mapLeft, box.mapTop, box.mapWidth, box.height);
  ctx.strokeStyle = "#4a4c4d";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(box.mapLeft + 0.5, box.mapTop);
  ctx.lineTo(box.mapLeft + 0.5, box.mapBottom);
  ctx.moveTo(box.mapRight + 0.5, box.mapTop);
  ctx.lineTo(box.mapRight + 0.5, box.mapBottom);
  ctx.stroke();
  drawResizeHandles(box);

  if (!state.map) {
    drawEmpty(state.loadingMaps ? "Loading maps..." : "No maps found in output/maps.");
    return;
  }

  if (state.data && Array.isArray(state.data.samples)) {
    drawSamples(box);
    drawNavigationBar(box);
    drawRightHeaderBand(box);
    drawOccurrenceScale(box);
    if (showStructureInput.checked) drawStructure(box);
    if (showWordsInput.checked) drawWords(box);
  } else {
    drawEmpty("Loading...");
  }
}

function drawNavigationBar(box) {
  ctx.fillStyle = "#060606";
  ctx.fillRect(box.navLeft, box.mapTop, box.navWidth, box.height);
  ctx.strokeStyle = "#737679";
  ctx.strokeRect(box.navLeft + 0.5, box.mapTop + 0.5, box.navWidth - 1, box.height - 1);

  if (state.overview && Array.isArray(state.overview.samples)) {
    for (const sample of state.overview.samples) {
      const y0 = box.mapTop + (sample.start / state.map.totalRows) * box.height;
      const y1 = box.mapTop + (sample.end / state.map.totalRows) * box.height;
      ctx.fillStyle = sample.color;
      ctx.fillRect(box.navLeft + 2, Math.floor(y0), box.navWidth - 4, Math.max(1, Math.ceil(y1 - y0)));
    }
  }

  const range = visibleRange();
  const y0 = box.mapTop + (range.start / state.map.totalRows) * box.height;
  const y1 = box.mapTop + (range.end / state.map.totalRows) * box.height;
  ctx.fillStyle = "rgba(214, 164, 58, 0.28)";
  ctx.fillRect(box.navLeft, y0, box.navWidth, Math.max(4, y1 - y0));
  ctx.strokeStyle = "#d6a43a";
  ctx.strokeRect(box.navLeft + 0.5, y0 + 0.5, box.navWidth - 1, Math.max(4, y1 - y0) - 1);
}

function drawRightHeaderBand(box) {
  ctx.fillStyle = "#101112";
  ctx.fillRect(box.mapRight + 1, 0, box.width - box.mapRight - 1, box.mapTop + 28);
  ctx.fillRect(0, 0, box.mapLeft - 1, box.mapTop + 28);
}

function drawResizeHandles(box) {
  ctx.strokeStyle = "#6b6e70";
  ctx.lineWidth = 1;
  for (const x of [box.mapLeft, box.mapRight]) {
    ctx.beginPath();
    ctx.moveTo(x + 0.5, box.mapTop);
    ctx.lineTo(x + 0.5, box.mapBottom);
    ctx.stroke();
  }
}

function drawEmpty(text) {
  const box = layout();
  ctx.fillStyle = "#eeeeea";
  ctx.font = `${state.fontSize}px Arial, Helvetica, sans-serif`;
  ctx.fillText(text, 18, box.mapTop + 28);
}

function drawSamples(box) {
  for (const sample of state.data.samples) {
    const y0 = yFor(sample.start);
    const y1 = yFor(sample.end);
    if (y1 < box.mapTop || y0 > box.mapBottom) continue;
    ctx.fillStyle = sample.color;
    ctx.fillRect(box.mapLeft, Math.floor(y0), box.mapWidth, Math.max(1, Math.ceil(y1 - y0)));
  }
}

function drawOccurrenceScale(box) {
  const range = visibleRange();
  const interval = chooseTickInterval(46);
  const first = Math.ceil(range.start / interval) * interval;
  ctx.strokeStyle = "#d8d3c5";
  ctx.fillStyle = "#eeeeea";
  ctx.font = `${state.fontSize}px Arial, Helvetica, sans-serif`;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";

  for (let value = first; value <= range.end; value += interval) {
    const y = yFor(value);
    ctx.beginPath();
    ctx.moveTo(box.mapLeft, Math.round(y) + 0.5);
    ctx.lineTo(box.axisTickX, Math.round(y) + 0.5);
    ctx.stroke();
    ctx.fillText(String(value), box.axisLabelX, y);
  }

  ctx.fillStyle = "#a9aaa4";
  ctx.textBaseline = "top";
  ctx.fillText("occ", box.axisLabelX, box.mapTop + 6);
}

function drawBracket(box, x, y0, y1, label, color, labelQueue) {
  const minY = Math.max(box.mapTop, y0);
  const maxY = Math.min(box.mapBottom, y1);
  if (maxY - minY < 4) return;
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(box.mapRight, minY + 0.5);
  ctx.lineTo(x, minY + 0.5);
  ctx.lineTo(x, maxY + 0.5);
  ctx.lineTo(box.mapRight, maxY + 0.5);
  ctx.stroke();
  const preferredY = (minY + maxY) / 2;
  const labelY = Math.min(
    maxY - state.fontSize * 0.6,
    Math.max(minY + state.fontSize * 0.6, preferredY, box.mapTop + 28),
  );
  if (labelY < box.mapTop + 28) return;
  labelQueue.push({ text: label, x: x + 12, y: labelY, color, baseline: "middle" });
}

function drawStructure(box) {
  ctx.font = `${state.fontSize}px Arial, Helvetica, sans-serif`;
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";

  const availableSegments = state.data?.segments || {};
  const columns = [
    ["sentence", "Sent", box.sentenceX, "#b7b2df"],
    ["paragraph", "Par", box.paragraphX, "#9ccfbe"],
    ["chapter", "Ch", box.chapterX, "#e4c978"],
  ].filter(([key]) => Array.isArray(availableSegments[key]) && availableSegments[key].length > 0);

  const labelQueue = [];
  for (const [, label, x, color] of columns) {
    labelQueue.push({ text: label, x: x + 12, y: box.mapTop + 6, color, baseline: "top" });
  }
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";

  for (const [key, prefix, x, color] of columns) {
    drawScaledBrackets(box, key, prefix, x, color, labelQueue);
  }

  for (const label of labelQueue) {
    drawOutlinedText(label.text, label.x, label.y, label.color, label.baseline);
  }
}

function drawScaledBrackets(box, key, prefix, x, color, labelQueue) {
  const segments = state.data.segments && state.data.segments[key] ? state.data.segments[key] : [];
  if (segments.length === 0) return;
  const minPixels = state.fontSize + 12;
  const scale = bracketValueScale(segments, minPixels);
  const brackets = scale === 1 ? segments.map((segment) => ({
    start: segment.start,
    end: segment.end,
    label: `${prefix} ${segment.value}`,
  })) : groupedBrackets(segments, prefix, scale);

  for (const bracket of brackets) {
    const y0 = yFor(bracket.start);
    const y1 = yFor(bracket.end);
    if (y1 - y0 < 4) continue;
    drawBracket(box, x, y0, y1, bracket.label, color, labelQueue);
  }
}

function drawOutlinedText(text, x, y, color, baseline = "middle") {
  ctx.save();
  ctx.textAlign = "left";
  ctx.textBaseline = baseline;
  ctx.lineJoin = "round";
  ctx.miterLimit = 2;
  ctx.lineWidth = 2;
  ctx.strokeStyle = "rgba(0, 0, 0, 0.9)";
  ctx.strokeText(text, x, y);
  ctx.fillStyle = color;
  ctx.fillText(text, x, y);
  ctx.restore();
}

function bracketValueScale(segments, minPixels) {
  const totalPixels = segments.reduce((sum, segment) => {
    return sum + Math.max(0, yFor(segment.end) - yFor(segment.start));
  }, 0);
  const values = new Set(segments.map((segment) => segment.value));
  const averagePixels = totalPixels / Math.max(1, values.size);
  if (averagePixels >= minPixels) return 1;
  const raw = minPixels / Math.max(0.001, averagePixels);
  return 10 ** Math.ceil(Math.log10(raw));
}

function groupedBrackets(segments, prefix, scale) {
  const groups = [];
  let current = null;
  for (const segment of segments) {
    const bucketStart = Math.floor((segment.value - 1) / scale) * scale + 1;
    const bucketEnd = bucketStart + scale - 1;
    const bucketKey = `${bucketStart}:${bucketEnd}`;
    if (!current || current.key !== bucketKey) {
      current = {
        key: bucketKey,
        start: segment.start,
        end: segment.end,
        label: `${prefix} ${compactRange(bucketStart, bucketEnd)}`,
      };
      groups.push(current);
    } else {
      current.end = segment.end;
    }
  }
  return groups;
}

function compactRange(start, end) {
  return `${compactNumber(start)}-${compactNumber(end)}`;
}

function compactNumber(value) {
  if (Math.abs(value) >= 1000000) {
    return `${trimDecimal(value / 1000000)}m`;
  }
  if (Math.abs(value) >= 1000) {
    return `${trimDecimal(value / 1000)}k`;
  }
  return String(value);
}

function trimDecimal(value) {
  return value.toFixed(value % 1 === 0 ? 0 : 1).replace(".0", "");
}

function drawWords(box) {
  if (!state.data || state.data.mode !== "rows") return;
  if (state.zoom < state.fontSize + 4) return;
  ctx.font = `${state.fontSize}px Arial, Helvetica, sans-serif`;
  ctx.textBaseline = "middle";
  ctx.textAlign = "left";
  for (const row of state.data.samples) {
    const y = yFor(row.start) + state.zoom / 2;
    if (y < box.mapTop - state.fontSize || y > box.mapBottom + state.fontSize) continue;
    const word = row.word || "";
    const detail = wordDetailText(row);
    const x = box.mapLeft + 10;
    ctx.lineWidth = 3;
    ctx.strokeStyle = "#000000";
    ctx.fillStyle = "#ffffff";
    ctx.strokeText(detail, x, y);
    ctx.fillText(detail, x, y);
  }
}

function wordDetailText(row) {
  const parts = [row.word || ""];
  if (row.wordClass) parts.push(row.wordClass);
  if (typeof row.metricValue === "number") {
    parts.push(`${metricLabel(row.metric || state.map?.metric)} ${formatMetricValue(row.metricValue, row.metric || state.map?.metric)}`);
  }
  return parts.join(" | ");
}

function metricLabel(metric) {
  if (metric === "book_freq" || metric === "book_frequency" || metric === "frequency_total_F" || metric === "book_frequency_F") return "book_freq";
  if (metric === "book_avg_dev" || metric === "book_frequency_average_deviation" || metric === "book_frequency_deviation_pct") return "book_avg_dev";
  if (metric === "book_med_dev" || metric === "book_frequency_median_deviation") return "book_med_dev";
  if (metric === "fic_ngram_total_freq" || metric === "ngram_total_frequency") return "fic_ngram_total_freq";
  if (metric === "fic_ngram_total_avg_dev" || metric === "ngram_total_average_deviation") return "fic_ngram_total_avg_dev";
  if (metric === "fic_ngram_total_med_dev") return "fic_ngram_total_med_dev";
  if (metric === "fic_ngram_prepub_10y_freq" || metric === "ngram_pre_publication_10y_frequency") return "fic_ngram_prepub_10y_freq";
  if (metric === "fic_ngram_prepub_10y_avg_dev" || metric === "ngram_pre_publication_10y_average_deviation") return "fic_ngram_prepub_10y_avg_dev";
  if (metric === "fic_ngram_prepub_10y_med_dev") return "fic_ngram_prepub_10y_med_dev";
  if (metric === "fic_ngram_99_19_freq" || metric === "ngram_recent_1999_2019_frequency") return "fic_ngram_99_19_freq";
  if (metric === "fic_ngram_99_19_avg_dev" || metric === "ngram_recent_1999_2019_average_deviation") return "fic_ngram_99_19_avg_dev";
  if (metric === "fic_ngram_99_19_med_dev") return "fic_ngram_99_19_med_dev";
  return String(metric || "Value").replaceAll("_", " ");
}

function formatMetricValue(value, metric) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "";
  const isDeviation = metricLabel(metric).toLowerCase().includes("dev");
  const sign = isDeviation && numeric > 0 ? "+" : "";
  const abs = Math.abs(numeric);
  if (abs >= 100) return `${sign}${numeric.toFixed(1)}`;
  if (abs >= 10) return `${sign}${numeric.toFixed(2)}`;
  if (abs >= 1) return `${sign}${numeric.toFixed(3)}`;
  if (abs === 0) return "0";
  return `${sign}${numeric.toPrecision(4)}`;
}

function zoomAt(factor, screenY) {
  if (!state.map) return;
  const box = layout();
  const mapY = Math.max(0, Math.min(box.height, screenY - box.mapTop));
  const anchor = state.viewportStart + mapY / state.zoom;
  state.zoom = Math.max(0.001, Math.min(80, state.zoom * factor));
  state.viewportStart = anchor - mapY / state.zoom;
  clampViewport();
  scheduleFetch();
}

canvas.addEventListener("wheel", (event) => {
  event.preventDefault();
  const factor = Math.exp(-event.deltaY * 0.001);
  zoomAt(factor, event.offsetY);
}, { passive: false });

canvas.addEventListener("mousedown", (event) => {
  const box = layout();
  if (isOnNavigationBar(event.offsetX, box)) {
    state.navigating = true;
    navigateBarTo(event.offsetY);
    canvas.style.cursor = "ns-resize";
    return;
  }
  if (isOnResizeHandle(event.offsetX, box)) {
    state.resizingPanel = true;
    canvas.style.cursor = "col-resize";
    return;
  }
  state.dragging = true;
  state.lastY = event.clientY;
});

window.addEventListener("mouseup", () => {
  state.dragging = false;
  state.navigating = false;
  state.resizingPanel = false;
  canvas.style.cursor = "";
});

window.addEventListener("mousemove", (event) => {
  if (state.navigating) {
    const canvasY = event.clientY - canvas.getBoundingClientRect().top;
    navigateBarTo(canvasY);
    return;
  }
  if (state.resizingPanel) {
    const box = layout();
    const canvasX = event.clientX - canvas.getBoundingClientRect().left;
    const fromLeft = Math.abs(canvasX - box.mapLeft) <= Math.abs(canvasX - box.mapRight);
    state.panelSize = fromLeft ? canvasX / LEFT_PANEL_RATIO : box.width - canvasX;
    syncPanelControl();
    scheduleFetch();
    return;
  }
  if (!state.dragging) return;
  const delta = event.clientY - state.lastY;
  state.lastY = event.clientY;
  state.viewportStart -= delta / state.zoom;
  clampViewport();
  scheduleFetch();
});

canvas.addEventListener("mousemove", (event) => {
  if (state.dragging || state.resizingPanel || state.navigating) return;
  const box = layout();
  canvas.style.cursor = isOnNavigationBar(event.offsetX, box) ? "ns-resize" : isOnResizeHandle(event.offsetX, box) ? "col-resize" : "";
});

function isOnResizeHandle(x, box) {
  return Math.abs(x - box.mapLeft) <= 7 || Math.abs(x - box.mapRight) <= 7;
}

function isOnNavigationBar(x, box) {
  return x >= box.navLeft - 4 && x <= box.navRight + 4;
}

function navigateBarTo(y) {
  if (!state.map) return;
  const box = layout();
  const clampedY = Math.max(box.mapTop, Math.min(box.mapBottom, y));
  const ratio = (clampedY - box.mapTop) / box.height;
  const visibleRows = box.height / state.zoom;
  state.viewportStart = ratio * state.map.totalRows - visibleRows / 2;
  clampViewport();
  scheduleFetch();
}

function renderSummary() {
  syncSummaryVisibility();
  if (!state.summary) {
    mapInfoEl.textContent = state.map ? "Loading map information..." : "";
    return;
  }
  const summary = state.summary;
  const metric = metricLabel(summary.metric);
  const isDeviation = metric.toLowerCase().includes("dev");
  const biblio = summary.bibliographic || {};
  const counts = summary.wordCounts || {};
  const frequency = summary.frequency || {};
  const deviation = summary.deviation || {};
  const rows = [
    ["Map", summary.mapType || metric],
    ["Author", biblio.author || "Unknown"],
    ["Publication", biblio.publicationYear || "Unknown"],
    ["Edition", biblio.edition || "Unknown"],
    ["Total words", formatInteger(counts.total)],
    ["Functional", formatInteger(counts.functional)],
    ["Lexical", formatInteger(counts.lexical)],
    ["Functional ratio", formatPercent(counts.functionalRatio)],
  ];

  const metricRows = isDeviation
    ? [
        ["Max positive", formatMetricValue(deviation.maxPositive, summary.metric)],
        ["Max negative", formatMetricValue(deviation.maxNegative, summary.metric)],
        ["Average deviation", formatMetricValue(deviation.average, summary.metric)],
        ["Average red", formatNumber(deviation.averageRgb?.red, 1)],
        ["Average green", formatNumber(deviation.averageRgb?.green, 1)],
        ["Average blue", formatNumber(deviation.averageRgb?.blue, 1)],
      ]
    : [
        ...classStatsRows(frequency.classStats || {}, summary.metric),
        ["B/W average", `${formatNumber(frequency.grayscaleAverage0To1000, 1)} / 1000`],
      ];

  mapInfoEl.innerHTML = `
    <h2>${escapeHtml(summary.book || "Current Map")}</h2>
    ${definitionList(rows)}
    <h3>${escapeHtml(metric)}</h3>
    ${definitionList(metricRows)}
  `;
}

function syncSummaryVisibility() {
  mapInfoEl.classList.toggle("hidden", !state.summaryVisible);
  toggleSummaryButton.textContent = state.summaryVisible ? "Hide summary" : "Show summary";
  toggleSummaryButton.setAttribute("aria-pressed", state.summaryVisible ? "true" : "false");
}

function classStatsRows(classStats, metric) {
  const rows = [];
  for (const className of Object.keys(classStats).sort()) {
    const stats = classStats[className];
    const label = className.charAt(0).toUpperCase() + className.slice(1);
    rows.push([`${label} max`, formatMetricValue(stats.max, metric)]);
    rows.push([`${label} min`, formatMetricValue(stats.min, metric)]);
    rows.push([`${label} avg`, formatMetricValue(stats.average, metric)]);
  }
  return rows;
}

function definitionList(rows) {
  return `<dl>${rows.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}</dl>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatInteger(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString() : "Unknown";
}

function formatNumber(value, digits = 3) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "Unknown";
  return number.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "Unknown";
  return `${(number * 100).toFixed(2)}%`;
}

bookSelect.addEventListener("change", () => selectBook(bookSelect.value));
mapTypeSelect.addEventListener("change", () => selectMap(mapTypeSelect.value));
document.getElementById("zoomIn").addEventListener("click", () => {
  const box = layout();
  zoomAt(1.6, box.mapTop + box.height / 2);
});
document.getElementById("zoomOut").addEventListener("click", () => {
  const box = layout();
  zoomAt(1 / 1.6, box.mapTop + box.height / 2);
});
document.getElementById("fit").addEventListener("click", fitMap);
document.getElementById("actualSize").addEventListener("click", actualSizeMap);
toggleSummaryButton.addEventListener("click", () => {
  state.summaryVisible = !state.summaryVisible;
  syncSummaryVisibility();
});
fontSizeInput.addEventListener("input", () => {
  state.fontSize = Number(fontSizeInput.value);
  fontSizeValue.value = String(state.fontSize);
  draw();
});
panelSizeInput.addEventListener("input", () => {
  state.panelSize = Number(panelSizeInput.value);
  syncPanelControl();
  scheduleFetch();
});
showWordsInput.addEventListener("change", draw);
showStructureInput.addEventListener("change", draw);
classDiscriminationInput.addEventListener("change", () => {
  state.data = null;
  state.overview = null;
  state.summary = null;
  renderSummary();
  fetchSummary();
  scheduleOverviewFetch();
  scheduleFetch();
});
window.addEventListener("resize", resizeCanvas);

resizeCanvas();
syncSummaryVisibility();
loadMaps(new URLSearchParams(window.location.search).get("map") || "");
