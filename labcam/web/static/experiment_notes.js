const root = document.querySelector("#post-notes-root");
const form = document.querySelector("#post-notes-form");
const textarea = document.querySelector("#post-notes");
const saveButton = document.querySelector("#notes-save");
const alerts = document.querySelector("#notes-alerts");
const title = document.querySelector("#notes-title");
const subtitle = document.querySelector("#notes-sub");
const stateLabel = document.querySelector("#notes-state");
const details = document.querySelector("#notes-details");
const metadataNotes = document.querySelector("#metadata-notes");

const experimentId = root?.dataset.experimentId || "";

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
  saveButton.disabled = isLoading || textarea.disabled;
  saveButton.classList.toggle("is-loading", isLoading);
}

function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return date.toLocaleString();
}

function applyPayload(payload) {
  const experimentName = payload.experiment_name || payload.experiment_id;
  title.textContent = experimentName;
  subtitle.textContent = `${payload.camera_label || "Unknown camera"} · ${payload.end_reason || "finished"}`;
  stateLabel.textContent = payload.has_post_notes ? "Notes saved" : "No notes yet";
  textarea.disabled = !payload.editable;
  textarea.value = payload.post_notes || "";
  saveButton.disabled = !payload.editable;

  const rows = [
    ["Experiment", experimentName],
    ["Camera", payload.camera_label || "—"],
    ["Ended", formatDateTime(payload.ended_at)],
    ["Reason", payload.end_reason || "—"],
    ["Folder", payload.folder || "—"],
    ["Notes file", payload.post_notes_file || "—"],
  ];
  details.innerHTML = rows.map(([label, value]) => `
    <div>
      <dt>${escapeHtml(label)}</dt>
      <dd class="${label === "Folder" || label === "Notes file" ? "mono" : ""}">${escapeHtml(value)}</dd>
    </div>
  `).join("");
  metadataNotes.innerHTML = `<div class="body">${escapeHtml(payload.metadata_notes || "—")}</div>`;
}

async function loadNotes({ quiet = false } = {}) {
  setLoading(true);
  if (!quiet) renderAlert("", "");
  try {
    const response = await fetch(`/api/experiments/${encodeURIComponent(experimentId)}/post-notes`, {
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "Could not load notes");
    }
    applyPayload(payload);
  } catch (error) {
    textarea.disabled = true;
    saveButton.disabled = true;
    renderAlert("danger", `<strong>Could not load post-run notes.</strong><span class="meta">${escapeHtml(error.message)}</span>`);
  } finally {
    setLoading(false);
  }
}

async function saveNotes(event) {
  event.preventDefault();
  setLoading(true);
  renderAlert("", "");
  try {
    const response = await fetch(`/api/experiments/${encodeURIComponent(experimentId)}/post-notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes: textarea.value }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "Could not save notes");
    }
    applyPayload(payload);
    const message = payload.has_post_notes
      ? "Post-run notes saved."
      : "Post-run notes removed.";
    renderAlert("info", `<strong>${escapeHtml(message)}</strong><span class="meta">The experiment metadata was not changed.</span>`);
  } catch (error) {
    renderAlert("danger", `<strong>Notes not saved.</strong><span class="meta">${escapeHtml(error.message)}</span>`);
  } finally {
    setLoading(false);
  }
}

form.addEventListener("submit", saveNotes);
loadNotes().catch(() => {});
