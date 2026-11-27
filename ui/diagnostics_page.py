"""Aba de diagnóstico técnico (Telemetry Console) sem excesso de cards."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.sync_service import ServiceSnapshot, SyncService


def _hline() -> QFrame:
    f = QFrame()
    f.setObjectName("HairlineH")
    return f


def _vline() -> QFrame:
    f = QFrame()
    f.setObjectName("HairlineV")
    return f


class DiagnosticsPage(QWidget):
    """Console técnico de diagnóstico: fita de métricas, payload sanitizado, eventos e logs."""

    def __init__(self, service: SyncService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._last_payload_str = ""
        self._last_logs_str = ""
        self._build_ui()

    @staticmethod
    def _ribbon_cell(title: str) -> tuple[QWidget, QLabel]:
        cell = QWidget()
        v = QVBoxLayout(cell)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(2)
        k = QLabel(title)
        k.setObjectName("Overline")
        val = QLabel("-")
        val.setObjectName("MonoReadout")
        val.setWordWrap(True)
        val.setStyleSheet(
            'color: #E8ECF2; font-family: "Cascadia Mono", "Consolas", monospace; font-size: 11.5px;'
        )
        v.addWidget(k)
        v.addWidget(val)
        return cell, val

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Cabeçalho
        header = QWidget()
        top = QHBoxLayout(header)
        top.setContentsMargins(28, 20, 28, 18)
        top.setSpacing(12)

        tcol = QVBoxLayout()
        tcol.setSpacing(2)
        title = QLabel("Diagnóstico & Telemetria")
        title.setObjectName("PageTitle")
        sub = QLabel(
            "Inspeção em tempo real do payload GSI mascarado, fila de eventos e decisões RGB"
        )
        sub.setObjectName("PageSubtitle")
        tcol.addWidget(title)
        tcol.addWidget(sub)
        top.addLayout(tcol, 1)

        self.btn_copy_logs = QPushButton("Copiar Logs")
        self.btn_copy_logs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_logs.clicked.connect(self._copy_logs)
        top.addWidget(self.btn_copy_logs)
        outer.addWidget(header)

        # Fita horizontal de métricas técnicas
        ribbon = QFrame()
        ribbon.setObjectName("SignalStrip")
        rib_lay = QHBoxLayout(ribbon)
        rib_lay.setContentsMargins(12, 0, 12, 0)
        rib_lay.setSpacing(0)

        c1, self.lbl_sdk_state = self._ribbon_cell("ESTADO SDK")
        c2, self.lbl_device = self._ribbon_cell("DISPOSITIVO")
        c3, self.lbl_last_cmd = self._ribbon_cell("ÚLTIMO COMANDO")
        c4, self.lbl_req_stats = self._ribbon_cell("REQUISIÇÕES GSI")
        c5, self.lbl_latency = self._ribbon_cell("LATÊNCIA SW / SDK")

        for idx, (cell, stretch) in enumerate(((c1, 1), (c2, 1), (c3, 2), (c4, 1), (c5, 1))):
            rib_lay.addWidget(cell, stretch)
            if idx < 4:
                rib_lay.addWidget(_vline())
        outer.addWidget(ribbon)

        # Split central: Último Payload (esq) + Eventos Recentes (dir)
        split_host = QWidget()
        split = QHBoxLayout(split_host)
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(0)

        left = QWidget()
        p_lay = QVBoxLayout(left)
        p_lay.setContentsMargins(24, 16, 20, 16)
        p_lay.setSpacing(8)
        p_title = QLabel("ÚLTIMO PAYLOAD GSI (TOKEN MASCARADO)")
        p_title.setObjectName("Overline")
        p_lay.addWidget(p_title)
        self.txt_payload = QPlainTextEdit()
        self.txt_payload.setReadOnly(True)
        self.txt_payload.setPlaceholderText("Nenhum payload GSI recebido ainda.")
        self.txt_payload.setStyleSheet(
            'background-color: #0B0D10; border: 1px solid #181B21; '
            'font-family: "Cascadia Mono", "Consolas", monospace; font-size: 11.5px; color: #A6B0BE;'
        )
        p_lay.addWidget(self.txt_payload)
        split.addWidget(left, 1)
        split.addWidget(_vline())

        right = QWidget()
        e_lay = QVBoxLayout(right)
        e_lay.setContentsMargins(20, 16, 24, 16)
        e_lay.setSpacing(8)
        e_title = QLabel("EVENTOS DETECTADOS")
        e_title.setObjectName("Overline")
        e_lay.addWidget(e_title)
        self.list_events = QListWidget()
        self.list_events.setWordWrap(True)
        self.list_events.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_events.setStyleSheet(
            'background-color: #0B0D10; border: 1px solid #181B21; '
            'font-family: "Cascadia Mono", "Consolas", monospace; font-size: 11.5px;'
        )
        e_lay.addWidget(self.list_events)
        split.addWidget(right, 1)

        outer.addWidget(split_host, 3)
        outer.addWidget(_hline())

        # Console inferior de logs
        logs_host = QFrame()
        logs_host.setStyleSheet("background-color: #060709;")
        l_lay = QVBoxLayout(logs_host)
        l_lay.setContentsMargins(24, 14, 24, 16)
        l_lay.setSpacing(8)
        l_title = QLabel("CONSOLE DE LOGS DO APLICATIVO")
        l_title.setObjectName("Overline")
        l_lay.addWidget(l_title)
        self.txt_logs = QPlainTextEdit()
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setMaximumHeight(165)
        self.txt_logs.setStyleSheet(
            'background-color: #08090C; border: 1px solid #161920; '
            'font-family: "Cascadia Mono", "Consolas", monospace; font-size: 11px; color: #8B94A3;'
        )
        l_lay.addWidget(self.txt_logs)
        outer.addWidget(logs_host, 2)

    def _copy_logs(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.txt_logs.toPlainText())

    def update_from_snapshot(self, snap: ServiceSnapshot) -> None:
        icue = snap.icue_status
        self.lbl_sdk_state.setText(
            f"{icue.session_state}" + (f" ({icue.last_error})" if icue.last_error else "")
        )
        self.lbl_device.setText(
            f"{icue.device_model} · {len(icue.led_ids)} LED(s)"
            if icue.device_found
            else "NENHUM DISPOSITIVO"
        )
        self.lbl_last_cmd.setText(
            f"RGBA={icue.last_rgba} ({icue.commands_sent}/{icue.commands_skipped})"
        )

        srv = snap.server_stats
        self.lbl_req_stats.setText(
            f"ok={srv.requests_accepted} · err={srv.auth_failures + srv.parse_errors} · fila={srv.queue_size}"
        )

        lat = snap.render_state.latency
        self.lbl_latency.setText(
            f"{lat.last_processing_ms:.2f} / {lat.last_sdk_call_ms:.2f} ms"
        )

        if snap.last_payload is not None:
            pretty = json.dumps(snap.last_payload, indent=2, ensure_ascii=False)
            if pretty != self._last_payload_str:
                self._last_payload_str = pretty
                self.txt_payload.setPlainText(pretty)

        self.list_events.clear()
        for ev in snap.recent_events[:40]:
            prefix = "[SIM] " if ev.simulation else ""
            self.list_events.addItem(
                f"{ev.timestamp_str} {prefix}{ev.event_type}: {ev.summary}"
            )

        if snap.recent_logs != self._last_logs_str:
            self._last_logs_str = snap.recent_logs
            self.txt_logs.setPlainText(snap.recent_logs)
            sb = self.txt_logs.verticalScrollBar()
            if sb is not None:
                sb.setValue(sb.maximum())
