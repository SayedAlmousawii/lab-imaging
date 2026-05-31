const root = document.querySelector("#experiment-detail-root");
const alerts = document.querySelector("#experiment-alerts");
const title = document.querySelector("#experiment-title");
const subtitle = document.querySelector("#experiment-sub");
const details = document.querySelector("#experiment-details");
const latestFrame = document.querySelector("#latest-frame");
const latestSub = document.querySelector("#latest-sub");
const logSub = document.querySelector("#log-sub");
const logLines = document.querySelector("#log-lines");
const notesSub = document.querySelector("#post-notes-sub");
const notesBody = document.querySelector("#post-notes-body");
const notesLink = document.querySelector("#experiment-notes-link");

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

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "-";
  return date.toLocaleString();
}

function formatStatus(experiment) {
  const reason = experiment.end_reason ? ` / ${experiment.end_reason}` : "";
  return `${experiment.status || "incomplete"}${reason}`;
}

function renderDetails(experiment) {
  const rows = [
    ["Experiment", experiment.name || experiment.experiment_id],
    ["Station", experiment.camera_label || "-"],
    ["Status", formatStatus(experiment)],
    ["Started", formatDateTime(experiment.started_at)],
    ["Planned stop", formatDateTime(experiment.planned_stop_at)],
    ["Ended", formatDateTime(experiment.ended_at)],
    ["Images", experiment.images_captured ?? 0],
    ["Folder", experiment.folder || "-"],
  ];
  details.innerHTML = rows.map(([label, value]) => `
    <div>
      <dt>${escapeHtml(label)}</dt>
      <dd class="${label === "Folder" ? "mono" : ""}">${escapeHtml(value)}</dd>
    </div>
  `).join("");
}

function renderLatest(experiment) {
  latestSub.textContent = experiment.latest_image || "No image";
  if (!experiment.latest_image_url) {
    latestFrame.innerHTML = `
      <div class="frame-empty">
        <svg class="ic ic-22 ico" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><line x1="3" y1="5" x2="21" y2="19"/></svg>
        <div>No captured still found</div>
      </div>
    `;
    return;
  }
  latestFrame.innerHTML = `
    <img class="frame-img" src="${escapeHtml(experiment.latest_image_url)}?t=${Date.now()}" alt="Latest still for ${escapeHtml(experiment.name || experiment.experiment_id)}">
  `;
}

function renderLog(captureLog) {
  if (!captureLog?.available) {
    logSub.textContent = "Unavailable";
    logLines.textContent = captureLog?.warning || "capture_log.txt is unavailable.";
    return;
  }
  logSub.textContent = `${captureLog.line_count} lines / ${captureLog.error_count} errors`;
  logLines.textContent = (captureLog.recent_lines || []).join("\n") || "No log entries.";
}

function renderNotes(experiment) {
  if (experiment.post_notes_url) {
    notesLink.href = experiment.post_notes_url;
    notesLink.hidden = false;
    notesLink.innerHTML = `
      <svg class="ic ic-16" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="14" y2="17"/></svg>
      ${experiment.has_post_notes ? "Edit notes" : "Add notes"}
    `;
  } else {
    notesLink.hidden = true;
  }

  if (experiment.has_post_notes && experiment.post_notes) {
    notesSub.textContent = "Saved";
    notesBody.innerHTML = `<div class="body">${escapeHtml(experiment.post_notes)}</div>`;
  } else {
    notesSub.textContent = "None";
    notesBody.innerHTML = "<div class=\"body\">No post-run notes saved.</div>";
  }
}

function renderWarnings(experiment) {
  const warnings = experiment.warnings || [];
  if (!warnings.length) {
    renderAlert("", "");
    return;
  }
  renderAlert("warn", `<strong>Folder warning.</strong><span class="meta">${escapeHtml(warnings.join(" "))}</span>`);
}

function applyPayload(payload) {
  const experiment = payload.experiment || {};
  title.textContent = experiment.name || experiment.experiment_id || "Experiment detail";
  subtitle.textContent = `${experiment.camera_label || "Unknown station"} / ${formatStatus(experiment)}`;
  renderWarnings(experiment);
  renderDetails(experiment);
  renderLatest(experiment);
  renderLog(experiment.capture_log);
  renderNotes(experiment);
}

async function loadExperiment() {
  try {
    const response = await fetch(`/api/experiments/${encodeURIComponent(experimentId)}`, {
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "Could not load experiment");
    }
    applyPayload(payload);
  } catch (error) {
    title.textContent = "Experiment unavailable";
    subtitle.textContent = experimentId;
    latestSub.textContent = "-";
    logSub.textContent = "-";
    logLines.textContent = "";
    notesBody.innerHTML = "<div class=\"body\">-</div>";
    renderAlert("danger", `<strong>Could not load experiment.</strong><span class="meta">${escapeHtml(error.message)}</span>`);
  }
}

loadExperiment().catch(() => {});
