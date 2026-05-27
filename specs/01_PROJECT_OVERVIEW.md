# Lab Imaging System — Project Overview

## The Problem

Laboratory experiments currently rely on **mobile phones** to record long-duration
tests (7–20 hours) as continuous video for later review and manual measurement
extraction. This approach causes:

- **Storage limitations** — multi-hour video files are huge.
- **Overheating** — phones run hot during long continuous recording.
- **Battery constraints** — phones can't reliably last a 20-hour unattended run.
- **Unreliable long-term recording** — recordings fail or stop without warning.
- **No multi-experiment management** — one phone per experiment doesn't scale.

## The Goal

Build a **scalable, reliable laboratory imaging system** using dedicated USB
webcams, a central computer, and custom software that:

- Automates **periodic image capture** (not continuous video).
- **Organizes** each experiment's data into a self-contained dataset.
- Supports **multiple simultaneous experiments / stations** on one machine.
- Provides a **local dashboard** to configure, start, monitor, and stop runs.

## Key Insight: Images, Not Video

The measurements are read by sampling the experiment's state at intervals, so
**video is unnecessary**. Capturing one still image every 5–10 minutes:

- A 20-hour run = ~120–240 images per station (vs. ~2M video frames).
- Eliminates storage, overheating, and encoding-reliability problems.
- The capture hardware is **idle >99% of the time**.

This single reframe is what makes the system simple and robust.

## What the System Does (and Doesn't) Do

**Does (v1):**
- Capture clear, timestamped still images of a liquid column against a ruler.
- Organize images per experiment with metadata and logs.
- Run multiple experiments concurrently, each duration-bounded.
- Serve a local web dashboard for control and fresh preview snapshots.

**Does NOT do (v1):**
- No computer vision / automatic level detection. **Readings are manual** — a
  human scrubs the captured images and reads the liquid level against the ruler
  by eye. (Auto-detection is a possible future extension, not in scope now.)
- No continuous video recording.
- No cloud hosting, no external database.

## The Measurement Task

Oil/water level measurement. A **physical ruler sits next to the liquid column**.
The user reviews captured images afterward and records, by eye, where the liquid
sits relative to the ruler. The software's job is purely to produce clear,
consistent, well-organized images that make this manual reading easy and reliable.

## Success Criteria

1. Runs unattended for 7–20 hours without failure.
2. Produces a self-contained, timestamped image dataset per experiment.
3. Handles at least 4 concurrent USB cameras on one machine (target; not a hard
   ceiling given the capture strategy — see Architecture).
4. Usable by lab staff via a dashboard with no terminal/config-file editing.
5. Developed on macOS, deployed reliably on Windows.
