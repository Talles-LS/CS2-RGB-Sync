"""
Simulated CS2 GSI scenario generator for testing effects without launching CS2.

Always marks generated payloads with ``_simulation=True`` so simulated data
is strictly isolated from live match telemetry.
"""

from __future__ import annotations

import copy
import time
from typing import Any, Optional

from app.i18n import t

WEAPON_PRESETS: dict[str, tuple[str, str, int, int]] = {
    "knife": ("weapon_knife_karambit", "Knife", 0, 0),
    "pistol": ("weapon_deagle", "Pistol", 7, 7),
    "rifle": ("weapon_ak47", "Rifle", 30, 30),
    "sniper": ("weapon_awp", "SniperRifle", 5, 5),
    "smg": ("weapon_mp9", "Submachine Gun", 30, 30),
    "shotgun": ("weapon_mag7", "Shotgun", 5, 5),
    "grenade": ("weapon_flashbang", "Grenade", 0, 0),
}

_VALID_ROUND_PHASES = frozenset({"freezetime", "live", "over"})


class GSISimulator:
    """Maintains simulated match state and emits payloads in official CS2 GSI format."""

    is_simulation: bool = True

    def __init__(self) -> None:
        self._team = "CT"
        self._round_phase = "live"
        self._bomb: str | None = None
        self._prev_round_phase = "live"
        self._prev_bomb: str | None = None
        self._health = 100
        self._armor = 100
        self._flashed = 0
        self._burning = 0
        self._weapon_key = "rifle"
        self._ammo_clip = 30
        self._connected = True

    @property
    def team(self) -> str:
        return self._team

    @property
    def round_phase(self) -> str:
        return self._round_phase

    @property
    def bomb(self) -> Optional[str]:
        return self._bomb

    @property
    def health(self) -> int:
        return self._health

    @property
    def flashed(self) -> int:
        return self._flashed

    @property
    def burning(self) -> int:
        return self._burning

    @property
    def weapon_key(self) -> str:
        return self._weapon_key

    @property
    def ammo_clip(self) -> int:
        return self._ammo_clip

    @property
    def connected(self) -> bool:
        return self._connected

    def reset(self) -> dict[str, Any]:
        """Reset simulated state to clean connected defaults and return baseline payload."""
        self._team = "CT"
        self._round_phase = "live"
        self._bomb = None
        self._prev_round_phase = "live"
        self._prev_bomb = None
        self._health = 100
        self._armor = 100
        self._flashed = 0
        self._burning = 0
        self._weapon_key = "rifle"
        self._ammo_clip = 30
        self._connected = True
        return self.build_payload()

    def set_team(self, team: str) -> dict[str, Any]:
        self._team = "T" if team.upper() in ("T", "TR") else "CT"
        self._connected = True
        return self.build_payload()

    def set_round_phase(self, phase: str) -> dict[str, Any]:
        normalized = str(phase).strip().lower()
        if normalized not in _VALID_ROUND_PHASES:
            normalized = "live"
        self._round_phase = normalized
        if normalized == "freezetime":
            self._bomb = None
        self._connected = True
        return self.build_payload()

    def set_health(self, health: int) -> dict[str, Any]:
        self._health = max(0, min(100, int(health)))
        self._connected = True
        return self.build_payload()

    def set_flashed(self, intensity: int) -> dict[str, Any]:
        self._flashed = max(0, min(255, int(intensity)))
        self._connected = True
        return self.build_payload()

    def set_burning(self, intensity: int) -> dict[str, Any]:
        self._burning = max(0, min(255, int(intensity)))
        self._connected = True
        return self.build_payload()

    def set_bomb(self, bomb_state: str | None) -> dict[str, Any]:
        self._bomb = bomb_state
        if bomb_state == "planted" and self._round_phase == "freezetime":
            self._round_phase = "live"
        self._connected = True
        return self.build_payload()

    def select_weapon(self, category: str) -> dict[str, Any]:
        key = category.lower()
        if key not in WEAPON_PRESETS:
            raise ValueError(t("errors.unknown_weapon_cat", category=category))
        self._weapon_key = key
        _, _, clip, _ = WEAPON_PRESETS[key]
        self._ammo_clip = clip
        self._connected = True
        return self.build_payload()

    def prepare_shot_baseline(self) -> Optional[dict[str, Any]]:
        """
        Ensure simulator state is valid for a real ammo_clip drop before firing.

        Returns a baseline payload if weapon, health, round phase, or magazine had
        to be prepared first; otherwise returns None.
        """
        needs_baseline = False
        self._connected = True
        if self._round_phase != "live":
            self._round_phase = "live"
            needs_baseline = True
        if self._health <= 0:
            self._health = 100
            needs_baseline = True
        if self._weapon_key in ("knife", "grenade"):
            self._weapon_key = "rifle"
            self._ammo_clip = 30
            needs_baseline = True
        elif self._ammo_clip <= 0:
            _, _, clip_max, _ = WEAPON_PRESETS[self._weapon_key]
            self._ammo_clip = max(2, clip_max)
            needs_baseline = True

        return self.build_payload() if needs_baseline else None

    def trigger_shot(self) -> dict[str, Any]:
        self._connected = True
        if self._weapon_key in ("knife", "grenade"):
            self._weapon_key = "rifle"
            self._ammo_clip = 30
        if self._ammo_clip <= 0:
            _, _, clip_max, _ = WEAPON_PRESETS[self._weapon_key]
            self._ammo_clip = max(1, clip_max)
        else:
            self._ammo_clip -= 1
        return self.build_payload()

    def build_payload(self) -> dict[str, Any]:
        wname, wtype, clip_max, _ = WEAPON_PRESETS[self._weapon_key]
        weapon_entry: dict[str, Any] = {
            "name": wname,
            "type": wtype,
            "state": "active",
        }
        if clip_max > 0:
            weapon_entry["ammo_clip"] = self._ammo_clip
            weapon_entry["ammo_clip_max"] = clip_max
            weapon_entry["ammo_reserve"] = 90

        round_block: dict[str, Any] = {"phase": self._round_phase}
        prev_round: dict[str, Any] = {}
        if self._bomb is not None:
            round_block["bomb"] = self._bomb
        elif self._prev_bomb is not None:
            prev_round["bomb"] = self._prev_bomb
        if self._prev_round_phase != self._round_phase:
            prev_round["phase"] = self._prev_round_phase

        previously: dict[str, Any] = {"round": prev_round} if prev_round else {}
        self._prev_bomb = self._bomb
        self._prev_round_phase = self._round_phase

        return copy.deepcopy(
            {
                "provider": {
                    "name": "CS2 RGB Sync Simulator",
                    "appid": 730,
                    "steamid": "76561198000000001",
                    "timestamp": int(time.time()),
                },
                "map": {"name": "de_mirage", "phase": "live", "round": 1},
                "round": round_block,
                "phase_countdowns": {"phase": self._round_phase},
                "player": {
                    "steamid": "76561198000000001",
                    "name": "Simulation",
                    "activity": "playing",
                    "team": self._team,
                    "state": {
                        "health": self._health,
                        "armor": self._armor,
                        "helmet": True,
                        "flashed": self._flashed,
                        "burning": self._burning,
                    },
                    "weapons": {"weapon_1": weapon_entry},
                },
                "previously": previously,
                "_simulation": True,
            }
        )
