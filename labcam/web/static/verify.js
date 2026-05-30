const verifyGrid = document.querySelector("#verify-grid");
const verifySub = document.querySelector("#verify-sub");
const verifyAlerts = document.querySelector("#verify-alerts");

const ICONS = {
  alert: '<svg class="ic ic-16 ico" viewBox="0 0 24 24"><path d="M12 3 2 21h20L12 3Z"/><line x1="12" y1="10" x2="12" y2="14"/><circle cx="12" cy="17.5" r="0.6" fill="currentColor" stroke="none"/></svg>',
  check: '<svg class="ic ic-16 ico" viewBox="0 0 24 24"><polyline points="4 12 10 18 20 6"/></svg>',
  camera: '<svg class="ic ic-32 ico" viewBox="0 0 24 24"><path d="M14.5 5 16 8h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3l1.5-3h5Z"/><circle cx="12" cy="13.5" r="3"/></svg>',
  refresh: '<svg class="ic ic-16" viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-3-6.7"/><polyline points="21 4 21 9 16 9"/></svg>',
  spinner: '<svg class="ic ic-22" viewBox="0 0 24 24" style="animation:spin .9s linear infinite"><path d="M21 12a9 9 0 1 1-9-9"/></svg>',
};

let cameras = [];
const cameraState = new Map();

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function stateFor(label) {
  if (!cameraState.has(label)) {
    cameraState.set(label, {
      previewOk: false,
      previewUrl: "",
      busy: false,
      confirmBusy: false,
      error: "",
    });
  }
  return cameraState.get(label);
}

function renderNote(tone, html) {
  const toneClass = tone ? ` is-${tone}` : "";
  const icon = tone === "danger" || tone === "warn" ? ICONS.alert : ICONS.check;
  return `<div class="note${toneClass}">${icon}<div class="body">${html}</div></div>`;
}

function renderAlerts() {
  const confirmed = cameras.filter((camera) => camera.confirmed).length;
  const total = cameras.length;
  if (!total) {
    verifyAlerts.innerHTML = renderNote("danger", "<strong>No cameras are configured.</strong><span class=\"meta\">Run camera setup before using the dashboard.</span>");
    verifySub.textContent = "No configured stations found.";
    return;
  }
  verifySub.textContent = `${confirmed} of ${total} stations confirmed for this startup session.`;
  verifyAlerts.innerHTML = confirmed === total
    ? renderNote("info", "<strong>All cameras are confirmed.</strong><span class=\"meta\">Station status and experiment start are available for this startup session.</span>")
    : renderNote("warn", "<strong>Experiments are locked until every station is confirmed.</strong><span class=\"meta\">Capture a fresh still for each label, then confirm the station.</span>");
}

function renderCamera(camera) {
  const state = stateFor(camera.label);
  const confirmed = !!camera.confirmed;
  const isFallback = !!camera.identity_warning;
  const frame = state.busy
    ? `<div class="ph-state">${ICONS.spinner}<strong>Capturing preview…</strong></div><span class="shimmer"></span>`
    : state.previewUrl
      ? `<img class="frame-img" src="${state.previewUrl}" alt="Fresh preview for ${escapeHtml(camera.label)}">`
      : `<div class="ph-state">${ICONS.camera}<strong>No preview captured</strong></div>`;
  const metadata = [
    `<span class="${isFallback ? "id-strategy is-warn" : "id-strategy mono"}">${isFallback ? ICONS.alert : ""}${escapeHtml(camera.identity_strategy)}</span>`,
    `<span class="mono">index ${escapeHtml(camera.last_seen_index)}</span>`,
  ].join('<span class="sep">·</span>');
  const warnings = [
    ...(camera.warnings || []),
    ...(isFallback ? ["Camera identity can change after replug. Match this preview to the station label."] : []),
  ];
  const previewDisabled = state.busy || state.confirmBusy || confirmed;
  const confirmDisabled = state.busy || state.confirmBusy || confirmed || !state.previewOk;

  return `
    <article class="verify-card${confirmed ? " is-confirmed" : ""}" data-camera-label="${escapeHtml(camera.label)}">
      <header class="verify-card-head">
        <div>
          <h2>${escapeHtml(camera.label)}</h2>
          <div class="verify-meta">${metadata}</div>
        </div>
        <span class="pill ${confirmed ? "is-running" : "is-warn"}"><span class="dot"></span>${confirmed ? "Confirmed" : "Needs check"}</span>
      </header>
      <div class="verify-frame${state.error ? " is-error" : ""}">
        ${frame}
      </div>
      <div class="verify-body">
        ${warnings.map((warning) => renderNote("warn", `<strong>Identity warning.</strong><span class="meta">${escapeHtml(warning)}</span>`)).join("")}
        ${state.error ? renderNote("danger", `<strong>Preview failed.</strong><span class="meta">${escapeHtml(state.error)}</span>`) : ""}
      </div>
      <footer class="verify-actions">
        <button class="btn js-preview" type="button" ${previewDisabled ? "disabled" : ""}>
          ${ICONS.refresh}
          Capture preview
        </button>
        <button class="btn is-accent js-confirm" type="button" ${confirmDisabled ? "disabled" : ""}>
          ${state.confirmBusy ? ICONS.spinner : ICONS.check}
          Confirm station
        </button>
      </footer>
    </article>
  `;
}

function render() {
  renderAlerts();
  if (!cameras.length) {
    verifyGrid.innerHTML = "";
    return;
  }
  verifyGrid.innerHTML = cameras.map(renderCamera).join("");
}

async function loadStatus() {
  const response = await fetch("/api/verification", { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error?.message || "Could not load verification status");
  }
  cameras = payload.cameras || [];
  render();
}

async function capturePreview(label) {
  const state = stateFor(label);
  state.busy = true;
  state.error = "";
  state.previewOk = false;
  render();

  try {
    const response = await fetch("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ camera_label: label }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error?.message || "Could not capture preview");
    }
    const blob = await response.blob();
    if (state.previewUrl) {
      URL.revokeObjectURL(state.previewUrl);
    }
    state.previewUrl = URL.createObjectURL(blob);
    state.previewOk = true;
  } catch (error) {
    state.error = error.message || "Could not capture preview";
  } finally {
    state.busy = false;
    render();
  }
}

async function confirmCamera(label) {
  const state = stateFor(label);
  state.confirmBusy = true;
  state.error = "";
  render();

  try {
    const response = await fetch("/api/verification/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ camera_label: label }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "Could not confirm camera");
    }
    cameras = payload.cameras || [];
    state.previewOk = false;
  } catch (error) {
    state.error = error.message || "Could not confirm camera";
  } finally {
    state.confirmBusy = false;
    render();
  }
}

verifyGrid.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const card = button.closest("[data-camera-label]");
  const label = card?.dataset.cameraLabel || "";
  if (!label) return;
  if (button.classList.contains("js-preview")) {
    capturePreview(label);
  } else if (button.classList.contains("js-confirm")) {
    confirmCamera(label);
  }
});

loadStatus().catch((error) => {
  verifyGrid.innerHTML = renderNote("danger", `<strong>Could not load cameras.</strong><span class="meta">${escapeHtml(error.message)}</span>`);
});
