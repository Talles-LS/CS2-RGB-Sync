"""Ponto de entrada desktop e utilitários CLI do CS2 RGB Sync."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import __app_name__, __version__  # noqa: E402
from app.config_manager import ConfigManager  # noqa: E402
from app.gsi_config import (  # noqa: E402
    GSI_CFG_FILENAME,
    detect_cs2_game_dir,
    install_gsi_cfg,
    normalize_cs2_game_dir,
    uninstall_gsi_cfg,
)
from app.i18n import set_language as set_i18n_language, t  # noqa: E402
from app.logger import REDACTED_PLACEHOLDER, configure_logging, get_logger  # noqa: E402


def _safe_print(msg: str) -> None:
    if sys.stdout is not None:
        print(msg, flush=True)


def _run_setup_gsi(cs2_dir_arg: str, config_path: Optional[str]) -> int:
    logger = get_logger("cli")
    cfg_mgr = ConfigManager(
        user_config_path=Path(config_path) if config_path else None
    )
    set_i18n_language(str(cfg_mgr.get("ui.language", "en_US")))
    detected = detect_cs2_game_dir(preferred_path=cs2_dir_arg)
    if detected is None:
        msg = t("cli.cs2_dir_not_found", path=cs2_dir_arg)
        logger.error(msg)
        _safe_print(f"[ERROR] {msg}")
        return 2

    cfg_mgr.set("gsi.cs2_path", str(detected))
    target = install_gsi_cfg(
        cs2_game_dir=detected,
        port=int(cfg_mgr.get("server.port", 3000)),
        token=str(cfg_mgr.get("server.token", "")),
        buffer=float(cfg_mgr.get("gsi.buffer", 0.05)),
        throttle=float(cfg_mgr.get("gsi.throttle", 0.05)),
        timeout=float(cfg_mgr.get("gsi.timeout", 5.0)),
        heartbeat=float(cfg_mgr.get("gsi.heartbeat", 15.0)),
    )
    _safe_print(t("cli.gsi_installed", target=target))
    return 0


def _run_uninstall_gsi(cs2_dir_arg: str) -> int:
    normalized = normalize_cs2_game_dir(cs2_dir_arg)
    if normalized is not None:
        cfg_file = normalized / "cfg" / GSI_CFG_FILENAME
    else:
        cfg_file = Path(cs2_dir_arg) / "cfg" / GSI_CFG_FILENAME
    removed = uninstall_gsi_cfg(cfg_file)
    _safe_print(
        t("cli.gsi_removed", cfg_file=cfg_file)
        if removed
        else t("cli.gsi_none_removed", cfg_file=cfg_file)
    )
    return 0


def _run_self_check(config_path: Optional[str]) -> int:
    from PySide6.QtWidgets import QApplication  # noqa: F401
    from app.gsi_server import GSIServer
    from app.icue_controller import ICueController, is_icue_process_running

    with tempfile.TemporaryDirectory(prefix="cs2rgbsync_check_") as tmp_dir:
        cfg_file = Path(config_path) if config_path else (Path(tmp_dir) / "config.json")
        cfg_mgr = ConfigManager(user_config_path=cfg_file)
        set_i18n_language(str(cfg_mgr.get("ui.language", "en_US")))
        token = str(cfg_mgr.get("server.token", ""))

        server = GSIServer(host="127.0.0.1", port=0, auth_token=token)
        port = server.start()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/",
                data=json.dumps(
                    {
                        "provider": {"name": "SelfCheck", "appid": 730},
                        "player": {"team": "CT", "state": {"health": 100}},
                        "auth": {"token": token},
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status != 200:
                    _safe_print(t("cli.self_check_http_err", status=resp.status))
                    return 3
            last_payload = server.get_last_payload() or {}
            if (last_payload.get("auth") or {}).get("token") != REDACTED_PLACEHOLDER:
                _safe_print(t("cli.self_check_redact_err"))
                return 4
            _safe_print(t("cli.self_check_http_ok", port=port))
        finally:
            server.stop()

        controller = ICueController(
            sdk_path=cfg_mgr.get("hardware.sdk_path") or None,
            target_model=str(cfg_mgr.get("hardware.target_model", "")),
        )
        if is_icue_process_running():
            if controller.connect(timeout_s=4.0):
                st = controller.get_status()
                _safe_print(
                    t(
                        "cli.self_check_icue_ok",
                        model=st.device_model,
                        leds=st.led_ids,
                    )
                )
                controller.release_and_disconnect()
            else:
                st = controller.get_status()
                _safe_print(t("cli.self_check_icue_warn", err=st.last_error))
                controller.release_and_disconnect()
        else:
            from cuesdk import CueSdk

            _sdk = CueSdk()
            _safe_print(t("cli.self_check_dll_ok"))

    _safe_print(t("cli.self_check_done"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{__app_name__} v{__version__}")
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="Inicia minimizado na bandeja do sistema.",
    )
    parser.add_argument(
        "--setup-gsi",
        type=str,
        default=None,
        help="Instala gamestate_integration_cs2rgbsync.cfg na pasta informada do CS2.",
    )
    parser.add_argument(
        "--uninstall-gsi",
        type=str,
        default=None,
        help="Remove gamestate_integration_cs2rgbsync.cfg gerenciado da pasta do CS2.",
    )
    parser.add_argument(
        "--config-path",
        type=str,
        default=None,
        help="Caminho alternativo do config.json (uso em testes/instalador).",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Executa autodiagnóstico rápido do executável (GSI + PySide6 + iCUE DLL).",
    )
    args = parser.parse_args(argv)

    configure_logging(enable_file=True, enable_console=False)

    if args.setup_gsi:
        return _run_setup_gsi(args.setup_gsi, args.config_path)
    if args.uninstall_gsi:
        return _run_uninstall_gsi(args.uninstall_gsi)
    if args.self_check:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        return _run_self_check(args.config_path)

    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "CS2RGBSync.Desktop.App"
            )
        except Exception:
            pass

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from app.sync_service import SyncService
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)

    icon_file = MainWindow._find_icon_path()
    if icon_file is not None:
        app.setWindowIcon(QIcon(str(icon_file)))

    cfg_mgr = ConfigManager(
        user_config_path=Path(args.config_path) if args.config_path else None
    )
    service = SyncService(config_manager=cfg_mgr)
    window = MainWindow(service=service, start_minimized=args.minimized)
    if not args.minimized:
        window.show()

    app.aboutToQuit.connect(window.shutdown_service)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
