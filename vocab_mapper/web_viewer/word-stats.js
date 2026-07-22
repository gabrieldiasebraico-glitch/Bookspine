const savedCsvSelect = document.getElementById("savedCsvSelect");
const csvInput = document.getElementById("csvInput");
const chooseCsvButton = document.getElementById("chooseCsv");
const csvNameEl = document.getElementById("csvName");
const rowFilterInput = document.getElementById("rowFilter");
const filterColumnSelect = document.getElementById("filterColumn");
const filterTextInput = document.getElementById("filterText");
const filterMinInput = document.getElementById("filterMin");
const filterMaxInput = document.getElementById("filterMax");
const addFilterButton = document.getElementById("addFilter");
const activeFiltersEl = document.getElementById("activeFilters");
const columnSelect = document.getElementById("columnSelect");
const sortColumnSelect = document.getElementById("sortColumn");
const sortDirectionSelect = document.getElementById("sortDirection");
const colorColumnSelect = document.getElementById("colorColumn");
const colorScaleSelect = document.getElementById("colorScale");
const lowColorInput = document.getElementById("lowColor");
const midColorInput = document.getElementById("midColor");
const highColorInput = document.getElementById("highColor");
const statsStatusEl = document.getElementById("statsStatus");
const statsTable = document.getElementById("statsTable");
const kdeGroupSelect = document.getElementById("kdeGroup");
const kdeMetricSelect = document.getElementById("kdeMetric");
const kdeConfigButton = document.getElementById("kdeConfigButton");
const kdeConfigPanel = document.getElementById("kdeConfigPanel");
const kdeScaleSelect = document.getElementById("kdeScale");
const kdeYScaleSelect = document.getElementById("kdeYScale");
const kdeVerticalLinesInput = document.getElementById("kdeVerticalLines");
const kdeHorizontalLinesInput = document.getElementById("kdeHorizontalLines");
const kdeMeanLineInput = document.getElementById("kdeMeanLine");
const kdeMedianLineInput = document.getElementById("kdeMedianLine");
const kdeCanvas = document.getElementById("kdeCanvas");
const kdeCtx = kdeCanvas.getContext("2d");

const statsState = {
  headers: [],
  rows: [],
  savedFiles: [],
  filters: [],
};

const MAX_RENDERED_ROWS = 2000;

async function loadSavedCsvList() {
  try {
    const response = await fetch("/api/word-stats");
    const payload = await readJsonResponse(response, "Saved CSVs unavailable.");
    statsState.savedFiles = payload.files || [];
    savedCsvSelect.innerHTML = "";
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "";
    savedCsvSelect.appendChild(blank);
    for (const file of statsState.savedFiles) {
      const option = document.createElement("option");
      option.value = file.id;
      option.textContent = file.name;
      savedCsvSelect.appendChild(option);
    }
  } catch (error) {
    setStatsStatus(error.message || "Saved CSVs unavailable.", true);
    console.error(error);
  }
}

async function loadSavedCsv(fileId) {
  if (!fileId) return;
  try {
    const response = await fetch(`/api/word-stats/${encodeURIComponent(fileId)}`);
    const payload = await readJsonResponse(response, "Could not load CSV.");
    loadCsvText(payload.content || "", payload.path || payload.name || "Saved CSV");
  } catch (error) {
    setStatsStatus(error.message || "Could not load CSV.", true);
    console.error(error);
  }
}

function loadCsvText(text, name) {
  const parsed = parseCsv(text);
  statsState.headers = parsed.headers;
  statsState.rows = parsed.rows;
  csvNameEl.textContent = name;
  populateColumnControls();
  renderTable();
}

function populateColumnControls() {
  columnSelect.innerHTML = "";
  sortColumnSelect.innerHTML = "";
  colorColumnSelect.innerHTML = "";
  filterColumnSelect.innerHTML = "";
  kdeMetricSelect.innerHTML = "";

  const noColor = document.createElement("option");
  noColor.value = "";
  noColor.textContent = "";
  colorColumnSelect.appendChild(noColor);

  for (const header of statsState.headers) {
    const visibleOption = document.createElement("option");
    visibleOption.value = header;
    visibleOption.textContent = header;
    visibleOption.selected = true;
    columnSelect.appendChild(visibleOption);

    const filterOption = document.createElement("option");
    filterOption.value = header;
    filterOption.textContent = header;
    filterColumnSelect.appendChild(filterOption);

    const sortOption = document.createElement("option");
    sortOption.value = header;
    sortOption.textContent = header;
    sortColumnSelect.appendChild(sortOption);

    const colorOption = document.createElement("option");
    colorOption.value = header;
    colorOption.textContent = header;
    colorColumnSelect.appendChild(colorOption);

    const kdeOption = document.createElement("option");
    kdeOption.value = header;
    kdeOption.textContent = header;
    kdeMetricSelect.appendChild(kdeOption);
  }

  const preferredMetric = statsState.headers.includes("book_freq")
    ? "book_freq"
    : statsState.headers.find((header) => parseNumber(statsState.rows[0]?.[header]) !== null) || "";
  sortColumnSelect.value = preferredMetric || statsState.headers[0] || "";
  colorColumnSelect.value = preferredMetric;
  kdeMetricSelect.value = preferredMetric;
  statsState.filters = [];
  renderActiveFilters();
}

function visibleColumns() {
  const selected = [...columnSelect.selectedOptions].map((option) => option.value);
  return selected.length ? selected : statsState.headers;
}

function filteredRows() {
  const filter = rowFilterInput.value.trim().toLowerCase();
  let rows = statsState.rows;
  if (filter) {
    const columns = visibleColumns();
    rows = rows.filter((row) => columns.some((header) => String(row[header] ?? "").toLowerCase().includes(filter)));
  }

  for (const activeFilter of statsState.filters) {
    rows = rows.filter((row) => rowPassesFilter(row, activeFilter));
  }

  const sortColumn = sortColumnSelect.value;
  const direction = sortDirectionSelect.value === "desc" ? -1 : 1;
  if (sortColumn) {
    rows = [...rows].sort((left, right) => compareValues(left[sortColumn], right[sortColumn]) * direction);
  }
  return rows;
}

function rowPassesFilter(row, filter) {
  const rawValue = row[filter.column] ?? "";
  const textValue = String(rawValue).toLowerCase();
  if (filter.text && !textValue.includes(filter.text.toLowerCase())) return false;
  const number = parseNumber(rawValue);
  if (filter.min !== "" && filter.min !== null) {
    if (number === null || number < Number(filter.min)) return false;
  }
  if (filter.max !== "" && filter.max !== null) {
    if (number === null || number > Number(filter.max)) return false;
  }
  return true;
}

function compareValues(left, right) {
  const leftNumber = parseNumber(left);
  const rightNumber = parseNumber(right);
  if (leftNumber !== null && rightNumber !== null) return leftNumber - rightNumber;
  return String(left ?? "").localeCompare(String(right ?? ""), undefined, { numeric: true });
}

function renderTable() {
  if (!statsState.headers.length) {
    statsTable.innerHTML = "";
    setStatsStatus("");
    return;
  }

  const columns = visibleColumns();
  const rows = filteredRows();
  const shownRows = rows.slice(0, MAX_RENDERED_ROWS);
  const colorColumn = colorColumnSelect.value;
  const colorScale = buildColorScale(rows, colorColumn);

  const headerHtml = columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("");
  const bodyHtml = shownRows.map((row) => {
    const cells = columns.map((column) => {
      const value = row[column] ?? "";
      const style = colorColumn && column === colorColumn ? colorScale.style(value) : "";
      return `<td${style}>${escapeHtml(value)}</td>`;
    }).join("");
    return `<tr>${cells}</tr>`;
  }).join("");

  statsTable.innerHTML = `<thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody>`;
  setStatsStatus(`Showing ${shownRows.length.toLocaleString()} of ${rows.length.toLocaleString()} rows`);
  drawKdeChart(rows);
}

function buildColorScale(rows, column) {
  const values = rows.map((row) => parseNumber(row[column])).filter((value) => value !== null);
  const transformed = values.map((value) => transformScaleValue(value, colorScaleSelect.value));
  const min = Math.min(...transformed);
  const max = Math.max(...transformed);
  const low = hexToRgb(lowColorInput.value);
  const mid = hexToRgb(midColorInput.value);
  const high = hexToRgb(highColorInput.value);
  return {
    style(value) {
      const number = parseNumber(value);
      if (number === null || !Number.isFinite(min) || !Number.isFinite(max) || min === max) return "";
      const scaled = transformScaleValue(number, colorScaleSelect.value);
      const ratio = (scaled - min) / (max - min);
      const color = ratio <= 0.5
        ? interpolateColor(low, mid, ratio * 2)
        : interpolateColor(mid, high, (ratio - 0.5) * 2);
      const contrast = readableTextColor(color);
      return ` style="background:${rgbCss(color)};color:${contrast}"`;
    },
  };
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (quoted) {
      if (char === '"' && next === '"') {
        cell += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        cell += char;
      }
      continue;
    }

    if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(cell);
      cell = "";
    } else if (char === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else if (char !== "\r") {
      cell += char;
    }
  }
  row.push(cell);
  if (row.length > 1 || row[0] !== "") rows.push(row);

  const headers = (rows.shift() || []).map((header, index) => header || `Column ${index + 1}`);
  return {
    headers,
    rows: rows.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]))),
  };
}

function parseNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(String(value).replace(/,/g, ""));
  return Number.isFinite(number) ? number : null;
}

function transformScaleValue(value, scale) {
  if (scale !== "log") return value;
  return Math.sign(value) * Math.log1p(Math.abs(value));
}

function inverseScaleValue(value, scale) {
  if (scale !== "log") return value;
  return Math.sign(value) * Math.expm1(Math.abs(value));
}

function hexToRgb(hex) {
  const normalized = hex.replace("#", "");
  return {
    r: parseInt(normalized.slice(0, 2), 16),
    g: parseInt(normalized.slice(2, 4), 16),
    b: parseInt(normalized.slice(4, 6), 16),
  };
}

function interpolateColor(start, end, amount) {
  return {
    r: Math.round(start.r + (end.r - start.r) * amount),
    g: Math.round(start.g + (end.g - start.g) * amount),
    b: Math.round(start.b + (end.b - start.b) * amount),
  };
}

function rgbCss(color) {
  return `rgb(${color.r}, ${color.g}, ${color.b})`;
}

function readableTextColor(color) {
  const luminance = (0.299 * color.r + 0.587 * color.g + 0.114 * color.b) / 255;
  return luminance > 0.62 ? "#101112" : "#ffffff";
}

function addActiveFilter() {
  const column = filterColumnSelect.value;
  if (!column) return;
  const text = filterTextInput.value.trim();
  const min = filterMinInput.value.trim();
  const max = filterMaxInput.value.trim();
  if (!text && !min && !max) {
    setStatsStatus("Set text, min, or max before adding a filter.", true);
    return;
  }
  statsState.filters.push({ column, text, min, max });
  filterTextInput.value = "";
  filterMinInput.value = "";
  filterMaxInput.value = "";
  renderActiveFilters();
  renderTable();
}

function renderActiveFilters() {
  activeFiltersEl.innerHTML = statsState.filters.map((filter, index) => {
    const parts = [filter.column];
    if (filter.text) parts.push(`contains "${filter.text}"`);
    if (filter.min) parts.push(`>= ${filter.min}`);
    if (filter.max) parts.push(`<= ${filter.max}`);
    return `
      <span class="filter-chip">
        ${escapeHtml(parts.join(" "))}
        <button type="button" data-filter-index="${index}" aria-label="Remove filter">x</button>
      </span>
    `;
  }).join("");
}

function drawKdeChart(rows) {
  resizeKdeCanvas();
  const width = kdeCanvas.clientWidth;
  const height = kdeCanvas.clientHeight;
  kdeCtx.clearRect(0, 0, width, height);
  kdeCtx.fillStyle = "#101112";
  kdeCtx.fillRect(0, 0, width, height);

  const series = kdeSeries(rows);
  if (series.points.length < 2) {
    drawKdeMessage("No numeric KDE data");
    return;
  }

  const margin = { left: 54, right: 18, top: 18, bottom: 38 };
  const plotW = Math.max(1, width - margin.left - margin.right);
  const plotH = Math.max(1, height - margin.top - margin.bottom);
  const xMin = series.xMin;
  const xMax = series.xMax;
  const yMax = Math.max(...series.points.map((point) => point.y), 1e-12);
  const xScale = kdeScaleSelect.value;
  const yScale = kdeYScaleSelect.value;
  const txMin = transformScaleValue(xMin, xScale);
  const txMax = transformScaleValue(xMax, xScale);
  const tyMin = transformScaleValue(0, yScale);
  const tyMax = transformScaleValue(yMax, yScale);

  function xFor(value) {
    const transformed = transformScaleValue(value, xScale);
    return margin.left + ((transformed - txMin) / Math.max(1e-12, txMax - txMin)) * plotW;
  }
  function yFor(value) {
    const transformed = transformScaleValue(value, yScale);
    return margin.top + plotH - ((transformed - tyMin) / Math.max(1e-12, tyMax - tyMin)) * plotH;
  }

  drawKdeGrid(margin, plotW, plotH, xMin, xMax, yMax, xFor, yFor, yScale);

  kdeCtx.strokeStyle = "#d6a43a";
  kdeCtx.lineWidth = 2;
  kdeCtx.beginPath();
  series.points.forEach((point, index) => {
    const x = xFor(point.x);
    const y = yFor(point.y);
    if (index === 0) kdeCtx.moveTo(x, y);
    else kdeCtx.lineTo(x, y);
  });
  kdeCtx.stroke();

  if (kdeMeanLineInput.checked) drawReferenceLine("mean", series.mean, xFor, margin, plotH, "#9ccfbe");
  if (kdeMedianLineInput.checked) drawReferenceLine("median", series.median, xFor, margin, plotH, "#b7b2df");

  kdeCtx.strokeStyle = "#737679";
  kdeCtx.strokeRect(margin.left + 0.5, margin.top + 0.5, plotW, plotH);
}

function kdeSeries(rows) {
  const metric = kdeMetricSelect.value || "book_freq";
  const group = kdeGroupSelect.value;
  let values = rows
    .filter((row) => group === "mixed" || String(row.word_class || "").toLowerCase() === group)
    .map((row) => ({
      value: parseNumber(row[metric]),
      weight: Math.max(1, parseNumber(row.book_count) || 1),
    }))
    .filter((item) => item.value !== null);

  if (values.length > 800) {
    values = values
      .sort((left, right) => Math.abs(right.weight) - Math.abs(left.weight))
      .slice(0, 800);
  }
  if (values.length < 2) return { points: [], xMin: 0, xMax: 1, mean: 0, median: 0 };

  const rawValues = values.map((item) => item.value);
  const xMin = Math.min(...rawValues);
  const xMax = Math.max(...rawValues);
  const bandwidth = silvermanBandwidth(rawValues) || Math.max(1e-9, (xMax - xMin) / 30);
  const totalWeight = values.reduce((sum, item) => sum + item.weight, 0);
  const points = [];
  const steps = 180;
  for (let index = 0; index < steps; index += 1) {
    const x = xMin + ((xMax - xMin) * index) / (steps - 1);
    const density = values.reduce((sum, item) => {
      const z = (x - item.value) / bandwidth;
      return sum + item.weight * Math.exp(-0.5 * z * z);
    }, 0) / (totalWeight * bandwidth * Math.sqrt(2 * Math.PI));
    points.push({ x, y: density });
  }
  return {
    points,
    xMin,
    xMax,
    mean: weightedMean(values),
    median: weightedMedian(values),
  };
}

function silvermanBandwidth(values) {
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / Math.max(1, values.length - 1);
  const stdDev = Math.sqrt(variance);
  return 1.06 * stdDev * values.length ** -0.2;
}

function weightedMean(items) {
  const totalWeight = items.reduce((sum, item) => sum + item.weight, 0);
  return items.reduce((sum, item) => sum + item.value * item.weight, 0) / totalWeight;
}

function weightedMedian(items) {
  const ordered = [...items].sort((left, right) => left.value - right.value);
  const totalWeight = ordered.reduce((sum, item) => sum + item.weight, 0);
  let running = 0;
  for (const item of ordered) {
    running += item.weight;
    if (running >= totalWeight / 2) return item.value;
  }
  return ordered[ordered.length - 1].value;
}

function drawKdeGrid(margin, plotW, plotH, xMin, xMax, yMax, xFor, yFor, yScale) {
  const verticalLines = Number(kdeVerticalLinesInput.value) || 0;
  const horizontalLines = Number(kdeHorizontalLinesInput.value) || 0;
  const tyMin = transformScaleValue(0, yScale);
  const tyMax = transformScaleValue(yMax, yScale);
  kdeCtx.font = "12px Arial, Helvetica, sans-serif";
  kdeCtx.fillStyle = "#a9aaa4";
  kdeCtx.strokeStyle = "#2e3032";
  kdeCtx.lineWidth = 1;

  for (let index = 0; index <= verticalLines; index += 1) {
    const ratio = verticalLines ? index / verticalLines : 0;
    const value = xMin + (xMax - xMin) * ratio;
    const x = xFor(value);
    kdeCtx.beginPath();
    kdeCtx.moveTo(x + 0.5, margin.top);
    kdeCtx.lineTo(x + 0.5, margin.top + plotH);
    kdeCtx.stroke();
    kdeCtx.fillText(compactMetric(value), x - 12, margin.top + plotH + 22);
  }

  for (let index = 0; index <= horizontalLines; index += 1) {
    const ratio = horizontalLines ? index / horizontalLines : 0;
    const value = inverseScaleValue(tyMin + (tyMax - tyMin) * ratio, yScale);
    const y = yFor(value);
    kdeCtx.beginPath();
    kdeCtx.moveTo(margin.left, y + 0.5);
    kdeCtx.lineTo(margin.left + plotW, y + 0.5);
    kdeCtx.stroke();
    kdeCtx.fillText(compactMetric(value), 8, y + 4);
  }
}

function drawReferenceLine(label, value, xFor, margin, plotH, color) {
  const x = xFor(value);
  kdeCtx.strokeStyle = color;
  kdeCtx.fillStyle = color;
  kdeCtx.lineWidth = 1.5;
  kdeCtx.beginPath();
  kdeCtx.moveTo(x + 0.5, margin.top);
  kdeCtx.lineTo(x + 0.5, margin.top + plotH);
  kdeCtx.stroke();
  kdeCtx.fillText(label, x + 5, margin.top + 14);
}

function resizeKdeCanvas() {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.floor(kdeCanvas.clientWidth * ratio));
  const height = Math.max(1, Math.floor(kdeCanvas.clientHeight * ratio));
  if (kdeCanvas.width !== width || kdeCanvas.height !== height) {
    kdeCanvas.width = width;
    kdeCanvas.height = height;
  }
  kdeCtx.setTransform(ratio, 0, 0, ratio, 0, 0);
}

function drawKdeMessage(text) {
  kdeCtx.fillStyle = "#eeeeea";
  kdeCtx.font = "13px Arial, Helvetica, sans-serif";
  kdeCtx.fillText(text, 18, 30);
}

function compactMetric(value) {
  const abs = Math.abs(value);
  if (abs >= 1000) return value.toExponential(1);
  if (abs >= 1) return value.toFixed(2).replace(/\.?0+$/, "");
  if (abs === 0) return "0";
  return value.toPrecision(2);
}

function setStatsStatus(text, isError = false) {
  statsStatusEl.textContent = text;
  statsStatusEl.classList.toggle("error", isError);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

chooseCsvButton.addEventListener("click", () => csvInput.click());
csvInput.addEventListener("change", async () => {
  const file = csvInput.files?.[0];
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".csv")) {
    setStatsStatus("Use a CSV file.", true);
    return;
  }
  loadCsvText(await file.text(), file.name);
});
savedCsvSelect.addEventListener("change", () => loadSavedCsv(savedCsvSelect.value));
for (const control of [
  rowFilterInput,
  filterColumnSelect,
  filterTextInput,
  filterMinInput,
  filterMaxInput,
  columnSelect,
  sortColumnSelect,
  sortDirectionSelect,
  colorColumnSelect,
  colorScaleSelect,
  lowColorInput,
  midColorInput,
  highColorInput,
  kdeGroupSelect,
  kdeMetricSelect,
  kdeScaleSelect,
  kdeYScaleSelect,
  kdeVerticalLinesInput,
  kdeHorizontalLinesInput,
  kdeMeanLineInput,
  kdeMedianLineInput,
]) {
  control.addEventListener("input", renderTable);
  control.addEventListener("change", renderTable);
}
addFilterButton.addEventListener("click", addActiveFilter);
activeFiltersEl.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-filter-index]");
  if (!button) return;
  statsState.filters.splice(Number(button.dataset.filterIndex), 1);
  renderActiveFilters();
  renderTable();
});
kdeConfigButton.addEventListener("click", () => {
  kdeConfigPanel.classList.toggle("hidden");
});
window.addEventListener("resize", () => drawKdeChart(filteredRows()));

loadSavedCsvList();
