"""Gera os ícones Optical Reticle (SVG, PNG 256px e ICO multi-resolução) em assets/icons/."""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QBrush,
    QColor,
    QGuiApplication,
    QImage,
    QPainter,
    QPen,
    QPolygonF,
)

ICO_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256)

SVG_MASTER = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 64 64" fill="none">
  <rect x="2" y="2" width="60" height="60" rx="14" fill="#0B0C0F" stroke="#232833" stroke-width="1.8"/>
  <circle cx="32" cy="32" r="23" stroke="#181C24" stroke-width="1"/>
  <path d="M21.5 14A20.5 20.5 0 0 1 42.5 14" stroke="#ECEFF4" stroke-width="4.4" stroke-linecap="butt"/>
  <path d="M50 21.5A20.5 20.5 0 0 1 50 42.5" stroke="#FF6B1A" stroke-width="4.4" stroke-linecap="butt"/>
  <path d="M42.5 50A20.5 20.5 0 0 1 21.5 50" stroke="#ECEFF4" stroke-width="4.4" stroke-linecap="butt"/>
  <path d="M14 42.5A20.5 20.5 0 0 1 14 21.5" stroke="#ECEFF4" stroke-width="4.4" stroke-linecap="butt"/>
  <line x1="32" y1="7" x2="32" y2="14" stroke="#5B6372" stroke-width="2.2" stroke-linecap="round"/>
  <line x1="32" y1="50" x2="32" y2="57" stroke="#5B6372" stroke-width="2.2" stroke-linecap="round"/>
  <line x1="7" y1="32" x2="14" y2="32" stroke="#5B6372" stroke-width="2.2" stroke-linecap="round"/>
  <line x1="50" y1="32" x2="57" y2="32" stroke="#FF6B1A" stroke-width="2.2" stroke-linecap="round"/>
  <rect x="27.2" y="27.2" width="9.6" height="9.6" transform="rotate(45 32 32)" fill="#FF6B1A"/>
</svg>
"""


def render_icon_image(size: int = 256) -> QImage:
    """Renderiza o símbolo Optical Reticle adaptado oticamente ao tamanho alvo."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    s = float(size)
    c = s / 2.0

    # Contêiner obsidiana com contorno discreto
    margin = max(1.0, s * 0.032)
    bg_rect = QRectF(margin, margin, s - 2.0 * margin, s - 2.0 * margin)
    border_w = max(1.0, s * (0.042 if size <= 24 else 0.028))
    p.setPen(QPen(QColor("#232833"), border_w))
    p.setBrush(QBrush(QColor("#0B0C0F")))
    radius = s * 0.22
    p.drawRoundedRect(bg_rect, radius, radius)

    # Anel de calibração fino apenas para tamanhos >= 64px
    if size >= 64:
        cal_r = s * 0.36
        cal_rect = QRectF(c - cal_r, c - cal_r, cal_r * 2.0, cal_r * 2.0)
        p.setPen(QPen(QColor("#181C24"), max(1.0, s * 0.015)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cal_rect)

    # Quatro arcos segmentados a 90 graus (quadrante direito em #FF6B1A)
    if size <= 24:
        arc_r = s * 0.30
        stroke_w = max(2.2, s * 0.115)
        span_deg = 56
    elif size <= 48:
        arc_r = s * 0.31
        stroke_w = max(2.8, s * 0.090)
        span_deg = 54
    else:
        arc_r = s * 0.32
        stroke_w = s * 0.072
        span_deg = 52

    arc_rect = QRectF(c - arc_r, c - arc_r, arc_r * 2.0, arc_r * 2.0)
    white_pen = QPen(
        QColor("#ECEFF4"), stroke_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap
    )
    orange_pen = QPen(
        QColor("#FF6B1A"), stroke_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap
    )
    p.setBrush(Qt.BrushStyle.NoBrush)

    half_span = span_deg / 2.0
    # Qt usa 1/16 de grau no sentido anti-horário a partir das 3h (0 deg = direita)
    quadrants = (
        (90.0, white_pen),   # Topo
        (180.0, white_pen),  # Esquerda
        (270.0, white_pen),  # Base
        (0.0, orange_pen),   # Direita energizada em #FF6B1A
    )
    for center_deg, pen in quadrants:
        p.setPen(pen)
        p.drawArc(
            arc_rect,
            int(round((center_deg - half_span) * 16)),
            int(round(span_deg * 16)),
        )

    # Retículos cardinais discretos para >= 48px
    if size >= 48:
        tick_w = max(1.3, s * 0.032)
        outer_r = s * 0.395
        inner_r = s * 0.285
        for angle_deg, col in (
            (90, "#5B6372"),
            (180, "#5B6372"),
            (270, "#5B6372"),
            (0, "#FF6B1A"),
        ):
            p.setPen(QPen(QColor(col), tick_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            if angle_deg == 90:
                p.drawLine(QPointF(c, c - outer_r), QPointF(c, c - inner_r))
            elif angle_deg == 270:
                p.drawLine(QPointF(c, c + outer_r), QPointF(c, c + inner_r))
            elif angle_deg == 180:
                p.drawLine(QPointF(c - outer_r, c), QPointF(c - inner_r, c))
            else:
                p.drawLine(QPointF(c + inner_r, c), QPointF(c + outer_r, c))

    # Núcleo losangular central #FF6B1A
    diamond_r = s * (0.145 if size <= 24 else 0.115)
    diamond = QPolygonF(
        [
            QPointF(c, c - diamond_r),
            QPointF(c + diamond_r, c),
            QPointF(c, c + diamond_r),
            QPointF(c - diamond_r, c),
        ]
    )
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor("#FF6B1A")))
    p.drawPolygon(diamond)

    p.end()
    return img


def _encode_png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    ok = img.save(buf, "PNG")
    if not ok:
        raise RuntimeError("Falha ao codificar imagem PNG.")
    return bytes(buf.data())


def _encode_dib_entry_bytes(img: QImage) -> bytes:
    """Codifica uma QImage ARGB32 em payload DIB 32-bit BGRA + máscara AND para .ico."""
    argb = img.convertToFormat(QImage.Format.Format_ARGB32)
    w = argb.width()
    h = argb.height()

    ptr = argb.constBits()
    stride = argb.bytesPerLine()
    raw = bytes(ptr[: stride * h])

    xor_rows = bytearray()
    and_row_stride = ((w + 31) // 32) * 4
    and_rows = bytearray()

    for y in range(h - 1, -1, -1):
        row_start = y * stride
        row_bytes = raw[row_start : row_start + w * 4]
        xor_rows.extend(row_bytes)

        mask_row = bytearray(and_row_stride)
        for x in range(w):
            alpha = row_bytes[x * 4 + 3]
            if alpha < 128:
                mask_row[x // 8] |= 1 << (7 - (x % 8))
        and_rows.extend(mask_row)

    image_bytes = len(xor_rows) + len(and_rows)
    header = struct.pack(
        "<IiiHHIIiiII",
        40,              # biSize
        w,               # biWidth
        h * 2,           # biHeight (XOR + AND)
        1,               # biPlanes
        32,              # biBitCount (BGRA)
        0,               # biCompression (BI_RGB)
        image_bytes,     # biSizeImage
        0,               # biXPelsPerMeter
        0,               # biYPelsPerMeter
        0,               # biClrUsed
        0,               # biClrImportant
    )
    return header + bytes(xor_rows) + bytes(and_rows)


def save_multi_res_ico(images: list[QImage], ico_path: Path) -> None:
    """Grava arquivo .ico padrão Windows com múltiplas camadas de resolução."""
    count = len(images)
    entries_payloads: list[tuple[int, int, bytes]] = []
    for img in images:
        size = img.width()
        if size >= 256:
            payload = _encode_png_bytes(img)
        else:
            payload = _encode_dib_entry_bytes(img)
        entries_payloads.append((size, size, payload))

    icon_dir = struct.pack("<HHH", 0, 1, count)
    offset = 6 + count * 16
    dir_entries = bytearray()
    body = bytearray()

    for w, h, payload in entries_payloads:
        bw = 0 if w >= 256 else w
        bh = 0 if h >= 256 else h
        dir_entries.extend(
            struct.pack(
                "<BBBBHHII",
                bw,
                bh,
                0,
                0,
                1,
                32,
                len(payload),
                offset,
            )
        )
        body.extend(payload)
        offset += len(payload)

    ico_path.write_bytes(icon_dir + bytes(dir_entries) + bytes(body))


def main() -> int:
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    out_dir = Path(__file__).resolve().parent.parent / "assets" / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)

    svg_path = out_dir / "cs2_rgb_sync.svg"
    png_path = out_dir / "cs2_rgb_sync.png"
    ico_path = out_dir / "cs2_rgb_sync.ico"

    svg_path.write_text(SVG_MASTER, encoding="utf-8")

    images = [render_icon_image(sz) for sz in ICO_SIZES]
    ok_png = images[-1].save(str(png_path), "PNG")
    save_multi_res_ico(images, ico_path)

    print(
        f"SVG={svg_path} | PNG={png_path} ({ok_png}) | "
        f"ICO={ico_path} (camadas={list(ICO_SIZES)})"
    )
    return 0 if ok_png and ico_path.is_file() else 1


if __name__ == "__main__":
    raise SystemExit(main())
