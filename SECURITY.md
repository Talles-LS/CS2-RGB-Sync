# Security Policy

## Supported Versions

CS2 RGB Sync is currently in pre-release preparation (`0.1.0`). Security fixes apply to the latest development state and upcoming tagged releases.

| Version | Supported |
| ------- | --------- |
| `0.1.0` (pre-release) | Yes |

## Architecture & Threat Model

CS2 RGB Sync operates locally on Windows:

- The Game State Integration (GSI) listener binds strictly to loopback (`127.0.0.1`) via `app/config_manager.py` and `app/gsi_server.py`. Attempts to set a non-loopback host are rejected.
- Authentication uses a locally generated shared token (`server.token`) written into `%LOCALAPPDATA%\CS2RGBSync\config.json` and `gamestate_integration_cs2rgbsync.cfg`.
- Sensitive tokens are automatically redacted (`***REDACTED***`) in logs and Diagnostic UI payload previews (`app/logger.py`, `app/gsi_server.py`).
- CS2 RGB Sync does **not** read or write CS2 process memory, inject DLLs, hook game functions, install drivers, or transmit gameplay data to remote servers.

## Reporting a Vulnerability

Please report suspected security vulnerabilities responsibly through the repository's GitHub **Security Advisories** (*Security -> Advisories -> Report a vulnerability*) if enabled, or via a confidential report path on the GitHub project page before opening a public discussion.

If private reporting is not available on the hosted fork/repository, open a GitHub issue containing only high-level reproduction steps without disclosing exploitable payloads or personal secrets until maintainers coordinate a fix.

### What to Include in a Report

- Affected module or file path (e.g., `app/gsi_server.py`, `app/config_manager.py`, installer script)
- Clear step-by-step reproduction instructions
- Expected vs. actual security impact
- Python version / packaged build used when reproducing

### Protecting Your Privacy When Reporting

**Never attach or paste** any of the following in issues, screenshots, or reports:

- Your real `%LOCALAPPDATA%\CS2RGBSync\config.json`
- Your `gamestate_integration_cs2rgbsync.cfg` file containing your live `server.token`
- Unredacted log files, SteamIDs, or local filesystem paths containing your Windows username
