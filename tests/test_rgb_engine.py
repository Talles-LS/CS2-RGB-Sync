"""Testes automatizados para RGBEngine (idle apagado, flashbang real/gradual, fogo > C4, prioridades e concorrência)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from app.event_manager import EventManager
from app.gsi_parser import GSIParser
from app.icue_controller import RecordingRGBController
from app.rgb_engine import RGBEngine
from app.simulator import GSISimulator

DEFAULT_CFG_PATH = Path(__file__).resolve().parent.parent / "config" / "default_config.json"


def _load_cfg() -> dict:
    return json.loads(DEFAULT_CFG_PATH.read_text(encoding="utf-8"))


def test_idle_led_remains_off_with_default_config() -> None:
    cfg = _load_cfg()
    controller = RecordingRGBController()
    parser = GSIParser()
    event_mgr = EventManager()
    engine = RGBEngine(controller=controller, config=cfg)
    sim = GSISimulator()

    # Jogador vivo em partida sem eventos ativos -> LED rigorosamente apagado (0, 0, 0)
    sim.set_team("CT")
    sim.set_health(100)
    snap = parser.parse(sim.build_payload(), received_at_ns=1_000_000_000, received_at_wall=1.0)
    engine.update_state(snap, event_mgr.process_snapshot(snap), now_ns=1_000_000_000)
    state = engine.step(now_ns=1_010_000_000)

    assert state.active_effect_id == "idle"
    assert state.current_rgb == (0, 0, 0)
    assert state.current_color_hex == "#000000"
    assert controller.history[-1] == (0, 0, 0, 255)


def test_flashbang_peak_retention_smooth_fade_and_return_to_off() -> None:
    cfg = _load_cfg()
    controller = RecordingRGBController()
    parser = GSIParser()
    event_mgr = EventManager()
    engine = RGBEngine(controller=controller, config=cfg)
    sim = GSISimulator()

    # 1. Pico de flashbang 255 seguido imediatamente por 0 antes do próximo tick
    snap_peak = parser.parse(
        sim.set_flashed(255), received_at_ns=1_000_000_000, received_at_wall=1.0
    )
    engine.update_state(snap_peak, event_mgr.process_snapshot(snap_peak), now_ns=1_000_000_000)

    snap_drop = parser.parse(
        sim.set_flashed(0), received_at_ns=1_005_000_000, received_at_wall=1.005
    )
    engine.update_state(snap_drop, event_mgr.process_snapshot(snap_drop), now_ns=1_005_000_000)

    # Primeiro step deve ainda capturar o pico branco!
    s_peak = engine.step(now_ns=1_010_000_000)
    assert s_peak.active_effect_id == "flashbang"
    assert s_peak.current_color_hex == "#FFFFFF"

    # Steps seguintes decaem suavemente ao longo de fade_tail_ms (220 ms)
    s_mid = engine.step(now_ns=1_120_000_000)
    assert s_mid.active_effect_id == "flashbang"
    assert 0 < s_mid.current_rgb[0] < 255

    # Após passar o fade_tail_ms -> retorna ao LED apagado
    s_done = engine.step(now_ns=1_300_000_000)
    assert s_done.active_effect_id == "idle"
    assert s_done.current_rgb == (0, 0, 0)
    assert controller.history[-1] == (0, 0, 0, 255)


def test_flashbang_real_binary_replaces_color_immediately_and_resumes() -> None:
    cfg = _load_cfg()
    controller = RecordingRGBController()
    parser = GSIParser()
    event_mgr = EventManager()
    engine = RGBEngine(controller=controller, config=cfg)

    # C4 plantada e Fogo ativos com cor quente
    p_fire_c4 = {
        "provider": {"name": "Counter-Strike 2", "appid": 730, "steamid": "1"},
        "round": {"phase": "live", "bomb": "planted"},
        "player": {
            "steamid": "1",
            "activity": "playing",
            "team": "CT",
            "state": {"health": 80, "flashed": 0, "burning": 180},
        },
    }
    snap0 = parser.parse(p_fire_c4, received_at_ns=1_000_000_000, received_at_wall=1.0)
    engine.update_state(snap0, event_mgr.process_snapshot(snap0), now_ns=1_000_000_000)
    s0 = engine.step(now_ns=1_025_000_000)
    assert s0.active_effect_id == "fire"

    # Flashbang real observada no CS2 (0 -> 1) deve substituir imediatamente por branco puro #FFFFFF
    p_flash_1 = {
        "provider": {"name": "Counter-Strike 2", "appid": 730, "steamid": "1"},
        "round": {"phase": "live", "bomb": "planted"},
        "player": {
            "steamid": "1",
            "activity": "playing",
            "team": "CT",
            "state": {"health": 80, "flashed": 1, "burning": 180},
        },
    }
    snap1 = parser.parse(p_flash_1, received_at_ns=1_050_000_000, received_at_wall=1.05)
    engine.update_state(snap1, event_mgr.process_snapshot(snap1), now_ns=1_050_000_000)
    s1 = engine.step(now_ns=1_055_000_000)
    assert s1.active_effect_id == "flashbang"
    assert s1.current_rgb == (255, 255, 255)
    assert s1.current_color_hex == "#FFFFFF"

    # Espectador flashed NÃO aciona flashbang local
    p_spec = {
        "provider": {"name": "Counter-Strike 2", "appid": 730, "steamid": "1"},
        "player": {
            "steamid": "999",
            "activity": "playing",
            "state": {"health": 80, "flashed": 255},
        },
    }
    # Mantém branco pleno #FFFFFF enquanto cego no loop antes de zerar
    s_hold = engine.step(now_ns=1_480_000_000)
    assert s_hold.active_effect_id == "flashbang"
    assert s_hold.current_color_hex == "#FFFFFF"

    # Sem misturar com retorno da flashbang do jogador local após zerar:
    p_flash_0 = {
        "provider": {"name": "Counter-Strike 2", "appid": 730, "steamid": "1"},
        "round": {"phase": "live", "bomb": "planted"},
        "player": {
            "steamid": "1",
            "activity": "playing",
            "team": "CT",
            "state": {"health": 80, "flashed": 0, "burning": 180},
        },
    }
    snap2 = parser.parse(p_flash_0, received_at_ns=1_500_000_000, received_at_wall=1.5)
    engine.update_state(snap2, event_mgr.process_snapshot(snap2), now_ns=1_500_000_000)

    # Durante binary_fade_ms (650ms) decai suavemente mantendo branco neutro (r == g == b)
    s_decay = engine.step(now_ns=1_750_000_000)
    assert s_decay.active_effect_id == "flashbang"
    assert s_decay.current_rgb[0] == s_decay.current_rgb[1] == s_decay.current_rgb[2]
    assert 0 < s_decay.current_rgb[0] < 255

    # Ao terminar a cegueira -> retoma Fogo (acima da C4); quando Fogo zera -> C4 retoma
    s_resume_fire = engine.step(now_ns=2_300_000_000)
    assert s_resume_fire.active_effect_id == "fire"

    p_no_fire = {
        "provider": {"name": "Counter-Strike 2", "appid": 730, "steamid": "1"},
        "round": {"phase": "live", "bomb": "planted"},
        "player": {
            "steamid": "1",
            "activity": "playing",
            "team": "CT",
            "state": {"health": 80, "flashed": 0, "burning": 0},
        },
    }
    snap_nf = parser.parse(p_no_fire, received_at_ns=2_320_000_000, received_at_wall=2.32)
    engine.update_state(snap_nf, event_mgr.process_snapshot(snap_nf), now_ns=2_320_000_000)
    s_resume_c4 = engine.step(now_ns=2_350_000_000)
    assert s_resume_c4.active_effect_id == "c4"

    # Garante que espectador isolado não gera branco
    p_spec["player"]["state"]["flashed"] = 255
    parser_spec = GSIParser()
    eng_spec = RGBEngine(controller=RecordingRGBController(), config=cfg)
    snap_spec = parser_spec.parse(p_spec, received_at_ns=100_000_000, received_at_wall=0.1)
    eng_spec.update_state(snap_spec, now_ns=100_000_000)
    assert eng_spec.step(now_ns=110_000_000).active_effect_id == "idle"


def test_priority_hierarchy_fire_over_c4_and_manual_health_team() -> None:
    cfg = _load_cfg()
    # Ativa manualmente vida e equipe para testar toda a cadeia de 8 prioridades
    cfg["effects"]["health"]["enabled"] = True
    cfg["effects"]["team"]["enabled"] = True
    cfg["effects"]["weapons"]["enabled"] = True

    controller = RecordingRGBController()
    parser = GSIParser()
    event_mgr = EventManager(shot_debounce_ms=0.0)
    engine = RGBEngine(controller=controller, config=cfg)
    sim = GSISimulator()

    # 1. 15 HP + C4 + Fogo + Flashbang -> Flashbang prevalece e substitui por #FFFFFF
    sim.set_team("CT")
    sim.set_health(15)
    sim.set_bomb("planted")
    sim.set_burning(180)
    snap1 = parser.parse(
        sim.set_flashed(255), received_at_ns=1_000_000_000, received_at_wall=1.0
    )
    engine.update_state(snap1, event_mgr.process_snapshot(snap1), now_ns=1_000_000_000)

    s1 = engine.step(now_ns=1_005_000_000)
    assert s1.active_effect_id == "flashbang"
    assert s1.current_color_hex == "#FFFFFF"

    # 2. Flashbang zera e decai (fade_tail_ms=220) -> retorna para Fogo (que está acima da C4!)
    snap2 = parser.parse(
        sim.set_flashed(0), received_at_ns=1_010_000_000, received_at_wall=1.01
    )
    engine.update_state(snap2, event_mgr.process_snapshot(snap2), now_ns=1_010_000_000)
    s2_fire = engine.step(now_ns=1_280_000_000)
    assert s2_fire.active_effect_id == "fire"

    # 3. Disparo durante Fogo/C4 -> Disparo sobrepõe por 50 ms e volta para Fogo
    snap_shot = parser.parse(
        sim.trigger_shot(), received_at_ns=1_350_000_000, received_at_wall=1.35
    )
    engine.update_state(
        snap_shot, event_mgr.process_snapshot(snap_shot), now_ns=1_350_000_000
    )
    s3 = engine.step(now_ns=1_360_000_000)
    assert s3.active_effect_id == "shot"
    assert s3.current_color_hex == "#FF9900"

    s3_back = engine.step(now_ns=1_410_000_000)
    assert s3_back.active_effect_id == "fire"

    # 4. Fogo cessa -> C4 plantada continua normalmente
    snap_no_fire = parser.parse(
        sim.set_burning(0), received_at_ns=1_450_000_000, received_at_wall=1.45
    )
    engine.update_state(
        snap_no_fire, event_mgr.process_snapshot(snap_no_fire), now_ns=1_450_000_000
    )
    s4 = engine.step(now_ns=1_470_000_000)
    assert s4.active_effect_id == "c4"

    # 5. C4 desarmada -> Vida Crítica (15 HP)
    sim.set_bomb("defused")
    snap_def = parser.parse(sim.build_payload(), received_at_ns=1_500_000_000, received_at_wall=1.5)
    engine.update_state(snap_def, event_mgr.process_snapshot(snap_def), now_ns=1_500_000_000)
    s6 = engine.step(now_ns=1_505_000_000)
    assert s6.active_effect_id == "health_critical"

    # 6. 100 HP -> Vida Normal
    sim.set_health(100)
    snap_hp = parser.parse(sim.build_payload(), received_at_ns=1_600_000_000, received_at_wall=1.6)
    engine.update_state(snap_hp, event_mgr.process_snapshot(snap_hp), now_ns=1_600_000_000)
    s7 = engine.step(now_ns=1_605_000_000)
    assert s7.active_effect_id == "health"

    # 7. Em round ativo (live), Equipe não acende -> vai direto para Arma; em Freezetime acende Equipe CT; ao sair desliga -> LED apagado
    cfg["effects"]["health"]["enabled"] = False
    engine.update_config(cfg)
    assert engine.step(now_ns=1_620_000_000).active_effect_id == "weapon"

    snap_freeze = parser.parse(
        sim.set_round_phase("freezetime"),
        received_at_ns=1_630_000_000,
        received_at_wall=1.63,
    )
    engine.update_state(snap_freeze, event_mgr.process_snapshot(snap_freeze), now_ns=1_630_000_000)
    assert engine.step(now_ns=1_635_000_000).active_effect_id == "team_round"

    snap_live_back = parser.parse(
        sim.set_round_phase("live"),
        received_at_ns=1_640_000_000,
        received_at_wall=1.64,
    )
    engine.update_state(
        snap_live_back, event_mgr.process_snapshot(snap_live_back), now_ns=1_640_000_000
    )
    assert engine.step(now_ns=1_645_000_000).active_effect_id == "weapon"

    cfg["effects"]["team"]["enabled"] = False
    cfg["effects"]["weapons"]["enabled"] = False
    engine.update_config(cfg)
    s_off = engine.step(now_ns=1_660_000_000)
    assert s_off.active_effect_id == "idle"
    assert s_off.current_rgb == (0, 0, 0)


def test_engine_deduplicates_identical_colors_and_tracks_latency() -> None:
    cfg = _load_cfg()
    cfg["effects"]["team"]["enabled"] = True
    cfg["effects"]["team"]["freezetime_pulse"] = False
    controller = RecordingRGBController()
    parser = GSIParser()
    event_mgr = EventManager()
    engine = RGBEngine(controller=controller, config=cfg)

    sim = GSISimulator()
    sim.set_team("CT")
    sim.set_round_phase("freezetime")
    snap = parser.parse(
        sim.build_payload(), received_at_ns=time.perf_counter_ns(), received_at_wall=time.time()
    )
    engine.update_state(snap, event_mgr.process_snapshot(snap))

    base = time.perf_counter_ns()
    for i in range(5):
        state = engine.step(now_ns=base + i * 25_000_000)

    hw_status = controller.get_status()
    assert hw_status.commands_sent == 1
    assert hw_status.commands_skipped == 4
    assert state.latency.samples_count == 1
    assert state.latency.last_gsi_received_ns <= state.latency.last_event_detected_ns
    assert state.latency.last_event_detected_ns <= state.latency.last_rgb_sent_ns


def test_engine_thread_concurrency_and_safe_shutdown() -> None:
    cfg = _load_cfg()
    cfg["engine"]["tick_ms"] = 15
    controller = RecordingRGBController()
    engine = RGBEngine(controller=controller, config=cfg)
    engine.start()

    errors: list[Exception] = []

    def producer(worker_id: int) -> None:
        local_parser = GSIParser()
        local_mgr = EventManager(shot_debounce_ms=0.0)
        local_sim = GSISimulator()
        local_sim.set_team("T" if worker_id % 2 == 0 else "CT")
        try:
            for step_i in range(25):
                if step_i % 5 == 0:
                    payload = local_sim.trigger_shot()
                else:
                    payload = local_sim.set_health(max(10, 100 - step_i * 3))
                snap = local_parser.parse(
                    payload,
                    received_at_ns=time.perf_counter_ns(),
                    received_at_wall=time.time(),
                )
                engine.update_state(snap, local_mgr.process_snapshot(snap), simulation_mode=True)
                time.sleep(0.01)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=producer, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    time.sleep(0.08)
    state = engine.get_render_state()
    engine.stop(release_controller=True)

    assert not errors
    assert state.frames_rendered >= 10
    assert state.simulation_mode is True
    assert controller.disconnect_count == 1
    assert controller.is_connected() is False


def test_cs2_disconnect_and_icue_disconnect_recovery() -> None:
    cfg = _load_cfg()
    controller = RecordingRGBController()
    parser = GSIParser()
    engine = RGBEngine(controller=controller, config=cfg)
    sim = GSISimulator()

    snap = parser.parse(sim.set_flashed(255), received_at_ns=100_000_000, received_at_wall=1.0)
    engine.update_state(snap, now_ns=100_000_000)
    engine.step(now_ns=110_000_000)
    assert controller.get_status().commands_sent == 1

    # Desconexão do iCUE / dispositivo: motor continua estável e recupera depois
    controller.simulate_disconnect()
    engine.step(now_ns=135_000_000)
    controller.simulate_reconnect()
    engine.step(now_ns=160_000_000)
    assert controller.get_status().commands_sent == 2

    # Desconexão do CS2: motor libera controle padrão (sem deixar LED preso)
    disc_snap = parser.mark_disconnected()
    engine.update_state(disc_snap, now_ns=180_000_000)
    s_idle = engine.step(now_ns=185_000_000)
    assert s_idle.active_effect_id == "idle"
    assert controller.restore_count >= 1
