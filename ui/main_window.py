"""Janela principal do CS2 RGB Sync com identidade visual Obsidian Calibre."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app import __app_name__, __version__
from app.config_manager import get_project_root
from app.sync_service import SyncService
from ui.dashboard import DashboardPage
from ui.diagnostics_page import DiagnosticsPage
from ui.effects_page import EffectsPage
from ui.icons import BrandMarkWidget, apply_windows_dark_titlebar, make_nav_icon
from ui.settings_page import SettingsPage
from ui.theme import OBSIDIAN_STYLESHEET, build_obsidian_palette


def _h_divider() -> QFrame:
    line = QFrame()
    line.setObjectName("HairlineH")
    line.setFrameShape(QFrame.Shape.NoFrame)
    return line


class MainWindow(QMainWindow):
    """Janela desktop principal com navegação lateral minimalista, tray e atualização assíncrona."""

    _integrationActionDone = Signal(bool, str, bool)

    def __init__(self, service: SyncService, start_minimized: bool = False) -> None:
        super().__init__()
        self._service = service
        self._force_quit = False
        self._action_in_flight = False

        self.setWindowTitle(__app_name__)
        self.resize(1140, 720)
        self.setMinimumSize(960, 620)
        self.setPalette(build_obsidian_palette())
        app_inst = QApplication.instance()
        if app_inst is not None:
            app_inst.setPalette(build_obsidian_palette())
        self.setStyleSheet(OBSIDIAN_STYLESHEET)

        icon_path = self._find_icon_path()
        if icon_path is not None:
            self.setWindowIcon(QIcon(str(icon_path)))

        self._build_ui()
        self._setup_tray(icon_path)
        self._integrationActionDone.connect(self._on_integration_action_done)

        try:
            apply_windows_dark_titlebar(int(self.winId()))
        except Exception:
            pass

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(100)
        self._refresh_timer.timeout.connect(self._refresh_ui)
        self._refresh_timer.start()
        self._refresh_ui()

        if self._service.get_config().get("ui", {}).get("auto_start_integration", False):
            QTimer.singleShot(250, self._trigger_toggle_integration)

        if start_minimized and self._tray is not None:
            self.hide()

    @staticmethod
    def _find_icon_path() -> Path | None:
        for name in ("cs2_rgb_sync.ico", "cs2_rgb_sync.png"):
            candidate = get_project_root() / "assets" / "icons" / name
            if candidate.is_file():
                return candidate
        return None

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        try:
            apply_windows_dark_titlebar(int(self.winId()))
        except Exception:
            pass

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("RootWindow")
        self.setCentralWidget(root)

        main_lay = QHBoxLayout(root)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # Barra lateral Obsidian Rail (208px)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(208)
        side_lay = QVBoxLayout(sidebar)
        side_lay.setContentsMargins(14, 18, 14, 16)
        side_lay.setSpacing(6)

        # Lockup de marca com Optical Reticle vetorial
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(4, 2, 4, 12)
        brand_row.setSpacing(10)
        brand_row.addWidget(BrandMarkWidget(size=28))

        brand_text_col = QVBoxLayout()
        brand_text_col.setContentsMargins(0, 0, 0, 0)
        brand_text_col.setSpacing(1)
        lbl_title = QLabel('CS2 <span style="color:#FF6B1A;">SYNC</span>')
        lbl_title.setObjectName("AppTitle")
        lbl_title.setTextFormat(Qt.TextFormat.RichText)
        lbl_sub = QLabel("CORSAIR iCUE RGB")
        lbl_sub.setObjectName("AppSubtitle")
        brand_text_col.addWidget(lbl_title)
        brand_text_col.addWidget(lbl_sub)
        brand_row.addLayout(brand_text_col, 1)
        side_lay.addLayout(brand_row)

        side_lay.addWidget(_h_divider())
        side_lay.addSpacing(8)

        self.nav_buttons: list[QPushButton] = []
        nav_items = (
            ("Painel", "dashboard"),
            ("Efeitos RGB", "effects"),
            ("Configurações", "settings"),
            ("Diagnóstico", "diagnostics"),
        )
        for idx, (text, icon_kind) in enumerate(nav_items):
            btn = QPushButton(text)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(make_nav_icon(icon_kind, size=16))
            btn.setIconSize(QSize(16, 16))
            btn.clicked.connect(lambda _=False, i=idx: self._select_page(i))
            side_lay.addWidget(btn)
            self.nav_buttons.append(btn)

        side_lay.addStretch(1)
        side_lay.addWidget(_h_divider())
        side_lay.addSpacing(6)

        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(4, 2, 4, 0)
        footer_row.setSpacing(7)
        self._footer_dot = QLabel()
        self._footer_dot.setFixedSize(7, 7)
        self._footer_dot.setStyleSheet("background-color: #4E5563; border-radius: 3px;")
        self.lbl_footer_status = QLabel("Pronto")
        self.lbl_footer_status.setWordWrap(True)
        self.lbl_footer_status.setStyleSheet("color: #B8BFC9; font-size: 11.5px;")
        footer_row.addWidget(self._footer_dot, 0, Qt.AlignmentFlag.AlignTop)
        footer_row.addWidget(self.lbl_footer_status, 1)
        side_lay.addLayout(footer_row)

        port = self._service.get_config().get("server", {}).get("port", 3000)
        self.lbl_version_meta = QLabel(f"v{__version__} · 127.0.0.1:{port}")
        self.lbl_version_meta.setObjectName("MonoMuted")
        self.lbl_version_meta.setContentsMargins(4, 2, 4, 0)
        side_lay.addWidget(self.lbl_version_meta)
        main_lay.addWidget(sidebar)

        # Páginas
        self.stack = QStackedWidget()
        self.dashboard_page = DashboardPage(self._service)
        self.effects_page = EffectsPage(self._service)
        self.settings_page = SettingsPage(self._service)
        self.diagnostics_page = DiagnosticsPage(self._service)

        self.dashboard_page.toggleRequested.connect(self._trigger_toggle_integration)
        self.effects_page.statusMessage.connect(self._set_footer_status)
        self.settings_page.statusMessage.connect(self._set_footer_status)
        self.settings_page.defaultsRestored.connect(self.effects_page.load_from_config)

        for page in (
            self.dashboard_page,
            self.effects_page,
            self.settings_page,
            self.diagnostics_page,
        ):
            self.stack.addWidget(page)

        main_lay.addWidget(self.stack, 1)
        self._select_page(0)

    def _setup_tray(self, icon_path: Path | None) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = None
            return
        tray = QSystemTrayIcon(self)
        if icon_path is not None:
            tray.setIcon(QIcon(str(icon_path)))
        tray.setToolTip(__app_name__)

        menu = QMenu(self)
        act_open = QAction("Abrir Painel", self)
        act_open.triggered.connect(self._restore_from_tray)
        self._tray_toggle_action = QAction("Iniciar Integração", self)
        self._tray_toggle_action.triggered.connect(self._trigger_toggle_integration)
        act_quit = QAction("Sair", self)
        act_quit.triggered.connect(self._quit_app)

        menu.addAction(act_open)
        menu.addAction(self._tray_toggle_action)
        menu.addSeparator()
        menu.addAction(act_quit)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self._tray = tray

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._restore_from_tray()

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        if index == 1:
            self.effects_page.load_from_config(self._service.get_config())
        elif index == 2:
            self.settings_page.load_from_config(self._service.get_config())
        self._refresh_ui()

    def _set_footer_status(self, message: str) -> None:
        self.lbl_footer_status.setText(message)

    def _trigger_toggle_integration(self) -> None:
        if self._action_in_flight:
            return
        self._action_in_flight = True
        currently_running = self._service.get_ui_snapshot().integration_running
        self.dashboard_page.set_busy(
            True, "PARANDO..." if currently_running else "INICIANDO..."
        )

        def worker() -> None:
            if currently_running:
                self._service.stop_integration()
                self._integrationActionDone.emit(True, "Integração encerrada.", False)
            else:
                ok, msg = self._service.start_integration()
                self._integrationActionDone.emit(ok, msg, True)

        threading.Thread(target=worker, name="CS2RGBSync-UIWorker", daemon=True).start()

    def _on_integration_action_done(self, ok: bool, msg: str, was_start: bool) -> None:
        self._action_in_flight = False
        self.dashboard_page.set_busy(False)
        self._set_footer_status(msg)
        if hasattr(self, "_tray_toggle_action"):
            self._tray_toggle_action.setText(
                "Parar Integração" if (ok and was_start) else "Iniciar Integração"
            )
        if not ok and was_start:
            QMessageBox.warning(self, "Erro ao Iniciar Integração", msg)
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        snap = self._service.get_ui_snapshot()
        self.dashboard_page.update_from_snapshot(snap)
        if self.stack.currentWidget() is self.diagnostics_page:
            self.diagnostics_page.update_from_snapshot(snap)

        dot_col = "#22C55E" if snap.integration_running else "#4E5563"
        self._footer_dot.setStyleSheet(
            f"background-color: {dot_col}; border-radius: 3px;"
        )
        self.lbl_version_meta.setText(
            f"v{__version__} · 127.0.0.1:{snap.server_stats.port}"
        )
        if hasattr(self, "_tray_toggle_action"):
            self._tray_toggle_action.setText(
                "Parar Integração" if snap.integration_running else "Iniciar Integração"
            )

    def _quit_app(self) -> None:
        self._force_quit = True
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def shutdown_service(self) -> None:
        """Encerra timer, tray e serviço com segurança."""
        self._refresh_timer.stop()
        if self._tray is not None:
            self._tray.hide()
        self._service.shutdown()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        minimize_to_tray = bool(
            self._service.get_config().get("ui", {}).get("minimize_to_tray", True)
        )
        if not self._force_quit and minimize_to_tray and self._tray is not None:
            event.ignore()
            self.hide()
            self._tray.showMessage(
                __app_name__,
                "CS2 RGB Sync continua ativo na bandeja do sistema.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            return

        self.shutdown_service()
        super().closeEvent(event)
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)
