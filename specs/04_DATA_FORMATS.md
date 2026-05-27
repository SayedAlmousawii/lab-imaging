# Data Formats & On-Disk Layout

All data is stored as plain files. No database. The per-experiment folder is the
complete, portable dataset.

## Experiment Folder

```
experiments/
  2026-05-27_oil-water-trialA_station1/
    metadata.json
    capture_log.txt
    images/
      0000_2026-05-27T14-00-00.jpg
      0001_2026-05-27T14-05-00.jpg
      0002_2026-05-27T14-10-00.jpg
      ...
```

### Folder name
Format: `<YYYY-MM-DD>_<experiment-name>_<camera-label>`
- Self-describing in a file browser listing.
- Sanitize the experiment name (no spaces/slashes; use hyphens).
- If a collision occurs, append a short suffix (e.g. `_2`).

### Image filenames
Format: `<NNNN>_<YYYY-MM-DDTHH-MM-SS>.jpg`
- `NNNN` — zero-padded sequence number → perfect chronological sort everywhere.
- Embedded timestamp → know the local lab time when each frame was taken without
  opening it.
- Colons avoided in the time (`HH-MM-SS`) for Windows filename compatibility.
- Sequence `0000` is the **t=0 baseline** captured immediately on start.
- If the baseline capture fails after configured retries, the experiment start
  fails. For later scheduled captures, a total failure creates a sequence gap in
  the images and an error in the log; the next scheduled capture uses the next
  monotonic sequence number.

Timestamps in JSON and logs use local lab time in ISO-8601 format with timezone
offset, for example `2026-05-27T14:00:00+03:00`. Image filenames use local lab
time without an offset because Windows filenames cannot contain colons.

## `metadata.json` (per experiment)

```json
{
  "name": "oil-water-trialA",
  "camera_label": "station1",
  "camera_id": "<hardware-id-usb-port-or-index>",
  "camera_identity_strategy": "hardware_id",
  "interval_minutes": 5,
  "duration_hours": 12,
  "operator": "Sara",
  "notes": "Batch 3, 40C ambient",
  "started_at": "2026-05-27T14:00:00+03:00",
  "planned_stop_at": "2026-05-28T02:00:00+03:00",
  "ended_at": "2026-05-28T02:00:00+03:00",
  "end_reason": "completed",
  "images_captured": 145,
  "interval_seconds_effective": 300
}
```

Field notes:
- `end_reason` ∈ `completed` | `stopped_early` | `unknown` (e.g. if a crash left
  it unfinalized — written as `unknown` only if discovered later; v1 does not
  auto-resume).
- `ended_at` / `images_captured` are filled in when the experiment finalizes.
- Write `metadata.json` at start with the known fields; update on finalize.
  Writes must be atomic (temporary file + fsync + rename).

## `capture_log.txt` (per experiment)

One line per event, append-only, human-readable. Example:

```
2026-05-27T14:00:00+03:00  START   experiment=oil-water-trialA camera=station1 interval=5min duration=12h
2026-05-27T14:00:01+03:00  CAPTURE seq=0000 file=0000_2026-05-27T14-00-00.jpg ok
2026-05-27T14:05:00+03:00  CAPTURE seq=0001 file=0001_2026-05-27T14-05-00.jpg ok
2026-05-27T14:10:02+03:00  ERROR   seq=0002 camera open failed, retry 1
2026-05-27T14:10:05+03:00  ERROR   seq=0002 failed after retries; sequence gap recorded
2026-05-27T14:15:00+03:00  CAPTURE seq=0003 file=0003_2026-05-27T14-15-00.jpg ok
...
2026-05-28T02:00:00+03:00  STOP    reason=completed images=145
```

## `config/cameras.json` (camera labels and identity metadata)

Created by `tools/camera_setup.py`. Maps physical cameras to labels and records
how confident the system can be when matching them later.

```json
{
  "cameras": [
    {
      "label": "station1",
      "identity_strategy": "hardware_id",
      "stable_id": "<os-specific hardware/instance id>",
      "last_seen_index": 0,
      "warnings": [],
      "notes": "Left rig, oil column"
    },
    {
      "label": "station2",
      "identity_strategy": "usb_port",
      "stable_id": "<os-specific usb port path>",
      "last_seen_index": 1,
      "warnings": [
        "topology-dependent — moving this camera to a different USB port will break the mapping"
      ],
      "notes": "Right rig"
    }
  ]
}
```

- `identity_strategy` is required and must be one of `hardware_id`, `usb_port`,
  or `index_fallback`.
- `warnings` is required; use an empty array when there are no warnings.
- `stable_id` contains the matching value for the selected strategy. For
  `hardware_id`, it is a true durable hardware identifier. For `usb_port`, it is
  a topology-dependent USB port path. For `index_fallback`, it is the OpenCV
  index value and is not durable.
- `last_seen_index` is a hint OpenCV uses to open the device. Code must
  re-validate it according to `identity_strategy` where possible.
- Labels are free-form but sanitized to alphanumeric plus hyphens; no
  spaces/slashes. `station1`, `station2`, etc. are the suggested convention.

## `config/settings.json` (app settings)

```json
{
  "experiments_dir": "./experiments",
  "web_port": 5000,
  "allow_lan_access": false,
  "warmup_frames": 5,
  "capture_retries": 2,
  "default_interval_minutes": 5,
  "default_duration_hours": 12,
  "jpeg_quality": 90
}
```

`settings.json` is auto-created from defaults on first run. Absence of
`cameras.json` is a hard error that points the operator to `tools/camera_setup.py`.

## Runtime State File (currently-running experiments)

A single small file (e.g. `config/running_state.json`) tracking live experiments
so the dashboard has one source of truth and the program can recover its view of
what's active on restart. Per v1 (Option A) it does **not** resume crashed runs —
on startup, any experiment found in `running_state.json` is marked
`ended_at=<startup time>` and `end_reason="unknown"` in its `metadata.json`, then
`running_state.json` is cleared.

```json
{
  "running": [
    {
      "experiment_id": "2026-05-27_oil-water-trialA_station1",
      "camera_label": "station1",
      "next_capture_at": "2026-05-27T14:15:00+03:00",
      "planned_stop_at": "2026-05-28T02:00:00+03:00",
      "images_captured": 3
    }
  ]
}
```

Writes to `running_state.json` must be atomic (temporary file + fsync + rename).
