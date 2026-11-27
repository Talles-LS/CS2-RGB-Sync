"""Technical diagnostics tab (Telemetry Console) with live i18n support."""

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

from app.i18n import t
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
    """Technical diagnostics console: metric ribbon, redacted payload, events, and logs."""

    def __init__(self, service: SyncService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._last_payload_str = ""
        self._last_logs_str = ""
        self._build_ui()

    @staticmethod
    def _ribbon_cell() -> tuple[QWidget, QLabel, QLabel]:
        cell = QWidget()
        v = QVBoxLayout(cell)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(2)
        k = QLabel()
        k.setObjectName("Overline")
        val = QLabel("-")
        val.setObjectName("MonoReadout")
        val.setWordWrap(True)
        val.setStyleSheet(
            'color: #E8ECF2; font-family: "Cascadia Mono", "Consolas", monospace; font-size: 11.5px;'
        )
        v.addWidget(k)
        v.addWidget(val)
        return cell, k, val

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

        self.btn_copy_logs = QPushButton()
        self.btn_copy_logs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_logs.clicked.connect(self._copy_logs)
        top.addWidget(self.btn_copy_logs)
        outer.addWidget(header)

        ribbon = QFrame()
        ribbon.setObjectName("SignalStrip")
        rib_lay = QHBoxLayout(ribbon)
        rib_lay.setContentsMargins(12, 0, 12, 0)
        rib_lay.setSpacing(0)

        c1, self._k_sdk, self.lbl_sdk_state = self._ribbon_cell()
        c2, self._k_dev, self.lbl_device = self._ribbon_cell()
        c3, self._k_cmd, self.lbl_last_cmd = self._ribbon_cell()
        c4, self._k_req, self.lbl_req_stats = self._ribbon_cell()
        c5, self._k_lat, self.lbl_latency = self._ribbon_cell()

        for idx, (cell, stretch) in enumerate(((c1, 1), (c2, 1), (c3, 2), (c4, 1), (c5, 1))):
            rib_lay.addWidget(cell, stretch)
            if idx < 4:
                rib_lay.addWidget(_vline())
        outer.addWidget(ribbon)

        split_host = QWidget()
        split = QHBoxLayout(split_host)
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(0)

        left = QWidget()
        p_lay = QVBoxLayout(left)
        p_lay.setContentsMargins(24, 16, 20, 16)
        p_lay.setSpacing(8)
        self._p_title = QLabel()
        self._p_title.setObjectName("Overline")
        p_lay.addWidget(self._p_title)
        self.txt_payload = QPlainTextEdit()
        self.txt_payload.setReadOnly(True)
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
        self._e_title = QLabel()
        self._e_title.setObjectName("Overline")
        e_lay.addWidget(self._e_title)
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

        logs_host = QFrame()
        logs_host.setStyleSheet("background-color: #060709;")
        l_lay = QVBoxLayout(logs_host)
        l_lay.setContentsMargins(24, 14, 24, 16)
        l_lay.setSpacing(8)
        self._l_title = QLabel()
        self._l_title.setObjectName("Overline")
        l_lay.addWidget(self._l_title)
        self.txt_logs = QPlainTextEdit()
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setMaximumHeight(165)
        self.txt_logs.setStyleSheet(
            'background-color: #08090C; border: 1px solid #161920; '
            'font-family: "Cascadia Mono", "Consolas", monospace; font-size: 11px; color: #8B94A3;'
        )
        l_lay.addWidget(self.txt_logs)
        outer.addWidget(logs_host, 2)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self._lbl_title.setText(t("diagnostics.title"))
        self._lbl_subtitle.setText(t("diagnostics.subtitle"))
        self.btn_copy_logs.setText(t("diagnostics.btn_copy_logs"))

        self._k_sdk.setText(t("diagnostics.cell_sdk"))
        self._k_dev.setText(t("diagnostics.cell_device"))
        self._k_cmd.setText(t("diagnostics.cell_last_cmd"))
        self._k_req.setText(t("diagnostics.cell_req_stats"))
        self._k_lat.setText(t("diagnostics.cell_latency"))

        self._p_title.setText(t("diagnostics.payload_title"))
        self.txt_payload.setPlaceholderText(t("diagnostics.payload_placeholder"))
        self._e_title.setText(t("diagnostics.events_title"))
        self._l_title.setText(t("diagnostics.logs_title"))

        self.update_from_snapshot(self._service.get_ui_snapshot())

    def _copy_logs(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.txt_logs.toPlainText())

    def update_from_snapshot(self, snap: ServiceSnapshot) -> None:
        icue = snap.icue_status
        self.lbl_sdk_state.setText(
            f"{icue.session_state}" + (f" ({icue.last_error})" if icue.last_error else "")
        )
        if icue.device_found:
            led_word = t(
                "diagnostics.led_singular"
                if len(icue.led_ids) == 1
                else "diagnostics.led_plural"
            )
            self.lbl_device.setText(f"{icue.device_model} · {len(icue.led_ids)} {led_word}")
        else:
            self.lbl_device.setText(t("common.no_device"))
        self.lbl_last_cmd.setText(
            f"RGBA={icue.last_rgba} ({icue.commands_sent}/{icue.commands_skipped})"
        )

        srv = snap.server_stats
        self.lbl_req_stats.setText(
            t(
                "diagnostics.req_stats_fmt",
                accepted=srv.requests_accepted,
                errors=srv.auth_failures + srv.parse_errors,
                queue=srv.queue_size,
            )
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
        elif self._last_payload_str:
            self._last_payload_str = ""
            self.txt_payload.clear()

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
