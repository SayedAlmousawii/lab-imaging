# Lab Imaging

Developer setup notes for the lab imaging system.

This repository builds a local laboratory imaging system for periodic still
captures from USB webcams. This is the developer README; the lab-staff runbook
will be finalized later in Phase 5.

## Setup

Requires Python 3.11.

```sh
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

See `AGENTS.md` and `specs/` for the design. Start with
`specs/00_README.md`.

For Phase 4 Windows validation, use
`specs/phase-4-windows-manual-validation.md` after pulling the
`phase-4-windows-verification` branch on the Windows lab machine.

## Dashboard

After camera setup has created `config/cameras.json`, start the local
dashboard with:

```sh
python -m labcam.main
```

By default the dashboard binds to `127.0.0.1` and has no authentication.
If `allow_lan_access` is set to `true` in `config/settings.json`, it binds
to the local network instead; use that only on a trusted lab network.

The dashboard ships with self-hosted Inter and JetBrains Mono webfonts
under `labcam/web/static/fonts/` (SIL OFL 1.1; license at
`labcam/web/static/fonts/OFL.txt`). No CDN is contacted at runtime —
the dashboard renders identically offline.

If `design_handoff_lab_imaging/` exists locally, it is a gitignored
Claude Design reference export only. It is not shipped runtime code.
