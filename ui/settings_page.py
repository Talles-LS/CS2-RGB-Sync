"""General settings page (Grouped Precision Settings) with live language selector."""

from __future__ import annotations

import copy
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.i18n import (
    available_languages,
    get_language,
    get_language_display_name,
    t,
)
from app.sync_service import SyncService
from ui.theme import ToggleSwitch


def _hline() -> QFrame:
    line = QFrame()
    line.setObjectName("HairlineH")
    return line


class SettingsPage(QWidget):
    """Manages UI language, local HTTP server, CS2 path, Corsair hardware, and system."""

    statusMessage = Signal(str)
    defaultsRestored = Signal(dict)

    def __init__(self, service: SyncService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._token_visible = False
        self._language_actions: dict[str, QAction] = {}
        self._build_ui()
        self.load_from_config(self._service.get_config())

    @property
    def language_actions(self) -> dict[str, QAction]:
        return self._language_actions

    def _begin_section(self, overline: str) -> tuple[QWidget, QLabel, QGridLayout]:
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
        return sec, lbl, grid

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
        self._lbl_title = QLabel()
        self._lbl_title.setObjectName("PageTitle")
        self._lbl_subtitle = QLabel()
        self._lbl_subtitle.setObjectName("PageSubtitle")
        tcol.addWidget(self._lbl_title)
        tcol.addWidget(self._lbl_subtitle)
        top.addLayout(tcol, 1)

        self.btn_restore_defaults = QPushButton()
        self.btn_restore_defaults.clicked.connect(self._on_restore_defaults)
        self.btn_save = QPushButton()
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

        # 01. Language
        sec_lang, self._sec_lang_lbl, g_lang = self._begin_section("")
        self._lbl_language_field = self._field_label("")
        self.btn_language = QPushButton()
        self.btn_language.setObjectName("LanguageButton")
        self.btn_language.setMinimumWidth(220)
        self.btn_language.setFixedHeight(34)
        self.btn_language.setCursor(Qt.CursorShape.PointingHandCursor)

        self.language_menu = QMenu(self.btn_language)
        lang_group = QActionGroup(self.language_menu)
        lang_group.setExclusive(True)
        for code, display_name in available_languages():
            act = QAction(display_name, self.language_menu)
            act.setCheckable(True)
            act.setData(code)
            act.triggered.connect(
                lambda _checked=False, c=code: self._on_language_selected(c)
            )
            lang_group.addAction(act)
            self.language_menu.addAction(act)
            self._language_actions[code] = act

        self.btn_language.clicked.connect(self._open_language_menu)

        self._lbl_language_desc = QLabel()
        self._lbl_language_desc.setStyleSheet("color: #6E7685; font-size: 11.5px;")
        self._lbl_language_desc.setWordWrap(True)

        g_lang.addWidget(self._lbl_language_field, 0, 0)
        g_lang.addWidget(self.btn_language, 0, 1)
        g_lang.addWidget(self._lbl_language_desc, 0, 2, 1, 2)
        wrap_lay.addWidget(sec_lang)
        wrap_lay.addWidget(_hline())

        # 02. Local HTTP Server
        sec_gsi, self._sec_gsi_lbl, g_gsi = self._begin_section("")
        self.txt_host = QLineEdit("127.0.0.1")
        self.txt_host.setReadOnly(True)
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1024, 65535)
        self.txt_token = QLineEdit()
        self.txt_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_token.setReadOnly(True)
        self.btn_toggle_token = QPushButton()
        self.btn_toggle_token.clicked.connect(self._toggle_token_visibility)
        self.btn_regen_token = QPushButton()
        self.btn_regen_token.clicked.connect(self._on_regen_token)

        self._lbl_loopback = self._field_label("")
        self._lbl_port = self._field_label("")
        self._lbl_token = self._field_label("")
        g_gsi.addWidget(self._lbl_loopback, 0, 0)
        g_gsi.addWidget(self.txt_host, 0, 1)
        g_gsi.addWidget(self._lbl_port, 0, 2)
        g_gsi.addWidget(self.spin_port, 0, 3)
        g_gsi.addWidget(self._lbl_token, 1, 0)
        g_gsi.addWidget(self.txt_token, 1, 1)
        g_gsi.addWidget(self.btn_toggle_token, 1, 2)
        g_gsi.addWidget(self.btn_regen_token, 1, 3)
        wrap_lay.addWidget(sec_gsi)
        wrap_lay.addWidget(_hline())

        # 03. Counter-Strike 2
        sec_cs2, self._sec_cs2_lbl, g_cs2 = self._begin_section("")
        self.txt_cs2_path = QLineEdit()
        self.btn_detect_cs2 = QPushButton()
        self.btn_detect_cs2.clicked.connect(self._on_detect_cs2)
        self.btn_browse_cs2 = QPushButton()
        self.btn_browse_cs2.clicked.connect(self._on_browse_cs2)
        self.btn_install_gsi = QPushButton()
        self.btn_install_gsi.setObjectName("AccentBlue")
        self.btn_install_gsi.clicked.connect(self._on_install_gsi)

        self._lbl_cs2_folder = self._field_label("")
        g_cs2.addWidget(self._lbl_cs2_folder, 0, 0)
        g_cs2.addWidget(self.txt_cs2_path, 0, 1, 1, 3)
        act_row = QHBoxLayout()
        act_row.setSpacing(8)
        act_row.addStretch(1)
        act_row.addWidget(self.btn_detect_cs2)
        act_row.addWidget(self.btn_browse_cs2)
        act_row.addWidget(self.btn_install_gsi)
        g_cs2.addLayout(act_row, 1, 1, 1, 3)
        wrap_lay.addWidget(sec_cs2)
        wrap_lay.addWidget(_hline())

        # 04. Corsair Hardware & RGB Engine
        sec_hw, self._sec_hw_lbl, g_hw = self._begin_section("")
        self.txt_sdk_path = QLineEdit()
        self.btn_browse_sdk = QPushButton()
        self.btn_browse_sdk.clicked.connect(self._on_browse_sdk)
        self.slider_brightness = QSlider(Qt.Orientation.Horizontal)
        self.slider_brightness.setRange(0, 100)
        self.lbl_brightness_val = QLabel("100%")
        self.lbl_brightness_val.setObjectName("MonoReadout")
        self.lbl_brightness_val.setMinimumWidth(46)
        self.lbl_brightness_val.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.slider_brightness.valueChanged.connect(
            lambda v: self.lbl_brightness_val.setText(f"{v}%")
        )
        self.spin_tick_ms = QSpinBox()
        self.spin_tick_ms.setRange(15, 100)
        self.chk_restore_exit = ToggleSwitch()

        self._lbl_sdk_path = self._field_label("")
        self._lbl_brightness = self._field_label("")
        self._lbl_render_interval = self._field_label("")
        self._lbl_hint_hz = QLabel()
        self._lbl_hint_hz.setStyleSheet("color: #6E7685; font-size: 11.5px;")

        g_hw.addWidget(self._lbl_sdk_path, 0, 0)
        g_hw.addWidget(self.txt_sdk_path, 0, 1, 1, 2)
        g_hw.addWidget(self.btn_browse_sdk, 0, 3)
        g_hw.addWidget(self._lbl_brightness, 1, 0)
        g_hw.addWidget(self.slider_brightness, 1, 1, 1, 2)
        g_hw.addWidget(self.lbl_brightness_val, 1, 3)
        g_hw.addWidget(self._lbl_render_interval, 2, 0)
        g_hw.addWidget(self.spin_tick_ms, 2, 1)
        g_hw.addWidget(self._lbl_hint_hz, 2, 2, 1, 2)
        wrap_lay.addWidget(sec_hw)

        restore_row, self._lbl_restore_exit = self._toggle_row("", self.chk_restore_exit)
        wrap_lay.addWidget(restore_row)
        wrap_lay.addWidget(_hline())

        # 05. System Behavior
        sec_sys, self._sec_sys_lbl, _ = self._begin_section("")
        wrap_lay.addWidget(sec_sys)
        self.chk_start_windows = ToggleSwitch()
        self.chk_minimize_tray = ToggleSwitch()
        self.chk_auto_start = ToggleSwitch()
        self.chk_sim_mode = ToggleSwitch()

        self._sys_toggle_labels: list[tuple[QLabel, str]] = []
        for key, sw in (
            ("settings.start_windows", self.chk_start_windows),
            ("settings.minimize_tray", self.chk_minimize_tray),
            ("settings.auto_start", self.chk_auto_start),
            ("settings.sim_mode", self.chk_sim_mode),
        ):
            row, lbl = self._toggle_row("", sw)
            self._sys_toggle_labels.append((lbl, key))
            wrap_lay.addWidget(row)

        lay.addWidget(content_wrap)
        lay.addStretch(1)
        self.retranslate_ui()

    @staticmethod
    def _field_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #9EA5B2; font-size: 12.5px;")
        lbl.setMinimumWidth(175)
        return lbl

    @staticmethod
    def _toggle_row(text: str, toggle: ToggleSwitch) -> tuple[QWidget, QLabel]:
        row = QWidget()
        rlay = QHBoxLayout(row)
        rlay.setContentsMargins(0, 4, 0, 4)
        rlay.setSpacing(12)
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #C8CDD6; font-size: 13px;")
        rlay.addWidget(lbl, 1)
        rlay.addWidget(toggle)
        return row, lbl

    def _open_language_menu(self) -> None:
        pos = self.btn_language.mapToGlobal(self.btn_language.rect().bottomLeft())
        self.language_menu.setMinimumWidth(self.btn_language.width())
        self.language_menu.popup(pos)

    def _sync_language_button(self, code: str | None = None) -> None:
        active = code or get_language()
        display_name = get_language_display_name(active)
        self.btn_language.setText(f"{display_name}  ▾")
        for lang_code, act in self._language_actions.items():
            act.setChecked(lang_code == active)

    def _on_language_selected(self, lang_code: str) -> None:
        canonical = self._service.set_language(lang_code)
        self._sync_language_button(canonical)
        display_name = get_language_display_name(canonical)
        self.statusMessage.emit(t("dialogs.language_saved_status", name=display_name))

    def retranslate_ui(self) -> None:
        self._lbl_title.setText(t("settings.title"))
        self._lbl_subtitle.setText(t("settings.subtitle"))
        self.btn_restore_defaults.setText(t("settings.btn_restore"))
        self.btn_save.setText(t("settings.btn_save"))

        self._sec_lang_lbl.setText(t("settings.section_language"))
        self._lbl_language_field.setText(t("settings.language_label"))
        self._lbl_language_desc.setText(t("settings.language_desc"))
        self._sync_language_button()

        self._sec_gsi_lbl.setText(t("settings.section_gsi"))
        self._lbl_loopback.setText(t("settings.loopback_addr"))
        self._lbl_port.setText(t("settings.http_port"))
        self._lbl_token.setText(t("settings.gsi_token"))
        self.btn_toggle_token.setText(
            t("settings.btn_hide") if self._token_visible else t("settings.btn_reveal")
        )
        self.btn_regen_token.setText(t("settings.btn_regen_token"))

        self._sec_cs2_lbl.setText(t("settings.section_cs2"))
        self._lbl_cs2_folder.setText(t("settings.cs2_folder"))
        self.btn_detect_cs2.setText(t("settings.btn_detect_steam"))
        self.btn_browse_cs2.setText(t("settings.btn_browse_folder"))
        self.btn_install_gsi.setText(t("settings.btn_install_gsi"))

        self._sec_hw_lbl.setText(t("settings.section_hardware"))
        self._lbl_sdk_path.setText(t("settings.sdk_custom_path"))
        self.txt_sdk_path.setPlaceholderText(t("settings.sdk_placeholder"))
        self.btn_browse_sdk.setText(t("settings.btn_browse_dll"))
        self._lbl_brightness.setText(t("settings.global_brightness"))
        self._lbl_render_interval.setText(t("settings.render_interval"))
        self.spin_tick_ms.setSuffix(t("common.ms_unit"))
        self._lbl_hint_hz.setText(t("settings.render_interval_hint"))
        self._lbl_restore_exit.setText(t("settings.restore_on_exit"))

        self._sec_sys_lbl.setText(t("settings.section_system"))
        for lbl, key in self._sys_toggle_labels:
            lbl.setText(t(key))

    def _toggle_token_visibility(self) -> None:
        self._token_visible = not self._token_visible
        self.txt_token.setEchoMode(
            QLineEdit.EchoMode.Normal
            if self._token_visible
            else QLineEdit.EchoMode.Password
        )
        self.btn_toggle_token.setText(
            t("settings.btn_hide") if self._token_visible else t("settings.btn_reveal")
        )

    def _on_regen_token(self) -> None:
        ok, msg = self._service.regenerate_token_and_reinstall()
        self.load_from_config(self._service.get_config())
        self.statusMessage.emit(msg)
        QMessageBox.information(self, t("dialogs.token_title"), msg)

    def _on_detect_cs2(self) -> None:
        found = self._service.detect_cs2_path()
        if found:
            self.txt_cs2_path.setText(str(found))
            self.statusMessage.emit(t("dialogs.cs2_detected_status", path=found))
        else:
            QMessageBox.warning(
                self,
                t("dialogs.cs2_not_found_title"),
                t("dialogs.cs2_not_found_body"),
            )

    def _on_browse_cs2(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, t("dialogs.browse_cs2_title")
        )
        if chosen:
            self.txt_cs2_path.setText(chosen)

    def _on_browse_sdk(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, t("dialogs.browse_sdk_title"), "", "DLL (*.dll)"
        )
        if chosen:
            self.txt_sdk_path.setText(chosen)

    def _on_install_gsi(self) -> None:
        ok, msg = self._service.install_gsi_file(
            self.txt_cs2_path.text().strip() or None
        )
        self.load_from_config(self._service.get_config())
        self.statusMessage.emit(msg)
        if ok:
            QMessageBox.information(self, t("dialogs.gsi_installed_title"), msg)
        else:
            QMessageBox.warning(self, t("dialogs.gsi_failed_title"), msg)

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
        self._sync_language_button(str(ui.get("language", get_language())))

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
            QMessageBox.warning(self, t("dialogs.error_title"), msg)

    def _on_restore_defaults(self) -> None:
        reply = QMessageBox.question(
            self,
            t("dialogs.restore_settings_title"),
            t("dialogs.restore_settings_body"),
        )
        if reply == QMessageBox.StandardButton.Yes:
            restored = self._service.restore_default_settings()
            self.load_from_config(restored)
            self.defaultsRestored.emit(restored)
            self.statusMessage.emit(t("dialogs.defaults_restored"))
