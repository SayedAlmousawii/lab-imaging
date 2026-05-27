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

