"""Ícones vetoriais desenhados via QPainter e utilitários nativos da barra de título no Windows 11."""

from __future__ import annotations

import math
import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QWidget


def apply_windows_dark_titlebar(hwnd: int) -> None:
    """Aplica modo escuro e cor de barra de título #08090B no Windows 11 (DWM)."""
    if os.name != "nt" or not hwnd:
        return
    try:
        import ctypes

        dwmapi = ctypes.windll.dwmapi
        dark_val = ctypes.c_int(1)
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_val), ctypes.sizeof(dark_val))
        # DWMWA_CAPTION_COLOR = 35 -> COLORREF 0x00BBGGRR para #08090B
        caption_col = ctypes.c_uint32(0x000B0908)
        dwmapi.DwmSetWindowAttribute(
            hwnd, 35, ctypes.byref(caption_col), ctypes.sizeof(caption_col)
        )
        # DWMWA_BORDER_COLOR = 34 -> COLORREF 0x00BBGGRR para #181B21
        border_col = ctypes.c_uint32(0x00211B18)
        dwmapi.DwmSetWindowAttribute(
            hwnd, 34, ctypes.byref(border_col), ctypes.sizeof(border_col)
        )
    except Exception:
        pass


def draw_optical_reticle(
    p: QPainter,
    rect: QRectF,
    *,
    show_container: bool = True,
    show_ticks: bool = True,
) -> None:
    """Desenha o emblema Optical Reticle com nitidez vetorial."""
    s = min(rect.width(), rect.height())
    cx = rect.center().x()
    cy = rect.center().y()

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    if show_container:
        margin = s * 0.035
        bg = QRectF(cx - s / 2 + margin, cy - s / 2 + margin, s - 2 * margin, s - 2 * margin)
        p.setPen(QPen(QColor("#232833"), max(1.0, s * 0.032)))
        p.setBrush(QBrush(QColor("#0B0C0F")))
        p.drawRoundedRect(bg, s * 0.22, s * 0.22)

    arc_r = s * 0.32
    arc_rect = QRectF(cx - arc_r, cy - arc_r, arc_r * 2.0, arc_r * 2.0)
    stroke_w = max(1.8, s * 0.078)
    span_deg = 52

    white_pen = QPen(
        QColor("#ECEFF4"), stroke_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap
    )
    orange_pen = QPen(
        QColor("#FF6B1A"), stroke_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap
    )
    p.setBrush(Qt.BrushStyle.NoBrush)
    for center_deg, pen in (
        (90.0, white_pen),
        (180.0, white_pen),
        (270.0, white_pen),
        (0.0, orange_pen),
    ):
        p.setPen(pen)
        p.drawArc(
            arc_rect,
            int(round((center_deg - span_deg / 2.0) * 16)),
            int(round(span_deg * 16)),
        )

    if show_ticks and s >= 24.0:
        tick_w = max(1.1, s * 0.032)
        outer_r = s * 0.40
        inner_r = s * 0.29
        for angle_deg, col in (
            (90, "#5B6372"),
            (180, "#5B6372"),
            (270, "#5B6372"),
            (0, "#FF6B1A"),
        ):
            p.setPen(
                QPen(QColor(col), tick_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            )
            rad = math.radians(angle_deg)
            p.drawLine(
                QPointF(cx + math.cos(rad) * inner_r, cy - math.sin(rad) * inner_r),
                QPointF(cx + math.cos(rad) * outer_r, cy - math.sin(rad) * outer_r),
            )

    dr = s * 0.125
    diamond = QPolygonF(
        [
            QPointF(cx, cy - dr),
            QPointF(cx + dr, cy),
            QPointF(cx, cy + dr),
            QPointF(cx - dr, cy),
        ]
    )
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor("#FF6B1A")))
    p.drawPolygon(diamond)
    p.restore()


class BrandMarkWidget(QWidget):
    """Widget compacto exibindo o símbolo vetorial Optical Reticle na barra lateral."""

    def __init__(self, size: int = 28, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        draw_optical_reticle(
            p,
            QRectF(0.0, 0.0, float(self.width()), float(self.height())),
            show_container=True,
            show_ticks=True,
        )
        p.end()


def _draw_nav_pixmap(kind: str, color: str, size: int = 16) -> QPixmap:
    dpr = 2
    px = QPixmap(size * dpr, size * dpr)
    px.setDevicePixelRatio(float(dpr))
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    s = float(size)
    c = s / 2.0

    if kind == "dashboard":
        r = s * 0.31
        p.drawEllipse(QRectF(c - r, c - r, r * 2.0, r * 2.0))
        p.drawLine(QPointF(c, 1.8), QPointF(c, 4.2))
        p.drawLine(QPointF(c, s - 4.2), QPointF(c, s - 1.8))
        p.drawLine(QPointF(1.8, c), QPointF(4.2, c))
        p.drawLine(QPointF(s - 4.2, c), QPointF(s - 1.8, c))
        p.setBrush(QBrush(QColor(color)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(c - 1.5, c - 1.5, 3.0, 3.0))
    elif kind == "effects":
        ys = (4.0, 8.0, 12.0)
        xs = (5.5, 11.0, 7.0)
        for y, node_x in zip(ys, xs):
            p.setPen(pen)
            p.drawLine(QPointF(2.2, y), QPointF(node_x - 2.0, y))
            p.drawLine(QPointF(node_x + 2.0, y), QPointF(s - 2.2, y))
            p.drawEllipse(QPointF(node_x, y), 1.8, 1.8)
    elif kind == "settings":
        outer = s * 0.36
        pts = []
        for idx in range(6):
            ang = math.radians(60 * idx - 30)
            pts.append(QPointF(c + math.cos(ang) * outer, c + math.sin(ang) * outer))
        p.drawPolygon(QPolygonF(pts))
        p.drawEllipse(QPointF(c, c), 2.1, 2.1)
    else:
        # diagnostics: terminal >_
        p.drawLine(QPointF(3.0, 4.5), QPointF(6.8, 8.0))
        p.drawLine(QPointF(6.8, 8.0), QPointF(3.0, 11.5))
        p.drawLine(QPointF(8.2, 11.8), QPointF(13.2, 11.8))

    p.end()
    return px


def make_nav_icon(kind: str, size: int = 16) -> QIcon:
    """Cria ícone com estados normal (#7F8794) e ativo (#FF6B1A) para a navegação."""
    icon = QIcon()
    icon.addPixmap(_draw_nav_pixmap(kind, "#7F8794", size), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_draw_nav_pixmap(kind, "#FF6B1A", size), QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(_draw_nav_pixmap(kind, "#D8DDE6", size), QIcon.Mode.Active, QIcon.State.Off)
    return icon
