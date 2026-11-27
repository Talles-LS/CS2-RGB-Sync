"""
Serviço orquestrador desacoplado do CS2 RGB Sync.

Conecta `ConfigManager`, `GSIServer`, `GSIParser`, `EventManager`, `RGBEngine`,
`ICueController` e `GSISimulator` em uma fachada thread-safe, sem qualquer
dependência do Qt, permitindo que a interface PySide6 apenas consulte snapshots
e envie comandos assíncronos sem bloquear rede ou hardware.
"""

from __future__ import annotations

import copy
import json
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from app.config_manager import ConfigManager
from app.event_manager import EventManager, GameEvent
from app.gsi_config import detect_cs2_game_dir, install_gsi_cfg
from app.gsi_parser import GSIParser, GameStateSnapshot
from app.gsi_server import GSIServer, GSIServerStats
from app.icue_controller import (
    ICueController,
    ICueStatusSnapshot,
    RGBHardwareController,
    is_icue_process_running,
)
from app.logger import get_logger, get_ring_buffer_handler
from app.rgb_engine import EngineRenderState, RGBEngine
from app.simulator import GSISimulator
from app.windows_startup import set_windows_startup


@dataclass(frozen=True)
class EventLogItem:
    """Entrada resumida de evento detectado para exibição no diagnóstico."""

    timestamp_str: str
    event_type: str
    summary: str
    simulation: bool


@dataclass(frozen=True)
class ServiceSnapshot:
    """Fotografia completa do estado do aplicativo para atualização da UI."""

    integration_running: bool
    simulation_mode: bool
    icue_status: ICueStatusSnapshot
    server_stats: GSIServerStats
    game_state: GameStateSnapshot
    render_state: EngineRenderState
    last_payload: Optional[dict[str, Any]]
    recent_events: tuple[EventLogItem, ...]
    recent_logs: str
    last_service_error: str


class SyncService:
    """Orquestra ciclo de vida do servidor GSI, eventos, motor RGB e simulação."""

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        controller: Optional[RGBHardwareController] = None,
        controller_factory: Optional[Callable[[dict[str, Any]], RGBHardwareController]] = None,
        port_override: Optional[int] = None,
    ) -> None:
        self._logger = get_logger("sync_service")
        self._config_mgr = config_manager or ConfigManager()
        self._port_override = port_override

        self._lifecycle_lock = threading.RLock()
        self._data_lock = threading.RLock()

        cfg = self._config_mgr.get_all()
        if controller is not None:
            self._controller: RGBHardwareController = controller
        elif controller_factory is not None:
            self._controller = controller_factory(cfg)
        else:
            self._controller = self._build_default_controller(cfg)

        self._parser = GSIParser()
        self._event_mgr = self._build_event_manager(cfg)
        self._engine = RGBEngine(controller=self._controller, config=cfg)
        self._simulator = GSISimulator()
        self._sim_parser = GSIParser()
        self._sim_event_mgr = self._build_event_manager(cfg)

        self._server: Optional[GSIServer] = None
        self._consumer_thread: Optional[threading.Thread] = None
        self._consumer_stop = threading.Event()
        self._integration_running = False
        self._simulation_mode = bool(cfg.get("engine", {}).get("simulation_mode", False))

        self._latest_snapshot = GameStateSnapshot(connected=False)
        self._recent_events: deque[EventLogItem] = deque(maxlen=80)
        self._last_payload: Optional[dict[str, Any]] = None
        self._last_service_error: str = ""

    @staticmethod
    def _build_default_controller(cfg: dict[str, Any]) -> ICueController:
        hw = cfg.get("hardware", {})
        return ICueController(
            sdk_path=hw.get("sdk_path") or None,
            target_model=str(hw.get("target_model", "")),
            layer_priority=int(hw.get("layer_priority", 200)),
            exclusive_control=bool(hw.get("exclusive_control", False)),
        )

    @staticmethod
    def _build_event_manager(cfg: dict[str, Any]) -> EventManager:
        effects = cfg.get("effects", {})
        gsi = cfg.get("gsi", {})
        return EventManager(
            shot_debounce_ms=float(effects.get("shot", {}).get("debounce_ms", 40.0)),
            critical_health_threshold=int(
                effects.get("health", {}).get("critical_threshold", 25)
            ),
            disconnect_timeout_s=float(gsi.get("disconnect_timeout_s", 35.0)),
            fire_enabled=bool(effects.get("fire", {}).get("enabled", True)),
        )

    @property
    def config_manager(self) -> ConfigManager:
        return self._config_mgr

    def get_config(self) -> dict[str, Any]:
        return self._config_mgr.get_all()

    def start_integration(self) -> tuple[bool, str]:
        """Inicia servidor GSI, conecta iCUE (sem falhar se ausente) e liga o motor RGB."""
        with self._lifecycle_lock:
            if self._integration_running:
                return True, "Integração já está em execução."

            cfg = self._config_mgr.get_all()
            port = (
                self._port_override
                if self._port_override is not None
                else int(cfg["server"]["port"])
            )
            token = str(cfg["server"]["token"])

            try:
                server = GSIServer(host="127.0.0.1", port=port, auth_token=token)
                active_port = server.start()
            except Exception as exc:
                msg = f"Falha ao iniciar servidor GSI na porta {port}: {exc}"
                with self._data_lock:
                    self._last_service_error = msg
                self._logger.error(msg)
                return False, msg

            self._server = server
            self._parser.reset()
            self._event_mgr = self._build_event_manager(cfg)
            self._engine.update_config(cfg)

            if not self._controller.is_connected():
                self._controller.connect(timeout_s=2.5)

            self._engine.start()

            self._consumer_stop.clear()
            self._consumer_thread = threading.Thread(
                target=self._consume_gsi_loop,
                name="CS2RGBSync-EventConsumer",
                daemon=True,
            )
            self._consumer_thread.start()
            self._integration_running = True
            with self._data_lock:
                self._last_service_error = ""

            hw_ok = self._controller.is_connected()
            info_msg = (
                f"Integração ativa em http://127.0.0.1:{active_port}/ "
                f"({'dispositivo conectado' if hw_ok else 'aguardando iCUE/dispositivo'})"
            )
            self._logger.info(info_msg)
            return True, info_msg

    def stop_integration(self) -> None:
        """Para consumidor, servidor HTTP e motor RGB devolvendo controle ao iCUE."""
        with self._lifecycle_lock:
            self._consumer_stop.set()
            consumer = self._consumer_thread
            server = self._server

            if consumer is not None and consumer.is_alive():
                consumer.join(timeout=2.0)
            self._consumer_thread = None

            if server is not None:
                server.stop()
            self._server = None

            self._engine.stop(release_controller=True)
            self._integration_running = False
            with self._data_lock:
                self._latest_snapshot = GameStateSnapshot(connected=False)

    def _consume_gsi_loop(self) -> None:
        last_activity: Optional[str] = None
        last_raw_flashed: Any = None
        last_raw_burning: Any = None
        while not self._consumer_stop.is_set():
            server = self._server
            if server is None:
                break
            try:
                msg = server.event_queue.get(timeout=0.1)
                with self._data_lock:
                    sim_active = self._simulation_mode
                    self._last_payload = msg.payload
                if sim_active:
                    continue

                raw_payload = msg.payload if isinstance(msg.payload, dict) else {}
                raw_player = (
                    raw_payload.get("player")
                    if isinstance(raw_payload.get("player"), dict)
                    else {}
                )
                raw_state = (
                    raw_player.get("state")
                    if isinstance(raw_player.get("state"), dict)
                    else {}
                )
                raw_prev = (
                    raw_payload.get("previously")
                    if isinstance(raw_payload.get("previously"), dict)
                    else raw_payload.get("previous")
                )
                raw_prev_player = (
                    raw_prev.get("player")
                    if isinstance(raw_prev, dict) and isinstance(raw_prev.get("player"), dict)
                    else {}
                )
                raw_prev_state = (
                    raw_prev_player.get("state")
                    if isinstance(raw_prev_player.get("state"), dict)
                    else {}
                )

                snap = self._parser.parse(
                    msg.payload,
                    received_at_ns=msg.received_at_ns,
                    received_at_wall=msg.received_at_wall,
                )
                events = self._event_mgr.process_snapshot(snap)

                has_diag_event = any(
                    ev.event_type.value
                    in (
                        "flashbang_changed",
                        "fire_changed",
                        "bomb_planted",
                        "bomb_defused",
                        "bomb_exploded",
                        "bomb_cleared",
                    )
                    for ev in events
                )
                flashed_in_raw = "flashed" in raw_state
                burning_in_raw = "burning" in raw_state
                raw_flash_val = raw_state.get("flashed") if flashed_in_raw else None
                raw_burn_val = raw_state.get("burning") if burning_in_raw else None
                raw_flash_changed = flashed_in_raw and raw_flash_val != last_raw_flashed
                raw_burn_changed = burning_in_raw and raw_burn_val != last_raw_burning
                activity_changed = snap.player_activity != last_activity

                if (
                    has_diag_event
                    or raw_flash_changed
                    or raw_burn_changed
                    or "flashed" in raw_prev_state
                    or "burning" in raw_prev_state
                    or activity_changed
                ):
                    self._logger.info(
                        "GSI diagnóstico -> payload_state_keys=%s | flashed_raw=%r(%s) | "
                        "burning_raw=%r | prev_state_keys=%s | activity=%s | local_player=%s | "
                        "parser=(flashed=%s, scale=%s, burning=%s, bomb=%s)",
                        sorted(raw_state.keys()),
                        raw_flash_val,
                        type(raw_flash_val).__name__ if flashed_in_raw else "absent",
                        raw_burn_val,
                        sorted(raw_prev_state.keys()),
                        snap.player_activity,
                        snap.is_local_player,
                        snap.flashed,
                        snap.flashed_scale,
                        snap.burning,
                        snap.bomb_state,
                    )

                if flashed_in_raw:
                    last_raw_flashed = raw_flash_val
                if burning_in_raw:
                    last_raw_burning = raw_burn_val
                last_activity = snap.player_activity

                for ev in events:
                    if ev.event_type.value in (
                        "flashbang_changed",
                        "fire_changed",
                        "bomb_planted",
                        "bomb_defused",
                        "bomb_exploded",
                        "bomb_cleared",
                    ):
                        self._logger.info("GSI evento %s -> %s", ev.event_type.value, ev.data)
                self._engine.update_state(snap, events, simulation_mode=False)
                self._record_events(snap, events, simulation=False)
            except queue.Empty:
                with self._data_lock:
                    sim_active = self._simulation_mode
                if sim_active:
                    continue
                timeout_events = self._event_mgr.check_timeout()
                if timeout_events:
                    disc_snap = self._parser.mark_disconnected()
                    self._engine.update_state(
                        disc_snap, timeout_events, simulation_mode=False
                    )
                    self._record_events(disc_snap, timeout_events, simulation=False)
            except Exception as exc:
                self._logger.exception("Erro no consumidor de eventos GSI")
                with self._data_lock:
                    self._last_service_error = f"Erro no consumidor GSI: {exc}"

    def _record_events(
        self,
        snap: GameStateSnapshot,
        events: list[GameEvent],
        *,
        simulation: bool,
    ) -> None:
        ts_str = time.strftime("%H:%M:%S")
        with self._data_lock:
            self._latest_snapshot = snap
            for ev in events:
                summary = ", ".join(f"{k}={v}" for k, v in ev.data.items())
                self._recent_events.appendleft(
                    EventLogItem(
                        timestamp_str=ts_str,
                        event_type=ev.event_type.value,
                        summary=summary or "-",
                        simulation=simulation,
                    )
                )

    def set_simulation_mode(self, enabled: bool) -> None:
        """Ativa ou desativa explicitamente o modo de simulação."""
        flag = bool(enabled)
        with self._data_lock:
            self._simulation_mode = flag
            self._config_mgr.set("engine.simulation_mode", flag)
            if not flag:
                self._sim_parser.reset()
                self._sim_event_mgr.reset()
                self._latest_snapshot = self._parser.current_state
                self._engine.update_state(
                    self._parser.current_state, [], simulation_mode=False
                )
            else:
                self._engine.update_state(
                    self._sim_parser.current_state, [], simulation_mode=True
                )

    def trigger_simulation(self, action: str, **kwargs: Any) -> None:
        """Dispara um estado ou evento simulado sem misturá-lo com dados reais."""
        with self._data_lock:
            if not self._simulation_mode:
                self._simulation_mode = True
                self._config_mgr.set("engine.simulation_mode", True)

            if action == "flashbang":
                payload = self._simulator.set_flashed(int(kwargs.get("intensity", 255)))
            elif action == "shot":
                payload = self._simulator.trigger_shot()
            elif action == "c4_planted":
                payload = self._simulator.set_bomb("planted")
            elif action == "c4_defused":
                payload = self._simulator.set_bomb("defused")
            elif action == "c4_exploded":
                payload = self._simulator.set_bomb("exploded")
            elif action == "fire":
                payload = self._simulator.set_burning(int(kwargs.get("intensity", 180)))
            elif action == "health":
                payload = self._simulator.set_health(int(kwargs.get("health", 100)))
            elif action == "team":
                payload = self._simulator.set_team(str(kwargs.get("team", "CT")))
            elif action == "freezetime":
                payload = self._simulator.set_round_phase("freezetime")
            elif action == "live":
                payload = self._simulator.set_round_phase("live")
            elif action == "weapon":
                payload = self._simulator.select_weapon(str(kwargs.get("category", "rifle")))
            elif action == "disconnect":
                self._sim_parser.reset()
                self._sim_event_mgr.reset()
                disc = GameStateSnapshot(connected=False)
                self._latest_snapshot = disc
                self._engine.update_state(disc, [], simulation_mode=True)
                return
            else:
                raise ValueError(f"Ação de simulação desconhecida: {action}")

            self._last_payload = payload
            snap = self._sim_parser.parse(
                payload,
                received_at_ns=time.perf_counter_ns(),
                received_at_wall=time.time(),
            )
            events = self._sim_event_mgr.process_snapshot(snap)

        if self._integration_running and not self._controller.is_connected():
            self._controller.connect(timeout_s=1.0)
        self._engine.update_state(snap, events, simulation_mode=True)
        self._record_events(snap, events, simulation=True)
        if not self._integration_running:
            self._engine.step()

    def apply_config(
        self,
        new_config: dict[str, Any],
        *,
        apply_windows_startup: bool = False,
    ) -> tuple[bool, str]:
        """Valida, persiste e aplica novas configurações em tempo de execução."""
        try:
            old_port = int(self._config_mgr.get("server.port", 3000))
            saved = self._config_mgr.update(new_config, save_now=True)
        except Exception as exc:
            return False, f"Configuração inválida: {exc}"

        new_port = int(saved["server"]["port"])
        hw = saved.get("hardware", {})
        if isinstance(self._controller, ICueController):
            self._controller.configure(
                sdk_path=hw.get("sdk_path") or None,
                target_model=str(hw.get("target_model", "")),
                layer_priority=int(hw.get("layer_priority", 200)),
                exclusive_control=bool(hw.get("exclusive_control", False)),
            )

        self._engine.update_config(saved)
        effects = saved.get("effects", {})
        gsi = saved.get("gsi", {})
        self._event_mgr.shot_debounce_ms = float(
            effects.get("shot", {}).get("debounce_ms", 40.0)
        )
        self._event_mgr.critical_health_threshold = int(
            effects.get("health", {}).get("critical_threshold", 25)
        )
        self._event_mgr.disconnect_timeout_s = float(
            gsi.get("disconnect_timeout_s", 35.0)
        )
        self._event_mgr.fire_enabled = bool(effects.get("fire", {}).get("enabled", True))

        with self._data_lock:
            self._simulation_mode = bool(
                saved.get("engine", {}).get("simulation_mode", False)
            )

        if apply_windows_startup:
            set_windows_startup(bool(saved.get("ui", {}).get("start_with_windows", False)))

        with self._lifecycle_lock:
            if self._integration_running and self._server is not None:
                self._server.update_token(str(saved["server"]["token"]))
                if new_port != old_port and self._port_override is None:
                    self._server.stop()
                    try:
                        self._server = GSIServer(
                            host="127.0.0.1",
                            port=new_port,
                            auth_token=str(saved["server"]["token"]),
                        )
                        self._server.start()
                    except Exception as exc:
                        return False, f"Configuração salva, mas falha ao reiniciar porta {new_port}: {exc}"

        return True, "Configurações salvas e aplicadas com sucesso."

    def restore_default_settings(self) -> dict[str, Any]:
        """Restaura padrões de `default_config.json`, preservando token e caminho do CS2."""
        current = self._config_mgr.get_all()
        defaults = json.loads(
            self._config_mgr.default_config_path.read_text(encoding="utf-8")
        )
        defaults["server"]["token"] = current["server"]["token"]
        defaults["gsi"]["cs2_path"] = current["gsi"].get("cs2_path", "")
        self.apply_config(defaults, apply_windows_startup=False)
        return self._config_mgr.get_all()

    def detect_cs2_path(self) -> Optional[Path]:
        """Tenta detectar automaticamente a pasta `game\\csgo` do CS2."""
        preferred = self._config_mgr.get("gsi.cs2_path") or None
        detected = detect_cs2_game_dir(preferred_path=preferred)
        if detected is not None:
            self._config_mgr.set("gsi.cs2_path", str(detected))
        return detected

    def install_gsi_file(self, cs2_path: Optional[str] = None) -> tuple[bool, str]:
        """Instala ou atualiza `gamestate_integration_cs2rgbsync.cfg` no CS2."""
        cfg = self._config_mgr.get_all()
        candidate = cs2_path or cfg["gsi"].get("cs2_path") or None
        detected = detect_cs2_game_dir(preferred_path=candidate)
        if detected is None:
            return (
                False,
                "Pasta válida do CS2 (game\\csgo\\cfg) não encontrada. Selecione manualmente.",
            )
        try:
            self._config_mgr.set("gsi.cs2_path", str(detected))
            target = install_gsi_cfg(
                cs2_game_dir=detected,
                port=int(cfg["server"]["port"]),
                token=str(cfg["server"]["token"]),
                buffer=float(cfg["gsi"]["buffer"]),
                throttle=float(cfg["gsi"]["throttle"]),
                timeout=float(cfg["gsi"]["timeout"]),
                heartbeat=float(cfg["gsi"]["heartbeat"]),
            )
            return True, f"Arquivo GSI instalado em: {target}"
        except Exception as exc:
            return False, f"Erro ao instalar arquivo GSI: {exc}"

    def regenerate_token_and_reinstall(self) -> tuple[bool, str]:
        """Gera novo token GSI, atualiza servidor ativo e reinstala o `.cfg` se possível."""
        new_token = self._config_mgr.regenerate_token(save_now=True)
        with self._lifecycle_lock:
            if self._server is not None:
                self._server.update_token(new_token)
        cs2_path = self._config_mgr.get("gsi.cs2_path") or None
        if cs2_path:
            ok, msg = self.install_gsi_file(cs2_path)
            if ok:
                return True, f"Novo token gerado e arquivo GSI atualizado ({msg})."
            return True, f"Novo token gerado, mas atualize o arquivo GSI manualmente: {msg}"
        return True, "Novo token gerado e salvo localmente."

    def get_ui_snapshot(self) -> ServiceSnapshot:
        """Retorna um retrato completo e thread-safe para renderização na UI."""
        icue_status = self._controller.get_status()
        if not self._integration_running and not icue_status.icue_process_running:
            # Garante detecção do processo iCUE mesmo antes de iniciar integração
            running_icue = is_icue_process_running()
            if running_icue != icue_status.icue_process_running:
                icue_status = ICueStatusSnapshot(
                    icue_process_running=running_icue,
                    sdk_connected=icue_status.sdk_connected,
                    session_state=icue_status.session_state,
                    device_found=icue_status.device_found,
                    device_connected=icue_status.device_connected,
                    device_model=icue_status.device_model,
                    device_id=icue_status.device_id,
                    led_ids=icue_status.led_ids,
                    last_rgba=icue_status.last_rgba,
                    last_error=icue_status.last_error,
                    commands_sent=icue_status.commands_sent,
                    commands_skipped=icue_status.commands_skipped,
                    last_sdk_call_ms=icue_status.last_sdk_call_ms,
                )

        if self._server is not None:
            server_stats = self._server.get_stats()
        else:
            cfg = self._config_mgr.get_all()
            server_stats = GSIServerStats(
                running=False,
                host="127.0.0.1",
                port=int(cfg["server"]["port"]),
                requests_received=0,
                requests_accepted=0,
                auth_failures=0,
                parse_errors=0,
                dropped_events=0,
                queue_size=0,
                last_received_at=None,
                last_error="",
            )

        render_state = self._engine.get_render_state()
        logs_text = get_ring_buffer_handler().get_text()

        with self._data_lock:
            return ServiceSnapshot(
                integration_running=self._integration_running,
                simulation_mode=self._simulation_mode,
                icue_status=icue_status,
                server_stats=server_stats,
                game_state=self._latest_snapshot,
                render_state=render_state,
                last_payload=copy.deepcopy(self._last_payload),
                recent_events=tuple(self._recent_events),
                recent_logs=logs_text,
                last_service_error=self._last_service_error,
            )

    def shutdown(self) -> None:
        """Encerra todo o serviço com segurança ao fechar o aplicativo."""
        self.stop_integration()
