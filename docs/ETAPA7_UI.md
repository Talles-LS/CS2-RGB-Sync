# ETAPA 7 — Interface Gráfica Desktop (PySide6)

## 1. Arquitetura Desacoplada

A interface gráfica foi construída com **PySide6 (`6.12.0`)** sobre uma fachada desacoplada (`app/sync_service.py`), preservando integralmente os módulos validados nas etapas anteriores (`gsi_server.py`, `gsi_parser.py`, `event_manager.py`, `effects.py`, `rgb_engine.py`, `icue_controller.py`):

```text
PySide6 MainWindow (Thread Qt - nunca bloqueia)
  ├── Ações assíncronas (Iniciar/Parar em thread auxiliar + QTimer 100 ms)
  └── SyncService (app/sync_service.py)
        ├── GSIServer (127.0.0.1:porta) -> queue.Queue -> CS2RGBSync-EventConsumer
        ├── GSIParser + EventManager -> RGBEngine (tick 25 ms)
        ├── ICueController (Corsair Katar Pro XT)
        ├── GSISimulator (modo de simulação isolado com banner visual)
        └── ConfigManager (%LOCALAPPDATA%\CS2RGBSync\config.json)
```

---

## 2. Telas e Recursos Implementados

1. **Painel (`ui/dashboard.py`):**
   - Botão principal **INICIAR INTEGRAÇÃO / PARAR INTEGRAÇÃO** executado em thread auxiliar para não travar a interface durante o handshake do iCUE.
   - 4 cartões de status em tempo real: **Corsair iCUE**, **Katar Pro XT**, **Servidor GSI** e **Counter-Strike 2**.
   - Prévia visual da rodinha (`ColorPreviewWheel`) mostrando a cor `#RRGGBB` aplicada e o efeito controlador atual.
   - Telemetria da partida (Vida, Equipe, Fase/Bomba, Arma e Munição).
   - Painel de **Modo de Simulação** com banner explícito de aviso e controles manuais (Flashbang, Disparo, C4, Fogo, Vida, Equipe, Freezetime, Round Ativo, 7 categorias de Armas e Desconexão).

2. **Efeitos RGB (`ui/effects_page.py`):**
   - Ativação/desativação individual para **Flashbang**, **Disparos**, **C4**, **Dano de Fogo**, **Vida/Vida Crítica**, **Equipe/Freezetime** e **Armas**.
   - Edição de cores (`ColorPickerButton` + `QColorDialog`), intensidade (`0–100%`), duração de disparo (`ms`), debounce (`ms`), timer/frequências da C4 (`s` e `Hz`), velocidade de fogo/freezetime (`Hz`) e reordenação visual de prioridades (`Subir` / `Descer`).
   - Botões **Aplicar e Salvar** e **Restaurar Padrões**.

3. **Configurações (`ui/settings_page.py`):**
   - Endereço fixo `127.0.0.1` (somente leitura), porta HTTP configurável (`1024–65535`), token GSI mascarado (com opção Revelar/Ocultar e Regenerar Token + Atualizar GSI).
   - Detecção automática/seleção manual da pasta do CS2 e botão **Instalar / Atualizar Arquivo GSI**.
   - Caminho opcional da DLL do SDK, brilho global (`0–100%`), frequência do motor (`15–100 ms`), restauração ao encerrar, inicialização com Windows (`HKCU\...\Run` via `app/windows_startup.py`), minimizar para bandeja e iniciar integração automaticamente.
   - Botão **Restaurar Configurações Padrão** preservando o token GSI para não invalidar o `.cfg` instalado.

4. **Diagnóstico (`ui/diagnostics_page.py`):**
   - Estado do SDK, dispositivo identificado, último comando RGBA, estatísticas do servidor GSI, latência de software/SDK, último payload GSI com `auth.token` mascarado (`***REDACTED***`), lista de eventos recentes e visualizador de logs com botão **Copiar Logs**.

5. **Bandeja do Sistema (`ui/main_window.py`):**
   - Ícone próprio (`assets/icons/cs2_rgb_sync.ico` e `.png`), menu de contexto (`Abrir Painel`, `Iniciar/Parar Integração`, `Sair`) e encerramento seguro liberando o iCUE ao sair.

---

## 3. Resultados dos Testes Executados

1. **`tools/generate_icon.py` e `py_compile`:** ícones PNG/ICO gerados e todos os módulos compilados sem erros (código `0`).
2. **`pytest -v` (suíte completa acumulada):** **30 testes executados, 30 aprovados (0 falhas)** em `2.96s`, incluindo `tests/test_ui.py` (`QT_QPA_PLATFORM=offscreen`), validando:
   - Navegação entre todas as 4 abas.
   - Fluxo completo Iniciar Integração -> HTTP POST GSI real em `127.0.0.1` -> atualização do Dashboard e controlador.
   - Diagnóstico com token mascarado (`***REDACTED***`).
   - Edição/persistência de efeitos e restauração de padrões.
   - Modo de simulação com banner visível e envio de cor ao controlador.
   - Parada e encerramento seguro liberando o controlador.
