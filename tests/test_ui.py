"""Testes automatizados da interface gráfica PySide6 integrada ao SyncService e RGBEngine."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.config_manager import ConfigManager
from app.icue_controller import RecordingRGBController
from app.logger import REDACTED_PLACEHOLDER
from app.sync_service import SyncService
from ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def _pump_events(app: QApplication, duration_s: float = 0.2) -> None:
    deadline = time.monotonic() + duration_s
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)


def _post_gsi(port: int, payload: dict) -> int:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        return resp.status


def test_ui_end_to_end_live_gsi_effects_simulation_and_diagnostics(
    qapp: QApplication, tmp_path: Path
) -> None:
    cfg_path = tmp_path / "user_config.json"
    cfg_mgr = ConfigManager(user_config_path=cfg_path)
    controller = RecordingRGBController()
    service = SyncService(
        config_manager=cfg_mgr,
        controller=controller,
        port_override=0,
    )
    window = MainWindow(service=service)
    window.show()
    qapp.processEvents()
    try:
        # 1. Navegação entre todas as 4 abas
        for idx in range(4):
            window._select_page(idx)
            assert window.stack.currentIndex() == idx
        window._select_page(0)

        # 2. Iniciar integração pelo botão principal
        window.dashboard_page.toggle_btn.click()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            qapp.processEvents()
            if service.get_ui_snapshot().integration_running:
                break
            time.sleep(0.02)

        snap = service.get_ui_snapshot()
        assert snap.integration_running is True
        assert snap.server_stats.running is True
        active_port = snap.server_stats.port
        assert active_port > 0

        # 3. Envia payload GSI real via HTTP loopback e valida atualização no Dashboard
        token = cfg_mgr.get("server.token")
        status_code = _post_gsi(
            active_port,
            {
                "provider": {
                    "name": "Counter-Strike 2",
                    "appid": 730,
                    "steamid": "76561198000000001",
                },
                "map": {"name": "de_inferno", "phase": "live"},
                "round": {"phase": "live"},
                "player": {
                    "steamid": "76561198000000001",
                    "activity": "playing",
                    "team": "CT",
                    "state": {"health": 100, "armor": 100, "flashed": 0},
                    "weapons": {
                        "weapon_1": {
                            "name": "weapon_m4a1_silencer",
                            "type": "Rifle",
                            "state": "active",
                            "ammo_clip": 20,
                            "ammo_clip_max": 20,
                        }
                    },
                },
                "auth": {"token": token},
            },
        )
        assert status_code == 200
        _pump_events(qapp, 0.25)

        assert window.dashboard_page.lbl_health.text() == "100 HP"
        assert window.dashboard_page.lbl_team.text() == "CT"
        assert "weapon_m4a1_silencer" in window.dashboard_page.lbl_weapon.text()
        assert window.dashboard_page.lbl_ammo.text() == "20/20"
        assert window.dashboard_page.card_cs2.badge_label.text() == "Conectado"
        # Por padrão vida/equipe ficam desativados -> em idle sem eventos o LED fica apagado (0,0,0)
        assert controller.get_status().last_rgba == (0, 0, 0, 255)

        # 4. Aba de Diagnóstico exibe payload sanitizado (nunca token em claro)
        window._select_page(3)
        _pump_events(qapp, 0.15)
        diag_payload = window.diagnostics_page.txt_payload.toPlainText()
        assert REDACTED_PLACEHOLDER in diag_payload
        assert token not in diag_payload
        assert window.diagnostics_page.list_events.count() >= 1

        # 5. Aba de Efeitos: alterar cor/duração e ativar manualmente Vida -> salva em JSON
        window._select_page(1)
        assert window.effects_page.chk_health.isChecked() is False
        assert window.effects_page.chk_team.isChecked() is False
        assert not hasattr(window.effects_page, "chk_he")
        window.effects_page.col_shot.set_color("#123456")
        window.effects_page.spin_shot_dur.setValue(85)
        window.effects_page.chk_health.setChecked(True)
        window.effects_page._on_save()

        reloaded = ConfigManager(user_config_path=cfg_path)
        assert reloaded.get("effects.shot.color") == "#123456"
        assert reloaded.get("effects.shot.duration_ms") == 85
        assert reloaded.get("effects.health.enabled") is True

        # 6. Restaurar padrões preserva token e restaura padrões novos (vida/equipe False, fogo antes da C4, sem HE)
        restored = service.restore_default_settings()
        window.effects_page.load_from_config(restored)
        assert restored["server"]["token"] == token
        assert restored["effects"]["shot"]["color"] == "#FF9900"
        assert restored["effects"]["shot"]["duration_ms"] == 50
        assert restored["effects"]["health"]["enabled"] is False
        assert restored["effects"]["team"]["enabled"] is False
        assert "he_explosion" not in restored["effects"]
        assert restored["priorities"].index("fire") < restored["priorities"].index("c4")

        # 7. Envia Flashbang binária real (flashed=1) via GSI loopback e valida logs diagnósticos sem vazar token
        status_fl = _post_gsi(
            active_port,
            {
                "provider": {
                    "name": "Counter-Strike 2",
                    "appid": 730,
                    "steamid": "76561198000000001",
                },
                "round": {"phase": "live"},
                "player": {
                    "steamid": "76561198000000001",
                    "activity": "playing",
                    "team": "CT",
                    "state": {"health": 100, "flashed": 1},
                },
                "auth": {"token": token},
            },
        )
        assert status_fl == 200
        _pump_events(qapp, 0.20)
        snap_fl = service.get_ui_snapshot()
        assert snap_fl.render_state.active_effect_id == "flashbang"
        assert snap_fl.render_state.current_color_hex == "#FFFFFF"
        assert "GSI diagnóstico" in snap_fl.recent_logs
        assert token not in snap_fl.recent_logs

        # 8. Modo de Simulação exibe banner e testa Flashbang simulada
        window._select_page(0)
        window.dashboard_page.chk_simulation.setChecked(True)
        _pump_events(qapp, 0.15)
        assert window.dashboard_page.sim_banner.isVisible() is True

        service.trigger_simulation("flashbang", intensity=255)
        _pump_events(qapp, 0.15)
        snap_sim = service.get_ui_snapshot()
        assert snap_sim.simulation_mode is True
        assert snap_sim.render_state.active_effect_id == "flashbang"
        assert snap_sim.render_state.current_color_hex == "#FFFFFF"

        # 8. Parar integração pelo botão principal
        window.dashboard_page.toggle_btn.click()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            qapp.processEvents()
            if not service.get_ui_snapshot().integration_running:
                break
            time.sleep(0.02)
        assert service.get_ui_snapshot().integration_running is False
    finally:
        window.shutdown_service()
        assert controller.disconnect_count >= 1


def test_ui_window_close_exits_cleanly_when_minimize_to_tray_disabled(
    qapp: QApplication, tmp_path: Path
) -> None:
    cfg_path = tmp_path / "close_test_cfg.json"
    cfg_mgr = ConfigManager(user_config_path=cfg_path)
    cfg_mgr.set("ui.minimize_to_tray", False)

    controller = RecordingRGBController()
    service = SyncService(config_manager=cfg_mgr, controller=controller, port_override=0)
    window = MainWindow(service=service)
    quit_called = {"flag": False}
    orig_quit = qapp.quit

    def _spy_quit() -> None:
        quit_called["flag"] = True

    qapp.quit = _spy_quit  # type: ignore[method-assign]
    try:
        window.show()
        qapp.processEvents()
        closed = window.close()
        _pump_events(qapp, 0.1)
        assert closed is True
        assert controller.disconnect_count >= 1
        assert quit_called["flag"] is True
    finally:
        qapp.quit = orig_quit  # type: ignore[method-assign]
        window.shutdown_service()
