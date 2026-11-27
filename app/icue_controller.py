"""
Controlador de hardware Corsair iCUE SDK v4 para o CS2 RGB Sync.

Integra-se a dispositivos Corsair compatíveis com RGB via `cuesdk==4.0.84`
(`iCUESDK.x64_2019.dll`), utilizando seleção automática ou filtro opcional por modelo.

Garantias:
- Serializa todas as chamadas ao SDK com `threading.RLock()`.
- Nunca modifica configurações, macros ou perfis do hardware no iCUE.
- Detecta desconexão/reconexão do iCUE e do dispositivo e tenta recuperação.
- Aplica o workaround validado de desconexão segura (mantendo referências de
  callbacks C até após `CorsairDisconnect()` para evitar crash `0xC000001D`).
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Optional, Protocol

import psutil
from cuesdk import (
    CorsairAccessLevel,
    CorsairDeviceFilter,
    CorsairDeviceInfo,
    CorsairDeviceType,
    CorsairError,
    CorsairEvent,
    CorsairEventId,
    CorsairLedColor,
    CorsairSessionState,
    CorsairSessionStateChanged,
    CueSdk,
)

from app.i18n import t
from app.logger import get_logger


@dataclass(frozen=True)
class ICueStatusSnapshot:
    """Estado atual da comunicação com o iCUE e com o periférico Corsair."""

    icue_process_running: bool
    sdk_connected: bool
    session_state: str
    device_found: bool
    device_connected: bool
    device_model: str
    device_id: str
    led_ids: tuple[int, ...]
    last_rgba: Optional[tuple[int, int, int, int]]
    last_error: str
    commands_sent: int
    commands_skipped: int
    last_sdk_call_ms: float


class RGBHardwareController(Protocol):
    """Interface comum para controladores de hardware real ou simulado/teste."""

    def is_connected(self) -> bool: ...

    def connect(self, timeout_s: float = 5.0) -> bool: ...

    def poll_recovery(self) -> bool: ...

    def set_color(
        self, r: int, g: int, b: int, a: int = 255, force: bool = False
    ) -> bool: ...

    def restore_default(self) -> bool: ...

    def release_and_disconnect(self) -> None: ...

    def get_status(self) -> ICueStatusSnapshot: ...


def is_icue_process_running() -> bool:
    """Verifica se algum processo do Corsair iCUE está em execução no Windows."""
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info.get("name") or ""
            if "icue" in name.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


class ICueController:
    """Controlador thread-safe para iluminação RGB de dispositivos Corsair via iCUE SDK v4."""

    def __init__(
        self,
        sdk_path: Optional[str] = None,
        target_model: str = "",
        layer_priority: int = 200,
        exclusive_control: bool = False,
        recovery_cooldown_s: float = 2.0,
    ) -> None:
        self._logger = get_logger("icue")
        self._lock = threading.RLock()
        self._cb_lock = threading.Lock()

        self._sdk_path = sdk_path.strip() if isinstance(sdk_path, str) and sdk_path.strip() else None
        self._target_model = (target_model or "").strip()
        self._layer_priority = max(0, min(255, int(layer_priority)))
        self._exclusive_control = bool(exclusive_control)
        self._recovery_cooldown_s = max(0.5, float(recovery_cooldown_s))

        self._sdk: Optional[CueSdk] = None
        self._session_state = CorsairSessionState.CSS_Closed
        self._session_connected = threading.Event()
        self._session_terminal = threading.Event()
        self._session_handler_ref = None
        self._event_handler_ref = None

        self._device_id: str = ""
        self._device_model: str = ""
        self._device_connected: bool = False
        self._needs_rediscover: bool = False
        self._led_ids: tuple[int, ...] = ()

        self._last_rgba: Optional[tuple[int, int, int, int]] = None
        self._last_error: str = ""
        self._commands_sent: int = 0
        self._commands_skipped: int = 0
        self._last_sdk_call_ms: float = 0.0
        self._last_recovery_attempt: float = 0.0
        self._control_active: bool = False

    def configure(
        self,
        *,
        sdk_path: Optional[str] = None,
        target_model: Optional[str] = None,
        layer_priority: Optional[int] = None,
        exclusive_control: Optional[bool] = None,
    ) -> None:
        """Atualiza parâmetros de configuração sem alterar perfis do hardware."""
        with self._lock:
            if sdk_path is not None:
                self._sdk_path = sdk_path.strip() or None
            if target_model is not None:
                self._target_model = target_model.strip()
            if layer_priority is not None:
                self._layer_priority = max(0, min(255, int(layer_priority)))
                if self._sdk and self._session_state == CorsairSessionState.CSS_Connected:
                    self._sdk.set_layer_priority(self._layer_priority)
            if exclusive_control is not None:
                self._exclusive_control = bool(exclusive_control)

    def is_connected(self) -> bool:
        with self._lock:
            with self._cb_lock:
                session_state = self._session_state
                dev_connected = self._device_connected
                needs_rediscover = self._needs_rediscover
            if needs_rediscover and session_state == CorsairSessionState.CSS_Connected:
                with self._cb_lock:
                    self._needs_rediscover = False
                self._discover_device_locked()
                with self._cb_lock:
                    dev_connected = self._device_connected
            return (
                self._sdk is not None
                and session_state == CorsairSessionState.CSS_Connected
                and bool(self._device_id)
                and dev_connected
                and bool(self._led_ids)
            )

    def _ensure_sdk_loaded(self) -> bool:
        if self._sdk is not None:
            return True
        if self._sdk_path and not os.path.isfile(self._sdk_path):
            self._last_error = t("errors.icue_dll_not_found", path=self._sdk_path)
            self._logger.error(self._last_error)
            return False
        try:
            self._sdk = CueSdk(sdk_path=self._sdk_path)
            return True
        except Exception as exc:
            self._last_error = t("errors.icue_sdk_load_failed", exc=exc)
            self._logger.error(self._last_error)
            self._sdk = None
            return False

    def _on_session_state_changed(self, evt: CorsairSessionStateChanged) -> None:
        with self._cb_lock:
            self._session_state = evt.state
            if evt.state == CorsairSessionState.CSS_Connected:
                self._last_error = ""
                self._session_connected.set()
            elif evt.state in (
                CorsairSessionState.CSS_Timeout,
                CorsairSessionState.CSS_ConnectionRefused,
                CorsairSessionState.CSS_ConnectionLost,
                CorsairSessionState.CSS_Closed,
            ):
                if evt.state == CorsairSessionState.CSS_ConnectionRefused:
                    self._last_error = t("errors.icue_refused")
                elif evt.state == CorsairSessionState.CSS_ConnectionLost:
                    self._last_error = t("errors.icue_lost")
                elif evt.state == CorsairSessionState.CSS_Timeout:
                    self._last_error = t("errors.icue_timeout")
                self._device_connected = False
                self._last_rgba = None
                self._session_terminal.set()

    def _on_sdk_event(self, evt: CorsairEvent) -> None:
        if evt.id != CorsairEventId.CEI_DeviceConnectionStatusChangedEvent:
            return
        data = evt.data
        with self._cb_lock:
            if self._device_id and data.device_id == self._device_id:
                self._device_connected = bool(data.is_connected)
                self._last_rgba = None
                if data.is_connected:
                    self._needs_rediscover = True
                else:
                    self._last_error = t(
                        "errors.icue_device_disconnected", model=self._device_model
                    )
            elif data.is_connected and not self._device_id:
                self._needs_rediscover = True

    def connect(self, timeout_s: float = 5.0) -> bool:
        """Inicializa o iCUE SDK, localiza um dispositivo Corsair compatível e consulta seus LEDs."""
        with self._lock:
            if self.is_connected():
                return True
            if not self._ensure_sdk_loaded():
                return False
            assert self._sdk is not None

            if self._session_state != CorsairSessionState.CSS_Connected:
                self._session_connected.clear()
                self._session_terminal.clear()
                err = self._sdk.connect(self._on_session_state_changed)
                self._session_handler_ref = getattr(
                    self._sdk, "session_state_changed_event_handler", None
                )
                if err != CorsairError.CE_Success:
                    self._last_error = t("errors.icue_connect_failed", err=err)
                    self._logger.warning(self._last_error)
                    return False

                deadline = time.monotonic() + max(0.2, timeout_s)
                while time.monotonic() < deadline:
                    if self._session_connected.is_set():
                        break
                    if self._session_terminal.is_set():
                        return False
                    # Libera o lock brevemente enquanto aguarda o callback do SDK
                    self._lock.release()
                    try:
                        self._session_connected.wait(timeout=0.05)
                    finally:
                        self._lock.acquire()

                if self._session_state != CorsairSessionState.CSS_Connected:
                    if not self._last_error:
                        self._last_error = t(
                            "errors.icue_connect_timeout", state=self._session_state
                        )
                    return False

            sub_err = self._sdk.subscribe_for_events(self._on_sdk_event)
            self._event_handler_ref = getattr(self._sdk, "event_handler", None)
            if sub_err != CorsairError.CE_Success:
                self._logger.debug("subscribe_for_events retornou %s", sub_err)

            return self._discover_device_locked()

    def _discover_device_locked(self) -> bool:
        if self._sdk is None or self._session_state != CorsairSessionState.CSS_Connected:
            return False

        devices, dev_err = self._sdk.get_devices(
            CorsairDeviceFilter(device_type_mask=CorsairDeviceType.CDT_All)
        )
        if dev_err != CorsairError.CE_Success or not devices:
            self._device_id = ""
            self._device_model = ""
            self._device_connected = False
            self._led_ids = ()
            self._last_error = t("errors.icue_no_devices", err=dev_err)
            return False

        candidates = self._select_device_candidates(devices)
        if not candidates:
            self._device_id = ""
            self._device_model = ""
            self._device_connected = False
            self._led_ids = ()
            self._last_error = t("errors.icue_no_compatible")
            return False

        target: Optional[CorsairDeviceInfo] = None
        positions = None
        last_pos_err = None
        for cand in candidates:
            cand_positions, pos_err = self._sdk.get_led_positions(cand.device_id)
            if pos_err == CorsairError.CE_Success and cand_positions:
                target = cand
                positions = cand_positions
                break
            last_pos_err = (cand.model, pos_err)

        if target is None or not positions:
            self._device_id = ""
            self._device_model = ""
            self._device_connected = False
            self._led_ids = ()
            if last_pos_err is not None:
                self._last_error = t(
                    "errors.icue_no_leds_dev",
                    model=last_pos_err[0],
                    err=last_pos_err[1],
                )
            else:
                self._last_error = t("errors.icue_no_leds")
            return False

        self._device_id = target.device_id
        self._device_model = target.model
        self._device_connected = True
        self._led_ids = tuple(pos.id for pos in positions)
        self._last_error = ""
        self._last_rgba = None

        self._sdk.set_layer_priority(self._layer_priority)
        if self._exclusive_control:
            self._sdk.request_control(
                self._device_id, CorsairAccessLevel.CAL_ExclusiveLightingControl
            )

        self._logger.info(
            "Hardware Corsair pronto: modelo='%s', leds=%d",
            self._device_model,
            len(self._led_ids),
        )
        return True

    def _select_device_candidates(
        self, devices: list[CorsairDeviceInfo]
    ) -> list[CorsairDeviceInfo]:
        """Ordena dispositivos compatíveis priorizando `target_model`, se configurado."""
        if not devices:
            return []
        wanted = self._target_model.strip().lower()
        if not wanted:
            return list(devices)
        preferred = [dev for dev in devices if wanted in (dev.model or "").lower()]
        others = [dev for dev in devices if wanted not in (dev.model or "").lower()]
        return preferred + others

    def _select_device(self, devices: list[CorsairDeviceInfo]) -> Optional[CorsairDeviceInfo]:
        candidates = self._select_device_candidates(devices)
        return candidates[0] if candidates else None

    def poll_recovery(self) -> bool:
        """Tenta recuperar conexão com o iCUE ou dispositivo respeitando cooldown."""
        with self._lock:
            if self.is_connected():
                return True
            now = time.monotonic()
            if (now - self._last_recovery_attempt) < self._recovery_cooldown_s:
                return False
            self._last_recovery_attempt = now

            if self._sdk is not None and self._session_state == CorsairSessionState.CSS_Connected:
                return self._discover_device_locked()
            return self.connect(timeout_s=1.0)

    def set_color(
        self, r: int, g: int, b: int, a: int = 255, force: bool = False
    ) -> bool:
        """Aplica cor RGBA nas zonas RGB do dispositivo evitando comandos redundantes."""
        rgba = (
            max(0, min(255, int(r))),
            max(0, min(255, int(g))),
            max(0, min(255, int(b))),
            max(0, min(255, int(a))),
        )
        with self._lock:
            if not self.is_connected():
                return False
            assert self._sdk is not None

            if not force and self._last_rgba == rgba:
                self._commands_skipped += 1
                return True

            payload = [
                CorsairLedColor(
                    id=led_id, r=rgba[0], g=rgba[1], b=rgba[2], a=rgba[3]
                )
                for led_id in self._led_ids
            ]
            t0 = time.perf_counter_ns()
            err = self._sdk.set_led_colors(self._device_id, payload)
            self._last_sdk_call_ms = (time.perf_counter_ns() - t0) / 1_000_000.0

            if err != CorsairError.CE_Success:
                self._last_error = t("errors.icue_set_color_failed", err=err)
                if err in (
                    CorsairError.CE_NotConnected,
                    CorsairError.CE_DeviceNotFound,
                ):
                    self._device_connected = False
                    self._last_rgba = None
                return False

            self._last_rgba = rgba
            self._control_active = rgba[3] > 0
            self._commands_sent += 1
            self._last_error = ""
            return True

    def restore_default(self) -> bool:
        """Devolve controle da iluminação ao perfil normal do iCUE (alpha=0 + release)."""
        with self._lock:
            if not self._control_active and self._last_rgba is None:
                return True
            ok = True
            if self._sdk is not None and self._session_state == CorsairSessionState.CSS_Connected:
                if self._device_id and self._led_ids:
                    transparent = [
                        CorsairLedColor(id=led_id, r=0, g=0, b=0, a=0)
                        for led_id in self._led_ids
                    ]
                    err = self._sdk.set_led_colors(self._device_id, transparent)
                    ok = err == CorsairError.CE_Success
                if self._device_id and self._exclusive_control:
                    self._sdk.release_control(self._device_id)
            self._last_rgba = None
            self._control_active = False
            return ok

    def release_and_disconnect(self) -> None:
        """Restaura a iluminação padrão e encerra a sessão SDK com segurança sem deadlock."""
        with self._lock:
            self.restore_default()
            sdk = self._sdk
            if sdk is None:
                return
            ev_handler_ref = self._event_handler_ref or getattr(sdk, "event_handler", None)
            sess_handler_ref = self._session_handler_ref or getattr(
                sdk, "session_state_changed_event_handler", None
            )
            self._sdk = None
            with self._cb_lock:
                self._device_connected = False
                self._needs_rediscover = False
                self._last_rgba = None
                self._control_active = False

        # Chamadas C executadas FORA de `self._lock` para evitar deadlock com threads
        # internas de callback do iCUE SDK ao disparar CSS_Closed.
        from cuesdk import api as cuesdk_api

        try:
            if hasattr(cuesdk_api, "napi"):
                cuesdk_api.napi.CorsairUnsubscribeFromEvents()
        except Exception:
            pass
        finally:
            _ = ev_handler_ref
            self._event_handler_ref = None
            sdk.event_handler = None

        try:
            if hasattr(cuesdk_api, "napi"):
                cuesdk_api.napi.CorsairDisconnect()
        except Exception:
            pass
        finally:
            _ = sess_handler_ref
            self._session_handler_ref = None
            sdk.session_state_changed_event_handler = None
            with self._cb_lock:
                self._session_state = CorsairSessionState.CSS_Closed

    def get_status(self) -> ICueStatusSnapshot:
        with self._lock:
            return ICueStatusSnapshot(
                icue_process_running=is_icue_process_running(),
                sdk_connected=self._session_state == CorsairSessionState.CSS_Connected,
                session_state=str(self._session_state),
                device_found=bool(self._device_id),
                device_connected=self._device_connected,
                device_model=self._device_model,
                device_id=self._device_id,
                led_ids=self._led_ids,
                last_rgba=self._last_rgba,
                last_error=self._last_error,
                commands_sent=self._commands_sent,
                commands_skipped=self._commands_skipped,
                last_sdk_call_ms=self._last_sdk_call_ms,
            )


class RecordingRGBController:
    """
    Controlador em memória para testes automatizados e modo sem hardware físico.
    Registra todos os comandos RGBA recebidos sem tocar em dispositivos reais.
    """

    def __init__(
        self,
        initially_connected: bool = True,
        device_model: str = "Dispositivo Corsair (Simulado)",
        device_id: str = "mock-corsair-device",
    ) -> None:
        self._lock = threading.RLock()
        self._connected = initially_connected
        self._device_connected = initially_connected
        self._device_model = device_model
        self._device_id = device_id
        self._last_rgba: Optional[tuple[int, int, int, int]] = None
        self._commands_sent = 0
        self._commands_skipped = 0
        self._restore_count = 0
        self._disconnect_count = 0
        self.history: list[tuple[int, int, int, int]] = []
        self.timestamps_ns: list[int] = []

    def simulate_disconnect(self) -> None:
        with self._lock:
            self._device_connected = False
            self._last_rgba = None

    def simulate_reconnect(self) -> None:
        with self._lock:
            self._connected = True
            self._device_connected = True

    def is_connected(self) -> bool:
        with self._lock:
            return self._connected and self._device_connected

    def connect(self, timeout_s: float = 5.0) -> bool:
        with self._lock:
            self._connected = True
            self._device_connected = True
            return True

    def poll_recovery(self) -> bool:
        with self._lock:
            return self._connected and self._device_connected

    def set_color(
        self, r: int, g: int, b: int, a: int = 255, force: bool = False
    ) -> bool:
        rgba = (
            max(0, min(255, int(r))),
            max(0, min(255, int(g))),
            max(0, min(255, int(b))),
            max(0, min(255, int(a))),
        )
        with self._lock:
            if not self.is_connected():
                return False
            if not force and self._last_rgba == rgba:
                self._commands_skipped += 1
                return True
            self._last_rgba = rgba
            self._commands_sent += 1
            self.history.append(rgba)
            self.timestamps_ns.append(time.perf_counter_ns())
            return True

    def restore_default(self) -> bool:
        with self._lock:
            if self._last_rgba is not None:
                self._restore_count += 1
            self._last_rgba = None
            return True

    def release_and_disconnect(self) -> None:
        with self._lock:
            self.restore_default()
            self._disconnect_count += 1
            self._connected = False
            self._device_connected = False

    def get_status(self) -> ICueStatusSnapshot:
        with self._lock:
            return ICueStatusSnapshot(
                icue_process_running=self._connected,
                sdk_connected=self._connected,
                session_state=(
                    "CSS_Connected" if self._connected else "CSS_Closed"
                ),
                device_found=self._connected,
                device_connected=self._device_connected,
                device_model=self._device_model if self._connected else "",
                device_id=self._device_id if self._connected else "",
                led_ids=(0x00040001,),
                last_rgba=self._last_rgba,
                last_error="" if self.is_connected() else "Controlador desconectado",
                commands_sent=self._commands_sent,
                commands_skipped=self._commands_skipped,
                last_sdk_call_ms=0.01,
            )

    @property
    def restore_count(self) -> int:
        with self._lock:
            return self._restore_count

    @property
    def disconnect_count(self) -> int:
        with self._lock:
            return self._disconnect_count
