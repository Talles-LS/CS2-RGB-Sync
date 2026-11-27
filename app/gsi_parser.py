"""
Interpretador de payloads JSON do Counter-Strike 2 Game State Integration (GSI).

Responsabilidades:
- Interpretar payloads completos e parciais do CS2 GSI.
- Tratar blocos `previously` (ou `previous`) e `added` para limpar estados removidos.
- Preservar o último estado válido de cada campo entre atualizações parciais.
- Nunca confundir ausência de campo com valor numérico `0` (ex.: 0 HP, 0 flashed, 0 munição).
- Classificar armas por categoria e detectar quando o usuário está espectando outro jogador.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Optional

_KNIFE_PREFIXES = ("weapon_knife", "weapon_bayonet")

_PISTOLS = frozenset(
    {
        "weapon_glock",
        "weapon_hkp2000",
        "weapon_usp_silencer",
        "weapon_elite",
        "weapon_p250",
        "weapon_tec9",
        "weapon_fiveseven",
        "weapon_cz75a",
        "weapon_deagle",
        "weapon_revolver",
    }
)

_SNIPERS = frozenset(
    {
        "weapon_awp",
        "weapon_ssg08",
        "weapon_scar20",
        "weapon_g3sg1",
    }
)

_SMGS = frozenset(
    {
        "weapon_mac10",
        "weapon_mp9",
        "weapon_mp7",
        "weapon_mp5sd",
        "weapon_ump45",
        "weapon_p90",
        "weapon_bizon",
    }
)

_SHOTGUNS = frozenset(
    {
        "weapon_nova",
        "weapon_xm1014",
        "weapon_sawedoff",
        "weapon_mag7",
    }
)

_RIFLES = frozenset(
    {
        "weapon_ak47",
        "weapon_m4a1",
        "weapon_m4a1_silencer",
        "weapon_famas",
        "weapon_galilar",
        "weapon_aug",
        "weapon_sg556",
        "weapon_m249",
        "weapon_negev",
    }
)

_GRENADES = frozenset(
    {
        "weapon_hegrenade",
        "weapon_flashbang",
        "weapon_smokegrenade",
        "weapon_molotov",
        "weapon_incgrenade",
        "weapon_decoy",
        "weapon_tagrenade",
    }
)


def classify_weapon(weapon_name: str, weapon_type: str = "") -> str:
    """Classifica o nome/tipo de arma do CS2 em categorias configuráveis."""
    name = (weapon_name or "").strip().lower()
    wtype = (weapon_type or "").strip().lower()

    if name == "weapon_c4" or wtype == "c4":
        return "c4"
    if any(name.startswith(prefix) for prefix in _KNIFE_PREFIXES) or wtype == "knife":
        return "knife"
    if name in _GRENADES or wtype == "grenade":
        return "grenade"
    if name in _SNIPERS or wtype in {"sniperrifle", "sniper rifle"}:
        return "sniper"
    if name in _PISTOLS or wtype == "pistol":
        return "pistol"
    if name in _SMGS or wtype in {"submachine gun", "smg"}:
        return "smg"
    if name in _SHOTGUNS or wtype == "shotgun":
        return "shotgun"
    if name in _RIFLES or wtype in {"rifle", "machine gun", "machinegun"}:
        return "rifle"
    return "other"


def _to_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None
    return None


def _parse_intensity_255(value: Any) -> tuple[Optional[int], str]:
    """
    Interpreta valores de intensidade GSI (`flashed`, `burning`) normalizando para `0..255`.

    Retorna `(valor_normalizado, escala_detectada)` aceitando:
    - bool: `True -> 255`, `False -> 0` (`"bool"`)
    - int: faixa direta `0..255` (`"int"`)
    - float: `0.0..1.0` escalado para `0..255` (`"float_unit"`) ou `> 1.0` direto (`"float_255"`)
    - str: string decimal unitária (`"str_unit"`) ou inteira (`"str_int"`)
    """
    if isinstance(value, bool):
        return (255 if value else 0), "bool"
    if isinstance(value, int):
        return max(0, min(255, value)), "int"
    if isinstance(value, float):
        if value <= 0.0:
            return 0, "float_unit"
        if value <= 1.0:
            return max(1, min(255, round(value * 255.0))), "float_unit"
        return max(0, min(255, round(value))), "float_255"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None, "none"
        try:
            fval = float(text)
        except ValueError:
            return None, "none"
        if "." in text:
            if fval <= 0.0:
                return 0, "str_unit"
            if fval <= 1.0:
                return max(1, min(255, round(fval * 255.0))), "str_unit"
        return max(0, min(255, int(round(fval)))), "str_int"
    return None, "none"


def _to_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    return None


def _to_str(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value
    return None


@dataclass(frozen=True)
class WeaponState:
    """Estado de uma arma do jogador no inventário GSI."""

    slot: str
    name: str
    weapon_type: str
    category: str
    state: str
    ammo_clip: Optional[int]
    ammo_clip_max: Optional[int]
    ammo_reserve: Optional[int]


@dataclass(frozen=True)
class GameStateSnapshot:
    """Fotografia consolidada do estado atual do jogo após interpretar um payload GSI."""

    connected: bool = False
    provider_name: Optional[str] = None
    provider_appid: Optional[int] = None
    provider_steamid: Optional[str] = None
    last_update_wall: float = 0.0
    last_update_ns: int = 0

    map_name: Optional[str] = None
    map_phase: Optional[str] = None
    map_round: Optional[int] = None
    round_phase: Optional[str] = None
    countdown_phase: Optional[str] = None
    round_win_team: Optional[str] = None
    bomb_state: Optional[str] = None

    player_steamid: Optional[str] = None
    player_name: Optional[str] = None
    player_activity: Optional[str] = None
    is_local_player: bool = True
    team: Optional[str] = None
    health: Optional[int] = None
    armor: Optional[int] = None
    helmet: Optional[bool] = None
    flashed: Optional[int] = None
    flashed_raw: Any = None
    flashed_raw_type: str = "none"
    flashed_scale: str = "none"
    flashed_field_seen: bool = False
    burning: Optional[int] = None
    burning_field_seen: bool = False

    active_weapon: Optional[WeaponState] = None
    weapons: dict[str, WeaponState] = field(default_factory=dict)

    previously: dict[str, Any] = field(default_factory=dict)
    added: dict[str, Any] = field(default_factory=dict)

    @property
    def is_freezetime(self) -> bool:
        """Indica com segurança se o jogo está atualmente em Freezetime."""
        if not self.connected or self.player_activity == "menu":
            return False
        if (self.map_phase or "").strip().lower() == "warmup":
            return False
        rp = (self.round_phase or "").strip().lower()
        cp = (self.countdown_phase or "").strip().lower()
        if cp and cp != "freezetime":
            return False
        if rp and rp != "freezetime":
            return False
        return rp == "freezetime" or cp == "freezetime"


class GSIParser:
    """Interpretador com memória persistente para payloads completos e parciais do CS2 GSI."""

    def __init__(self) -> None:
        self._state = GameStateSnapshot()

    @property
    def current_state(self) -> GameStateSnapshot:
        return self._state

    def reset(self) -> None:
        """Reinicia todo o estado acumulado do interpretador."""
        self._state = GameStateSnapshot()

    def mark_disconnected(self) -> GameStateSnapshot:
        """Marca a conexão como encerrada e limpa estados voláteis de partida."""
        s = self._state
        self._state = GameStateSnapshot(
            connected=False,
            provider_name=s.provider_name,
            provider_appid=s.provider_appid,
            provider_steamid=s.provider_steamid,
            last_update_wall=s.last_update_wall,
            last_update_ns=s.last_update_ns,
            round_phase=None,
            countdown_phase=None,
            round_win_team=None,
            bomb_state=None,
            flashed=0,
            flashed_raw=0,
            flashed_raw_type="none",
            flashed_scale="none",
            flashed_field_seen=s.flashed_field_seen,
            burning=0,
            burning_field_seen=s.burning_field_seen,
            active_weapon=None,
            weapons={},
        )
        return self._state

    def parse(
        self,
        payload: dict[str, Any],
        received_at_ns: Optional[int] = None,
        received_at_wall: Optional[float] = None,
    ) -> GameStateSnapshot:
        """
        Interpreta um payload GSI (completo ou parcial) e retorna o novo `GameStateSnapshot`.
        """
        if not isinstance(payload, dict):
            return self._state

        now_ns = received_at_ns if received_at_ns is not None else time.perf_counter_ns()
        now_wall = received_at_wall if received_at_wall is not None else time.time()

        raw_prev = payload.get("previously")
        if not isinstance(raw_prev, dict):
            raw_prev = payload.get("previous")
        previously: dict[str, Any] = (
            copy.deepcopy(raw_prev) if isinstance(raw_prev, dict) else {}
        )
        raw_added = payload.get("added")
        added: dict[str, Any] = (
            copy.deepcopy(raw_added) if isinstance(raw_added, dict) else {}
        )

        s = self._state

        # --- Provider ---
        provider_name = s.provider_name
        provider_appid = s.provider_appid
        provider_steamid = s.provider_steamid
        provider_block = payload.get("provider")
        if isinstance(provider_block, dict):
            if "name" in provider_block:
                provider_name = _to_str(provider_block["name"])
            if "appid" in provider_block:
                parsed_appid = _to_int(provider_block["appid"])
                if parsed_appid is not None:
                    provider_appid = parsed_appid
            if "steamid" in provider_block:
                provider_steamid = _to_str(provider_block["steamid"])

        # --- Map ---
        map_name = s.map_name
        map_phase = s.map_phase
        map_round = s.map_round
        map_block = payload.get("map")
        if isinstance(map_block, dict):
            if "name" in map_block:
                map_name = _to_str(map_block["name"])
            if "phase" in map_block:
                map_phase = _to_str(map_block["phase"])
            if "round" in map_block:
                parsed_round = _to_int(map_block["round"])
                if parsed_round is not None:
                    map_round = parsed_round
        elif "map" in previously:
            map_name = None
            map_phase = None
            map_round = None

        # --- Round, Phase Countdowns & Bomb ---
        round_phase = s.round_phase
        countdown_phase = s.countdown_phase
        round_win_team = s.round_win_team
        bomb_state = s.bomb_state
        round_block = payload.get("round")
        prev_round = previously.get("round") if isinstance(previously.get("round"), dict) else {}
        has_round_phase = False

        if isinstance(round_block, dict):
            if "phase" in round_block:
                raw_rp = _to_str(round_block["phase"])
                round_phase = raw_rp.strip().lower() if raw_rp and raw_rp.strip() else None
                has_round_phase = True
            elif "phase" in prev_round:
                round_phase = None
                has_round_phase = True

            if "win_team" in round_block:
                round_win_team = _to_str(round_block["win_team"])
            elif "win_team" in prev_round or round_phase == "freezetime":
                round_win_team = None

            if "bomb" in round_block:
                bomb_state = _to_str(round_block["bomb"])
            elif "bomb" in prev_round or round_phase == "freezetime":
                bomb_state = None
        elif "round" in previously:
            round_phase = None
            round_win_team = None
            bomb_state = None
            has_round_phase = True

        pc_block = payload.get("phase_countdowns")
        prev_pc = (
            previously.get("phase_countdowns")
            if isinstance(previously.get("phase_countdowns"), dict)
            else {}
        )
        has_countdown_phase = False
        if isinstance(pc_block, dict):
            if "phase" in pc_block:
                raw_cp = _to_str(pc_block["phase"])
                countdown_phase = raw_cp.strip().lower() if raw_cp and raw_cp.strip() else None
                has_countdown_phase = True
            elif "phase" in prev_pc:
                countdown_phase = None
                has_countdown_phase = True
        elif "phase_countdowns" in previously:
            countdown_phase = None
            has_countdown_phase = True

        # Reconciliação entre round.phase e phase_countdowns.phase em payloads parciais
        if has_round_phase and not has_countdown_phase:
            if (round_phase == "freezetime") != (countdown_phase == "freezetime"):
                countdown_phase = None
        elif has_countdown_phase and not has_round_phase:
            if countdown_phase in ("freezetime", "live", "over"):
                round_phase = countdown_phase
            elif round_phase == "freezetime" and countdown_phase != "freezetime":
                round_phase = None

        # --- Player ---
        player_steamid = s.player_steamid
        player_name = s.player_name
        player_activity = s.player_activity
        team = s.team
        health = s.health
        armor = s.armor
        helmet = s.helmet
        flashed = s.flashed
        flashed_raw = s.flashed_raw
        flashed_raw_type = s.flashed_raw_type
        flashed_scale = s.flashed_scale
        flashed_field_seen = s.flashed_field_seen
        burning = s.burning
        burning_field_seen = s.burning_field_seen
        weapons = dict(s.weapons)
        active_weapon = s.active_weapon

        player_block = payload.get("player")
        prev_player = (
            previously.get("player") if isinstance(previously.get("player"), dict) else {}
        )
        prev_state = (
            prev_player.get("state") if isinstance(prev_player.get("state"), dict) else {}
        )
        state_has_flashed = False
        state_has_burning = False

        if isinstance(player_block, dict):
            if "steamid" in player_block:
                player_steamid = _to_str(player_block["steamid"])
            if "name" in player_block:
                player_name = _to_str(player_block["name"])
            if "activity" in player_block:
                player_activity = _to_str(player_block["activity"])
            if "team" in player_block:
                team = _to_str(player_block["team"])
            elif "team" in prev_player:
                team = None

            state_block = player_block.get("state")
            if isinstance(state_block, dict):
                if "health" in state_block:
                    parsed_hp = _to_int(state_block["health"])
                    if parsed_hp is not None:
                        health = max(0, min(100, parsed_hp))
                if "armor" in state_block:
                    parsed_armor = _to_int(state_block["armor"])
                    if parsed_armor is not None:
                        armor = max(0, min(100, parsed_armor))
                if "helmet" in state_block:
                    parsed_helmet = _to_bool(state_block["helmet"])
                    if parsed_helmet is not None:
                        helmet = parsed_helmet
                if "flashed" in state_block:
                    raw_flashed_val = state_block["flashed"]
                    parsed_flashed, detected_scale = _parse_intensity_255(raw_flashed_val)
                    if parsed_flashed is not None:
                        flashed = parsed_flashed
                        flashed_raw = raw_flashed_val
                        flashed_raw_type = type(raw_flashed_val).__name__
                        flashed_scale = detected_scale
                        flashed_field_seen = True
                        state_has_flashed = True
                if "burning" in state_block:
                    parsed_burning, _burn_scale = _parse_intensity_255(state_block["burning"])
                    if parsed_burning is not None:
                        burning = parsed_burning
                        burning_field_seen = True
                        state_has_burning = True

            weapons_block = player_block.get("weapons")
            if isinstance(weapons_block, dict):
                weapons, active_weapon = self._parse_weapons(weapons_block)
            elif "weapons" in prev_player:
                weapons = {}
                active_weapon = None
        elif "player" in previously:
            player_activity = None
            team = None
            health = None
            armor = None
            helmet = None
            flashed = 0
            flashed_raw = 0
            flashed_raw_type = "previously"
            flashed_scale = "none"
            burning = 0
            weapons = {}
            active_weapon = None

        if not state_has_flashed and "flashed" in prev_state:
            flashed = 0
            flashed_raw = 0
            flashed_raw_type = "previously"
            flashed_scale = "none"
        if not state_has_burning and "burning" in prev_state:
            burning = 0

        if player_activity == "menu":
            round_phase = None
            countdown_phase = None
            round_win_team = None
            bomb_state = None
            flashed = 0
            flashed_raw = 0
            flashed_raw_type = "menu"
            flashed_scale = "none"
            burning = 0
            weapons = {}
            active_weapon = None

        is_local_player = True
        if provider_steamid and player_steamid:
            is_local_player = provider_steamid == player_steamid

        self._state = GameStateSnapshot(
            connected=True,
            provider_name=provider_name,
            provider_appid=provider_appid,
            provider_steamid=provider_steamid,
            last_update_wall=now_wall,
            last_update_ns=now_ns,
            map_name=map_name,
            map_phase=map_phase,
            map_round=map_round,
            round_phase=round_phase,
            countdown_phase=countdown_phase,
            round_win_team=round_win_team,
            bomb_state=bomb_state,
            player_steamid=player_steamid,
            player_name=player_name,
            player_activity=player_activity,
            is_local_player=is_local_player,
            team=team,
            health=health,
            armor=armor,
            helmet=helmet,
            flashed=flashed,
            flashed_raw=flashed_raw,
            flashed_raw_type=flashed_raw_type,
            flashed_scale=flashed_scale,
            flashed_field_seen=flashed_field_seen,
            burning=burning,
            burning_field_seen=burning_field_seen,
            active_weapon=active_weapon,
            weapons=weapons,
            previously=previously,
            added=added,
        )
        return self._state

    @staticmethod
    def _parse_weapons(
        weapons_block: dict[str, Any],
    ) -> tuple[dict[str, WeaponState], Optional[WeaponState]]:
        parsed: dict[str, WeaponState] = {}
        active: Optional[WeaponState] = None
        reloading_fallback: Optional[WeaponState] = None

        for slot, raw in weapons_block.items():
            if not isinstance(raw, dict):
                continue
            name = _to_str(raw.get("name"))
            if not name:
                continue
            wtype = _to_str(raw.get("type")) or ""
            wstate = (_to_str(raw.get("state")) or "").lower()
            ammo_clip = _to_int(raw.get("ammo_clip")) if "ammo_clip" in raw else None
            ammo_clip_max = (
                _to_int(raw.get("ammo_clip_max")) if "ammo_clip_max" in raw else None
            )
            ammo_reserve = (
                _to_int(raw.get("ammo_reserve")) if "ammo_reserve" in raw else None
            )

            weapon = WeaponState(
                slot=str(slot),
                name=name,
                weapon_type=wtype,
                category=classify_weapon(name, wtype),
                state=wstate,
                ammo_clip=ammo_clip,
                ammo_clip_max=ammo_clip_max,
                ammo_reserve=ammo_reserve,
            )
            parsed[str(slot)] = weapon
            if wstate == "active" and active is None:
                active = weapon
            elif wstate == "reloading" and reloading_fallback is None:
                reloading_fallback = weapon

        return parsed, (active or reloading_fallback)
