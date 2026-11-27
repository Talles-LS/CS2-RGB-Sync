# Troubleshooting — CS2 RGB Sync

## 1. Corsair iCUE Connected, Device Not Detected or Not Lighting Up

1. Ensure **Corsair iCUE** is open and running in the background.
2. Inside Corsair iCUE, go to **Settings -> SDK** and verify **iCUE SDK** / **Game & Application Integrations** is enabled.
3. Open **Diagnostics** in CS2 RGB Sync and inspect **Device** and **SDK State**:
   - If the SDK status shows `CSS_ConnectionRefused`, iCUE SDK access is disabled or blocked in iCUE settings.
   - If it shows `NO DEVICE` (`NENHUM DISPOSITIVO` / `SIN DISPOSITIVO`), check that your Corsair device appears in iCUE and exposes controllable RGB LEDs via the SDK.
4. Check whether `hardware.target_model` in `%LOCALAPPDATA%\CS2RGBSync\config.json` contains an old model filter. Leave it empty (`""`) to let CS2 RGB Sync automatically select any compatible connected Corsair RGB device.

> Remember: Compatibility depends on the device capabilities exposed by the Corsair iCUE SDK. Not every Corsair product or RGB device is necessarily supported.

---

## 2. Counter-Strike 2 Is Not Sending GSI Updates

1. Click **START INTEGRATION** in the **Dashboard** so the local HTTP server (`127.0.0.1:<port>`) is listening (`Listening :<port>`).
2. Open **Settings** and verify the detected CS2 folder ends with:
   `...\Counter-Strike Global Offensive\game\csgo`
3. Click **Install / Update GSI File** to write `gamestate_integration_cs2rgbsync.cfg` inside `game\csgo\cfg\`.
4. **Restart Counter-Strike 2** if the game was already running when `.cfg` was created or updated (CS2 reads GSI `.cfg` files at startup).
5. In **Diagnostics**, verify `GSI Requests` (`ok=...`) increments while playing or in Practice mode, and confirm no `err=` auth failures are occurring (which indicate a mismatched token or port between `config.json` and the `.cfg` file — clicking **Install / Update GSI File** resynchronizes them).

---

## 3. Port `3000` Already in Use

If another local tool (Grafana, Node.js dev server, etc.) is listening on `127.0.0.1:3000`:

1. Open **Settings** -> change **HTTP port** (e.g., `3001` or `4123`, valid range `1024..65535`) -> click **Save Settings**.
2. Click **Install / Update GSI File**.
3. Restart integration and restart CS2.

---

## 4. CT / T Team Colors Do Not Appear During Rounds

By design, CT and T team colors apply **exclusively during Freezetime**:

1. Ensure **Freezetime (CT / T)** (`effects.team.enabled`) is switched **ON** in **RGB Effects** (it is disabled by default) and click **Apply & Save**.
2. During live rounds, round-over phases, warmup, or menus, `team_round` stays inactive so your device remains idle `(0, 0, 0)` or yields to combat/objective effects.
3. Verify your `gamestate_integration_cs2rgbsync.cfg` includes `"phase_countdowns" "1"` (older `.cfg` files can be refreshed by clicking **Install / Update GSI File** in **Settings**).

---

## 5. Testing Effects Safely Without Launching CS2 (Simulator)

1. In **Dashboard**, expand **MANUAL SIMULATION (TEST WITHOUT CS2)** by switching **Enable controls** ON.
2. Trigger **Flashbang**, **Fire Shot**, **Fire**, **Plant/Defuse/Explode C4**, **HP** presets, **CT/T**, **Freezetime / Live Round / Round Over**, or **Weapons**.
3. Use **Pause / Resume** to freeze/unfreeze animations cleanly, **Reset** to clear active states back to `CT · live · 100 HP`, and **Stop** to end simulation and return LEDs to idle / iCUE defaults.

---

## 6. RGB Color Remains Active After Closing the Window

Check if **Minimize to system tray when closing window** is enabled in **Settings**. When active, clicking **X** hides the app to the Windows system tray while keeping integration running. To exit completely and hand lighting control back to iCUE, right-click the tray icon and click **Quit** (or click **STOP INTEGRATION** in the Dashboard).

---

## 7. Resetting Local Data or Removing App State

To perform a clean reset:

1. Stop integration and quit the app completely from the tray (**Quit**).
2. Delete `%LOCALAPPDATA%\CS2RGBSync\` (contains `config.json` and `logs/`).
3. Remove `gamestate_integration_cs2rgbsync.cfg` from `...\game\csgo\cfg\` (or run `CS2RGBSync.exe --uninstall-gsi "<cs2_dir>"`).
