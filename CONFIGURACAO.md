# Guia de Configuração — CS2 RGB Sync

## 1. Local de Persistência no Windows

Todas as configurações do usuário e logs ficam armazenados por usuário, preservados durante atualizações do aplicativo:

- **Arquivo de configuração:** `%LOCALAPPDATA%\CS2RGBSync\config.json`
- **Arquivos de log:** `%LOCALAPPDATA%\CS2RGBSync\logs\cs2rgbsync.log` (rotação automática de até 2 MB x 3 arquivos; tokens são sempre mascarados como `***REDACTED***`).
- **Configuração padrão de fábrica:** `config/default_config.json` (somente leitura no pacote).

---

## 2. Parâmetros do Arquivo `config.json`

### `server`
- `host`: fixo em `"127.0.0.1"` (o aplicativo rejeita qualquer tentativa de expor o servidor à rede local ou internet).
- `port`: porta HTTP local padrão `3000` (faixa permitida: `1024` a `65535`).
- `token`: segredo local compartilhado com o arquivo GSI do CS2, gerado automaticamente na primeira execução.

### `gsi`
- `cs2_path`: caminho da pasta `...\Counter-Strike Global Offensive\game\csgo`.
- `buffer`: `0.05` s (janela de agrupamento de pacotes no CS2).
- `throttle`: `0.05` s (intervalo mínimo entre POSTs do CS2).
- `timeout`: `5.0` s.
- `heartbeat`: `15.0` s (envio periódico mesmo sem mudanças de estado).
- `disconnect_timeout_s`: `35.0` s (tempo sem pacotes até considerar o CS2 desconectado e restaurar a iluminação padrão do dispositivo).

### `hardware`
- `sdk_path`: caminho opcional de uma DLL customizada do iCUE SDK (vazio usa `iCUESDK.x64_2019.dll` embutida).
- `target_model`: `""` (vazio seleciona automaticamente qualquer dispositivo Corsair com zonas RGB; pode ser preenchido para filtrar um modelo específico).
- `layer_priority`: `200` (prioridade da camada SDK no iCUE, `0..255`).
- `exclusive_control`: `false` por padrão (permite devolver o controle ao iCUE imediatamente ao enviar `alpha=0`).
- `restore_on_exit`: `true` (restaura a iluminação do perfil do usuário ao encerrar).
- `global_brightness`: `0..100` (%).

### `engine`
- `tick_ms`: intervalo de renderização do motor RGB (`25` ms padrão, configurável entre `15` e `100` ms).
- `simulation_mode`: `false` por padrão (quando `true`, exibe banner explícito de simulação na interface).

### `priorities`
Ordem padrão (topo = maior prioridade):
`["flashbang", "shot", "fire", "c4", "health_critical", "health", "team_round", "weapon"]`

### `effects`
Por padrão, apenas efeitos reativos de partida começam ativados (`flashbang`, `shot`, `fire`, `c4`). Os efeitos permanentes de estado (`health`, `team`, `weapons`) vêm desativados (`enabled: false`), mantendo o LED apagado `(0, 0, 0)` durante momentos neutros da partida até que você opte por ativá-los manualmente na interface.

- `flashbang`: `enabled` (`true`), `color` (`#FFFFFF`), `fade_tail_ms` (`220`), `binary_fade_ms` (`650`), `intensity` (`100`).
- `shot`: `enabled` (`true`), `color` (`#FF9900`), `duration_ms` (`50`), `debounce_ms` (`40`), `intensity` (`100`).
- `fire`: `enabled` (`true`), `color_primary` (`#FF2200`), `color_secondary` (`#FF9900`), `oscillation_hz` (`4.0`), `intensity` (`100`).
- `c4`: `enabled` (`true`), `color` (`#FF0000`), `bomb_timer_s` (`40.0`), `initial_interval_s` (`1.0`), `min_interval_s` (`0.15`), `beep_duration_s` (`0.24`), `intensity` (`100`).
- `health`: `enabled` (`false`), `critical_threshold` (`25`), `critical_pulse_hz` (`2.5`), `color_100` (`#00FF00`), `color_75` (`#80FF00`), `color_50` (`#FFFF00`), `color_25` (`#FF9900`), `color_critical` (`#FF0000`), `intensity` (`100`).
- `team`: `enabled` (`false`), `t_color` (`#FF9900`), `ct_color` (`#008CFF`), `freezetime_pulse` (`true`), `freezetime_pulse_hz` (`0.8`), `intensity` (`100`) — aplicado exclusivamente durante o Freezetime.
- `weapons`: `enabled` (`false`), `intensity` (`100`), `categories` (`knife`, `pistol`, `rifle`, `sniper`, `smg`, `shotgun`, `grenade`).

---

## 3. Arquivo GSI no CS2

Local de instalação:
`<BibliotecaSteam>\steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg\gamestate_integration_cs2rgbsync.cfg`

Se a porta ou o token forem alterados na aba **Configurações**, clique em **Instalar / Atualizar Arquivo GSI** (ou use **Regenerar Token**) e reinicie o CS2 caso o jogo já esteja aberto.
