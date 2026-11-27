"""Testes automatizados para GSIParser (payloads parciais, previously/added e ausência vs zero)."""

from __future__ import annotations

from app.gsi_parser import GSIParser, classify_weapon


def _full_payload() -> dict:
    return {
        "provider": {
            "name": "Counter-Strike 2",
            "appid": 730,
            "steamid": "76561198000000001",
        },
        "map": {"name": "de_mirage", "phase": "live", "round": 4},
        "round": {"phase": "live", "bomb": "planted"},
        "player": {
            "steamid": "76561198000000001",
            "name": "Jogador",
            "activity": "playing",
            "team": "CT",
            "state": {
                "health": 82,
                "armor": 95,
                "helmet": True,
                "flashed": 140,
                "burning": 60,
            },
            "weapons": {
                "weapon_0": {
                    "name": "weapon_knife",
                    "type": "Knife",
                    "state": "holstered",
                },
                "weapon_1": {
                    "name": "weapon_m4a1_silencer",
                    "type": "Rifle",
                    "state": "active",
                    "ammo_clip": 20,
                    "ammo_clip_max": 20,
                    "ammo_reserve": 60,
                },
            },
        },
    }


def test_parser_interprets_full_payload() -> None:
    parser = GSIParser()
    snap = parser.parse(_full_payload(), received_at_ns=1000, received_at_wall=10.0)

    assert snap.connected is True
    assert snap.provider_appid == 730
    assert snap.map_name == "de_mirage"
    assert snap.round_phase == "live"
    assert snap.bomb_state == "planted"
    assert snap.team == "CT"
    assert snap.is_local_player is True
    assert snap.health == 82
    assert snap.armor == 95
    assert snap.helmet is True
    assert snap.flashed == 140
    assert snap.burning == 60
    assert snap.burning_field_seen is True
    assert snap.active_weapon is not None
    assert snap.active_weapon.name == "weapon_m4a1_silencer"
    assert snap.active_weapon.category == "rifle"
    assert snap.active_weapon.ammo_clip == 20


def test_parser_preserves_last_valid_state_across_partial_payloads() -> None:
    parser = GSIParser()
    parser.parse(_full_payload(), received_at_ns=1000, received_at_wall=10.0)

    # Heartbeat parcial apenas com provider
    snap2 = parser.parse(
        {"provider": {"name": "Counter-Strike 2", "appid": 730}},
        received_at_ns=2000,
        received_at_wall=11.0,
    )
    assert snap2.health == 82
    assert snap2.team == "CT"
    assert snap2.bomb_state == "planted"
    assert snap2.active_weapon is not None
    assert snap2.active_weapon.ammo_clip == 20

    # Update parcial alterando somente health
    snap3 = parser.parse(
        {"player": {"state": {"health": 37}}},
        received_at_ns=3000,
        received_at_wall=12.0,
    )
    assert snap3.health == 37
    assert snap3.armor == 95
    assert snap3.flashed == 140
    assert snap3.team == "CT"
    assert snap3.bomb_state == "planted"


def test_parser_distinguishes_zero_from_missing_field() -> None:
    parser = GSIParser()
    parser.parse(_full_payload(), received_at_ns=1000, received_at_wall=10.0)

    # Ausência de health/flashed/burning não zera os campos
    snap_missing = parser.parse(
        {"player": {"state": {"armor": 50}}},
        received_at_ns=2000,
        received_at_wall=11.0,
    )
    assert snap_missing.armor == 50
    assert snap_missing.health == 82
    assert snap_missing.flashed == 140
    assert snap_missing.burning == 60

    # Zero explícito deve atualizar para 0
    snap_zeros = parser.parse(
        {
            "player": {
                "state": {"health": 0, "flashed": 0, "burning": 0},
                "weapons": {
                    "weapon_1": {
                        "name": "weapon_m4a1_silencer",
                        "type": "Rifle",
                        "state": "active",
                        "ammo_clip": 0,
                        "ammo_clip_max": 20,
                        "ammo_reserve": 40,
                    }
                },
            }
        },
        received_at_ns=3000,
        received_at_wall=12.0,
    )
    assert snap_zeros.health == 0
    assert snap_zeros.flashed == 0
    assert snap_zeros.burning == 0
    assert snap_zeros.active_weapon is not None
    assert snap_zeros.active_weapon.ammo_clip == 0


def test_parser_handles_previously_added_and_menu_transitions() -> None:
    parser = GSIParser()
    parser.parse(_full_payload(), received_at_ns=1000, received_at_wall=10.0)

    # Nova rodada sem round.bomb, com bomb presente em previously.round
    snap_new_round = parser.parse(
        {
            "round": {"phase": "freezetime"},
            "previously": {"round": {"phase": "live", "bomb": "planted"}},
            "added": {"round": {"phase": True}},
        },
        received_at_ns=2000,
        received_at_wall=11.0,
    )
    assert snap_new_round.round_phase == "freezetime"
    assert snap_new_round.bomb_state is None
    assert snap_new_round.previously["round"]["bomb"] == "planted"
    assert snap_new_round.added["round"]["phase"] is True

    # Suporte defensivo à chave "previous"
    parser.parse({"round": {"phase": "live", "bomb": "planted"}})
    snap_prev_alias = parser.parse(
        {
            "round": {"phase": "over"},
            "previous": {"round": {"bomb": "planted"}},
        }
    )
    assert snap_prev_alias.bomb_state is None

    # Retorno ao menu limpa estados voláteis de partida mantendo conexão
    snap_menu = parser.parse({"player": {"activity": "menu"}})
    assert snap_menu.connected is True
    assert snap_menu.round_phase is None
    assert snap_menu.bomb_state is None
    assert snap_menu.active_weapon is None
    assert snap_menu.flashed == 0


def test_parser_detects_spectator_and_weapon_categories() -> None:
    parser = GSIParser()
    payload = _full_payload()
    payload["player"]["steamid"] = "76561198000000099"
    snap = parser.parse(payload)
    assert snap.is_local_player is False

    assert classify_weapon("weapon_knife_karambit", "Knife") == "knife"
    assert classify_weapon("weapon_deagle", "Pistol") == "pistol"
    assert classify_weapon("weapon_ak47", "Rifle") == "rifle"
    assert classify_weapon("weapon_awp", "SniperRifle") == "sniper"
    assert classify_weapon("weapon_mp9", "Submachine Gun") == "smg"
    assert classify_weapon("weapon_mag7", "Shotgun") == "shotgun"
    assert classify_weapon("weapon_flashbang", "Grenade") == "grenade"
    assert classify_weapon("weapon_c4", "C4") == "c4"


def test_parser_flashed_scales_types_and_previously_clearing() -> None:
    parser = GSIParser()

    # 1. Payload com string inteira ("210")
    snap1 = parser.parse(
        {
            "provider": {"name": "Counter-Strike 2", "appid": 730, "steamid": "1"},
            "round": {"phase": "live"},
            "player": {"steamid": "1", "activity": "playing", "state": {"flashed": "210"}},
        }
    )
    assert snap1.flashed == 210
    assert snap1.flashed_scale == "str_int"
    assert snap1.flashed_raw == "210"
    assert snap1.flashed_field_seen is True

    # 2. Se flashed desaparecer sem bloco player.state, mas constar em previously.player.state, zera
    snap2 = parser.parse(
        {
            "player": {},
            "previously": {"player": {"state": {"flashed": 210}}},
        }
    )
    assert snap2.flashed == 0
    assert snap2.flashed_raw_type == "previously"

    # 3. Payload representativo do modo binário real observado no CS2 (0 -> 1 -> 0)
    snap_bin_on = parser.parse({"player": {"state": {"flashed": 1}}})
    assert snap_bin_on.flashed == 1
    assert snap_bin_on.flashed_scale == "int"
    assert snap_bin_on.flashed_raw == 1

    # 4. Payload normalizado em float (0.0..1.0) e booleano
    snap_float = parser.parse({"player": {"state": {"flashed": 0.65}}})
    assert snap_float.flashed == round(0.65 * 255)
    assert snap_float.flashed_scale == "float_unit"

    snap_float_one = parser.parse({"player": {"state": {"flashed": 1.0}}})
    assert snap_float_one.flashed == 255
    assert snap_float_one.flashed_scale == "float_unit"

    snap_bool = parser.parse({"player": {"state": {"flashed": True}}})
    assert snap_bool.flashed == 255
    assert snap_bool.flashed_scale == "bool"

    snap_str_unit = parser.parse({"player": {"state": {"flashed": "0.5"}}})
    assert snap_str_unit.flashed == round(0.5 * 255)
    assert snap_str_unit.flashed_scale == "str_unit"

    snap_off = parser.parse({"player": {"state": {"flashed": 0.0}}})
    assert snap_off.flashed == 0
