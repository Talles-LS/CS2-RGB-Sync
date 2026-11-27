"""
Gerador de cenários simulados do CS2 GSI para testes sem abrir o jogo.

Sempre identifica explicitamente o estado gerado como simulação (`is_simulation=True`),
nunca apresentando dados simulados como se fossem dados reais de partida.
"""

from __future__ import annotations

import copy
import time
from typing import Any


WEAPON_PRESETS: dict[str, tuple[str, str, int, int]] = {
    "knife": ("weapon_knife_karambit", "Knife", 0, 0),
    "pistol": ("weapon_deagle", "Pistol", 7, 7),
    "rifle": ("weapon_ak47", "Rifle", 30, 30),
    "sniper": ("weapon_awp", "SniperRifle", 5, 5),
    "smg": ("weapon_mp9", "Submachine Gun", 30, 30),
    "shotgun": ("weapon_mag7", "Shotgun", 5, 5),
    "grenade": ("weapon_flashbang", "Grenade", 0, 0),
}


class GSISimulator:
    """Mantém estado de partida simulado e produz payloads no formato oficial GSI."""

    is_simulation: bool = True

    def __init__(self) -> None:
        self._team = "CT"
        self._round_phase = "live"
        self._bomb: str | None = None
        self._health = 100
        self._armor = 100
        self._flashed = 0
        self._burning = 0
        self._weapon_key = "rifle"
        self._ammo_clip = 30
        self._connected = True

    def set_team(self, team: str) -> dict[str, Any]:
        self._team = "T" if team.upper() in ("T", "TR") else "CT"
        self._connected = True
        return self.build_payload()

    def set_round_phase(self, phase: str) -> dict[str, Any]:
        self._round_phase = phase
        if phase == "freezetime":
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
        self._connected = True
        return self.build_payload()

    def select_weapon(self, category: str) -> dict[str, Any]:
        key = category.lower()
        if key not in WEAPON_PRESETS:
            raise ValueError(f"Categoria de arma simulada desconhecida: {category}")
        self._weapon_key = key
        _, _, clip, _ = WEAPON_PRESETS[key]
        self._ammo_clip = clip
        self._connected = True
        return self.build_payload()

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
        previously: dict[str, Any] = {}
        if self._bomb is not None:
            round_block["bomb"] = self._bomb
        else:
            previously = {"round": {"bomb": "planted"}}

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
                    "name": "Simulacao",
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
