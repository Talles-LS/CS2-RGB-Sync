"""Gera o arquivo MANUAL_INSTALACAO.pdf em português brasileiro via PySide6."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMarginsF  # noqa: E402
from PySide6.QtGui import QGuiApplication, QPageLayout, QPageSize, QPdfWriter, QTextDocument  # noqa: E402

MANUAL_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8" />
<style>
  body { font-family: "Segoe UI", Arial, sans-serif; color: #1F2328; font-size: 10.5pt; line-height: 1.45; }
  h1 { color: #0B192C; border-bottom: 3px solid #FF9900; padding-bottom: 6px; font-size: 20pt; }
  h2 { color: #005FB8; margin-top: 16px; font-size: 13pt; border-left: 4px solid #FF9900; padding-left: 8px; }
  code { background-color: #F3F4F6; padding: 2px 5px; border-radius: 3px; font-family: Consolas, monospace; font-size: 9.5pt; }
  .box { background-color: #FFF8EC; border: 1px solid #FF9900; padding: 8px 12px; border-radius: 4px; margin: 8px 0; }
  ul, ol { margin-top: 4px; margin-bottom: 8px; }
</style>
</head>
<body>
  <h1>Manual de Instalação e Uso — CS2 RGB Sync</h1>
  <p><strong>Versão:</strong> 0.2.0 &nbsp;|&nbsp; <strong>Plataforma:</strong> Windows 11 (64 bits) &nbsp;|&nbsp; <strong>Idiomas:</strong> English (padrão), Português (Brasil), Español &nbsp;|&nbsp; <strong>Hardware:</strong> Dispositivos Corsair compatíveis com iCUE SDK</p>
  <div class="box">
    <strong>Arquitetura 100% Local e Segura:</strong> O CS2 RGB Sync utiliza exclusivamente a API oficial
    <em>Game State Integration (GSI)</em> da Valve em <code>127.0.0.1</code> e o <em>Corsair iCUE SDK</em> oficial.
    Não realiza leitura de memória, injeção de DLL, hooks ou automação de jogabilidade, e não usa APIs pagas nem serviços em nuvem.
  </div>

  <h2>1. Como instalar o Corsair iCUE</h2>
  <ol>
    <li>Baixe e instale o software oficial <strong>Corsair iCUE 5</strong> no site da Corsair (<code>corsair.com/icue</code>).</li>
    <li>Conclua a instalação e reinicie o computador caso solicitado.</li>
    <li>Mantenha o iCUE em execução em segundo plano sempre que for usar o CS2 RGB Sync.</li>
  </ol>

  <h2>2. Como conectar seu dispositivo Corsair</h2>
  <ol>
    <li>Conecte o dispositivo RGB <strong>Corsair</strong> compatível com o iCUE diretamente ao computador.</li>
    <li>Abra o Corsair iCUE e confirme que o hardware aparece reconhecido na tela inicial.</li>
    <li><em>Observação:</em> o CS2 RGB Sync controla apenas a iluminação RGB e nunca altera DPI, perfis, botões ou macros.</li>
  </ol>

  <h2>3. Como configurar o SDK no iCUE</h2>
  <ol>
    <li>No Corsair iCUE 5, clique no ícone de <strong>Configurações</strong> (engrenagem).</li>
    <li>Acesse a aba <strong>SDK</strong>.</li>
    <li>Ative a opção de <strong>SDK do iCUE / Integrações de jogos e aplicativos</strong> para permitir que aplicativos locais controlem a iluminação.</li>
  </ol>

  <h2>4. Como instalar o CS2 RGB Sync</h2>
  <ol>
    <li>Execute o instalador <code>CS2RGBSync_Setup.exe</code> com duplo clique.</li>
    <li>Escolha os atalhos desejados (Menu Iniciar, Área de Trabalho e inicialização opcional com o Windows).</li>
    <li>Na etapa de detecção do Counter-Strike 2, confirme a pasta detectada automaticamente ou selecione manualmente caso seu jogo esteja em outra unidade.</li>
    <li>Ao concluir, o aplicativo estará pronto para uso sem necessidade de instalar Python.</li>
  </ol>

  <h2>5. Como localizar a pasta do CS2</h2>
  <p>A pasta esperada pelo CS2 para arquivos GSI segue o padrão:</p>
  <p><code>&lt;Biblioteca Steam&gt;\\steamapps\\common\\Counter-Strike Global Offensive\\game\\csgo</code></p>
  <p>Exemplo: <code>D:\\SteamLibrary\\steamapps\\common\\Counter-Strike Global Offensive\\game\\csgo</code>. Na aba <strong>Configurações</strong> do aplicativo, você pode clicar em <strong>Detectar</strong> ou <strong>Selecionar Pasta...</strong> a qualquer momento.</p>

  <h2>6. Como instalar o arquivo GSI</h2>
  <ol>
    <li>Durante a instalação, o assistente gera um token local exclusivo e cria apenas o arquivo <code>gamestate_integration_cs2rgbsync.cfg</code> dentro de <code>game\\csgo\\cfg</code>.</li>
    <li>Nenhum outro arquivo do Counter-Strike 2 é alterado.</li>
    <li>Caso mude a porta HTTP ou o diretório do jogo posteriormente, abra a aba <strong>Configurações</strong> e clique em <strong>Instalar / Atualizar Arquivo GSI</strong>.</li>
  </ol>

  <h2>7. Como iniciar o programa</h2>
  <ol>
    <li>Abra o <strong>CS2 RGB Sync</strong> pelo atalho da Área de Trabalho ou Menu Iniciar.</li>
    <li>No <strong>Painel</strong>, verifique se os cartões de status indicam <strong>Corsair iCUE</strong> e <strong>Dispositivo</strong> prontos.</li>
    <li>Clique no botão laranja <strong>INICIAR INTEGRAÇÃO</strong>.</li>
    <li>Abra o Counter-Strike 2 (se o arquivo GSI foi instalado com o CS2 já aberto, reinicie o jogo uma vez para carregar o <code>.cfg</code>).</li>
  </ol>

  <h2>8. Como testar os efeitos (Modo de Simulação e Partida)</h2>
  <ul>
    <li><strong>Sem abrir o CS2:</strong> no Painel, marque <strong>Ativar controles</strong> no Simulador Manual (um banner de alerta laranja indicará que os dados são simulados) e teste Flashbang, Disparo, C4 plantada, Dano de fogo, Vida Crítica, Freezetime CT/TR e Armas com controles completos de <strong>Pausar / Retomar / Reiniciar / Parar</strong>.</li>
    <li><strong>Troca de idioma instantânea:</strong> acesse <strong>Configurações → Idioma</strong> para alternar entre <em>English</em>, <em>Português (Brasil)</em> e <em>Español</em> em tempo real sem reiniciar.</li>
    <li><strong>Em partida real:</strong> desative o Modo de Simulação, mantenha a integração iniciada e entre em uma partida (ou treino com bots) no CS2.</li>
  </ul>

  <h2>9. Como configurar cores, intensidades e prioridades</h2>
  <ul>
    <li>Abra a aba <strong>Efeitos RGB</strong> para ativar/desativar efeitos individualmente, escolher cores, intensidade (0–100%), duração do pulso de disparo (ms), tempo estimado da C4 (s) e velocidade das animações (Hz).</li>
    <li>Na seção <strong>Hierarquia de Prioridades</strong>, use <strong>Subir</strong> e <strong>Descer</strong> para definir qual efeito prevalece quando vários eventos ocorrem simultaneamente.</li>
    <li>Clique em <strong>Aplicar e Salvar</strong> ou use <strong>Restaurar Padrões</strong> para voltar às configurações originais.</li>
  </ul>

  <h2>10. Como solucionar problemas comuns</h2>
  <ul>
    <li><strong>iCUE conectado, mas o dispositivo não muda de cor:</strong> verifique em <em>Configurações → SDK</em> no iCUE 5 se o SDK está habilitado e se o dispositivo Corsair está conectado e reconhecido.</li>
    <li><strong>CS2 não envia dados:</strong> confira na aba <em>Diagnóstico</em> a porta (padrão <code>3000</code>), verifique se <code>gamestate_integration_cs2rgbsync.cfg</code> existe em <code>game\\csgo\\cfg</code> com o mesmo token/porta e reinicie o CS2.</li>
    <li><strong>Porta 3000 ocupada:</strong> altere a porta na aba <em>Configurações</em>, salve e clique em <em>Instalar / Atualizar Arquivo GSI</em>.</li>
    <li><strong>Minimizar para a bandeja:</strong> ao clicar no X da janela com a opção ativada, o app continua na bandeja do Windows; use o menu da bandeja → <em>Sair</em> para encerrar totalmente e liberar o LED.</li>
  </ul>

  <h2>11. Como desinstalar</h2>
  <ol>
    <li>Feche completamente o CS2 RGB Sync pela bandeja do sistema.</li>
    <li>Acesse <strong>Configurações do Windows → Aplicativos → Aplicativos instalados</strong> e selecione <strong>CS2 RGB Sync</strong> → <strong>Desinstalar</strong>.</li>
    <li>Durante a desinstalação, o assistente perguntará se deseja remover o arquivo <code>gamestate_integration_cs2rgbsync.cfg</code> criado pelo aplicativo.</li>
    <li>Configurações do Corsair iCUE e demais arquivos do CS2 nunca são removidos ou alterados. As preferências do usuário em <code>%LOCALAPPDATA%\\CS2RGBSync</code> também são preservadas caso queira reinstalar depois.</li>
  </ol>
</body>
</html>
"""


def main() -> int:
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    out_path = Path(__file__).resolve().parent.parent / "MANUAL_INSTALACAO.pdf"

    writer = QPdfWriter(str(out_path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Portrait)
    writer.setPageMargins(QMarginsF(16, 16, 16, 16), QPageLayout.Unit.Millimeter)
    writer.setTitle("Manual de Instalação e Uso — CS2 RGB Sync")
    writer.setCreator("CS2 RGB Sync")

    doc = QTextDocument()
    doc.setHtml(MANUAL_HTML)
    doc.print_(writer)

    ok = out_path.is_file() and out_path.stat().st_size > 1000
    print(f"PDF={out_path} ({ok}, {out_path.stat().st_size if out_path.exists() else 0} bytes)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
