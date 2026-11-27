"""
ETAPA 3 — Ferramenta de instalação, autodiagnóstico e sonda ao vivo do CS2 GSI.

Modos de uso:
  --install-cfg   Detecta a pasta do CS2, gera/carrega o config local e grava
                  `gamestate_integration_cs2rgbsync.cfg` na pasta `cfg` do jogo.
  --self-test     Inicia o GSIServer em 127.0.0.1 e executa requisições HTTP POST
                  reais em loopback (válida, token inválido, JSON inválido, parcial).
  --listen        (Padrão) Inicia o servidor GSI e exibe em tempo real os eventos
                  recebidos do CS2 (com token mascarado) até Ctrl+C.
"""

from __future__ import annotations

import argparse
import json
import queue
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config_manager import ConfigManager  # noqa: E402
from app.event_manager import EventManager  # noqa: E402
from app.gsi_config import detect_cs2_game_dir, install_gsi_cfg  # noqa: E402
from app.gsi_parser import GSIParser  # noqa: E402
from app.gsi_server import GSIServer  # noqa: E402
from app.logger import configure_logging  # noqa: E402

REFERENCE_CS2_DIR = Path(
    r"D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive\game\csgo"
)


def _post_json(
    url: str, raw_body: bytes, timeout: float = 3.0
) -> tuple[int, str, float]:
    req = urllib.request.Request(
        url,
        data=raw_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter_ns()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
            return resp.status, body, elapsed_ms
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
        return exc.code, body, elapsed_ms


def run_install_cfg(cfg_mgr: ConfigManager, cs2_override: Optional[str]) -> int:
    preferred = cs2_override or cfg_mgr.get("gsi.cs2_path") or str(REFERENCE_CS2_DIR)
    cs2_dir = detect_cs2_game_dir(preferred_path=preferred)
    if cs2_dir is None:
        print(
            "[ERRO] Não foi possível localizar a pasta do CS2 (game\\csgo\\cfg). "
            "Informe --cs2-path explicitamente.",
            flush=True,
        )
        return 2

    cfg_mgr.set("gsi.cs2_path", str(cs2_dir))
    port = int(cfg_mgr.get("server.port", 3000))
    token = str(cfg_mgr.get("server.token", ""))
    installed_path = install_gsi_cfg(
        cs2_game_dir=cs2_dir,
        port=port,
        token=token,
        buffer=float(cfg_mgr.get("gsi.buffer", 0.05)),
        throttle=float(cfg_mgr.get("gsi.throttle", 0.05)),
        timeout=float(cfg_mgr.get("gsi.timeout", 5.0)),
        heartbeat=float(cfg_mgr.get("gsi.heartbeat", 15.0)),
    )
    print(f"[OK] CS2 detectado em: {cs2_dir}", flush=True)
    print(f"[OK] Arquivo GSI instalado em: {installed_path}", flush=True)
    print(
        f"[OK] Endpoint configurado: http://127.0.0.1:{port}/ "
        f"(token gerado localmente com {len(token)} caracteres, ocultado por segurança)",
        flush=True,
    )
    return 0


def run_self_test(cfg_mgr: ConfigManager) -> int:
    port = int(cfg_mgr.get("server.port", 3000))
    token = str(cfg_mgr.get("server.token", ""))

    # Tenta a porta configurada; se ocupada, usa porta efêmera apenas para o teste de loopback
    server = GSIServer(host="127.0.0.1", port=port, auth_token=token)
    try:
        active_port = server.start()
    except OSError as exc:
        print(
            f"[AVISO] Porta {port} indisponível ({exc}); testando em porta efêmera.",
            flush=True,
        )
        server = GSIServer(host="127.0.0.1", port=0, auth_token=token)
        active_port = server.start()

    url = f"http://127.0.0.1:{active_port}/"
    print(f"[SELF-TEST] Servidor ativo em {url}", flush=True)

    try:
        # 1. Payload completo válido
        valid_payload: dict[str, Any] = {
            "provider": {"name": "Counter-Strike 2", "appid": 730, "timestamp": 1700000000},
            "round": {"phase": "live", "bomb": "planted"},
            "player": {
                "team": "CT",
                "state": {"health": 85, "armor": 100, "flashed": 0},
                "weapons": {
                    "weapon_0": {"name": "weapon_m4a1_silencer", "ammo_clip": 20, "state": "active"}
                },
            },
            "auth": {"token": token},
        }
        code1, _, ms1 = _post_json(url, json.dumps(valid_payload).encode("utf-8"))
        print(f"  1) POST válido -> HTTP {code1} ({ms1:.2f} ms)", flush=True)

        # 2. Token inválido
        bad_token_payload = {"provider": {"appid": 730}, "auth": {"token": "wrong-token"}}
        code2, _, ms2 = _post_json(url, json.dumps(bad_token_payload).encode("utf-8"))
        print(f"  2) POST token inválido -> HTTP {code2} ({ms2:.2f} ms)", flush=True)

        # 3. JSON inválido
        code3, _, ms3 = _post_json(url, b"{not-valid-json")
        print(f"  3) POST JSON inválido -> HTTP {code3} ({ms3:.2f} ms)", flush=True)

        # 4. Payload parcial (heartbeat / apenas provider + previously)
        partial_payload = {
            "provider": {"name": "Counter-Strike 2", "appid": 730},
            "previously": {"player": {"state": {"health": 100}}},
            "auth": {"token": token},
        }
        code4, _, ms4 = _post_json(url, json.dumps(partial_payload).encode("utf-8"))
        print(f"  4) POST parcial -> HTTP {code4} ({ms4:.2f} ms)", flush=True)

        stats = server.get_stats()
        last_payload = server.get_last_payload() or {}
        masked_token = (last_payload.get("auth") or {}).get("token")
        print(
            f"[STATS] recebidas={stats.requests_received}, aceitas={stats.requests_accepted}, "
            f"falhas_token={stats.auth_failures}, erros_json={stats.parse_errors}, "
            f"fila={stats.queue_size}, token_em_diag={masked_token}",
            flush=True,
        )

        all_ok = (
            code1 == 200
            and code2 == 401
            and code3 == 400
            and code4 == 200
            and stats.requests_accepted == 2
            and stats.auth_failures == 1
            and stats.parse_errors == 1
            and masked_token == "***REDACTED***"
        )
        if not all_ok:
            print("[ERRO] Resultado inesperado no self-test GSI.", flush=True)
            return 1
        print("[OK] Self-test HTTP GSI validado com sucesso.", flush=True)
        return 0
    finally:
        server.stop()


def run_listen(cfg_mgr: ConfigManager) -> int:
    port = int(cfg_mgr.get("server.port", 3000))
    token = str(cfg_mgr.get("server.token", ""))
    server = GSIServer(host="127.0.0.1", port=port, auth_token=token)
    parser = GSIParser()
    event_mgr = EventManager(
        shot_debounce_ms=float(cfg_mgr.get("effects.shot.debounce_ms", 40.0)),
        critical_health_threshold=int(cfg_mgr.get("effects.health.critical_threshold", 25)),
        disconnect_timeout_s=float(cfg_mgr.get("gsi.disconnect_timeout_s", 35.0)),
    )
    active_port = server.start()
    print(
        f"[LISTEN] Servidor GSI escutando em http://127.0.0.1:{active_port}/\n"
        "Abra o Counter-Strike 2 para observar payloads e eventos em tempo real. Pressione Ctrl+C para sair.",
        flush=True,
    )
    try:
        while True:
            try:
                msg = server.event_queue.get(timeout=0.5)
                snap = parser.parse(
                    msg.payload,
                    received_at_ns=msg.received_at_ns,
                    received_at_wall=msg.received_at_wall,
                )
                events = event_mgr.process_snapshot(snap)
                weapon_info = (
                    f"{snap.active_weapon.name}({snap.active_weapon.ammo_clip})"
                    if snap.active_weapon
                    else "-"
                )
                event_names = [ev.event_type.value for ev in events]
                print(
                    f"[GSI] round={snap.round_phase} bomb={snap.bomb_state} "
                    f"team={snap.team} hp={snap.health} flashed={snap.flashed} "
                    f"burning={snap.burning if snap.burning_field_seen else 'n/a'} "
                    f"weapon={weapon_info} events={event_names}",
                    flush=True,
                )
            except queue.Empty:
                timeout_events = event_mgr.check_timeout()
                for ev in timeout_events:
                    print(f"[EVENTO] {ev.event_type.value} -> {ev.data}", flush=True)
                continue
    except KeyboardInterrupt:
        print("\n[LISTEN] Encerrando sonda GSI...", flush=True)
        return 0
    finally:
        server.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ferramenta de instalação e teste do servidor GSI do CS2 RGB Sync."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--install-cfg",
        action="store_true",
        help="Instala gamestate_integration_cs2rgbsync.cfg na pasta cfg do CS2.",
    )
    mode.add_argument(
        "--self-test",
        action="store_true",
        help="Executa bateria local de testes HTTP POST em loopback.",
    )
    mode.add_argument(
        "--listen",
        action="store_true",
        help="Inicia o servidor GSI e imprime payloads reais recebidos do CS2.",
    )
    parser.add_argument(
        "--cs2-path",
        type=str,
        default=None,
        help="Caminho opcional da pasta do CS2 (...\\game\\csgo).",
    )
    return parser


def main() -> int:
    configure_logging(enable_file=True, enable_console=False)
    args = build_parser().parse_args()
    cfg_mgr = ConfigManager()

    if args.install_cfg:
        return run_install_cfg(cfg_mgr, args.cs2_path)
    if args.self_test:
        return run_self_test(cfg_mgr)
    return run_listen(cfg_mgr)


if __name__ == "__main__":
    sys.exit(main())
