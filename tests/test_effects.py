"""Testes automatizados para os efeitos RGB individuais (`app/effects.py`)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from app.effects import (
    DEFAULT_PRIORITY_ORDER,
    EffectInput,
    compute_c4_beep_intensity,
    evaluate_c4,
    evaluate_fire,
    evaluate_flashbang,
    evaluate_health,
    evaluate_health_critical,
    evaluate_shot,
    evaluate_team_round,
    evaluate_weapon,
    resolve_active_effect,
)
from app.gsi_parser import GameStateSnapshot, WeaponState

DEFAULT_CFG_PATH = Path(__file__).resolve().parent.parent / "config" / "default_config.json"


def _load_default_cfg() -> dict:
    return json.loads(DEFAULT_CFG_PATH.read_text(encoding="utf-8"))


def test_flashbang_scales_proportionally_handles_value_one_and_spectator() -> None:
    cfg = _load_default_cfg()
    full = evaluate_flashbang(
        EffectInput(
            snapshot=GameStateSnapshot(connected=True, flashed=255),
            now_ns=1_000_000,
            shot_active_until_ns=0,
            bomb_planted_at_ns=None,
            config=cfg,
        )
    )
    mid = evaluate_flashbang(
        EffectInput(
            snapshot=GameStateSnapshot(connected=True, flashed=128),
            now_ns=1_000_000,
            shot_active_until_ns=0,
            bomb_planted_at_ns=None,
            config=cfg,
        )
    )
    low = evaluate_flashbang(
        EffectInput(
            snapshot=GameStateSnapshot(connected=True, flashed=40),
            now_ns=1_000_000,
            shot_active_until_ns=0,
            bomb_planted_at_ns=None,
            config=cfg,
        )
    )
    unit_one = evaluate_flashbang(
        EffectInput(
            snapshot=GameStateSnapshot(connected=True, flashed=1),
            now_ns=1_000_000,
            shot_active_until_ns=0,
            bomb_planted_at_ns=None,
            config=cfg,
        )
    )
    spectator = evaluate_flashbang(
        EffectInput(
            snapshot=GameStateSnapshot(
                connected=True, flashed=255, is_local_player=False
            ),
            now_ns=1_000_000,
            shot_active_until_ns=0,
            bomb_planted_at_ns=None,
            config=cfg,
        )
    )
    off = evaluate_flashbang(
        EffectInput(
            snapshot=GameStateSnapshot(connected=True, flashed=0),
            now_ns=1_000_000,
            shot_active_until_ns=0,
            bomb_planted_at_ns=None,
            config=cfg,
        )
    )

    assert full is not None and full.color.to_tuple() == (255, 255, 255)
    assert full.instant is True
    assert mid is not None and low is not None and mid.instant is True and low.instant is True
    assert full.color.r > mid.color.r > low.color.r > 0
    assert unit_one is not None and unit_one.color.r > 0 and unit_one.instant is True
    assert spectator is None
    assert off is None


def test_priority_order_places_fire_above_c4() -> None:
    cfg = _load_default_cfg()
    assert DEFAULT_PRIORITY_ORDER == (
        "flashbang",
        "shot",
        "fire",
        "c4",
        "health_critical",
        "health",
        "team_round",
        "weapon",
    )
    res = resolve_active_effect(
        EffectInput(
            snapshot=GameStateSnapshot(
                connected=True,
                bomb_state="planted",
                burning=180,
                burning_field_seen=True,
            ),
            now_ns=1_000_000_000,
            shot_active_until_ns=0,
            bomb_planted_at_ns=900_000_000,
            config=cfg,
        )
    )
    assert res is not None and res.effect_id == "fire"


def test_shot_effect_window() -> None:
    cfg = _load_default_cfg()
    snap = GameStateSnapshot(connected=True)
    active = evaluate_shot(
        EffectInput(
            snapshot=snap,
            now_ns=10_000_000,
            shot_active_until_ns=60_000_000,
            bomb_planted_at_ns=None,
            config=cfg,
        )
    )
    expired = evaluate_shot(
        EffectInput(
            snapshot=snap,
            now_ns=60_000_000,
            shot_active_until_ns=60_000_000,
            bomb_planted_at_ns=None,
            config=cfg,
        )
    )
    assert active is not None and active.color.to_hex() == "#FF9900"
    assert expired is None


def test_c4_beep_cadence_off_between_beeps_and_accelerates() -> None:
    cfg = _load_default_cfg()
    planted_ns = 1_000_000_000
    snap_planted = GameStateSnapshot(connected=True, bomb_state="planted")

    # No início (intervalo ~1.0s, bipada ~0.24s): acende no pico (~0.08s) e apaga no intervalo (0.50s)
    assert compute_c4_beep_intensity(0.08) > 0.7
    assert compute_c4_beep_intensity(0.50) == 0.0
    assert compute_c4_beep_intensity(0.95) == 0.0

    # Conta picos por janela de 3 segundos no início vs próximo de 40s
    def count_beeps(start_s: float, end_s: float) -> int:
        was_lit = False
        beeps = 0
        steps = 300
        for i in range(steps):
            t_s = start_s + (end_s - start_s) * (i / steps)
            res = evaluate_c4(
                EffectInput(
                    snapshot=snap_planted,
                    now_ns=planted_ns + int(t_s * 1_000_000_000),
                    shot_active_until_ns=0,
                    bomb_planted_at_ns=planted_ns,
                    config=cfg,
                )
            )
            assert res is not None
            assert res.color.g == 0 and res.color.b == 0
            is_lit = res.color.r >= 100
            if is_lit and not was_lit:
                beeps += 1
            was_lit = is_lit
        return beeps

    early_beeps = count_beeps(0.0, 3.0)
    mid_beeps = count_beeps(20.0, 23.0)
    late_beeps = count_beeps(36.5, 39.5)
    assert 2 <= early_beeps <= 4
    assert mid_beeps > early_beeps
    assert late_beeps > mid_beeps * 2

    # Interrompe imediatamente ao desarmar ou explodir
    assert (
        evaluate_c4(
            EffectInput(
                snapshot=GameStateSnapshot(connected=True, bomb_state="defused"),
                now_ns=planted_ns + 5_000_000_000,
                shot_active_until_ns=0,
                bomb_planted_at_ns=None,
                config=cfg,
            )
        )
        is None
    )
    assert (
        evaluate_c4(
            EffectInput(
                snapshot=GameStateSnapshot(connected=True, bomb_state="exploded"),
                now_ns=planted_ns + 5_000_000_000,
                shot_active_until_ns=0,
                bomb_planted_at_ns=None,
                config=cfg,
            )
        )
        is None
    )


def test_fire_requires_real_burning_field() -> None:
    cfg = _load_default_cfg()
    without_field = evaluate_fire(
        EffectInput(
            snapshot=GameStateSnapshot(
                connected=True, burning=150, burning_field_seen=False
            ),
            now_ns=1_000_000_000,
            shot_active_until_ns=0,
            bomb_planted_at_ns=None,
            config=cfg,
        )
    )
    with_field = evaluate_fire(
        EffectInput(
            snapshot=GameStateSnapshot(
                connected=True, burning=150, burning_field_seen=True
            ),
            now_ns=1_000_000_000,
            shot_active_until_ns=0,
            bomb_planted_at_ns=None,
            config=cfg,
        )
    )
    assert without_field is None
    assert with_field is not None
    assert with_field.color.r == 255
    assert with_field.color.b == 0


def test_health_disabled_by_default_and_works_when_enabled() -> None:
    cfg = _load_default_cfg()
    snap_live = GameStateSnapshot(connected=True, round_phase="live", health=100)
    assert (
        evaluate_health(
            EffectInput(
                snapshot=snap_live,
                now_ns=1_000_000_000,
                shot_active_until_ns=0,
                bomb_planted_at_ns=None,
                config=cfg,
            )
        )
        is None
    )

    cfg["effects"]["health"]["enabled"] = True

    def hp_color(hp: int):
        return evaluate_health(
            EffectInput(
                snapshot=GameStateSnapshot(
                    connected=True, round_phase="live", health=hp
                ),
                now_ns=1_000_000_000,
                shot_active_until_ns=0,
                bomb_planted_at_ns=None,
                config=cfg,
            )
        )

    assert hp_color(100).color.to_hex() == "#00FF00"
    assert hp_color(75).color.to_hex() == "#80FF00"
    assert hp_color(50).color.to_hex() == "#FFFF00"
    assert hp_color(25).color.to_hex() == "#FF9900"
    mid = hp_color(88)
    assert 0 < mid.color.r < 128 and mid.color.g == 255
    assert hp_color(20) is None

    crit = evaluate_health_critical(
        EffectInput(
            snapshot=GameStateSnapshot(connected=True, round_phase="live", health=15),
            now_ns=1_100_000_000,
            shot_active_until_ns=0,
            bomb_planted_at_ns=None,
            config=cfg,
        )
    )
    assert crit is not None and crit.color.r > 0 and crit.color.g == 0


def test_team_and_weapons_disabled_by_default_and_work_when_enabled() -> None:
    cfg = _load_default_cfg()
    assert (
        evaluate_team_round(
            EffectInput(
                snapshot=GameStateSnapshot(connected=True, team="CT", round_phase="freezetime"),
                now_ns=1_000_000,
                shot_active_until_ns=0,
                bomb_planted_at_ns=None,
                config=cfg,
            )
        )
        is None
    )

    cfg["effects"]["team"]["enabled"] = True
    cfg["effects"]["weapons"]["enabled"] = True

    # Em fase live ou over, cores CT/TR devem permanecer desativadas
    assert (
        evaluate_team_round(
            EffectInput(
                snapshot=GameStateSnapshot(connected=True, team="T", round_phase="live"),
                now_ns=1_000_000,
                shot_active_until_ns=0,
                bomb_planted_at_ns=None,
                config=cfg,
            )
        )
        is None
    )
    assert (
        evaluate_team_round(
            EffectInput(
                snapshot=GameStateSnapshot(connected=True, team="CT", round_phase="over"),
                now_ns=1_000_000,
                shot_active_until_ns=0,
                bomb_planted_at_ns=None,
                config=cfg,
            )
        )
        is None
    )

    # Em freezetime sem pulso (cor sólida), aplica exatamente as cores configuradas
    cfg["effects"]["team"]["freezetime_pulse"] = False
    t_freeze = evaluate_team_round(
        EffectInput(
            snapshot=GameStateSnapshot(connected=True, team="T", round_phase="freezetime"),
            now_ns=1_000_000,
            shot_active_until_ns=0,
            bomb_planted_at_ns=None,
            config=cfg,
        )
    )
    ct_freeze = evaluate_team_round(
        EffectInput(
            snapshot=GameStateSnapshot(connected=True, team="CT", round_phase="freezetime"),
            now_ns=1_000_000,
            shot_active_until_ns=0,
            bomb_planted_at_ns=None,
            config=cfg,
        )
    )
    assert t_freeze is not None and t_freeze.color.to_hex() == "#FF9900"
    assert ct_freeze is not None and ct_freeze.color.to_hex() == "#008CFF"

    # Em freezetime com pulso habilitado, varia a luminosidade suavemente
    cfg["effects"]["team"]["freezetime_pulse"] = True
    ct_freeze_samples = {
        evaluate_team_round(
            EffectInput(
                snapshot=GameStateSnapshot(
                    connected=True, team="CT", round_phase="freezetime"
                ),
                now_ns=t_ms * 1_000_000,
                shot_active_until_ns=0,
                bomb_planted_at_ns=None,
                config=cfg,
            )
        ).color.b
        for t_ms in (0, 300, 625, 900)
    }
    assert len(ct_freeze_samples) > 1

    expected_categories = copy.deepcopy(cfg["effects"]["weapons"]["categories"])
    for cat, expected_hex in expected_categories.items():
        w = WeaponState(
            slot="weapon_1",
            name=f"weapon_{cat}",
            weapon_type=cat,
            category=cat,
            state="active",
            ammo_clip=10,
            ammo_clip_max=10,
            ammo_reserve=30,
        )
        res = evaluate_weapon(
            EffectInput(
                snapshot=GameStateSnapshot(connected=True, active_weapon=w),
                now_ns=1_000_000,
                shot_active_until_ns=0,
                bomb_planted_at_ns=None,
                config=cfg,
            )
        )
        assert res is not None and res.color.to_hex() == expected_hex
