"""Dashboard screen (Precision Control Stage) with optical emitter, telemetry, and simulator."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t
from app.sync_service import ServiceSnapshot, SyncService
from ui.theme import ColorPreviewWheel, StatusCard, ToggleSwitch

_WEAPON_SIM_KEYS: tuple[tuple[str, str], ...] = (
    ("simulator.weapon_rifle", "rifle"),
    ("simulator.weapon_sniper", "sniper"),
    ("simulator.weapon_pistol", "pistol"),
    ("simulator.weapon_smg", "smg"),
    ("simulator.weapon_shotgun", "shotgun"),
    ("simulator.weapon_knife", "knife"),
    ("simulator.weapon_grenade", "grenade"),
)

_ARMED_EFFECT_KEYS: tuple[tuple[str, str], ...] = (
    ("flashbang", "simulator.armed_flashbang"),
    ("shot", "simulator.armed_shot"),
    ("fire", "simulator.armed_fire"),
    ("c4", "simulator.armed_c4"),
    ("health", "simulator.armed_health"),
    ("team", "simulator.armed_team"),
    ("weapons", "simulator.armed_weapons"),
)


def _hline() -> QFrame:
    f = QFrame()
    f.setObjectName("HairlineH")
    return f


def _vline() -> QFrame:
    f = QFrame()
    f.setObjectName("HairlineV")
    return f


class DashboardPage(QWidget):
    """Dashboard with Signal Pipeline strip, Optical Stage, Telemetry, and Simulation Drawer."""

    toggleRequested = Signal()

    def __init__(self, service: SyncService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._busy = False
        self._busy_key: str | None = None
        self._sim_trigger_buttons: list[tuple[QPushButton, str]] = []
        self._sim_paused_state = False
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        header_box = QWidget()
        header_lay = QHBoxLayout(header_box)
        header_lay.setContentsMargins(28, 20, 28, 18)
        header_lay.setSpacing(16)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self._lbl_title = QLabel()
        self._lbl_title.setObjectName("PageTitle")
        self._lbl_subtitle = QLabel()
        self._lbl_subtitle.setObjectName("PageSubtitle")
        title_col.addWidget(self._lbl_title)
        title_col.addWidget(self._lbl_subtitle)
        header_lay.addLayout(title_col, 1)

        self.toggle_btn = QPushButton()
        self.toggle_btn.setObjectName("PrimaryStart")
        self.toggle_btn.setMinimumWidth(196)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self.toggleRequested.emit)
        header_lay.addWidget(self.toggle_btn)
        outer.addWidget(header_box)

        # Horizontal Signal Pipeline strip (4 hairline-separated nodes)
        strip = QFrame()
        strip.setObjectName("SignalStrip")
        strip_lay = QHBoxLayout(strip)
        strip_lay.setContentsMargins(12, 0, 12, 0)
        strip_lay.setSpacing(0)

        self.card_icue = StatusCard("")
        self.card_device = StatusCard("")
        self.card_gsi = StatusCard("")
        self.card_cs2 = StatusCard("")

        strip_lay.addWidget(self.card_icue, 1)
        strip_lay.addWidget(_vline())
        strip_lay.addWidget(self.card_device, 1)
        strip_lay.addWidget(_vline())
        strip_lay.addWidget(self.card_gsi, 1)
        strip_lay.addWidget(_vline())
        strip_lay.addWidget(self.card_cs2, 1)
        outer.addWidget(strip)

        # Scrollable main stage
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll, 1)

        stage = QWidget()
        stage.setObjectName("PageCanvas")
        stage.setAutoFillBackground(True)
        scroll.viewport().setObjectName("PageCanvas")
        scroll.viewport().setAutoFillBackground(True)
        scroll.setWidget(stage)
        stage_lay = QHBoxLayout(stage)
        stage_lay.setContentsMargins(0, 0, 0, 0)
        stage_lay.setSpacing(0)

        # Left column: Optical RGB Emitter
        left_pane = QWidget()
        left_lay = QVBoxLayout(left_pane)
        left_lay.setContentsMargins(28, 22, 28, 20)
        left_lay.setSpacing(16)

        emitter_top = QHBoxLayout()
        self._lbl_emitter_kicker = QLabel()
        self._lbl_emitter_kicker.setObjectName("Overline")
        self.lbl_engine_tick = QLabel()
        self.lbl_engine_tick.setObjectName("MonoMuted")
        emitter_top.addWidget(self._lbl_emitter_kicker)
        emitter_top.addStretch(1)
        emitter_top.addWidget(self.lbl_engine_tick)
        left_lay.addLayout(emitter_top)

        left_lay.addStretch(1)

        dial_row = QHBoxLayout()
        dial_row.setSpacing(24)
        self.wheel_preview = ColorPreviewWheel()
        dial_row.addWidget(self.wheel_preview, 0, Qt.AlignmentFlag.AlignVCenter)

        readout_col = QVBoxLayout()
        readout_col.setSpacing(6)
        self._lbl_active_kicker = QLabel()
        self._lbl_active_kicker.setObjectName("Overline")
        self.lbl_active_effect = QLabel()
        self.lbl_active_effect.setObjectName("HeroTitle")
        self.lbl_active_effect.setWordWrap(True)

        self._lbl_idle_hint = QLabel()
        self._lbl_idle_hint.setStyleSheet("color: #7A8290; font-size: 12px;")
        self._lbl_idle_hint.setWordWrap(True)

        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(0, 6, 0, 0)
        chip_row.setSpacing(10)
        self._color_chip = QFrame()
        self._color_chip.setStyleSheet(
            "background-color: #0E1014; border: 1px solid #222630; border-radius: 4px;"
        )
        chip_lay = QHBoxLayout(self._color_chip)
        chip_lay.setContentsMargins(8, 5, 10, 5)
        chip_lay.setSpacing(8)
        self._color_dot = QLabel()
        self._color_dot.setFixedSize(11, 11)
        self._color_dot.setStyleSheet(
            "background-color: #141820; border: 1px solid #2D3340; border-radius: 2px;"
        )
        self.lbl_color_hex = QLabel("#000000 (0, 0, 0)")
        self.lbl_color_hex.setObjectName("MonoReadout")
        self.lbl_color_hex.setMinimumWidth(190)
        chip_lay.addWidget(self._color_dot)
        chip_lay.addWidget(self.lbl_color_hex)
        chip_row.addWidget(self._color_chip, 0)
        chip_row.addStretch(1)

        readout_col.addWidget(self._lbl_active_kicker)
        readout_col.addWidget(self.lbl_active_effect)
        readout_col.addWidget(self._lbl_idle_hint)
        readout_col.addLayout(chip_row)
        dial_row.addLayout(readout_col, 1)
        left_lay.addLayout(dial_row)

        left_lay.addStretch(1)
        left_lay.addWidget(_hline())

        armed_row = QHBoxLayout()
        armed_row.setSpacing(10)
        self._lbl_armed_k = QLabel()
        self._lbl_armed_k.setObjectName("Overline")
        self._lbl_armed_summary = QLabel("-")
        self._lbl_armed_summary.setObjectName("MonoMuted")
        self._lbl_armed_summary.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        armed_row.addWidget(self._lbl_armed_k)
        armed_row.addWidget(self._lbl_armed_summary, 1)
        left_lay.addLayout(armed_row)

        stage_lay.addWidget(left_pane, 7)

        # Right column: Match Telemetry
        right_pane = QFrame()
        right_pane.setObjectName("TelemetryPanel")
        right_lay = QVBoxLayout(right_pane)
        right_lay.setContentsMargins(26, 22, 26, 20)
        right_lay.setSpacing(12)

        tele_head = QHBoxLayout()
        self._lbl_tele_k = QLabel()
        self._lbl_tele_k.setObjectName("Overline")
        self._lbl_map_phase = QLabel()
        self._lbl_map_phase.setObjectName("MonoMuted")
        tele_head.addWidget(self._lbl_tele_k)
        tele_head.addStretch(1)
        tele_head.addWidget(self._lbl_map_phase)
        right_lay.addLayout(tele_head)
        right_lay.addWidget(_hline())

        self.lbl_health = QLabel("-")
        self.lbl_health.setObjectName("MonoReadout")
        self.lbl_health.setMinimumWidth(56)
        self.lbl_health.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._hp_bar = QProgressBar()
        self._hp_bar.setRange(0, 100)
        self._hp_bar.setValue(0)
        self._hp_bar.setTextVisible(False)
        self._hp_bar.setFixedSize(72, 4)
        self._hp_bar.setStyleSheet(
            "QProgressBar { background-color: #1A1E26; border: none; border-radius: 2px; }"
            "QProgressBar::chunk { background-color: #22C55E; border-radius: 2px; }"
        )
        hp_val_widget = QWidget()
        hp_val_lay = QHBoxLayout(hp_val_widget)
        hp_val_lay.setContentsMargins(0, 0, 0, 0)
        hp_val_lay.setSpacing(10)
        hp_val_lay.addWidget(self._hp_bar)
        hp_val_lay.addWidget(self.lbl_health)

        self.lbl_team = QLabel("-")
        self.lbl_team.setObjectName("MonoReadout")
        self.lbl_round_phase = QLabel("-")
        self.lbl_round_phase.setObjectName("MonoReadout")
        self.lbl_weapon = QLabel("-")
        self.lbl_weapon.setObjectName("MonoReadout")
        self.lbl_ammo = QLabel("-")
        self.lbl_ammo.setObjectName("MonoReadout")

        self._tele_row_labels: list[tuple[QLabel, str]] = []
        rows = (
            ("dashboard.row_health", hp_val_widget),
            ("dashboard.row_team", self.lbl_team),
            ("dashboard.row_round_c4", self.lbl_round_phase),
            ("dashboard.row_weapon", self.lbl_weapon),
            ("dashboard.row_ammo", self.lbl_ammo),
        )
        for idx, (label_key, val_widget) in enumerate(rows):
            row_w = QWidget()
            r_lay = QHBoxLayout(row_w)
            r_lay.setContentsMargins(0, 8, 0, 8)
            r_lay.setSpacing(12)
            lbl = QLabel()
            lbl.setStyleSheet("color: #7A8290; font-size: 12.5px;")
            self._tele_row_labels.append((lbl, label_key))
            r_lay.addWidget(lbl)
            r_lay.addStretch(1)
            r_lay.addWidget(val_widget)
            right_lay.addWidget(row_w)
            if idx < len(rows) - 1:
                right_lay.addWidget(_hline())

        right_lay.addStretch(1)
        right_lay.addWidget(_hline())

        lat_row = QHBoxLayout()
        self._lbl_lat_k = QLabel()
        self._lbl_lat_k.setObjectName("Overline")
        self._lbl_latency_quick = QLabel("-")
        self._lbl_latency_quick.setObjectName("MonoMuted")
        lat_row.addWidget(self._lbl_lat_k)
        lat_row.addStretch(1)
        lat_row.addWidget(self._lbl_latency_quick)
        right_lay.addLayout(lat_row)

        stage_lay.addWidget(right_pane, 5)

        # Collapsible Simulation Drawer
        drawer = QFrame()
        drawer.setObjectName("SimDrawer")
        drawer_lay = QVBoxLayout(drawer)
        drawer_lay.setContentsMargins(28, 10, 28, 12)
        drawer_lay.setSpacing(10)

        bar_row = QHBoxLayout()
        bar_row.setSpacing(10)
        self._lbl_sim_k = QLabel()
        self._lbl_sim_k.setObjectName("Overline")
        bar_row.addWidget(self._lbl_sim_k)

        self.sim_banner = QFrame()
        self.sim_banner.setObjectName("SimBanner")
        sb_lay = QHBoxLayout(self.sim_banner)
        sb_lay.setContentsMargins(8, 2, 8, 2)
        self._lbl_sim_banner = QLabel()
        self._lbl_sim_banner.setStyleSheet(
            'color: #FF8542; font-family: "Cascadia Mono", "Consolas", monospace; '
            "font-size: 10px; font-weight: 600; letter-spacing: 0.5px;"
        )
        sb_lay.addWidget(self._lbl_sim_banner)
        self.sim_banner.setVisible(False)
        bar_row.addWidget(self.sim_banner)
        bar_row.addStretch(1)

        self._lbl_toggle_sim = QLabel()
        self._lbl_toggle_sim.setStyleSheet("color: #7A8290; font-size: 12px;")
        self.chk_simulation = ToggleSwitch()
        self.chk_simulation.toggled.connect(self._on_simulation_toggled)
        bar_row.addWidget(self._lbl_toggle_sim)
        bar_row.addWidget(self.chk_simulation)
        drawer_lay.addLayout(bar_row)

        self.sim_controls = QWidget()
        self.sim_controls.setVisible(False)
        sc_lay = QVBoxLayout(self.sim_controls)
        sc_lay.setContentsMargins(0, 6, 0, 2)
        sc_lay.setSpacing(8)

        # Row 0: Simulator lifecycle controls (Running/Paused, Pause/Resume, Reset, Stop)
        row0 = QHBoxLayout()
        row0.setSpacing(8)
        self.lbl_sim_state = QLabel()
        self.lbl_sim_state.setObjectName("MonoMuted")
        row0.addWidget(self.lbl_sim_state)

        self.btn_sim_pause = QPushButton()
        self.btn_sim_pause.clicked.connect(self._on_sim_pause_clicked)
        self.btn_sim_reset = QPushButton()
        self.btn_sim_reset.clicked.connect(self._service.reset_simulation)
        self.btn_sim_stop = QPushButton()
        self.btn_sim_stop.clicked.connect(self._on_sim_stop_clicked)
        row0.addWidget(self.btn_sim_pause)
        row0.addWidget(self.btn_sim_reset)
        row0.addWidget(self.btn_sim_stop)
        row0.addStretch(1)
        sc_lay.addLayout(row0)

        # Row 1: Flash + Shot + Fire
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self._lbl_sim_flash = QLabel()
        self._lbl_sim_flash.setStyleSheet("color: #8E95A2; font-size: 12px;")
        row1.addWidget(self._lbl_sim_flash)
        self.slider_flash = QSlider(Qt.Orientation.Horizontal)
        self.slider_flash.setRange(0, 255)
        self.slider_flash.setValue(255)
        self.slider_flash.setMaximumWidth(130)
        row1.addWidget(self.slider_flash)

        for key, fn in (
            (
                "simulator.btn_apply_flash",
                lambda: self._service.trigger_simulation(
                    "flashbang", intensity=self.slider_flash.value()
                ),
            ),
            (
                "simulator.btn_clear_flash",
                lambda: self._service.trigger_simulation("flashbang", intensity=0),
            ),
            ("simulator.btn_shot", lambda: self._service.trigger_simulation("shot")),
            (
                "simulator.btn_fire_on",
                lambda: self._service.trigger_simulation("fire", intensity=180),
            ),
            (
                "simulator.btn_fire_off",
                lambda: self._service.trigger_simulation("fire", intensity=0),
            ),
        ):
            btn = QPushButton()
            btn.clicked.connect(fn)
            self._sim_trigger_buttons.append((btn, key))
            row1.addWidget(btn)
        row1.addStretch(1)
        sc_lay.addLayout(row1)

        # Row 2: C4 & Health
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        for key, action, kwargs in (
            ("simulator.btn_plant_c4", "c4_planted", {}),
            ("simulator.btn_defuse_c4", "c4_defused", {}),
            ("simulator.btn_explode_c4", "c4_exploded", {}),
            ("simulator.btn_hp_100", "health", {"health": 100}),
            ("simulator.btn_hp_50", "health", {"health": 50}),
            ("simulator.btn_hp_15", "health", {"health": 15}),
        ):
            btn = QPushButton()
            btn.clicked.connect(
                lambda _=False, a=action, kw=kwargs: self._service.trigger_simulation(
                    a, **kw
                )
            )
            self._sim_trigger_buttons.append((btn, key))
            row2.addWidget(btn)
        row2.addStretch(1)
        sc_lay.addLayout(row2)

        # Row 3: Team, Round Phases & Weapons
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        for key, action, kwargs in (
            ("simulator.btn_team_ct", "team", {"team": "CT"}),
            ("simulator.btn_team_t", "team", {"team": "T"}),
            ("simulator.btn_freezetime", "freezetime", {}),
            ("simulator.btn_live", "live", {}),
            ("simulator.btn_over", "over", {}),
        ):
            btn = QPushButton()
            btn.clicked.connect(
                lambda _=False, a=action, kw=kwargs: self._service.trigger_simulation(
                    a, **kw
                )
            )
            self._sim_trigger_buttons.append((btn, key))
            row3.addWidget(btn)

        self.combo_sim_weapon = QComboBox()
        for label_key, key in _WEAPON_SIM_KEYS:
            self.combo_sim_weapon.addItem(t(label_key), key)
        row3.addWidget(self.combo_sim_weapon)

        btn_weapon = QPushButton()
        btn_weapon.clicked.connect(
            lambda: self._service.trigger_simulation(
                "weapon", category=self.combo_sim_weapon.currentData()
            )
        )
        self._sim_trigger_buttons.append((btn_weapon, "simulator.btn_equip_weapon"))
        row3.addWidget(btn_weapon)

        btn_disc = QPushButton()
        btn_disc.clicked.connect(lambda: self._service.trigger_simulation("disconnect"))
        self._sim_trigger_buttons.append((btn_disc, "simulator.btn_disconnect"))
        row3.addWidget(btn_disc)
        row3.addStretch(1)
        sc_lay.addLayout(row3)

        drawer_lay.addWidget(self.sim_controls)
        outer.addWidget(drawer)

        self.retranslate_ui()

    def _on_simulation_toggled(self, checked: bool) -> None:
        self._service.set_simulation_mode(checked)
        self.sim_controls.setVisible(checked)
        self.sim_controls.setEnabled(checked)
        self.sim_banner.setVisible(checked)

    def _on_sim_pause_clicked(self) -> None:
        self._service.set_simulation_paused(not self._sim_paused_state)
        self.update_from_snapshot(self._service.get_ui_snapshot())

    def _on_sim_stop_clicked(self) -> None:
        self.chk_simulation.setChecked(False)
        self.update_from_snapshot(self._service.get_ui_snapshot())

    def set_busy(self, busy: bool, text: str | None = None, text_key: str | None = None) -> None:
        self._busy = busy
        self._busy_key = text_key
        self.toggle_btn.setEnabled(not busy)
        if text:
            self.toggle_btn.setText(text)
        elif text_key:
            self.toggle_btn.setText(t(text_key))

    def retranslate_ui(self) -> None:
        self._lbl_title.setText(t("dashboard.title"))
        self._lbl_subtitle.setText(t("dashboard.subtitle"))
        self.card_icue.set_title(t("dashboard.card_icue_title"))
        self.card_device.set_title(t("dashboard.card_device_title"))
        self.card_gsi.set_title(t("dashboard.card_gsi_title"))
        self.card_cs2.set_title(t("dashboard.card_cs2_title"))

        self._lbl_emitter_kicker.setText(t("dashboard.emitter_kicker"))
        self._lbl_active_kicker.setText(t("dashboard.active_effect_kicker"))
        self._lbl_armed_k.setText(t("dashboard.armed_effects_kicker"))
        self._lbl_tele_k.setText(t("dashboard.telemetry_kicker"))
        for lbl, key in self._tele_row_labels:
            lbl.setText(t(key))
        self._lbl_lat_k.setText(t("dashboard.latency_kicker"))

        self._lbl_sim_k.setText(t("simulator.drawer_title"))
        self._lbl_sim_banner.setText(t("simulator.banner_active"))
        self._lbl_toggle_sim.setText(t("simulator.toggle_controls"))
        self._lbl_sim_flash.setText(t("simulator.flash_label"))
        self.btn_sim_reset.setText(t("simulator.btn_reset"))
        self.btn_sim_stop.setText(t("simulator.btn_stop"))

        for btn, key in self._sim_trigger_buttons:
            btn.setText(t(key))

        current_data = self.combo_sim_weapon.currentData()
        for idx, (label_key, _data) in enumerate(_WEAPON_SIM_KEYS):
            self.combo_sim_weapon.setItemText(idx, t(label_key))
        if current_data is not None:
            found_idx = self.combo_sim_weapon.findData(current_data)
            if found_idx >= 0:
                self.combo_sim_weapon.setCurrentIndex(found_idx)

        self.update_from_snapshot(self._service.get_ui_snapshot())

    def update_from_snapshot(self, snap: ServiceSnapshot) -> None:
        if self._busy and self._busy_key:
            self.toggle_btn.setText(t(self._busy_key))
        elif not self._busy:
            if snap.integration_running:
                self.toggle_btn.setText(t("dashboard.stop_btn"))
                if self.toggle_btn.objectName() != "PrimaryStop":
                    self.toggle_btn.setObjectName("PrimaryStop")
                    self.toggle_btn.style().unpolish(self.toggle_btn)
                    self.toggle_btn.style().polish(self.toggle_btn)
            else:
                self.toggle_btn.setText(t("dashboard.start_btn"))
                if self.toggle_btn.objectName() != "PrimaryStart":
                    self.toggle_btn.setObjectName("PrimaryStart")
                    self.toggle_btn.style().unpolish(self.toggle_btn)
                    self.toggle_btn.style().polish(self.toggle_btn)

        if self.chk_simulation.isChecked() != snap.simulation_mode:
            self.chk_simulation.blockSignals(True)
            self.chk_simulation.setChecked(snap.simulation_mode)
            self.chk_simulation.blockSignals(False)
        self.sim_controls.setVisible(snap.simulation_mode)
        self.sim_controls.setEnabled(snap.simulation_mode)
        self.sim_banner.setVisible(snap.simulation_mode)

        self._sim_paused_state = bool(snap.simulation_paused)
        self.lbl_sim_state.setText(
            t("simulator.state_paused" if snap.simulation_paused else "simulator.state_running")
        )
        self.lbl_sim_state.setStyleSheet(
            "color: #F59E0B;" if snap.simulation_paused else "color: #22C55E;"
        )
        self.btn_sim_pause.setText(
            t("simulator.btn_resume" if snap.simulation_paused else "simulator.btn_pause")
        )
        triggers_enabled = snap.simulation_mode and not snap.simulation_paused
        self.slider_flash.setEnabled(triggers_enabled)
        self.combo_sim_weapon.setEnabled(triggers_enabled)
        for btn, _ in self._sim_trigger_buttons:
            btn.setEnabled(triggers_enabled)

        # 1. iCUE
        icue = snap.icue_status
        if icue.sdk_connected:
            self.card_icue.set_status(
                t("common.connected"), "ok", t("dashboard.icue_sdk_active")
            )
        elif icue.icue_process_running:
            self.card_icue.set_status(
                t("dashboard.icue_running"),
                "warn",
                icue.last_error or t("dashboard.icue_waiting_sdk"),
            )
        else:
            self.card_icue.set_status(
                t("common.disconnected"), "error", t("dashboard.icue_not_detected")
            )

        # 2. Corsair Device
        if icue.device_connected:
            zone_word = t(
                "dashboard.zone_singular"
                if len(icue.led_ids) == 1
                else "dashboard.zone_plural"
            )
            self.card_device.set_status(
                t("common.connected"),
                "ok",
                f"{icue.device_model} · {len(icue.led_ids)} {zone_word}",
            )
        elif icue.device_found:
            self.card_device.set_status(
                t("common.disconnected"), "warn", icue.device_model or t("common.no_device")
            )
        else:
            self.card_device.set_status(
                t("common.no_device"), "neutral", t("dashboard.waiting_icue_hw")
            )

        # 3. GSI Server
        srv = snap.server_stats
        if srv.running:
            self.card_gsi.set_status(
                t("dashboard.gsi_listening", port=srv.port),
                "ok",
                t("dashboard.gsi_accepted_detail", count=srv.requests_accepted),
            )
        else:
            self.card_gsi.set_status(
                t("common.stopped"), "neutral", f"127.0.0.1:{srv.port}"
            )

        # 4. CS2
        gs = snap.game_state
        if snap.simulation_mode:
            self.card_cs2.set_status(
                t("dashboard.cs2_simulated"), "warn", t("dashboard.cs2_simulated_detail")
            )
        elif gs.connected:
            detail = (
                gs.map_name
                or gs.player_activity
                or t("dashboard.cs2_connected_via_gsi")
            )
            self.card_cs2.set_status(t("common.connected"), "ok", detail)
        elif srv.running:
            self.card_cs2.set_status(
                t("dashboard.cs2_waiting_game"),
                "info",
                t("dashboard.cs2_waiting_detail"),
            )
        else:
            self.card_cs2.set_status(
                t("dashboard.cs2_inactive"), "neutral", t("dashboard.cs2_integration_off")
            )

        # Optical emitter
        rs = snap.render_state
        is_lit = rs.active_effect_id != "idle" and rs.current_rgb != (0, 0, 0)
        self.wheel_preview.set_color(rs.current_rgb, is_lit)
        self.lbl_active_effect.setText(rs.active_effect_label)
        self.lbl_color_hex.setText(f"{rs.current_color_hex} {rs.current_rgb}")
        dot_bg = rs.current_color_hex if is_lit else "#141820"
        self._color_dot.setStyleSheet(
            f"background-color: {dot_bg}; border: 1px solid #2D3340; border-radius: 2px;"
        )
        hz = round(1000.0 / max(1, rs.tick_ms))
        if rs.paused:
            engine_state = t("dashboard.engine_paused")
        elif rs.running:
            engine_state = t("dashboard.engine_active")
        else:
            engine_state = t("dashboard.engine_standby")
        self.lbl_engine_tick.setText(
            t(
                "dashboard.engine_tick_fmt",
                state=engine_state,
                tick_ms=rs.tick_ms,
                hz=hz,
                frames=rs.frames_rendered,
            )
        )
        if is_lit:
            self._lbl_idle_hint.setText(t("dashboard.hint_lit"))
        elif gs.connected and gs.player_activity != "menu":
            self._lbl_idle_hint.setText(t("dashboard.hint_idle_playing"))
        elif gs.player_activity == "menu":
            self._lbl_idle_hint.setText(t("dashboard.hint_menu"))
        else:
            self._lbl_idle_hint.setText(t("dashboard.hint_disconnected"))

        # Armed effects summary
        effects_cfg = self._service.get_config().get("effects", {})
        armed = [
            t(label_key)
            for key, label_key in _ARMED_EFFECT_KEYS
            if effects_cfg.get(key, {}).get("enabled", False)
        ]
        self._lbl_armed_summary.setText(
            " · ".join(armed) if armed else t("dashboard.no_effects_enabled")
        )

        # Telemetry
        map_txt = gs.map_name or t("dashboard.waiting_map")
        if gs.round_phase:
            phase_localized = t(f"dashboard.round_{gs.round_phase}")
            map_txt = f"{map_txt} · {phase_localized}"
        self._lbl_map_phase.setText(map_txt)

        if gs.health is not None:
            self.lbl_health.setText(f"{gs.health}{t('common.hp_unit')}")
            self._hp_bar.setValue(max(0, min(100, gs.health)))
            hp_col = (
                "#22C55E"
                if gs.health >= 50
                else ("#FF6B1A" if gs.health >= 25 else "#F26D71")
            )
            self._hp_bar.setStyleSheet(
                "QProgressBar { background-color: #1A1E26; border: none; border-radius: 2px; }"
                f"QProgressBar::chunk {{ background-color: {hp_col}; border-radius: 2px; }}"
            )
        else:
            self.lbl_health.setText("-")
            self._hp_bar.setValue(0)

        if gs.team == "CT":
            self.lbl_team.setText(t("dashboard.team_ct"))
            self.lbl_team.setStyleSheet("color: #4B9BFF;")
        elif gs.team == "T":
            self.lbl_team.setText(t("dashboard.team_t"))
            self.lbl_team.setStyleSheet("color: #FF6B1A;")
        else:
            self.lbl_team.setText("-")
            self.lbl_team.setStyleSheet("color: #F2F4F7;")

        if gs.round_phase:
            phase_txt = t(f"dashboard.round_{gs.round_phase}")
        else:
            phase_txt = "-"
        if gs.bomb_state:
            bomb_txt = t(f"dashboard.bomb_{gs.bomb_state}")
            phase_txt = f"{phase_txt} (C4: {bomb_txt})"
        self.lbl_round_phase.setText(phase_txt)

        if gs.active_weapon:
            self.lbl_weapon.setText(
                f"{gs.active_weapon.name} [{gs.active_weapon.category}]"
            )
            if gs.active_weapon.ammo_clip is not None:
                clip_max = gs.active_weapon.ammo_clip_max
                ammo_str = (
                    f"{gs.active_weapon.ammo_clip}/{clip_max}"
                    if clip_max is not None
                    else str(gs.active_weapon.ammo_clip)
                )
                self.lbl_ammo.setText(ammo_str)
            else:
                self.lbl_ammo.setText("-")
        else:
            self.lbl_weapon.setText("-")
            self.lbl_ammo.setText("-")

        lat = rs.latency
        self._lbl_latency_quick.setText(
            f"{lat.last_processing_ms:.2f} ms · SDK {lat.last_sdk_call_ms:.2f} ms"
        )
