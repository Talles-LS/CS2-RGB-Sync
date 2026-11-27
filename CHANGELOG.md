# Changelog — CS2 RGB Sync

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project is currently in pre-release preparation (`0.1.0`).

## [Unreleased]

### Added
- **Game State Integration (GSI) Pipeline:**
  - Local loopback HTTP listener (`127.0.0.1`, configurable port) implemented with Flask/Werkzeug (`app/gsi_server.py`).
  - Shared local token authentication and automatic secret masking (`***REDACTED***`) in logs and UI diagnostics (`app/logger.py`).
  - Automatic Steam `libraryfolders.vdf` / Windows Registry CS2 path discovery and non-destructive `gamestate_integration_cs2rgbsync.cfg` installation/removal (`app/gsi_config.py`).
  - Stateful JSON parser (`app/gsi_parser.py`) handling partial updates, `previously`/`added` diffs, explicit zero values vs. omitted fields, binary/int/float intensity scaling, and `round.phase` + `phase_countdowns.phase` reconciliation.
- **Event Detection & Priority RGB Engine (`app/event_manager.py`, `app/effects.py`, `app/rgb_engine.py`):**
  - Independent render thread (default `25 ms` tick, configurable `15–100 ms`) with color smoothing, peak retention, and automatic LED off (`(0, 0, 0)`) or iCUE profile handback outside matches.
  - Eight reactive and state-based RGB effects evaluated in configurable priority order (`flashbang > shot > fire > c4 > health_critical > health > team_round > weapon`):
    - Flashbang (`player.state.flashed`) with real in-game binary (`0 -> 1 -> 0`) and continuous (`0..255` / `0.0..1.0`) scaling support.
    - Weapon shots (`ammo_clip` delta detection with reload/weapon-switch/spectator guards).
    - Fire / Molotov / Incendiary burn damage (`player.state.burning`) prioritized above C4.
    - C4 planted countdown approximation (`40.0 s` configurable timer with accelerating red pulses).
    - Health & Critical Health gradient/pulse (disabled by default).
    - Team/Freezetime CT & TR colors (disabled by default).
    - Active weapon category colors (disabled by default).
  - Built-in GSI Simulator (`app/simulator.py`) explicitly tagged as simulation telemetry in the UI.
- **Corsair iCUE SDK Integration (`app/icue_controller.py`):**
  - Thread-safe Corsair iCUE SDK v4 integration via `cuesdk==4.0.84` (`iCUESDK.x64_2019.dll`).
  - Dynamic device discovery via `CorsairDeviceType.CDT_All` and runtime LED enumeration via `get_led_positions(device_id)` without altering hardware profiles, DPI, or macros.
  - Safe teardown sequencing (`restore_default()`, `CorsairUnsubscribeFromEvents()`, `CorsairDisconnect()`) keeping C callback references alive until disconnect completes.
- **Desktop GUI & Distribution (`ui/`, `installer/`):**
  - PySide6 desktop interface using the **Obsidian Calibre** dark theme and vector **Optical Reticle** brand assets across Dashboard, RGB Effects, Settings, Diagnostics, and Windows system tray.
  - PyInstaller portable packaging (`CS2RGBSync.spec`) and Inno Setup 6 Windows installer (`installer/CS2RGBSync.iss`) with automatic Steam/CS2 detection, Start Menu/Desktop shortcuts, and non-destructive uninstallation.

### Changed
- **Hardware-Agnostic Corsair Device Identity:** Replaced single-peripheral defaults (`target_model: ""`) and mouse-specific UI/text references with generic Corsair iCUE SDK device discovery and dynamic model display (showing `"NENHUM DISPOSITIVO"` when no compatible device is connected).
- **CT / TR Team Illumination Scoped Strictly to Freezetime:** Fixed `evaluate_team_round` (`app/effects.py`) and `GameStateSnapshot.is_freezetime` (`app/gsi_parser.py`) using both `round.phase` and `phase_countdowns.phase` so custom CT/TR colors activate exclusively during Freezetime and turn off immediately when a round transitions to `live`, `over`, `warmup`, or partial updates.

### Removed
- **HE Grenade Explosion Effect (`he_explosion`):** Completely removed from default configuration, priority lists, config migration (`config_version: 2`), GSI `.cfg` generation (`allgrenades`), event detection, effect evaluation, simulator, and UI.

### Fixed
- **Clean Application Exit Without Tray Minimize:** Fixed `MainWindow.closeEvent` (`ui/main_window.py`) so closing the main window when `ui.minimize_to_tray` is `false` shuts down `SyncService` and explicitly exits the `QApplication` event loop.
