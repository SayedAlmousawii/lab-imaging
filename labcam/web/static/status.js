const tableBody = document.querySelector("#status-table-body");
const statusMessage = document.querySelector("#status-message");
const STATUS_REFRESH_MS = 10000;
const THUMBNAIL_REFRESH_MS = 3000;

function showMessage(text, kind = "info") {
  statusMessage.textContent = text;
  statusMessage.className = `message ${kind}`;
  statusMessage.hidden = false;
}

function clearMessage() {
  statusMessage.hidden = true;
  statusMessage.textContent = "";
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) {
    return "-";
  }
  const total = Math.max(0, Number(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
}

function identityCell(station) {
  const warning = station.identity_strategy !== "hardware_id";
  const warnings = station.warnings || [];
  const note = warnings.length > 0 ? `<div class="station-note">${escapeHtml(warnings.join(" "))}</div>` : "";
  return `
    <span class="badge ${warning ? "warn" : "ok"}">${escapeHtml(station.identity_strategy)}</span>
    ${note}
  `;
}

function latestCell(station) {
  if (!station.latest_url) {
    return '<span class="muted">No frame</span>';
  }
  const url = `${station.latest_url}?t=${Date.now()}`;
  const refreshAttrs = station.state === "running"
    ? ` data-latest-url="${escapeHtml(station.latest_url)}"`
    : "";
  return `<img class="thumb" src="${url}" alt="Latest frame for ${escapeHtml(station.camera_label)}"${refreshAttrs}>`;
}

function actionCell(station) {
  if (station.state !== "running") {
    return '<span class="muted">-</span>';
  }
  return `<button type="button" data-stop-id="${escapeHtml(station.experiment_id)}">Stop</button>`;
}

function renderStations(stations) {
  if (!stations.length) {
    tableBody.innerHTML = '<tr><td colspan="9">No cameras are configured.</td></tr>';
    return;
  }

  tableBody.innerHTML = stations.map((station) => `
    <tr>
      <td><strong>${escapeHtml(station.camera_label)}</strong></td>
      <td>${escapeHtml(station.state)}</td>
      <td>${identityCell(station)}</td>
      <td>${station.experiment_name ? escapeHtml(station.experiment_name) : '<span class="muted">-</span>'}</td>
      <td>${formatDuration(station.elapsed_seconds)}</td>
      <td>${station.images_captured ?? "-"}</td>
      <td>${formatDuration(station.remaining_seconds)}</td>
      <td>${latestCell(station)}</td>
      <td>${actionCell(station)}</td>
    </tr>
  `).join("");
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "Could not load station status");
    }
    renderStations(payload.stations || []);
    clearMessage();
  } catch (error) {
    showMessage(error.message, "error");
  }
}

function refreshThumbnails() {
  for (const image of tableBody.querySelectorAll("img.thumb[data-latest-url]")) {
    const latestUrl = image.dataset.latestUrl;
    if (latestUrl) {
      image.src = `${latestUrl}?t=${Date.now()}`;
    }
  }
}

async function stopExperiment(experimentId, button) {
  button.disabled = true;
  button.textContent = "Stopping...";
  try {
    const response = await fetch(`/api/experiments/${encodeURIComponent(experimentId)}/stop`, {
      method: "POST",
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "Could not stop experiment");
    }
    showMessage("Experiment stopped.", "info");
    await refreshStatus();
  } catch (error) {
    showMessage(error.message, "error");
    button.disabled = false;
    button.textContent = "Stop";
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

tableBody.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-stop-id]");
  if (!button) {
    return;
  }
  stopExperiment(button.dataset.stopId, button);
});

refreshStatus();
setInterval(refreshStatus, STATUS_REFRESH_MS);
setInterval(refreshThumbnails, THUMBNAIL_REFRESH_MS);
