# Configuration Reference — CS2 RGB Sync

## Local Storage Locations

User settings, shared GSI authentication tokens, and rotating application logs are stored per Windows user in `%LOCALAPPDATA%\CS2RGBSync\`:

| Path | Purpose | Notes |
| ---- | ------- | ----- |
| `%LOCALAPPDATA%\CS2RGBSync\config.json` | User settings and local GSI token | Preserved across upgrades; created from `config/default_config.json` on first run |
| `%LOCALAPPDATA%\CS2RGBSync\logs\cs2rgbsync.log` | Application logs (2 MB x 3 rotating files) | Sensitive tokens are masked as `***REDACTED***` |

An anonymized template without any real token is available in [`config.example.json`](../config.example.json).

---

## Configuration Sections (`config.json`)

### `server`
- `host` *(string, fixed)*: Always `"127.0.0.1"`. `ConfigManager` rejects non-loopback hosts for security.
- `port` *(int)*: Local HTTP port (`3000` default; valid range `1024..65535`). If changed, click **Instalar / Atualizar Arquivo GSI** in Settings so CS2 uses the updated URI.
- `token` *(string)*: Local shared GSI auth secret automatically generated (`secrets.token_urlsafe(24)`) on first run. Used solely to authenticate local CS2 HTTP POST payloads.

### `gsi`
- `cs2_path` *(string)*: Path to `...\Counter-Strike Global Offensive\game\csgo`.
- `buffer` *(float)*: CS2 GSI `buffer` parameter (`0.05` s default).
- `throttle` *(float)*: CS2 GSI `throttle` parameter (`0.05` s default).
- `timeout` *(float)*: CS2 GSI `timeout` parameter (`5.0` s default).
- `heartbeat` *(float)*: CS2 GSI periodic heartbeat interval (`15.0` s default).
- `disconnect_timeout_s` *(float)*: Time without incoming GSI payloads (`35.0` s default) before marking CS2 disconnected and restoring iCUE control.

### `hardware`
- `sdk_path` *(string)*: Optional path to a custom iCUE SDK DLL. Leave empty (`""`) to use the bundled `iCUESDK.x64_2019.dll`.
- `target_model` *(string)*: Optional device model substring filter. Leave empty (`""`, default) to automatically select the first connected Corsair device exposing controllable RGB LEDs via iCUE SDK. If set, `ICueController` prioritizes matching models and falls back to other detected Corsair RGB devices.
- `layer_priority` *(int)*: iCUE SDK lighting layer priority (`200` default, range `0..255`).
- `exclusive_control` *(bool)*: Default `false` (uses standard transparent alpha handoff on `restore_default()`).
- `restore_on_exit` *(bool)*: Default `true` — returns lighting control to iCUE when exiting or stopping integration.
- `global_brightness` *(int)*: Global output multiplier (`0..100` %, default `100`).

### `engine`
- `tick_ms` *(int)*: Independent RGB render loop interval (`25` ms default; clamped to `10..200` ms, UI range `15..100` ms).
- `simulation_mode` *(bool)*: Default `false`. Enables internal test events in Dashboard without running CS2.

### `priorities`
Ordered list (highest priority first):
```json
[
  "flashbang",
  "shot",
  "fire",
  "c4",
  "health_critical",
  "health",
  "team_round",
  "weapon"
]
```

### `effects`
By default, only match-reactive combat/objective effects are enabled (`flashbang`, `shot`, `fire`, `c4`), while persistent/phase effects (`health`, `team`, `weapons`) start disabled (`false`) so LEDs stay off (`(0, 0, 0)`) during neutral gameplay unless enabled manually:

- `flashbang`: `enabled: true`, `color: "#FFFFFF"`, `fade_tail_ms: 220`, `binary_fade_ms: 650`, `intensity: 100`.
- `shot`: `enabled: true`, `color: "#FF9900"`, `duration_ms: 50`, `debounce_ms: 40`, `intensity: 100`.
- `fire`: `enabled: true`, `color_primary: "#FF2200"`, `color_secondary: "#FF9900"`, `oscillation_hz: 4.0`, `intensity: 100`.
- `c4`: `enabled: true`, `color: "#FF0000"`, `bomb_timer_s: 40.0`, `initial_interval_s: 1.0`, `min_interval_s: 0.15`, `beep_duration_s: 0.24`, `intensity: 100`.
- `health`: `enabled: false`, `critical_threshold: 25`, `critical_pulse_hz: 2.5`, `color_100: "#00FF00"`, `color_75: "#80FF00"`, `color_50: "#FFFF00"`, `color_25: "#FF9900"`, `color_critical: "#FF0000"`, `intensity: 100`.
- `team`: `enabled: false`, `t_color: "#FF9900"`, `ct_color: "#008CFF"`, `freezetime_pulse: true`, `freezetime_pulse_hz: 0.8`, `intensity: 100`. Applies **exclusively during Freezetime**.
- `weapons`: `enabled: false`, `intensity: 100`, `categories` (`knife`, `pistol`, `rifle`, `sniper`, `smg`, `shotgun`, `grenade`).

### `ui`
- `language` *(string)*: Active interface language code (`"en_US"` default; supported: `"en_US"`, `"pt_BR"`, `"es_ES"`). Can also be changed live in **Settings → 01 · Language** without restarting.
- `start_with_windows` *(bool)*: Registers/removes `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\CS2RGBSync` (`--minimized`).
- `minimize_to_tray` *(bool)*: Default `true`. Closing the window hides it to the system tray instead of quitting.
- `auto_start_integration` *(bool)*: Default `false`. Starts GSI server + RGB engine automatically upon launch.
