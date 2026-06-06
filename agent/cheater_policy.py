"""Tanque cheater con información privilegiada de ambos vehículos.

A diferencia de seek_policy, este controlador asume acceso completo a la
telemetría del enemigo (pos, health, velocidad estimada). La idea es entrenar
a nuestro agente contra este oponente "tramposo" — si aprende a ganarle a
alguien que sabe todo, va a ganar fácil contra oponentes honestos (privileged
learning / asymmetric self-play).

4 niveles de dificultad con presets calibrados:
- EASY:       baseline torpe (mucho noise de aim, reacción lenta, sin lead)
- MEDIUM:     responde con delay corto, lead aim suave
- HARD:       reacción casi instantánea, lead aim moderado, dispara preciso
- IMPOSSIBLE: aim perfecto, lead aim agresivo, sin ruido

Calibración esperada (win-rate de seek_policy contra cada nivel):
    EASY ~70%, MEDIUM ~40%, HARD ~15%, IMPOSSIBLE ~3%
"""
import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

import numpy as np

from .policy_utils import (
    azimuth_deg, relative_bearing_deg, pitch_to_target_rad,
    artillery_aim, estimate_velocity_from_history, estimate_vy_from_history,
    should_use_high_arc,
)


class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    IMPOSSIBLE = "impossible"
    PREDATOR = "predator"     # HARD-aim + bait + fire-on-the-move
    PREDATOR_V2 = "predator_v2"  # PREDATOR + chaotic_evasion (movimientos random + fire bajo evade)


@dataclass
class CheaterParams:
    aim_noise_deg: float            # ruido gaussiano al apuntar
    reaction_delay_ticks: int       # delay en ticks antes de reaccionar a movimiento del enemigo
    prediction_horizon_ticks: int   # ticks a proyectar adelante (lead aim)
    fire_cone_deg: float            # |bearing| < esto para disparar
    evasion_health_threshold: float # cuánto health perdido en ventana corta para evadir
    evasion_window_ticks: int       # tamaño de la ventana de detección de daño
    evasion_duration_ticks: int     # cuántos ticks dura el modo evasivo
    thrust_max: float
    dist_engage: float              # más allá de esto deja de avanzar
    dist_fire: float                # adentro de esto entra en cono de fuego
    noise_prob: float               # fracción de ticks con acción aleatoria (fallas humanas)
    use_vertical_aim: bool = False  # True → calcula pitch correcto al enemigo;
                                    # False → pitch random (torpeza humana).
                                    # Ver agent/docs/01-altura-y-pitch.md

    # Heurísticas anti-scripted (level PREDATOR). Defaults desactivan todo.
    # Ver agent/docs/04-predator.md
    standoff_ratio: float = 0.0           # 0 = off. Si > 0: mantener distancia
                                          # standoff_ratio × dist_fire del enemigo
    feint_interval_ticks: int = 0         # 0 = off. Cada N ticks invierte steering
    feint_intensity: float = 0.0          # 0-1, cuán fuerte el feint
    strafe_when_aiming: bool = False      # cuando apunto, agregar componente lateral
    bait_when_chased: bool = False        # si el enemigo se acerca rápido, retroceder
    bait_approach_threshold: float = 50.0 # m/s de cambio de dist que cuenta como "se acerca"

    # Lead aim adaptativo (mejora 1): calcula prediction_horizon_ticks
    # dinámicamente en función de la distancia al enemigo. Si False, usa el
    # valor fijo de prediction_horizon_ticks.
    adaptive_lead_aim: bool = False
    projectile_speed_m_per_tick: float = 1.5  # ~75 m/s a 50Hz (calibrar empírico)
    max_lead_ticks: int = 60              # cap superior para evitar predicciones erráticas

    # Evasión caótica (anti-lead-aim del oponente): cuando recibe daño, en
    # vez de retroceder predeciblemente, hace movimientos random + sigue
    # disparando (fire-on-the-move evasive).
    chaotic_evasion: bool = False
    chaos_resample_every: int = 8     # cambiar dirección random cada N ticks

    # Modo artillería: lead aim balístico + compensación de gravedad.
    # Permite disparar desde mucho más lejos (1500-3000m) con buena precisión.
    # Si está activo, OVERRIDE el aim_x/aim_z del _delayed_and_predicted_pos
    # con el cálculo balístico completo.
    artillery_mode: bool = False

    # FIX #1: cooldown real del cañón = setTtl(100) en AdvancedWalrus.cpp:660
    # = 100 sim ticks × dWorldStep(0.05) = 2.0s. CAMBIO post-examen: bajado a 1
    # para mandar fire=True en CADA TICK que estemos alineados. El sim filtra
    # por su cooldown interno; así no perdemos ningún disparo disponible
    # (antes, si esperábamos exactamente 100 ticks y el aim no estaba listo
    # en ese tick puntual, perdíamos el disparo hasta el próximo 200).
    fire_cooldown_ticks: int = 1

    # FIX #2: si el bearing al enemigo cambió mucho en los últimos N ticks,
    # no disparar — el proyectil va a fallar porque el enemigo está girando.
    # CALIBRACIÓN (jun 2026, post-examen): el lead aim balístico YA compensa
    # el movimiento del enemigo. Suprimir por bearing_rate descartaba tiros
    # válidos. Subido a 45° = efectivamente off (sólo bloquea tiros con
    # enemigo en TP/teleport, casos imposibles del sim).
    bearing_rate_suppress_deg: float = 45.0
    bearing_rate_window: int = 5

    # FIX #4: lookback corto en estimate_velocity_from_history → más reactivo
    # a cambios de rumbo del enemigo.
    velocity_lookback: int = 3

    # Body jiggle durante engage: oscila el cuerpo de forma random mientras
    # está en rango de fuego. La torreta apunta independientemente (precesion
    # es relativa al cuerpo, pero se compensa cada tick), así que el cuerpo
    # zigzaguea sin afectar el aim. Esto:
    #   1. Hace al predator más impredecible (oponente le pega menos)
    #   2. Genera dataset BC más diverso (más rotaciones)
    # Distinto al chaotic_evasion (que solo se activa post-daño).
    engage_jiggle_enabled: bool = False
    engage_jiggle_every: int = 15       # ticks entre re-samples (15 = 0.3s)
    engage_jiggle_strength: float = 0.5  # magnitud del jiggle steering, sumado al normal
    engage_jiggle_range: float = 1.5     # activa hasta dist_fire × esto (cobertura más amplia que el cono de fire)

    # Swerve burst post-fire: cuando el predator dispara, durante los próximos
    # N ticks aplica steering fuerte aleatorio (±1) para esquivar el contra-tiro
    # reactivo del enemigo (ese contra-tiro va a llegar ~1s después al punto
    # donde el predator estaba al disparar — si se desplaza lateral, falla).
    # La torreta sigue apuntando al enemigo (precesion independiente).
    swerve_burst_enabled: bool = False
    swerve_burst_duration_ticks: int = 30    # duración total ~0.6s a 50Hz
    swerve_resample_every: int = 10          # re-sample dirección cada 0.2s
                                             # → 3 cambios random en 0.6s
                                             # → patrón impredecible para el enemigo
    swerve_burst_thrust_factor: float = 0.7  # baja un poco thrust para giro más cerrado

    # === STUCK DETECTOR + ESCAPE ===
    # Si pedimos avanzar (thrust > umbral) pero la posición XZ casi no cambió
    # en N ticks, probablemente estamos chocando contra algo (edificio, caja).
    # Solución: rotar fuerte hasta cambiar 90° el heading, después avanzar
    # 4s en línea recta para zafarse.
    stuck_detection_enabled: bool = False
    stuck_window_ticks: int = 30             # ventana de detección (0.6s)
    stuck_threshold_m: float = 1.5           # < 1.5m de desplazamiento = stuck
    stuck_thrust_min: float = 20.0           # sólo detectar si pedimos thrust > esto
    escape_rotation_target_deg: float = 90.0 # girar 90° antes de avanzar
    escape_advance_ticks: int = 200          # 4s avanzando recto
    escape_max_rotation_ticks: int = 80      # fallback: cortar la rotación tras 1.6s

    # === OPTIMIZACIÓN DE AIM (CADENCIA MÁXIMA, jun 2026 post-examen) ===
    # 1) Cono ampliado: 2°→5°. El sim tiene dispersión natural del proyectil
    #    aún con aim perfecto; 5° captura más oportunidades sin afectar hits.
    fire_cone_strict_deg: float = 5.0
    # 2) No disparar si steering alto: completamente OFF (10.0 ≫ rangos reales).
    no_fire_if_steering_above: float = 10.0
    # 3) Sweet spot DESACTIVADO: si está dentro de dist_fire (=2000), dispara.
    #    El sim cuenta con dispersión natural; reservar cooldown sólo perdía
    #    oportunidades. Mejor "always fire when aligned".
    dist_fire_effective: float = 3000.0

    # === WATER GUARD (anti-caída al agua) ===
    # PREVENTIVO: detectamos el borde del mapa por distancia al centro (polar_d).
    # Los Otters spawnean en [-1400, 1400] (ver testcase_131.cpp:97-98). El
    # polar_warn subido a 1500 — antes (1200) cortaba TODO el combate cuando
    # los tanques estaban en spawns alejados del centro (caso muy común).
    # IMPORTANTE: en este modo el cheater SÍ DISPARA mientras vuelve al centro
    # (el water_guard sólo override thrust/steering, no fire).
    water_guard_enabled: bool = False
    water_polar_warn: float = 1500.0  # más allá de esto: empezar a volver
    water_polar_danger: float = 1700.0 # más allá: emergencia, ignorar TODO
    water_y_danger: float = 8.0       # fallback: Y absoluto en agua
    water_y_warn: float = 15.0        # fallback: zona baja
    water_falling_vy: float = -2.0    # m/s descendente que cuenta como "cayendo"
    water_recovery_ticks: int = 60    # mantener modo recovery N ticks tras detectar


_PRESETS = {
    DifficultyLevel.EASY: CheaterParams(
        aim_noise_deg=15.0,            # torpe APUNTANDO (gaussiano suave)
        reaction_delay_ticks=20,
        prediction_horizon_ticks=0,
        fire_cone_deg=8.0,
        evasion_health_threshold=10.0,
        evasion_window_ticks=40,
        evasion_duration_ticks=40,
        thrust_max=35.0,           # 70% del max — EASY menos hábil
        dist_engage=1500.0,
        dist_fire=500.0,
        noise_prob=0.0,                # SIN noise por tick (rompe rotaciones)
    ),
    DifficultyLevel.MEDIUM: CheaterParams(
        aim_noise_deg=7.0,
        reaction_delay_ticks=8,
        prediction_horizon_ticks=3,
        fire_cone_deg=5.0,
        evasion_health_threshold=8.0,
        evasion_window_ticks=40,
        evasion_duration_ticks=50,
        thrust_max=45.0,           # 90% del max — MEDIUM
        dist_engage=1700.0,
        dist_fire=500.0,
        noise_prob=0.0,                # SIN noise por tick (rompe rotaciones)
    ),
    DifficultyLevel.HARD: CheaterParams(
        aim_noise_deg=2.0,
        reaction_delay_ticks=2,
        prediction_horizon_ticks=8,
        fire_cone_deg=6.0,   # ampliado para más cadencia (era 3°)
        evasion_health_threshold=5.0,
        evasion_window_ticks=30,
        evasion_duration_ticks=60,
        thrust_max=50.0,
        dist_engage=2500.0,        # persigue de lejos
        # dist_fire=2000 (artillería): el cheater es REFERENCIA/oponente.
        # Necesita disparar de lejos para sostener combate y que su daño
        # gatille la chaotic_evasion del rival. NOTA: el humano usa 700m
        # porque a >700m no impacta, pero el cheater tiene info perfecta
        # y mantiene una mejor tasa de impacto a larga.
        dist_fire=2000.0,
        noise_prob=0.0,
        use_vertical_aim=True,
        artillery_mode=True,       # lead aim balístico + compensación de gravedad
    ),
    DifficultyLevel.IMPOSSIBLE: CheaterParams(
        aim_noise_deg=0.0,
        reaction_delay_ticks=0,
        prediction_horizon_ticks=12,
        fire_cone_deg=2.0,
        evasion_health_threshold=3.0,
        evasion_window_ticks=25,
        evasion_duration_ticks=70,
        thrust_max=50.0,           # valor estable (sin errores LCP en ODE)
        dist_engage=2000.0,
        dist_fire=500.0,
        noise_prob=0.0,
        use_vertical_aim=True,
    ),
    # PREDATOR: aim mecánico de HARD + bait + safety belts.
    # Versión simplificada: feint y strafe eliminados porque rotaban el
    # cuerpo demasiado (las ruedas Ackermann giran ±5° con steering=1, y
    # como precesion es relativo al cuerpo, la torreta zigzaguea visualmente).
    # Solo queda bait: cuando el enemigo me persigue rápido, retroceder en
    # diagonal. Aim de HARD + dist_fire amplio + fire-on-the-move.
    # Ver agent/docs/04-predator.md
    DifficultyLevel.PREDATOR: CheaterParams(
        # Aim PRECISO: aim_noise=0 (los datos muestran que el ruido era la fuente
        # principal de misses, no la rotación del cuerpo).
        aim_noise_deg=0.0,
        reaction_delay_ticks=2,
        prediction_horizon_ticks=8,    # ignorado por adaptive_lead_aim=True
        fire_cone_deg=4.0,
        evasion_health_threshold=5.0,
        evasion_window_ticks=30,
        evasion_duration_ticks=60,
        thrust_max=50.0,           # valor estable (sin errores LCP en ODE)
        dist_engage=2000.0,
        dist_fire=500.0,
        noise_prob=0.0,
        use_vertical_aim=True,
        # Solo bait — feint y strafe eliminados por rotación excesiva del cuerpo:
        standoff_ratio=0.0,
        feint_interval_ticks=0,
        feint_intensity=0.0,
        strafe_when_aiming=False,
        bait_when_chased=True,
        bait_approach_threshold=40.0,
        # Lead aim adaptativo: DESACTIVADO en este preset porque empíricamente
        # empeoró el win-rate (sobre-predicción). El proyectil del sim parece
        # ser muy rápido (firepower=600 m/s) — lead aim debe ser muy chico.
        # Mantenemos los parámetros disponibles para experimentos futuros.
        adaptive_lead_aim=False,
        projectile_speed_m_per_tick=30.0,
        max_lead_ticks=20,
    ),
    # PREDATOR_V2: igual que PREDATOR pero con evasión CAÓTICA — cuando recibe
    # daño, movimientos genuinamente aleatorios + sigue disparando (fire-on-
    # the-move evasive). Diseñado para romper el lead aim de oponentes
    # scripted que esperan evasión predecible (retroceder + giro fijo).
    DifficultyLevel.PREDATOR_V2: CheaterParams(
        aim_noise_deg=0.0,
        reaction_delay_ticks=2,
        prediction_horizon_ticks=8,
        # Cono ANCHO (8°) — el dataset mostró que el aim siempre era < 3°
        # post-balístico, pero ampliar a 8° captura más oportunidades a larga
        # distancia donde la dispersión del proyectil ya domina al aim.
        fire_cone_deg=8.0,
        evasion_health_threshold=5.0,
        evasion_window_ticks=30,
        evasion_duration_ticks=60,
        thrust_max=50.0,
        dist_engage=2500.0,        # persigue de lejos
        # dist_fire=2000 (artillería): mantener el rango largo es lo que
        # permite que el combate empiece desde el spawn (1200-2400m
        # iniciales). Bajar a 700 rompe el cheater vs cheater porque casi
        # no hay daño → no se gatilla chaotic_evasion → se comporta como
        # PREDATOR normal.
        dist_fire=2000.0,
        noise_prob=0.0,
        use_vertical_aim=True,
        standoff_ratio=0.0,
        feint_interval_ticks=0,
        feint_intensity=0.0,
        strafe_when_aiming=False,
        bait_when_chased=True,
        bait_approach_threshold=40.0,
        adaptive_lead_aim=False,
        projectile_speed_m_per_tick=30.0,
        max_lead_ticks=20,
        chaotic_evasion=True,
        chaos_resample_every=8,
        artillery_mode=True,       # lead aim balístico + drop compensation
        # Body jiggle: cuerpo oscila random mientras dispara y persigue.
        # Mantiene aim preciso (torreta es independiente) pero hace al
        # predator impredecible. Genera dataset BC con más variedad de
        # rotaciones del cuerpo.
        engage_jiggle_enabled=True,
        engage_jiggle_every=20,        # cada 0.4s (menos nervioso que 0.3s)
        engage_jiggle_strength=0.35,   # ±0.35 (más sutil que 0.5)
        engage_jiggle_range=1.5,       # activa hasta dist_fire * 1.5 = 3000m
        # Swerve burst DESACTIVADO: con fire_cooldown_ticks=1, fire=True en
        # cada tick alineado → swerve_burst se reactivaba constantemente,
        # impidiendo girar para apuntar al enemigo cuando se desplazaba.
        swerve_burst_enabled=False,
        swerve_burst_duration_ticks=30,
        swerve_burst_thrust_factor=0.7,
        # Stuck detector: si pedimos avanzar pero no nos movemos (caja /
        # edificio en el medio), rotar 90° + avanzar 4s.
        # threshold subido a 5m: empíricamente las ruedas vibran 2-3m al chocar.
        # ventana 25 ticks = 0.5s (un poco más reactivo).
        stuck_detection_enabled=True,
        stuck_window_ticks=25,
        stuck_threshold_m=5.0,
        stuck_thrust_min=20.0,
        escape_rotation_target_deg=90.0,
        escape_advance_ticks=200,          # 4s
        escape_max_rotation_ticks=80,      # fallback 1.6s
        # Water guard: si caemos al agua, perdemos. Detección por Y absoluto.
        water_guard_enabled=True,
        water_y_danger=8.0,
        water_y_warn=15.0,
        water_falling_vy=-2.0,
        water_recovery_ticks=60,           # 1.2s manteniendo el rumbo al centro
    ),
}


def params_for_level(level) -> CheaterParams:
    """Devuelve presets calibrados para el nivel dado. Acepta str o enum."""
    if isinstance(level, str):
        level = DifficultyLevel(level.lower())
    return _PRESETS[level]


@dataclass
class CheaterState:
    enemy_pos_history: deque = field(default_factory=lambda: deque(maxlen=40))
    my_pos_history: deque = field(default_factory=lambda: deque(maxlen=40))
    # Histórico de Y para lead aim vertical (parábola con target en pendiente)
    enemy_y_history: deque = field(default_factory=lambda: deque(maxlen=40))
    my_y_history: deque = field(default_factory=lambda: deque(maxlen=40))
    health_history: deque = field(default_factory=lambda: deque(maxlen=120))
    evasion_left: int = 0
    evasion_dir: float = 1.0
    # Estado para heurísticas predator
    tick_counter: int = 0                   # cuenta ticks (para feint timing)
    feint_dir: float = 1.0                  # dirección actual del feint
    enemy_dist_history: deque = field(default_factory=lambda: deque(maxlen=15))
    # Estado para chaotic evasion (re-sampleado cada chaos_resample_every ticks)
    chaos_thrust: float = 0.0
    chaos_steering: float = 0.0
    # Estado para engage jiggle (oscilación random del cuerpo durante engage,
    # re-sampleado cada engage_jiggle_every ticks)
    jiggle_steering: float = 0.0
    # Estado para swerve burst post-fire: cuando dispara, arranca un burst
    # de N ticks donde el cuerpo se desplaza lateral fuerte para esquivar
    # el contra-tiro reactivo.
    swerve_left: int = 0
    swerve_dir: float = 1.0
    # Estado para stuck detection + escape: si pedimos avanzar y no nos
    # movemos, rotar 90° y avanzar 4s.
    thrust_history: deque = field(default_factory=lambda: deque(maxlen=35))
    escape_phase: str = "none"     # "none", "rotating", "advancing"
    escape_left: int = 0           # ticks restantes en la fase actual
    escape_az_start: float = 0.0   # azimuth al iniciar rotación
    escape_steer_dir: float = 1.0  # +1 = derecha, -1 = izquierda (random)
    escape_rotation_left: int = 0  # ticks máximos rotando (fallback)
    # FIX #1, #2: cooldown real + supresión por giro del enemigo
    ticks_since_fire: int = 100  # arranca "listo"
    bearing_history: deque = field(default_factory=lambda: deque(maxlen=10))
    # Water guard: ticks restantes de modo "recovery hacia centro"
    water_recovery_left: int = 0
    # === CLOSED-LOOP FIRE CONTROL ===
    # Auto-corrección del aim_y basado en landingPos del sim. Cada vez que
    # disparamos, guardamos dónde apuntamos + el tick. Cuando el sim manda un
    # landingPos nuevo, matcheamos por XZ (más cercano) con TTL de 200 ticks
    # (4s, suficiente para tiros más largos). EMA conservador (alpha=0.15)
    # y necesitamos ≥2 muestras antes de aplicar correction (anti-outlier).
    # Cada entry de pending_shots: (target_x, target_y, target_z, tick_fired)
    aim_y_correction: float = 0.0
    aim_correction_samples: int = 0   # cuántos updates exitosos llevamos
    pending_shots: deque = field(default_factory=lambda: deque(maxlen=12))
    last_landing_pos: Optional[Tuple[float, float, float]] = None
    last_my_health: float = 1000.0    # para detectar nuevo round
    tick_global: int = 0              # contador para TTL de pending_shots


def init_state(params: CheaterParams) -> CheaterState:
    maxlen = max(params.reaction_delay_ticks + params.prediction_horizon_ticks + 5, 10)
    # my_pos_history necesita ser >= stuck_window_ticks para detectar stuck.
    # Tomamos el máximo entre el maxlen del lead aim y la ventana de stuck.
    pos_window = max(maxlen, params.stuck_window_ticks + 5)
    thrust_window = max(params.stuck_window_ticks + 5, 35)
    return CheaterState(
        thrust_history=deque(maxlen=thrust_window),
        enemy_pos_history=deque(maxlen=maxlen),
        my_pos_history=deque(maxlen=pos_window),
        health_history=deque(maxlen=max(params.evasion_window_ticks + 5, 30)),
        bearing_history=deque(maxlen=params.bearing_rate_window + 2),
        ticks_since_fire=params.fire_cooldown_ticks,  # arranca "listo"
    )


def _delayed_and_predicted_pos(state: CheaterState, params: CheaterParams,
                               current_other_pos: Tuple[float, float, float],
                               my_pos: Tuple[float, float, float],
                               ) -> Tuple[float, float, int]:
    """Devuelve (aim_x, aim_z, lead_ticks_usados) — la posición que el cheater
    "ve" para apuntar.

    1. Toma la posición retrasada `reaction_delay_ticks` (lo que ve ahora,
       no en tiempo real).
    2. Estima velocidad con diferencia entre la pose vista y la anterior.
    3. Proyecta `lead_ticks` adelante.

    Si `params.adaptive_lead_aim=True`, `lead_ticks` se calcula dinámicamente
    como `distancia / projectile_speed`, capeado en `max_lead_ticks`. Esto
    soluciona el problema de que un lead fijo de 8 ticks subestima muchísimo
    el tiempo de vuelo del proyectil a distancias >300m.
    """
    state.enemy_pos_history.append((float(current_other_pos[0]),
                                    float(current_other_pos[2])))
    hist = list(state.enemy_pos_history)
    n = len(hist)

    # Posición que el cheater "ve" hoy (retrasada)
    delay_idx = max(0, n - 1 - params.reaction_delay_ticks)
    seen_x, seen_z = hist[delay_idx]

    # Determinar cuántos ticks predecir hacia adelante
    if params.adaptive_lead_aim:
        my_x = float(my_pos[0])
        my_z = float(my_pos[2])
        seen_dist = math.sqrt((seen_x - my_x) ** 2 + (seen_z - my_z) ** 2)
        speed = max(0.1, params.projectile_speed_m_per_tick)
        lead_ticks = min(params.max_lead_ticks, int(seen_dist / speed))
    else:
        lead_ticks = params.prediction_horizon_ticks

    if lead_ticks == 0 or delay_idx == 0:
        return seen_x, seen_z, lead_ticks

    # Velocidad estimada con diff finita corta (entre la pose vista y una previa)
    prev_idx = max(0, delay_idx - 3)
    prev_x, prev_z = hist[prev_idx]
    dt = max(1, delay_idx - prev_idx)
    vx = (seen_x - prev_x) / dt
    vz = (seen_z - prev_z) / dt

    pred_x = seen_x + vx * lead_ticks
    pred_z = seen_z + vz * lead_ticks
    return pred_x, pred_z, lead_ticks


def _fire_when_aligned(my_x: float, my_z: float,
                        aim_x: float, aim_z: float,
                        other_x: float, other_z: float,
                        state: "CheaterState", params: "CheaterParams",
                        target_y_for_correction: float = 0.0) -> bool:
    """Decide fire para los modos "especiales" (water_guard, escape_*).

    Si dispara, registra el target en state.pending_shots para el closed-loop.
    """
    if state.ticks_since_fire < params.fire_cooldown_ticks:
        return False
    dx_real = other_x - my_x
    dz_real = other_z - my_z
    real_dist = math.sqrt(dx_real * dx_real + dz_real * dz_real)
    if real_dist < 50 or real_dist > params.dist_fire:
        return False
    aim_dx = aim_x - my_x
    aim_dz = aim_z - my_z
    cross = aim_dx * dz_real - aim_dz * dx_real
    dot = aim_dx * dx_real + aim_dz * dz_real
    aim_offset = math.degrees(math.atan2(cross, dot))
    if abs(aim_offset) > params.fire_cone_deg:
        return False
    state.ticks_since_fire = 0
    state.pending_shots.append((other_x, target_y_for_correction, other_z,
                                 state.tick_global))
    return True


# Constantes del closed-loop (tuneables si hace falta)
_PENDING_SHOT_TTL_TICKS = 200      # 4s a 50Hz — descartar shots que nunca aterrizaron
_PENDING_MATCH_HORIZ_TOL_M = 300.0 # tolerancia XZ del matching landing↔target
_CORRECTION_EMA_ALPHA = 0.20       # conservador, evita overshoot por outliers
_CORRECTION_CLAMP_M = 25.0         # cota dura del offset
_CORRECTION_MIN_SAMPLES = 2        # ≥2 muestras antes de aplicar correction
_CORRECTION_OUTLIER_REJECT_M = 60.0 # dy_err > esto = outlier, descartar update


def _update_aim_correction(state: CheaterState, my_landing_pos):
    """Closed-loop: matchea landingPos nuevo con el shot pendiente más viejo
    que todavía esté en TTL, y actualiza aim_y_correction con EMA conservador.
    """
    # Limpiar shots vencidos por TTL (no aterrizaron cerca, los descartamos)
    while state.pending_shots and (
            state.tick_global - state.pending_shots[0][3] > _PENDING_SHOT_TTL_TICKS):
        state.pending_shots.popleft()

    if my_landing_pos is None:
        return
    lx, ly, lz = (float(my_landing_pos[0]), float(my_landing_pos[1]),
                  float(my_landing_pos[2]))
    # Sanidad: el sim manda basura/NaN antes del primer disparo
    if (not (math.isfinite(lx) and math.isfinite(ly) and math.isfinite(lz))
            or abs(lx) > 1e6 or abs(ly) > 1e6 or abs(lz) > 1e6):
        return
    cur = (lx, ly, lz)
    if state.last_landing_pos == cur:
        return  # mismo landing que ya procesamos
    state.last_landing_pos = cur

    if not state.pending_shots:
        return

    # Matcheamos con el shot más viejo (FIFO con TTL ya filtrado arriba)
    tx, ty, tz, _t_fired = state.pending_shots.popleft()
    horiz_err = math.sqrt((lx - tx) ** 2 + (lz - tz) ** 2)
    if horiz_err > _PENDING_MATCH_HORIZ_TOL_M:
        return  # landing muy lejos del target → outlier o mal match

    dy_err = ly - ty   # >0 = pasó por arriba; <0 = pasó por debajo
    if abs(dy_err) > _CORRECTION_OUTLIER_REJECT_M:
        return  # rechazo de outlier extremo (tiro muy raro / glitch del sim)

    state.aim_y_correction = (
        (1 - _CORRECTION_EMA_ALPHA) * state.aim_y_correction
        + _CORRECTION_EMA_ALPHA * dy_err
    )
    state.aim_y_correction = max(-_CORRECTION_CLAMP_M,
                                   min(_CORRECTION_CLAMP_M, state.aim_y_correction))
    state.aim_correction_samples += 1


def _maybe_reset_for_new_round(state: CheaterState, my_health: float):
    """Detectar inicio de nuevo round (health saltó de bajo → 1000) y limpiar
    estado dependiente del round."""
    if my_health > 990 and state.last_my_health < 500:
        # Nuevo round detectado
        state.aim_y_correction = 0.0
        state.aim_correction_samples = 0
        state.pending_shots.clear()
        state.last_landing_pos = None
        state.evasion_left = 0
        state.escape_phase = "none"
        state.swerve_left = 0
        state.water_recovery_left = 0
    state.last_my_health = my_health


def decide(my_pos, my_az_deg: float, my_health: float,
           other_pos, other_health: float,
           params: CheaterParams, state: CheaterState, rng,
           my_landing_pos=None
           ) -> Tuple[float, float, float, float, bool, str]:
    """Devuelve (thrust, steering, turret_decl, turret_bearing_deg, fire, mode_tag).

    Mode tag posibles: 'cheater_engage', 'cheater_evade', 'cheater_noise'.
    """
    my_x, my_y, my_z = float(my_pos[0]), float(my_pos[1]), float(my_pos[2])
    other_y = float(other_pos[1])

    state.health_history.append(float(my_health))
    # Trackear posición y Y SIEMPRE (no sólo cuando artillery_mode):
    # el stuck detector + el water guard dependen de estas series.
    state.my_pos_history.append((my_x, my_z))
    state.my_y_history.append(my_y)
    state.enemy_y_history.append(other_y)
    state.tick_global += 1

    # Detectar inicio de nuevo round (health saltó a 1000) y limpiar estado
    _maybe_reset_for_new_round(state, float(my_health))

    # === CLOSED-LOOP FIRE CONTROL ===
    # Update correction si hay landingPos nuevo
    _update_aim_correction(state, my_landing_pos)
    # Solo aplicar correction después de ≥2 muestras (anti-outlier)
    if state.aim_correction_samples >= _CORRECTION_MIN_SAMPLES:
        other_y_aim = other_y - state.aim_y_correction
    else:
        other_y_aim = other_y

    # 1) Noise override — fallas humanas en niveles bajos.
    # IMPORTANTE: noise NUNCA dispara — el propósito es diversidad de
    # MOVIMIENTO, no contaminar el dataset con disparos al aire.
    if params.noise_prob > 0 and rng.uniform() < params.noise_prob:
        return (
            float(rng.uniform(-params.thrust_max, params.thrust_max)),
            float(rng.uniform(-1, 1)),
            float(rng.uniform(-0.4, 0.4)),
            float(rng.uniform(-180, 180)),
            False,
            "cheater_noise",
        )

    # 2) Detectar daño rápido → activar evasivo
    if state.evasion_left == 0 and len(state.health_history) > params.evasion_window_ticks:
        h_old = state.health_history[-params.evasion_window_ticks]
        if (h_old - my_health) > params.evasion_health_threshold:
            state.evasion_left = params.evasion_duration_ticks
            state.evasion_dir = float(rng.choice([-1.0, 1.0]))

    # Posición efectiva del enemigo (con delay + lead aim, posiblemente adaptativo)
    aim_x, aim_z, _lead_used = _delayed_and_predicted_pos(
        state, params, other_pos, my_pos,
    )

    # ARTILLERÍA: si está activo, recalcular aim_x/aim_z/pitch con balística
    # completa (lead aim + drop por gravedad). Sobreescribe el aim simple del
    # _delayed_and_predicted_pos para distancias largas.
    if params.artillery_mode:
        # Velocidad estimada del enemigo + mía (lead relativo XZ + Y).
        # Las velocidades vienen en m/s (no por tick) — coherente con el
        # nuevo artillery_aim que trabaja en SI.
        # (my_pos_history / my_y_history / enemy_y_history se actualizan al
        # inicio de decide() — siempre, no sólo aquí.)
        e_v_xz = estimate_velocity_from_history(
            list(state.enemy_pos_history), lookback=params.velocity_lookback,
        )
        m_v_xz = estimate_velocity_from_history(
            list(state.my_pos_history), lookback=params.velocity_lookback,
        )
        e_vy = estimate_vy_from_history(
            list(state.enemy_y_history), lookback=params.velocity_lookback,
        )
        m_vy = estimate_vy_from_history(
            list(state.my_y_history), lookback=params.velocity_lookback,
        )
        # Auto-arco alto cuando hay relieve probable (enemigo abajo + media-larga dist)
        d_pre_xz = math.sqrt(
            (float(other_pos[0]) - my_x) ** 2 + (float(other_pos[2]) - my_z) ** 2
        )
        arc_high = should_use_high_arc(my_y, other_y, d_pre_xz)
        aim_x, aim_z, turret_decl = artillery_aim(
            my_pos=(my_x, my_y, my_z),
            other_pos=(float(other_pos[0]), other_y_aim, float(other_pos[2])),
            other_vel_xz=e_v_xz,
            my_vel_xz=m_v_xz,
            other_vel_y=e_vy,
            my_vel_y=m_vy,
            arc_high=arc_high,
        )

    # Bearing al punto de mira + ruido gaussiano
    bearing = relative_bearing_deg(my_x, my_z, my_az_deg, aim_x, aim_z)
    if params.aim_noise_deg > 0:
        bearing += float(rng.normal(0.0, params.aim_noise_deg))

    target_dist = math.sqrt((aim_x - my_x) ** 2 + (aim_z - my_z) ** 2)
    polar_d = math.sqrt(my_x ** 2 + my_z ** 2)

    # Pitch de torreta: si NO usamos artillería, calcular el clásico.
    # (Si artillery_mode, ya se calculó arriba con drop compensation.)
    if not params.artillery_mode:
        if params.use_vertical_aim:
            turret_decl = pitch_to_target_rad(my_y, other_y, max(target_dist, 1.0))
            turret_decl = max(-0.4, min(0.4, turret_decl))
        else:
            turret_decl = float(rng.uniform(-0.4, 0.4))

    # 2.5) WATER GUARD — PREVENTIVO. Detecta el riesgo ANTES de tocar agua:
    # más allá del radio polar_warn ya estamos en zona de borde de terreno.
    # Cuando se activa, anula combate + apunta al centro + NO dispara.
    # Mantiene el modo recovery `water_recovery_ticks` ticks para no oscilar
    # justo en el umbral. Fallback por Y si caímos por acantilado central.
    if params.water_guard_enabled:
        polar_d_now = math.sqrt(my_x * my_x + my_z * my_z)
        # Estimar velocidad vertical (fallback de caída)
        vy_est = 0.0
        if len(state.my_y_history) >= 6:
            y_recent = list(state.my_y_history)[-6:]
            vy_est = (y_recent[-1] - y_recent[0]) / (5 * 0.02)  # 5 ticks @ 50Hz

        polar_danger = polar_d_now > params.water_polar_warn
        y_danger = (
            my_y < params.water_y_danger
            or (vy_est < params.water_falling_vy and my_y < params.water_y_warn)
        )
        if polar_danger or y_danger:
            state.water_recovery_left = params.water_recovery_ticks

        if state.water_recovery_left > 0:
            state.water_recovery_left -= 1
            # Apuntar hacia el centro del mapa (0, 0): bearing relativo
            recover_bearing = relative_bearing_deg(
                my_x, my_z, my_az_deg, 0.0, 0.0,
            )
            if recover_bearing > 5.0:
                steering_w = 1.0
            elif recover_bearing < -5.0:
                steering_w = -1.0
            else:
                steering_w = 0.0
            # Resetear escape phase (si estábamos en stuck-escape, prioridad agua)
            state.escape_phase = "none"
            state.swerve_left = 0
            # FIRE-ANYWAY: aunque estemos saliendo del agua, si el aim está bien
            # disparamos igual (la torreta es independiente del cuerpo).
            state.ticks_since_fire += 1
            fire_anyway = _fire_when_aligned(
                my_x, my_z, aim_x, aim_z,
                float(other_pos[0]), float(other_pos[2]),
                state, params,
                target_y_for_correction=other_y,
            )
            return (
                float(params.thrust_max),
                float(steering_w),
                turret_decl,
                float(bearing),
                fire_anyway,
                "cheater_water_guard",
            )

    # 3) Modo evasivo
    if state.evasion_left > 0:
        state.evasion_left -= 1

        if params.chaotic_evasion:
            # Movimientos genuinamente random (rompen lead aim del oponente).
            # Re-sampleamos cada N ticks para que la dirección cambie con
            # frecuencia humana (cada ~160ms a 50Hz con N=8).
            ticks_into_evasion = params.evasion_duration_ticks - state.evasion_left
            if ticks_into_evasion % params.chaos_resample_every == 1:
                state.chaos_thrust = float(rng.choice([
                    -params.thrust_max,
                    -params.thrust_max * 0.5,
                    0.0,
                    params.thrust_max * 0.5,
                    params.thrust_max,
                ]))
                state.chaos_steering = float(rng.choice([-1.0, -0.5, 0.0, 0.5, 1.0]))

            # Fire-on-the-move evasive: si la torreta está apuntando bien,
            # también dispara durante la evasión (la torreta es independiente
            # del cuerpo — el body zigzaguea, la torreta sigue al enemigo).
            # Aplicamos también el cooldown FIX #1 — sino spammeamos fire
            # al pedo durante toda la evasión.
            real_dx_e = float(other_pos[0]) - my_x
            real_dz_e = float(other_pos[2]) - my_z
            aim_dx_e = aim_x - my_x
            aim_dz_e = aim_z - my_z
            cross_e = aim_dx_e * real_dz_e - aim_dz_e * real_dx_e
            dot_e = aim_dx_e * real_dx_e + aim_dz_e * real_dz_e
            aim_offset_e = math.degrees(math.atan2(cross_e, dot_e))
            real_dist_e = math.sqrt(real_dx_e ** 2 + real_dz_e ** 2)
            state.ticks_since_fire += 1
            evade_fire = (real_dist_e < params.dist_fire and
                          abs(aim_offset_e) < params.fire_cone_deg and
                          state.ticks_since_fire >= params.fire_cooldown_ticks)
            if evade_fire:
                state.ticks_since_fire = 0

            return (
                state.chaos_thrust,
                state.chaos_steering,
                turret_decl,
                float(bearing),
                evade_fire,
                "cheater_chaos",
            )

        # Evasión clásica predecible (retroceder + giro fijo, sin disparar)
        return (
            -params.thrust_max * 0.7,
            state.evasion_dir,
            turret_decl,
            float(bearing),
            False,
            "cheater_evade",
        )

    # --- PREDATOR pre-cálculos: detectar si el enemigo se acerca rápido ---
    state.tick_counter += 1
    state.enemy_dist_history.append(target_dist)
    enemy_approaching = False
    if params.bait_when_chased and len(state.enemy_dist_history) >= 10:
        d_change = state.enemy_dist_history[0] - state.enemy_dist_history[-1]
        dist_velocity = d_change * 2.0   # ~m/s
        if dist_velocity > params.bait_approach_threshold:
            enemy_approaching = True

    # --- PREDATOR safety belts ---
    # Las heurísticas anti-scripted (standoff, bait, feint, strafe) son útiles
    # SOLO en combate cercano. Si el predator se aleja mucho del centro del
    # mapa, retrocede sin frenar y termina cayéndose al agua. Definimos dos
    # umbrales que desactivan las heurísticas defensivas:
    #
    # 1. polar_d > MAP_RECOVERY_DIST → "modo recovery": volver al centro
    # 2. target_dist > ENGAGE_DIST → "modo persecución": ignorar standoff/bait
    MAP_RECOVERY_DIST = 1500.0
    ENGAGE_PURSUIT_DIST = 700.0
    in_recovery = polar_d > MAP_RECOVERY_DIST
    far_from_enemy = target_dist > ENGAGE_PURSUIT_DIST

    # Heurísticas predator activas solo en combate cercano sin riesgo de salirse
    use_heuristics = (
        params.standoff_ratio > 0.0 and
        not in_recovery and
        not far_from_enemy
    )

    # 4) Engage: perseguir + apuntar + disparar si está en cono
    thrust = 0.0
    steering = 0.0
    mode_tag = "cheater_engage"

    # --- PREDATOR: standoff (solo si heurísticas habilitadas) ---
    if use_heuristics:
        desired_dist = params.dist_fire * params.standoff_ratio
        if target_dist < desired_dist * 0.9:
            thrust = -params.thrust_max * 0.8
            mode_tag = "cheater_standoff"
        elif target_dist > desired_dist * 1.1:
            thrust = params.thrust_max
        # En el sweet spot: thrust=0
    else:
        # Lógica clásica (cheater no-predator o predator en recovery/persecución)
        if in_recovery:
            mode_tag = "cheater_recovery"
        if polar_d < params.dist_engage:
            thrust = params.thrust_max
        else:
            thrust = 0.0

    # --- FIX CRÍTICO: el sim spawnea el proyectil 40m ADELANTE del cañón
    # (AdvancedWalrus.cpp:732 — position += 40*forward). Si la distancia al
    # enemigo es <40m, el proyectil aparece PASADO el enemigo y se va al
    # vacío. Solución: si están muy pegados, retroceder fuerte SIN disparar
    # hasta separarse al menos a (FIRING_FORWARD_OFFSET + margen) = 60m. ---
    real_dx_close = float(other_pos[0]) - my_x
    real_dz_close = float(other_pos[2]) - my_z
    real_dist_close = math.sqrt(real_dx_close ** 2 + real_dz_close ** 2)
    too_close = real_dist_close < 60.0   # margen sobre los 40m de spawn

    if too_close:
        # Retroceso fuerte alejándose en la dirección opuesta al enemigo.
        # Steering: girar para quedar de espaldas al enemigo (más rápido
        # alejarse de espaldas que de costado).
        thrust = -params.thrust_max
        steering = 1.0 if bearing > 0 else -1.0
        mode_tag = "cheater_too_close"
    elif (params.bait_when_chased and
          enemy_approaching and
          target_dist < params.dist_fire * 2.0 and
          not in_recovery and
          not far_from_enemy):
        # PREDATOR bait normal: enemigo se acerca rápido pero todavía no estamos pegados
        thrust = -params.thrust_max * 0.7
        bait_steer = 1.0 if bearing > 0 else -1.0
        steering = bait_steer
        mode_tag = "cheater_bait"
    else:
        # Steering normal: girar hacia el enemigo
        if bearing > 0:
            steering = 1.0
            if thrust == 0.0 and not use_heuristics:
                thrust = params.thrust_max
        elif bearing < 0:
            steering = -1.0
            if thrust == 0.0 and not use_heuristics:
                thrust = params.thrust_max

    # --- PREDATOR: feint (solo si heurísticas habilitadas) ---
    if use_heuristics and params.feint_interval_ticks > 0:
        if state.tick_counter % params.feint_interval_ticks == 0:
            state.feint_dir *= -1.0
        if mode_tag == "cheater_engage":
            steering = float(np.clip(
                steering + state.feint_dir * params.feint_intensity, -1.0, 1.0
            ))

    # --- PREDATOR: strafe (solo si heurísticas habilitadas) ---
    if use_heuristics and params.strafe_when_aiming and abs(bearing) < params.fire_cone_deg * 3.0:
        strafe_dir = 1.0 if bearing >= 0 else -1.0
        steering = float(np.clip(steering + strafe_dir * 0.3, -1.0, 1.0))

    # --- BODY JIGGLE: oscilar cuerpo random durante engage ---
    # Solo en modo engage (NO durante bait, too_close, recovery) y solo si
    # estamos en rango cercano de combate (target_dist < dist_fire * range).
    # La torreta apunta independientemente al enemigo (precesion se manda
    # cada tick), así que el cuerpo zigzaguea sin afectar el aim.
    #
    # CONDICIONAL: solo aplicar jiggle cuando el cuerpo YA está alineado al
    # enemigo (bearing chico). Si necesita girar fuerte para perseguir,
    # prioridad a la persecución — sin esto el predator daba vueltas en
    # círculos en vez de avanzar (medido empíricamente: ratio displ/dist
    # bajaba a 0.42 con 3 vueltas completas en un episodio).
    body_aligned = abs(bearing) < 30.0   # menos de 30° de bearing → estamos OK
    if (params.engage_jiggle_enabled and
            mode_tag == "cheater_engage" and
            body_aligned and
            target_dist < params.dist_fire * params.engage_jiggle_range):
        if state.tick_counter % params.engage_jiggle_every == 0:
            state.jiggle_steering = float(rng.uniform(
                -params.engage_jiggle_strength, params.engage_jiggle_strength
            ))
        steering = float(np.clip(steering + state.jiggle_steering, -1.0, 1.0))
        mode_tag = "cheater_engage_jiggle"

    # Fire trigger basado en la TORRETA, no en el cuerpo.
    # Verificamos en agent/docs/02-contrato-cpp.md: el disparo del Otter sale
    # donde apunta la torreta (precesion), NO donde mira el cuerpo. Como nuestra
    # torreta apunta a `bearing` (que viene del aim_x, aim_z post-delay+lead),
    # el cono mide cuán cerca está ese aim de la POSICIÓN REAL del enemigo.
    # Esto habilita fire-on-the-move: el cuerpo puede ir lateral/zigzag mientras
    # la torreta sigue apuntando bien al enemigo.
    real_dx = float(other_pos[0]) - my_x
    real_dz = float(other_pos[2]) - my_z
    aim_dx = aim_x - my_x
    aim_dz = aim_z - my_z
    # Ángulo entre vector aim y vector real desde mi posición
    cross = aim_dx * real_dz - aim_dz * real_dx
    dot = aim_dx * real_dx + aim_dz * real_dz
    aim_offset_deg = math.degrees(math.atan2(cross, dot))

    # Distancia 2D al enemigo REAL (no al punto predicho)
    real_dist = math.sqrt(real_dx ** 2 + real_dz ** 2)

    # FIX #2: supresión por giro del ENEMIGO. Usamos azimuth ABSOLUTO al
    # enemigo (world frame), NO el bearing relativo, porque si el cheater
    # gira (steering/bait/chaos), el bearing cambia aunque el enemigo no se
    # mueva, y eso suprimiría disparos válidos. Sólo queremos suprimir cuando
    # el ENEMIGO cambia de posición rápido.
    world_az_to_enemy = azimuth_deg(my_x, my_z,
                                    float(other_pos[0]), float(other_pos[2]))
    state.bearing_history.append(world_az_to_enemy)
    bearing_rate_high = False
    if len(state.bearing_history) >= params.bearing_rate_window + 1:
        recent = list(state.bearing_history)[-(params.bearing_rate_window + 1):]
        d_b = recent[-1] - recent[0]
        d_b = (d_b + 180.0) % 360.0 - 180.0
        if abs(d_b) > params.bearing_rate_suppress_deg:
            bearing_rate_high = True

    # FIX #1: cooldown local. setTtl(100) = 2.0s entre tiros reales.
    # Mandar fire=True más rápido es desperdicio y contamina el dataset.
    state.ticks_since_fire += 1
    cooldown_ready = state.ticks_since_fire >= params.fire_cooldown_ticks

    # FIX TOO-CLOSE: el proyectil del sim spawnea 40m adelante del cañón.
    # Si dist < 50m, el proyectil sale PASADO el enemigo → imposible impactar.
    # Suprimimos el disparo en rango cercano para no desperdiciar cooldowns.
    # Ver AdvancedWalrus.cpp:732 (`position += 40*forward`).
    too_close_to_fire = real_dist < 50.0

    # OPT 3: Sweet spot de distancia. Cap efectivo: si > dist_fire_effective,
    # no disparar (reserva cooldown para tiros con chance real >0%).
    too_far_for_effective = real_dist > params.dist_fire_effective

    # OPT 2: No disparar mientras el cuerpo está rotando fuerte POR EL JIGGLE.
    # Si el jiggle metió un steering random alto, el aim de la torreta puede
    # tener un instante de desalineamiento → mejor esperar. NO suprimimos
    # cuando el steering alto viene de seguir al enemigo (es estable).
    body_rotating_hard = (
        params.engage_jiggle_enabled and
        mode_tag == "cheater_engage_jiggle" and
        abs(state.jiggle_steering) > params.no_fire_if_steering_above * 0.6
    )

    # OPT 1: Cono adaptativo. Si hay tiempo (enemigo no se aleja rápido y
    # no estamos forzados), usar cono ESTRICTO. Si el enemigo va a salir
    # del rango efectivo pronto, usar el cono ancho normal.
    # Detectamos "enemigo alejándose" si dist_velocity > umbral.
    enemy_leaving = False
    if len(state.enemy_dist_history) >= 5:
        d_change = state.enemy_dist_history[-1] - state.enemy_dist_history[0]
        if d_change > 30.0:  # se alejó >30m en los últimos ticks
            enemy_leaving = True
    cone_deg = (params.fire_cone_deg if enemy_leaving
                else params.fire_cone_strict_deg)

    fire = False
    if (real_dist < params.dist_fire
            and not too_close_to_fire
            and not too_far_for_effective
            and not body_rotating_hard
            and abs(aim_offset_deg) < cone_deg
            and cooldown_ready
            and not bearing_rate_high):
        fire = True
        state.ticks_since_fire = 0
        # Registrar shot para closed-loop fire control (incluye tick para TTL)
        state.pending_shots.append((float(other_pos[0]), other_y,
                                     float(other_pos[2]), state.tick_global))
        # No paramos thrust al disparar — fire-on-the-move es la idea
        # SWERVE BURST: cuando dispara, arranca un burst de N ticks de
        # desplazamiento lateral fuerte para esquivar el contra-tiro del
        # enemigo (que va a llegar ~1-2s después al punto donde el predator
        # estaba al disparar — si se mueve lateral, falla).
        if params.swerve_burst_enabled:
            state.swerve_left = params.swerve_burst_duration_ticks
            state.swerve_dir = float(rng.choice([-1.0, 1.0]))

    # Aplicar swerve burst si está activo. Override del steering normal.
    # Mantiene el aim (torreta independiente) pero el cuerpo se desplaza
    # fuerte para esquivar contra-tiros.
    #
    # Cada `swerve_resample_every` ticks (default 10 = 0.2s) re-sampleamos
    # la dirección random. Eso da ~3 cambios de dirección en los 0.6s del
    # burst → patrón impredecible para el enemigo. La magnitud también
    # varía levemente para que no sea siempre exacto ±1.
    if state.swerve_left > 0:
        ticks_into_swerve = params.swerve_burst_duration_ticks - state.swerve_left
        if ticks_into_swerve % params.swerve_resample_every == 0:
            state.swerve_dir = float(rng.choice([-1.0, -0.8, 0.8, 1.0]))
        steering = state.swerve_dir
        thrust = thrust * params.swerve_burst_thrust_factor   # giro más cerrado
        state.swerve_left -= 1
        mode_tag = "cheater_swerve_burst"

    # === STUCK DETECTOR + ESCAPE ===
    # Si pedimos avanzar pero el cuerpo no se mueve (chocando contra caja /
    # edificio / barco / borde), rotar 90° y avanzar 4s para zafarse.
    # Esta lógica SOBRE-ESCRIBE thrust/steering/fire si está activa.
    if params.stuck_detection_enabled:
        # Trackear cuánto thrust pedimos en cada tick (para el detector)
        state.thrust_history.append(float(thrust))

        # Si ya estamos en escape, continuar el flujo
        if state.escape_phase == "rotating":
            # Rotar hasta que hayamos girado escape_rotation_target_deg
            # (o hasta el fallback de escape_max_rotation_ticks)
            az_delta = abs((my_az_deg - state.escape_az_start + 180.0) % 360.0 - 180.0)
            state.escape_rotation_left -= 1
            if (az_delta >= params.escape_rotation_target_deg or
                    state.escape_rotation_left <= 0):
                state.escape_phase = "advancing"
                state.escape_left = params.escape_advance_ticks
                steering = 0.0
                thrust = params.thrust_max
                mode_tag = "cheater_escape_advance"
            else:
                steering = state.escape_steer_dir
                thrust = params.thrust_max
                mode_tag = "cheater_escape_rotate"
            # FIRE-ANYWAY: la torreta sigue al enemigo aunque el cuerpo rote
            state.ticks_since_fire += 1
            fire = _fire_when_aligned(
                my_x, my_z, aim_x, aim_z,
                float(other_pos[0]), float(other_pos[2]),
                state, params,
                target_y_for_correction=other_y,
            )
            return (float(thrust), float(steering), turret_decl,
                    float(bearing), fire, mode_tag)

        if state.escape_phase == "advancing":
            steering = 0.0
            thrust = params.thrust_max
            state.escape_left -= 1
            if state.escape_left <= 0:
                state.escape_phase = "none"
            mode_tag = "cheater_escape_advance"
            # FIRE-ANYWAY también acá
            state.ticks_since_fire += 1
            fire = _fire_when_aligned(
                my_x, my_z, aim_x, aim_z,
                float(other_pos[0]), float(other_pos[2]),
                state, params,
                target_y_for_correction=other_y,
            )
            return (float(thrust), float(steering), turret_decl,
                    float(bearing), fire, mode_tag)

        # Detectar stuck: thrust positivo sostenido + pos casi sin cambio
        if (state.escape_phase == "none" and
                len(state.my_pos_history) >= params.stuck_window_ticks and
                len(state.thrust_history) >= params.stuck_window_ticks):
            recent_thrusts = list(state.thrust_history)[-params.stuck_window_ticks:]
            avg_thrust = sum(recent_thrusts) / len(recent_thrusts)
            recent_pos = list(state.my_pos_history)[-params.stuck_window_ticks:]
            x_then, z_then = recent_pos[0]
            x_now, z_now = recent_pos[-1]
            displacement = math.sqrt((x_now - x_then) ** 2 + (z_now - z_then) ** 2)

            if abs(avg_thrust) > params.stuck_thrust_min and displacement < params.stuck_threshold_m:
                state.escape_phase = "rotating"
                state.escape_az_start = my_az_deg
                state.escape_steer_dir = float(rng.choice([-1.0, 1.0]))
                state.escape_rotation_left = params.escape_max_rotation_ticks
                steering = state.escape_steer_dir
                thrust = params.thrust_max
                mode_tag = "cheater_escape_rotate"
                # FIRE-ANYWAY también acá (primer tick de stuck-detected)
                state.ticks_since_fire += 1
                fire = _fire_when_aligned(
                    my_x, my_z, aim_x, aim_z,
                    float(other_pos[0]), float(other_pos[2]),
                    state, params,
                )
                return (float(thrust), float(steering), turret_decl,
                        float(bearing), fire, mode_tag)

    return (
        float(thrust),
        float(steering),
        turret_decl,           # pitch correcto si use_vertical_aim, random si no
        float(bearing),        # turret_bearing = bearing apuntado
        fire,
        mode_tag,
    )
