"""
Motor de iluminação RGB independente e sistema de prioridades do CS2 RGB Sync.

Executa um loop próprio em frequência configurável (padrão 25 ms), desacoplado
das requisições HTTP do GSI, garantindo:
- Único ponto de envio de comandos para o controlador de hardware.
- Suavização temporal em transições contínuas e resposta imediata em pulsos curtos.
- Retenção de pico e decaimento suave para flashbang.
- LED completamente apagado (0, 0, 0) em idle quando efeitos permanentes estão desativados.
- Medição de latência entre recepção GSI, detecção de evento e envio ao SDK.
- Restauração automática da iluminação padrão ao desconectar ou encerrar.
"""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.effects import EffectInput, RGBColor, lerp_color, resolve_active_effect
from app.event_manager import EventType, GameEvent
from app.gsi_parser import GameStateSnapshot
from app.i18n import t
from app.icue_controller import RGBHardwareController
from app.logger import get_logger


@dataclass(frozen=True)
class LatencyMetrics:
    """Métricas de latência de software (não representa medição óptica do LED)."""

    last_gsi_received_ns: int = 0
    last_event_detected_ns: int = 0
    last_rgb_sent_ns: int = 0
    last_processing_ms: float = 0.0
    avg_processing_ms: float = 0.0
    max_processing_ms: float = 0.0
    last_sdk_call_ms: float = 0.0
    samples_count: int = 0


@dataclass(frozen=True)
class EngineRenderState:
    """Snapshot do estado visual e de desempenho do motor RGB."""

    running: bool = False
    paused: bool = False
    simulation_mode: bool = False
    active_effect_id: str = "idle"
    active_effect_label: str = "Waiting for game"
    current_color_hex: str = "#000000"
    current_rgb: tuple[int, int, int] = (0, 0, 0)
    tick_ms: int = 25
    frames_rendered: int = 0
    latency: LatencyMetrics = field(default_factory=LatencyMetrics)


class RGBEngine:
    """Motor independente de animação e prioridades RGB."""

    def __init__(
        self,
        controller: RGBHardwareController,
        config: dict[str, Any],
    ) -> None:
        self._logger = get_logger("rgb_engine")
        self._controller = controller
        self._state_lock = threading.RLock()
        self._config = copy.deepcopy(config)

        self._snapshot = GameStateSnapshot(connected=False)
        self._simulation_mode = bool(config.get("engine", {}).get("simulation_mode", False))
        self._shot_active_until_ns: int = 0
        self._bomb_planted_at_ns: Optional[int] = None

        self._flash_level: float = 0.0
        self._flash_target: float = 0.0
        self._flash_pending_peak: float = 0.0
        self._flash_episode_max_raw: int = 0
        self._flash_binary_mode: bool = False
        self._last_step_ns: int = 0
        self._last_logged_effect_id: str = ""
        self._last_logged_flash_level: float = 0.0

        self._current_color: Optional[RGBColor] = None
        self._active_effect_id: str = "idle"
        self._active_effect_label: str = t("engine.waiting_game")
        self._frames_rendered: int = 0

        self._paused: bool = False
        self._paused_at_ns: int = 0

        # Controle de latência de software
        self._pending_gsi_ns: int = 0
        self._pending_detected_ns: int = 0
        self._last_gsi_ns: int = 0
        self._last_detected_ns: int = 0
        self._last_rgb_sent_ns: int = 0
        self._last_processing_ms: float = 0.0
        self._sum_processing_ms: float = 0.0
        self._max_processing_ms: float = 0.0
        self._latency_samples: int = 0
        self._last_sdk_call_ms: float = 0.0

        self._running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def set_paused(self, paused: bool) -> None:
        """Pause or resume time progression cleanly without losing bomb/shot timers."""
        now_ns = time.perf_counter_ns()
        with self._state_lock:
            flag = bool(paused)
            if flag == self._paused:
                return
            if flag:
                self._paused = True
                self._paused_at_ns = now_ns
            else:
                delta_ns = max(0, now_ns - self._paused_at_ns) if self._paused_at_ns > 0 else 0
                if self._bomb_planted_at_ns is not None:
                    self._bomb_planted_at_ns += delta_ns
                if self._shot_active_until_ns > 0:
                    self._shot_active_until_ns += delta_ns
                self._last_step_ns = now_ns
                self._paused_at_ns = 0
                self._paused = False

    def is_paused(self) -> bool:
        with self._state_lock:
            return self._paused

    def reset_transient_state(self) -> None:
        """Clear transient flashbang/shot/C4 timers and rendered color state."""
        with self._state_lock:
            self._current_color = None
            self._shot_active_until_ns = 0
            self._bomb_planted_at_ns = None
            self._flash_level = 0.0
            self._flash_target = 0.0
            self._flash_pending_peak = 0.0
            self._flash_episode_max_raw = 0
            self._flash_binary_mode = False
            self._last_step_ns = 0
            self._last_logged_effect_id = ""
            self._last_logged_flash_level = 0.0
            self._active_effect_id = "idle"
            self._active_effect_label = (
                t("engine.waiting_game") if self._running else t("engine.stopped")
            )

    def refresh_labels(self) -> None:
        """Refresh active_effect_label after an active language switch."""
        with self._state_lock:
            running = self._running
            was_paused = self._paused
            snapshot = self._snapshot
        if running and not was_paused:
            self.step()
            return
        with self._state_lock:
            if not running:
                self._active_effect_label = t("engine.waiting_game")
            elif not snapshot.connected or snapshot.player_activity == "menu":
                self._active_effect_label = (
                    t("engine.cs2_menu") if snapshot.connected else t("engine.waiting_cs2")
                )
            elif self._active_effect_id == "idle":
                self._active_effect_label = t("engine.standby_led_off")

    def update_config(self, config: dict[str, Any]) -> None:
        """Atualiza configurações em tempo de execução de forma thread-safe."""
        with self._state_lock:
            self._config = copy.deepcopy(config)
            self._simulation_mode = bool(
                config.get("engine", {}).get("simulation_mode", False)
            )

    def update_state(
        self,
        snapshot: GameStateSnapshot,
        events: Optional[list[GameEvent]] = None,
        simulation_mode: Optional[bool] = None,
        now_ns: Optional[int] = None,
    ) -> None:
        """Atualiza o estado do jogo consumido pelo loop de renderização sem bloquear."""
        eval_now_ns = now_ns if now_ns is not None else time.perf_counter_ns()
        with self._state_lock:
            self._snapshot = snapshot
            if simulation_mode is not None:
                self._simulation_mode = bool(simulation_mode)

            if snapshot.last_update_ns > 0:
                self._pending_gsi_ns = snapshot.last_update_ns
                self._pending_detected_ns = eval_now_ns

            # Atualiza alvo de flashbang preservando picos breves e tratando escala binária (0 -> 1 -> 0)
            if not snapshot.connected or snapshot.player_activity == "menu":
                self._flash_level = 0.0
                self._flash_target = 0.0
                self._flash_pending_peak = 0.0
                self._flash_episode_max_raw = 0
                self._flash_binary_mode = False
                self._shot_active_until_ns = 0
                self._bomb_planted_at_ns = None
            elif not snapshot.is_local_player:
                self._flash_target = 0.0
            elif snapshot.flashed is not None and snapshot.flashed > 0:
                self._flash_episode_max_raw = max(
                    self._flash_episode_max_raw, snapshot.flashed
                )
                if (
                    snapshot.flashed == 1
                    and self._flash_episode_max_raw == 1
                    and snapshot.flashed_scale in ("int", "str_int")
                ):
                    self._flash_binary_mode = True
                    new_flash = 1.0
                else:
                    if snapshot.flashed > 1:
                        self._flash_binary_mode = False
                    new_flash = max(0, min(255, snapshot.flashed)) / 255.0
                self._flash_target = new_flash
                if new_flash > self._flash_pending_peak:
                    self._flash_pending_peak = new_flash
            else:
                self._flash_target = 0.0

            if events:
                shot_duration_ms = float(
                    self._config.get("effects", {})
                    .get("shot", {})
                    .get("duration_ms", 50)
                )
                shot_duration_ns = max(10, round(shot_duration_ms)) * 1_000_000

                for ev in events:
                    if ev.detected_at_ns > self._pending_detected_ns:
                        self._pending_detected_ns = ev.detected_at_ns
                    if ev.event_type == EventType.SHOT_FIRED:
                        base_ns = (
                            ev.received_at_ns
                            if now_ns is not None and ev.received_at_ns > 0
                            else max(eval_now_ns, ev.received_at_ns)
                        )
                        self._shot_active_until_ns = max(
                            self._shot_active_until_ns,
                            base_ns + shot_duration_ns,
                        )
                    elif ev.event_type == EventType.BOMB_PLANTED:
                        self._bomb_planted_at_ns = ev.data.get(
                            "planted_at_ns", ev.received_at_ns
                        )
                    elif ev.event_type in (
                        EventType.BOMB_DEFUSED,
                        EventType.BOMB_EXPLODED,
                        EventType.BOMB_CLEARED,
                    ):
                        self._bomb_planted_at_ns = None
                    elif (
                        ev.event_type == EventType.CONNECTION_CHANGED
                        and not ev.data.get("connected", False)
                    ):
                        self._bomb_planted_at_ns = None
                        self._shot_active_until_ns = 0
                        self._flash_level = 0.0
                        self._flash_target = 0.0
                        self._flash_pending_peak = 0.0
                        self._flash_episode_max_raw = 0
                        self._flash_binary_mode = False

            if snapshot.bomb_state == "planted" and self._bomb_planted_at_ns is None:
                self._bomb_planted_at_ns = snapshot.last_update_ns or eval_now_ns
            elif snapshot.bomb_state != "planted":
                self._bomb_planted_at_ns = None

    def get_render_state(self) -> EngineRenderState:
        with self._state_lock:
            rgb = self._current_color.to_tuple() if self._current_color else (0, 0, 0)
            hex_str = self._current_color.to_hex() if self._current_color else "#000000"
            avg_ms = (
                self._sum_processing_ms / self._latency_samples
                if self._latency_samples > 0
                else 0.0
            )
            tick_ms = self._get_tick_ms_locked()
            return EngineRenderState(
                running=self._running,
                paused=self._paused,
                simulation_mode=self._simulation_mode,
                active_effect_id=self._active_effect_id,
                active_effect_label=self._active_effect_label,
                current_color_hex=hex_str,
                current_rgb=rgb,
                tick_ms=tick_ms,
                frames_rendered=self._frames_rendered,
                latency=LatencyMetrics(
                    last_gsi_received_ns=self._last_gsi_ns,
                    last_event_detected_ns=self._last_detected_ns,
                    last_rgb_sent_ns=self._last_rgb_sent_ns,
                    last_processing_ms=self._last_processing_ms,
                    avg_processing_ms=avg_ms,
                    max_processing_ms=self._max_processing_ms,
                    last_sdk_call_ms=self._last_sdk_call_ms,
                    samples_count=self._latency_samples,
                ),
            )

    def _get_tick_ms_locked(self) -> int:
        raw = self._config.get("engine", {}).get("tick_ms", 25)
        try:
            return max(10, min(200, int(raw)))
        except (TypeError, ValueError):
            return 25

    def step(self, now_ns: Optional[int] = None) -> EngineRenderState:
        """Executa um passo único do motor de prioridades e envia a cor ao controlador."""
        eval_ns = now_ns if now_ns is not None else time.perf_counter_ns()

        with self._state_lock:
            if self._paused:
                return self.get_render_state()
            snapshot = self._snapshot
            config = self._config
            shot_until = self._shot_active_until_ns
            bomb_at = self._bomb_planted_at_ns
            prev_color = self._current_color
            prev_effect_id = self._active_effect_id
            pending_gsi = self._pending_gsi_ns
            pending_det = self._pending_detected_ns
            self._pending_gsi_ns = 0
            self._pending_detected_ns = 0

            dt_s = (
                max(0.005, (eval_ns - self._last_step_ns) / 1_000_000_000.0)
                if self._last_step_ns > 0 and eval_ns > self._last_step_ns
                else (self._get_tick_ms_locked() / 1000.0)
            )
            self._last_step_ns = eval_ns

            flash_rising = False
            if not snapshot.connected or snapshot.player_activity == "menu":
                self._flash_level = 0.0
                self._flash_target = 0.0
                self._flash_pending_peak = 0.0
                self._flash_episode_max_raw = 0
                self._flash_binary_mode = False
            elif self._flash_pending_peak > self._flash_level:
                self._flash_level = self._flash_pending_peak
                self._flash_pending_peak = 0.0
                flash_rising = True
            elif self._flash_target > self._flash_level:
                self._flash_level = self._flash_target
                self._flash_pending_peak = 0.0
                flash_rising = True
            elif self._flash_target == self._flash_level:
                self._flash_pending_peak = 0.0
            else:
                self._flash_pending_peak = 0.0
                flash_cfg = config.get("effects", {}).get("flashbang", {})
                fade_ms = (
                    float(flash_cfg.get("binary_fade_ms", 650))
                    if self._flash_binary_mode
                    else float(flash_cfg.get("fade_tail_ms", 220))
                )
                fade_tail_s = max(0.05, fade_ms / 1000.0)
                self._flash_level = max(
                    self._flash_target, self._flash_level - (dt_s / fade_tail_s)
                )
                if self._flash_level < 0.01 and self._flash_target == 0.0:
                    self._flash_level = 0.0
                    self._flash_episode_max_raw = 0
                    self._flash_binary_mode = False

            flash_level = self._flash_level
            binary_mode = self._flash_binary_mode

        ctx = EffectInput(
            snapshot=snapshot,
            now_ns=eval_ns,
            shot_active_until_ns=shot_until,
            bomb_planted_at_ns=bomb_at,
            config=config,
            flash_effective_level=flash_level,
            flash_rising=flash_rising,
        )
        result = resolve_active_effect(ctx)

        # Fora de partida ou desconectado: devolve controle padrão ao iCUE
        if not snapshot.connected or snapshot.player_activity == "menu":
            self._controller.restore_default()
            with self._state_lock:
                if prev_effect_id in ("flashbang", "fire", "c4", "team_round") and self._last_logged_effect_id != "idle":
                    self._logger.info(
                        "RGBEngine decisão: efeito=idle (anterior=%s) | fora de partida/desconectado -> controle devolvido ao iCUE",
                        prev_effect_id,
                    )
                    self._last_logged_effect_id = "idle"
                    self._last_logged_flash_level = 0.0
                self._current_color = None
                self._active_effect_id = "idle"
                self._active_effect_label = (
                    t("engine.cs2_menu") if snapshot.connected else t("engine.waiting_cs2")
                )
                self._frames_rendered += 1
            return self.get_render_state()

        # Em partida sem efeito ativo (idle): apaga explicitamente o LED (0, 0, 0)
        if result is None:
            if not self._controller.is_connected():
                self._controller.poll_recovery()
            if self._controller.is_connected():
                self._controller.set_color(0, 0, 0, 255)
            with self._state_lock:
                if prev_effect_id in ("flashbang", "fire", "c4", "team_round") and self._last_logged_effect_id != "idle":
                    self._logger.info(
                        "RGBEngine decisão: efeito=idle (anterior=%s) | cor=#000000 | flashed=%s (raw=%r/%s)",
                        prev_effect_id,
                        snapshot.flashed,
                        snapshot.flashed_raw,
                        snapshot.flashed_raw_type,
                    )
                    self._last_logged_effect_id = "idle"
                    self._last_logged_flash_level = 0.0
                self._current_color = RGBColor(0, 0, 0)
                self._active_effect_id = "idle"
                self._active_effect_label = t("engine.standby_led_off")
                self._frames_rendered += 1
            return self.get_render_state()

        global_brightness = float(
            config.get("hardware", {}).get("global_brightness", 100)
        )
        global_factor = max(0.0, min(100.0, global_brightness)) / 100.0
        target_color = result.color.scale(global_factor)

        if prev_color is None or result.instant:
            rendered_color = target_color
        else:
            rendered_color = lerp_color(prev_color, target_color, 0.45)

        if not self._controller.is_connected():
            self._controller.poll_recovery()

        sent_ok = False
        if self._controller.is_connected():
            sent_ok = self._controller.set_color(
                rendered_color.r, rendered_color.g, rendered_color.b, 255
            )
        sent_ns = time.perf_counter_ns()
        sdk_status = self._controller.get_status()

        with self._state_lock:
            should_log_decision = (
                result.effect_id != self._last_logged_effect_id
                and (
                    result.effect_id in ("flashbang", "fire", "c4", "team_round")
                    or self._last_logged_effect_id in ("flashbang", "fire", "c4", "team_round")
                )
            ) or (
                result.effect_id == "flashbang"
                and abs(flash_level - self._last_logged_flash_level) >= 0.20
            )
            if should_log_decision:
                self._logger.info(
                    "RGBEngine decisão: efeito=%s (anterior=%s) | cor=%s | flashed=%s (raw=%r/%s) | flash_lvl=%.3f | binary=%s",
                    result.effect_id,
                    prev_effect_id,
                    rendered_color.to_hex(),
                    snapshot.flashed,
                    snapshot.flashed_raw,
                    snapshot.flashed_raw_type,
                    flash_level,
                    binary_mode,
                )
                self._last_logged_effect_id = result.effect_id
                self._last_logged_flash_level = flash_level
            self._current_color = rendered_color
            self._active_effect_id = result.effect_id
            self._active_effect_label = result.label
            self._frames_rendered += 1
            self._last_sdk_call_ms = sdk_status.last_sdk_call_ms
            if sent_ok and pending_gsi > 0:
                self._last_gsi_ns = pending_gsi
                self._last_detected_ns = pending_det
                self._last_rgb_sent_ns = sent_ns
                proc_ms = max(0.0, (sent_ns - pending_gsi) / 1_000_000.0)
                self._last_processing_ms = proc_ms
                self._sum_processing_ms += proc_ms
                self._max_processing_ms = max(self._max_processing_ms, proc_ms)
                self._latency_samples += 1

        return self.get_render_state()

    def start(self) -> None:
        """Inicia a thread independente do motor RGB."""
        with self._state_lock:
            if self._running:
                return
            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(
                target=self._run_loop,
                name="CS2RGBSync-RGBEngine",
                daemon=True,
            )
            self._thread.start()
            self._logger.info(
                "Motor RGB iniciado (tick=%d ms).", self._get_tick_ms_locked()
            )

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            t0 = time.perf_counter()
            try:
                self.step()
            except Exception:
                self._logger.exception("Erro no ciclo de renderização do motor RGB")

            with self._state_lock:
                tick_s = self._get_tick_ms_locked() / 1000.0
            elapsed = time.perf_counter() - t0
            sleep_s = max(0.002, tick_s - elapsed)
            self._stop_event.wait(timeout=sleep_s)

    def stop(self, release_controller: bool = True) -> None:
        """Para o motor RGB e restaura a iluminação padrão se configurado."""
        with self._state_lock:
            thread = self._thread
            self._running = False
            self._stop_event.set()
            restore_on_exit = bool(
                self._config.get("hardware", {}).get("restore_on_exit", True)
            )

        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)

        with self._state_lock:
            self._thread = None
            self._current_color = None
            self._shot_active_until_ns = 0
            self._bomb_planted_at_ns = None
            self._flash_level = 0.0
            self._flash_target = 0.0
            self._flash_pending_peak = 0.0
            self._flash_episode_max_raw = 0
            self._flash_binary_mode = False
            self._last_logged_effect_id = ""
            self._last_logged_flash_level = 0.0
            self._active_effect_id = "idle"
            self._active_effect_label = t("engine.stopped")
            self._paused = False
            self._paused_at_ns = 0

        if release_controller:
            if restore_on_exit:
                self._controller.release_and_disconnect()
        elif restore_on_exit:
            self._controller.restore_default()
        self._logger.info("Motor RGB encerrado.")
