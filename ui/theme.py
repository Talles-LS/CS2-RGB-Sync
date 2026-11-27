"""Sistema de design Obsidian Calibre e componentes visuais do CS2 RGB Sync (PySide6)."""

from __future__ import annotations

import math

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Tokens de cor Obsidian Calibre
PALETTE = {
    "bg_void": "#08090B",
    "bg_rail": "#0B0C0F",
    "bg_surface": "#0F1115",
    "bg_control": "#14171D",
    "bg_hover": "#1B1F27",
    "border_hairline": "#181B21",
    "border_control": "#252A34",
    "border_hover": "#353C4B",
    "text_primary": "#F2F4F7",
    "text_secondary": "#8E95A2",
    "text_muted": "#555D6B",
    "text_disabled": "#3B404B",
    "accent_orange": "#FF6B1A",
    "accent_orange_hover": "#FF7F3A",
    "accent_blue": "#4B9BFF",
    "status_ok": "#22C55E",
    "status_warn": "#F59E0B",
    "status_danger": "#F26D71",
}

OBSIDIAN_STYLESHEET = """
QMainWindow, QWidget#RootWindow, QWidget#PageCanvas, QStackedWidget {
    background-color: #08090B;
    color: #F2F4F7;
    font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
    font-size: 13px;
}

QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {
    background-color: #08090B;
    border: none;
}

QFrame#Sidebar {
    background-color: #0B0C0F;
    border-right: 1px solid #181B21;
}

QLabel#AppTitle {
    color: #F2F4F7;
    font-family: "Segoe UI Variable Display", "Segoe UI", sans-serif;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0.7px;
}

QLabel#AppSubtitle {
    color: #5B6270;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 10px;
    letter-spacing: 0.5px;
}

QPushButton#NavButton {
    text-align: left;
    padding: 9px 12px;
    border: none;
    border-left: 2px solid transparent;
    border-radius: 4px;
    background-color: transparent;
    color: #7F8794;
    font-size: 13px;
    font-weight: 500;
}

QPushButton#NavButton:hover {
    background-color: #12151B;
    color: #D8DDE6;
}

QPushButton#NavButton:checked {
    background-color: #12151B;
    border-left: 2px solid #FF6B1A;
    color: #F2F4F7;
    font-weight: 600;
}

QFrame#SignalStrip {
    background-color: #0B0D10;
    border-top: 1px solid #181B21;
    border-bottom: 1px solid #181B21;
}

QFrame#TelemetryPanel {
    background-color: #090B0E;
    border-left: 1px solid #181B21;
}

QFrame#SimDrawer {
    background-color: #0B0C0F;
    border-top: 1px solid #181B21;
}

QFrame#SimBanner {
    background-color: #24130A;
    border: 1px solid #6E3212;
    border-radius: 3px;
}

QFrame#MasterPane {
    background-color: #0A0C0F;
    border-right: 1px solid #181B21;
}

QFrame#HairlineH {
    background-color: #181B21;
    min-height: 1px;
    max-height: 1px;
    border: none;
}

QFrame#HairlineV {
    background-color: #181B21;
    min-width: 1px;
    max-width: 1px;
    border: none;
}

QLabel#Overline {
    color: #555D6B;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.1px;
}

QLabel#SectionOverline {
    color: #FF6B1A;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 1.2px;
}

QLabel#PageTitle {
    color: #F2F4F7;
    font-family: "Segoe UI Variable Display", "Segoe UI", sans-serif;
    font-size: 20px;
    font-weight: 600;
}

QLabel#PageSubtitle {
    color: #7A8290;
    font-size: 12px;
}

QLabel#HeroTitle {
    color: #F2F4F7;
    font-family: "Segoe UI Variable Display", "Segoe UI", sans-serif;
    font-size: 22px;
    font-weight: 600;
}

QLabel#MonoReadout {
    color: #F2F4F7;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 13px;
    font-weight: 600;
}

QLabel#MonoMuted {
    color: #7A8290;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 11px;
}

QPushButton {
    background-color: #14171D;
    border: 1px solid #252A34;
    border-radius: 4px;
    padding: 6px 13px;
    color: #D4D8DF;
    font-size: 12.5px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #1B1F27;
    border-color: #353C4B;
    color: #F2F4F7;
}

QPushButton:pressed {
    background-color: #0E1014;
}

QPushButton:disabled {
    background-color: #0C0D11;
    color: #3B404B;
    border-color: #181B21;
}

QPushButton#PrimaryStart, QPushButton#PrimaryAccent {
    background-color: #FF6B1A;
    border: 1px solid #FF7F3A;
    border-radius: 4px;
    color: #08090B;
    font-size: 12.5px;
    font-weight: 700;
    padding: 8px 16px;
}

QPushButton#PrimaryStart:hover, QPushButton#PrimaryAccent:hover {
    background-color: #FF7F3A;
    border-color: #FF9457;
    color: #08090B;
}

QPushButton#PrimaryStart:pressed, QPushButton#PrimaryAccent:pressed {
    background-color: #E35D12;
}

QPushButton#PrimaryStop {
    background-color: #1A0E10;
    border: 1px solid #6E2429;
    border-radius: 4px;
    color: #F26D71;
    font-size: 12.5px;
    font-weight: 700;
    padding: 8px 16px;
}

QPushButton#PrimaryStop:hover {
    background-color: #261316;
    border-color: #9E323A;
}

QPushButton#AccentBlue {
    background-color: #102033;
    border: 1px solid #284C7A;
    border-radius: 4px;
    color: #6CB0FF;
    font-weight: 600;
}

QPushButton#AccentBlue:hover {
    background-color: #162B45;
    border-color: #4B9BFF;
    color: #A4CFFF;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QListWidget {
    background-color: #0E1014;
    border: 1px solid #222630;
    border-radius: 4px;
    padding: 6px 9px;
    color: #F2F4F7;
    font-size: 12.5px;
    selection-background-color: #FF6B1A;
    selection-color: #08090B;
}

QSpinBox, QDoubleSpinBox {
    font-family: "Cascadia Mono", "Consolas", monospace;
    min-width: 108px;
    padding-right: 22px;
}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background-color: #14171D;
    border-left: 1px solid #222630;
    width: 18px;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    border-bottom: 1px solid #1C2028;
    border-top-right-radius: 3px;
}

QSpinBox::down-button, QDoubleSpinBox::down-button {
    border-bottom-right-radius: 3px;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #1E232D;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    width: 0px;
    height: 0px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #9EA5B2;
}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    width: 0px;
    height: 0px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #9EA5B2;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QListWidget:focus {
    border-color: #FF6B1A;
}

QLineEdit:read-only {
    color: #8E95A2;
}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    background-color: #0A0B0E;
    color: #3B404B;
    border-color: #171A20;
}

QComboBox::drop-down {
    border: none;
    width: 22px;
}

QComboBox QAbstractItemView {
    background-color: #0E1014;
    border: 1px solid #252A34;
    color: #F2F4F7;
    selection-background-color: #1D212A;
    selection-color: #FF6B1A;
}

QListWidget {
    padding: 0px;
}

QListWidget::item {
    padding: 7px 10px;
    border-bottom: 1px solid #14171D;
}

QListWidget::item:selected {
    background-color: #13161D;
    color: #F2F4F7;
}

QSlider::groove:horizontal {
    height: 4px;
    background: #1C2029;
    border-radius: 2px;
}

QSlider::sub-page:horizontal {
    background: #FF6B1A;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #F2F4F7;
    border: 2px solid #FF6B1A;
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 7px;
}

QSlider::handle:horizontal:hover {
    background: #FF6B1A;
}

QScrollArea {
    border: none;
    background-color: #08090B;
}

QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 2px 0;
}

QScrollBar::handle:vertical {
    background: #232833;
    border-radius: 3px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #353D4D;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
    height: 0px;
}

QScrollBar:horizontal {
    background: transparent;
    height: 6px;
}

QScrollBar::handle:horizontal {
    background: #232833;
    border-radius: 3px;
}

QMenu {
    background-color: #0D0F13;
    border: 1px solid #222630;
    color: #F2F4F7;
    padding: 4px;
}

QMenu::item {
    padding: 6px 18px;
    border-radius: 3px;
}

QMenu::item:selected {
    background-color: #171B22;
    color: #FF6B1A;
}

QMenu::separator {
    height: 1px;
    background: #181B21;
    margin: 4px 8px;
}

QMessageBox {
    background-color: #0B0D10;
    color: #F2F4F7;
}
"""

DARK_STYLESHEET = OBSIDIAN_STYLESHEET


def build_obsidian_palette() -> QPalette:
    """Constroi QPalette escura Obsidian para impedir vazamento de fundo claro em widgets Qt."""
    pal = QPalette()
    void = QColor("#08090B")
    surface = QColor("#0E1014")
    control = QColor("#14171D")
    text = QColor("#F2F4F7")
    muted = QColor("#8E95A2")
    accent = QColor("#FF6B1A")

    pal.setColor(QPalette.ColorRole.Window, void)
    pal.setColor(QPalette.ColorRole.WindowText, text)
    pal.setColor(QPalette.ColorRole.Base, surface)
    pal.setColor(QPalette.ColorRole.AlternateBase, control)
    pal.setColor(QPalette.ColorRole.ToolTipBase, surface)
    pal.setColor(QPalette.ColorRole.ToolTipText, text)
    pal.setColor(QPalette.ColorRole.Text, text)
    pal.setColor(QPalette.ColorRole.Button, control)
    pal.setColor(QPalette.ColorRole.ButtonText, text)
    pal.setColor(QPalette.ColorRole.BrightText, text)
    pal.setColor(QPalette.ColorRole.Highlight, accent)
    pal.setColor(QPalette.ColorRole.HighlightedText, void)
    pal.setColor(QPalette.ColorRole.PlaceholderText, muted)
    return pal

_STATUS_DOT_COLORS = {
    "ok": ("#22C55E", "#E8ECF2"),
    "warn": ("#F59E0B", "#F59E0B"),
    "error": ("#F26D71", "#F26D71"),
    "info": ("#4B9BFF", "#4B9BFF"),
    "neutral": ("#4E5563", "#7A8290"),
}


class ToggleSwitch(QAbstractButton):
    """Interruptor tátil minimalista com animação discreta para estados ON/OFF."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(36, 20)
        self._knob_pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob_pos", self)
        self._anim.setDuration(130)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_to)

    def sizeHint(self) -> QSize:
        return QSize(36, 20)

    def _get_knob_pos(self) -> float:
        return self._knob_pos

    def _set_knob_pos(self, val: float) -> None:
        self._knob_pos = float(val)
        self.update()

    knob_pos = Property(float, _get_knob_pos, _set_knob_pos)

    def _animate_to(self, checked: bool) -> None:
        target = 1.0 if checked else 0.0
        if not self.isVisible():
            self._anim.stop()
            self._knob_pos = target
            self.update()
            return
        self._anim.stop()
        self._anim.setStartValue(self._knob_pos)
        self._anim.setEndValue(target)
        self._anim.start()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        checked = self.isChecked()
        enabled = self.isEnabled()

        track_rect = QRectF(1.0, 1.0, self.width() - 2.0, self.height() - 2.0)
        if not enabled:
            track_bg = QColor("#111318")
            track_border = QColor("#1E222A")
            knob_col = QColor("#3B404B")
        elif checked:
            track_bg = QColor("#FF6B1A")
            track_border = QColor("#FF7F3A")
            knob_col = QColor("#08090B")
        else:
            track_bg = QColor("#191D25")
            track_border = QColor("#2D3340" if not self.underMouse() else "#41495A")
            knob_col = QColor("#8E95A2")

        p.setPen(QPen(track_border, 1.0))
        p.setBrush(QBrush(track_bg))
        p.drawRoundedRect(track_rect, 9.0, 9.0)

        knob_d = 12.0
        x_off = 4.0
        x_on = float(self.width()) - knob_d - 4.0
        knob_x = x_off + (x_on - x_off) * self._knob_pos
        knob_y = (float(self.height()) - knob_d) / 2.0

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(knob_col))
        p.drawEllipse(QRectF(knob_x, knob_y, knob_d, knob_d))
        p.end()


class StatusCard(QFrame):
    """Nó compacto da faixa Signal Pipeline (sem borda de card arredondada)."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PipelineNode")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 11, 16, 11)
        layout.setSpacing(3)

        self.title_label = QLabel(title.upper())
        self.title_label.setObjectName("Overline")
        layout.addWidget(self.title_label)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)

        self.dot_label = QLabel()
        self.dot_label.setFixedSize(7, 7)
        row.addWidget(self.dot_label)

        self.badge_label = QLabel("Inativo")
        self.badge_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self.badge_label, 1)
        layout.addLayout(row)

        self.detail_label = QLabel("-")
        self.detail_label.setWordWrap(False)
        self.detail_label.setStyleSheet("color: #6E7685; font-size: 11.5px;")
        layout.addWidget(self.detail_label)

        self.set_status("Inativo", "neutral", "-")

    def set_status(
        self, status_text: str, level: str = "neutral", detail: str = ""
    ) -> None:
        dot_col, fg = _STATUS_DOT_COLORS.get(level, _STATUS_DOT_COLORS["neutral"])
        self.dot_label.setStyleSheet(
            f"background-color: {dot_col}; border-radius: 3px;"
        )
        self.badge_label.setText(status_text)
        self.badge_label.setStyleSheet(
            f"color: {fg}; font-size: 12.5px; font-weight: 600;"
        )
        if detail:
            self.detail_label.setText(detail)
            self.detail_label.setToolTip(detail)


class ColorPreviewWheel(QWidget):
    """Mostrador óptico calibrado da iluminação RGB ativa."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rgb: tuple[int, int, int] = (0, 0, 0)
        self._active: bool = False
        self.setFixedSize(136, 136)

    def set_color(self, rgb: tuple[int, int, int], active: bool) -> None:
        if self._rgb == rgb and self._active == active:
            return
        self._rgb = rgb
        self._active = active
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        is_lit = self._active and self._rgb != (0, 0, 0)
        live_col = QColor(*self._rgb) if is_lit else QColor("#252A34")

        # Anel de calibração externo sutil com 24 marcações
        outer_r = 62.0
        p.setPen(QPen(QColor("#181C23"), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(cx - outer_r, cy - outer_r, outer_r * 2.0, outer_r * 2.0))

        for idx in range(24):
            ang = math.radians(idx * 15)
            is_cardinal = idx % 6 == 0
            r1 = outer_r - (7.0 if is_cardinal else 3.5)
            r2 = outer_r
            pen_col = "#363D4B" if is_cardinal else "#1E222B"
            p.setPen(QPen(QColor(pen_col), 1.4 if is_cardinal else 1.0))
            p.drawLine(
                QPointF(cx + math.cos(ang) * r1, cy + math.sin(ang) * r1),
                QPointF(cx + math.cos(ang) * r2, cy + math.sin(ang) * r2),
            )

        # Trilha circular do emissor
        ring_r = 43.0
        ring_rect = QRectF(cx - ring_r, cy - ring_r, ring_r * 2.0, ring_r * 2.0)
        p.setPen(QPen(live_col, 5.0))
        p.setBrush(QBrush(QColor("#0B0D11")))
        p.drawEllipse(ring_rect)

        # Anel de abertura concêntrico e marcadores cardeais (emissor RGB genérico)
        inner_r = 25.0
        inner_col = (
            QColor(live_col.red(), live_col.green(), live_col.blue(), 90)
            if is_lit
            else QColor("#222732")
        )
        p.setPen(QPen(inner_col, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(cx - inner_r, cy - inner_r, inner_r * 2.0, inner_r * 2.0))

        tick_col = live_col if is_lit else QColor("#2A303D")
        p.setPen(QPen(tick_col, 1.4))
        for deg in (0, 90, 180, 270):
            ang = math.radians(deg)
            p.drawLine(
                QPointF(cx + math.cos(ang) * 21.0, cy + math.sin(ang) * 21.0),
                QPointF(cx + math.cos(ang) * 29.0, cy + math.sin(ang) * 29.0),
            )

        # Lente central do emissor óptico
        core_r = 14.0
        p.setPen(QPen(live_col, 1.8))
        p.setBrush(QBrush(live_col if is_lit else QColor("#141820")))
        p.drawEllipse(QRectF(cx - core_r, cy - core_r, core_r * 2.0, core_r * 2.0))

        # Ponto focal central discreto
        pin_r = 3.5
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#08090B" if is_lit else "#222732")))
        p.drawEllipse(QRectF(cx - pin_r, cy - pin_r, pin_r * 2.0, pin_r * 2.0))
        p.end()


class EffectSignatureBar(QWidget):
    """Miniatura vetorial demonstrando o padrão visual/cores do efeito selecionado."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(14)
        self._mode = "solid"
        self._colors = ["#FFFFFF"]
        self._enabled = True

    def set_signature(self, mode: str, colors: list[str], enabled: bool) -> None:
        self._mode = mode
        self._colors = colors or ["#FF6B1A"]
        self._enabled = enabled
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)

        p.setPen(QPen(QColor("#222630"), 1.0))
        p.setBrush(QBrush(QColor("#0D0F13")))
        p.drawRoundedRect(rect, 2.0, 2.0)

        if not self._enabled:
            p.end()
            return

        inner = rect.adjusted(1.5, 1.5, -1.5, -1.5)
        w = inner.width()
        h = inner.height()

        if self._mode == "fade":
            grad = QLinearGradient(inner.topLeft(), inner.topRight())
            c0 = QColor(self._colors[0])
            c_end = QColor(c0)
            c_end.setAlpha(20)
            grad.setColorAt(0.0, c0)
            grad.setColorAt(0.25, c0)
            grad.setColorAt(1.0, c_end)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(inner, 1.5, 1.5)
        elif self._mode == "pulse":
            c0 = QColor(self._colors[0])
            p.setPen(Qt.PenStyle.NoPen)
            for frac in (0.05, 0.25, 0.55):
                c = QColor(c0)
                c.setAlpha(220 if frac == 0.05 else 150)
                p.setBrush(QBrush(c))
                p.drawRect(QRectF(inner.left() + w * frac, inner.top(), max(12.0, w * 0.08), h))
        elif self._mode == "beeps":
            c0 = QColor(self._colors[0])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(c0))
            x = inner.left() + 6.0
            gap = max(26.0, w * 0.14)
            while x < inner.right() - 12.0:
                p.drawRect(QRectF(x, inner.top(), 11.0, h))
                x += gap
                gap = max(16.0, gap * 0.80)
        elif self._mode == "gradient" and len(self._colors) >= 2:
            grad = QLinearGradient(inner.topLeft(), inner.topRight())
            n = len(self._colors)
            for idx, hx in enumerate(self._colors):
                grad.setColorAt(idx / max(1, n - 1), QColor(hx))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(inner, 1.5, 1.5)
        elif self._mode == "segments":
            n = len(self._colors)
            seg_w = w / max(1, n)
            p.setPen(Qt.PenStyle.NoPen)
            for idx, hx in enumerate(self._colors):
                p.setBrush(QBrush(QColor(hx)))
                p.drawRect(
                    QRectF(inner.left() + idx * seg_w, inner.top(), max(2.0, seg_w - 2.0), h)
                )
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(self._colors[0])))
            p.drawRoundedRect(inner, 1.5, 1.5)

        p.end()


class ColorPickerButton(QWidget):
    """Swatch chip minimalista (#0E1014 + amostra 14x14 + texto #HEX mono)."""

    colorChanged = Signal(str)

    def __init__(self, hex_color: str = "#FFFFFF", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hex = self._normalize_hex(hex_color)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._button = QPushButton()
        self._button.setMinimumWidth(116)
        self._button.setFixedHeight(30)
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button.clicked.connect(self._choose_color)
        self._button.setStyleSheet(
            "QPushButton { background-color: #0E1014; border: 1px solid #252A34; "
            "border-radius: 4px; padding: 0px 10px; text-align: left; }"
            "QPushButton:hover { border-color: #3D4556; background-color: #14171D; }"
        )

        btn_lay = QHBoxLayout(self._button)
        btn_lay.setContentsMargins(8, 0, 10, 0)
        btn_lay.setSpacing(8)

        self._swatch = QLabel()
        self._swatch.setFixedSize(14, 14)
        self._swatch.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._hex_label = QLabel(self._hex)
        self._hex_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._hex_label.setStyleSheet(
            'color: #E8ECF2; font-family: "Cascadia Mono", "Consolas", monospace; '
            "font-size: 12px; font-weight: 600;"
        )
        btn_lay.addWidget(self._swatch)
        btn_lay.addWidget(self._hex_label, 1)

        layout.addWidget(self._button)
        self._refresh_style()

    @staticmethod
    def _normalize_hex(hex_str: str) -> str:
        clean = (hex_str or "#FFFFFF").strip().lstrip("#")
        if len(clean) != 6:
            return "#FFFFFF"
        return f"#{clean.upper()}"

    def color(self) -> str:
        return self._hex

    def set_color(self, hex_color: str) -> None:
        self._hex = self._normalize_hex(hex_color)
        self._hex_label.setText(self._hex)
        self._refresh_style()

    def _refresh_style(self) -> None:
        self._swatch.setStyleSheet(
            f"background-color: {self._hex}; border: 1px solid #3C4352; border-radius: 2px;"
        )

    def _choose_color(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._hex), self, "Selecionar Cor RGB")
        if chosen.isValid():
            self.set_color(chosen.name().upper())
            self.colorChanged.emit(self._hex)
