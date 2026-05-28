const grid = document.querySelector("#station-grid");
const summary = document.querySelector("#summary");
const pageSub = document.querySelector("#page-sub");
const livePill = document.querySelector("#live-pill");
const lastRefreshEl = document.querySelector("#last-refresh");
const refreshBtn = document.querySelector("#refresh-btn");

const STATUS_REFRESH_MS = 10000;
const THUMBNAIL_REFRESH_MS = 3000;
const LIVE_LABEL_REFRESH_MS = 1000;

let lastRefreshAt = null;
let lastStations = [];

const ICONS = {
  refresh: '<svg class="ic ic-16" viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-3-6.7"/><polyline points="21 4 21 9 16 9"/></svg>',
  square: '<svg class="ic" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="1.5"/></svg>',
  play: '<svg class="ic" viewBox="0 0 24 24"><polygon points="6 4 20 12 6 20 6 4"/></svg>',
  eye: '<svg class="ic" viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>',
  alert: '<svg class="ic ic-16 ico" viewBox="0 0 24 24"><path d="M12 3 2 21h20L12 3Z"/><line x1="12" y1="10" x2="12" y2="14"/><circle cx="12" cy="17.5" r="0.6" fill="currentColor" stroke="none"/></svg>',
  info: '<svg class="ic ic-16 ico" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><line x1="12" y1="11" x2="12" y2="16"/><circle cx="12" cy="8" r="0.7" fill="currentColor" stroke="none"/></svg>',
  imageOff: '<svg class="ic ic-22 ico" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><line x1="3" y1="5" x2="21" y2="19"/></svg>',
  plug: '<svg class="ic ic-16 ico" viewBox="0 0 24 24"><path d="M9 2v6"/><path d="M15 2v6"/><path d="M6 8h12v4a6 6 0 0 1-12 0V8Z"/><path d="M12 18v4"/></svg>',
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) {
    return "—";
  }
  const total = Math.max(0, Math.floor(Number(seconds)));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

function formatNextIn(nextCaptureAt) {
  if (!nextCaptureAt) {
    return null;
  }
  const target = new Date(nextCaptureAt).getTime();
  if (!Number.isFinite(target)) {
    return null;
  }
  const secs = Math.max(0, Math.round((target - Date.now()) / 1000));
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function formatClock(iso) {
  if (!iso) {
    return "—";
  }
  const d = new Date(iso);
  if (!Number.isFinite(d.getTime())) {
    return "—";
  }
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatIntervalMinutes(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  const minutes = Number(value);
  if (!Number.isFinite(minutes) || minutes <= 0) {
    return "—";
  }
  const label = Number.isInteger(minutes)
    ? String(minutes)
    : String(Number(minutes.toFixed(2)));
  return `${label} min`;
}

function clientState(station) {
  if (station.state === "running") return "running";
  if (station.state === "finished" || station.state === "completed") return "done";
  if (station.state === "error") return "error";
  if (station.state === "offline" || station.disconnected) return "offline";
  return "idle";
}

function stateLabel(state) {
  return ({
    running: "Running",
    idle: "Idle",
    done: "Finished",
    error: "Error",
    offline: "Offline",
  })[state] || "Idle";
}

function pillToneFor(state) {
  if (state === "running") return "is-running";
  if (state === "done") return "is-done";
  if (state === "error") return "is-danger";
  return "is-idle";
}

function frameBlock(station, state) {
  if (station.latest_url) {
    const url = `${station.latest_url}?t=${Date.now()}`;
    const refreshAttr = state === "running"
      ? ` data-latest-url="${escapeHtml(station.latest_url)}"`
      : "";
    return `
      <img class="frame-img" src="${url}" alt="Latest frame for ${escapeHtml(station.camera_label)}"${refreshAttr}>
    `;
  }
  const label = state === "offline" ? "Camera disconnected" : "No frame yet";
  return `
    <div class="frame-empty">
      ${ICONS.imageOff}
      <div>${escapeHtml(label)}</div>
    </div>
  `;
}

function identityNote(station) {
  if (station.identity_strategy === "hardware_id") return "";
  return `
    <div class="note is-warn">
      ${ICONS.info}
      <div class="body">
        <strong>Identity uses ${escapeHtml(station.identity_strategy || "fallback")}.</strong>
        <span class="meta">May change if cameras are replugged. Verify before long runs.</span>
      </div>
    </div>
  `;
}

function metricRow(station) {
  return `
    <div class="metric-row">
      <div class="metric"><div class="k">Elapsed</div><div class="v">${escapeHtml(formatDuration(station.elapsed_seconds))}</div></div>
      <div class="metric"><div class="k">Remaining</div><div class="v">${escapeHtml(formatDuration(station.remaining_seconds))}</div></div>
      <div class="metric"><div class="k">Frames</div><div class="v">${escapeHtml(station.images_captured ?? "—")}</div></div>
      <div class="metric"><div class="k">Interval</div><div class="v">${escapeHtml(formatIntervalMinutes(station.interval_minutes))}</div></div>
    </div>
  `;
}

function progressBar(station) {
  const elapsed = Number(station.elapsed_seconds) || 0;
  const remaining = Number(station.remaining_seconds) || 0;
  const total = elapsed + remaining;
  const pct = total > 0 ? Math.min(100, (elapsed / total) * 100) : 0;
  return `<div class="progress"><i style="width:${pct.toFixed(1)}%"></i></div>`;
}

function runningBody(station) {
  const nextIn = formatNextIn(station.next_capture_at);
  return `
    <div class="exp-line">
      <span class="exp-name">${escapeHtml(station.experiment_name || "")}</span>
    </div>
    ${metricRow(station)}
    ${progressBar(station)}
    <div class="station-foot">
      ${nextIn ? `<span>Next capture in <span class="mono" data-next-capture-at="${escapeHtml(station.next_capture_at)}">${escapeHtml(nextIn)}</span></span>` : ""}
      <span class="spacer"></span>
      <button type="button" class="btn is-danger btn-sm" data-stop-id="${escapeHtml(station.experiment_id)}">${ICONS.square} Stop</button>
    </div>
    ${identityNote(station)}
  `;
}

function idleBody(station) {
  return `
    <div class="exp-line">
      <span class="exp-op">Ready · no experiment scheduled.</span>
    </div>
    <div class="station-foot">
      <span class="spacer"></span>
      <a class="btn btn-sm" href="/new">${ICONS.eye} Preview</a>
      <a class="btn is-accent btn-sm" href="/new">${ICONS.play} Start experiment</a>
    </div>
    ${identityNote(station)}
  `;
}

function doneBody(station) {
  const endReason = station.end_reason ? `<span class="exp-op">${escapeHtml(station.end_reason)}</span>` : "";
  const folder = station.folder
    ? `<span>Output: <span class="mono">${escapeHtml(station.folder)}</span></span>`
    : "";
  return `
    <div class="exp-line">
      <span class="exp-name">${escapeHtml(station.experiment_name || "")}</span>
      ${endReason}
    </div>
    <div class="metric-row">
      <div class="metric"><div class="k">Duration</div><div class="v">${escapeHtml(formatDuration(station.elapsed_seconds))}</div></div>
      <div class="metric"><div class="k">Frames</div><div class="v">${escapeHtml(station.images_captured ?? "—")}</div></div>
      <div class="metric"><div class="k">Finished</div><div class="v">${escapeHtml(formatClock(station.ended_at))}</div></div>
      <div class="metric"><div class="k">Interval</div><div class="v">${escapeHtml(formatIntervalMinutes(station.interval_minutes))}</div></div>
    </div>
    <div class="station-foot">
      ${folder}
      <span class="spacer"></span>
      <a class="btn btn-sm" href="/new">Start another</a>
    </div>
    ${identityNote(station)}
  `;
}

function errorBody(station) {
  return `
    <div class="note is-danger">
      ${ICONS.alert}
      <div class="body">
        <strong>Capture error.</strong>
        <span class="meta">${escapeHtml(station.error_message || "An error was reported by the engine.")}</span>
      </div>
    </div>
    <div class="station-foot">
      <span class="spacer"></span>
      ${station.experiment_id ? `<button type="button" class="btn is-danger btn-sm" data-stop-id="${escapeHtml(station.experiment_id)}">${ICONS.square} Stop run</button>` : ""}
    </div>
    ${identityNote(station)}
  `;
}

function offlineBody(station) {
  return `
    <div class="note">
      ${ICONS.plug}
      <div class="body">
        <strong>Camera not detected.</strong>
        <span class="meta">Check USB connection and replug if needed.</span>
      </div>
    </div>
    ${identityNote(station)}
  `;
}

function stationCard(station) {
  const state = clientState(station);
  const tone = pillToneFor(state);
  const label = stateLabel(state);
  let body;
  if (state === "running") body = runningBody(station);
  else if (state === "done") body = doneBody(station);
  else if (state === "error") body = errorBody(station);
  else if (state === "offline") body = offlineBody(station);
  else body = idleBody(station);

  return `
    <article class="station" data-state="${state}">
      <header class="station-head">
        <div>
          <div class="name">${escapeHtml(station.camera_label)}</div>
          <div class="id mono">${escapeHtml(station.identity_strategy || "")}</div>
        </div>
        <div class="head-right">
          <span class="pill ${tone}"><span class="dot"></span>${escapeHtml(label)}</span>
        </div>
      </header>
      <div class="station-frame">
        ${frameBlock(station, state)}
      </div>
      <div class="station-body">
        ${body}
      </div>
    </article>
  `;
}

function renderStations(stations) {
  if (!stations.length) {
    grid.innerHTML = `<div class="note"><div class="body">No cameras are configured.</div></div>`;
    return;
  }
  grid.innerHTML = stations.map(stationCard).join("");
}

function renderSummary(stations) {
  const states = stations.map(clientState);
  const total = stations.length;
  const running = states.filter((s) => s === "running").length;
  const idle = states.filter((s) => s === "idle").length;
  const done = states.filter((s) => s === "done").length;
  const errored = states.filter((s) => s === "error" || s === "offline").length;
  const frames = stations.reduce((acc, s) => acc + (Number(s.images_captured) || 0), 0);

  const nextCaptures = stations
    .filter((s) => clientState(s) === "running" && s.next_capture_at)
    .map((s) => ({ at: new Date(s.next_capture_at).getTime(), label: s.camera_label }))
    .filter((row) => Number.isFinite(row.at) && row.at > Date.now())
    .sort((a, b) => a.at - b.at);
  const nextCell = nextCaptures[0];
  const nextLabel = nextCell
    ? `<span class="num">${escapeHtml(formatNextIn(new Date(nextCell.at).toISOString()))}</span><span class="of">${escapeHtml(nextCell.label)}</span>`
    : `<span class="num">—</span>`;

  const fallbackCount = stations.filter((s) => s.identity_strategy && s.identity_strategy !== "hardware_id").length;
  const healthCell = fallbackCount > 0
    ? `<div class="v is-warn"><span class="num">${fallbackCount}</span><span class="of">camera${fallbackCount === 1 ? "" : "s"} need${fallbackCount === 1 ? "s" : ""} attention</span></div>`
    : `<div class="v"><span class="num">OK</span></div>`;

  summary.innerHTML = `
    <div class="cell">
      <div class="k">Running</div>
      <div class="v is-running"><span class="num">${running}</span><span class="of">/ ${total} stations</span></div>
    </div>
    <div class="cell">
      <div class="k">Frames captured</div>
      <div class="v"><span class="num">${frames}</span></div>
    </div>
    <div class="cell">
      <div class="k">Next capture</div>
      <div class="v">${nextLabel}</div>
    </div>
    <div class="cell">
      <div class="k">Health</div>
      ${healthCell}
    </div>
  `;

  const parts = [`${total} station${total === 1 ? "" : "s"}`];
  if (running) parts.push(`<span class="num">${running}</span> running`);
  if (idle) parts.push(`<span class="num">${idle}</span> idle`);
  if (done) parts.push(`<span class="num">${done}</span> finished`);
  if (errored) parts.push(`<span class="num">${errored}</span> attention`);
  pageSub.innerHTML = parts.join(`<span class="dot-sep"> · </span>`);
}

function refreshNextInCounters() {
  for (const el of document.querySelectorAll("[data-next-capture-at]")) {
    const at = el.dataset.nextCaptureAt;
    if (!at) continue;
    const text = formatNextIn(at);
    if (text) el.textContent = text;
  }
}

function refreshThumbnails() {
  for (const image of grid.querySelectorAll("img.frame-img[data-latest-url]")) {
    const latestUrl = image.dataset.latestUrl;
    if (latestUrl) {
      image.src = `${latestUrl}?t=${Date.now()}`;
    }
  }
}

function updateLastRefreshLabel() {
  if (!lastRefreshAt) {
    livePill.hidden = true;
    return;
  }
  livePill.hidden = false;
  const elapsed = Math.max(0, Math.floor((Date.now() - lastRefreshAt) / 1000));
  if (elapsed < 2) {
    lastRefreshEl.textContent = "now";
  } else if (elapsed < 60) {
    lastRefreshEl.textContent = `${elapsed}s ago`;
  } else {
    lastRefreshEl.textContent = `${Math.floor(elapsed / 60)}m ago`;
  }
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "Could not load station status");
    }
    lastStations = payload.stations || [];
    renderStations(lastStations);
    renderSummary(lastStations);
    lastRefreshAt = Date.now();
    updateLastRefreshLabel();
  } catch (error) {
    grid.innerHTML = `<div class="note is-danger">${ICONS.alert}<div class="body"><strong>Could not load station status.</strong><span class="meta">${escapeHtml(error.message)}</span></div></div>`;
  }
}

async function stopExperiment(experimentId, button) {
  button.disabled = true;
  button.classList.add("is-loading");
  try {
    const response = await fetch(`/api/experiments/${encodeURIComponent(experimentId)}/stop`, {
      method: "POST",
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "Could not stop experiment");
    }
    await refreshStatus();
  } catch (error) {
    button.disabled = false;
    button.classList.remove("is-loading");
    alert(error.message);
  }
}

grid.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-stop-id]");
  if (!button) {
    return;
  }
  stopExperiment(button.dataset.stopId, button);
});

refreshBtn.addEventListener("click", () => {
  refreshStatus();
});

refreshStatus();
setInterval(refreshStatus, STATUS_REFRESH_MS);
setInterval(refreshThumbnails, THUMBNAIL_REFRESH_MS);
setInterval(refreshNextInCounters, 1000);
setInterval(updateLastRefreshLabel, LIVE_LABEL_REFRESH_MS);
