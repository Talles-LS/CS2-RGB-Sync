# Changelog — CS2 RGB Sync

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-11-27

### Added
- **Full Multi-Language Internationalization (i18n):**
  - **English (`en_US`)** is now the official default language for fresh installations, default configs (`ui.language: "en_US"`), UI strings, documentation, and Release Notes.
  - Added complete JSON translation catalogs in [`locales/`](locales/) for **English (`en_US`)**, **Português (Brasil) (`pt_BR`)**, and **Español (`es_ES`)** managed by [`app/i18n.py`](app/i18n.py) with automatic `en_US` fallback.
  - Added a dedicated **01 · Language** selector button in **Settings** (`ui/settings_page.py`) displaying written language names (`English`, `Português (Brasil)`, `Español`) that switches the entire interface (Sidebar, Dashboard, RGB Effects, Settings, Diagnostics, Engine effect labels, Dialogs, and System Tray menu) immediately at runtime without restarting, persisting the user's preference automatically.
  - Added safe migration in `ConfigManager` preserving any previously saved language choice while defaulting unconfigured installs to `en_US` without altering other settings.
  - Added multi-language support (`english`, `ptbr`, `spanish`) in the Windows Inno Setup installer (`installer/CS2RGBSync.iss`).
- **Simulator Lifecycle Controls & Round Over Phase:**
  - Added **Pause / Resume**, **Reset**, and **Stop** controls alongside **Round Over** trigger support inside the Dashboard Simulator drawer (`ui/dashboard.py`, `app/sync_service.py`).
- **Expanded Automated & Visual Verification:**
  - Added [`tests/test_i18n.py`](tests/test_i18n.py) (JSON key parity, fallback, normalization, migration preservation, and live runtime UI + tray switching across all 3 languages) and [`tests/test_simulator_pipeline.py`](tests/test_simulator_pipeline.py) (all 8 effects, simultaneous priority interactions, Pause/Resume/Reset/Stop lifecycle, gunfire edge cases, and real-GSI isolation).

### Fixed
- **Simulator Render Loop & Real Pipeline Execution:**
  - Starting Simulation Mode or triggering a simulated action without real GSI integration running now connects available hardware and starts `RGBEngine`'s real render loop so time-driven effects (`c4`, `fire`, `health_critical`, `team_round` Freezetime pulse), `shot` expiration, and `flashbang` decay animate continuously instead of freezing on frame 1.
  - Exiting Simulation Mode cleanly stops the engine and calls `restore_default()` when real integration is inactive, or restores the latest real GSI state without leaking simulated timers.
- **Gunfire Simulation Edge Cases:**
  - Fixed `trigger_shot()` silently failing on the very first click, during Freezetime, from non-ballistic slots (knife/grenade), or at 0 ammo by emitting clean baseline transitions through `GSIParser -> EventManager -> RGBEngine`.
- **State Reset, Config Sync & Real-GSI Isolation:**
  - Added `GSISimulator.reset()`, accurate `previously` diff tracking (no longer injecting fake bomb-planted clears on every payload), `RGBEngine.reset_transient_state()`, `_sim_event_mgr` parameter synchronization in `apply_config()`, and strict separation of `_real_last_payload` / `_sim_last_payload`.

## [0.1.0-rc1] - 2026-11-26

### Added
- **Game State Integration (GSI) Pipeline:**
  - Local loopback HTTP listener (`127.0.0.1`, configurable port) implemented with Flask/Werkzeug (`app/gsi_server.py`).
  - Shared local token authentication and automatic secret masking (`***REDACTED***`) in logs and UI diagnostics (`app/logger.py`).
  - Automatic Steam `libraryfolders.vdf` / Windows Registry CS2 path discovery and non-destructive `gamestate_integration_cs2rgbsync.cfg` installation/removal (`app/gsi_config.py`).
  - Stateful JSON parser (`app/gsi_parser.py`) handling partial updates, `previously`/`added` diffs, explicit zero values vs. omitted fields, binary/int/float intensity scaling, and `round.phase` + `phase_countdowns.phase` reconciliation.
- **Event Detection & Priority RGB Engine (`app/event_manager.py`, `app/effects.py`, `app/rgb_engine.py`):**
  - Independent render thread (default `25 ms` tick, configurable `15–100 ms`) with color smoothing, peak retention, and automatic LED off (`(0, 0, 0)`) or iCUE profile handback outside matches.
  - Eight reactive and state-based RGB effects evaluated in configurable priority order (`flashbang > shot > fire > c4 > health_critical > health > team_round > weapon`).
  - Built-in GSI Simulator (`app/simulator.py`) explicitly tagged as simulation telemetry in the UI.
- **Corsair iCUE SDK Integration (`app/icue_controller.py`):**
  - Thread-safe Corsair iCUE SDK v4 integration via `cuesdk==4.0.84` (`iCUESDK.x64_2019.dll`).
  - Dynamic device discovery via `CorsairDeviceType.CDT_All` and runtime LED enumeration via `get_led_positions(device_id)` without altering hardware profiles, DPI, or macros.
- **Desktop GUI & Distribution (`ui/`, `installer/`):**
  - PySide6 desktop interface (**Obsidian Calibre** theme + **Optical Reticle** mark), PyInstaller portable packaging (`CS2RGBSync.spec`), and Inno Setup 6 Windows installer (`installer/CS2RGBSync.iss`).
- **MIT License (`LICENSE`):** Licensed original project source code under the MIT License (`Copyright (c) 2026 Tales Souza`).
