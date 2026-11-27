"""Tela principal (Dashboard — Precision Control Stage) do CS2 RGB Sync."""

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

from app.sync_service import ServiceSnapshot, SyncService
from ui.theme import ColorPreviewWheel, StatusCard, ToggleSwitch

_WEAPON_SIM_OPTIONS = [
    ("Rifle (AK-47)", "rifle"),
    ("Sniper (AWP)", "sniper"),
    ("Pistola (Desert Eagle)", "pistol"),
    ("SMG (MP9)", "smg"),
    ("Escopeta (MAG-7)", "shotgun"),
    ("Faca (Karambit)", "knife"),
    ("Granada (Flashbang)", "grenade"),
]

_ARMED_EFFECT_NAMES = (
    ("flashbang", "Flashbang"),
    ("shot", "Disparo"),
    ("fire", "Fogo"),
    ("c4", "C4"),
    ("health", "Vida"),
    ("team", "Freezetime CT/TR"),
    ("weapons", "Arma"),
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
    """Painel com faixa Signal Pipeline, Palco Óptico, Telemetria e Gaveta de Simulação."""

    toggleRequested = Signal()

    def __init__(self, service: SyncService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._busy = False
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Cabeçalho
        header_box = QWidget()
        header_lay = QHBoxLayout(header_box)
        header_lay.setContentsMargins(28, 20, 28, 18)
        header_lay.setSpacing(16)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Painel de Controle")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Sincronização óptica em tempo real · Counter-Strike 2 GSI")
        subtitle.setObjectName("PageSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header_lay.addLayout(title_col, 1)

        self.toggle_btn = QPushButton("INICIAR INTEGRAÇÃO")
        self.toggle_btn.setObjectName("PrimaryStart")
        self.toggle_btn.setMinimumWidth(196)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self.toggleRequested.emit)
        header_lay.addWidget(self.toggle_btn)
        outer.addWidget(header_box)

        # Faixa horizontal Signal Pipeline (4 nós divididos por hairlines)
        strip = QFrame()
        strip.setObjectName("SignalStrip")
        strip_lay = QHBoxLayout(strip)
        strip_lay.setContentsMargins(12, 0, 12, 0)
        strip_lay.setSpacing(0)

        self.card_icue = StatusCard("01 · Corsair iCUE")
        self.card_device = StatusCard("02 · Dispositivo")
        self.card_gsi = StatusCard("03 · Servidor GSI")
        self.card_cs2 = StatusCard("04 · Counter-Strike 2")

        strip_lay.addWidget(self.card_icue, 1)
        strip_lay.addWidget(_vline())
        strip_lay.addWidget(self.card_device, 1)
        strip_lay.addWidget(_vline())
        strip_lay.addWidget(self.card_gsi, 1)
        strip_lay.addWidget(_vline())
        strip_lay.addWidget(self.card_cs2, 1)
        outer.addWidget(strip)

        # Área principal rolável em janelas menores
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

        # Coluna Esquerda: Emissor Óptico RGB
        left_pane = QWidget()
        left_lay = QVBoxLayout(left_pane)
        left_lay.setContentsMargins(28, 22, 28, 20)
        left_lay.setSpacing(16)

        emitter_top = QHBoxLayout()
        lbl_emitter_kicker = QLabel("EMISSOR ÓPTICO · ILUMINAÇÃO RGB")
        lbl_emitter_kicker.setObjectName("Overline")
        self.lbl_engine_tick = QLabel("MOTOR EM ESPERA · 25 MS")
        self.lbl_engine_tick.setObjectName("MonoMuted")
        emitter_top.addWidget(lbl_emitter_kicker)
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
        lbl_active_kicker = QLabel("EFEITO ATIVO")
        lbl_active_kicker.setObjectName("Overline")
        self.lbl_active_effect = QLabel("Aguardando")
        self.lbl_active_effect.setObjectName("HeroTitle")
        self.lbl_active_effect.setWordWrap(True)

        self._lbl_idle_hint = QLabel("LED apagado em momentos neutros da partida")
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

        readout_col.addWidget(lbl_active_kicker)
        readout_col.addWidget(self.lbl_active_effect)
        readout_col.addWidget(self._lbl_idle_hint)
        readout_col.addLayout(chip_row)
        dial_row.addLayout(readout_col, 1)
        left_lay.addLayout(dial_row)

        left_lay.addStretch(1)
        left_lay.addWidget(_hline())

        armed_row = QHBoxLayout()
        armed_row.setSpacing(10)
        lbl_armed_k = QLabel("EFEITOS ARMADOS")
        lbl_armed_k.setObjectName("Overline")
        self._lbl_armed_summary = QLabel("-")
        self._lbl_armed_summary.setObjectName("MonoMuted")
        self._lbl_armed_summary.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        armed_row.addWidget(lbl_armed_k)
        armed_row.addWidget(self._lbl_armed_summary, 1)
        left_lay.addLayout(armed_row)

        stage_lay.addWidget(left_pane, 7)

        # Coluna Direita: Telemetria da Partida
        right_pane = QFrame()
        right_pane.setObjectName("TelemetryPanel")
        right_lay = QVBoxLayout(right_pane)
        right_lay.setContentsMargins(26, 22, 26, 20)
        right_lay.setSpacing(12)

        tele_head = QHBoxLayout()
        lbl_tele_k = QLabel("TELEMETRIA DA PARTIDA")
        lbl_tele_k.setObjectName("Overline")
        self._lbl_map_phase = QLabel("aguardando mapa")
        self._lbl_map_phase.setObjectName("MonoMuted")
        tele_head.addWidget(lbl_tele_k)
        tele_head.addStretch(1)
        tele_head.addWidget(self._lbl_map_phase)
        right_lay.addLayout(tele_head)
        right_lay.addWidget(_hline())

        # Linhas de telemetria
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

        rows = (
            ("Vida", hp_val_widget),
            ("Equipe", self.lbl_team),
            ("Round / C4", self.lbl_round_phase),
            ("Arma ativa", self.lbl_weapon),
            ("Munição", self.lbl_ammo),
        )
        for idx, (label_txt, val_widget) in enumerate(rows):
            row_w = QWidget()
            r_lay = QHBoxLayout(row_w)
            r_lay.setContentsMargins(0, 8, 0, 8)
            r_lay.setSpacing(12)
            lbl = QLabel(label_txt)
            lbl.setStyleSheet("color: #7A8290; font-size: 12.5px;")
            r_lay.addWidget(lbl)
            r_lay.addStretch(1)
            r_lay.addWidget(val_widget)
            right_lay.addWidget(row_w)
            if idx < len(rows) - 1:
                right_lay.addWidget(_hline())

        right_lay.addStretch(1)
        right_lay.addWidget(_hline())

        lat_row = QHBoxLayout()
        lbl_lat_k = QLabel("LATÊNCIA SW / SDK")
        lbl_lat_k.setObjectName("Overline")
        self._lbl_latency_quick = QLabel("-")
        self._lbl_latency_quick.setObjectName("MonoMuted")
        lat_row.addWidget(lbl_lat_k)
        lat_row.addStretch(1)
        lat_row.addWidget(self._lbl_latency_quick)
        right_lay.addLayout(lat_row)

        stage_lay.addWidget(right_pane, 5)

        # Gaveta Colapsável de Simulação
        drawer = QFrame()
        drawer.setObjectName("SimDrawer")
        drawer_lay = QVBoxLayout(drawer)
        drawer_lay.setContentsMargins(28, 10, 28, 12)
        drawer_lay.setSpacing(10)

        bar_row = QHBoxLayout()
        bar_row.setSpacing(12)
        lbl_sim_k = QLabel("SIMULAÇÃO MANUAL (TESTE SEM CS2)")
        lbl_sim_k.setObjectName("Overline")
        bar_row.addWidget(lbl_sim_k)

        self.sim_banner = QFrame()
        self.sim_banner.setObjectName("SimBanner")
        sb_lay = QHBoxLayout(self.sim_banner)
        sb_lay.setContentsMargins(8, 2, 8, 2)
        sb_lbl = QLabel("SIMULAÇÃO ATIVA · NÃO REPRESENTA PARTIDA REAL")
        sb_lbl.setStyleSheet(
            'color: #FF8542; font-family: "Cascadia Mono", "Consolas", monospace; '
            "font-size: 10px; font-weight: 600; letter-spacing: 0.5px;"
        )
        sb_lay.addWidget(sb_lbl)
        self.sim_banner.setVisible(False)
        bar_row.addWidget(self.sim_banner)
        bar_row.addStretch(1)

        lbl_toggle_sim = QLabel("Ativar controles")
        lbl_toggle_sim.setStyleSheet("color: #7A8290; font-size: 12px;")
        self.chk_simulation = ToggleSwitch()
        self.chk_simulation.toggled.connect(self._on_simulation_toggled)
        bar_row.addWidget(lbl_toggle_sim)
        bar_row.addWidget(self.chk_simulation)
        drawer_lay.addLayout(bar_row)

        self.sim_controls = QWidget()
        self.sim_controls.setVisible(False)
        sc_lay = QVBoxLayout(self.sim_controls)
        sc_lay.setContentsMargins(0, 6, 0, 2)
        sc_lay.setSpacing(8)

        # Linha 1: Flash + Disparo + Fogo
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        lbl_fl = QLabel("Flashbang:")
        lbl_fl.setStyleSheet("color: #8E95A2; font-size: 12px;")
        row1.addWidget(lbl_fl)
        self.slider_flash = QSlider(Qt.Orientation.Horizontal)
        self.slider_flash.setRange(0, 255)
        self.slider_flash.setValue(255)
        self.slider_flash.setMaximumWidth(130)
        row1.addWidget(self.slider_flash)

        btn_flash = QPushButton("Aplicar Flash")
        btn_flash.clicked.connect(
            lambda: self._service.trigger_simulation(
                "flashbang", intensity=self.slider_flash.value()
            )
        )
        btn_clear_flash = QPushButton("Limpar Flash")
        btn_clear_flash.clicked.connect(
            lambda: self._service.trigger_simulation("flashbang", intensity=0)
        )
        btn_shot = QPushButton("Disparar")
        btn_shot.clicked.connect(lambda: self._service.trigger_simulation("shot"))
        btn_fire_on = QPushButton("Fogo (Ativar)")
        btn_fire_on.clicked.connect(
            lambda: self._service.trigger_simulation("fire", intensity=180)
        )
        btn_fire_off = QPushButton("Fogo (Parar)")
        btn_fire_off.clicked.connect(
            lambda: self._service.trigger_simulation("fire", intensity=0)
        )
        for w in (btn_flash, btn_clear_flash, btn_shot, btn_fire_on, btn_fire_off):
            row1.addWidget(w)
        row1.addStretch(1)
        sc_lay.addLayout(row1)

        # Linha 2: C4 e Vida
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        for text, action, kwargs in (
            ("Plantar C4", "c4_planted", {}),
            ("Desarmar C4", "c4_defused", {}),
            ("Explodir C4", "c4_exploded", {}),
            ("100 HP", "health", {"health": 100}),
            ("50 HP", "health", {"health": 50}),
            ("15 HP (Crítica)", "health", {"health": 15}),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(
                lambda _=False, a=action, kw=kwargs: self._service.trigger_simulation(a, **kw)
            )
            row2.addWidget(btn)
        row2.addStretch(1)
        sc_lay.addLayout(row2)

        # Linha 3: Equipe, Round e Arma
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        for text, action, kwargs in (
            ("CT", "team", {"team": "CT"}),
            ("TR", "team", {"team": "T"}),
            ("Freezetime", "freezetime", {}),
            ("Round Ativo", "live", {}),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(
                lambda _=False, a=action, kw=kwargs: self._service.trigger_simulation(a, **kw)
            )
            row3.addWidget(btn)

        self.combo_sim_weapon = QComboBox()
        for label, key in _WEAPON_SIM_OPTIONS:
            self.combo_sim_weapon.addItem(label, key)
        row3.addWidget(self.combo_sim_weapon)

        btn_weapon = QPushButton("Equipar Arma")
        btn_weapon.clicked.connect(
            lambda: self._service.trigger_simulation(
                "weapon", category=self.combo_sim_weapon.currentData()
            )
        )
        btn_disc = QPushButton("Desconectar Simulação")
        btn_disc.clicked.connect(lambda: self._service.trigger_simulation("disconnect"))
        row3.addWidget(btn_weapon)
        row3.addWidget(btn_disc)
        row3.addStretch(1)
        sc_lay.addLayout(row3)

        drawer_lay.addWidget(self.sim_controls)
        outer.addWidget(drawer)

    def _on_simulation_toggled(self, checked: bool) -> None:
        self._service.set_simulation_mode(checked)
        self.sim_controls.setVisible(checked)
        self.sim_controls.setEnabled(checked)
        self.sim_banner.setVisible(checked)

    def set_busy(self, busy: bool, text: str | None = None) -> None:
        self._busy = busy
        self.toggle_btn.setEnabled(not busy)
        if text:
            self.toggle_btn.setText(text)

    def update_from_snapshot(self, snap: ServiceSnapshot) -> None:
        if not self._busy:
            if snap.integration_running:
                self.toggle_btn.setText("PARAR INTEGRAÇÃO")
                if self.toggle_btn.objectName() != "PrimaryStop":
                    self.toggle_btn.setObjectName("PrimaryStop")
                    self.toggle_btn.style().unpolish(self.toggle_btn)
                    self.toggle_btn.style().polish(self.toggle_btn)
            else:
                self.toggle_btn.setText("INICIAR INTEGRAÇÃO")
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

        # 1. iCUE
        icue = snap.icue_status
        if icue.sdk_connected:
            self.card_icue.set_status("Conectado", "ok", "SDK v4 ativo")
        elif icue.icue_process_running:
            self.card_icue.set_status(
                "iCUE em execução",
                "warn",
                icue.last_error or "Aguardando inicialização do SDK",
            )
        else:
            self.card_icue.set_status("Desconectado", "error", "Corsair iCUE não detectado")

        # 2. Dispositivo Corsair
        if icue.device_connected:
            zona_word = "zona" if len(icue.led_ids) == 1 else "zonas"
            self.card_device.set_status(
                "Conectado",
                "ok",
                f"{icue.device_model} · {len(icue.led_ids)} {zona_word}",
            )
        elif icue.device_found:
            self.card_device.set_status(
                "Desconectado", "warn", icue.device_model or "NENHUM DISPOSITIVO"
            )
        else:
            self.card_device.set_status(
                "NENHUM DISPOSITIVO", "neutral", "Aguardando hardware iCUE"
            )

        # 3. Servidor GSI
        srv = snap.server_stats
        if srv.running:
            self.card_gsi.set_status(
                f"Escutando :{srv.port}",
                "ok",
                f"127.0.0.1 · {srv.requests_accepted} aceita(s)",
            )
        else:
            self.card_gsi.set_status("Parado", "neutral", f"127.0.0.1:{srv.port}")

        # 4. CS2
        gs = snap.game_state
        if snap.simulation_mode:
            self.card_cs2.set_status("Simulado", "warn", "Modo de teste interno")
        elif gs.connected:
            detail = gs.map_name or gs.player_activity or "Conectado via GSI"
            self.card_cs2.set_status("Conectado", "ok", detail)
        elif srv.running:
            self.card_cs2.set_status("Aguardando jogo", "info", "Pronto para payloads GSI")
        else:
            self.card_cs2.set_status("Inativo", "neutral", "Integração desligada")

        # Emissor óptico
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
        self.lbl_engine_tick.setText(
            f"{'ATIVO' if rs.running else 'EM ESPERA'} · {rs.tick_ms} MS ({hz} HZ) · {rs.frames_rendered} FRAMES"
        )
        if is_lit:
            self._lbl_idle_hint.setText("Iluminação aplicada em tempo real no dispositivo")
        elif gs.connected and gs.player_activity != "menu":
            self._lbl_idle_hint.setText("Em espera · LED mantido apagado (0, 0, 0)")
        elif gs.player_activity == "menu":
            self._lbl_idle_hint.setText("No menu do CS2 · Controle devolvido ao iCUE")
        else:
            self._lbl_idle_hint.setText("Desconectado ou em repouso · Controle nativo no iCUE")

        # Resumo de efeitos armados
        effects_cfg = self._service.get_config().get("effects", {})
        armed = [
            label
            for key, label in _ARMED_EFFECT_NAMES
            if effects_cfg.get(key, {}).get("enabled", False)
        ]
        self._lbl_armed_summary.setText(
            " · ".join(armed) if armed else "Nenhum efeito ativado"
        )

        # Telemetria
        map_txt = gs.map_name or "aguardando mapa"
        if gs.round_phase:
            map_txt = f"{map_txt} · {gs.round_phase}"
        self._lbl_map_phase.setText(map_txt)

        if gs.health is not None:
            self.lbl_health.setText(f"{gs.health} HP")
            self._hp_bar.setValue(max(0, min(100, gs.health)))
            hp_col = "#22C55E" if gs.health >= 50 else ("#FF6B1A" if gs.health >= 25 else "#F26D71")
            self._hp_bar.setStyleSheet(
                "QProgressBar { background-color: #1A1E26; border: none; border-radius: 2px; }"
                f"QProgressBar::chunk {{ background-color: {hp_col}; border-radius: 2px; }}"
            )
        else:
            self.lbl_health.setText("-")
            self._hp_bar.setValue(0)

        self.lbl_team.setText(gs.team or "-")
        if gs.team == "CT":
            self.lbl_team.setStyleSheet("color: #4B9BFF;")
        elif gs.team == "T":
            self.lbl_team.setStyleSheet("color: #FF6B1A;")
        else:
            self.lbl_team.setStyleSheet("color: #F2F4F7;")

        phase_txt = gs.round_phase or "-"
        if gs.bomb_state:
            phase_txt = f"{phase_txt} (C4: {gs.bomb_state})"
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
