const form = document.querySelector("#experiment-form");
const cameraInput = document.querySelector("#camera-label");
const cameraPicker = document.querySelector("#camera-picker");
const previewButton = document.querySelector("#preview-button");
const previewRecaptureButton = document.querySelector("#preview-recapture-button");
const startButton = document.querySelector("#start-button");
const nameInput = document.querySelector("#experiment-name");
const nameHint = document.querySelector("#name-hint");
const nameNote = document.querySelector("#name-note");
const cameraNote = document.querySelector("#camera-note");
const formNote = document.querySelector("#form-note");
const intervalInput = document.querySelector("#interval-minutes");
const durationInput = document.querySelector("#duration-hours");
const operatorInput = document.querySelector("#operator");
const identityStrategyEl = document.querySelector("#identity-strategy");
const previewFrame = document.querySelector("#preview-frame");
const previewCameraLabel = document.querySelector("#preview-camera-label");
const previewFoot = document.querySelector("#preview-foot");
const pfTime = document.querySelector("#pf-time");
const rsFrames = document.querySelector("#rs-frames");
const rsFinish = document.querySelector("#rs-finish");
const rsStorage = document.querySelector("#rs-storage");

const BYTES_PER_FRAME_MB = 0.05;

const ICONS = {
  alert: '<svg class="ic ic-16 ico" viewBox="0 0 24 24"><path d="M12 3 2 21h20L12 3Z"/><line x1="12" y1="10" x2="12" y2="14"/><circle cx="12" cy="17.5" r="0.6" fill="currentColor" stroke="none"/></svg>',
  info: '<svg class="ic ic-16 ico" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><line x1="12" y1="11" x2="12" y2="16"/><circle cx="12" cy="8" r="0.7" fill="currentColor" stroke="none"/></svg>',
  check: '<svg class="ic ic-16 ico" viewBox="0 0 24 24"><polyline points="4 12 10 18 20 6"/></svg>',
  spinner: '<svg class="ic ic-22" viewBox="0 0 24 24" style="animation:spin .9s linear infinite"><path d="M21 12a9 9 0 1 1-9-9"/></svg>',
  image: '<svg class="ic ic-32 ico" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" r="1.8"/><polyline points="3 17 9 12 13 16 21 9"/></svg>',
  refresh: '<svg class="ic" viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-3-6.7"/><polyline points="21 4 21 9 16 9"/></svg>',
};

let cameras = [];
let busyCameraInfo = new Map();
let nameCheckTimer = null;
let nameCheckRequest = 0;
let recentlyStartedNameCheckKey = "";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderNote(target, tone, html) {
  if (!html) {
    target.hidden = true;
    target.innerHTML = "";
    return;
  }
  const toneClass = tone ? ` is-${tone}` : "";
  const icon = tone === "danger" ? ICONS.alert
            : tone === "info"   ? ICONS.check
            :                     ICONS.info;
  target.hidden = false;
  target.innerHTML = `<div class="note${toneClass}">${icon}<div class="body">${html}</div></div>`;
}

function clearNote(target) {
  target.hidden = true;
  target.innerHTML = "";
}

function camRow(camera) {
  const selected = cameraInput.value === camera.label;
  const busyInfo = busyCameraInfo.get(camera.label);
  const isBusy = !!busyInfo;
  const isFallback = camera.identity_strategy !== "hardware_id";
  const selectedCameraIsBusy = busyCameraInfo.has(cameraInput.value);
  const firstIdleCamera = cameras.find((candidate) => !busyCameraInfo.has(candidate.label));
  const isTabStop = !isBusy && (
    selected
    || !cameraInput.value
    || selectedCameraIsBusy
    || !cameras.some((candidate) => candidate.label === cameraInput.value)
  ) && (!firstIdleCamera || firstIdleCamera.label === camera.label || selected);

  const meta = isBusy
    ? `
        <span class="pill is-running"><span class="dot"></span>Running</span>
        <span class="sep">·</span>
        <span>busy with <span class="mono">${escapeHtml(busyInfo.experiment_name || "an experiment")}</span></span>
      `
    : `
        <span class="pill is-idle"><span class="dot"></span>Idle</span>
        <span class="sep">·</span>
        ${
          isFallback
            ? `<span class="id-strategy is-warn"><svg class="ic" viewBox="0 0 24 24"><path d="M12 3 2 21h20L12 3Z"/><line x1="12" y1="10" x2="12" y2="14"/><circle cx="12" cy="17.5" r="0.6" fill="currentColor" stroke="none"/></svg> ${escapeHtml(camera.identity_strategy || "fallback")}</span>`
            : `<span class="id-strategy mono">${escapeHtml(camera.identity_strategy)}</span>`
        }
      `;

  const classes = ["cam"];
  if (selected) classes.push("is-selected");
  if (isBusy) classes.push("is-busy");

  return `
    <div class="${classes.join(" ")}" role="radio" aria-checked="${selected}" aria-disabled="${isBusy}" tabindex="${isTabStop ? "0" : "-1"}" data-camera-label="${escapeHtml(camera.label)}">
      <span class="cam-radio"></span>
      <div class="cam-info">
        <div class="cam-name">${escapeHtml(camera.label)}<span class="id-tag">${escapeHtml(camera.stable_id || camera.identity_strategy || "")}</span></div>
        <div class="cam-meta">${meta}</div>
      </div>
    </div>
  `;
}

function renderCameraPicker() {
  if (!cameras.length) {
    cameraPicker.innerHTML = `<div class="cam" aria-disabled="true"><span class="cam-radio"></span><div class="cam-info"><div class="cam-name">No cameras configured.</div></div></div>`;
    return;
  }
  cameraPicker.innerHTML = cameras.map(camRow).join("");
}

function selectCamera(label, { preserveMessage = false, preserveRecentStart = false } = {}) {
  const nextLabel = label || "";
  if (!preserveRecentStart && cameraInput.value !== nextLabel) {
    recentlyStartedNameCheckKey = "";
  }
  cameraInput.value = nextLabel;
  renderCameraPicker();
  updateIdentityStrategy();
  updateCameraAvailability({ preserveMessage });
  updatePreviewCameraLabel();
  scheduleNameCheck();
}

function selectableCameraRows() {
  return [...cameraPicker.querySelectorAll(".cam[data-camera-label]")]
    .filter((row) => row.getAttribute("aria-disabled") !== "true");
}

function focusCameraRow(label) {
  const row = selectableCameraRows().find((candidate) => candidate.dataset.cameraLabel === label);
  if (row && row.getAttribute("aria-disabled") !== "true") {
    for (const candidate of selectableCameraRows()) {
      candidate.tabIndex = candidate === row ? 0 : -1;
    }
    row.focus();
  }
}

function moveCameraFocus(currentRow, direction) {
  const rows = selectableCameraRows();
  if (!rows.length) {
    return;
  }
  const currentIndex = Math.max(0, rows.indexOf(currentRow));
  const nextIndex = (currentIndex + direction + rows.length) % rows.length;
  const nextLabel = rows[nextIndex].dataset.cameraLabel;
  selectCamera(nextLabel, { preserveMessage: true });
  focusCameraRow(nextLabel);
}

function updateIdentityStrategy() {
  const camera = cameras.find((c) => c.label === cameraInput.value);
  if (!camera) {
    identityStrategyEl.innerHTML = `<span class="id-strategy mono">—</span>`;
    return;
  }
  if (camera.identity_strategy === "hardware_id") {
    identityStrategyEl.innerHTML = `<span class="id-strategy mono">${escapeHtml(camera.identity_strategy)}</span>`;
  } else {
    identityStrategyEl.innerHTML = `<span class="id-strategy is-warn" title="Identity uses ${escapeHtml(camera.identity_strategy)} — may change after replug"><svg class="ic" viewBox="0 0 24 24"><path d="M12 3 2 21h20L12 3Z"/><line x1="12" y1="10" x2="12" y2="14"/><circle cx="12" cy="17.5" r="0.6" fill="currentColor" stroke="none"/></svg> ${escapeHtml(camera.identity_strategy || "fallback")}</span>`;
  }
}

function updatePreviewCameraLabel() {
  previewCameraLabel.textContent = cameraInput.value || "—";
}

function updateCameraAvailability({ preserveMessage = false } = {}) {
  const label = cameraInput.value;
  const camera = cameras.find((c) => c.label === label);
  const busyInfo = busyCameraInfo.get(label);
  const isBusy = !!busyInfo;
  const noCameraSelected = !label;

  previewButton.disabled = isBusy || noCameraSelected;
  previewRecaptureButton.disabled = isBusy || noCameraSelected;
  startButton.disabled = isBusy || noCameraSelected;

  if (isBusy) {
    if (!preserveMessage) {
      renderNote(cameraNote, "danger",
        `<strong>This camera is busy.</strong><span class="meta">A run named <span class="mono">${escapeHtml(busyInfo.experiment_name || "an experiment")}</span> is in progress. Pick another camera or stop it first.</span>`
      );
    }
  } else if (camera && camera.identity_strategy !== "hardware_id") {
    renderNote(cameraNote, "warn",
      `<strong>Camera identity uses ${escapeHtml(camera.identity_strategy || "fallback")}.</strong><span class="meta">Identity may change after a replug — verify before long runs.</span>`
    );
  } else {
    clearNote(cameraNote);
  }

  if (noCameraSelected && cameras.length > 0 && !preserveMessage) {
    renderNote(formNote, "danger",
      `<strong>No camera selected.</strong><span class="meta">Choose a camera from the list above.</span>`
    );
  } else if (!preserveMessage && !isBusy) {
    clearNote(formNote);
  }
}

async function loadCameras({ preserveMessage = false, preserveSelection = true } = {}) {
  const previousSelection = preserveSelection ? cameraInput.value : "";
  const [cameraResponse, statusResponse] = await Promise.all([
    fetch("/api/cameras", { cache: "no-store" }),
    fetch("/api/status", { cache: "no-store" }),
  ]);
  const cameraPayload = await cameraResponse.json();
  const statusPayload = await statusResponse.json();
  if (!cameraResponse.ok) throw new Error(cameraPayload.error?.message || "Could not load cameras");
  if (!statusResponse.ok) throw new Error(statusPayload.error?.message || "Could not load station status");

  cameras = cameraPayload.cameras || [];
  busyCameraInfo = new Map();
  for (const station of statusPayload.stations || []) {
    if (station.state === "running") {
      busyCameraInfo.set(station.camera_label, {
        experiment_name: station.experiment_name,
        experiment_id: station.experiment_id,
      });
    }
  }

  let nextSelection = previousSelection;
  if (!nextSelection || !cameras.some((c) => c.label === nextSelection)) {
    const firstIdle = cameras.find((c) => !busyCameraInfo.has(c.label));
    nextSelection = firstIdle ? firstIdle.label : (cameras[0]?.label || "");
  }
  selectCamera(nextSelection, { preserveMessage, preserveRecentStart: true });
}

function payloadFromForm() {
  const data = new FormData(form);
  return {
    camera_label: String(data.get("camera_label") || ""),
    name: String(data.get("name") || "").trim(),
    interval_minutes: Number(data.get("interval_minutes")),
    duration_hours: Number(data.get("duration_hours")),
    operator: String(data.get("operator") || "").trim(),
    notes: String(data.get("notes") || "").trim(),
  };
}

function validatePayload(payload) {
  if (!payload.camera_label) {
    throw new Error("Choose a camera.");
  }
  if (!payload.name || !/[A-Za-z0-9]/.test(payload.name)) {
    throw new Error("Experiment name must contain at least one letter or number.");
  }
  if (!(payload.interval_minutes > 0)) {
    throw new Error("Interval must be greater than 0.");
  }
  if (!(payload.duration_hours > 0)) {
    throw new Error("Duration must be greater than 0.");
  }
  if (busyCameraInfo.has(payload.camera_label)) {
    throw new Error("That camera already has a running experiment.");
  }
}

function nameCheckKey(payload) {
  return JSON.stringify([payload.camera_label, payload.name]);
}

function scheduleNameCheck() {
  clearTimeout(nameCheckTimer);
  nameCheckTimer = setTimeout(checkExperimentName, 250);
}

async function checkExperimentName() {
  const requestId = ++nameCheckRequest;
  const payload = payloadFromForm();
  if (!payload.camera_label || !payload.name || !/[A-Za-z0-9]/.test(payload.name)) {
    clearNote(nameNote);
    return;
  }
  if (recentlyStartedNameCheckKey === nameCheckKey(payload)) {
    clearNote(nameNote);
    return;
  }

  try {
    const response = await fetch("/api/experiments/name-check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        camera_label: payload.camera_label,
        name: payload.name,
      }),
    });
    const responsePayload = await response.json();
    if (requestId !== nameCheckRequest) {
      return;
    }
    if (!response.ok || !responsePayload.duplicate) {
      clearNote(nameNote);
      return;
    }
    if (recentlyStartedNameCheckKey === nameCheckKey(payload)) {
      clearNote(nameNote);
      return;
    }
    renderNote(nameNote, "warn",
      `<strong>Name already used today on this camera.</strong><span class="meta">Starting will create <span class="mono">${escapeHtml(responsePayload.next_folder_name)}</span> — original data is preserved.</span>`
    );
  } catch {
    if (requestId === nameCheckRequest) {
      clearNote(nameNote);
    }
  }
}

function updateRunSummary() {
  const interval = Number(intervalInput.value);
  const duration = Number(durationInput.value);
  if (!(interval > 0) || !(duration > 0)) {
    rsFrames.textContent = "—";
    rsFinish.textContent = "—";
    rsStorage.textContent = "—";
    return;
  }
  const frames = Math.floor((duration * 60) / interval);
  const finishMs = Date.now() + duration * 3600 * 1000;
  const finishDate = new Date(finishMs);
  const pad = (n) => String(n).padStart(2, "0");
  const finishLabel = `${pad(finishDate.getHours())}:${pad(finishDate.getMinutes())}`;
  const storageMb = frames * BYTES_PER_FRAME_MB;
  const storageLabel = storageMb < 1
    ? `${(storageMb * 1024).toFixed(0)} KB`
    : storageMb < 1024
      ? `${storageMb.toFixed(storageMb < 10 ? 1 : 0)} MB`
      : `${(storageMb / 1024).toFixed(2)} GB`;

  rsFrames.textContent = String(frames);
  rsFinish.textContent = finishLabel;
  rsStorage.textContent = storageLabel;
}

function setPreviewState(state, payload = {}) {
  previewFrame.dataset.state = state;
  previewFrame.className = `ph-frame is-${state}`;
  if (state === "empty") {
    previewFrame.innerHTML = `
      <div class="ph-state">
        ${ICONS.image}
        <strong>No preview yet</strong>
        <span>Click <em>Preview frame</em> to capture from the selected camera.</span>
      </div>
    `;
    previewFoot.hidden = true;
  } else if (state === "loading") {
    previewFrame.innerHTML = `
      <div class="shimmer"></div>
      <div class="ph-state">
        ${ICONS.spinner}
        <strong>Capturing preview…</strong>
        <span>Connecting to ${escapeHtml(cameraInput.value || "camera")}</span>
      </div>
    `;
    previewFoot.hidden = true;
  } else if (state === "success") {
    previewFrame.innerHTML = `
      <img class="frame-img" src="${payload.url}" alt="Latest preview for ${escapeHtml(cameraInput.value)}">
      <span class="overlay-tl">${escapeHtml(payload.label)}</span>
    `;
    previewFoot.hidden = false;
    pfTime.textContent = payload.label;
  } else if (state === "error") {
    previewFrame.innerHTML = `
      <div class="ph-state is-error">
        <svg class="ic ic-22 ico" viewBox="0 0 24 24"><path d="M12 3 2 21h20L12 3Z"/><line x1="12" y1="10" x2="12" y2="14"/><circle cx="12" cy="17.5" r="0.6" fill="currentColor" stroke="none"/></svg>
        <strong>Preview failed</strong>
        <span>${escapeHtml(payload.message || "Could not capture a frame.")}</span>
        <button type="button" class="btn btn-sm" id="preview-retry-button" style="margin-top:6px">${ICONS.refresh} Retry</button>
      </div>
    `;
    previewFoot.hidden = true;
    const retry = document.querySelector("#preview-retry-button");
    if (retry) retry.addEventListener("click", preview);
  }
}

async function preview() {
  const payload = payloadFromForm();
  if (!payload.camera_label) {
    setPreviewState("error", { message: "Choose a camera first." });
    return;
  }
  if (busyCameraInfo.has(payload.camera_label)) {
    setPreviewState("error", { message: "That camera already has a running experiment." });
    return;
  }

  setPreviewState("loading");
  previewButton.classList.add("is-loading");
  previewButton.disabled = true;
  previewRecaptureButton.classList.add("is-loading");
  previewRecaptureButton.disabled = true;

  try {
    const response = await fetch("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ camera_label: payload.camera_label }),
    });
    if (!response.ok) {
      const errorPayload = await response.json();
      throw new Error(errorPayload.error?.message || "Preview failed");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    const label = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    setPreviewState("success", { url, label });
  } catch (error) {
    setPreviewState("error", { message: error.message });
  } finally {
    previewButton.classList.remove("is-loading");
    previewRecaptureButton.classList.remove("is-loading");
    updateCameraAvailability({ preserveMessage: true });
  }
}

async function startExperiment(event) {
  event.preventDefault();
  const payload = payloadFromForm();
  try {
    validatePayload(payload);
  } catch (error) {
    renderNote(formNote, "danger", `<strong>${escapeHtml(error.message)}</strong>`);
    return;
  }

  startButton.disabled = true;
  startButton.classList.add("is-loading");
  let refreshedAvailability = false;
  try {
    const response = await fetch("/api/experiments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const responsePayload = await response.json();
    if (!response.ok) {
      renderNote(formNote, "danger",
        `<strong>${escapeHtml(responsePayload.error?.message || "Could not start experiment")}</strong>`
      );
      if (responsePayload.error?.code === "camera_busy") {
        await loadCameras({ preserveMessage: true, preserveSelection: true });
        refreshedAvailability = true;
      }
      return;
    }
    renderNote(formNote, "info",
      `<strong>Experiment started.</strong><span class="meta">${escapeHtml(payload.camera_label)} · <span class="mono">${escapeHtml(payload.name)}</span> · runs for ${escapeHtml(String(payload.duration_hours))}h.</span>`
    );
    recentlyStartedNameCheckKey = nameCheckKey(payload);
    nameCheckRequest += 1;
    clearNote(nameNote);
    await loadCameras({ preserveMessage: true, preserveSelection: true });
    refreshedAvailability = true;
  } catch (error) {
    renderNote(formNote, "danger", `<strong>${escapeHtml(error.message)}</strong>`);
  } finally {
    startButton.classList.remove("is-loading");
    if (!refreshedAvailability) {
      updateCameraAvailability({ preserveMessage: true });
    }
  }
}

cameraPicker.addEventListener("click", (event) => {
  const row = event.target.closest(".cam[data-camera-label]");
  if (!row) return;
  if (row.getAttribute("aria-disabled") === "true") return;
  selectCamera(row.dataset.cameraLabel);
  focusCameraRow(row.dataset.cameraLabel);
});

cameraPicker.addEventListener("keydown", (event) => {
  const row = event.target.closest(".cam[data-camera-label]");
  if (!row || row.getAttribute("aria-disabled") === "true") {
    return;
  }

  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    selectCamera(row.dataset.cameraLabel);
    focusCameraRow(row.dataset.cameraLabel);
  } else if (event.key === "ArrowDown" || event.key === "ArrowRight") {
    event.preventDefault();
    moveCameraFocus(row, 1);
  } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
    event.preventDefault();
    moveCameraFocus(row, -1);
  } else if (event.key === "Home") {
    event.preventDefault();
    const rowToSelect = selectableCameraRows()[0];
    if (rowToSelect) {
      selectCamera(rowToSelect.dataset.cameraLabel, { preserveMessage: true });
      focusCameraRow(rowToSelect.dataset.cameraLabel);
    }
  } else if (event.key === "End") {
    event.preventDefault();
    const rows = selectableCameraRows();
    const rowToSelect = rows[rows.length - 1];
    if (rowToSelect) {
      selectCamera(rowToSelect.dataset.cameraLabel, { preserveMessage: true });
      focusCameraRow(rowToSelect.dataset.cameraLabel);
    }
  }
});

nameInput.addEventListener("input", () => {
  recentlyStartedNameCheckKey = "";
  if (nameInput.value.trim()) {
    nameHint.hidden = true;
  } else {
    nameHint.hidden = false;
  }
  scheduleNameCheck();
});
intervalInput.addEventListener("input", updateRunSummary);
durationInput.addEventListener("input", updateRunSummary);
previewButton.addEventListener("click", preview);
previewRecaptureButton.addEventListener("click", preview);
form.addEventListener("submit", startExperiment);

updateRunSummary();
loadCameras().catch((error) => {
  renderNote(formNote, "danger", `<strong>${escapeHtml(error.message)}</strong>`);
});
