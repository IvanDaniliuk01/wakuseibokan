"""Helpers compartidos entre seek_policy y cheater_policy.

Mantener acá las funciones que no dependen del estado del controlador para que
ambas políticas (la "fábrica de datos" y el cheater) las usen sin duplicar.

Convención de ejes del sim: Y es vertical, X-Z es el plano horizontal. Ver
agent/docs/01-altura-y-pitch.md para por qué la mayoría de las funciones
solo usan (x, z) y dónde sí importa Y (pitch de torreta).
"""
import math
import numpy as np


def azimuth_deg(x1: float, z1: float, x2: float, z2: float) -> float:
    """Ángulo en grados de (x1,z1)→(x2,z2) en la convención del simulador.

    El sim usa Y como vertical y X-Z como plano horizontal. El azimuth 0°
    apunta al -Z, crece hacia +X. La fórmula aplica el offset clásico
    (+270 / -90) para alinear con la convención de ModelRecord.azimuth.
    """
    dx = x2 - x1
    dz = z2 - z1
    val = np.arctan2(dz, dx) * 180.0 / np.pi
    return (val - 90) if val >= 90 else (val + 270)


def relative_bearing_deg(my_x: float, my_z: float, my_az_deg: float,
                         other_x: float, other_z: float) -> float:
    """Bearing del enemigo relativo a la heading del agente. En [-180, 180]."""
    raw = azimuth_deg(my_x, my_z, other_x, other_z) - my_az_deg
    # normalizar a [-180, 180]
    raw = (raw + 180.0) % 360.0 - 180.0
    return raw


# Modelo balístico real del sim (verificado leyendo AdvancedWalrus.cpp:705-760):
#  - El proyectil spawnea en `getPos() + 40*forward + (0, FIRING_Y_OFFSET_M, 0)`
#    donde `forward` ya incluye el pitch de la torreta (apunta en 3D).
#  - La velocidad inicial es `firepower * forward` = 600 * forward (m/s),
#    NO horizontal. Si pitch=10° arriba, la velocidad vertical inicial es
#    600*sin(10°) ≈ 104 m/s hacia arriba.
#  - Gravedad de ODE en Y = -9.81 m/s² (keplerivworld.cpp:1017).
#  - dWorldStep(0.05) → 50 Hz, todo en metros y segundos.

FIRING_Y_OFFSET_M = 2.3      # firingpos[1] en AdvancedWalrus.cpp:40
FIRING_FORWARD_OFFSET_M = 40.0  # `position += 40*forward` en AdvancedWalrus.cpp:732
PROJECTILE_SPEED_M_PER_S = 600.0  # firepower (AdvancedWalrus.h:21)
GRAVITY_M_PER_S2 = 9.81
SIM_TICK_DT_S = 0.05

# Aliases por compatibilidad con código que esperaba la unidad "por tick":
PROJECTILE_SPEED_M_PER_TICK = PROJECTILE_SPEED_M_PER_S * SIM_TICK_DT_S  # = 30.0
GRAVITY_M_PER_TICK_SQ = GRAVITY_M_PER_S2 * (SIM_TICK_DT_S ** 2)         # = 0.0245
GUN_OFFSET_Y_M = FIRING_Y_OFFSET_M  # 2.3, valor REAL del sim


def pitch_to_target_rad(my_y: float, other_y: float,
                        horizontal_dist: float,
                        gun_offset_y: float = GUN_OFFSET_Y_M) -> float:
    """Declinación de la torreta para apuntar al CENTRO del enemigo,
    compensando que el cañón está físicamente por encima del centro del Otter.
    Ver artillery_aim() para el modelo balístico completo (incluye drop).
    """
    real_dy = (other_y - my_y) - gun_offset_y
    return math.atan2(real_dy, max(horizontal_dist, 1.0))


def artillery_aim(my_pos, other_pos, other_vel_xz,
                  my_vel_xz=(0.0, 0.0),
                  other_vel_y: float = 0.0,
                  my_vel_y: float = 0.0,
                  projectile_speed_s=PROJECTILE_SPEED_M_PER_S,
                  gravity_s=GRAVITY_M_PER_S2,
                  gun_offset_y=FIRING_Y_OFFSET_M,
                  forward_offset=FIRING_FORWARD_OFFSET_M,
                  iters=4,
                  arc_high: bool = False):
    """Aim balístico 3D completo, modelando exactamente el sim.

    Modelo (todo en m y s):
        spawn = my_pos + 40*forward + (0, 2.3, 0)
        v_proj = 600 * forward      (forward = unit vector con pitch + azimuth)
        pos(t) = spawn + v_proj*t + 0.5*(0,-g,0)*t²
        target(t) = enemy_pos + (v_enemy_x, 0, v_enemy_z) * t

    Asumimos pitch chico (≤ ~10°), lo cual es válido para nuestro rango de
    distancias (<3000m) — la componente horizontal de la velocidad del
    proyectil es ≈ projectile_speed * cos(pitch) ≈ projectile_speed. La
    componente vertical sí importa para el drop.

    Args:
        my_pos: (x, y, z) propia
        other_pos: (x, y, z) del enemigo
        other_vel_xz: (vx, vz) en m/s del enemigo
        my_vel_xz: (vx, vz) en m/s propia — IMPORTANTE: cuando vos te movés,
                   también te alejás/acercás del punto de impacto durante el
                   tiempo de vuelo, así que tu velocidad también entra al lead.
        other_vel_y: vy en m/s del enemigo (subir/bajar pendiente). Si el
                     enemigo va cuesta arriba/abajo durante el tiempo de
                     vuelo (1-2s), su Y cambia → el pitch calculado quedará
                     desfasado. Compensamos prediciendo Y futuro.
        my_vel_y: vy propia (mismo motivo).
        projectile_speed_s: m/s velocidad inicial del proyectil
        gravity_s: m/s² gravedad mundo
        arc_high: si True, usa la SOLUCIÓN ALTA (tipo mortero, parábola
                  arqueada) en vez de la directa. Útil cuando hay terreno
                  entre yo y el enemigo (proyectil pasa por encima del
                  relieve). El sim tiene pitch clampeado a [-0.4, 0.4]
                  (~23°), entonces no podemos hacer arcos demasiado altos.

    Returns:
        (aim_x, aim_z, pitch_rad) — torreta debe apuntar a (aim_x, aim_z) en
        coordenadas mundo, con pitch_rad clampeado a [-0.4, 0.4].
    """
    my_x, my_y, my_z = float(my_pos[0]), float(my_pos[1]), float(my_pos[2])
    ox, oy, oz = float(other_pos[0]), float(other_pos[1]), float(other_pos[2])
    e_vx, e_vz = float(other_vel_xz[0]), float(other_vel_xz[1])
    m_vx, m_vz = float(my_vel_xz[0]), float(my_vel_xz[1])
    e_vy = float(other_vel_y)
    m_vy = float(my_vel_y)

    # Spawn del proyectil ANTES de aplicar el forward offset (eso depende del
    # pitch que estamos calculando — iteramos).
    # Aproximación inicial: el aim point es la posición ACTUAL del enemigo.
    aim_x, aim_z = ox, oz
    aim_y = oy  # lead aim vertical (se refina en cada iteración con t_flight)
    t_flight = 0.0
    pitch = 0.0

    # Velocidad relativa: el "blanco efectivo" se mueve a (e_vx - m_vx, e_vz - m_vz)
    # respecto de nosotros porque nosotros también nos movemos. Idem en Y.
    rel_vx = e_vx - m_vx
    rel_vz = e_vz - m_vz
    rel_vy = e_vy - m_vy

    # Para resolver la ecuación balística:
    #   dx_horiz = v0 * cos(p) * t
    #   dy       = v0 * sin(p) * t - 0.5 * g * t²
    # Despejando t = dx_horiz / (v0 * cos(p)) y sustituyendo:
    #   dy = dx_horiz * tan(p) - g * dx_horiz² / (2 * v0² * cos²(p))
    # Que en función de tan(p) (con sec² = 1 + tan²) es una cuadrática en tan(p):
    #   (g * dx² / (2 * v0²)) * tan²(p) - dx * tan(p) + (g * dx² / (2 * v0²) + dy) = 0
    # Dos soluciones: arco bajo (tan(p) chica) y arco alto (tan(p) grande).
    v0 = projectile_speed_s
    g = gravity_s

    for _ in range(iters):
        dx = aim_x - my_x
        dz = aim_z - my_z
        dist_xz = math.sqrt(dx * dx + dz * dz)
        if dist_xz < 1.0:
            break

        # FIX CRÍTICO: el spawn del sim NO es horizontal, sino 3D en la
        # dirección del cañón (AdvancedWalrus.cpp:732):
        #   forward = toVectorInFixedSystem(0,0,1, azimuth, elevation)
        #   position = position + 40 * forward      ← 3D, no horizontal!
        #   position[1] += firingpos[1]              ← +2.3m DESPUÉS
        #
        # Componente horizontal del 40m: 40 * cos(pitch)
        # Componente vertical:           40 * sin(pitch)
        #
        # Iteramos: pitch arranca en 0, cada iter refina spawn y vuelve a
        # resolver la cuadrática. Converge en 3-4 iters.
        sin_p = math.sin(pitch)
        cos_p = math.cos(pitch)
        spawn_horiz = forward_offset * cos_p
        spawn_vert = forward_offset * sin_p
        ux = dx / dist_xz
        uz = dz / dist_xz
        spawn_x = my_x + spawn_horiz * ux
        spawn_z = my_z + spawn_horiz * uz
        spawn_y = my_y + gun_offset_y + spawn_vert

        dx_s = aim_x - spawn_x
        dz_s = aim_z - spawn_z
        dist_xz_s = math.sqrt(dx_s * dx_s + dz_s * dz_s)
        if dist_xz_s < 1.0:
            break

        # Δy contra el aim_y PREDICHO (no el actual oy). Esto cubre el caso
        # del enemigo subiendo/bajando una pendiente durante el tiempo de
        # vuelo: si va cuesta arriba a 5 m/s y t_flight=1.5s, el target
        # estará 7.5m más arriba que ahora — apuntamos a eso.
        dy = aim_y - spawn_y

        # Cuadrática: a*tan² + b*tan + c = 0
        a = (g * dist_xz_s * dist_xz_s) / (2.0 * v0 * v0)
        b = -dist_xz_s
        c = a + dy
        disc = b * b - 4.0 * a * c

        if disc < 0:
            # Sin solución balística (target inalcanzable con v0). Usamos
            # el ángulo de máximo alcance (45° con dy=0, ajustado por dy).
            pitch = math.atan2(max(0.0, dy + 100.0), dist_xz_s) + 0.1
        else:
            sqrt_disc = math.sqrt(disc)
            # tan_low = arco bajo (proyectil va casi horizontal, llega rápido)
            # tan_high = arco alto (mortero, llega arqueado por encima)
            tan_low = (-b - sqrt_disc) / (2.0 * a)
            tan_high = (-b + sqrt_disc) / (2.0 * a)
            pitch = math.atan(tan_high if arc_high else tan_low)

        # Tiempo de vuelo con el pitch encontrado
        v_horiz = v0 * math.cos(pitch)
        t_flight = dist_xz_s / max(v_horiz, 1.0)

        # Lead aim relativo en XZ Y EN Y: target se mueve durante el tiempo
        # de vuelo. La Y se proyecta linealmente (asumimos pendiente local
        # estable — válido para t_flight < 2s a velocidades < 20 m/s).
        aim_x = ox + rel_vx * t_flight
        aim_z = oz + rel_vz * t_flight
        aim_y = oy + rel_vy * t_flight

    # Clamp al rango aceptado por el sim
    pitch = max(-0.4, min(0.4, pitch))

    return aim_x, aim_z, pitch


def should_use_high_arc(my_y: float, other_y: float, horiz_dist: float) -> bool:
    """Heurística para elegir entre solución directa y arco alto (mortero).

    Si el enemigo está mucho más abajo que yo a media distancia, probablemente
    hay terreno entre medio que bloquearía un disparo directo (apunta abajo y
    choca con la pendiente). El arco alto pasa por encima del relieve.
    """
    dy = other_y - my_y
    # Cuesta abajo pronunciada (>5%) a media-larga distancia → terreno probable
    if horiz_dist > 200 and dy < -0.05 * horiz_dist:
        return True
    # Enemigo bastante abajo (>15m) y NO está al lado mío
    if dy < -15.0 and horiz_dist > 300.0:
        return True
    return False


def estimate_velocity_from_history(history, lookback=5,
                                   tick_dt=SIM_TICK_DT_S):
    """Estima velocidad (vx, vz) desde una deque de posiciones (x, z).

    Devuelve en **m/s** (no por tick), compatible con el nuevo artillery_aim
    que trabaja en SI. Si necesitás m/tick, multiplicá por tick_dt.
    """
    n = len(history)
    if n < 2:
        return 0.0, 0.0
    k = min(lookback, n - 1)
    cur = history[-1]
    prev = history[-1 - k]
    # k ticks separan las dos muestras → tiempo = k * tick_dt segundos
    vx = (cur[0] - prev[0]) / (k * tick_dt)
    vz = (cur[1] - prev[1]) / (k * tick_dt)
    return vx, vz


def estimate_vy_from_history(history_y, lookback=5,
                             tick_dt=SIM_TICK_DT_S):
    """Estima velocidad vertical (vy en m/s) desde una lista/deque de Y.

    Para el lead aim vertical: si el enemigo va cuesta arriba/abajo, su Y
    cambia durante el tiempo de vuelo del proyectil (1-2s). Trackeando vy
    y proyectando, el pitch calculado da en el punto donde estará, no
    donde está.
    """
    n = len(history_y)
    if n < 2:
        return 0.0
    k = min(lookback, n - 1)
    return (history_y[-1] - history_y[-1 - k]) / (k * tick_dt)
