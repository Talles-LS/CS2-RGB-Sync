"""Testes dos 12 cenários de Freezetime (CT/TR) e da generalização de hardware."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.config_manager import ConfigManager
from app.effects import _EFFECT_EVALUATORS
from app.event_manager import EventManager
from app.gsi_config import render_gsi_cfg
from app.gsi_parser import GSIParser
from app.i18n import set_language
from app.icue_controller import ICueController, ICueStatusSnapshot, RecordingRGBController
from app.rgb_engine import RGBEngine
from app.sync_service import ServiceSnapshot, SyncService
from ui.effects_page import get_group_meta
from ui.main_window import MainWindow

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CFG_PATH = PROJECT_ROOT / "config" / "default_config.json"


def _load_cfg() -> dict:
    with DEFAULT_CFG_PATH.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def _feed(
    parser: GSIParser,
    event_mgr: EventManager,
    engine: RGBEngine,
    payload: dict,
    t_ns: int,
):
    snap = parser.parse(payload, received_at_ns=t_ns, received_at_wall=t_ns / 1e9)
    events = event_mgr.process_snapshot(snap)
    engine.update_state(snap, events, now_ns=t_ns)
    return snap, engine.step(now_ns=t_ns + 5_000_000)


def _settle(engine: RGBEngine, start_ns: int, frames: int = 16):
    state = engine.get_render_state()
    for i in range(frames):
        state = engine.step(now_ns=start_ns + i * 25_000_000)
    return state


# ---------------------------------------------------------------------------
# Parte 2: Todos os 12 cenários obrigatórios de Freezetime CT / TR
# ---------------------------------------------------------------------------


def test_freezetime_01_and_02_ct_and_tr_activation() -> None:
    cfg = _load_cfg()
    cfg["effects"]["team"]["enabled"] = True
    cfg["effects"]["team"]["freezetime_pulse"] = False
    cfg["effects"]["team"]["ct_color"] = "#1040FF"
    cfg["effects"]["team"]["t_color"] = "#FF7010"

    # 1. Início de round como CT -> aplica cor personalizada CT
    parser = GSIParser()
    mgr = EventManager()
    ctrl_ct = RecordingRGBController()
    eng_ct = RGBEngine(ctrl_ct, cfg)
    snap, state = _feed(
        parser,
        mgr,
        eng_ct,
        {
            "map": {"name": "de_mirage", "phase": "live", "round": 1},
            "round": {"phase": "freezetime"},
            "phase_countdowns": {"phase": "freezetime"},
            "player": {"activity": "playing", "team": "CT", "state": {"health": 100}},
        },
        100_000_000,
    )
    assert snap.is_freezetime is True
    assert state.active_effect_id == "team_round"
    assert state.current_color_hex == "#1040FF"
    assert ctrl_ct.get_status().last_rgba == (16, 64, 255, 255)

    # 2. Início de round como TR -> aplica cor personalizada TR
    parser_t = GSIParser()
    mgr_t = EventManager()
    ctrl_t = RecordingRGBController()
    eng_t = RGBEngine(ctrl_t, cfg)
    snap_t, state_t = _feed(
        parser_t,
        mgr_t,
        eng_t,
        {
            "map": {"name": "de_mirage", "phase": "live", "round": 1},
            "round": {"phase": "freezetime"},
            "phase_countdowns": {"phase": "freezetime"},
            "player": {"activity": "playing", "team": "T", "state": {"health": 100}},
        },
        100_000_000,
    )
    assert snap_t.is_freezetime is True
    assert state_t.active_effect_id == "team_round"
    assert state_t.current_color_hex == "#FF7010"
    assert ctrl_t.get_status().last_rgba == (255, 112, 16, 255)


def test_freezetime_03_04_05_transitions_live_over_and_new_round() -> None:
    cfg = _load_cfg()
    cfg["effects"]["team"]["enabled"] = True
    cfg["effects"]["team"]["freezetime_pulse"] = False

    parser = GSIParser()
    mgr = EventManager()
    ctrl = RecordingRGBController()
    engine = RGBEngine(ctrl, cfg)

    # Freezetime Round 1
    _, st1 = _feed(
        parser,
        mgr,
        engine,
        {
            "map": {"name": "de_inferno", "phase": "live", "round": 1},
            "round": {"phase": "freezetime"},
            "phase_countdowns": {"phase": "freezetime"},
            "player": {"activity": "playing", "team": "CT", "state": {"health": 100}},
        },
        100_000_000,
    )
    assert st1.active_effect_id == "team_round"
    assert st1.current_color_hex == "#008CFF"

    # 3 & 4. Fim do Freezetime -> LIVE desativa imediatamente e apaga LED
    _, st2 = _feed(
        parser,
        mgr,
        engine,
        {
            "round": {"phase": "live"},
            "phase_countdowns": {"phase": "live"},
            "previously": {"round": {"phase": "freezetime"}},
        },
        200_000_000,
    )
    assert st2.active_effect_id == "idle"
    assert st2.current_rgb == (0, 0, 0)
    assert ctrl.get_status().last_rgba == (0, 0, 0, 255)

    # 4. Transição LIVE -> OVER permanece desativado (não acende cor CT/TR)
    _, st3 = _feed(
        parser,
        mgr,
        engine,
        {
            "round": {"phase": "over", "win_team": "CT"},
            "phase_countdowns": {"phase": "over"},
        },
        300_000_000,
    )
    assert st3.active_effect_id == "idle"
    assert st3.current_rgb == (0, 0, 0)

    # 5. Novo round e novo Freezetime -> volta a ativar normalmente
    _, st4 = _feed(
        parser,
        mgr,
        engine,
        {
            "map": {"round": 2},
            "round": {"phase": "freezetime"},
            "phase_countdowns": {"phase": "freezetime"},
            "previously": {"round": {"phase": "over", "win_team": "CT"}},
        },
        400_000_000,
    )
    st4 = _settle(engine, 410_000_000)
    assert st4.active_effect_id == "team_round"
    assert abs(st4.current_rgb[0] - 0) <= 2
    assert abs(st4.current_rgb[1] - 140) <= 2
    assert abs(st4.current_rgb[2] - 255) <= 2


def test_freezetime_06_team_swap_updates_color() -> None:
    cfg = _load_cfg()
    cfg["effects"]["team"]["enabled"] = True
    cfg["effects"]["team"]["freezetime_pulse"] = False
    cfg["effects"]["team"]["ct_color"] = "#008CFF"
    cfg["effects"]["team"]["t_color"] = "#FF9900"

    parser = GSIParser()
    mgr = EventManager()
    ctrl = RecordingRGBController()
    engine = RGBEngine(ctrl, cfg)

    _, st_ct = _feed(
        parser,
        mgr,
        engine,
        {
            "round": {"phase": "freezetime"},
            "phase_countdowns": {"phase": "freezetime"},
            "player": {"activity": "playing", "team": "CT", "state": {"health": 100}},
        },
        100_000_000,
    )
    assert st_ct.current_color_hex == "#008CFF"

    # Troca para TR no freezetime / metade da partida
    _, st_tr = _feed(
        parser,
        mgr,
        engine,
        {
            "player": {"team": "T"},
        },
        200_000_000,
    )
    st_tr = _settle(engine, 210_000_000)
    assert st_tr.active_effect_id == "team_round"
    assert abs(st_tr.current_rgb[0] - 255) <= 2
    assert abs(st_tr.current_rgb[1] - 153) <= 2
    assert abs(st_tr.current_rgb[2] - 0) <= 2


def test_freezetime_07_and_08_partial_payloads_never_leak_or_get_stuck() -> None:
    cfg = _load_cfg()
    cfg["effects"]["team"]["enabled"] = True
    cfg["effects"]["team"]["freezetime_pulse"] = False

    parser = GSIParser()
    mgr = EventManager()
    ctrl = RecordingRGBController()
    engine = RGBEngine(ctrl, cfg)

    # Começa em Freezetime
    _feed(
        parser,
        mgr,
        engine,
        {
            "map": {"phase": "live"},
            "round": {"phase": "freezetime"},
            "phase_countdowns": {"phase": "freezetime"},
            "player": {"activity": "playing", "team": "CT", "state": {"health": 100}},
        },
        100_000_000,
    )

    # 7. Payload parcial SEM bloco `round` nem `phase_countdowns` durante Freezetime -> preserva Freezetime
    snap_p1, st_p1 = _feed(
        parser,
        mgr,
        engine,
        {"player": {"state": {"armor": 100}}},
        200_000_000,
    )
    assert snap_p1.is_freezetime is True
    assert st_p1.active_effect_id == "team_round"

    # 8a. Fim do Freezetime sinalizado apenas por phase_countdowns (sem bloco round) -> deve apagar
    snap_end_pc, st_end_pc = _feed(
        parser,
        mgr,
        engine,
        {"phase_countdowns": {"phase": "live"}},
        300_000_000,
    )
    assert snap_end_pc.is_freezetime is False
    assert st_end_pc.active_effect_id == "idle"
    assert st_end_pc.current_rgb == (0, 0, 0)

    # 8b. Payload parcial posterior sem fase não reativa Freezetime
    snap_after, st_after = _feed(
        parser,
        mgr,
        engine,
        {"player": {"state": {"health": 95}}},
        400_000_000,
    )
    assert snap_after.is_freezetime is False
    assert st_after.active_effect_id == "idle"

    # 8c. Novo Freezetime encerrado via `previously.round` sem novo `round` explícito -> deve apagar
    _feed(
        parser,
        mgr,
        engine,
        {
            "round": {"phase": "freezetime"},
            "phase_countdowns": {"phase": "freezetime"},
        },
        500_000_000,
    )
    snap_prev, st_prev = _feed(
        parser,
        mgr,
        engine,
        {
            "previously": {
                "round": {"phase": "freezetime"},
                "phase_countdowns": {"phase": "freezetime"},
            }
        },
        600_000_000,
    )
    assert snap_prev.is_freezetime is False
    assert st_prev.active_effect_id == "idle"
    assert st_prev.current_rgb == (0, 0, 0)


def test_freezetime_09_disabled_config_and_warmup_excluded() -> None:
    cfg = _load_cfg()
    cfg["effects"]["team"]["enabled"] = False

    parser = GSIParser()
    mgr = EventManager()
    ctrl = RecordingRGBController()
    engine = RGBEngine(ctrl, cfg)

    # 9. Desativado na config durante Freezetime -> permanece apagado
    _, st_disabled = _feed(
        parser,
        mgr,
        engine,
        {
            "map": {"phase": "live"},
            "round": {"phase": "freezetime"},
            "phase_countdowns": {"phase": "freezetime"},
            "player": {"activity": "playing", "team": "CT", "state": {"health": 100}},
        },
        100_000_000,
    )
    assert st_disabled.active_effect_id == "idle"
    assert st_disabled.current_rgb == (0, 0, 0)

    # Warmup nunca acende Freezetime mesmo se enabled=True e round.phase="freezetime"
    cfg["effects"]["team"]["enabled"] = True
    engine.update_config(cfg)
    snap_warm, st_warm = _feed(
        parser,
        mgr,
        engine,
        {
            "map": {"phase": "warmup"},
            "round": {"phase": "freezetime"},
            "phase_countdowns": {"phase": "warmup"},
            "player": {"activity": "playing", "team": "CT", "state": {"health": 100}},
        },
        200_000_000,
    )
    assert snap_warm.is_freezetime is False
    assert st_warm.active_effect_id == "idle"


def test_freezetime_10_and_11_interaction_with_other_effects_and_flashbang() -> None:
    cfg = _load_cfg()
    cfg["effects"]["team"]["enabled"] = True
    cfg["effects"]["team"]["freezetime_pulse"] = False
    cfg["effects"]["health"]["enabled"] = True

    parser = GSIParser()
    mgr = EventManager()
    ctrl = RecordingRGBController()
    engine = RGBEngine(ctrl, cfg)

    # Freezetime CT -> team_round tem preferência sobre Vida normal
    _, st_freeze = _feed(
        parser,
        mgr,
        engine,
        {
            "map": {"phase": "live"},
            "round": {"phase": "freezetime"},
            "phase_countdowns": {"phase": "freezetime"},
            "player": {
                "activity": "playing",
                "team": "CT",
                "state": {"health": 100, "flashed": 0},
            },
        },
        100_000_000,
    )
    assert st_freeze.active_effect_id == "team_round"
    assert st_freeze.current_color_hex == "#008CFF"

    # 11. Flashbang durante o Freezetime -> flashbang assume prioridade imediatamente
    _, st_flash = _feed(
        parser,
        mgr,
        engine,
        {"player": {"state": {"flashed": 255}}},
        200_000_000,
    )
    assert st_flash.active_effect_id == "flashbang"
    assert st_flash.current_color_hex == "#FFFFFF"

    # Flashbang termina ainda durante Freezetime -> volta ao Freezetime CT (sem vazar fora)
    _, st_flash_end = _feed(
        parser,
        mgr,
        engine,
        {"player": {"state": {"flashed": 0}}},
        300_000_000,
    )
    assert st_flash_end.active_effect_id == "flashbang"  # cauda de fade ainda ativa
    st_back = engine.step(now_ns=900_000_000)
    assert st_back.active_effect_id == "team_round"

    # 10. Freezetime termina com outro efeito habilitado (Vida) -> assume Vida limpa (verde 100 HP)
    _, st_live_hp = _feed(
        parser,
        mgr,
        engine,
        {"round": {"phase": "live"}, "phase_countdowns": {"phase": "live"}},
        1_000_000_000,
    )
    assert st_live_hp.active_effect_id == "health"
    assert st_live_hp.current_rgb[1] > st_live_hp.current_rgb[2]  # Verde > Azul


def test_freezetime_12_disconnect_reconnect_and_pulse_option() -> None:
    cfg = _load_cfg()
    cfg["effects"]["team"]["enabled"] = True
    cfg["effects"]["team"]["freezetime_pulse"] = True

    parser = GSIParser()
    mgr = EventManager()
    ctrl = RecordingRGBController()
    engine = RGBEngine(ctrl, cfg)

    # Freezetime com pulso ativo
    _, st_pulse = _feed(
        parser,
        mgr,
        engine,
        {
            "map": {"phase": "live"},
            "round": {"phase": "freezetime"},
            "phase_countdowns": {"phase": "freezetime"},
            "player": {"activity": "playing", "team": "CT", "state": {"health": 100}},
        },
        100_000_000,
    )
    assert st_pulse.active_effect_id == "team_round"

    # 12a. Desconexão limpa estado e devolve controle ao iCUE
    disc = parser.mark_disconnected()
    engine.update_state(disc, mgr.process_snapshot(disc), now_ns=200_000_000)
    st_disc = engine.step(now_ns=205_000_000)
    assert st_disc.active_effect_id == "idle"
    assert ctrl.restore_count >= 1

    # 12b. Reconexão em round LIVE -> permanece idle (0, 0, 0)
    _, st_reconn_live = _feed(
        parser,
        mgr,
        engine,
        {
            "map": {"phase": "live"},
            "round": {"phase": "live"},
            "phase_countdowns": {"phase": "live"},
            "player": {"activity": "playing", "team": "CT", "state": {"health": 100}},
        },
        300_000_000,
    )
    assert st_reconn_live.active_effect_id == "idle"
    assert st_reconn_live.current_rgb == (0, 0, 0)

    # 12c. Reconexão / atualização entrando em Freezetime -> ativa pulso CT
    _, st_reconn_freeze = _feed(
        parser,
        mgr,
        engine,
        {
            "round": {"phase": "freezetime"},
            "phase_countdowns": {"phase": "freezetime"},
        },
        400_000_000,
    )
    assert st_reconn_freeze.active_effect_id == "team_round"

    # Confirma que HE continua completamente ausente do GSI e dos avaliadores
    cfg_txt = render_gsi_cfg(port=3000, token="test_token_123456")
    assert '"phase_countdowns"' in cfg_txt
    assert "allgrenades" not in cfg_txt
    assert "he_explosion" not in _EFFECT_EVALUATORS


# ---------------------------------------------------------------------------
# Parte 1: Generalização de hardware e identidade visual na UI
# ---------------------------------------------------------------------------


def test_hardware_selection_generalized_for_any_corsair_device() -> None:
    @dataclass
    class FakeDev:
        device_id: str
        model: str

    # Sem modelo fixo (padrão ""): seleciona qualquer dispositivo Corsair (teclado, headset, mouse)
    ctrl_auto = ICueController(target_model="")
    devices = [
        FakeDev("kbd-1", "K70 RGB PRO"),
        FakeDev("hs-1", "VIRTUOSO RGB WIRELESS XT"),
    ]
    cands = ctrl_auto._select_device_candidates(devices)  # type: ignore[arg-type]
    assert [d.device_id for d in cands] == ["kbd-1", "hs-1"]

    # Com filtro específico opcional: prioriza o modelo desejado mantendo fallback
    ctrl_pref = ICueController(target_model="VIRTUOSO")
    cands_pref = ctrl_pref._select_device_candidates(devices)  # type: ignore[arg-type]
    assert [d.device_id for d in cands_pref] == ["hs-1", "kbd-1"]

    # Padrões de configuração não citam Katar nem rodinha
    default_txt = DEFAULT_CFG_PATH.read_text(encoding="utf-8")
    assert "katar" not in default_txt.lower()
    assert "rodinha" not in default_txt.lower()
    assert _load_cfg()["hardware"]["target_model"] == ""


def test_ui_displays_generic_identity_dynamic_device_and_neutral_disconnected_state(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    cfg_mgr = ConfigManager(user_config_path=tmp_path / "cfg.json")
    controller = RecordingRGBController(device_model="K70 RGB PRO", device_id="mock-kbd")
    service = SyncService(config_manager=cfg_mgr, controller=controller, port_override=0)
    window = MainWindow(service=service)
    try:
        # Subtítulo e textos da UI nunca citam modelo específico ou "rodinha"
        win_texts = [lbl.text() for lbl in window.findChildren(type(window.lbl_footer_status))]
        joined = " | ".join(win_texts).lower()
        assert "katar" not in joined
        assert "rodinha" not in joined

        # Estado conectado: exibe nome dinâmico do SDK ("K70 RGB PRO")
        window._refresh_ui()
        app.processEvents()
        assert "K70 RGB PRO" in window.dashboard_page.card_device.detail_label.text()
        assert "NO DEVICE" not in window.dashboard_page.card_device.badge_label.text()

        # Estado nenhum dispositivo encontrado: exibe estado neutro localizado ("NO DEVICE" / "NENHUM DISPOSITIVO" / "SIN DISPOSITIVO")
        snap = service.get_ui_snapshot()
        no_dev_snap = ServiceSnapshot(
            integration_running=snap.integration_running,
            simulation_mode=snap.simulation_mode,
            server_stats=snap.server_stats,
            icue_status=ICueStatusSnapshot(
                icue_process_running=True,
                sdk_connected=True,
                session_state="CSS_Connected",
                device_found=False,
                device_connected=False,
                device_model="",
                device_id="",
                led_ids=(),
                last_rgba=None,
                last_error="",
                commands_sent=0,
                commands_skipped=0,
                last_sdk_call_ms=0.0,
            ),
            game_state=snap.game_state,
            render_state=snap.render_state,
            recent_events=snap.recent_events,
            last_payload=snap.last_payload,
            recent_logs=snap.recent_logs,
            last_service_error=snap.last_service_error,
        )
        window.dashboard_page.update_from_snapshot(no_dev_snap)
        window.diagnostics_page.update_from_snapshot(no_dev_snap)
        assert window.dashboard_page.card_device.badge_label.text() == "NO DEVICE"
        assert window.diagnostics_page.lbl_device.text() == "NO DEVICE"

        # Verifica rótulo claro de Freezetime-only na aba Efeitos RGB em en_US e pt_BR
        window._select_page(1)
        meta_en = get_group_meta("team_round")
        assert "Freezetime" in meta_en["title"]
        assert "exclusively" in meta_en["desc"].lower()

        service.set_language("pt_BR")
        app.processEvents()
        window.dashboard_page.update_from_snapshot(no_dev_snap)
        window.diagnostics_page.update_from_snapshot(no_dev_snap)
        assert window.dashboard_page.card_device.badge_label.text() == "NENHUM DISPOSITIVO"
        assert window.diagnostics_page.lbl_device.text() == "NENHUM DISPOSITIVO"
        meta_pt = get_group_meta("team_round")
        assert "Freezetime" in meta_pt["title"]
        assert "exclusivamente" in meta_pt["desc"].lower()

        service.set_language("es_ES")
        app.processEvents()
        window.dashboard_page.update_from_snapshot(no_dev_snap)
        window.diagnostics_page.update_from_snapshot(no_dev_snap)
        assert window.dashboard_page.card_device.badge_label.text() == "SIN DISPOSITIVO"
        assert window.diagnostics_page.lbl_device.text() == "SIN DISPOSITIVO"
    finally:
        set_language("en_US")
        window.shutdown_service()
