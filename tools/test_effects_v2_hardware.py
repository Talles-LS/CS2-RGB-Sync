"""
Validação física no Corsair Katar Pro XT dos efeitos RGB ajustados:
1. Estado idle em partida com LED completamente apagado (0, 0, 0).
2. Flashbang intensa (255), média (140), modo binário real (0 -> 1 -> 0) e decaimento suave -> apagado.
3. Disparo (#FF9900).
4. C4 plantada (bipada discreta) interrompida por Dano de Fogo (prioridade superior à C4),
   retomando C4 após fogo cessar, interrompida por Flashbang -> desarme -> apagado -> restauração do iCUE.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.event_manager import EventManager  # noqa: E402
from app.gsi_parser import GSIParser  # noqa: E402
from app.icue_controller import ICueController  # noqa: E402
from app.logger import configure_logging  # noqa: E402
from app.rgb_engine import RGBEngine  # noqa: E402
from app.simulator import GSISimulator  # noqa: E402


def _push(sim: GSISimulator, parser: GSIParser, mgr: EventManager, eng: RGBEngine, payload: dict) -> None:
    snap = parser.parse(payload, received_at_ns=time.perf_counter_ns(), received_at_wall=time.time())
    events = mgr.process_snapshot(snap)
    eng.update_state(snap, events, simulation_mode=True)


def main() -> int:
    configure_logging(enable_file=False, enable_console=False)
    default_cfg = json.loads(
        (PROJECT_ROOT / "config" / "default_config.json").read_text(encoding="utf-8")
    )
    # Usa temporizador reduzido para 12s nesta demonstração física da progressão completa da C4
    default_cfg["effects"]["c4"]["bomb_timer_s"] = 12.0

    controller = ICueController()
    print("=== Teste Físico dos Efeitos RGB v2 (Corsair Katar Pro XT) ===", flush=True)
    if not controller.connect(timeout_s=8.0):
        print(f"[ERRO] Falha ao conectar ao Katar Pro XT: {controller.get_status().last_error}")
        return 2

    parser = GSIParser()
    mgr = EventManager(shot_debounce_ms=40.0)
    eng = RGBEngine(controller=controller, config=default_cfg)
    sim = GSISimulator()
    eng.start()

    try:
        print("[1/4] Estado idle em partida (vida/equipe desativados -> LED apagado 0,0,0)...", flush=True)
        _push(sim, parser, mgr, eng, sim.set_team("CT"))
        _push(sim, parser, mgr, eng, sim.set_health(100))
        time.sleep(0.5)
        st = eng.get_render_state()
        print(f"      ativo={st.active_effect_id} | rgb={st.current_rgb} | sdk_rgba={controller.get_status().last_rgba}", flush=True)

        print("[2/4] Flashbang (255 -> 140 -> 0 e sequencia real 0 -> 1 -> 0 -> decaimento suave)...", flush=True)
        for fl, wait_s in ((255, 0.7), (140, 0.7), (0, 0.8)):
            _push(sim, parser, mgr, eng, sim.set_flashed(fl))
            time.sleep(0.05)
            st = eng.get_render_state()
            print(f"      flashed={fl:<3} -> {st.active_effect_id} {st.current_color_hex}", flush=True)
            time.sleep(wait_s)
        _push(sim, parser, mgr, eng, sim.set_flashed(1))
        time.sleep(0.06)
        st_bin = eng.get_render_state()
        print(f"      flashed=1 (binario real) -> {st_bin.active_effect_id} {st_bin.current_color_hex}", flush=True)
        time.sleep(0.5)
        _push(sim, parser, mgr, eng, sim.set_flashed(0))
        time.sleep(0.8)

        print("[3/4] Disparo (#FF9900)...", flush=True)
        _push(sim, parser, mgr, eng, sim.trigger_shot())
        time.sleep(0.03)
        print(f"      disparo -> {eng.get_render_state().active_effect_id} {eng.get_render_state().current_color_hex}", flush=True)
        time.sleep(0.35)

        print("[4/4] C4 plantada -> interrompida por Fogo (prioridade > C4) -> retoma C4 -> Flashbang -> desarme...", flush=True)
        _push(sim, parser, mgr, eng, sim.set_bomb("planted"))
        time.sleep(2.4)
        print("      ativando Dano de Fogo durante C4...", flush=True)
        _push(sim, parser, mgr, eng, sim.set_burning(180))
        time.sleep(1.0)
        print(f"      efeito durante fogo -> {eng.get_render_state().active_effect_id} {eng.get_render_state().current_color_hex}", flush=True)
        _push(sim, parser, mgr, eng, sim.set_burning(0))
        time.sleep(1.8)
        print(f"      retorno a C4 -> {eng.get_render_state().active_effect_id}", flush=True)
        print("      interrompendo C4 com Flashbang...", flush=True)
        _push(sim, parser, mgr, eng, sim.set_flashed(255))
        time.sleep(0.4)
        _push(sim, parser, mgr, eng, sim.set_flashed(0))
        print("      retornando a C4 acelerando ate o fim...", flush=True)
        time.sleep(3.5)
        _push(sim, parser, mgr, eng, sim.set_bomb("defused"))
        time.sleep(0.4)
        st_end = eng.get_render_state()
        print(f"      apos desarme -> {st_end.active_effect_id} {st_end.current_rgb}", flush=True)
        return 0
    finally:
        eng.stop(release_controller=True)
        print(f"[ENCERRAMENTO] SDK={controller.get_status().session_state} | controle devolvido ao iCUE.", flush=True)


if __name__ == "__main__":
    sys.exit(main())
