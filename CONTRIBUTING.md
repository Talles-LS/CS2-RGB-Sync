# Contributing to CS2 RGB Sync

Thank you for your interest in contributing to **CS2 RGB Sync**.

## Prerequisites

- **OS:** Windows 11 (64-bit)
- **Python:** Python 3.12 (64-bit)
- **Hardware / Runtime (optional for unit tests, required for live hardware checks):**
  - Corsair iCUE 5 installed and running with SDK enabled
  - A Corsair device whose RGB lighting capabilities are exposed by the Corsair iCUE SDK

## Setting Up the Development Environment

1. Create and activate a virtual environment:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Run the application from source:

   ```powershell
   .\.venv\Scripts\python.exe main.py
   ```

4. Run the automated test suite:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -v
   ```

> **Note on Configuration in Development:** By default, running the app writes user settings to `%LOCALAPPDATA%\CS2RGBSync\config.json`. To isolate development tests from personal settings, pass `--config-path <temp_path>\config.json`.

## Repository Structure Overview

- `app/` — Core backend: config manager, GSI HTTP server, GSI parser, event manager, priority resolver, RGB engine, iCUE controller, GSI simulator, and `SyncService` facade
- `ui/` — PySide6 desktop GUI (`Obsidian Calibre` dark theme, `Optical Reticle` vector marks, 4 pages + tray integration)
- `config/` — Default factory settings template (`default_config.json`)
- `gsi/` — Reference Counter-Strike 2 GSI configuration template (token-free)
- `assets/icons/` — Official `Optical Reticle` SVG/PNG/ICO assets
- `installer/` — Inno Setup installer script (`CS2RGBSync.iss`)
- `tools/` — Asset generators, GSI probe, and direct hardware diagnostic scripts
- `tests/` — Automated pytest suite covering GSI, parser, events, effects, engine, config, packaging, and offscreen GUI
- `docs/` — Documentation (`INSTALLATION.md`, `CONFIGURATION.md`, `TROUBLESHOOTING.md`) and screenshots (`docs/assets/`)

## Guidelines for Changes

- **Keep local-only security invariants:** HTTP GSI server must bind strictly to `127.0.0.1`, require token verification, and redact tokens in logs and diagnostics (`app/logger.py`).
- **Keep gameplay integrity:** Never read/write CS2 memory, inject code, hook processes, or automate gameplay inputs. Use official CS2 GSI data only.
- **Hardware neutrality:** Rely dynamically on Corsair iCUE SDK device/LED discovery (`app/icue_controller.py`). Avoid hardcoding specific peripheral models or device-type assumptions in the UI or defaults.
- **Do not commit secrets or personal files:** Never include `%LOCALAPPDATA%\CS2RGBSync\config.json`, live GSI tokens, `.env` files, or private logs in commits or pull requests.
- **Test before submitting:** Ensure all tests in `.\.venv\Scripts\python.exe -m pytest -v` pass, adding unit/integration tests for any new logic or bug fix.

## Reporting Bugs & Suggesting Improvements

When opening an issue or pull request, please include:

- Application version (`app/__init__.py`) and whether you ran from source, portable ZIP, or installer
- Steps to reproduce (and anonymized sample GSI payload if relevant — strip tokens and SteamIDs)
- Connected Corsair device model name as shown in **Diagnostics**, if reporting hardware behavior (note whether SDK exposes LEDs or fails to connect)
