# ETAPA 3 — Integração com CS2 Game State Integration (GSI)

## 1. Arquitetura Implementada

Nesta etapa foi implementada a camada de configuração persistente, detecção automática do Counter-Strike 2, geração segura do arquivo GSI e servidor HTTP local estrito em `127.0.0.1`:

```text
Counter-Strike 2 (Engine Source 2 - API oficial GSI)
  └── HTTP POST -> http://127.0.0.1:3000/ (token local em auth.token)
        └── GSIServer (app/gsi_server.py - Flask + ThreadedWSGIServer)
              ├── Validação de JSON (HTTP 400 se inválido)
              ├── Validação de token com hmac.compare_digest (HTTP 401 se inválido)
              ├── Sanitização do payload (auth.token -> ***REDACTED***)
              ├── Resposta imediata HTTP 200 (sem bloquear em chamadas RGB)
              └── queue.Queue(maxsize=256) -> fila interna de eventos (GSIRawMessage)
```

---

## 2. Segurança e Compatibilidade com VAC

- O aplicativo utiliza **exclusivamente** a API oficial **Game State Integration (GSI)** da Valve, configurada por arquivo `.cfg` na pasta `game\csgo\cfg`.
- **Nenhuma** técnica invasiva é utilizada: não há `ReadProcessMemory`, `WriteProcessMemory`, injeção de DLL, hooks no processo do CS2, drivers próprios, alteração de binários do jogo ou automação de entrada.
- **Nenhum** outro arquivo da instalação do CS2 é modificado: apenas `gamestate_integration_cs2rgbsync.cfg` é gravado (com escrita atômica via `.cfg.tmp`).
- A desinstalação condicional (`uninstall_gsi_cfg`) remove o arquivo somente se ele contiver o cabeçalho gerenciado `// Managed by CS2 RGB Sync - Do not share auth token`.
- **Nota de transparência:** embora o GSI seja uma API oficial fornecida pela própria Valve para telemetria local de eventos de partida, nenhum software de terceiros pode afirmar garantia absoluta contra falsos positivos futuros de sistemas anti-cheat; o projeto limita-se estritamente ao papel de receptor passivo HTTP local e controlador de iluminação do periférico externo via Corsair iCUE SDK.

---

## 3. Segurança do Servidor Local e Proteção de Token

- **Bind estrito em loopback:** `GSIServer` e `ConfigManager` exigem `host == "127.0.0.1"`. Qualquer tentativa de configurar ou iniciar com `0.0.0.0` ou IP externo lança `ValueError`. O servidor não fica exposto à rede local (LAN) nem à internet.
- **Token local automático:** gerado via `secrets.token_urlsafe(24)` (32 caracteres) na primeira inicialização e persistido em `%LOCALAPPDATA%\CS2RGBSync\config.json`.
- **Redação em logs e diagnóstico:** `TokenRedactingFilter` substitui o token em todas as mensagens e argumentos de log por `***REDACTED***`, e `sanitize_payload()` mascara `auth.token` antes de armazenar `last_payload` ou enfileirar `GSIRawMessage`.

---

## 4. Instalação Real do Arquivo GSI no CS2

- **Caminho detectado:** `D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive\game\csgo`
- **Arquivo instalado:** `D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg\gamestate_integration_cs2rgbsync.cfg` (418 bytes)
- **Demais arquivos preservados:** verificado que arquivos pré-existentes na pasta `cfg` (como `gamestate_integration_medal.cfg`) permaneceram intactos.
- **Parâmetros configurados no `.cfg`:**
  - `uri`: `http://127.0.0.1:3000/`
  - `timeout`: `5.00`
  - `buffer`: `0.05`
  - `throttle`: `0.05`
  - `heartbeat`: `15.0`
  - `data`: `provider`, `map`, `round`, `player_id`, `player_state`, `player_weapons`, `player_match_stats` (somente os dados necessários aos efeitos).

---

## 5. Resultados dos Testes Executados

### 5.1 Suíte Automatizada (`pytest -v`)
- **11 testes executados, 11 aprovados (0 falhas)** em `1.43s`:
  - `tests/test_config.py` (6 testes): geração/persistência de token, bloqueio de host não-loopback e porta inválida, redação do token nos logs e payload, parsing de `libraryfolders.vdf` priorizando AppID `730`, detecção/instalação/remoção condicional sem alterar outros arquivos e validação de parâmetros de `.cfg`.
  - `tests/test_gsi_server.py` (5 testes): rejeição de bind fora de `127.0.0.1`, recepção HTTP 200 com mascaramento de token, rejeição HTTP 401 para token ausente/inválido, tratamento HTTP 400 para JSON inválido e HTTP 200 para payload parcial, e descarte não bloqueante do evento mais antigo em rajada + reinício limpo.

### 5.2 Validação Real em Loopback (`tools/gsi_live_probe.py --self-test`)
- `1) POST válido -> HTTP 200 (35.92 ms)`
- `2) POST token inválido -> HTTP 401 (2.33 ms)`
- `3) POST JSON inválido -> HTTP 400 (2.30 ms)`
- `4) POST parcial -> HTTP 200 (2.14 ms)`
- `[STATS] recebidas=4, aceitas=2, falhas_token=1, erros_json=1, fila=2, token_em_diag=***REDACTED***`

---

## 6. Limitações Conhecidas desta Etapa
1. **Latência/agrupamento do GSI:** o CS2 agrupa atualizações respeitando `buffer` (`0.05s`) e `throttle` (`0.05s`). O envio real pelo jogo durante uma partida depende do CS2 estar aberto e carregado com o arquivo `gamestate_integration_cs2rgbsync.cfg` presente antes da inicialização do jogo (ou recarregado pelo jogo).
2. **Testes com socket no ambiente sandbox:** a execução de testes que abrem sockets TCP em `127.0.0.1` requer execução fora do sandbox restrito de rede do Windows (`WinError 10013` quando executado dentro da sandbox).
