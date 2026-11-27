"""
ETAPA 5 — Teste físico no Corsair Katar Pro XT com o motor RGB real (`RGBEngine`).

Executa cenários sequenciais através de `GSIParser` -> `EventManager` -> `RGBEngine` -> `ICueController`,
comprovando fisicamente na rodinha do mouse:
1. Freezetime CT (pulso azul)
2. Vida contínua 100 -> 75 -> 50 -> 25 -> 15 HP (vermelho pulsante)
3. Disparos curtos (50 ms laranja #FF9900)
4. Dano de fogo (oscilação vermelho/laranja)
5. C4 plantada acelerando progressivamente e desarme
6. Conflito de prioridades: 15 HP + C4 plantada + Flashbang decaindo -> retorno para C4
7. Encerramento seguro liberando o LED para o iCUE.

AVISO: Este script utiliza payloads gerados localmente para exercitar o hardware real.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config_manager import ConfigManager  # noqa: E402
from app.event_manager import EventManager  # noqa: E402
from app.gsi_parser import GSIParser  # noqa: E402
from app.icue_controller import ICueController  # noqa: E402
from app.logger import configure_logging  # noqa: E402
from app.rgb_engine import RGBEngine  # noqa: E402
from app.simulator import GSISimulator  # noqa: E402


def push_payload(
    sim: GSISimulator,
    parser: GSIParser,
    event_mgr: EventManager,
    engine: RGBEngine,
    payload: dict,
) -> None:
    snap = parser.parse(
        payload,
        received_at_ns=time.perf_counter_ns(),
        received_at_wall=time.time(),
    )
    events = event_mgr.process_snapshot(snap)
    engine.update_state(snap, events, simulation_mode=True)


def main() -> int:
    configure_logging(enable_file=True, enable_console=False)
    cfg_mgr = ConfigManager()
    config = cfg_mgr.get_all()
    # Acelera o timer da C4 apenas nesta demonstração de hardware (10s) para observar a rampa completa
    config["effects"]["c4"]["bomb_timer_s"] = 10.0

    controller = ICueController(
        sdk_path=config["hardware"].get("sdk_path") or None,
        target_model=config["hardware"].get("target_model", "KATAR PRO XT"),
        layer_priority=int(config["hardware"].get("layer_priority", 200)),
        exclusive_control=bool(config["hardware"].get("exclusive_control", False)),
    )

    print("=== CS2 RGB Sync | ETAPA 5 — Teste Físico do Motor RGB no Katar Pro XT ===", flush=True)
    if not controller.connect(timeout_s=8.0):
        print(f"[ERRO] Não foi possível conectar ao Katar Pro XT: {controller.get_status().last_error}", flush=True)
        return 2

    status = controller.get_status()
    print(f"[OK] Conectado ao dispositivo: '{status.device_model}' | LEDs={status.led_ids}", flush=True)

    parser = GSIParser()
    event_mgr = EventManager(shot_debounce_ms=40.0)
    engine = RGBEngine(controller=controller, config=config)
    sim = GSISimulator()

    engine.start()
    try:
        print("\n[1/6] Freezetime CT (pulso azul suave)...", flush=True)
        sim.set_team("CT")
        push_payload(sim, parser, event_mgr, engine, sim.set_round_phase("freezetime"))
        time.sleep(2.2)

        print("[2/6] Round ativo + gradiente de vida (100 -> 75 -> 50 -> 25 -> 15 HP)...", flush=True)
        push_payload(sim, parser, event_mgr, engine, sim.set_round_phase("live"))
        for hp in (100, 75, 50, 25, 15):
            print(f"      HP={hp}", flush=True)
            push_payload(sim, parser, event_mgr, engine, sim.set_health(hp))
            time.sleep(1.0)

        print("[3/6] Disparos (pulsos laranja de 50 ms sobre fundo CT)...", flush=True)
        push_payload(sim, parser, event_mgr, engine, sim.set_health(100))
        push_payload(sim, parser, event_mgr, engine, sim.select_weapon("rifle"))
        time.sleep(0.4)
        for shot_idx in range(1, 4):
            push_payload(sim, parser, event_mgr, engine, sim.trigger_shot())
            time.sleep(0.03)
            st = engine.get_render_state()
            print(f"      Disparo #{shot_idx} enviado | efeito={st.active_effect_id} cor={st.current_color_hex}", flush=True)
            time.sleep(0.32)

        print("[4/6] Dano de fogo (oscilação vermelho/laranja)...", flush=True)
        push_payload(sim, parser, event_mgr, engine, sim.set_burning(180))
        time.sleep(2.0)
        push_payload(sim, parser, event_mgr, engine, sim.set_burning(0))

        print("[5/6] C4 plantada (vermelho acelerando progressivamente)...", flush=True)
        push_payload(sim, parser, event_mgr, engine, sim.set_bomb("planted"))
        time.sleep(4.5)

        print("[6/6] Conflito: 15 HP + C4 plantada + Flashbang (255 -> 150 -> 60 -> 0) -> volta para C4...", flush=True)
        push_payload(sim, parser, event_mgr, engine, sim.set_health(15))
        for fl in (255, 150, 60, 0):
            push_payload(sim, parser, event_mgr, engine, sim.set_flashed(fl))
            time.sleep(0.6)
            st = engine.get_render_state()
            print(f"      flashed={fl:<3} -> ativo='{st.active_effect_id}' cor={st.current_color_hex}", flush=True)

        time.sleep(1.0)
        push_payload(sim, parser, event_mgr, engine, sim.set_bomb("defused"))
        time.sleep(0.6)
        st_after_defuse = engine.get_render_state()
        print(f"      Após desarme (15 HP): ativo='{st_after_defuse.active_effect_id}' cor={st_after_defuse.current_color_hex}", flush=True)

        final_state = engine.get_render_state()
        final_hw = controller.get_status()
        print("\n=== Métricas Reais de Desempenho (Software/SDK) ===", flush=True)
        print(f"Frames renderizados : {final_state.frames_rendered} (tick={final_state.tick_ms} ms)", flush=True)
        print(f"Comandos SDK env.   : {final_hw.commands_sent} (ignorados por redundância={final_hw.commands_skipped})", flush=True)
        print(f"Latência proc. SW   : última={final_state.latency.last_processing_ms:.2f} ms | média={final_state.latency.avg_processing_ms:.2f} ms | máx={final_state.latency.max_processing_ms:.2f} ms", flush=True)
        print(f"Última chamada SDK  : {final_state.latency.last_sdk_call_ms:.2f} ms", flush=True)
        return 0
    finally:
        engine.stop(release_controller=True)
        end_status = controller.get_status()
        print(f"[ENCERRAMENTO] SDK={end_status.session_state} | controle liberado com segurança.", flush=True)


if __name__ == "__main__":
    sys.exit(main())
