"""
ETAPA 2 — Prova real de controle da iluminação RGB no Corsair Katar Pro XT.

Executa conexão com o Corsair iCUE SDK v4 (via pacote oficial `cuesdk`),
enumera dispositivos conectados, localiza o Corsair Katar Pro XT, consulta
suas posições/LUIDs de LED e aplica uma sequência visual de cores na rodinha
com leitura de confirmação via `get_led_colors`.

Não altera DPI, polling rate, macros, botões ou perfis do mouse.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from typing import Iterable, Optional

import psutil
from cuesdk import (
    CorsairAccessLevel,
    CorsairDeviceFilter,
    CorsairDeviceInfo,
    CorsairDeviceType,
    CorsairError,
    CorsairLedColor,
    CorsairLedPosition,
    CorsairSessionState,
    CorsairSessionStateChanged,
    CueSdk,
)


DEFAULT_SEQUENCE: list[tuple[str, tuple[int, int, int, int]]] = [
    ("Vermelho (#FF0000)", (255, 0, 0, 255)),
    ("Verde (#00FF00)", (0, 255, 0, 255)),
    ("Azul (#0000FF)", (0, 0, 255, 255)),
    ("Branco (#FFFFFF)", (255, 255, 255, 255)),
    ("Laranja (#FF9900)", (255, 153, 0, 255)),
    ("Laranja 40% brilho (#663D00)", (102, 61, 0, 255)),
    ("Desligado (#000000)", (0, 0, 0, 255)),
]


def find_icue_processes() -> list[tuple[int, str]]:
    """Retorna PIDs e nomes de processos relacionados ao iCUE em execução."""
    found: list[tuple[int, str]] = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = proc.info.get("name") or ""
            if "icue" in name.lower():
                found.append((proc.info["pid"], name))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def parse_hex_color(hex_str: str, brightness_pct: int) -> tuple[int, int, int]:
    """Converte string #RRGGBB e brilho 0..100 em tupla RGB."""
    clean = hex_str.strip().lstrip("#")
    if len(clean) != 6:
        raise ValueError(f"Cor inválida '{hex_str}'. Use o formato #RRGGBB.")
    r = int(clean[0:2], 16)
    g = int(clean[2:4], 16)
    b = int(clean[4:6], 16)
    factor = max(0, min(100, brightness_pct)) / 100.0
    return (round(r * factor), round(g * factor), round(b * factor))


def connect_sdk(sdk: CueSdk, timeout_s: float = 10.0) -> CorsairSessionState:
    """Conecta ao iCUE SDK v4 e aguarda transição de sessão."""
    connected_event = threading.Event()
    terminal_event = threading.Event()
    state_lock = threading.Lock()
    latest_state: list[CorsairSessionState] = [CorsairSessionState.CSS_Invalid]

    def on_state_changed(evt: CorsairSessionStateChanged) -> None:
        with state_lock:
            latest_state[0] = evt.state
        print(f"[SDK] Estado da sessão alterado -> {evt.state}")
        if evt.state == CorsairSessionState.CSS_Connected:
            connected_event.set()
        elif evt.state in (
            CorsairSessionState.CSS_Timeout,
            CorsairSessionState.CSS_ConnectionRefused,
            CorsairSessionState.CSS_Closed,
        ):
            terminal_event.set()

    err = sdk.connect(on_state_changed)
    print(f"[SDK] CorsairConnect retornou: {err}")
    if err != CorsairError.CE_Success:
        return latest_state[0]

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if connected_event.wait(timeout=0.1):
            return CorsairSessionState.CSS_Connected
        if terminal_event.is_set():
            with state_lock:
                return latest_state[0]

    with state_lock:
        return latest_state[0]


def select_target_mouse(
    devices: Iterable[CorsairDeviceInfo],
) -> tuple[Optional[CorsairDeviceInfo], bool]:
    """
    Seleciona o Corsair Katar Pro XT dentre os dispositivos conectados.
    Retorna (dispositivo, é_katar_pro_xt).
    """
    device_list = list(devices)
    for dev in device_list:
        if "katar pro xt" in dev.model.lower():
            return dev, True
    for dev in device_list:
        if dev.type == CorsairDeviceType.CDT_Mouse:
            return dev, False
    return None, False


def apply_and_verify_color(
    sdk: CueSdk,
    device_id: str,
    led_ids: list[int],
    label: str,
    rgba: tuple[int, int, int, int],
) -> bool:
    """Envia a cor para os LEDs alvo e lê de volta via get_led_colors."""
    r, g, b, a = rgba
    payload = [CorsairLedColor(id=led_id, r=r, g=g, b=b, a=a) for led_id in led_ids]
    err = sdk.set_led_colors(device_id, payload)
    print(
        f"[RGB] {label:<30} -> enviado RGBA=({r}, {g}, {b}, {a}) | set_led_colors={err}",
        flush=True,
    )
    if err != CorsairError.CE_Success:
        return False

    # O iCUE atualiza o cache interno de cores no próximo tick (~20-50 ms).
    time.sleep(0.08)
    read_query = [CorsairLedColor(id=led_id, r=0, g=0, b=0, a=0) for led_id in led_ids]
    read_back, read_err = sdk.get_led_colors(device_id, read_query)
    if read_err == CorsairError.CE_Success and read_back:
        formatted = ", ".join(
            f"LUID=0x{c.id:08X} RGBA=({c.r},{c.g},{c.b},{c.a})" for c in read_back
        )
        print(f"      confirmação get_led_colors -> {formatted}", flush=True)
    else:
        print(f"      aviso: get_led_colors retornou {read_err}", flush=True)
    return True


def safe_disconnect(sdk: CueSdk) -> CorsairError:
    """
    Desconecta do iCUE SDK preservando a referência do callback C durante a chamada.

    Workaround para bug no `cuesdk==4.0.84` (`api.py:92`), que zera
    `self.session_state_changed_event_handler = None` antes de chamar
    `napi.CorsairDisconnect()`, causando crash 0xC000001D quando a DLL dispara
    `CSS_Closed` no callback liberado.
    """
    from cuesdk import api as cuesdk_api

    handler_ref = getattr(sdk, "session_state_changed_event_handler", None)
    try:
        return CorsairError(cuesdk_api.napi.CorsairDisconnect())
    finally:
        _ = handler_ref
        sdk.session_state_changed_event_handler = None


def restore_icue_control(
    sdk: CueSdk, device_id: Optional[str], led_ids: list[int]
) -> None:
    """Restaura transparência (a=0) e libera controle exclusivo para o iCUE."""
    if device_id and led_ids:
        transparent = [
            CorsairLedColor(id=led_id, r=0, g=0, b=0, a=0) for led_id in led_ids
        ]
        err = sdk.set_led_colors(device_id, transparent)
        print(f"[SDK] Transparência restaurada (a=0): {err}")
    if device_id:
        rel_err = sdk.release_control(device_id)
        print(f"[SDK] CorsairReleaseControl: {rel_err}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Teste real de controle RGB do Corsair Katar Pro XT via iCUE SDK v4."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--auto",
        action="store_true",
        help="Executa a sequência automática de cores (padrão).",
    )
    mode.add_argument(
        "--interactive",
        action="store_true",
        help="Aguarda Enter antes de aplicar cada cor.",
    )
    mode.add_argument(
        "--list-only",
        action="store_true",
        help="Apenas enumera dispositivos e LEDs sem alterar iluminação.",
    )
    mode.add_argument(
        "--color",
        type=str,
        help="Aplica uma cor específica (#RRGGBB) e aguarda --hold segundos.",
    )
    parser.add_argument(
        "--brightness",
        type=int,
        default=100,
        help="Brilho em porcentagem (0..100) usado com --color. Padrão: 100.",
    )
    parser.add_argument(
        "--hold",
        type=float,
        default=2.5,
        help="Tempo em segundos mantendo cada cor no modo automático. Padrão: 2.5.",
    )
    parser.add_argument(
        "--exclusive",
        action="store_true",
        help="Solicita controle exclusivo de iluminação (CAL_ExclusiveLightingControl).",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    print("=== CS2 RGB Sync | ETAPA 2 — Prova Real Corsair Katar Pro XT ===")
    icue_procs = find_icue_processes()
    if icue_procs:
        proc_str = ", ".join(f"{name} (PID {pid})" for pid, name in icue_procs)
        print(f"[SO] Processos iCUE detectados: {proc_str}")
    else:
        print(
            "[AVISO] Nenhum processo 'iCUE' foi detectado em execução. "
            "Abra o Corsair iCUE 5 e habilite o SDK em Configurações -> SDK."
        )

    sdk = CueSdk()
    target_device_id: Optional[str] = None
    led_ids: list[int] = []

    try:
        state = connect_sdk(sdk, timeout_s=10.0)
        if state != CorsairSessionState.CSS_Connected:
            print(f"[ERRO] Falha ao conectar no iCUE SDK. Estado final: {state}")
            if state == CorsairSessionState.CSS_ConnectionRefused:
                print(
                    "       Verifique no Corsair iCUE 5: Configurações -> SDK -> "
                    "ative 'SDK do iCUE' / controle de jogos e aplicativos."
                )
            elif state == CorsairSessionState.CSS_Timeout:
                print(
                    "       Tempo esgotado aguardando o serviço do iCUE. "
                    "Confirme que o iCUE está aberto e executando."
                )
            return 2

        details, det_err = sdk.get_session_details()
        if det_err == CorsairError.CE_Success and details:
            cv = details.client_version
            sv = details.server_version
            hv = details.server_host_version
            print(
                f"[SDK] Versões -> Client: {cv.major}.{cv.minor}.{cv.patch} | "
                f"Server: {sv.major}.{sv.minor}.{sv.patch} | "
                f"iCUE Host: {hv.major}.{hv.minor}.{hv.patch}"
            )

        devices, dev_err = sdk.get_devices(
            CorsairDeviceFilter(device_type_mask=CorsairDeviceType.CDT_All)
        )
        if dev_err != CorsairError.CE_Success or devices is None:
            print(f"[ERRO] Falha ao enumerar dispositivos Corsair: {dev_err}")
            return 3

        print(f"[SDK] Dispositivos Corsair encontrados ({len(devices)}):")
        for idx, dev in enumerate(devices, start=1):
            print(
                f"  {idx}. Modelo='{dev.model}' | Tipo={dev.type} | "
                f"LEDs={dev.led_count} | Canais={dev.channel_count} | "
                f"ID={dev.device_id}"
            )

        if not devices:
            print(
                "[ERRO] Nenhum dispositivo Corsair retornado pelo iCUE SDK. "
                "Confirme que o mouse está conectado e reconhecido no iCUE."
            )
            return 4

        target_dev, is_katar = select_target_mouse(devices)
        if target_dev is None:
            print("[ERRO] Nenhum mouse Corsair (CDT_Mouse) encontrado.")
            return 5

        if not is_katar:
            print(
                f"[AVISO] Modelo exato 'KATAR PRO XT' não encontrado; "
                f"usando mouse encontrado: '{target_dev.model}'."
            )
        else:
            print(f"[OK] Mouse alvo identificado: '{target_dev.model}'")

        target_device_id = target_dev.device_id
        positions, pos_err = sdk.get_led_positions(target_device_id)
        if pos_err != CorsairError.CE_Success or not positions:
            print(f"[ERRO] Falha ao consultar LEDs do mouse: {pos_err}")
            return 6

        print(f"[LED] Posições retornadas ({len(positions)}):")
        for pos in positions:
            group = (pos.id >> 16) & 0xFFFF
            index = pos.id & 0xFFFF
            print(
                f"  - LUID=0x{pos.id:08X} ({pos.id}) | grupo={group}, "
                f"indice={index} | cx={pos.cx:.2f}, cy={pos.cy:.2f}"
            )
        led_ids = [pos.id for pos in positions]

        if args.list_only:
            print("[INFO] Modo --list-only finalizado sem alterar cores.")
            return 0

        prio_err = sdk.set_layer_priority(200)
        print(f"[SDK] set_layer_priority(200): {prio_err}")

        if args.exclusive:
            ctrl_err = sdk.request_control(
                target_device_id, CorsairAccessLevel.CAL_ExclusiveLightingControl
            )
            print(f"[SDK] request_control(CAL_ExclusiveLightingControl): {ctrl_err}")

        if args.color:
            r, g, b = parse_hex_color(args.color, args.brightness)
            steps = [(f"Cor {args.color} ({args.brightness}%)", (r, g, b, 255))]
        else:
            steps = DEFAULT_SEQUENCE

        print("\nIniciando sequência de iluminação na rodinha do mouse...")
        for step_num, (label, rgba) in enumerate(steps, start=1):
            if args.interactive:
                input(f"\n[{step_num}/{len(steps)}] Pressione ENTER para aplicar: {label} ")
            ok = apply_and_verify_color(sdk, target_device_id, led_ids, label, rgba)
            if not ok:
                print(f"[ERRO] Falha ao aplicar cor em '{label}'.")
                return 7
            if not args.interactive:
                time.sleep(max(0.1, args.hold))

        print(
            "\n[CONCLUÍDO] Sequência de comandos enviada ao iCUE SDK com sucesso.\n"
            "Confirme visualmente se a rodinha do Corsair Katar Pro XT mudou de cor."
        )
        return 0
    except KeyboardInterrupt:
        print("\n[INTERROMPIDO] Teste cancelado pelo usuário.")
        return 130
    finally:
        if target_device_id and not args.list_only:
            restore_icue_control(sdk, target_device_id, led_ids)
        disc_err = safe_disconnect(sdk)
        print(f"[SDK] CorsairDisconnect: {disc_err}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
