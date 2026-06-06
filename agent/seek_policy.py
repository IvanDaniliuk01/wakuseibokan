"""Política SeekAndDestroy con escape de atasco, variación por episodio y evasivo.

Pensada para generar dataset diverso para offline RL:
- ENGAGE: comportamiento base — persigue y dispara cuando target < dist_fire.
- ESCAPE: si la posición no cambia > stuck_threshold_m por stuck_max_ticks,
         marcha atrás + giro fuerte por escape_duration_ticks.
- EVASIVO: si perdió > evasive_dmg_threshold de health en evasive_window_ticks,
          retrocede + gira abruptamente por evasive_duration_ticks.
- NOISE: en cada tick con probabilidad noise_prob, acción uniforme random.

`sample_episode_params(rng)` samplea distinto dist_fire, dist_engage, thrust_max y
noise_prob para cada episodio → distribución de comportamientos en el dataset.
"""
import math
import numpy as np
from dataclasses import dataclass, field
from collections import deque
from typing import Optional, Tuple

from .policy_utils import azimuth_deg as _azimuth_deg
from .policy_utils import relative_bearing_deg as _relative_bearing


@dataclass
class PolicyParams:
    dist_fire: float = 200.0
    dist_engage: float = 1700.0
    thrust_max: float = 10.0
    noise_prob: float = 0.0
    evasive_dmg_threshold: float = 5.0
    evasive_window_ticks: int = 40
    evasive_duration_ticks: int = 60
    stuck_threshold_m: float = 0.05
    stuck_max_ticks: int = 60
    escape_duration_ticks: int = 50


def sample_episode_params(rng, base_noise_prob: float = 0.0) -> PolicyParams:
    """Samplea params al inicio de cada episodio para diversidad.

    NOTA: noise_prob default es 0.0. El noise por tick (acción totalmente
    random) rompe visualmente las rotaciones del Otter y no aporta valor
    real al dataset — la diversidad ya está cubierta por la variación de
    params entre episodios + los distintos niveles de oponente.
    """
    return PolicyParams(
        dist_fire=float(rng.uniform(400, 700)),
        dist_engage=float(rng.uniform(1500, 1900)),
        thrust_max=float(rng.uniform(35, 50)),  # rango estable (sin LCP errors)
        noise_prob=base_noise_prob,
        evasive_dmg_threshold=float(rng.uniform(3, 8)),
    )


@dataclass
class PolicyState:
    last_pos: Optional[Tuple[float, float]] = None
    stuck_count: int = 0
    escape_left: int = 0
    escape_dir: float = 1.0
    evasive_left: int = 0
    evasive_dir: float = 1.0
    health_history: deque = field(default_factory=lambda: deque(maxlen=120))


def init_state() -> PolicyState:
    return PolicyState()


def _aim(my_x, my_z, my_az_deg, ox, oz):
    """Bearing al objetivo sin normalizar (mantenido por compatibilidad con la
    lógica original de seek_policy que asume valores no normalizados)."""
    return _azimuth_deg(my_x, my_z, ox, oz) - my_az_deg


def decide(my_pos, my_az_deg, my_health, other_pos,
           params: PolicyParams, state: PolicyState, rng):
    """Devuelve (thrust, steering, turret_decl, turret_bearing, fire, mode_tag)."""
    my_x, my_z = float(my_pos[0]), float(my_pos[2])
    ox, oz = float(other_pos[0]), float(other_pos[2])

    state.health_history.append(float(my_health))

    polar_d = math.sqrt(my_x ** 2 + my_z ** 2)
    target_d = math.sqrt((ox - my_x) ** 2 + (oz - my_z) ** 2)
    bearing = _aim(my_x, my_z, my_az_deg, ox, oz)

    # 1) NOISE override (uniforme).
    # IMPORTANTE: noise NUNCA dispara — el propósito del noise es agregar
    # diversidad de MOVIMIENTO al dataset, no enseñar a la red a disparar al
    # aire. Sin esta restricción se ensucia mucho el dataset con disparos
    # desperdiciados.
    if rng.uniform() < params.noise_prob:
        return (
            float(rng.uniform(-10, 10)),
            float(rng.uniform(-1, 1)),
            float(rng.uniform(-0.4, 0.4)),
            float(rng.uniform(-180, 180)),
            False,
            "noise",
        )

    # 2) Detectar daño rápido → activar EVASIVO
    if state.evasive_left == 0 and len(state.health_history) > params.evasive_window_ticks:
        h_old = state.health_history[-params.evasive_window_ticks]
        if (h_old - my_health) > params.evasive_dmg_threshold:
            state.evasive_left = params.evasive_duration_ticks
            state.evasive_dir = float(rng.choice([-1.0, 1.0]))

    # 3) Detectar atasco → activar ESCAPE
    if state.last_pos is not None and state.escape_left == 0:
        delta = math.sqrt((my_x - state.last_pos[0]) ** 2 + (my_z - state.last_pos[1]) ** 2)
        if delta < params.stuck_threshold_m:
            state.stuck_count += 1
            if state.stuck_count > params.stuck_max_ticks:
                state.escape_left = params.escape_duration_ticks
                state.escape_dir = float(rng.choice([-1.0, 1.0]))
                state.stuck_count = 0
        else:
            state.stuck_count = 0
    state.last_pos = (my_x, my_z)

    # 4) Modo ESCAPE: marcha atrás + giro
    if state.escape_left > 0:
        state.escape_left -= 1
        return (
            -params.thrust_max,
            state.escape_dir,
            float(rng.uniform(-0.4, 0.4)),
            float(bearing),
            False,
            "escape",
        )

    # 5) Modo EVASIVO: retroceder y romper línea de fuego
    if state.evasive_left > 0:
        state.evasive_left -= 1
        return (
            -params.thrust_max * 0.7,
            state.evasive_dir,
            float(rng.uniform(-0.4, 0.4)),
            float(bearing),
            False,
            "evasive",
        )

    # 6) Modo ENGAGE (SeekAndDestroy con params del episodio)
    thrust = 0.0
    steering = 0.0
    if polar_d < params.dist_engage:
        thrust = params.thrust_max
    if bearing > 0.0:
        steering = 1.0
        thrust = params.thrust_max
    elif bearing < 0.0:
        steering = -1.0
        thrust = params.thrust_max
    if polar_d >= params.dist_engage:
        thrust = 0.0
        steering = 0.0

    # Fire: requiere distancia Y bearing razonable (cono amplio ±45°).
    # Sin el cono, seek dispara a la espalda cuando el enemigo entra en rango
    # por detrás → ensucia el dataset con disparos sin valor.
    fire = False
    if target_d < params.dist_fire and abs(bearing) < 45.0:
        fire = True
        thrust = 0.0

    return float(thrust), float(steering), float(rng.uniform(-0.4, 0.4)), float(bearing), fire, "engage"
