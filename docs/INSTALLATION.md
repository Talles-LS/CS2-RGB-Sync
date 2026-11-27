# Installation Guide — CS2 RGB Sync

## Requirements

- **Operating System:** Windows 11 (64-bit)
- **Software:**
  - [Corsair iCUE](https://www.corsair.com/icue) installed, running, with **SDK** enabled (*Settings -> SDK -> Enable iCUE SDK*)
  - Counter-Strike 2 installed via Steam
- **Hardware:**
  - A Corsair RGB device recognized by Corsair iCUE whose lighting zones are exposed through the Corsair iCUE SDK

> **Hardware Note:** Compatibility depends on the device capabilities exposed by the Corsair iCUE SDK. Not every Corsair product or RGB device is necessarily supported.

---

## Option 1: Windows Installer (`CS2RGBSync_Setup.exe`)

1. Download `CS2RGBSync_Setup.exe` from the local build output or a future official Release.
2. Double-click `CS2RGBSync_Setup.exe`.
3. Choose optional tasks during setup:
   - Desktop shortcut
   - Start automatically with Windows (`--minimized`)
   - Automatically configure Counter-Strike 2 GSI (`gamestate_integration_cs2rgbsync.cfg`)
4. If GSI auto-setup is checked, verify the auto-detected CS2 path (`...\Counter-Strike Global Offensive\game\csgo`) or browse to it manually.
   - Only `gamestate_integration_cs2rgbsync.cfg` is written inside `game\csgo\cfg\`. No CS2 binaries or other game configs are modified.
5. Finish installation and launch **CS2 RGB Sync**.

### Uninstalling

- Close **CS2 RGB Sync** completely from the Windows system tray (*Right-click tray icon -> Quit*).
- Open **Windows Settings -> Apps -> Installed apps -> CS2 RGB Sync -> Uninstall**.
- During uninstallation, you can choose whether to remove the managed `gamestate_integration_cs2rgbsync.cfg` file. Personal preferences in `%LOCALAPPDATA%\CS2RGBSync\` are left untouched unless removed manually.

---

## Option 2: Portable ZIP (`CS2RGBSync_Portable_v0.2.0.zip`)

1. Extract the **entire** archive preserving its directory structure so `CS2RGBSync.exe` and the `_internal\` folder remain side-by-side in `CS2RGBSync\`.
2. Run `CS2RGBSync\CS2RGBSync.exe`. (Python does **not** need to be installed.)
3. Open **Settings** inside the app:
   - *(Optional)* Switch the interface language in **01 · Language** (`English`, `Português (Brasil)`, `Español`).
   - Click **Detect Steam** (or **Browse Folder...**) to locate `...\Counter-Strike Global Offensive\game\csgo`.
   - Click **Install / Update GSI File** to write `gamestate_integration_cs2rgbsync.cfg`.
4. Restart Counter-Strike 2 if it was already open so CS2 loads the new GSI `.cfg` file.

---

## Option 3: Running from Source (Developers)

Requirements: Python 3.12 (64-bit) on Windows 11.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Optional CLI utilities supported by `main.py` (and `CS2RGBSync.exe`):

- `--minimized` — Start minimized in the Windows system tray
- `--config-path <path>` — Use an isolated custom `config.json` path
- `--setup-gsi <cs2_dir>` — Write `gamestate_integration_cs2rgbsync.cfg` into `<cs2_dir>\cfg\`
- `--uninstall-gsi <cs2_dir>` — Remove only a CS2 RGB Sync-managed `gamestate_integration_cs2rgbsync.cfg`
- `--self-check` — Validate loopback GSI HTTP server, token redaction, PySide6, and iCUE SDK library loading
