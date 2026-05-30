const alerts = document.querySelector("#settings-alerts");
const form = document.querySelector("#settings-form");
const saveButton = document.querySelector("#settings-save");
const refreshButton = document.querySelector("#settings-refresh");
const settingsSub = document.querySelector("#settings-sub");
const diagnosticsList = document.querySelector("#diagnostics-list");

const fields = {
  experiments_dir: document.querySelector("#experiments-dir"),
  default_interval_minutes: document.querySelector("#default-interval-minutes"),
  default_duration_hours: document.querySelector("#default-duration-hours"),
  jpeg_quality: document.querySelector("#jpeg-quality"),
  capture_retries: document.querySelector("#capture-retries"),
  warmup_frames: document.querySelector("#warmup-frames"),
};
const captureDefaultFields = new Set([
  "default_interval_minutes",
  "default_duration_hours",
  "jpeg_quality",
  "capture_retries",
  "warmup_frames",
]);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[ch]));
}

function renderNote(tone, html) {
  return `<div class="note${tone ? ` is-${tone}` : ""}"><div class="body">${html}</div></div>`;
}

function renderAlert(tone, html) {
  alerts.innerHTML = html ? renderNote(tone, html) : "";
}

function setLoading(isLoading) {
  saveButton.disabled = isLoading;
  refreshButton.disabled = isLoading;
  saveButton.classList.toggle("is-loading", isLoading);
}

function clearFieldErrors() {
  for (const field of form.querySelectorAll("[data-field]")) {
    field.classList.remove("is-invalid");
    const error = field.querySelector(".js-error");
    if (error) {
      error.hidden = true;
      error.textContent = "";
    }
  }
}

function applyFieldErrors(errors) {
  clearFieldErrors();
  for (const [name, message] of Object.entries(errors || {})) {
    const field = form.querySelector(`[data-field="${CSS.escape(name)}"]`);
    const error = field?.querySelector(".js-error");
    if (!field || !error) continue;
    field.classList.add("is-invalid");
    error.textContent = message;
    error.hidden = false;
  }
}

function setFormValues(settings) {
  for (const [name, input] of Object.entries(fields)) {
    input.value = settings[name] ?? "";
  }
}

function renderDiagnostics(diagnostics) {
  const rows = [
    ["Experiments directory", diagnostics.experiments_dir],
    ["Settings file", diagnostics.settings_path],
    ["Camera config", diagnostics.cameras_path],
    ["LAN access", diagnostics.allow_lan_access ? "Enabled" : "Disabled"],
    ["Python", diagnostics.python_version],
    ["OpenCV", diagnostics.opencv_version],
    ["Commit", diagnostics.git_commit || "Unavailable"],
  ];
  diagnosticsList.innerHTML = rows.map(([label, value]) => `
    <div>
      <dt>${escapeHtml(label)}</dt>
      <dd class="${label === "LAN access" ? "" : "mono"}">${escapeHtml(value)}</dd>
    </div>
  `).join("");
}

function applyPayload(payload) {
  setFormValues(payload.settings || {});
  renderDiagnostics(payload.diagnostics || {});
  const activeExperiments = Boolean(payload.active_experiments);
  for (const [name, input] of Object.entries(fields)) {
    input.disabled = activeExperiments && captureDefaultFields.has(name);
  }
  settingsSub.textContent = payload.active_experiments
    ? "Running experiments: storage changes apply to future runs."
    : "Ready.";
}

async function loadSettings({ quiet = false } = {}) {
  setLoading(true);
  clearFieldErrors();
  if (!quiet) renderAlert("", "");
  try {
    const response = await fetch("/api/settings", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "Could not load settings");
    }
    applyPayload(payload);
  } catch (error) {
    renderAlert("danger", `<strong>Could not load settings.</strong><span class="meta">${escapeHtml(error.message)}</span>`);
  } finally {
    setLoading(false);
  }
}

function formPayload() {
  return {
    experiments_dir: fields.experiments_dir.value,
    default_interval_minutes: fields.default_interval_minutes.value,
    default_duration_hours: fields.default_duration_hours.value,
    jpeg_quality: fields.jpeg_quality.value,
    capture_retries: fields.capture_retries.value,
    warmup_frames: fields.warmup_frames.value,
  };
}

async function saveSettings(event) {
  event.preventDefault();
  setLoading(true);
  clearFieldErrors();
  renderAlert("", "");
  try {
    const response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formPayload()),
    });
    const payload = await response.json();
    if (!response.ok) {
      applyFieldErrors(payload.error?.fields || {});
      throw new Error(payload.error?.message || "Could not save settings");
    }
    applyPayload(payload);
    renderAlert("info", "<strong>Settings saved.</strong><span class=\"meta\">New defaults apply to future experiments.</span>");
  } catch (error) {
    renderAlert("danger", `<strong>Settings not saved.</strong><span class="meta">${escapeHtml(error.message)}</span>`);
  } finally {
    setLoading(false);
  }
}

form.addEventListener("submit", saveSettings);
refreshButton.addEventListener("click", () => loadSettings());

loadSettings().catch(() => {});
