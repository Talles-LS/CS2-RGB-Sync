"""Aba de configurações gerais (Grouped Precision Settings) sem cards empilhados."""

from __future__ import annotations

import copy
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.sync_service import SyncService
from ui.theme import ToggleSwitch


def _hline() -> QFrame:
    line = QFrame()
    line.setObjectName("HairlineH")
    return line


class SettingsPage(QWidget):
    """Gerencia servidor HTTP local, caminho do CS2, hardware Corsair e sistema."""

    statusMessage = Signal(str)
    defaultsRestored = Signal(dict)

    def __init__(self, service: SyncService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._token_visible = False
        self._build_ui()
        self.load_from_config(self._service.get_config())

    def _begin_section(self, overline: str) -> tuple[QWidget, QGridLayout]:
        sec = QWidget()
        v = QVBoxLayout(sec)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        lbl = QLabel(overline)
        lbl.setObjectName("SectionOverline")
        v.addWidget(lbl)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)
        return sec, grid

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        top = QHBoxLayout(header)
        top.setContentsMargins(28, 20, 28, 18)
        top.setSpacing(12)

        tcol = QVBoxLayout()
        tcol.setSpacing(2)
        title = QLabel("Configurações")
        title.setObjectName("PageTitle")
        sub = QLabel(
            "Rede local GSI, diretório do Counter-Strike 2, hardware Corsair e comportamento"
        )
        sub.setObjectName("PageSubtitle")
        tcol.addWidget(title)
        tcol.addWidget(sub)
        top.addLayout(tcol, 1)

        self.btn_restore_defaults = QPushButton("Restaurar Configurações Padrão")
        self.btn_restore_defaults.clicked.connect(self._on_restore_defaults)
        self.btn_save = QPushButton("Salvar Configurações")
        self.btn_save.setObjectName("PrimaryAccent")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._on_save)
        top.addWidget(self.btn_restore_defaults)
        top.addWidget(self.btn_save)
        outer.addWidget(header)
        outer.addWidget(_hline())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setObjectName("PageCanvas")
        scroll.viewport().setAutoFillBackground(True)
        outer.addWidget(scroll, 1)

        body = QWidget()
        body.setObjectName("PageCanvas")
        body.setAutoFillBackground(True)
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 18, 28, 24)
        lay.setSpacing(16)

        content_wrap = QWidget()
        content_wrap.setMaximumWidth(840)
        wrap_lay = QVBoxLayout(content_wrap)
        wrap_lay.setContentsMargins(0, 0, 0, 0)
        wrap_lay.setSpacing(16)

        # 01. Servidor HTTP Local
        sec, g = self._begin_section("01 · SERVIDOR HTTP LOCAL (GSI)")
        self.txt_host = QLineEdit("127.0.0.1")
        self.txt_host.setReadOnly(True)
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1024, 65535)
        self.txt_token = QLineEdit()
        self.txt_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_token.setReadOnly(True)
        self.btn_toggle_token = QPushButton("Revelar")
        self.btn_toggle_token.clicked.connect(self._toggle_token_visibility)
        self.btn_regen_token = QPushButton("Regenerar Token")
        self.btn_regen_token.clicked.connect(self._on_regen_token)

        g.addWidget(self._field_label("Endereço loopback:"), 0, 0)
        g.addWidget(self.txt_host, 0, 1)
        g.addWidget(self._field_label("Porta HTTP:"), 0, 2)
        g.addWidget(self.spin_port, 0, 3)
        g.addWidget(self._field_label("Token local GSI:"), 1, 0)
        g.addWidget(self.txt_token, 1, 1)
        g.addWidget(self.btn_toggle_token, 1, 2)
        g.addWidget(self.btn_regen_token, 1, 3)
        wrap_lay.addWidget(sec)
        wrap_lay.addWidget(_hline())

        # 02. Counter-Strike 2
        sec, g = self._begin_section("02 · COUNTER-STRIKE 2")
        self.txt_cs2_path = QLineEdit()
        self.btn_detect_cs2 = QPushButton("Detectar Steam")
        self.btn_detect_cs2.clicked.connect(self._on_detect_cs2)
        self.btn_browse_cs2 = QPushButton("Selecionar Pasta...")
        self.btn_browse_cs2.clicked.connect(self._on_browse_cs2)
        self.btn_install_gsi = QPushButton("Instalar / Atualizar Arquivo GSI")
        self.btn_install_gsi.setObjectName("AccentBlue")
        self.btn_install_gsi.clicked.connect(self._on_install_gsi)

        g.addWidget(self._field_label("Pasta game\\csgo:"), 0, 0)
        g.addWidget(self.txt_cs2_path, 0, 1, 1, 3)
        act_row = QHBoxLayout()
        act_row.setSpacing(8)
        act_row.addStretch(1)
        act_row.addWidget(self.btn_detect_cs2)
        act_row.addWidget(self.btn_browse_cs2)
        act_row.addWidget(self.btn_install_gsi)
        g.addLayout(act_row, 1, 1, 1, 3)
        wrap_lay.addWidget(sec)
        wrap_lay.addWidget(_hline())

        # 03. Hardware Corsair e Motor RGB
        sec, g = self._begin_section("03 · HARDWARE CORSAIR & MOTOR RGB")
        self.txt_sdk_path = QLineEdit()
        self.txt_sdk_path.setPlaceholderText("Automático (iCUESDK.x64_2019.dll embutida)")
        self.btn_browse_sdk = QPushButton("Procurar DLL...")
        self.btn_browse_sdk.clicked.connect(self._on_browse_sdk)
        self.slider_brightness = QSlider(Qt.Orientation.Horizontal)
        self.slider_brightness.setRange(0, 100)
        self.lbl_brightness_val = QLabel("100%")
        self.lbl_brightness_val.setObjectName("MonoReadout")
        self.lbl_brightness_val.setMinimumWidth(46)
        self.lbl_brightness_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.slider_brightness.valueChanged.connect(
            lambda v: self.lbl_brightness_val.setText(f"{v}%")
        )
        self.spin_tick_ms = QSpinBox()
        self.spin_tick_ms.setRange(15, 100)
        self.spin_tick_ms.setSuffix(" ms")
        self.chk_restore_exit = ToggleSwitch()

        g.addWidget(self._field_label("Caminho customizado do SDK:"), 0, 0)
        g.addWidget(self.txt_sdk_path, 0, 1, 1, 2)
        g.addWidget(self.btn_browse_sdk, 0, 3)
        g.addWidget(self._field_label("Brilho global:"), 1, 0)
        g.addWidget(self.slider_brightness, 1, 1, 1, 2)
        g.addWidget(self.lbl_brightness_val, 1, 3)
        g.addWidget(self._field_label("Intervalo de renderização:"), 2, 0)
        g.addWidget(self.spin_tick_ms, 2, 1)
        hint_hz = QLabel("Frequência independente do loop RGB (15..100 ms)")
        hint_hz.setStyleSheet("color: #6E7685; font-size: 11.5px;")
        g.addWidget(hint_hz, 2, 2, 1, 2)
        wrap_lay.addWidget(sec)

        restore_row = self._toggle_row(
            "Restaurar iluminação padrão do iCUE ao encerrar (nunca altera perfis do hardware)",
            self.chk_restore_exit,
        )
        wrap_lay.addWidget(restore_row)
        wrap_lay.addWidget(_hline())

        # 04. Sistema
        sec_sys, _ = self._begin_section("04 · COMPORTAMENTO DO SISTEMA")
        wrap_lay.addWidget(sec_sys)
        self.chk_start_windows = ToggleSwitch()
        self.chk_minimize_tray = ToggleSwitch()
        self.chk_auto_start = ToggleSwitch()
        self.chk_sim_mode = ToggleSwitch()

        for text, sw in (
            ("Iniciar junto com o Windows (minimizado na bandeja)", self.chk_start_windows),
            ("Minimizar para a bandeja do sistema ao fechar a janela", self.chk_minimize_tray),
            ("Iniciar integração automaticamente ao abrir o aplicativo", self.chk_auto_start),
            ("Modo de simulação ativo", self.chk_sim_mode),
        ):
            wrap_lay.addWidget(self._toggle_row(text, sw))

        lay.addWidget(content_wrap)
        lay.addStretch(1)

    @staticmethod
    def _field_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #9EA5B2; font-size: 12.5px;")
        lbl.setMinimumWidth(175)
        return lbl

    @staticmethod
    def _toggle_row(text: str, toggle: ToggleSwitch) -> QWidget:
        row = QWidget()
        rlay = QHBoxLayout(row)
        rlay.setContentsMargins(0, 4, 0, 4)
        rlay.setSpacing(12)
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #C8CDD6; font-size: 13px;")
        rlay.addWidget(lbl, 1)
        rlay.addWidget(toggle)
        return row

    def _toggle_token_visibility(self) -> None:
        self._token_visible = not self._token_visible
        self.txt_token.setEchoMode(
            QLineEdit.EchoMode.Normal
            if self._token_visible
            else QLineEdit.EchoMode.Password
        )
        self.btn_toggle_token.setText("Ocultar" if self._token_visible else "Revelar")

    def _on_regen_token(self) -> None:
        ok, msg = self._service.regenerate_token_and_reinstall()
        self.load_from_config(self._service.get_config())
        self.statusMessage.emit(msg)
        QMessageBox.information(self, "Token GSI", msg)

    def _on_detect_cs2(self) -> None:
        found = self._service.detect_cs2_path()
        if found:
            self.txt_cs2_path.setText(str(found))
            self.statusMessage.emit(f"CS2 detectado: {found}")
        else:
            QMessageBox.warning(
                self,
                "CS2 não encontrado",
                "Não foi possível detectar automaticamente. Selecione a pasta manualmente.",
            )

    def _on_browse_cs2(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Selecionar pasta do CS2 (...\\game\\csgo)"
        )
        if chosen:
            self.txt_cs2_path.setText(chosen)

    def _on_browse_sdk(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Selecionar DLL do Corsair iCUE SDK", "", "DLL (*.dll)"
        )
        if chosen:
            self.txt_sdk_path.setText(chosen)

    def _on_install_gsi(self) -> None:
        ok, msg = self._service.install_gsi_file(self.txt_cs2_path.text().strip() or None)
        self.load_from_config(self._service.get_config())
        self.statusMessage.emit(msg)
        if ok:
            QMessageBox.information(self, "GSI Instalado", msg)
        else:
            QMessageBox.warning(self, "Falha no GSI", msg)

    def load_from_config(self, cfg: dict[str, Any]) -> None:
        srv = cfg.get("server", {})
        gsi = cfg.get("gsi", {})
        hw = cfg.get("hardware", {})
        eng = cfg.get("engine", {})
        ui = cfg.get("ui", {})

        self.txt_host.setText(str(srv.get("host", "127.0.0.1")))
        self.spin_port.setValue(int(srv.get("port", 3000)))
        self.txt_token.setText(str(srv.get("token", "")))
        self.txt_cs2_path.setText(str(gsi.get("cs2_path", "")))
        self.txt_sdk_path.setText(str(hw.get("sdk_path", "")))
        self.slider_brightness.setValue(int(hw.get("global_brightness", 100)))
        self.spin_tick_ms.setValue(int(eng.get("tick_ms", 25)))
        self.chk_restore_exit.setChecked(bool(hw.get("restore_on_exit", True)))

        self.chk_start_windows.setChecked(bool(ui.get("start_with_windows", False)))
        self.chk_minimize_tray.setChecked(bool(ui.get("minimize_to_tray", True)))
        self.chk_auto_start.setChecked(bool(ui.get("auto_start_integration", False)))
        self.chk_sim_mode.setChecked(bool(eng.get("simulation_mode", False)))

    def collect_config(self, base_cfg: dict[str, Any]) -> dict[str, Any]:
        cfg = copy.deepcopy(base_cfg)
        cfg["server"]["port"] = self.spin_port.value()
        cfg["gsi"]["cs2_path"] = self.txt_cs2_path.text().strip()
        cfg["hardware"]["sdk_path"] = self.txt_sdk_path.text().strip()
        cfg["hardware"]["global_brightness"] = self.slider_brightness.value()
        cfg["hardware"]["restore_on_exit"] = self.chk_restore_exit.isChecked()
        cfg["engine"]["tick_ms"] = self.spin_tick_ms.value()
        cfg["engine"]["simulation_mode"] = self.chk_sim_mode.isChecked()
        cfg["ui"]["start_with_windows"] = self.chk_start_windows.isChecked()
        cfg["ui"]["minimize_to_tray"] = self.chk_minimize_tray.isChecked()
        cfg["ui"]["auto_start_integration"] = self.chk_auto_start.isChecked()
        return cfg

    def _on_save(self) -> None:
        updated = self.collect_config(self._service.get_config())
        ok, msg = self._service.apply_config(updated, apply_windows_startup=True)
        self.statusMessage.emit(msg)
        if not ok:
            QMessageBox.warning(self, "Erro", msg)

    def _on_restore_defaults(self) -> None:
        reply = QMessageBox.question(
            self,
            "Restaurar Configurações Padrão",
            "Deseja restaurar todas as configurações padrão (preservando o token GSI)?",
        )
        if reply == QMessageBox.StandardButton.Yes:
            restored = self._service.restore_default_settings()
            self.load_from_config(restored)
            self.defaultsRestored.emit(restored)
            self.statusMessage.emit("Configurações padrão restauradas.")
