const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const chooseFileButton = document.getElementById("chooseFile");
const fileNameEl = document.getElementById("fileName");
const corpusSelect = document.getElementById("corpusSelect");
const metricSelect = document.getElementById("metricSelect");
const mapWidthInput = document.getElementById("mapWidth");
const mapScaleSelect = document.getElementById("mapScale");
const publicationYearInput = document.getElementById("publicationYear");
const generateMapsButton = document.getElementById("generateMaps");
const generationStatusEl = document.getElementById("generationStatus");
const generationResultsEl = document.getElementById("generationResults");

const uploadState = {
  options: null,
  selectedFile: null,
};

function setGenerationStatus(text, isError = false) {
  generationStatusEl.textContent = text;
  generationStatusEl.classList.toggle("error", isError);
}

function setSelectedFile(file) {
  if (file && !file.name.toLowerCase().endsWith(".txt")) {
    uploadState.selectedFile = null;
    fileNameEl.textContent = "No file selected";
    dropZone.classList.remove("has-file");
    setGenerationStatus("Use a .txt file.", true);
    return;
  }
  uploadState.selectedFile = file || null;
  fileNameEl.textContent = file ? file.name : "No file selected";
  if (file && !publicationYearInput.value) {
    const inferredYear = file.name.match(/(^|\D)(1[5-9]\d{2}|20\d{2})(?!\d)/);
    if (inferredYear) publicationYearInput.value = inferredYear[2];
  }
  dropZone.classList.toggle("has-file", Boolean(file));
  setGenerationStatus("");
  refreshMetricAvailability();
}

async function loadGenerationOptions() {
  generateMapsButton.disabled = true;
  try {
    const response = await fetch("/api/generation-options");
    uploadState.options = await readJsonResponse(response, "Generation options unavailable.");
    populateCorpusOptions();
    populateMetricOptions();
    refreshMetricAvailability();
    generateMapsButton.disabled = false;
  } catch (error) {
    setGenerationStatus(error.message || "Generation options unavailable.", true);
    console.error(error);
  }
}

function populateCorpusOptions() {
  const corpora = uploadState.options?.corpora || [];
  corpusSelect.innerHTML = "";
  for (const corpus of corpora) {
    const option = document.createElement("option");
    option.value = corpus.id;
    option.textContent = corpus.label;
    corpusSelect.appendChild(option);
  }
  corpusSelect.value = uploadState.options?.defaults?.corpusId || corpora[0]?.id || "";
}

function populateMetricOptions() {
  metricSelect.innerHTML = "";
  for (const metric of uploadState.options?.metrics || []) {
    const option = document.createElement("option");
    option.value = metric.name;
    option.textContent = metric.label;
    option.title = metric.definition || metric.label;
    option.dataset.requires = metric.requiresCorpusSource || "";
    option.selected = Boolean(metric.defaultSelected);
    metricSelect.appendChild(option);
  }
}

function selectedCorpusOption() {
  return (uploadState.options?.corpora || []).find((corpus) => corpus.id === corpusSelect.value) || null;
}

function refreshMetricAvailability() {
  const corpus = selectedCorpusOption();
  const sources = corpus?.sources || {};
  const dynamicSources = corpus?.dynamicSources || [];
  const hasPublicationYear = publicationYearInput.value.trim() !== "";
  for (const option of metricSelect.options) {
    const required = option.dataset.requires || "";
    const staticAvailable = Object.prototype.hasOwnProperty.call(sources, required);
    const dynamicAvailable = dynamicSources.includes(required);
    const available = !required
      || staticAvailable
      || (dynamicAvailable && (required !== "-10y" || hasPublicationYear));
    option.disabled = !available;
    if (!available) option.selected = false;
  }

  if (selectedMetricNames().length === 0) {
    const firstAvailable = [...metricSelect.options].find((option) => !option.disabled);
    if (firstAvailable) firstAvailable.selected = true;
  }
}

function selectedMetricNames() {
  return [...metricSelect.selectedOptions]
    .filter((option) => !option.disabled)
    .map((option) => option.value);
}

async function generateSelectedMaps() {
  if (!uploadState.selectedFile) {
    setGenerationStatus("Choose a .txt file.", true);
    return;
  }
  const metrics = selectedMetricNames();
  if (metrics.length === 0) {
    setGenerationStatus("Select at least one map.", true);
    return;
  }

  generateMapsButton.disabled = true;
  generationResultsEl.textContent = "";
  setGenerationStatus("Generating...");
  try {
    const content = await uploadState.selectedFile.text();
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: uploadState.selectedFile.name,
        content,
        corpusId: corpusSelect.value,
        metrics,
        width: Number(mapWidthInput.value),
        scale: mapScaleSelect.value,
        publicationYear: publicationYearInput.value ? Number(publicationYearInput.value) : null,
      }),
    });
    const payload = await readJsonResponse(response, "Generation failed.");
    renderResults(payload);
  } catch (error) {
    setGenerationStatus(error.message || "Generation failed.", true);
    console.error(error);
  } finally {
    generateMapsButton.disabled = false;
  }
}

function renderResults(payload) {
  const maps = payload.maps || [];
  const failures = payload.failures || [];
  setGenerationStatus(`Generated ${maps.length} map${maps.length === 1 ? "" : "s"}.`, failures.length > 0);
  const mapLinks = maps.map((map) => {
    const href = `/viewer.html?map=${encodeURIComponent(map.id)}`;
    return `<a href="${href}">${escapeHtml(map.mapType || map.metric)}</a>`;
  }).join("");
  const failureText = failures.map((failure) => (
    `<p class="error-line">${escapeHtml(failure.metric)}: ${escapeHtml(failure.error)}</p>`
  )).join("");
  const backfillText = (payload.ngramBackfill || [])
    .filter((entry) => Number(entry.addedWords || 0) > 0)
    .map((entry) => `${entry.source}: ${entry.addedWords}`)
    .join(", ");
  generationResultsEl.innerHTML = `
    <div class="result-links">${mapLinks}</div>
    ${backfillText ? `<p>Ngram data updated: ${escapeHtml(backfillText)}</p>` : ""}
    ${payload.occurrenceCsv ? `<p>${escapeHtml(payload.occurrenceCsv)}</p>` : ""}
    ${payload.wordMetricsCsv ? `<p>${escapeHtml(payload.wordMetricsCsv)}</p>` : ""}
    ${failureText}
  `;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

chooseFileButton.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});
fileInput.addEventListener("change", () => {
  setSelectedFile(fileInput.files?.[0] || null);
});
for (const eventName of ["dragenter", "dragover"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("drag-over");
  });
}
for (const eventName of ["dragleave", "drop"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("drag-over");
  });
}
dropZone.addEventListener("drop", (event) => {
  setSelectedFile(event.dataTransfer?.files?.[0] || null);
});
corpusSelect.addEventListener("change", refreshMetricAvailability);
publicationYearInput.addEventListener("input", refreshMetricAvailability);
generateMapsButton.addEventListener("click", generateSelectedMaps);

loadGenerationOptions();
