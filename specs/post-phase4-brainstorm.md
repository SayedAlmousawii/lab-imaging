# Lab Imaging — Post Phase 4 Feature Roadmap

## Purpose

This document captures usability, workflow, and operational improvements identified after Phase 4 Windows validation. These are not required for Phase 4 completion but are strong candidates for future feature specifications.

The goal of these features is to transition Lab Imaging from a functional experiment capture system into a polished lab application that requires minimal technical knowledge from end users.

## Disposition

- Phase 5 remains hardening-only: reliability, clearer error surfacing,
  lab-staff documentation, safe defaults, and final v1 polish.
- The usability/workflow ideas in this document are deferred to Phase 6
  and summarized in `specs/phase-6.md`.
- Continuous live preview and maintenance-mode preview require an
  explicit future spec because they affect the current invariant that
  preview is a fresh still captured via open-grab-close.

---

# 1. Startup Camera Verification Workflow

## Problem

Camera indexes and device enumeration can change across:

- Windows
- macOS
- Reboots
- USB reconnects
- Identical webcams

While hardware IDs and index fallback help, they are not ideal as the primary user experience.

## Proposed Solution

On application startup:

1. Detect available cameras.
2. Show live previews for each detected camera.
3. Allow user confirmation or remapping of:
   - Station 1
   - Station 2
   - Station 3
   - etc.
4. Save the mapping for future sessions.

## Workflow

```text
Launch App
↓
Camera Verification
↓
Confirm / Remap Stations
↓
Dashboard
```

## Notes

- Hardware IDs should still be used internally.
- Index fallback should still exist internally.
- Previous mappings should be suggested automatically.
- User confirmation becomes the final source of truth.

---

# 2. Live Preview on New Experiment Page

## Current State

The New Experiment page uses a one-shot preview capture.

```text
Capture Preview
↓
Display Still Image
```

## Proposed Solution

Replace this with a continuous live preview.

## Benefits

Users can verify:

- Correct station
- Framing
- Focus
- Lighting
- Sample placement

before starting a long experiment.

## Additional Features

Optional controls:

- Capture Still
- Refresh Preview

## Technical Notes

When experiment capture begins:

- Live preview must stop safely

or

- Camera access must be shared through a central camera manager.

---

# 3. Maintenance Mode During Experiments

## Problem

Long experiments frequently require:

- Camera repositioning
- Focus adjustment
- Lighting adjustment
- Sample repositioning

The current workflow only provides Stop/End.

## Proposed Solution

Add Maintenance Mode.

## Workflow

```text
Running Experiment
↓
Enter Maintenance Mode
↓
Capture Paused
↓
Live Preview Opens
↓
User Adjustments
↓
Resume Experiment
```

## Maintenance Log Entry

Example:

```json
{
  "type": "maintenance",
  "started_at": "...",
  "ended_at": "...",
  "note": "Adjusted framing"
}
```

## Benefits

- Preserves experiment integrity
- Documents gaps in capture
- Creates audit trail
- Provides safe camera access during runs

---

# 4. Dashboard-Based Camera Configuration

## Goal

Normal users should never need Terminal/PowerShell.

## Current State

Camera setup currently relies on:

```text
camera_setup.py list
camera_setup.py setup
camera_setup.py stress-test
```

## Proposed Solution

Move camera configuration into the dashboard.

## Settings → Cameras

Features:

### Detect Cameras

- Discover available cameras
- Show live previews

### Camera Assignment

- Assign cameras to stations
- Remap stations
- Save mappings

### Camera Verification

- Preview camera feeds
- Confirm correct station assignment

### Camera Stress Test

Run validation directly from dashboard:

```text
Station 1: 100/100 Passed
Station 2: 100/100 Passed
```

## Notes

Terminal tools should remain available for developers.

---

# 5. Settings Page

## Goal

Provide centralized system configuration.

## Initial Categories

### Storage

Experiment save location.

### Cameras

Camera mapping and testing.

### System

Future system configuration options.

### About

Version and diagnostic information.

---

# 6. Configurable Experiment Save Location

## Problem

Experiment storage location is currently configuration-file driven.

## Proposed Solution

Allow users to configure save location from Settings.

## Example

```text
Experiment Storage Folder

C:\LabImaging\Experiments
```

## Features

- Change folder
- Validate folder
- Test write access
- Open folder

## Notes

Changing save location should only affect future experiments.

Existing experiments should remain untouched.

---

# 7. Cloud-Synced Storage Support

## Goal

Support cloud backups without making experiment capture depend on internet connectivity.

## Recommended Architecture

```text
Lab Imaging
↓
Local Save Folder
↓
OneDrive / Google Drive / Dropbox Sync
```

## Notes

The application should:

- Always save locally first
- Never depend on cloud availability
- Remain fully functional offline

## Supported Examples

- OneDrive
- Google Drive Desktop
- Dropbox
- Synology Drive
- Network shares

No direct cloud integration is required initially.

---

# 8. Native Folder Picker (Packaging Phase)

## Goal

Improve save-folder configuration UX after application packaging.

## Current Recommendation

Manual path entry.

## Future Recommendation

Native folder selection dialog:

```text
[Browse...]
```

## Notes

Most appropriate once Electron packaging exists.

---

# 9. Post-Experiment Notes

## Goal

Allow researchers to attach notes after experiment completion.

## Example

```text
Experiment Notes

- Solution became cloudy after 3h
- Sample shifted slightly
- Lighting adjusted during run
```

## Storage

Potential options:

- metadata.json
- notes.txt
- dedicated experiment note model

---

# 10. Experiment Browser

## Goal

Allow users to review previous experiments directly from the dashboard.

## Potential Features

- Experiment list
- Search
- Filter by date
- Filter by station
- Open experiment folder
- View metadata
- View captured images

## Future Possibilities

- Thumbnail gallery
- Timelapse generation
- Export tools

---

# Guiding Principle

The core capture engine should remain simple, reliable, and local-first.

Future development should focus on:

- Usability
- Reliability
- Research workflow support
- Reduced technical requirements
- Reduced dependence on terminal tools

The long-term goal is for a researcher to install, configure, and operate Lab Imaging entirely through the dashboard without requiring command-line interaction.
