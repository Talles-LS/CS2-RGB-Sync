# ETAPA 4 — Interpretador JSON GSI e Gerenciador de Eventos

## 1. Arquitetura Implementada

Nesta etapa foram criados os dois módulos responsáveis por transformar o fluxo bruto de payloads JSON do CS2 GSI em estado consolidado e eventos semânticos de partida:

```text
GSIRawMessage (fila HTTP)
  └── GSIParser (app/gsi_parser.py)
        ├── Trata payloads completos e parciais preservando último estado válido
        ├── Processa blocos `previously` / `previous` e `added`
        ├── Diferencia explicitamente campo ausente vs valor numérico 0
        └── Produz GameStateSnapshot (imutável)
              └── EventManager (app/event_manager.py)
                    ├── Compara snapshot atual x anterior
                    ├── Detecta disparos via delta de `ammo_clip` com proteções
                    ├── Monitora timeout de heartbeat/desconexão
                    └── Emite lista ordenada de GameEvent (com timestamps ns)
```

---

## 2. Regras do `GSIParser` (`app/gsi_parser.py`)

### 2.1 Preservação de Estado e Ausência vs Zero
- Em atualizações parciais (como heartbeats contendo apenas `provider`, ou deltas contendo apenas `player.state.health`), os demais campos válidos anteriores (`team`, `armor`, `flashed`, `bomb_state`, `active_weapon`, etc.) são integralmente preservados.
- Todas as leituras numéricas (`health`, `armor`, `flashed`, `burning`, `ammo_clip`) verificam **presença explícita da chave** (`"health" in state_block`) e conversão segura de tipo. Nunca é usada avaliação booleana (`if state.get("health"):`), evitando confundir ausência de chave com `0` (0 HP, 0 flashed, 0 munição).

### 2.2 Blocos `previously` / `previous` e `added`
- O interpretador aceita tanto `"previously"` (padrão oficial do CS2) quanto `"previous"` (fallback defensivo) e `"added"`.
- Quando `round` aparece sem `bomb`, mas `previously.round` contém `bomb` (ou `round.phase == "freezetime"`), `bomb_state` é limpo para `None`.
- Quando `player.activity == "menu"` ou `map`/`round`/`player` constam em `previously` sem bloco correspondente no payload atual, estados voláteis da partida (`round_phase`, `bomb_state`, `flashed`, `burning`, `active_weapon`) são limpos enquanto `connected` permanece `True` (o jogo segue aberto no menu).

### 2.3 Espectador e Classificação de Armas
- `is_local_player` compara `provider.steamid` e `player.steamid`: quando ambos existem e diferem, indica que o usuário está morto espectando outro jogador (`is_local_player=False`).
- `classify_weapon()` categoriza armas do CS2 em `knife`, `pistol`, `sniper`, `rifle`, `smg`, `shotgun`, `grenade`, `c4` e `other`.

---

## 3. Regras do `EventManager` (`app/event_manager.py`)

### 3.1 Eventos Suportados (`EventType`)
- `CONNECTION_CHANGED` (conexão inicial, timeout de heartbeat e reconexão)
- `ROUND_PHASE_CHANGED` (`freezetime`, `live`, `over`)
- `TEAM_CHANGED` (`CT` / `T`)
- `HEALTH_CHANGED` (inclui `delta`, `is_critical` abaixo de 25 HP e `is_dead`)
- `FLASHBANG_CHANGED` (`intensity` 0..255 e `active`)
- `FIRE_CHANGED` (somente quando `burning_field_seen == True`)
- `BOMB_PLANTED`, `BOMB_DEFUSED`, `BOMB_EXPLODED`, `BOMB_CLEARED`
- `WEAPON_CHANGED`, `RELOAD_STARTED`, `RELOAD_FINISHED`
- `SHOT_FIRED` (inclui `received_at_ns` e `detected_at_ns` para medição de latência)

### 3.2 Detecção de Disparos e Proteção contra Falsos Positivos
Um evento `SHOT_FIRED` só é emitido quando `prev.ammo_clip > curr.ammo_clip >= 0` **e** todas as travas abaixo são satisfeitas:
1. Conexão ativa nos dois snapshots consecutivos (bloqueia disparos fantasma na conexão/reconexão).
2. `player.activity == "playing"` e `is_local_player == True` (ignora menus e espectador de aliados).
3. Jogador vivo (`health > 0` ou desconhecido) e fora de `freezetime` / transição de novo round.
4. Mesma arma no mesmo slot (`curr.name == prev.name` e `curr.slot == prev.slot`) e compatibilidade de `ammo_clip_max`.
5. Categoria balística válida (exclui `knife`, `grenade`, `c4`, `other`).
6. Nenhum dos dois snapshots com `state == "reloading"`.
7. Respeito ao intervalo configurável `shot_debounce_ms` (padrão `40.0 ms`).

---

## 4. Limitações Documentadas dos Campos do GSI

1. **Agrupamento de disparos (`ammo_clip`):** como o CS2 envia atualizações respeitando `buffer` (`0.05s`) e `throttle` (`0.05s`), armas de alta cadência podem reduzir `ammo_clip` em mais de 1 unidade entre duas requisições HTTP consecutivas (ex.: `30 -> 27`). Nesses casos, `EventManager` sinaliza `bullets_delta=3` e `grouped_shots=True`, mas **não** é possível garantir um pulso separado para cada projétil individual via GSI.
2. **Campo de queimadura (`player.state.burning`):** a presença e atualização desse campo dependem do que a versão atual do CS2 expõe no payload GSI para o jogador local (em alguns cenários ou versões do jogo, `burning` pode não estar presente ou permanecer `0`). O interpretador só marca `burning_field_seen=True` e emite `FIRE_CHANGED` quando o campo real aparece no JSON — sem inventar valores nem recorrer a leitura de memória.
3. **Tempo restante da C4:** para um jogador vivo em partida competitiva normal, `round.bomb` informa `"planted"`, `"defused"` ou `"exploded"`, **sem** enviar contagem regressiva exata em segundos. O `EventManager` registra `planted_at_ns` no instante da detecção de `"planted"` para permitir aproximação local configurável (padrão `40.0s`) na Etapa 5/6.
4. **Espectador pós-morte:** ao morrer e passar a espectar um aliado, o CS2 passa a enviar os dados do jogador espectado em `player.*` (`player.steamid != provider.steamid`). O `is_local_player=False` permite evitar falsos disparos atribuídos ao aliado.

---

## 5. Resultados dos Testes Executados
- **`py_compile`:** `app/gsi_parser.py`, `app/event_manager.py`, `tools/gsi_live_probe.py` — código de saída `0`.
- **`pytest -v` (suíte acumulada):** **19 testes executados, 19 aprovados (0 falhas)** em `1.87s`:
  - `tests/test_config.py`: 6/6 aprovados.
  - `tests/test_gsi_server.py`: 5/5 aprovados.
  - `tests/test_gsi_parser.py`: 5/5 aprovados.
  - `tests/test_event_manager.py`: 3/3 aprovados.
- **`tools/gsi_live_probe.py --self-test`:** HTTP `200`/`401`/`400`/`200` validado sem regressões.
