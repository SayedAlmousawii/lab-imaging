const form = document.querySelector("#experiment-form");
const cameraSelect = document.querySelector("#camera-label");
const previewButton = document.querySelector("#preview-button");
const startButton = document.querySelector("#start-button");
const message = document.querySelector("#form-message");
const nameInput = document.querySelector("#experiment-name");
const nameWarning = document.querySelector("#name-warning");
const previewImage = document.querySelector("#preview-image");
const previewPlaceholder = document.querySelector("#preview-placeholder");

let busyCameras = new Set();
let nameCheckTimer = null;
let nameCheckRequest = 0;

function showMessage(text, kind = "info") {
  message.textContent = text;
  message.className = `message ${kind}`;
  message.hidden = false;
}

function clearMessage() {
  message.hidden = true;
  message.textContent = "";
}

function showNameWarning(text) {
  nameWarning.textContent = text;
  nameWarning.hidden = false;
}

function clearNameWarning() {
  nameWarning.hidden = true;
  nameWarning.textContent = "";
}

async function loadCameras({ preserveMessage = false } = {}) {
  const selectedCamera = cameraSelect.value;
  const [cameraResponse, statusResponse] = await Promise.all([
    fetch("/api/cameras", { cache: "no-store" }),
    fetch("/api/status", { cache: "no-store" }),
  ]);
  const cameraPayload = await cameraResponse.json();
  const statusPayload = await statusResponse.json();

  if (!cameraResponse.ok) {
    throw new Error(cameraPayload.error?.message || "Could not load cameras");
  }
  if (!statusResponse.ok) {
    throw new Error(statusPayload.error?.message || "Could not load station status");
  }

  busyCameras = new Set(
    (statusPayload.stations || [])
      .filter((station) => station.state === "running")
      .map((station) => station.camera_label)
  );

  cameraSelect.innerHTML = "";
  for (const camera of cameraPayload.cameras || []) {
    const option = document.createElement("option");
    option.value = camera.label;
    option.textContent = `${camera.label} (${camera.identity_strategy})`;
    if (busyCameras.has(camera.label)) {
      option.textContent += " - running";
    }
    cameraSelect.append(option);
  }
  if (selectedCamera) {
    cameraSelect.value = selectedCamera;
  }
  updateCameraAvailability({ preserveMessage });
  scheduleNameCheck();
}

function updateCameraAvailability({ preserveMessage = false } = {}) {
  const busy = busyCameras.has(cameraSelect.value);
  previewButton.disabled = busy || !cameraSelect.value;
  startButton.disabled = busy || !cameraSelect.value;
  if (busy) {
    startButton.textContent = "Camera running";
    if (!preserveMessage) {
      showMessage("That camera already has a running experiment.", "error");
    }
  } else if (!cameraSelect.value) {
    startButton.textContent = "Start";
    showMessage("No camera is available.", "error");
  } else {
    startButton.textContent = "Start";
    if (!preserveMessage) {
      clearMessage();
    }
  }
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
  if (busyCameras.has(payload.camera_label)) {
    throw new Error("That camera already has a running experiment.");
  }
}

function scheduleNameCheck() {
  clearTimeout(nameCheckTimer);
  nameCheckTimer = setTimeout(checkExperimentName, 250);
}

async function checkExperimentName() {
  const requestId = ++nameCheckRequest;
  const payload = payloadFromForm();
  if (!payload.camera_label || !payload.name || !/[A-Za-z0-9]/.test(payload.name)) {
    clearNameWarning();
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
      clearNameWarning();
      return;
    }
    showNameWarning(
      `A run with this name and camera already exists today. Starting will create ${responsePayload.next_folder_name}.`
    );
  } catch {
    if (requestId === nameCheckRequest) {
      clearNameWarning();
    }
  }
}

async function preview() {
  const payload = payloadFromForm();
  try {
    validatePayload({ ...payload, name: payload.name || "preview" });
  } catch (error) {
    showMessage(error.message, "error");
    return;
  }

  previewButton.disabled = true;
  previewButton.textContent = "Capturing...";
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
    previewImage.src = URL.createObjectURL(blob);
    previewImage.hidden = false;
    previewPlaceholder.hidden = true;
    showMessage("Preview captured.", "info");
  } catch (error) {
    showMessage(error.message, "error");
  } finally {
    previewButton.textContent = "Preview";
    updateCameraAvailability({ preserveMessage: false });
  }
}

async function startExperiment(event) {
  event.preventDefault();
  const payload = payloadFromForm();
  try {
    validatePayload(payload);
  } catch (error) {
    showMessage(error.message, "error");
    return;
  }

  startButton.disabled = true;
  startButton.textContent = "Starting...";
  let refreshedAvailability = false;
  try {
    const response = await fetch("/api/experiments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const responsePayload = await response.json();
    if (!response.ok) {
      showMessage(responsePayload.error?.message || "Could not start experiment", "error");
      if (responsePayload.error?.code === "camera_busy") {
        await loadCameras({ preserveMessage: true });
        refreshedAvailability = true;
      }
      return;
    }
    showMessage("Experiment started. This camera is now running.", "info");
    await loadCameras({ preserveMessage: true });
    refreshedAvailability = true;
  } catch (error) {
    showMessage(error.message, "error");
  } finally {
    if (!refreshedAvailability) {
      startButton.textContent = "Start";
      updateCameraAvailability({ preserveMessage: true });
    }
  }
}

cameraSelect.addEventListener("change", () => {
  updateCameraAvailability();
  scheduleNameCheck();
});
nameInput.addEventListener("input", scheduleNameCheck);
previewButton.addEventListener("click", preview);
form.addEventListener("submit", startExperiment);

loadCameras().catch((error) => {
  showMessage(error.message, "error");
});
