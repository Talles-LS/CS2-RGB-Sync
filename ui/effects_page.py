"""Aba Master-Detail Studio para efeitos RGB e hierarquia de prioridades."""

from __future__ import annotations

import copy
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.sync_service import SyncService
from ui.theme import ColorPickerButton, EffectSignatureBar, ToggleSwitch

_DEFAULT_PRIORITY_IDS = [
    "flashbang",
    "shot",
    "fire",
    "c4",
    "health_critical",
    "health",
    "team_round",
    "weapon",
]

_GROUP_META: dict[str, dict[str, Any]] = {
    "flashbang": {
        "title": "Flashbang",
        "desc": "Clarão proporcional à cegueira real",
        "priority_keys": ["flashbang"],
        "sig_mode": "fade",
    },
    "shot": {
        "title": "Disparos",
        "desc": "Pulso curto via ammo_clip",
        "priority_keys": ["shot"],
        "sig_mode": "pulse",
    },
    "fire": {
        "title": "Dano de Fogo",
        "desc": "Oscilação térmica · acima da C4",
        "priority_keys": ["fire"],
        "sig_mode": "gradient",
    },
    "c4": {
        "title": "C4 Plantada",
        "desc": "Bipes acelerando até 40 s",
        "priority_keys": ["c4"],
        "sig_mode": "beeps",
    },
    "health": {
        "title": "Vida & Vida Crítica",
        "desc": "Gradiente de HP e alerta crítico",
        "priority_keys": ["health_critical", "health"],
        "sig_mode": "gradient",
    },
    "team_round": {
        "title": "Freezetime (CT / TR)",
        "desc": "Cores CT / TR exclusivamente no Freezetime",
        "priority_keys": ["team_round"],
        "sig_mode": "segments",
    },
    "weapon": {
        "title": "Arma Equipada",
        "desc": "Cor por categoria de arma",
        "priority_keys": ["weapon"],
        "sig_mode": "segments",
    },
}

_WEAPON_LABELS = {
    "knife": "Facas",
    "pistol": "Pistolas",
    "rifle": "Rifles",
    "sniper": "Snipers",
    "smg": "SMGs",
    "shotgun": "Escopetas",
    "grenade": "Granadas",
}


def _hline() -> QFrame:
    line = QFrame()
    line.setObjectName("HairlineH")
    return line


class _MasterEffectRow(QFrame):
    """Linha clicável na coluna Master com índice de prioridade, filete colorido e toggle."""

    clicked = Signal(str)

    def __init__(self, group_id: str, toggle: ToggleSwitch, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.group_id = group_id
        self.toggle = toggle
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 11, 14, 11)
        lay.setSpacing(11)

        self.lbl_rank = QLabel("01")
        self.lbl_rank.setObjectName("MonoMuted")
        self.lbl_rank.setFixedWidth(20)
        lay.addWidget(self.lbl_rank)

        self._stripe = QLabel()
        self._stripe.setFixedSize(3, 28)
        self._stripe.setStyleSheet("background-color: #FF6B1A; border-radius: 1px;")
        lay.addWidget(self._stripe)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)
        self.lbl_name = QLabel(_GROUP_META[group_id]["title"])
        self.lbl_name.setStyleSheet("color: #F2F4F7; font-size: 13px; font-weight: 500;")
        self.lbl_desc = QLabel(_GROUP_META[group_id]["desc"])
        self.lbl_desc.setStyleSheet("color: #636B7A; font-size: 11px;")
        text_col.addWidget(self.lbl_name)
        text_col.addWidget(self.lbl_desc)
        lay.addLayout(text_col, 1)

        lay.addWidget(toggle)
        self._apply_row_style()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.clicked.emit(self.group_id)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._apply_row_style()

    def set_rank(self, rank: int) -> None:
        self.lbl_rank.setText(f"{rank:02d}")

    def set_stripe_color(self, hex_color: str, enabled: bool) -> None:
        col = hex_color if enabled else "#232833"
        self._stripe.setStyleSheet(f"background-color: {col}; border-radius: 1px;")
        self.lbl_name.setStyleSheet(
            f"color: {'#F2F4F7' if enabled else '#6E7685'}; "
            f"font-size: 13px; font-weight: {'600' if self._selected else '500'};"
        )

    def _apply_row_style(self) -> None:
        if self._selected:
            self.setStyleSheet(
                "QFrame { background-color: #13161D; border: none; "
                "border-left: 2px solid #FF6B1A; border-bottom: 1px solid #15181E; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { background-color: transparent; border: none; "
                "border-left: 2px solid transparent; border-bottom: 1px solid #15181E; }"
                "QFrame:hover { background-color: #0E1015; }"
            )


class EffectsPage(QWidget):
    """Master-Detail Studio: lista ordenável à esquerda e inspetor dedicado à direita."""

    statusMessage = Signal(str)

    def __init__(self, service: SyncService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._priority_ids: list[str] = list(_DEFAULT_PRIORITY_IDS)
        self._group_order: list[str] = [
            "flashbang",
            "shot",
            "fire",
            "c4",
            "health",
            "team_round",
            "weapon",
        ]
        self._selected_group = "flashbang"
        self._weapon_pickers: dict[str, ColorPickerButton] = {}
        self._rows: dict[str, _MasterEffectRow] = {}
        self._inspector_headers: dict[str, tuple[QLabel, ToggleSwitch, EffectSignatureBar]] = {}
        self._inspector_indices: dict[str, int] = {}

        self._build_ui()
        self.load_from_config(self._service.get_config())

    @staticmethod
    def _percent_spin() -> QSpinBox:
        s = QSpinBox()
        s.setRange(0, 100)
        s.setSuffix(" %")
        return s

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
        lbl = QLabel("Efeitos RGB & Prioridades")
        lbl.setObjectName("PageTitle")
        sub = QLabel(
            "Selecione um efeito para ajustar comportamento, cores e prioridade"
        )
        sub.setObjectName("PageSubtitle")
        tcol.addWidget(lbl)
        tcol.addWidget(sub)
        top.addLayout(tcol, 1)

        self.btn_restore_defaults = QPushButton("Restaurar Padrões")
        self.btn_restore_defaults.clicked.connect(self._on_restore_defaults)
        self.btn_save = QPushButton("Aplicar e Salvar")
        self.btn_save.setObjectName("PrimaryAccent")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self._on_save)
        top.addWidget(self.btn_restore_defaults)
        top.addWidget(self.btn_save)
        outer.addWidget(header)
        outer.addWidget(_hline())

        # Split Master-Detail
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Coluna Master (368px)
        master = QFrame()
        master.setObjectName("MasterPane")
        master.setFixedWidth(368)
        m_lay = QVBoxLayout(master)
        m_lay.setContentsMargins(0, 0, 0, 0)
        m_lay.setSpacing(0)

        m_head = QWidget()
        mh_lay = QHBoxLayout(m_head)
        mh_lay.setContentsMargins(16, 10, 16, 10)
        lbl_p = QLabel("ORDEM DE PRIORIDADE (TOPO = MAIOR)")
        lbl_p.setObjectName("Overline")
        lbl_a = QLabel("ATIVO")
        lbl_a.setObjectName("Overline")
        mh_lay.addWidget(lbl_p)
        mh_lay.addStretch(1)
        mh_lay.addWidget(lbl_a)
        m_lay.addWidget(m_head)
        m_lay.addWidget(_hline())

        # Controles toggle por efeito (preservando nomes públicos chk_*)
        self.chk_flash = ToggleSwitch()
        self.chk_shot = ToggleSwitch()
        self.chk_fire = ToggleSwitch()
        self.chk_c4 = ToggleSwitch()
        self.chk_health = ToggleSwitch()
        self.chk_team = ToggleSwitch()
        self.chk_weapons = ToggleSwitch()

        toggle_map = {
            "flashbang": self.chk_flash,
            "shot": self.chk_shot,
            "fire": self.chk_fire,
            "c4": self.chk_c4,
            "health": self.chk_health,
            "team_round": self.chk_team,
            "weapon": self.chk_weapons,
        }

        master_scroll = QScrollArea()
        master_scroll.setWidgetResizable(True)
        master_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        master_scroll.viewport().setStyleSheet("background-color: #0A0C0F;")
        master_list_host = QWidget()
        master_list_host.setStyleSheet("background-color: #0A0C0F;")
        self._master_list_lay = QVBoxLayout(master_list_host)
        self._master_list_lay.setContentsMargins(0, 0, 0, 0)
        self._master_list_lay.setSpacing(0)

        for gid in self._group_order:
            tgl = toggle_map[gid]
            row = _MasterEffectRow(gid, tgl)
            row.clicked.connect(self._select_group)
            tgl.toggled.connect(lambda _chk, g=gid: self._on_master_toggle_changed(g))
            self._rows[gid] = row
            self._master_list_lay.addWidget(row)

        self._master_list_lay.addStretch(1)
        master_scroll.setWidget(master_list_host)
        m_lay.addWidget(master_scroll, 1)

        m_lay.addWidget(_hline())
        m_foot = QWidget()
        mf_lay = QHBoxLayout(m_foot)
        mf_lay.setContentsMargins(16, 10, 16, 10)
        mf_lay.setSpacing(8)
        lbl_reord = QLabel("Prioridade:")
        lbl_reord.setStyleSheet("color: #6E7685; font-size: 12px;")
        btn_up = QPushButton("↑ Subir")
        btn_up.clicked.connect(lambda: self._move_selected(-1))
        btn_down = QPushButton("↓ Descer")
        btn_down.clicked.connect(lambda: self._move_selected(1))
        mf_lay.addWidget(lbl_reord)
        mf_lay.addStretch(1)
        mf_lay.addWidget(btn_up)
        mf_lay.addWidget(btn_down)
        m_lay.addWidget(m_foot)

        body.addWidget(master)

        # Coluna Inspetor à Direita
        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inspector_scroll.viewport().setObjectName("PageCanvas")
        inspector_scroll.viewport().setAutoFillBackground(True)
        self.inspector_stack = QStackedWidget()
        self.inspector_stack.setObjectName("PageCanvas")
        self.inspector_stack.setAutoFillBackground(True)
        inspector_scroll.setWidget(self.inspector_stack)
        body.addWidget(inspector_scroll, 1)

        outer.addLayout(body, 1)

        # Constroi os 7 painéis de inspeção detalhada
        self._build_all_inspectors()
        self._select_group("flashbang")

    def _build_inspector_shell(
        self, group_id: str, master_toggle: ToggleSwitch
    ) -> tuple[QWidget, QVBoxLayout, EffectSignatureBar]:
        page = QWidget()
        page.setObjectName("PageCanvas")
        page.setAutoFillBackground(True)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(30, 24, 32, 24)
        lay.setSpacing(18)

        head_row = QHBoxLayout()
        head_row.setSpacing(16)
        meta_col = QVBoxLayout()
        meta_col.setSpacing(3)
        lbl_prio = QLabel("PRIORIDADE #01")
        lbl_prio.setObjectName("SectionOverline")
        lbl_title = QLabel(_GROUP_META[group_id]["title"])
        lbl_title.setObjectName("HeroTitle")
        lbl_desc = QLabel(_GROUP_META[group_id]["desc"])
        lbl_desc.setObjectName("PageSubtitle")
        meta_col.addWidget(lbl_prio)
        meta_col.addWidget(lbl_title)
        meta_col.addWidget(lbl_desc)
        head_row.addLayout(meta_col, 1)

        detail_toggle = ToggleSwitch()
        detail_toggle.toggled.connect(
            lambda chk, mt=master_toggle: self._sync_toggle_pair(mt, chk)
        )
        master_toggle.toggled.connect(
            lambda chk, dt=detail_toggle: self._sync_toggle_pair(dt, chk)
        )
        head_row.addWidget(detail_toggle, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head_row)

        sig_col = QVBoxLayout()
        sig_col.setSpacing(6)
        lbl_sig = QLabel("ASSINATURA VISUAL DO EFEITO")
        lbl_sig.setObjectName("Overline")
        sig_bar = EffectSignatureBar()
        sig_col.addWidget(lbl_sig)
        sig_col.addWidget(sig_bar)
        lay.addLayout(sig_col)

        lay.addWidget(_hline())

        params_col = QVBoxLayout()
        params_col.setContentsMargins(0, 0, 0, 0)
        params_col.setSpacing(0)
        lay.addLayout(params_col)
        lay.addStretch(1)

        self._inspector_headers[group_id] = (lbl_prio, detail_toggle, sig_bar)
        return page, params_col, sig_bar

    @staticmethod
    def _add_param_row(
        container: QVBoxLayout, label: str, widget: QWidget, with_divider: bool = True
    ) -> None:
        row = QWidget()
        rlay = QHBoxLayout(row)
        rlay.setContentsMargins(0, 11, 0, 11)
        rlay.setSpacing(16)
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #A8B0BE; font-size: 13px;")
        rlay.addWidget(lbl)
        rlay.addStretch(1)
        rlay.addWidget(widget)
        container.addWidget(row)
        if with_divider:
            container.addWidget(_hline())

    def _build_all_inspectors(self) -> None:
        # 1. Flashbang
        page, p_lay, _ = self._build_inspector_shell("flashbang", self.chk_flash)
        self.col_flash = ColorPickerButton("#FFFFFF")
        self.spin_flash_int = self._percent_spin()
        self.spin_flash_tail = QSpinBox()
        self.spin_flash_tail.setRange(50, 1500)
        self.spin_flash_tail.setSuffix(" ms")
        self.spin_flash_bin_fade = QSpinBox()
        self.spin_flash_bin_fade.setRange(100, 2500)
        self.spin_flash_bin_fade.setSuffix(" ms")
        self._add_param_row(p_lay, "Cor do clarão:", self.col_flash)
        self._add_param_row(p_lay, "Intensidade (%):", self.spin_flash_int)
        self._add_param_row(p_lay, "Cauda suave (rampa gradual):", self.spin_flash_tail)
        self._add_param_row(
            p_lay, "Decaimento pós-cegueira (modo binário):", self.spin_flash_bin_fade, False
        )
        self.col_flash.colorChanged.connect(lambda _: self._refresh_visual_indicators())
        self._inspector_indices["flashbang"] = self.inspector_stack.addWidget(page)

        # 2. Disparos
        page, p_lay, _ = self._build_inspector_shell("shot", self.chk_shot)
        self.col_shot = ColorPickerButton("#FF9900")
        self.spin_shot_dur = QSpinBox()
        self.spin_shot_dur.setRange(20, 500)
        self.spin_shot_dur.setSuffix(" ms")
        self.spin_shot_deb = QSpinBox()
        self.spin_shot_deb.setRange(0, 500)
        self.spin_shot_deb.setSuffix(" ms")
        self.spin_shot_int = self._percent_spin()
        self._add_param_row(p_lay, "Cor do pulso:", self.col_shot)
        self._add_param_row(p_lay, "Duração do pulso:", self.spin_shot_dur)
        self._add_param_row(p_lay, "Debounce mínimo:", self.spin_shot_deb)
        self._add_param_row(p_lay, "Intensidade (%):", self.spin_shot_int, False)
        self.col_shot.colorChanged.connect(lambda _: self._refresh_visual_indicators())
        self._inspector_indices["shot"] = self.inspector_stack.addWidget(page)

        # 3. Fogo
        page, p_lay, _ = self._build_inspector_shell("fire", self.chk_fire)
        self.col_fire_1 = ColorPickerButton("#FF2200")
        self.col_fire_2 = ColorPickerButton("#FF9900")
        self.spin_fire_hz = QDoubleSpinBox()
        self.spin_fire_hz.setRange(0.5, 15.0)
        self.spin_fire_hz.setSingleStep(0.5)
        self.spin_fire_hz.setSuffix(" Hz")
        self.spin_fire_int = self._percent_spin()
        self._add_param_row(p_lay, "Cor primária:", self.col_fire_1)
        self._add_param_row(p_lay, "Cor secundária:", self.col_fire_2)
        self._add_param_row(p_lay, "Frequência da oscilação:", self.spin_fire_hz)
        self._add_param_row(p_lay, "Intensidade (%):", self.spin_fire_int, False)
        self.col_fire_1.colorChanged.connect(lambda _: self._refresh_visual_indicators())
        self.col_fire_2.colorChanged.connect(lambda _: self._refresh_visual_indicators())
        self._inspector_indices["fire"] = self.inspector_stack.addWidget(page)

        # 4. C4
        page, p_lay, _ = self._build_inspector_shell("c4", self.chk_c4)
        self.col_c4 = ColorPickerButton("#FF0000")
        self.spin_c4_timer = QDoubleSpinBox()
        self.spin_c4_timer.setRange(10.0, 90.0)
        self.spin_c4_timer.setSuffix(" s")
        self.spin_c4_init_int = QDoubleSpinBox()
        self.spin_c4_init_int.setRange(0.20, 3.0)
        self.spin_c4_init_int.setSingleStep(0.05)
        self.spin_c4_init_int.setSuffix(" s")
        self.spin_c4_min_int = QDoubleSpinBox()
        self.spin_c4_min_int.setRange(0.08, 1.0)
        self.spin_c4_min_int.setSingleStep(0.01)
        self.spin_c4_min_int.setSuffix(" s")
        self.spin_c4_beep_dur = QDoubleSpinBox()
        self.spin_c4_beep_dur.setRange(0.08, 0.8)
        self.spin_c4_beep_dur.setSingleStep(0.02)
        self.spin_c4_beep_dur.setSuffix(" s")
        self.spin_c4_int = self._percent_spin()
        self._add_param_row(p_lay, "Cor da bipada:", self.col_c4)
        self._add_param_row(p_lay, "Tempo estimado da bomba:", self.spin_c4_timer)
        self._add_param_row(p_lay, "Intervalo inicial:", self.spin_c4_init_int)
        self._add_param_row(p_lay, "Intervalo mínimo:", self.spin_c4_min_int)
        self._add_param_row(p_lay, "Duração da bipada:", self.spin_c4_beep_dur)
        self._add_param_row(p_lay, "Intensidade (%):", self.spin_c4_int, False)
        self.col_c4.colorChanged.connect(lambda _: self._refresh_visual_indicators())
        self._inspector_indices["c4"] = self.inspector_stack.addWidget(page)

        # 5. Vida & Vida Crítica
        page, p_lay, _ = self._build_inspector_shell("health", self.chk_health)
        self.spin_hp_crit_thresh = QSpinBox()
        self.spin_hp_crit_thresh.setRange(5, 50)
        self.spin_hp_crit_thresh.setSuffix(" HP")
        self.spin_hp_crit_hz = QDoubleSpinBox()
        self.spin_hp_crit_hz.setRange(0.5, 10.0)
        self.spin_hp_crit_hz.setSingleStep(0.5)
        self.spin_hp_crit_hz.setSuffix(" Hz")
        self.col_hp_100 = ColorPickerButton("#00FF00")
        self.col_hp_75 = ColorPickerButton("#80FF00")
        self.col_hp_50 = ColorPickerButton("#FFFF00")
        self.col_hp_25 = ColorPickerButton("#FF9900")
        self.col_hp_crit = ColorPickerButton("#FF0000")
        self.spin_hp_int = self._percent_spin()
        self._add_param_row(p_lay, "Limiar crítico:", self.spin_hp_crit_thresh)
        self._add_param_row(p_lay, "Frequência do pulso crítico:", self.spin_hp_crit_hz)
        self._add_param_row(p_lay, "Cor em 100 HP:", self.col_hp_100)
        self._add_param_row(p_lay, "Cor em 75 HP:", self.col_hp_75)
        self._add_param_row(p_lay, "Cor em 50 HP:", self.col_hp_50)
        self._add_param_row(p_lay, "Cor em 25 HP:", self.col_hp_25)
        self._add_param_row(p_lay, "Cor em estado crítico:", self.col_hp_crit)
        self._add_param_row(p_lay, "Intensidade (%):", self.spin_hp_int, False)
        for cp in (
            self.col_hp_100,
            self.col_hp_75,
            self.col_hp_50,
            self.col_hp_25,
            self.col_hp_crit,
        ):
            cp.colorChanged.connect(lambda _: self._refresh_visual_indicators())
        self._inspector_indices["health"] = self.inspector_stack.addWidget(page)

        # 6. Freezetime (CT / TR)
        page, p_lay, _ = self._build_inspector_shell("team_round", self.chk_team)
        self.chk_freezetime_pulse = ToggleSwitch()
        self.col_t = ColorPickerButton("#FF9900")
        self.col_ct = ColorPickerButton("#008CFF")
        self.spin_freeze_hz = QDoubleSpinBox()
        self.spin_freeze_hz.setRange(0.2, 5.0)
        self.spin_freeze_hz.setSingleStep(0.1)
        self.spin_freeze_hz.setSuffix(" Hz")
        self.spin_team_int = self._percent_spin()
        self._add_param_row(p_lay, "Cor TR (Freezetime):", self.col_t)
        self._add_param_row(p_lay, "Cor CT (Freezetime):", self.col_ct)
        self._add_param_row(p_lay, "Pulsar suavemente no Freezetime:", self.chk_freezetime_pulse)
        self._add_param_row(p_lay, "Frequência do pulso no Freezetime:", self.spin_freeze_hz)
        self._add_param_row(p_lay, "Intensidade (%):", self.spin_team_int, False)
        self.col_t.colorChanged.connect(lambda _: self._refresh_visual_indicators())
        self.col_ct.colorChanged.connect(lambda _: self._refresh_visual_indicators())
        self._inspector_indices["team_round"] = self.inspector_stack.addWidget(page)

        # 7. Armas
        page, p_lay, _ = self._build_inspector_shell("weapon", self.chk_weapons)
        self.spin_weapons_int = self._percent_spin()
        self._add_param_row(p_lay, "Intensidade (%):", self.spin_weapons_int)
        cat_keys = list(_WEAPON_LABELS.items())
        for idx, (key, label) in enumerate(cat_keys):
            picker = ColorPickerButton("#CCCCCC")
            picker.colorChanged.connect(lambda _: self._refresh_visual_indicators())
            self._weapon_pickers[key] = picker
            self._add_param_row(
                p_lay, f"Categoria · {label}:", picker, with_divider=idx < len(cat_keys) - 1
            )
        self._inspector_indices["weapon"] = self.inspector_stack.addWidget(page)

    @staticmethod
    def _sync_toggle_pair(target: ToggleSwitch, checked: bool) -> None:
        if target.isChecked() != checked:
            target.blockSignals(True)
            target.setChecked(checked)
            target.blockSignals(False)

    def _on_master_toggle_changed(self, group_id: str) -> None:
        self._refresh_visual_indicators()
        self._select_group(group_id)

    def _select_group(self, group_id: str) -> None:
        if group_id not in self._inspector_indices:
            return
        self._selected_group = group_id
        for gid, row in self._rows.items():
            row.set_selected(gid == group_id)
        self.inspector_stack.setCurrentIndex(self._inspector_indices[group_id])
        self._refresh_visual_indicators()

    def _rebuild_master_order(self) -> None:
        seen_groups: list[str] = []
        for eff_id in self._priority_ids:
            gid = "health" if eff_id in ("health_critical", "health") else eff_id
            if gid in self._rows and gid not in seen_groups:
                seen_groups.append(gid)
        for gid in self._rows:
            if gid not in seen_groups:
                seen_groups.append(gid)
        self._group_order = seen_groups

        while self._master_list_lay.count() > 0:
            item = self._master_list_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        for idx, gid in enumerate(self._group_order, start=1):
            row = self._rows[gid]
            row.set_rank(idx)
            self._master_list_lay.addWidget(row)
        self._master_list_lay.addStretch(1)
        self._refresh_visual_indicators()

    def _move_selected(self, delta: int) -> None:
        gid = self._selected_group
        if gid not in self._group_order:
            return
        idx = self._group_order.index(gid)
        new_idx = idx + delta
        if not (0 <= new_idx < len(self._group_order)):
            return

        new_groups = list(self._group_order)
        item = new_groups.pop(idx)
        new_groups.insert(new_idx, item)

        rebuilt_priorities: list[str] = []
        for g in new_groups:
            rebuilt_priorities.extend(_GROUP_META[g]["priority_keys"])
        self._priority_ids = rebuilt_priorities
        self._rebuild_master_order()
        self._select_group(gid)

    def _refresh_visual_indicators(self) -> None:
        color_groups = {
            "flashbang": (self.chk_flash.isChecked(), [self.col_flash.color()]),
            "shot": (self.chk_shot.isChecked(), [self.col_shot.color()]),
            "fire": (
                self.chk_fire.isChecked(),
                [self.col_fire_1.color(), self.col_fire_2.color()],
            ),
            "c4": (self.chk_c4.isChecked(), [self.col_c4.color()]),
            "health": (
                self.chk_health.isChecked(),
                [
                    self.col_hp_100.color(),
                    self.col_hp_75.color(),
                    self.col_hp_50.color(),
                    self.col_hp_25.color(),
                    self.col_hp_crit.color(),
                ],
            ),
            "team_round": (
                self.chk_team.isChecked(),
                [self.col_ct.color(), self.col_t.color()],
            ),
            "weapon": (
                self.chk_weapons.isChecked(),
                [self._weapon_pickers[k].color() for k in _WEAPON_LABELS],
            ),
        }
        for rank, gid in enumerate(self._group_order, start=1):
            enabled, cols = color_groups[gid]
            row = self._rows[gid]
            row.set_rank(rank)
            row.set_stripe_color(cols[0], enabled)
            lbl_prio, detail_toggle, sig_bar = self._inspector_headers[gid]
            lbl_prio.setText(f"PRIORIDADE #{rank:02d}")
            self._sync_toggle_pair(detail_toggle, enabled)
            sig_bar.set_signature(_GROUP_META[gid]["sig_mode"], cols, enabled)

    def load_from_config(self, cfg: dict[str, Any]) -> None:
        eff = cfg.get("effects", {})

        fl = eff.get("flashbang", {})
        self.chk_flash.setChecked(bool(fl.get("enabled", True)))
        self.col_flash.set_color(str(fl.get("color", "#FFFFFF")))
        self.spin_flash_int.setValue(int(fl.get("intensity", 100)))
        self.spin_flash_tail.setValue(int(fl.get("fade_tail_ms", 220)))
        self.spin_flash_bin_fade.setValue(int(fl.get("binary_fade_ms", 650)))

        sh = eff.get("shot", {})
        self.chk_shot.setChecked(bool(sh.get("enabled", True)))
        self.col_shot.set_color(str(sh.get("color", "#FF9900")))
        self.spin_shot_dur.setValue(int(sh.get("duration_ms", 50)))
        self.spin_shot_deb.setValue(int(sh.get("debounce_ms", 40)))
        self.spin_shot_int.setValue(int(sh.get("intensity", 100)))

        fr = eff.get("fire", {})
        self.chk_fire.setChecked(bool(fr.get("enabled", True)))
        self.col_fire_1.set_color(str(fr.get("color_primary", "#FF2200")))
        self.col_fire_2.set_color(str(fr.get("color_secondary", "#FF9900")))
        self.spin_fire_hz.setValue(float(fr.get("oscillation_hz", 4.0)))
        self.spin_fire_int.setValue(int(fr.get("intensity", 100)))

        c4 = eff.get("c4", {})
        self.chk_c4.setChecked(bool(c4.get("enabled", True)))
        self.col_c4.set_color(str(c4.get("color", "#FF0000")))
        self.spin_c4_timer.setValue(float(c4.get("bomb_timer_s", 40.0)))
        self.spin_c4_init_int.setValue(float(c4.get("initial_interval_s", 1.0)))
        self.spin_c4_min_int.setValue(float(c4.get("min_interval_s", 0.15)))
        self.spin_c4_beep_dur.setValue(float(c4.get("beep_duration_s", 0.24)))
        self.spin_c4_int.setValue(int(c4.get("intensity", 100)))

        hp = eff.get("health", {})
        self.chk_health.setChecked(bool(hp.get("enabled", False)))
        self.spin_hp_crit_thresh.setValue(int(hp.get("critical_threshold", 25)))
        self.spin_hp_crit_hz.setValue(float(hp.get("critical_pulse_hz", 2.5)))
        self.col_hp_100.set_color(str(hp.get("color_100", "#00FF00")))
        self.col_hp_75.set_color(str(hp.get("color_75", "#80FF00")))
        self.col_hp_50.set_color(str(hp.get("color_50", "#FFFF00")))
        self.col_hp_25.set_color(str(hp.get("color_25", "#FF9900")))
        self.col_hp_crit.set_color(str(hp.get("color_critical", "#FF0000")))
        self.spin_hp_int.setValue(int(hp.get("intensity", 100)))

        tm = eff.get("team", {})
        self.chk_team.setChecked(bool(tm.get("enabled", False)))
        self.chk_freezetime_pulse.setChecked(bool(tm.get("freezetime_pulse", True)))
        self.col_t.set_color(str(tm.get("t_color", "#FF9900")))
        self.col_ct.set_color(str(tm.get("ct_color", "#008CFF")))
        self.spin_freeze_hz.setValue(float(tm.get("freezetime_pulse_hz", 0.8)))
        self.spin_team_int.setValue(int(tm.get("intensity", 100)))

        wp = eff.get("weapons", {})
        self.chk_weapons.setChecked(bool(wp.get("enabled", False)))
        self.spin_weapons_int.setValue(int(wp.get("intensity", 100)))
        cats = wp.get("categories", {})
        for key, picker in self._weapon_pickers.items():
            picker.set_color(str(cats.get(key, "#CCCCCC")))

        loaded_prio = [
            str(x) for x in cfg.get("priorities", _DEFAULT_PRIORITY_IDS) if x in _DEFAULT_PRIORITY_IDS
        ]
        for pid in _DEFAULT_PRIORITY_IDS:
            if pid not in loaded_prio:
                loaded_prio.append(pid)
        self._priority_ids = loaded_prio
        self._rebuild_master_order()
        self._select_group(self._selected_group)

    def collect_config(self, base_cfg: dict[str, Any]) -> dict[str, Any]:
        cfg = copy.deepcopy(base_cfg)
        eff = cfg.setdefault("effects", {})
        eff["flashbang"] = {
            "enabled": self.chk_flash.isChecked(),
            "color": self.col_flash.color(),
            "fade_tail_ms": self.spin_flash_tail.value(),
            "binary_fade_ms": self.spin_flash_bin_fade.value(),
            "intensity": self.spin_flash_int.value(),
        }
        eff.pop("he_explosion", None)
        eff["shot"] = {
            "enabled": self.chk_shot.isChecked(),
            "color": self.col_shot.color(),
            "duration_ms": self.spin_shot_dur.value(),
            "debounce_ms": self.spin_shot_deb.value(),
            "intensity": self.spin_shot_int.value(),
        }
        eff["c4"] = {
            "enabled": self.chk_c4.isChecked(),
            "color": self.col_c4.color(),
            "bomb_timer_s": round(self.spin_c4_timer.value(), 2),
            "initial_interval_s": round(self.spin_c4_init_int.value(), 2),
            "min_interval_s": round(self.spin_c4_min_int.value(), 2),
            "beep_duration_s": round(self.spin_c4_beep_dur.value(), 2),
            "intensity": self.spin_c4_int.value(),
        }
        eff["fire"] = {
            "enabled": self.chk_fire.isChecked(),
            "color_primary": self.col_fire_1.color(),
            "color_secondary": self.col_fire_2.color(),
            "oscillation_hz": round(self.spin_fire_hz.value(), 2),
            "intensity": self.spin_fire_int.value(),
        }
        eff["health"] = {
            "enabled": self.chk_health.isChecked(),
            "critical_threshold": self.spin_hp_crit_thresh.value(),
            "critical_pulse_hz": round(self.spin_hp_crit_hz.value(), 2),
            "color_100": self.col_hp_100.color(),
            "color_75": self.col_hp_75.color(),
            "color_50": self.col_hp_50.color(),
            "color_25": self.col_hp_25.color(),
            "color_critical": self.col_hp_crit.color(),
            "intensity": self.spin_hp_int.value(),
        }
        eff["team"] = {
            "enabled": self.chk_team.isChecked(),
            "t_color": self.col_t.color(),
            "ct_color": self.col_ct.color(),
            "freezetime_pulse": self.chk_freezetime_pulse.isChecked(),
            "freezetime_pulse_hz": round(self.spin_freeze_hz.value(), 2),
            "intensity": self.spin_team_int.value(),
        }
        eff["weapons"] = {
            "enabled": self.chk_weapons.isChecked(),
            "intensity": self.spin_weapons_int.value(),
            "categories": {
                key: picker.color() for key, picker in self._weapon_pickers.items()
            },
        }
        cfg["priorities"] = list(self._priority_ids)
        return cfg

    def _on_save(self) -> None:
        updated = self.collect_config(self._service.get_config())
        ok, msg = self._service.apply_config(updated)
        self.statusMessage.emit(msg)
        if not ok:
            QMessageBox.warning(self, "Erro de Configuração", msg)

    def _on_restore_defaults(self) -> None:
        reply = QMessageBox.question(
            self,
            "Restaurar Padrões",
            "Deseja restaurar as cores, durações, velocidades e prioridades padrão?",
        )
        if reply == QMessageBox.StandardButton.Yes:
            restored = self._service.restore_default_settings()
            self.load_from_config(restored)
            self.statusMessage.emit("Configurações padrão restauradas.")
