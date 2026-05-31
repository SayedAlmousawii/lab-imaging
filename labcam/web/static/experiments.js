const list = document.querySelector("#experiment-list");
const alerts = document.querySelector("#experiments-alerts");
const subtitle = document.querySelector("#experiments-sub");
const countLabel = document.querySelector("#experiments-count");
const refreshButton = document.querySelector("#experiments-refresh");
const dateFilter = document.querySelector("#filter-date");
const stationFilter = document.querySelector("#filter-station");
const clearButton = document.querySelector("#filters-clear");

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

function statusPill(experiment) {
  const status = experiment.status || "incomplete";
  const tone = ({
    running: "is-running",
    completed: "is-done",
    stopped: "is-done",
    failed: "is-danger",
    incomplete: "is-warn",
  })[status] || "is-idle";
  const label = ({
    running: "Running",
    completed: "Completed",
    stopped: "Stopped",
    failed: "Failed",
    incomplete: "Incomplete",
  })[status] || status;
  return `<span class="pill ${tone}"><span class="dot"></span>${escapeHtml(label)}</span>`;
}

function setSelectOptions(select, values, current, allLabel) {
  select.innerHTML = [
    `<option value="">${escapeHtml(allLabel)}</option>`,
    ...values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`),
  ].join("");
  select.value = values.includes(current) ? current : "";
}

function currentFilters() {
  return {
    date: dateFilter.value,
    station: stationFilter.value,
  };
}

function updateUrl(filters) {
  const params = new URLSearchParams();
  if (filters.date) params.set("date", filters.date);
  if (filters.station) params.set("station", filters.station);
  const query = params.toString();
  history.replaceState(null, "", query ? `/experiments?${query}` : "/experiments");
}

function renderExperiments(payload) {
  const filters = payload.filters || {};
  setSelectOptions(dateFilter, payload.dates || [], filters.date || "", "All dates");
  setSelectOptions(stationFilter, payload.stations || [], filters.station || "", "All stations");

  const experiments = payload.experiments || [];
  subtitle.textContent = `${payload.filtered_count || 0} shown from ${payload.total_count || 0} folders`;
  countLabel.textContent = `${payload.filtered_count || 0} shown`;

  if (!experiments.length) {
    list.innerHTML = renderNote("", "No experiment folders match the current filters.");
    return;
  }

  list.innerHTML = experiments.map((experiment) => {
    const warning = (experiment.warnings || []).length
      ? `<div class="experiment-warning">${escapeHtml(experiment.warnings[0])}</div>`
      : "";
    return `
      <a class="experiment-row" href="${escapeHtml(experiment.detail_url)}">
        <div class="experiment-main">
          <div class="experiment-name">${escapeHtml(experiment.name || experiment.experiment_id)}</div>
          <div class="experiment-meta">
            <span>${escapeHtml(experiment.date || "Unknown date")}</span>
            <span class="sep">/</span>
            <span>${escapeHtml(experiment.camera_label || "Unknown station")}</span>
            <span class="sep">/</span>
            <span class="mono">${escapeHtml(experiment.experiment_id)}</span>
          </div>
          ${warning}
          <div class="experiment-folder mono">${escapeHtml(experiment.folder || "")}</div>
        </div>
        <div class="experiment-stats">
          ${statusPill(experiment)}
          <div class="experiment-stat"><span class="k">Frames</span><span class="v">${escapeHtml(experiment.images_captured ?? 0)}</span></div>
          <div class="experiment-stat"><span class="k">Ended</span><span class="v">${escapeHtml(formatDateTime(experiment.ended_at))}</span></div>
        </div>
      </a>
    `;
  }).join("");
}

async function loadExperiments({ updateLocation = false } = {}) {
  refreshButton.disabled = true;
  refreshButton.classList.add("is-loading");
  renderAlert("", "");
  const filters = currentFilters();
  if (updateLocation) updateUrl(filters);

  try {
    const params = new URLSearchParams();
    if (filters.date) params.set("date", filters.date);
    if (filters.station) params.set("station", filters.station);
    const response = await fetch(`/api/experiments${params.toString() ? `?${params}` : ""}`, {
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message || "Could not load experiments");
    }
    renderExperiments(payload);
  } catch (error) {
    subtitle.textContent = "Could not load experiments";
    countLabel.textContent = "-";
    list.innerHTML = "";
    renderAlert("danger", `<strong>Experiment browser unavailable.</strong><span class="meta">${escapeHtml(error.message)}</span>`);
  } finally {
    refreshButton.disabled = false;
    refreshButton.classList.remove("is-loading");
  }
}

function initFiltersFromUrl() {
  const params = new URLSearchParams(location.search);
  dateFilter.value = params.get("date") || "";
  stationFilter.value = params.get("station") || "";
}

dateFilter.addEventListener("change", () => loadExperiments({ updateLocation: true }));
stationFilter.addEventListener("change", () => loadExperiments({ updateLocation: true }));
refreshButton.addEventListener("click", () => loadExperiments());
clearButton.addEventListener("click", () => {
  dateFilter.value = "";
  stationFilter.value = "";
  loadExperiments({ updateLocation: true });
});

initFiltersFromUrl();
loadExperiments().catch(() => {});
