const detectedGrid = document.querySelector("#detected-grid");
const detectedCount = document.querySelector("#detected-count");
const cameraAlerts = document.querySelector("#camera-alerts");
const detectButton = document.querySelector("#detect-button");
const saveButton = document.querySelector("#save-button");
const stressButton = document.querySelector("#stress-button");
const stressCycles = document.querySelector("#stress-cycles");
const stressResults = document.querySelector("#stress-results");

const LABEL_PATTERN = /^[A-Za-z0-9-]+$/;

const ICONS = {
  alert: '<svg class="ic ic-16 ico" viewBox="0 0 24 24"><path d="M12 3 2 21h20L12 3Z"/><line x1="12" y1="10" x2="12" y2="14"/><circle cx="12" cy="17.5" r="0.6" fill="currentColor" stroke="none"/></svg>',
  camera: '<svg class="ic ic-32 ico" viewBox="0 0 24 24"><path d="M14.5 5 16 8h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3l1.5-3h5Z"/><circle cx="12" cy="13.5" r="3"/></svg>',
  check: '<svg class="ic ic-16 ico" viewBox="0 0 24 24"><polyline points="4 12 10 18 20 6"/></svg>',
  refresh: '<svg class="ic ic-16" viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-3-6.7"/><polyline points="21 4 21 9 16 9"/></svg>',
  spinner: '<svg class="ic ic-22" viewBox="0 0 24 24" style="animation:spin .9s linear infinite"><path d="M21 12a9 9 0 1 1-9-9"/></svg>',
};

let detected = [];
let configuredByIndex = new Map();
const previewState = new Map();
const draftMappingState = new Map();
let detectionSignature = "";
let detectionRevision = 0;
let detectBusy = false;
let saveBusy = false;
let stressBusy = false;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderNote(tone, html) {
  const toneClass = tone ? ` is-${tone}` : "";
  const icon = tone === "danger" || tone === "warn" ? ICONS.alert : ICONS.check;
  return `<div class="note${toneClass}">${icon}<div class="body">${html}</div></div>`;
}

function stateFor(index) {
  if (!previewState.has(index)) {
    previewState.set(index, { busy: false, url: "", error: "", revision: 0 });
  }
  return previewState.get(index);
}

function cameraKey(camera) {
  return [
    camera.index,
    camera.identity_strategy || "",
    camera.stable_id || "",
    camera.label || "",
  ].join("|");
}

function signatureFor(cameras) {
  return cameras.map(cameraKey).join("||");
}

function clearPreviewState() {
  for (const state of previewState.values()) {
    if (state.url) {
      URL.revokeObjectURL(state.url);
    }
  }
  previewState.clear();
}

function clearDraftMappingState() {
  draftMappingState.clear();
}

function snapshotDraftMappingState() {
  for (const card of detectedGrid.querySelectorAll("[data-camera-key]")) {
    const key = card.dataset.cameraKey;
    if (!key) continue;
    draftMappingState.set(key, {
      label: card.querySelector(".js-label")?.value ?? "",
      notes: card.querySelector(".js-notes")?.value ?? "",
      stress: !!card.querySelector(".js-stress")?.checked,
    });
  }
}

function hasFreshPreview(camera) {
  const state = previewState.get(cameraKey(camera));
  return !!state?.url && state.revision === detectionRevision && !state.busy && !state.error;
}

function canSaveMapping() {
  return detected.length > 0 && detected.every(hasFreshPreview);
}

function updateActionButtons() {
  detectButton.disabled = detectBusy;
  saveButton.disabled = saveBusy || !canSaveMapping();
  stressButton.disabled = stressBusy || !detected.length;
}

function defaultLabelFor(camera, position) {
  const draft = draftMappingState.get(cameraKey(camera));
  if (draft) {
    return draft.label;
  }
  const existing = configuredByIndex.get(camera.index);
  return existing?.label || `station${position + 1}`;
}

function notesFor(camera) {
  const draft = draftMappingState.get(cameraKey(camera));
  if (draft) {
    return draft.notes;
  }
  return configuredByIndex.get(camera.index)?.notes || "";
}

function stressSelectedFor(camera) {
  const draft = draftMappingState.get(cameraKey(camera));
  return draft ? draft.stress : true;
}

function renderAlerts(tone, html) {
  if (!html) {
    cameraAlerts.innerHTML = "";
    return;
  }
  cameraAlerts.innerHTML = renderNote(tone, html);
}

function renderCamera(camera, position) {
  const key = cameraKey(camera);
  const state = stateFor(key);
  const isFallback = !!camera.identity_warning;
  const warnings = [
    ...(camera.warnings || []),
    ...(isFallback ? ["Camera identity can change after reboot or replug. Confirm the preview before saving."] : []),
  ];
  const frame = state.busy
    ? `<div class="ph-state">${ICONS.spinner}<strong>Capturing preview…</strong></div><span class="shimmer"></span>`
    : state.url
      ? `<img class="frame-img" src="${state.url}" alt="Fresh preview for camera index ${camera.index}">`
      : `<div class="ph-state">${ICONS.camera}<strong>No preview captured</strong></div>`;

  return `
    <article class="setup-card" data-camera-index="${camera.index}" data-camera-key="${escapeHtml(key)}">
      <header class="verify-card-head">
        <div>
          <h2>${escapeHtml(camera.label)}</h2>
          <div class="verify-meta">
            <span class="mono">index ${escapeHtml(camera.index)}</span>
            <span class="sep">·</span>
            <span class="${isFallback ? "id-strategy is-warn" : "id-strategy mono"}">${isFallback ? ICONS.alert : ""}${escapeHtml(camera.identity_strategy)}</span>
          </div>
        </div>
        <label class="checkline">
          <input class="js-stress" type="checkbox" ${stressSelectedFor(camera) ? "checked" : ""}>
          <span>Stress</span>
        </label>
      </header>
      <div class="verify-frame${state.error ? " is-error" : ""}">
        ${frame}
      </div>
      <div class="verify-body">
        ${warnings.map((warning) => renderNote("warn", `<strong>Identity warning.</strong><span class="meta">${escapeHtml(warning)}</span>`)).join("")}
        ${state.error ? renderNote("danger", `<strong>Preview failed.</strong><span class="meta">${escapeHtml(state.error)}</span>`) : ""}
        <div class="field">
          <label class="lbl" for="station-label-${camera.index}">Station label</label>
          <input id="station-label-${camera.index}" class="input is-mono js-label" type="text" value="${escapeHtml(defaultLabelFor(camera, position))}" autocomplete="off">
        </div>
        <div class="field">
          <label class="lbl" for="camera-notes-${camera.index}">Notes <span class="opt">optional</span></label>
          <input id="camera-notes-${camera.index}" class="input js-notes" type="text" value="${escapeHtml(notesFor(camera))}" autocomplete="off" placeholder="e.g. Logitech C310 over left bench">
        </div>
      </div>
      <footer class="verify-actions">
        <button class="btn js-preview" type="button" ${state.busy ? "disabled" : ""}>
          ${state.busy ? ICONS.spinner : ICONS.refresh}
          Capture preview
        </button>
      </footer>
    </article>
  `;
}

function renderDetected({ preserveDrafts = true } = {}) {
  if (preserveDrafts) {
    snapshotDraftMappingState();
  }
  detectedCount.textContent = detected.length ? `${detected.length} detected` : "none detected";
  if (!detected.length) {
    detectedGrid.innerHTML = renderNote("danger", "<strong>No cameras detected.</strong><span class=\"meta\">Check USB connections and camera permissions, then detect again.</span>");
    updateActionButtons();
    return;
  }
  detectedGrid.innerHTML = detected.map(renderCamera).join("");
  updateActionButtons();
}

function applyDetectedPayload(payload, { clearPreviews = false, clearDrafts = false } = {}) {
  const nextDetected = payload.detected || [];
  const nextSignature = signatureFor(nextDetected);
  detected = nextDetected;
  configuredByIndex = new Map((payload.configured || []).map((camera) => [camera.last_seen_index, camera]));
  detectionSignature = nextSignature;
  detectionRevision += 1;
  if (clearPreviews) {
    clearPreviewState();
  }
  if (clearDrafts) {
    clearDraftMappingState();
  }
  renderDetected({ preserveDrafts: !clearDrafts });
}

async function fetchDetectedPayload() {
  const response = await fetch("/api/cameras/detected", { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error?.message || "Could not detect cameras");
  }
  return payload;
}

async function loadDetected() {
  detectBusy = true;
  detectButton.classList.add("is-loading");
  clearPreviewState();
  clearDraftMappingState();
  stressResults.innerHTML = "";
  renderAlerts("", "");
  renderDetected({ preserveDrafts: false });
  try {
    applyDetectedPayload(await fetchDetectedPayload(), { clearPreviews: true, clearDrafts: true });
  } catch (error) {
    detected = [];
    detectionSignature = "";
    detectionRevision += 1;
    clearPreviewState();
    clearDraftMappingState();
    renderDetected({ preserveDrafts: false });
    renderAlerts("danger", `<strong>Camera detection failed.</strong><span class="meta">${escapeHtml(error.message)}</span>`);
  } finally {
    detectBusy = false;
    detectButton.classList.remove("is-loading");
    updateActionButtons();
  }
}

async function refreshBeforeAction() {
  const payload = await fetchDetectedPayload();
  const nextSignature = signatureFor(payload.detected || []);
  if (nextSignature !== detectionSignature) {
    applyDetectedPayload(payload, { clearPreviews: true, clearDrafts: true });
    stressResults.innerHTML = "";
    renderAlerts("warn", "<strong>Camera list changed.</strong><span class=\"meta\">Capture preview again before saving or testing cameras.</span>");
    return false;
  }
  configuredByIndex = new Map((payload.configured || []).map((camera) => [camera.last_seen_index, camera]));
  return true;
}

async function capturePreview(cameraIndex) {
  try {
    if (!(await refreshBeforeAction())) {
      return;
    }
  } catch (error) {
    renderAlerts("danger", `<strong>Camera detection failed.</strong><span class="meta">${escapeHtml(error.message)}</span>`);
    return;
  }

  const camera = detected.find((item) => item.index === cameraIndex);
  if (!camera) {
    renderAlerts("warn", "<strong>Camera list changed.</strong><span class=\"meta\">Click Detect and capture preview again.</span>");
    return;
  }
  const key = cameraKey(camera);
  const state = stateFor(key);
  state.busy = true;
  state.error = "";
  renderDetected();
  try {
    const response = await fetch("/api/cameras/detected/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ camera_index: cameraIndex }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error?.message || "Could not capture preview");
    }
    const blob = await response.blob();
    if (state.url) {
      URL.revokeObjectURL(state.url);
    }
    state.url = URL.createObjectURL(blob);
    state.revision = detectionRevision;
  } catch (error) {
    state.error = error.message || "Could not capture preview";
  } finally {
    state.busy = false;
    renderDetected();
  }
}

function mappingsFromCards() {
  const mappings = [];
  const seen = new Set();
  for (const card of detectedGrid.querySelectorAll("[data-camera-index]")) {
    const cameraIndex = Number(card.dataset.cameraIndex);
    const camera = detected.find((item) => item.index === cameraIndex);
    if (!camera || !hasFreshPreview(camera)) {
      throw new Error("Capture a fresh preview for every detected camera before saving.");
    }
    const label = card.querySelector(".js-label")?.value.trim() || "";
    const notes = card.querySelector(".js-notes")?.value.trim() || "";
    if (!LABEL_PATTERN.test(label)) {
      throw new Error("Station labels may use only letters, numbers, and hyphens.");
    }
    if (seen.has(label)) {
      throw new Error(`Duplicate station label: ${label}`);
    }
    seen.add(label);
    mappings.push({ camera_index: cameraIndex, label, notes });
  }
  if (!mappings.length) {
    throw new Error("Detect at least one camera before saving.");
  }
  return mappings;
}

async function saveMapping() {
  try {
    if (!(await refreshBeforeAction())) {
      return;
    }
  } catch (error) {
    renderAlerts("danger", `<strong>Camera detection failed.</strong><span class="meta">${escapeHtml(error.message)}</span>`);
    return;
  }

  let mappings;
  try {
    mappings = mappingsFromCards();
  } catch (error) {
    renderAlerts("danger", `<strong>Mapping not saved.</strong><span class="meta">${escapeHtml(error.message)}</span>`);
    return;
  }

  saveBusy = true;
  saveButton.classList.add("is-loading");
  updateActionButtons();
  try {
    const response = await fetch("/api/cameras/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mappings }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "Could not save camera mapping");
    }
    configuredByIndex = new Map((payload.configured || []).map((camera) => [camera.last_seen_index, camera]));
    clearDraftMappingState();
    renderDetected({ preserveDrafts: false });
    renderAlerts("info", "<strong>Camera mapping saved.</strong><span class=\"meta\">Startup verification is required again before experiments can start.</span>");
  } catch (error) {
    renderAlerts("danger", `<strong>Mapping not saved.</strong><span class="meta">${escapeHtml(error.message)}</span>`);
  } finally {
    saveBusy = false;
    saveButton.classList.remove("is-loading");
    updateActionButtons();
  }
}

function selectedStressIndexes() {
  return [...detectedGrid.querySelectorAll("[data-camera-index]")]
    .filter((card) => card.querySelector(".js-stress")?.checked)
    .map((card) => Number(card.dataset.cameraIndex));
}

function renderStressResults(payload) {
  const rows = (payload.results || []).map((result) => {
    const tone = result.ok ? "info" : "danger";
    const failureText = (result.failures || []).map((failure) => `<span class="meta">${escapeHtml(failure)}</span>`).join("");
    return renderNote(tone, `<strong>${escapeHtml(result.label)}: ${escapeHtml(result.passed)}/${escapeHtml(result.cycles)} passed</strong>${failureText}`);
  });
  stressResults.innerHTML = rows.join("");
}

async function runStressTest() {
  try {
    if (!(await refreshBeforeAction())) {
      return;
    }
  } catch (error) {
    stressResults.innerHTML = renderNote("danger", `<strong>Camera detection failed.</strong><span class="meta">${escapeHtml(error.message)}</span>`);
    return;
  }

  const camera_indexes = selectedStressIndexes();
  const cycles = Number(stressCycles.value);
  if (!camera_indexes.length) {
    stressResults.innerHTML = renderNote("danger", "<strong>Select at least one camera.</strong>");
    return;
  }

  stressBusy = true;
  stressButton.classList.add("is-loading");
  updateActionButtons();
  stressResults.innerHTML = renderNote("info", "<strong>Stress test running.</strong><span class=\"meta\">Cameras are tested one at a time.</span>");
  try {
    const response = await fetch("/api/cameras/stress-test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ camera_indexes, cycles }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "Stress test failed");
    }
    renderStressResults(payload);
  } catch (error) {
    stressResults.innerHTML = renderNote("danger", `<strong>Stress test failed.</strong><span class="meta">${escapeHtml(error.message)}</span>`);
  } finally {
    stressBusy = false;
    stressButton.classList.remove("is-loading");
    updateActionButtons();
  }
}

detectedGrid.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const card = button.closest("[data-camera-index]");
  if (!card) return;
  if (button.classList.contains("js-preview")) {
    capturePreview(Number(card.dataset.cameraIndex));
  }
});

detectButton.addEventListener("click", loadDetected);
saveButton.addEventListener("click", saveMapping);
stressButton.addEventListener("click", runStressTest);

loadDetected();
