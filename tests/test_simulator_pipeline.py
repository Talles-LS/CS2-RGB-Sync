"""End-to-end tests for the CS2 RGB Sync simulator pipeline, animations, priorities, and isolation."""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from app.config_manager import ConfigManager
from app.icue_controller import RecordingRGBController
from app.sync_service import SyncService


def _post_gsi(port: int, payload: dict) -> int:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        return resp.status


def test_simulator_all_effects_and_continuous_render_loop(tmp_path: Path) -> None:
    cfg_mgr = ConfigManager(user_config_path=tmp_path / "sim_effects.json")
    controller = RecordingRGBController()
    service = SyncService(config_manager=cfg_mgr, controller=controller, port_override=0)

    try:
        # Simulator runs its own real RGBEngine loop even when real GSI integration is off
        service.set_simulation_mode(True)
        snap0 = service.get_ui_snapshot()
        assert snap0.simulation_mode is True
        assert snap0.render_state.running is True
        frames_start = snap0.render_state.frames_rendered

        # 1. Gunfire works on the VERY FIRST click, from knife, and from 0 ammo, then expires automatically
        cfg = cfg_mgr.get_all()
        cfg["effects"]["shot"]["duration_ms"] = 60
        cfg["effects"]["shot"]["debounce_ms"] = 0
        service.apply_config(cfg)

        assert service.trigger_simulation("shot") is True
        snap_shot = service.get_ui_snapshot()
        assert snap_shot.render_state.active_effect_id == "shot"
        assert snap_shot.render_state.current_color_hex == "#FF9900"
        assert snap_shot.game_state.active_weapon is not None
        assert snap_shot.game_state.active_weapon.ammo_clip == 29

        # Wait past duration_ms (60 ms) -> real running RGBEngine must auto-expire back to idle (#000000)
        time.sleep(0.16)
        snap_after_shot = service.get_ui_snapshot()
        assert snap_after_shot.render_state.active_effect_id == "idle"
        assert snap_after_shot.render_state.current_rgb == (0, 0, 0)
        assert snap_after_shot.render_state.frames_rendered > frames_start

        # Switch to knife and fire -> must prepare rifle baseline and trigger shot immediately!
        service.trigger_simulation("weapon", category="knife")
        assert service.trigger_simulation("shot") is True
        assert service.get_ui_snapshot().render_state.active_effect_id == "shot"
        time.sleep(0.12)

        # 2. Flashbang applies peak then decays smoothly via real render loop when cleared
        service.trigger_simulation("flashbang", intensity=255)
        assert service.get_ui_snapshot().render_state.active_effect_id == "flashbang"
        assert service.get_ui_snapshot().render_state.current_color_hex == "#FFFFFF"
        service.trigger_simulation("flashbang", intensity=0)
        time.sleep(0.35)
        assert service.get_ui_snapshot().render_state.active_effect_id == "idle"

        # 3. Fire animates continuously (not frozen on frame 1)
        service.trigger_simulation("fire", intensity=180)
        colors_fire = set()
        for _ in range(8):
            colors_fire.add(service.get_ui_snapshot().render_state.current_rgb)
            time.sleep(0.035)
        assert service.get_ui_snapshot().render_state.active_effect_id == "fire"
        assert len(colors_fire) >= 2
        service.trigger_simulation("fire", intensity=0)

        # 4. C4 planted pulses continuously across ticks and stops on defuse
        service.trigger_simulation("c4_planted")
        colors_c4 = set()
        for _ in range(18):
            st = service.get_ui_snapshot().render_state
            assert st.active_effect_id == "c4"
            colors_c4.add(st.current_rgb)
            time.sleep(0.03)
        assert len(colors_c4) >= 2
        service.trigger_simulation("c4_defused")
        assert service.get_ui_snapshot().render_state.active_effect_id == "idle"

        # 5. Health & Critical Health when enabled
        cfg = cfg_mgr.get_all()
        cfg["effects"]["health"]["enabled"] = True
        cfg["effects"]["team"]["enabled"] = True
        cfg["effects"]["team"]["freezetime_pulse"] = False
        cfg["effects"]["team"]["ct_color"] = "#008CFF"
        cfg["effects"]["team"]["t_color"] = "#FF9900"
        cfg["effects"]["weapons"]["enabled"] = True
        service.apply_config(cfg)

        service.trigger_simulation("health", health=15)
        assert service.get_ui_snapshot().render_state.active_effect_id == "health_critical"
        service.trigger_simulation("health", health=100)
        assert service.get_ui_snapshot().render_state.active_effect_id == "health"

        # 6. Freezetime CT/T overrides normal health only in freezetime, off in live/over
        service.trigger_simulation("team", team="CT")
        service.trigger_simulation("freezetime")
        time.sleep(0.22)
        st_ct = service.get_ui_snapshot().render_state
        assert st_ct.active_effect_id == "team_round"
        assert abs(st_ct.current_rgb[0] - 0) <= 2
        assert abs(st_ct.current_rgb[1] - 140) <= 2
        assert abs(st_ct.current_rgb[2] - 255) <= 2

        service.trigger_simulation("team", team="T")
        time.sleep(0.22)
        st_tr = service.get_ui_snapshot().render_state
        assert st_tr.active_effect_id == "team_round"
        assert abs(st_tr.current_rgb[0] - 255) <= 2
        assert abs(st_tr.current_rgb[1] - 153) <= 2
        assert abs(st_tr.current_rgb[2] - 0) <= 2

        service.trigger_simulation("live")
        assert service.get_ui_snapshot().render_state.active_effect_id == "health"
        service.trigger_simulation("over")
        assert service.get_ui_snapshot().render_state.active_effect_id == "health"

        # 7. Weapon category lighting when health & freezetime inactive
        cfg = cfg_mgr.get_all()
        cfg["effects"]["health"]["enabled"] = False
        service.apply_config(cfg)
        service.trigger_simulation("weapon", category="sniper")
        time.sleep(0.22)
        st_wp = service.get_ui_snapshot().render_state
        assert st_wp.active_effect_id == "weapon"
        assert abs(st_wp.current_rgb[0] - 255) <= 2
        assert abs(st_wp.current_rgb[1] - 51) <= 2
        assert abs(st_wp.current_rgb[2] - 102) <= 2
    finally:
        service.shutdown()


def test_simulator_simultaneous_priorities_lifecycle_pause_reset_and_isolation(
    tmp_path: Path,
) -> None:
    cfg_mgr = ConfigManager(user_config_path=tmp_path / "sim_prio.json")
    controller = RecordingRGBController()
    service = SyncService(config_manager=cfg_mgr, controller=controller, port_override=0)

    try:
        cfg = cfg_mgr.get_all()
        cfg["effects"]["team"]["enabled"] = True
        cfg["effects"]["team"]["freezetime_pulse"] = False
        cfg["effects"]["health"]["enabled"] = True
        cfg["effects"]["shot"]["duration_ms"] = 60
        cfg["effects"]["shot"]["debounce_ms"] = 0
        service.apply_config(cfg)

        # Start real GSI integration first and send a real match state (CT, 80 HP, de_dust2)
        ok, _ = service.start_integration()
        assert ok is True
        port = service.get_ui_snapshot().server_stats.port
        token = cfg_mgr.get("server.token")
        assert (
            _post_gsi(
                port,
                {
                    "provider": {"name": "Counter-Strike 2", "appid": 730, "steamid": "1"},
                    "map": {"name": "de_dust2", "phase": "live"},
                    "round": {"phase": "live"},
                    "player": {
                        "steamid": "1",
                        "activity": "playing",
                        "team": "CT",
                        "state": {"health": 80, "flashed": 0},
                    },
                    "auth": {"token": token},
                },
            )
            == 200
        )
        time.sleep(0.15)
        assert service.get_ui_snapshot().game_state.map_name == "de_dust2"
        assert service.get_ui_snapshot().render_state.active_effect_id == "health"

        # Enable Simulation Mode -> isolates from real GSI; simultaneous Flashbang > Freezetime
        service.set_simulation_mode(True)
        service.trigger_simulation("team", team="CT")
        service.trigger_simulation("freezetime")
        assert service.get_ui_snapshot().render_state.active_effect_id == "team_round"

        service.trigger_simulation("flashbang", intensity=255)
        assert service.get_ui_snapshot().render_state.active_effect_id == "flashbang"
        service.trigger_simulation("flashbang", intensity=0)
        time.sleep(0.32)
        assert service.get_ui_snapshot().render_state.active_effect_id == "team_round"

        # Real GSI packet sent while simulation is active must NOT hijack simulation state
        assert (
            _post_gsi(
                port,
                {
                    "provider": {"name": "Counter-Strike 2", "appid": 730, "steamid": "1"},
                    "map": {"name": "de_nuke", "phase": "live"},
                    "round": {"phase": "live", "bomb": "planted"},
                    "player": {
                        "steamid": "1",
                        "activity": "playing",
                        "team": "T",
                        "state": {"health": 42, "flashed": 255},
                    },
                    "auth": {"token": token},
                },
            )
            == 200
        )
        time.sleep(0.10)
        assert service.get_ui_snapshot().game_state.map_name == "de_mirage"
        assert service.get_ui_snapshot().render_state.active_effect_id == "team_round"

        # Pause simulation -> freezes frame count and blocks triggers while paused
        assert service.set_simulation_paused(True) is True
        paused_snap = service.get_ui_snapshot()
        assert paused_snap.simulation_paused is True
        assert paused_snap.render_state.paused is True
        assert service.trigger_simulation("c4_planted") is False
        frames_at_pause = paused_snap.render_state.frames_rendered
        time.sleep(0.08)
        assert service.get_ui_snapshot().render_state.frames_rendered == frames_at_pause

        # Resume -> ticks advance again
        assert service.set_simulation_paused(False) is True
        time.sleep(0.08)
        assert service.get_ui_snapshot().render_state.frames_rendered > frames_at_pause

        # Simultaneous Fire > C4 -> Fire wins, then returns to C4 when Fire stops
        service.trigger_simulation("c4_planted")
        service.trigger_simulation("fire", intensity=200)
        assert service.get_ui_snapshot().render_state.active_effect_id == "fire"
        service.trigger_simulation("shot")
        assert service.get_ui_snapshot().render_state.active_effect_id == "shot"
        time.sleep(0.12)
        assert service.get_ui_snapshot().render_state.active_effect_id == "fire"
        service.trigger_simulation("fire", intensity=0)
        assert service.get_ui_snapshot().render_state.active_effect_id == "c4"

        # Reset -> wipes all stale flash/fire/c4/freezetime to clean CT, live, 100 HP
        service.reset_simulation()
        reset_snap = service.get_ui_snapshot()
        assert reset_snap.game_state.team == "CT"
        assert reset_snap.game_state.round_phase == "live"
        assert reset_snap.game_state.health == 100
        assert reset_snap.game_state.bomb_state is None
        assert reset_snap.render_state.active_effect_id == "health"

        # Exiting simulation mode restores real GSI state (de_nuke) cleanly without simulated leaks
        service.set_simulation_mode(False)
        post_sim = service.get_ui_snapshot()
        assert post_sim.simulation_mode is False
        assert post_sim.game_state.map_name == "de_nuke"
        assert post_sim.game_state.team == "T"
        assert post_sim.game_state.health == 42

        # Stopping real integration and running simulation standalone stops engine & restores LED on exit
        service.stop_integration()
        restore_before = controller.restore_count
        service.set_simulation_mode(True)
        service.trigger_simulation("flashbang", intensity=255)
        service.set_simulation_mode(False)
        assert service.get_ui_snapshot().render_state.running is False
        assert controller.restore_count > restore_before
    finally:
        service.shutdown()
