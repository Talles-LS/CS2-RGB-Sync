"""
Gerenciador de eventos de partida do CS2 RGB Sync.

Recebe `GameStateSnapshot` produzidos pelo `GSIParser`, compara transições
entre atualizações e gera eventos tipados (`GameEvent`), incluindo detecção
de disparos por delta de `ammo_clip` com proteções contra falsos positivos.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from app.gsi_parser import GameStateSnapshot, WeaponState

NON_BALLISTIC_CATEGORIES = frozenset({"knife", "grenade", "c4", "other"})


class EventType(str, Enum):
    """Eventos semânticos extraídos do fluxo GSI do Counter-Strike 2."""

    CONNECTION_CHANGED = "connection_changed"
    ROUND_PHASE_CHANGED = "round_phase_changed"
    TEAM_CHANGED = "team_changed"
    HEALTH_CHANGED = "health_changed"
    FLASHBANG_CHANGED = "flashbang_changed"
    FIRE_CHANGED = "fire_changed"
    BOMB_PLANTED = "bomb_planted"
    BOMB_DEFUSED = "bomb_defused"
    BOMB_EXPLODED = "bomb_exploded"
    BOMB_CLEARED = "bomb_cleared"
    WEAPON_CHANGED = "weapon_changed"
    SHOT_FIRED = "shot_fired"
    RELOAD_STARTED = "reload_started"
    RELOAD_FINISHED = "reload_finished"


@dataclass(frozen=True)
class GameEvent:
    """Evento discreto detectado com timestamps para medição de latência."""

    event_type: EventType
    received_at_ns: int
    detected_at_ns: int
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EventManagerStats:
    """Estatísticas acumuladas do gerenciador de eventos."""

    snapshots_processed: int
    events_emitted: int
    shots_detected: int
    grouped_shots_detected: int


class EventManager:
    """Detecta eventos discretos e disparos a partir de snapshots consecutivos do GSI."""

    def __init__(
        self,
        shot_debounce_ms: float = 40.0,
        critical_health_threshold: int = 25,
        disconnect_timeout_s: float = 35.0,
        fire_enabled: bool = True,
    ) -> None:
        self.shot_debounce_ms = max(0.0, float(shot_debounce_ms))
        self.critical_health_threshold = int(critical_health_threshold)
        self.disconnect_timeout_s = max(1.0, float(disconnect_timeout_s))
        self.fire_enabled = bool(fire_enabled)

        self._prev_snapshot: Optional[GameStateSnapshot] = None
        self._last_shot_ns: int = 0
        self._bomb_planted_at_ns: Optional[int] = None

        self._snapshots_processed = 0
        self._events_emitted = 0
        self._shots_detected = 0
        self._grouped_shots_detected = 0

    @property
    def last_snapshot(self) -> Optional[GameStateSnapshot]:
        return self._prev_snapshot

    @property
    def bomb_planted_at_ns(self) -> Optional[int]:
        return self._bomb_planted_at_ns

    def get_stats(self) -> EventManagerStats:
        return EventManagerStats(
            snapshots_processed=self._snapshots_processed,
            events_emitted=self._events_emitted,
            shots_detected=self._shots_detected,
            grouped_shots_detected=self._grouped_shots_detected,
        )

    def reset(self) -> None:
        """Reinicia o histórico de comparação de snapshots."""
        self._prev_snapshot = None
        self._last_shot_ns = 0
        self._bomb_planted_at_ns = None

    def process_snapshot(self, snapshot: GameStateSnapshot) -> list[GameEvent]:
        """Compara o snapshot atual com o anterior e retorna os eventos ocorridos."""
        events: list[GameEvent] = []
        prev = self._prev_snapshot
        received_ns = snapshot.last_update_ns or time.perf_counter_ns()
        detected_ns = time.perf_counter_ns()

        self._snapshots_processed += 1

        # 1. Conexão
        was_connected = prev.connected if prev is not None else False
        just_connected = (not was_connected) and snapshot.connected
        if snapshot.connected != was_connected:
            events.append(
                GameEvent(
                    event_type=EventType.CONNECTION_CHANGED,
                    received_at_ns=received_ns,
                    detected_at_ns=detected_ns,
                    data={"connected": snapshot.connected},
                )
            )
            if not snapshot.connected:
                self._bomb_planted_at_ns = None

        # 2. Fase do round
        prev_phase = prev.round_phase if prev is not None else None
        is_new_round_transition = (
            snapshot.round_phase == "freezetime" and prev_phase != "freezetime"
        )
        if snapshot.round_phase != prev_phase and snapshot.round_phase is not None:
            events.append(
                GameEvent(
                    event_type=EventType.ROUND_PHASE_CHANGED,
                    received_at_ns=received_ns,
                    detected_at_ns=detected_ns,
                    data={
                        "old_phase": prev_phase,
                        "new_phase": snapshot.round_phase,
                        "win_team": snapshot.round_win_team,
                    },
                )
            )

        # 3. Equipe
        prev_team = prev.team if prev is not None else None
        if snapshot.team != prev_team and snapshot.team is not None:
            events.append(
                GameEvent(
                    event_type=EventType.TEAM_CHANGED,
                    received_at_ns=received_ns,
                    detected_at_ns=detected_ns,
                    data={"old_team": prev_team, "new_team": snapshot.team},
                )
            )

        # 4. Vida
        prev_hp = prev.health if prev is not None else None
        if snapshot.health is not None and snapshot.health != prev_hp:
            delta = (snapshot.health - prev_hp) if prev_hp is not None else 0
            events.append(
                GameEvent(
                    event_type=EventType.HEALTH_CHANGED,
                    received_at_ns=received_ns,
                    detected_at_ns=detected_ns,
                    data={
                        "old_health": prev_hp,
                        "new_health": snapshot.health,
                        "delta": delta,
                        "is_critical": 0
                        < snapshot.health
                        < self.critical_health_threshold,
                        "is_dead": snapshot.health == 0,
                    },
                )
            )

        # 5. Flashbang
        prev_flashed = prev.flashed if prev is not None else None
        if snapshot.flashed is not None and (
            (prev is not None and snapshot.flashed != prev_flashed)
            or (prev is None and snapshot.flashed > 0)
        ):
            events.append(
                GameEvent(
                    event_type=EventType.FLASHBANG_CHANGED,
                    received_at_ns=received_ns,
                    detected_at_ns=detected_ns,
                    data={
                        "old_intensity": prev_flashed,
                        "intensity": snapshot.flashed,
                        "active": snapshot.flashed > 0,
                        "raw_value": snapshot.flashed_raw,
                        "raw_type": snapshot.flashed_raw_type,
                        "scale": snapshot.flashed_scale,
                        "is_local_player": snapshot.is_local_player,
                    },
                )
            )

        # 6. Fogo / Queimadura (somente se o GSI realmente disponibilizar o campo)
        prev_burning = prev.burning if prev is not None else None
        if (
            self.fire_enabled
            and snapshot.burning_field_seen
            and snapshot.burning is not None
            and (
                (prev is not None and snapshot.burning != prev_burning)
                or (prev is None and snapshot.burning > 0)
            )
        ):
            events.append(
                GameEvent(
                    event_type=EventType.FIRE_CHANGED,
                    received_at_ns=received_ns,
                    detected_at_ns=detected_ns,
                    data={
                        "old_intensity": prev_burning,
                        "intensity": snapshot.burning,
                        "active": snapshot.burning > 0,
                    },
                )
            )

        # 7. C4
        prev_bomb = prev.bomb_state if prev is not None else None
        curr_bomb = snapshot.bomb_state
        if curr_bomb != prev_bomb:
            if curr_bomb == "planted":
                self._bomb_planted_at_ns = received_ns
                events.append(
                    GameEvent(
                        event_type=EventType.BOMB_PLANTED,
                        received_at_ns=received_ns,
                        detected_at_ns=detected_ns,
                        data={"planted_at_ns": received_ns},
                    )
                )
            elif curr_bomb == "defused":
                self._bomb_planted_at_ns = None
                events.append(
                    GameEvent(
                        event_type=EventType.BOMB_DEFUSED,
                        received_at_ns=received_ns,
                        detected_at_ns=detected_ns,
                        data={},
                    )
                )
            elif curr_bomb == "exploded":
                self._bomb_planted_at_ns = None
                events.append(
                    GameEvent(
                        event_type=EventType.BOMB_EXPLODED,
                        received_at_ns=received_ns,
                        detected_at_ns=detected_ns,
                        data={},
                    )
                )
            elif curr_bomb is None and prev_bomb is not None:
                self._bomb_planted_at_ns = None
                events.append(
                    GameEvent(
                        event_type=EventType.BOMB_CLEARED,
                        received_at_ns=received_ns,
                        detected_at_ns=detected_ns,
                        data={"previous_state": prev_bomb},
                    )
                )

        # 8. Arma equipada, recarga e disparo
        prev_w = prev.active_weapon if prev is not None else None
        curr_w = snapshot.active_weapon
        if self._weapon_identity_changed(prev_w, curr_w):
            events.append(
                GameEvent(
                    event_type=EventType.WEAPON_CHANGED,
                    received_at_ns=received_ns,
                    detected_at_ns=detected_ns,
                    data={
                        "old_weapon": prev_w.name if prev_w else None,
                        "new_weapon": curr_w.name if curr_w else None,
                        "category": curr_w.category if curr_w else None,
                        "ammo_clip": curr_w.ammo_clip if curr_w else None,
                    },
                )
            )
        elif prev_w is not None and curr_w is not None:
            if prev_w.state != "reloading" and curr_w.state == "reloading":
                events.append(
                    GameEvent(
                        event_type=EventType.RELOAD_STARTED,
                        received_at_ns=received_ns,
                        detected_at_ns=detected_ns,
                        data={"weapon_name": curr_w.name},
                    )
                )
            elif (
                (prev_w.state == "reloading" and curr_w.state == "active")
                or (
                    prev_w.ammo_clip is not None
                    and curr_w.ammo_clip is not None
                    and curr_w.ammo_clip > prev_w.ammo_clip
                )
            ):
                events.append(
                    GameEvent(
                        event_type=EventType.RELOAD_FINISHED,
                        received_at_ns=received_ns,
                        detected_at_ns=detected_ns,
                        data={
                            "weapon_name": curr_w.name,
                            "ammo_clip": curr_w.ammo_clip,
                        },
                    )
                )

        shot_event = self._detect_shot(
            prev=prev,
            curr=snapshot,
            prev_w=prev_w,
            curr_w=curr_w,
            just_connected=just_connected,
            is_new_round_transition=is_new_round_transition,
            received_ns=received_ns,
            detected_ns=detected_ns,
        )
        if shot_event is not None:
            events.append(shot_event)

        self._prev_snapshot = snapshot
        self._events_emitted += len(events)
        return events

    def check_timeout(self, now_wall: Optional[float] = None) -> list[GameEvent]:
        """Verifica se o CS2 parou de enviar pacotes/heartbeats além do limite configurado."""
        prev = self._prev_snapshot
        if prev is None or not prev.connected or prev.last_update_wall <= 0.0:
            return []

        current_wall = now_wall if now_wall is not None else time.time()
        if (current_wall - prev.last_update_wall) <= self.disconnect_timeout_s:
            return []

        now_ns = time.perf_counter_ns()
        disconnected_snapshot = GameStateSnapshot(
            connected=False,
            provider_name=prev.provider_name,
            provider_appid=prev.provider_appid,
            provider_steamid=prev.provider_steamid,
            last_update_wall=prev.last_update_wall,
            last_update_ns=prev.last_update_ns,
            flashed=0,
            burning=0,
            burning_field_seen=prev.burning_field_seen,
        )
        self._prev_snapshot = disconnected_snapshot
        self._bomb_planted_at_ns = None
        self._events_emitted += 1
        return [
            GameEvent(
                event_type=EventType.CONNECTION_CHANGED,
                received_at_ns=now_ns,
                detected_at_ns=now_ns,
                data={"connected": False, "reason": "heartbeat_timeout"},
            )
        ]

    @staticmethod
    def _weapon_identity_changed(
        prev_w: Optional[WeaponState], curr_w: Optional[WeaponState]
    ) -> bool:
        if prev_w is None and curr_w is None:
            return False
        if prev_w is None or curr_w is None:
            return True
        return prev_w.name != curr_w.name or prev_w.slot != curr_w.slot

    def _detect_shot(
        self,
        *,
        prev: Optional[GameStateSnapshot],
        curr: GameStateSnapshot,
        prev_w: Optional[WeaponState],
        curr_w: Optional[WeaponState],
        just_connected: bool,
        is_new_round_transition: bool,
        received_ns: int,
        detected_ns: int,
    ) -> Optional[GameEvent]:
        """
        Detecta disparo pela redução de `ammo_clip` entre atualizações consecutivas
        com proteções contra recargas, trocas de arma, espectador e estados inválidos.
        """
        if just_connected or prev is None or not prev.connected or not curr.connected:
            return None
        if curr.player_activity != "playing" or not curr.is_local_player:
            return None
        if curr.health is not None and curr.health <= 0:
            return None
        if curr.round_phase == "freezetime" or is_new_round_transition:
            return None
        if prev_w is None or curr_w is None:
            return None
        if prev_w.name != curr_w.name or prev_w.slot != curr_w.slot:
            return None
        if curr_w.category in NON_BALLISTIC_CATEGORIES:
            return None
        if prev_w.state == "reloading" or curr_w.state == "reloading":
            return None
        if prev_w.ammo_clip is None or curr_w.ammo_clip is None:
            return None
        if curr_w.ammo_clip < 0 or prev_w.ammo_clip <= curr_w.ammo_clip:
            return None
        if (
            prev_w.ammo_clip_max is not None
            and curr_w.ammo_clip_max is not None
            and prev_w.ammo_clip_max != curr_w.ammo_clip_max
        ):
            return None

        debounce_ns = int(self.shot_debounce_ms * 1_000_000)
        if self._last_shot_ns > 0 and (received_ns - self._last_shot_ns) < debounce_ns:
            return None

        bullets_delta = prev_w.ammo_clip - curr_w.ammo_clip
        self._last_shot_ns = received_ns
        self._shots_detected += 1
        if bullets_delta > 1:
            self._grouped_shots_detected += 1

        return GameEvent(
            event_type=EventType.SHOT_FIRED,
            received_at_ns=received_ns,
            detected_at_ns=detected_ns,
            data={
                "weapon_name": curr_w.name,
                "weapon_category": curr_w.category,
                "prev_ammo": prev_w.ammo_clip,
                "curr_ammo": curr_w.ammo_clip,
                "bullets_delta": bullets_delta,
                "grouped_shots": bullets_delta > 1,
            },
        )
