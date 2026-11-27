"""
Efeitos RGB e resolução de prioridades para o CS2 RGB Sync.

Cada efeito recebe o estado consolidado do jogo (`GameStateSnapshot`),
temporizadores do motor e configurações do usuário, retornando uma cor alvo
ou `None` quando não estiver ativo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.gsi_parser import GameStateSnapshot

DEFAULT_PRIORITY_ORDER: tuple[str, ...] = (
    "flashbang",
    "shot",
    "fire",
    "c4",
    "health_critical",
    "health",
    "team_round",
    "weapon",
)


@dataclass(frozen=True)
class RGBColor:
    """Representa uma cor RGB de 8 bits por canal (0..255)."""

    r: int
    g: int
    b: int

    def clamped(self) -> RGBColor:
        return RGBColor(
            max(0, min(255, int(self.r))),
            max(0, min(255, int(self.g))),
            max(0, min(255, int(self.b))),
        )

    def scale(self, factor: float) -> RGBColor:
        f = max(0.0, min(1.0, float(factor)))
        return RGBColor(
            round(self.r * f),
            round(self.g * f),
            round(self.b * f),
        ).clamped()

    def to_hex(self) -> str:
        c = self.clamped()
        return f"#{c.r:02X}{c.g:02X}{c.b:02X}"

    def to_tuple(self) -> tuple[int, int, int]:
        c = self.clamped()
        return (c.r, c.g, c.b)

    @classmethod
    def from_hex(
        cls, hex_str: str, fallback: tuple[int, int, int] = (255, 255, 255)
    ) -> RGBColor:
        if not isinstance(hex_str, str):
            return cls(*fallback)
        clean = hex_str.strip().lstrip("#")
        if len(clean) != 6:
            return cls(*fallback)
        try:
            return cls(
                int(clean[0:2], 16),
                int(clean[2:4], 16),
                int(clean[4:6], 16),
            )
        except ValueError:
            return cls(*fallback)


def lerp_color(start: RGBColor, end: RGBColor, t: float) -> RGBColor:
    """Interpola linearmente entre duas cores (`t` em 0.0..1.0)."""
    alpha = max(0.0, min(1.0, float(t)))
    return RGBColor(
        round(start.r + (end.r - start.r) * alpha),
        round(start.g + (end.g - start.g) * alpha),
        round(start.b + (end.b - start.b) * alpha),
    ).clamped()


def _intensity_factor(effect_cfg: dict[str, Any]) -> float:
    val = effect_cfg.get("intensity", 100)
    try:
        return max(0.0, min(100.0, float(val))) / 100.0
    except (TypeError, ValueError):
        return 1.0


@dataclass(frozen=True)
class EffectInput:
    """Contexto completo avaliado a cada frame pelo motor RGB."""

    snapshot: GameStateSnapshot
    now_ns: int
    shot_active_until_ns: int
    bomb_planted_at_ns: Optional[int]
    config: dict[str, Any]
    flash_effective_level: float = 0.0
    flash_rising: bool = False


@dataclass(frozen=True)
class EffectResult:
    """Resultado de cor produzido pelo efeito vencedor."""

    effect_id: str
    label: str
    color: RGBColor
    instant: bool = False


def evaluate_flashbang(ctx: EffectInput) -> Optional[EffectResult]:
    cfg = ctx.config.get("effects", {}).get("flashbang", {})
    if not cfg.get("enabled", True):
        return None
    if not ctx.snapshot.is_local_player:
        return None

    raw_active = ctx.snapshot.flashed is not None and ctx.snapshot.flashed > 0
    raw_level = max(0, min(255, ctx.snapshot.flashed)) / 255.0 if raw_active else 0.0
    level = max(ctx.flash_effective_level, raw_level)
    if not raw_active and level <= 0.002:
        return None

    # Curva perceptível para que cegueiras parciais fiquem nítidas no LED branco
    perceptual = level ** 0.75
    intensity_factor = _intensity_factor(cfg)
    base = RGBColor.from_hex(cfg.get("color", "#FFFFFF"), (255, 255, 255))
    color = base.scale(perceptual * intensity_factor)
    if (
        raw_active
        and intensity_factor > 0.0
        and color.to_tuple() == (0, 0, 0)
        and base.to_tuple() != (0, 0, 0)
    ):
        color = base.scale(max(0.02, perceptual) * intensity_factor)
    display_val = max(1, round(level * 255)) if raw_active else round(level * 255)
    return EffectResult(
        effect_id="flashbang",
        label=f"Flashbang ({display_val}/255)",
        color=color,
        instant=True,
    )


def evaluate_shot(ctx: EffectInput) -> Optional[EffectResult]:
    cfg = ctx.config.get("effects", {}).get("shot", {})
    if not cfg.get("enabled", True):
        return None
    if ctx.now_ns >= ctx.shot_active_until_ns:
        return None

    base = RGBColor.from_hex(cfg.get("color", "#FF9900"), (255, 153, 0))
    return EffectResult(
        effect_id="shot",
        label="Disparo",
        color=base.scale(_intensity_factor(cfg)),
        instant=True,
    )


def compute_c4_beep_intensity(
    elapsed_s: float,
    *,
    bomb_timer_s: float = 40.0,
    initial_interval_s: float = 1.0,
    min_interval_s: float = 0.15,
    beep_duration_s: float = 0.24,
) -> float:
    """
    Calcula a intensidade (0.0..1.0) do pulso da C4 imitando o ritmo das bipadas.

    Modelo aproximado calibrado ao comportamento real do CS2 (intervalo inicial ~1.0s
    reduzindo proporcionalmente ao tempo restante até o piso de 0.15s).
    Entre as bipadas o retorno é rigorosamente 0.0 (LED apagado).
    """
    t = max(0.0, float(elapsed_s))
    timer_s = max(5.0, float(bomb_timer_s))
    init_int = max(0.20, float(initial_interval_s))
    min_int = max(0.08, min(init_int, float(min_interval_s)))
    beep_dur = max(0.06, float(beep_duration_s))

    beep_time = 0.0
    # Limite de segurança para tempos muito elevados após o timer estimado
    for _ in range(1000):
        remaining_frac = max(0.0, 1.0 - (beep_time / timer_s))
        interval = max(min_int, min_int + (init_int - min_int) * remaining_frac)
        next_beep = beep_time + interval

        if t < next_beep:
            local_t = t - beep_time
            pulse_dur = min(beep_dur, interval * 0.72)
            if local_t >= pulse_dur:
                return 0.0
            u = local_t / pulse_dur
            if u < 0.35:
                return 0.5 * (1.0 - math.cos(math.pi * (u / 0.35)))
            return 0.5 * (1.0 + math.cos(math.pi * ((u - 0.35) / 0.65)))

        beep_time = next_beep
    return 0.0


def evaluate_c4(ctx: EffectInput) -> Optional[EffectResult]:
    cfg = ctx.config.get("effects", {}).get("c4", {})
    if not cfg.get("enabled", True):
        return None
    if ctx.snapshot.bomb_state != "planted":
        return None

    base = RGBColor.from_hex(cfg.get("color", "#FF0000"), (255, 0, 0))
    timer_s = max(5.0, float(cfg.get("bomb_timer_s", 40.0)))
    init_int = float(cfg.get("initial_interval_s", 1.0))
    min_int = float(cfg.get("min_interval_s", 0.15))
    beep_dur = float(cfg.get("beep_duration_s", 0.24))

    planted_ns = ctx.bomb_planted_at_ns or ctx.now_ns
    elapsed_s = max(0.0, (ctx.now_ns - planted_ns) / 1_000_000_000.0)

    beep_level = compute_c4_beep_intensity(
        elapsed_s,
        bomb_timer_s=timer_s,
        initial_interval_s=init_int,
        min_interval_s=min_int,
        beep_duration_s=beep_dur,
    )
    brightness = beep_level * _intensity_factor(cfg)
    progress = min(1.0, elapsed_s / timer_s)
    return EffectResult(
        effect_id="c4",
        label=f"C4 Plantada ({progress * 100:.0f}%)",
        color=base.scale(brightness),
        instant=True,
    )


def evaluate_fire(ctx: EffectInput) -> Optional[EffectResult]:
    cfg = ctx.config.get("effects", {}).get("fire", {})
    if not cfg.get("enabled", True):
        return None
    if not ctx.snapshot.burning_field_seen:
        return None
    burning = ctx.snapshot.burning
    if burning is None or burning <= 0:
        return None

    c1 = RGBColor.from_hex(cfg.get("color_primary", "#FF2200"), (255, 34, 0))
    c2 = RGBColor.from_hex(cfg.get("color_secondary", "#FF9900"), (255, 153, 0))
    hz = max(0.5, float(cfg.get("oscillation_hz", 4.0)))
    t_s = ctx.now_ns / 1_000_000_000.0
    blend = 0.5 * (1.0 + math.sin(2.0 * math.pi * hz * t_s))
    mixed = lerp_color(c1, c2, blend)
    return EffectResult(
        effect_id="fire",
        label=f"Dano de Fogo ({burning})",
        color=mixed.scale(_intensity_factor(cfg)),
        instant=False,
    )


def evaluate_health_critical(ctx: EffectInput) -> Optional[EffectResult]:
    cfg = ctx.config.get("effects", {}).get("health", {})
    if not cfg.get("enabled", False):
        return None
    hp = ctx.snapshot.health
    threshold = int(cfg.get("critical_threshold", 25))
    if hp is None or hp <= 0 or hp >= threshold:
        return None

    crit_color = RGBColor.from_hex(cfg.get("color_critical", "#FF0000"), (255, 0, 0))
    hz = max(0.5, float(cfg.get("critical_pulse_hz", 2.5)))
    t_s = ctx.now_ns / 1_000_000_000.0
    pulse = 0.25 + 0.75 * (0.5 * (1.0 + math.sin(2.0 * math.pi * hz * t_s)))
    return EffectResult(
        effect_id="health_critical",
        label=f"Vida Crítica ({hp} HP)",
        color=crit_color.scale(pulse * _intensity_factor(cfg)),
        instant=False,
    )


def evaluate_health(ctx: EffectInput) -> Optional[EffectResult]:
    cfg = ctx.config.get("effects", {}).get("health", {})
    if not cfg.get("enabled", False):
        return None
    # No freezetime, cede prioridade para as cores de equipe somente se o efeito Freezetime estiver ativo
    team_cfg = ctx.config.get("effects", {}).get("team", {})
    if (
        ctx.snapshot.is_freezetime
        and team_cfg.get("enabled", False)
        and (ctx.snapshot.team or "").upper() in ("T", "CT")
    ):
        return None
    hp = ctx.snapshot.health
    threshold = int(cfg.get("critical_threshold", 25))
    if hp is None or hp < threshold:
        return None

    c100 = RGBColor.from_hex(cfg.get("color_100", "#00FF00"), (0, 255, 0))
    c75 = RGBColor.from_hex(cfg.get("color_75", "#80FF00"), (128, 255, 0))
    c50 = RGBColor.from_hex(cfg.get("color_50", "#FFFF00"), (255, 255, 0))
    c25 = RGBColor.from_hex(cfg.get("color_25", "#FF9900"), (255, 153, 0))

    clamped_hp = max(25, min(100, hp))
    if clamped_hp >= 75:
        color = lerp_color(c75, c100, (clamped_hp - 75) / 25.0)
    elif clamped_hp >= 50:
        color = lerp_color(c50, c75, (clamped_hp - 50) / 25.0)
    else:
        color = lerp_color(c25, c50, (clamped_hp - 25) / 25.0)

    return EffectResult(
        effect_id="health",
        label=f"Vida ({hp} HP)",
        color=color.scale(_intensity_factor(cfg)),
        instant=False,
    )


def evaluate_team_round(ctx: EffectInput) -> Optional[EffectResult]:
    cfg = ctx.config.get("effects", {}).get("team", {})
    if not cfg.get("enabled", False):
        return None
    if not ctx.snapshot.is_freezetime:
        return None

    team = (ctx.snapshot.team or "").upper()
    if team == "T":
        base = RGBColor.from_hex(cfg.get("t_color", "#FF9900"), (255, 153, 0))
        team_label = "TR"
    elif team == "CT":
        base = RGBColor.from_hex(cfg.get("ct_color", "#008CFF"), (0, 140, 255))
        team_label = "CT"
    else:
        return None

    intensity = _intensity_factor(cfg)
    if cfg.get("freezetime_pulse", True):
        hz = max(0.2, float(cfg.get("freezetime_pulse_hz", 0.8)))
        t_s = ctx.now_ns / 1_000_000_000.0
        pulse = 0.35 + 0.65 * (0.5 * (1.0 + math.sin(2.0 * math.pi * hz * t_s)))
        return EffectResult(
            effect_id="team_round",
            label=f"Freezetime ({team_label})",
            color=base.scale(pulse * intensity),
            instant=True,
        )

    return EffectResult(
        effect_id="team_round",
        label=f"Freezetime ({team_label})",
        color=base.scale(intensity),
        instant=False,
    )


def evaluate_weapon(ctx: EffectInput) -> Optional[EffectResult]:
    cfg = ctx.config.get("effects", {}).get("weapons", {})
    if not cfg.get("enabled", False):
        return None
    weapon = ctx.snapshot.active_weapon
    if weapon is None:
        return None

    categories = cfg.get("categories", {})
    hex_color = categories.get(weapon.category)
    if not hex_color:
        return None

    base = RGBColor.from_hex(hex_color, (200, 200, 200))
    return EffectResult(
        effect_id="weapon",
        label=f"Arma ({weapon.category}: {weapon.name})",
        color=base.scale(_intensity_factor(cfg)),
        instant=False,
    )


_EFFECT_EVALUATORS: dict[str, Callable[[EffectInput], Optional[EffectResult]]] = {
    "flashbang": evaluate_flashbang,
    "shot": evaluate_shot,
    "fire": evaluate_fire,
    "c4": evaluate_c4,
    "health_critical": evaluate_health_critical,
    "health": evaluate_health,
    "team_round": evaluate_team_round,
    "weapon": evaluate_weapon,
}


def resolve_active_effect(ctx: EffectInput) -> Optional[EffectResult]:
    """Avalia os efeitos em ordem de prioridade e retorna o primeiro efeito ativo."""
    if not ctx.snapshot.connected or ctx.snapshot.player_activity == "menu":
        return None

    configured_order = ctx.config.get("priorities")
    if isinstance(configured_order, list) and configured_order:
        order = [str(item) for item in configured_order if item in _EFFECT_EVALUATORS]
        for default_id in DEFAULT_PRIORITY_ORDER:
            if default_id not in order:
                order.append(default_id)
    else:
        order = list(DEFAULT_PRIORITY_ORDER)

    for effect_id in order:
        evaluator = _EFFECT_EVALUATORS.get(effect_id)
        if evaluator is None:
            continue
        result = evaluator(ctx)
        if result is not None:
            return result
    return None
