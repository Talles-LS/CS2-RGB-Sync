"""Testes automatizados para EventManager (eventos GSI, disparos, C4 e desconexão)."""

from __future__ import annotations

from app.event_manager import EventManager, EventType
from app.gsi_parser import GSIParser


def _make_payload(
    *,
    health: int = 100,
    flashed: int = 0,
    burning: int | None = None,
    team: str = "T",
    round_phase: str = "live",
    bomb: str | None = None,
    weapon_slot: str = "weapon_1",
    weapon_name: str = "weapon_ak47",
    weapon_type: str = "Rifle",
    weapon_state: str = "active",
    ammo_clip: int | None = 30,
    ammo_clip_max: int | None = 30,
    activity: str = "playing",
    provider_steamid: str = "76561198000000001",
    player_steamid: str = "76561198000000001",
) -> dict:
    state: dict = {"health": health, "armor": 100, "flashed": flashed}
    if burning is not None:
        state["burning"] = burning

    weapon: dict = {"name": weapon_name, "type": weapon_type, "state": weapon_state}
    if ammo_clip is not None:
        weapon["ammo_clip"] = ammo_clip
    if ammo_clip_max is not None:
        weapon["ammo_clip_max"] = ammo_clip_max

    round_block: dict = {"phase": round_phase}
    if bomb is not None:
        round_block["bomb"] = bomb

    return {
        "provider": {
            "name": "Counter-Strike 2",
            "appid": 730,
            "steamid": provider_steamid,
        },
        "round": round_block,
        "player": {
            "steamid": player_steamid,
            "activity": activity,
            "team": team,
            "state": state,
            "weapons": {weapon_slot: weapon},
        },
    }


def test_shot_detection_single_last_bullet_grouped_and_debounce() -> None:
    parser = GSIParser()
    mgr = EventManager(shot_debounce_ms=40.0)

    # Baseline inicial (não dispara evento de tiro)
    ev0 = mgr.process_snapshot(
        parser.parse(_make_payload(ammo_clip=30), received_at_ns=100_000_000, received_at_wall=1.0)
    )
    assert not any(e.event_type == EventType.SHOT_FIRED for e in ev0)

    # 30 -> 29 após 100 ms (disparo válido)
    ev1 = mgr.process_snapshot(
        parser.parse(_make_payload(ammo_clip=29), received_at_ns=200_000_000, received_at_wall=1.1)
    )
    shots1 = [e for e in ev1 if e.event_type == EventType.SHOT_FIRED]
    assert len(shots1) == 1
    assert shots1[0].data["bullets_delta"] == 1
    assert shots1[0].data["grouped_shots"] is False

    # 29 -> 28 após apenas 10 ms (bloqueado pelo debounce de 40 ms)
    ev2 = mgr.process_snapshot(
        parser.parse(_make_payload(ammo_clip=28), received_at_ns=210_000_000, received_at_wall=1.11)
    )
    assert not any(e.event_type == EventType.SHOT_FIRED for e in ev2)

    # 28 -> 25 após 100 ms (rajada agrupada pelo GSI)
    ev3 = mgr.process_snapshot(
        parser.parse(_make_payload(ammo_clip=25), received_at_ns=310_000_000, received_at_wall=1.21)
    )
    shots3 = [e for e in ev3 if e.event_type == EventType.SHOT_FIRED]
    assert len(shots3) == 1
    assert shots3[0].data["bullets_delta"] == 3
    assert shots3[0].data["grouped_shots"] is True

    # 1 -> 0 (última bala do carregador deve ser detectada)
    mgr.process_snapshot(
        parser.parse(_make_payload(ammo_clip=1), received_at_ns=400_000_000, received_at_wall=1.3)
    )
    ev4 = mgr.process_snapshot(
        parser.parse(_make_payload(ammo_clip=0), received_at_ns=500_000_000, received_at_wall=1.4)
    )
    shots4 = [e for e in ev4 if e.event_type == EventType.SHOT_FIRED]
    assert len(shots4) == 1
    assert shots4[0].data["curr_ammo"] == 0


def test_shot_detection_blocks_false_positives() -> None:
    parser = GSIParser()
    mgr = EventManager(shot_debounce_ms=0.0)

    # 1. Recarga (state='reloading' e aumento de munição)
    mgr.process_snapshot(parser.parse(_make_payload(ammo_clip=10), received_at_ns=1_000_000))
    ev_reload_start = mgr.process_snapshot(
        parser.parse(
            _make_payload(ammo_clip=10, weapon_state="reloading"),
            received_at_ns=2_000_000,
        )
    )
    assert any(e.event_type == EventType.RELOAD_STARTED for e in ev_reload_start)
    assert not any(e.event_type == EventType.SHOT_FIRED for e in ev_reload_start)

    ev_reload_end = mgr.process_snapshot(
        parser.parse(_make_payload(ammo_clip=30, weapon_state="active"), received_at_ns=3_000_000)
    )
    assert any(e.event_type == EventType.RELOAD_FINISHED for e in ev_reload_end)
    assert not any(e.event_type == EventType.SHOT_FIRED for e in ev_reload_end)

    # 2. Troca de arma (AK-47 30 -> Deagle 7)
    ev_swap = mgr.process_snapshot(
        parser.parse(
            _make_payload(
                weapon_slot="weapon_2",
                weapon_name="weapon_deagle",
                weapon_type="Pistol",
                ammo_clip=7,
                ammo_clip_max=7,
            ),
            received_at_ns=4_000_000,
        )
    )
    assert any(e.event_type == EventType.WEAPON_CHANGED for e in ev_swap)
    assert not any(e.event_type == EventType.SHOT_FIRED for e in ev_swap)

    # 3. Troca para faca/granada
    ev_knife = mgr.process_snapshot(
        parser.parse(
            _make_payload(
                weapon_slot="weapon_0",
                weapon_name="weapon_knife",
                weapon_type="Knife",
                ammo_clip=None,
                ammo_clip_max=None,
            ),
            received_at_ns=5_000_000,
        )
    )
    assert not any(e.event_type == EventType.SHOT_FIRED for e in ev_knife)

    # 4. Espectando aliado (provider_steamid != player_steamid)
    mgr.process_snapshot(
        parser.parse(
            _make_payload(ammo_clip=30, player_steamid="76561198000000099"),
            received_at_ns=6_000_000,
        )
    )
    ev_spec = mgr.process_snapshot(
        parser.parse(
            _make_payload(ammo_clip=29, player_steamid="76561198000000099"),
            received_at_ns=7_000_000,
        )
    )
    assert not any(e.event_type == EventType.SHOT_FIRED for e in ev_spec)

    # 5. Freezetime
    mgr.process_snapshot(
        parser.parse(_make_payload(round_phase="freezetime", ammo_clip=30), received_at_ns=8_000_000)
    )
    ev_freeze = mgr.process_snapshot(
        parser.parse(_make_payload(round_phase="freezetime", ammo_clip=29), received_at_ns=9_000_000)
    )
    assert not any(e.event_type == EventType.SHOT_FIRED for e in ev_freeze)

    # 6. Jogador morto (health=0)
    mgr.process_snapshot(
        parser.parse(_make_payload(health=10, ammo_clip=20), received_at_ns=10_000_000)
    )
    ev_dead = mgr.process_snapshot(
        parser.parse(_make_payload(health=0, ammo_clip=19), received_at_ns=11_000_000)
    )
    assert not any(e.event_type == EventType.SHOT_FIRED for e in ev_dead)


def test_c4_health_flash_fire_team_and_disconnect_lifecycle() -> None:
    parser = GSIParser()
    mgr = EventManager(critical_health_threshold=25, disconnect_timeout_s=35.0)

    # Conexão inicial + C4 plantada + flash + fogo + vida crítica
    ev1 = mgr.process_snapshot(
        parser.parse(
            _make_payload(
                health=18,
                flashed=220,
                burning=150,
                team="CT",
                bomb="planted",
            ),
            received_at_ns=1_000_000,
            received_at_wall=100.0,
        )
    )
    types1 = {e.event_type for e in ev1}
    assert EventType.CONNECTION_CHANGED in types1
    assert EventType.TEAM_CHANGED in types1
    assert EventType.HEALTH_CHANGED in types1
    assert EventType.FLASHBANG_CHANGED in types1
    assert EventType.FIRE_CHANGED in types1
    assert EventType.BOMB_PLANTED in types1
    assert mgr.bomb_planted_at_ns == 1_000_000

    hp_ev = next(e for e in ev1 if e.event_type == EventType.HEALTH_CHANGED)
    assert hp_ev.data["is_critical"] is True
    assert hp_ev.data["is_dead"] is False

    # Tick repetido com C4 ainda planted não duplica BOMB_PLANTED
    ev2 = mgr.process_snapshot(
        parser.parse(
            _make_payload(health=18, flashed=0, burning=0, team="CT", bomb="planted"),
            received_at_ns=2_000_000,
            received_at_wall=101.0,
        )
    )
    assert not any(e.event_type == EventType.BOMB_PLANTED for e in ev2)
    flash_off = next(e for e in ev2 if e.event_type == EventType.FLASHBANG_CHANGED)
    assert flash_off.data["active"] is False

    # Desarme da C4
    ev_def = mgr.process_snapshot(
        parser.parse(
            _make_payload(bomb="defused"),
            received_at_ns=3_000_000,
            received_at_wall=102.0,
        )
    )
    assert any(e.event_type == EventType.BOMB_DEFUSED for e in ev_def)
    assert mgr.bomb_planted_at_ns is None

    # Explosão da C4
    mgr.process_snapshot(
        parser.parse(_make_payload(bomb="planted"), received_at_ns=4_000_000, received_at_wall=103.0)
    )
    ev_exp = mgr.process_snapshot(
        parser.parse(_make_payload(bomb="exploded"), received_at_ns=5_000_000, received_at_wall=104.0)
    )
    assert any(e.event_type == EventType.BOMB_EXPLODED for e in ev_exp)

    # Limpeza em novo round
    mgr.process_snapshot(
        parser.parse(_make_payload(bomb="planted"), received_at_ns=6_000_000, received_at_wall=105.0)
    )
    ev_clear = mgr.process_snapshot(
        parser.parse(
            {"round": {"phase": "freezetime"}, "previously": {"round": {"bomb": "planted"}}},
            received_at_ns=7_000_000,
            received_at_wall=106.0,
        )
    )
    assert any(e.event_type == EventType.BOMB_CLEARED for e in ev_clear)

    # Timeout de desconexão após 36s sem pacotes
    assert mgr.check_timeout(now_wall=120.0) == []
    ev_disc = mgr.check_timeout(now_wall=143.0)
    assert len(ev_disc) == 1
    assert ev_disc[0].event_type == EventType.CONNECTION_CHANGED
    assert ev_disc[0].data["connected"] is False

    # Reconexão com munição menor que antes NÃO gera disparo fantasma
    ev_reconn = mgr.process_snapshot(
        parser.parse(_make_payload(ammo_clip=12), received_at_ns=8_000_000, received_at_wall=150.0)
    )
    assert any(
        e.event_type == EventType.CONNECTION_CHANGED and e.data["connected"] is True
        for e in ev_reconn
    )
    assert not any(e.event_type == EventType.SHOT_FIRED for e in ev_reconn)


def test_flashbang_real_binary_gradual_float_and_spectator_isolation() -> None:
    parser = GSIParser()
    mgr = EventManager()

    # 1. Sequência real capturada no log do CS2 em treino (0 -> 1 -> 0)
    mgr.process_snapshot(parser.parse(_make_payload(flashed=0), received_at_ns=1_000_000))
    ev_on = mgr.process_snapshot(
        parser.parse(_make_payload(flashed=1), received_at_ns=2_000_000)
    )
    fl_on = next(e for e in ev_on if e.event_type == EventType.FLASHBANG_CHANGED)
    assert fl_on.data["old_intensity"] == 0
    assert fl_on.data["intensity"] == 1
    assert fl_on.data["active"] is True
    assert fl_on.data["raw_value"] == 1
    assert fl_on.data["scale"] == "int"
    assert fl_on.data["is_local_player"] is True

    ev_off = mgr.process_snapshot(
        parser.parse(_make_payload(flashed=0), received_at_ns=3_000_000)
    )
    fl_off = next(e for e in ev_off if e.event_type == EventType.FLASHBANG_CHANGED)
    assert fl_off.data["active"] is False
    assert fl_off.data["intensity"] == 0

    # 2. Sequência gradual 0 -> 255 -> 140 -> 0
    ev_255 = mgr.process_snapshot(
        parser.parse(_make_payload(flashed=255), received_at_ns=4_000_000)
    )
    ev_140 = mgr.process_snapshot(
        parser.parse(_make_payload(flashed=140), received_at_ns=5_000_000)
    )
    ev_0 = mgr.process_snapshot(
        parser.parse(_make_payload(flashed=0), received_at_ns=6_000_000)
    )
    assert next(e for e in ev_255 if e.event_type == EventType.FLASHBANG_CHANGED).data["intensity"] == 255
    assert next(e for e in ev_140 if e.event_type == EventType.FLASHBANG_CHANGED).data["intensity"] == 140
    assert next(e for e in ev_0 if e.event_type == EventType.FLASHBANG_CHANGED).data["intensity"] == 0

    # 3. Sequência float normalizada 0.0 -> 1.0 -> 0.5 -> 0.0
    for fval, expected_int in ((1.0, 255), (0.5, 128), (0.0, 0)):
        p_float = _make_payload(flashed=0)
        p_float["player"]["state"]["flashed"] = fval
        ev_fl = mgr.process_snapshot(parser.parse(p_float, received_at_ns=7_000_000))
        fl_ev = next(e for e in ev_fl if e.event_type == EventType.FLASHBANG_CHANGED)
        assert fl_ev.data["intensity"] == expected_int
        assert fl_ev.data["scale"] == "float_unit"

    # 4. Espectador (provider_steamid != player_steamid) marca is_local_player=False
    ev_spec = mgr.process_snapshot(
        parser.parse(
            _make_payload(flashed=255, player_steamid="76561198000000099"),
            received_at_ns=8_000_000,
        )
    )
    fl_spec = next(e for e in ev_spec if e.event_type == EventType.FLASHBANG_CHANGED)
    assert fl_spec.data["is_local_player"] is False
