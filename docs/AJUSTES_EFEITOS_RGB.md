# Correção da Flashbang Real, Prioridade do Fogo e Remoção da HE — CS2 RGB Sync

Este documento registra a investigação em partida real, as correções aplicadas no pipeline completo de eventos do **CS2 RGB Sync**, o ajuste de prioridade de dano por fogo acima da C4 e a remoção completa da funcionalidade de granada HE (`he_explosion` / `allgrenades`), mantendo intacta a arquitetura modular, a UI existente (sem redesign nem alteração de ícone) e sem reconstruir o instalador nesta etapa.

---

## 1. Diagnóstico Real da Falha da Flashbang

A análise do arquivo real `%LOCALAPPDATA%\CS2RGBSync\logs\cs2rgbsync.log` durante sessão no modo treino do CS2 (`2026-11-27 04:08:43–04:21:33`) mostrou exatamente o comportamento real enviado pelo jogo na cadeia `CS2 → GSI → GSIServer → GSIParser → EventManager → RGBEngine → iCUE SDK → LED`:

```text
2026-11-27 04:13:39 [INFO] cs2rgbsync.sync_service: GSI evento flashbang_changed -> {'old_intensity': 0, 'intensity': 1, 'active': True}
2026-11-27 04:13:41 [INFO] cs2rgbsync.sync_service: GSI evento flashbang_changed -> {'old_intensity': 1, 'intensity': 0, 'active': False}
```

### Etapa em que o evento falhou e causas raiz comprovadas

1. **CS2 → GSI → `GSIServer` → `GSIParser` → `EventManager`:** o CS2 **enviou** `player.state.flashed` na partida de treino, porém o fluxo real apresentou `intensity: 1` ativo por cerca de 2 segundos antes de retornar para `0` (sem sequência decrescente `255..2` no log anterior).
2. **`RGBEngine` + `evaluate_flashbang` (falha crítica de descarte):**
   - Ao receber `intensity = 1`, o `RGBEngine` calculava `1 / 255.0 = 0.00392`.
   - Em `evaluate_flashbang()` (`app/effects.py`), existia o corte `if level <= 0.005: return None`.
   - Com isso, `0.00392 <= 0.005` descartava silenciosamente o evento inteiro da Flashbang e o motor mantinha `idle (0, 0, 0)`, nunca enviando branco ao Corsair iCUE SDK.
3. **Normalização de escala (`GSIParser._to_int`):** se o jogo ou driver enviasse `flashed` como float unitário (`0.0..1.0`, ex. `1.0 -> 0.8 -> 0.2`) ou booleano, `_to_int()` truncava `1.0 -> 1` e `0.95..0.01 -> 0` (e retornava `None` para `bool`).
4. **Substituição imediata e `previously`:**
   - `evaluate_flashbang` nem sempre marcava `instant=True`, permitindo interpolação (`lerp_color`) com a cor anterior nos frames não ascendentes.
   - A limpeza por `previously.player.state.flashed` só rodava quando `player.state` também vinha como bloco no delta.
   - Faltavam logs diagnósticos mostrando o tipo/valor bruto (`raw_value` + `type`) de `player.state.flashed` e a decisão de efeito/cor no `RGBEngine`.

---

## 2. Alterações Implementadas

### 2.1 Flashbang real (`flashed`)

- **`app/gsi_parser.py`:**
  - Adicionado `_parse_intensity_255()`, que normaliza `flashed` e `burning` preservando metadados no `GameStateSnapshot` (`flashed_raw`, `flashed_raw_type`, `flashed_scale`, `flashed_field_seen`), suportando `int` (`0..255`), `float` unitário (`0.0..1.0`), `bool` e strings numéricas (`"str_int"` / `"str_unit"`).
  - Limpeza de `previously.player.state.flashed` / `burning` corrigida para atuar mesmo em payloads delta sem `player.state`.
- **`app/event_manager.py`:**
  - `FLASHBANG_CHANGED` agora inclui `raw_value`, `raw_type`, `scale` e `is_local_player` em `ev.data` (sem tokens ou steamids).
- **`app/effects.py`:**
  - `evaluate_flashbang()` ignora alvos espectados (`is_local_player == False`), removeu o corte `<= 0.005` que descartava `flashed = 1`, garante brilho perceptível enquanto ativo e **sempre** retorna `instant=True` para substituir imediatamente por branco puro (`#FFFFFF` na cor configurada) qualquer cor anterior, sem misturar tons.
- **`app/rgb_engine.py`:**
  - Detecta o comportamento binário real (`0 -> 1 -> 0` em escala `int`/`str_int`), mantendo branco pleno `#FFFFFF` durante toda a cegueira e executando decaimento gradual suave via `binary_fade_ms` (`650 ms` padrão) ao retornar para `0` antes de retomar o efeito de maior prioridade seguinte (ou `idle (0, 0, 0)`).
  - Caso o jogo envie rampa gradual (`255..1` ou `1.0..0.01`), acompanha proporcionalmente a cegueira com curva perceptual (`level ** 0.75`) e decaimento final (`fade_tail_ms = 220 ms`).
- **Limitação conhecida e alternativa não invasiva:**
  - Quando o CS2 envia apenas indicador binário (`1` enquanto cego, `0` ao passar) em vez de valores decrescentes contínuos `255..1`, o GSI oficial da Valve não expõe a opacidade instantânea por frame ao jogador vivo. O comportamento adotado mantém branco sólido durante `flashed=1` e aplica decaimento temporal configurável (`binary_fade_ms`) ao voltar para `0` — 100% passivo via GSI, sem leitura de memória, DLL injection ou hooks.

### 2.2 Logs diagnósticos seguros

- **`app/sync_service.py` (`_consume_gsi_loop`):** registra em nível `INFO` (sem expor `auth.token` nem steamids) as chaves de `player.state`, `flashed_raw` com tipo Python, `burning_raw`, `prev_state_keys`, `activity`, `is_local_player`, valores consolidados no `GSIParser` e eventos emitidos pelo `EventManager`.
- **`app/rgb_engine.py` (`step`):** registra em nível `INFO` as transições de decisão envolvendo `flashbang`, `fire`, `c4` e `idle`, exibindo efeito escolhido, efeito anterior, cor hex aplicada, `flashed`, nível interno e modo binário.

### 2.3 Prioridade do dano por fogo acima da C4

Nova ordem padrão (`config/default_config.json`, `app/effects.py`, `ui/effects_page.py`):

1. `flashbang`
2. `shot`
3. **`fire` (Dano de fogo)**
4. **`c4` (C4 plantada)**
5. `health_critical` *(desativado por padrão)*
6. `health` *(desativado por padrão)*
7. `team_round` *(desativado por padrão)*
8. `weapon` *(desativado por padrão)*

Quando o dano por fogo está ativo (`burning > 0`), interrompe temporariamente a animação da C4; ao encerrar (`burning == 0`), a C4 retoma normalmente preservando o tempo desde `bomb_planted`.

### 2.4 Remoção completa de HE (`he_explosion` / `allgrenades`) e migração segura

- Removido `"allgrenades" "1"` de `app/gsi_config.py` e `gsi/gamestate_integration_cs2rgbsync.cfg`.
- Removidos `GrenadeState`, `grenades` e `_parse_grenades` de `app/gsi_parser.py`.
- Removidos `HE_GRENADE_TYPES`, `EventType.HE_EXPLOSION` e `_detect_he_explosions()` de `app/event_manager.py`.
- Removidos `evaluate_he_explosion()`, campos `he_*` de `EffectInput`, referências em `RGBEngine`, `GSISimulator.build_he_sequence()`, `SyncService`, card/check de HE em `ui/effects_page.py` e botão de HE em `ui/dashboard.py`.
- **Migração segura (`app/config_manager.py` + `config_version: 2`):** ao carregar um `config.json` existente que contenha `"he_explosion"` em `effects` ou `priorities`, ou a ordem legada `["c4", "fire"]`, o aplicativo remove apenas `"he_explosion"` e posiciona `"fire"` antes de `"c4"` na migração para `config_version: 2`, preservando `server.token` e todas as preferências personalizadas do usuário.

---

## 3. Testes Executados e Critérios de Validação

Os testes abaixo representam quatro camadas distintas:

1. **Testes do parser e gerenciador de eventos com payloads representativos (`tests/test_gsi_parser.py`, `tests/test_event_manager.py`):**
   - Payloads reais/representativos cobrindo a sequência real observada `0 -> 1 -> 0`, rampa `255 -> 140 -> 0`, floats normalizados `1.0 -> 0.5 -> 0.0`, booleano, string e limpeza por `previously.player.state.flashed` mesmo sem bloco `player.state`, além de isolamento de espectador (`is_local_player=False`).
2. **Testes de simulação interna e motor RGB (`tests/test_effects.py`, `tests/test_rgb_engine.py`, `tests/test_ui.py`):**
   - Validação de `flashed=1` substituindo imediatamente `fire` por `#FFFFFF` sem mistura de cor, decaimento suave até retomar `fire` e depois `c4`, prioridade `fire > c4`, ausência de `he_explosion` na UI e logs diagnósticos mascarados (sem token).
   - **Resultado da suíte completa (`.venv\Scripts\python.exe -m pytest -v`):** **`40 passed in 3.60s`** (0 falhas, 0 ignorados).
3. **Teste físico do LED pelo iCUE SDK (`tools/test_effects_v2_hardware.py`):**
   - Executado diretamente no **Corsair Katar Pro XT** (saída `0`):
     - `idle` em partida com `rgb=(0, 0, 0)` / `sdk_rgba=(0, 0, 0, 255)`;
     - Flashbang gradual (`255 -> #FFFFFF`, `140 -> #E2E2E2`, decaimento `#818181`) e sequência binária real `flashed=1 -> #FFFFFF` com decaimento suave;
     - Disparo `#FF9900`;
     - C4 interrompida por `fire #FE7800` -> retorno à C4 -> interrupção por Flashbang -> retorno à C4 até desarme -> `idle (0, 0, 0)` e devolução limpa do controle (`SDK=1`).
4. **Atualização real do `.cfg` e migração do usuário:**
   - `--setup-gsi "D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive\game\csgo"` removeu `"allgrenades"` do arquivo instalado no CS2 (`has_allgrenades: False`).
   - Validado em `%LOCALAPPDATA%\CS2RGBSync\config.json` que `config_version` subiu para `2`, `"he_explosion"` foi removido, `priorities` passou para `['flashbang', 'shot', 'fire', 'c4', 'health_critical', 'health', 'team_round', 'weapon']`, e `server.token` (32 caracteres), `effects.shot` (`#FF4000`, `61 ms`) e `health`/`team`/`weapons = False` foram integralmente preservados.

### O que ainda depende de validação em partida real no CS2

- **Flashbang real em jogo (modo treino ou partida):** validar na prática com flashbang própria, de aliado e de inimigo para confirmar no novo `cs2rgbsync.log` (`GSI diagnóstico -> ...` e `RGBEngine decisão: ...`) o comportamento exato do LED na rodinha do mouse durante a cegueira e o retorno ao efeito anterior.
- **Dano de fogo real sobrepondo C4:** validar em partida real pisando em Molotov/incendiária com a C4 plantada para confirmar se a versão atual do CS2 envia `player.state.burning > 0` nessas condições e o retorno à C4 após sair do fogo.
