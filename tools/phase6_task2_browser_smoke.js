#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const PROJECT_ROOT = path.resolve(__dirname, "..");
const SCRIPT_PATH = path.join(PROJECT_ROOT, "labcam", "web", "static", "cameras.js");

class ScenarioFailure extends Error {}

class ClassList {
  constructor() {
    this.items = new Set();
  }

  add(name) {
    this.items.add(name);
  }

  remove(name) {
    this.items.delete(name);
  }
}

class FakeInput {
  constructor({ value = "", checked = false } = {}) {
    this.value = value;
    this.checked = checked;
  }
}

class FakeCard {
  constructor({ index, key, label, notes, stress }) {
    this.dataset = {
      cameraIndex: String(index),
      cameraKey: key,
    };
    this.inputs = {
      ".js-label": new FakeInput({ value: label }),
      ".js-notes": new FakeInput({ value: notes }),
      ".js-stress": new FakeInput({ checked: stress }),
    };
  }

  querySelector(selector) {
    return this.inputs[selector] || null;
  }
}

class FakeElement {
  constructor(id) {
    this.id = id;
    this.classList = new ClassList();
    this.disabled = false;
    this.textContent = "";
    this._innerHTML = "";
    this.cards = [];
    this.listeners = new Map();
    this.value = "";
  }

  set innerHTML(value) {
    this._innerHTML = String(value);
    if (this.id === "detected-grid") {
      this.cards = parseCards(this._innerHTML);
    }
  }

  get innerHTML() {
    return this._innerHTML;
  }

  addEventListener(eventName, handler) {
    this.listeners.set(eventName, handler);
  }

  querySelectorAll(selector) {
    if (selector === "[data-camera-index]" || selector === "[data-camera-key]") {
      return this.cards;
    }
    return [];
  }
}

function unescapeAttr(value) {
  return String(value)
    .replaceAll("&quot;", '"')
    .replaceAll("&#039;", "'")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&amp;", "&");
}

function inputValue(html, className) {
  const re = new RegExp(`<input[^>]*class="[^"]*${className}[^"]*"[^>]*value="([^"]*)"`, "s");
  return unescapeAttr(html.match(re)?.[1] || "");
}

function stressChecked(html) {
  const match = html.match(/<input[^>]*class="[^"]*js-stress[^"]*"[^>]*>/s);
  return !!match?.[0].includes("checked");
}

function parseCards(html) {
  const cards = [];
  const re = /<article class="setup-card" data-camera-index="([^"]+)" data-camera-key="([^"]+)">([\s\S]*?)<\/article>/g;
  let match = re.exec(html);
  while (match) {
    cards.push(
      new FakeCard({
        index: Number(match[1]),
        key: unescapeAttr(match[2]),
        label: inputValue(match[3], "js-label"),
        notes: inputValue(match[3], "js-notes"),
        stress: stressChecked(match[3]),
      })
    );
    match = re.exec(html);
  }
  return cards;
}

function createHarness() {
  const elements = new Map();
  for (const id of [
    "detected-grid",
    "detected-count",
    "camera-alerts",
    "detect-button",
    "save-button",
    "stress-button",
    "stress-cycles",
    "stress-results",
  ]) {
    elements.set(id, new FakeElement(id));
  }
  elements.get("stress-cycles").value = "100";

  return {
    elements,
    document: {
      querySelector(selector) {
        if (!selector.startsWith("#")) return null;
        return elements.get(selector.slice(1)) || null;
      },
    },
  };
}

function camera(index, label, strategy, stableId) {
  return {
    index,
    label,
    identity_strategy: strategy,
    stable_id: stableId,
    warnings: [],
    identity_warning: strategy === "index_fallback",
  };
}

function response(payload) {
  return {
    ok: true,
    status: 200,
    async json() {
      return payload;
    },
    async blob() {
      return new Blob(["preview"], { type: "image/jpeg" });
    },
  };
}

function cardValues(grid) {
  return grid.cards.map((card) => ({
    index: card.dataset.cameraIndex,
    label: card.querySelector(".js-label").value,
    notes: card.querySelector(".js-notes").value,
    stress: card.querySelector(".js-stress").checked,
  }));
}

function assert(condition, message) {
  if (!condition) {
    throw new ScenarioFailure(message);
  }
}

async function main() {
  const harness = createHarness();
  const grid = harness.elements.get("detected-grid");
  let mode = "two";
  let previewCalls = 0;

  const context = {
    Blob,
    URL: {
      createObjectURL() {
        return `blob:preview-${++previewCalls}`;
      },
      revokeObjectURL() {},
    },
    document: harness.document,
    fetch: async (url, options = {}) => {
      if (url === "/api/cameras/detected") {
        const detected =
          mode === "two"
            ? [
                camera(0, "camera-0", "index_fallback", "0"),
                camera(1, "camera-1", "index_fallback", "1"),
              ]
            : [camera(0, "FaceTime HD Camera", "hardware_id", "facetime")];
        return response({
          configured: [
            { label: "saved-0", last_seen_index: 0, notes: "saved note 0" },
            { label: "saved-1", last_seen_index: 1, notes: "saved note 1" },
          ],
          detected,
        });
      }
      if (url === "/api/cameras/detected/preview" && options.method === "POST") {
        return response({});
      }
      throw new ScenarioFailure(`Unexpected fetch: ${options.method || "GET"} ${url}`);
    },
    console,
  };

  vm.runInNewContext(fs.readFileSync(SCRIPT_PATH, "utf8"), context, {
    filename: SCRIPT_PATH,
  });
  await context.loadDetected();

  assert(grid.cards.length === 2, `Expected two camera cards, got ${grid.cards.length}`);
  grid.cards[0].querySelector(".js-label").value = "draft-0";
  grid.cards[0].querySelector(".js-notes").value = "draft-note-0";
  await context.capturePreview(0);

  let values = cardValues(grid);
  assert(values[0].label === "draft-0", `Preview reset label: ${JSON.stringify(values)}`);
  assert(values[0].notes === "draft-note-0", `Preview reset notes: ${JSON.stringify(values)}`);

  grid.cards[0].querySelector(".js-label").value = "draft-after-0";
  grid.cards[1].querySelector(".js-label").value = "draft-1";
  grid.cards[1].querySelector(".js-notes").value = "draft-note-1";
  grid.cards[1].querySelector(".js-stress").checked = false;
  await context.capturePreview(1);

  values = cardValues(grid);
  assert(values[0].label === "draft-after-0", `Previewing camera 1 reset camera 0: ${JSON.stringify(values)}`);
  assert(values[1].label === "draft-1", `Previewing camera 1 reset camera 1: ${JSON.stringify(values)}`);
  assert(values[1].notes === "draft-note-1", `Previewing camera 1 reset notes: ${JSON.stringify(values)}`);
  assert(values[1].stress === false, `Previewing camera 1 reset stress checkbox: ${JSON.stringify(values)}`);

  mode = "one";
  await context.capturePreview(0);

  values = cardValues(grid);
  assert(values.length === 1, `Camera-list change did not re-render to one card: ${JSON.stringify(values)}`);
  assert(values[0].label !== "draft-after-0", `Camera-list change preserved stale draft: ${JSON.stringify(values)}`);

  console.log("PASS draft camera mapping inputs survive preview re-renders");
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exit(1);
});
