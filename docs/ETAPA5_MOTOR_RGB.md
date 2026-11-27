# ETAPA 5 (e ETAPA 6) — Controlador iCUE, Efeitos RGB e Motor de Prioridades

## 1. Arquitetura Implementada

```text
GSIParser / EventManager
  └── RGBEngine.update_state(snapshot, events)   [lock mínimo, não bloqueia HTTP]
        └── Thread independente (tick padrão 25 ms)
              ├── resolve_active_effect()        [8 níveis configuráveis]
              ├── Suavização temporal / pulso instantâneo
              ├── Medição de latência de software (received_ns -> sent_ns)
              └── ICueController (RLock + deduplicação RGBA)
                    └── iCUESDK.x64_2019.dll -> Corsair Katar Pro XT (rodinha)
```

---

## 2. Sistema de Prioridades e Retorno Automático

Ordem padrão configurável (`config/default_config.json`):
1. **`flashbang`** — Branco (`#FFFFFF`), brilho proporcional a `player.state.flashed / 255` e decaimento suave acompanhando o GSI real.
2. **`shot`** — Laranja (`#FF9900`), pulso curto de duração configurável (`50 ms` padrão) com resposta imediata (`instant=True`).
3. **`c4`** — Vermelho (`#FF0000`), piscar progressivamente mais rápido de `1.0 Hz` até `10.0 Hz` com fase contínua integrada; interrompe imediatamente em `defused`, `exploded` ou início de novo round.
4. **`fire`** — Oscilação vermelho/laranja (`4.0 Hz`) **somente** quando `burning_field_seen == True` e `burning > 0` no payload real do GSI.
5. **`health_critical`** — Vermelho pulsante (`2.5 Hz`) quando `0 < health < 25`.
6. **`health`** — Interpolação contínua entre `100 HP` (`#00FF00`), `75 HP` (`#80FF00`), `50 HP` (`#FFFF00`) e `25 HP` (`#FF9900`), cedendo vez no `freezetime` para o pulso da equipe.
7. **`team_round`** — TR (`#FF9900`) / CT (`#008CFF`), pulso suave no `freezetime` e cor fixa no round ativo.
8. **`weapon`** — Cores configuráveis por categoria (`knife`, `pistol`, `rifle`, `sniper`, `smg`, `shotgun`, `grenade`).

Quando um efeito prioritário termina (ex.: fim da flashbang, fim dos 50 ms do disparo ou desarme da C4), `resolve_active_effect()` retorna automaticamente o próximo efeito ativo na hierarquia.

---

## 3. Limitações Documentadas e Aproximações

1. **Aproximação configurável do timer da C4:** para jogadores vivos, o CS2 GSI informa `round.bomb = "planted"`, `"defused"` ou `"exploded"`, sem enviar o tempo restante em segundos. O motor utiliza a duração configurável `effects.c4.bomb_timer_s` (`40.0 s` padrão, ajustável para servidores customizados) medida a partir de `planted_at_ns`.
2. **Disparos agrupados pelo GSI:** quando vários tiros acontecem dentro da janela `buffer`/`throttle` (`0.05s`), o GSI reduz `ammo_clip` em mais de uma unidade por pacote (`grouped_shots=True`). Portanto, disparos muito rápidos podem gerar um único pulso consolidado em vez de pulsos individuais por projétil.
3. **Métricas de latência:** `LatencyMetrics` registra tempos de **software/SDK** (`received_at_ns`, `detected_at_ns`, `rgb_sent_ns` e duração de `CorsairSetLedColors`), não representando medição óptica física do LED.
4. **Integridade do mouse no iCUE:** `ICueController` atua exclusivamente em cores LED (`set_led_colors`, `set_layer_priority`, `request_control`/`release_control`) e nunca altera DPI, polling rate, botões, macros ou perfis internos do Katar Pro XT.

---

## 4. Descoberta Crítica e Correção no Hardware Real (`ICueController`)

Durante a primeira execução do teste contínuo no hardware real (`tools/test_engine_hardware.py`), o script travou no encerramento (`release_and_disconnect`) porque `CorsairDisconnect()` dispara o callback `_on_session_state_changed(CSS_Closed)` a partir de thread interna da DLL nativa enquanto a thread principal ainda mantinha `self._lock`.

**Correção implementada em `app/icue_controller.py`:**
- Callbacks `_on_session_state_changed` e `_on_sdk_event` usam exclusivamente um lock folha dedicado (`self._cb_lock`) sem chamar funções da DLL.
- `release_and_disconnect()` restaura a transparência (`a=0`), libera `self._lock` e executa `CorsairUnsubscribeFromEvents()` e `CorsairDisconnect()` **fora** de `self._lock`, mantendo as referências dos handlers C até após o retorno nativo.

---

## 5. Resultados Reais dos Testes

### 5.1 Testes Automatizados (`pytest -v`)
- **29 testes executados, 29 aprovados (0 falhas)** em `1.81s`:
  - `tests/test_config.py`: 6/6 aprovados
  - `tests/test_effects.py`: 6/6 aprovados
  - `tests/test_event_manager.py`: 3/3 aprovados
  - `tests/test_gsi_parser.py`: 5/5 aprovados
  - `tests/test_gsi_server.py`: 5/5 aprovados
  - `tests/test_rgb_engine.py`: 4/4 aprovados (hierarquia, reordenação dinâmica, deduplicação, latência, concorrência multi-thread, desconexão CS2 e recuperação iCUE).

### 5.2 Teste no Hardware Real (`tools/test_engine_hardware.py` no Corsair Katar Pro XT)
- **Dispositivo:** `'KATAR PRO XT'` (`LEDs=(262145,)`)
- **Cenários executados:**
  - Freezetime CT (pulso azul)
  - Gradiente de vida `100 -> 75 -> 50 -> 25 -> 15 HP`
  - 3 disparos consecutivos: `Disparo #1/#2/#3 -> efeito=shot cor=#FF9900`
  - Dano de fogo simulado (oscilação vermelho/laranja)
  - C4 plantada acelerando + conflito com `15 HP` e `Flashbang` (`255 -> #FFFFFF`, `150 -> #979797`, `60 -> #3D3D3D`, `0 -> c4`), retornando para `health_critical` após desarme.
- **Métricas reais coletadas:**
  - `Frames renderizados : 648 (tick=25 ms)`
  - `Comandos SDK env.   : 484 (ignorados por redundância=163)`
  - `Latência proc. SW   : última=26.25 ms | média=16.95 ms | máx=41.65 ms`
  - `Última chamada SDK  : 0.40 ms`
  - Encerramento limpo: `[ENCERRAMENTO] SDK=1 | controle liberado com segurança.` (código de saída `0`).
