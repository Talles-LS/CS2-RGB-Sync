# ETAPA 1 — Análise Técnica e Compatibilidade do Corsair Katar Pro XT com o iCUE SDK

## 1. Objetivo desta Etapa
Validar a arquitetura oficial de comunicação entre Python 3.12 (64 bits), o **Corsair iCUE SDK v4** e o mouse **Corsair Katar Pro XT** antes de iniciar o desenvolvimento do servidor GSI e da interface gráfica do **CS2 RGB Sync**.

---

## 2. Arquitetura Real do SDK Verificada

A integração utiliza o wrapper oficial em Python **`cuesdk` (versão `4.0.84`)**, que realiza chamadas via `ctypes` diretamente para a biblioteca nativa 64 bits fornecida no próprio pacote:

```text
Python 3.12 (64-bit)
  └── cuesdk 4.0.84 (cuesdk/api.py -> cuesdk/native/capi.py via ctypes.CDLL)
        └── iCUESDK.x64_2019.dll (509.992 bytes, PE AMD64 / 0x8664)
              └── IPC local com o serviço/aplicativo Corsair iCUE 5
                    └── Corsair Katar Pro XT (LED da rodinha / scroll wheel)
```

### Verificações de Ambiente Realizadas
- **Python:** `3.12.10` `[MSC v.1943 64 bit (AMD64)]` (64 bits).
- **DLL Nativa:** `.venv\Lib\site-packages\cuesdk\bin\iCUESDK.x64_2019.dll` — arquitetura confirmada `0x8664` (`AMD64`), 509.992 bytes.
- **Dependência de Sistema (Windows 11 x64):** Microsoft Visual C++ Redistributable 2019/2022 x64 (presente junto à instalação do iCUE 5 em `C:\Program Files\Corsair\Corsair iCUE5 Software\vc_redist.x64.exe`).
- **Software Base Detectado:** `C:\Program Files\Corsair\Corsair iCUE5 Software\iCUE.exe`.

---

## 3. API Real Inspecionada no Pacote `cuesdk==4.0.84`

Todos os símbolos abaixo foram verificados diretamente nos arquivos `.venv\Lib\site-packages\cuesdk\api.py`, `enums.py`, `structs.py`, `native/capi.py` e `native/structs.py`:

### 3.1 Sessão e Ciclo de Vida
- `CueSdk.connect(on_state_changed)` → retorna `CorsairError`.
  - O callback recebe `CorsairSessionStateChanged(state: CorsairSessionState, details: CorsairSessionDetails)`.
  - Estados possíveis (`CorsairSessionState`): `CSS_Invalid (0)`, `CSS_Closed (1)`, `CSS_Connecting (2)`, `CSS_Timeout (3)`, `CSS_ConnectionRefused (4)`, `CSS_ConnectionLost (5)`, `CSS_Connected (6)`.
  - Observação importante: `CSS_ConnectionRefused` ocorre tipicamente quando o controle via SDK está desabilitado nas configurações do iCUE 5 (Configurações → SDK → Habilitar SDK de jogos/aplicativos).
- `CueSdk.get_session_details()` → `(CorsairSessionDetails | None, CorsairError)` com `client_version`, `server_version`, `server_host_version`.
- `CueSdk.disconnect()` → `CorsairError`.

### 3.2 Enumeração de Dispositivos e Eventos de Conexão
- `CueSdk.get_devices(CorsairDeviceFilter(device_type_mask=...))` → `(list[CorsairDeviceInfo] | None, CorsairError)`.
  - Filtros relevantes: `CorsairDeviceType.CDT_Mouse (0x0002)` e `CorsairDeviceType.CDT_All (0xFFFFFFFF)`.
  - Cada `CorsairDeviceInfo` contém: `type`, `device_id` (string única de até 128 bytes), `serial`, `model`, `led_count`, `channel_count`.
- `CueSdk.get_device_info(device_id)` → `(CorsairDeviceInfo | None, CorsairError)`.
- `CueSdk.subscribe_for_events(on_event)` / `unsubscribe_from_events()`:
  - Recebe `CorsairEvent` com `CEI_DeviceConnectionStatusChangedEvent` (`device_id`, `is_connected`), permitindo detectar desconexão e reconexão física do Katar Pro XT sem polling agressivo.

### 3.3 Consulta de LEDs e Controle de Iluminação
- `CueSdk.get_led_positions(device_id)` → `(list[CorsairLedPosition] | None, CorsairError)`.
  - Cada `CorsairLedPosition` possui `id` (`CorsairLedLuid`, `uint32`), `cx` (`double`) e `cy` (`double`).
  - No SDK v4, não se utiliza o enum legado `CorsairLedId` para mouses; os IDs reais são retornados dinamicamente por `get_led_positions(device_id)`.
- `CueSdk.set_layer_priority(priority)` → `CorsairError` (`0..255`, máximo `CORSAIR_LAYER_PRIORITY_MAX = 255`).
- `CueSdk.request_control(device_id, access_level)` / `release_control(device_id)`:
  - `CorsairAccessLevel.CAL_Shared (0)` ou `CAL_ExclusiveLightingControl (1)`.
  - Ao encerrar ou desativar a integração, liberar o controle ou enviar `a=0` devolve o LED ao perfil configurado pelo usuário no iCUE.
- `CueSdk.set_led_colors(device_id, led_colors)` → `CorsairError` (síncrono).
- `CueSdk.set_led_colors_buffer(device_id, led_colors)` + `set_led_colors_flush_buffer_async(callback)` → atualização em buffer/assíncrona recomendada para o loop de animação de 20–30 ms.
- `CueSdk.get_led_colors(device_id, led_colors)` → `(list[CorsairLedColor] | None, CorsairError)`.
- `CorsairLedColor(id, r, g, b, a)`:
  - `r, g, b` em `[0..255]`.
  - `a` em `[0..255]`: `255` = opaco (cor aplicada integralmente), `0` = transparente (perfil do iCUE aparece por baixo). Para apagar fisicamente o LED mantendo controle ativo, envia-se `(r=0, g=0, b=0, a=255)`.

### 3.4 Peculiaridades Técnicas Encontradas no `cuesdk==4.0.84`
Durante a leitura do código-fonte e validação real do `cuesdk`, foram identificados três pontos críticos de atenção para o desenvolvimento:
1. **`CueSdk.disconnect()` (`cuesdk/api.py`, linhas 91–93) — BUG CRÍTICO DE CALLBACK:** o wrapper executa `self.session_state_changed_event_handler = None` **antes** de chamar `napi.CorsairDisconnect()`. Como a DLL nativa `iCUESDK.x64_2019.dll` dispara o evento `CSS_Closed` no callback durante `CorsairDisconnect()`, a liberação antecipada do objeto `CFUNCTYPE` pelo coletor de lixo causa falha nativa (`0xC000001D` / `STATUS_ILLEGAL_INSTRUCTION`). **Solução:** manter referência ao callback até depois do retorno de `CorsairDisconnect()`.
2. **`CorsairGetLedColors` (`cuesdk/native/capi.py`, linha 129):** o `restype` está declarado como `c_bool` em vez de `CorsairError`. Na prática, `CE_Success (0)` vira `False` -> `CorsairError(0)` (`CE_Success`), mas qualquer código de erro diferente de `0` é convertido em `True` -> `CorsairError(1)` (`CE_NotConnected`). Além disso, o cache interno do iCUE leva ~20–50 ms para refletir uma cor recém-enviada na leitura de retorno.
3. **`set_led_colors_flush_buffer_async` (`cuesdk/api.py`, linha 307):** quando um `callback` não-nulo é passado ao método wrapper, o objeto `CFUNCTYPE` (`async_callback`) é criado em variável local sem referência persistente na instância. Para evitar coleta de lixo (GC) em chamadas assíncronas de alta frequência, deve-se passar `callback=None` ou manter referência explícita ao callback C na camada nativa.

---

## 4. Licenciamento e Redistribuição
- **Wrapper Python (`cue-sdk-python` / `cuesdk`):** Licença **MIT** (`Copyright (c) 2020 Corsair Memory, Inc.`), permitindo uso, modificação e distribuição comercial/não-comercial mantendo o aviso de copyright.
- **SDK Nativo da Corsair (`iCUESDK.x64_2019.dll`):** Software proprietário da **Corsair Memory, Inc.**, regido pelo EULA oficial do iCUE SDK. A distribuição deve manter a DLL original inalterada (sem engenharia reversa ou modificação) e exige o software oficial **Corsair iCUE** instalado e em execução na máquina do usuário para operar.
- **Outros componentes planejados:** Python 3.12 (PSF License), PySide6 (LGPL v3), FastAPI/Uvicorn ou Flask (MIT/BSD), psutil (BSD-3-Clause), pytest (MIT), PyInstaller (GPLv2 com exceção de bootloader), Inno Setup (licença gratuita própria). Nenhuma API paga ou serviço em nuvem é utilizado.

---

## 5. Estratégia Específica para o Corsair Katar Pro XT
- O **Corsair Katar Pro XT** possui **1 zona RGB principal** na rodinha de rolagem (scroll wheel).
- O aplicativo atuará **exclusivamente sobre iluminação LED** via iCUE SDK:
  - **Não** lerá nem gravará propriedades de DPI, polling rate, macros, remapeamento de botões ou perfis de memória interna.
  - Identificará o dispositivo filtrando `CDT_Mouse` cujo campo `model` corresponda a `"KATAR PRO XT"` (insensível a maiúsculas/minúsculas).
  - Descobrirá dinamicamente os LUIDs via `get_led_positions(device_id)` para evitar dependência de IDs fixos.

---

## 6. Plano de Contingência (OpenRGB SDK)
Caso a prova real da **ETAPA 2** demonstre que o iCUE SDK v4 não enxerga o Katar Pro XT ou não consegue alterar fisicamente a cor da rodinha:
1. Investigar a integração via **OpenRGB SDK** (servidor SDK local em `127.0.0.1:6742` com `openrgb-python`), pois o Katar Pro XT possui suporte documentado no OpenRGB.
2. Documentar ao usuário a restrição conhecida de exclusividade (OpenRGB requer o encerramento completo do iCUE para evitar conflito de acesso USB HID ao mouse).
3. Não implementar comunicação USB HID direta antes de validar totalmente iCUE SDK e OpenRGB SDK.
