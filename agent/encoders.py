"""Encoders de estado y decoders de acción para el agente.

Single source of truth: tanto env.py (online) como train_otter_cql.py (offline)
y eval.py usan estas funciones, así que el formato es idéntico en training y
deployment.
"""
import math
import numpy as np

from . import packet_format as pf


# Constantes de normalización
POS_SCALE = 2000.0
Y_SCALE = 200.0   # Y va aprox 0-200m con relieve del sim
ACT_DIM = 6

# Dos encoders disponibles:
#   - simple (OBS_DIM=12):  el clásico. Pos x/z + heading + health + bearing.
#                           NO ve altura (Y) ni rotación completa.
#   - full   (OBS_DIM_FULL=44): TODA la telemetría del UDP. Por vehículo:
#                           pos xyz (3) + rotation 3x3 (9) + cos/sin azimuth (2) +
#                           health (1) + power (1) + landingPos relativo (3) = 19.
#                           Más relativos: dx/dy/dz (3) + dist (1) + bearing (2) = 6.
#                           Total: 19*2 + 6 = 44.
OBS_DIM = 12
OBS_DIM_FULL = 44

# Límites de acción decodificada.
# THRUST_MAX subido a 50 empíricamente: el sim Otter no clampa (Vehicle.cpp:406)
# y el torque max de las wheels permite velocidades mayores. Con 10 el Otter
# se siente muy lento. Ver agent/docs/05-thrust-max.md.
THRUST_MAX = 50.0
TURRET_DECL_MAX = 0.4


def encode_state(my_mr: pf.ModelRecord, other_mr: pf.ModelRecord) -> np.ndarray:
    """12 features: mi pos norm + cos/sin azimuth + health + power +
    delta pos al enemigo + distancia + cos/sin bearing relativo + health enemigo.

    Asume que my_mr y other_mr son ModelRecord parseados. Las posiciones del
    sim están en (x, y, z) con y=altura — usamos x, z para el plano horizontal.
    """
    pos_me = my_mr.pos
    pos_oth = other_mr.pos
    az_me = float(my_mr.azimuth)
    h_me = float(my_mr.health)
    p_me = float(my_mr.power)
    h_oth = float(other_mr.health)

    dx = float(pos_oth[0]) - float(pos_me[0])
    dz = float(pos_oth[2]) - float(pos_me[2])
    dist = math.sqrt(dx * dx + dz * dz)
    bearing_world = math.atan2(dz, dx)
    bearing_rel = bearing_world - az_me * math.pi / 180.0

    return np.array([
        float(pos_me[0]) / POS_SCALE,
        float(pos_me[2]) / POS_SCALE,
        math.cos(az_me * math.pi / 180.0),
        math.sin(az_me * math.pi / 180.0),
        max(-1.0, min(1.5, h_me / 1000.0)),
        max(0.0, min(1.5, p_me / 1000.0)),
        dx / POS_SCALE,
        dz / POS_SCALE,
        max(0.0, min(3.0, dist / POS_SCALE)),
        math.cos(bearing_rel),
        math.sin(bearing_rel),
        max(-1.0, min(1.5, h_oth / 1000.0)),
    ], dtype=np.float32)


def encode_state_from_arrays(pos_me, az_me_deg, h_me, p_me,
                             pos_oth, h_oth) -> np.ndarray:
    """Versión que toma arrays sueltos en vez de ModelRecord.

    Útil para encoding offline desde HDF5, donde los datos vienen como columnas.
    """
    az_rad = float(az_me_deg) * math.pi / 180.0
    dx = float(pos_oth[0]) - float(pos_me[0])
    dz = float(pos_oth[2]) - float(pos_me[2])
    dist = math.sqrt(dx * dx + dz * dz)
    bearing_world = math.atan2(dz, dx)
    bearing_rel = bearing_world - az_rad

    return np.array([
        float(pos_me[0]) / POS_SCALE,
        float(pos_me[2]) / POS_SCALE,
        math.cos(az_rad),
        math.sin(az_rad),
        max(-1.0, min(1.5, float(h_me) / 1000.0)),
        max(0.0, min(1.5, float(p_me) / 1000.0)),
        dx / POS_SCALE,
        dz / POS_SCALE,
        max(0.0, min(3.0, dist / POS_SCALE)),
        math.cos(bearing_rel),
        math.sin(bearing_rel),
        max(-1.0, min(1.5, float(h_oth) / 1000.0)),
    ], dtype=np.float32)


# ============================================================
# ENCODER FULL: usa TODA la telemetría del UDP (44 features)
# ============================================================

def _rotation_3x3_from_12(rot12) -> np.ndarray:
    """Extrae la 3x3 real del array de 12 floats (índices 3, 7, 11 son padding)."""
    r = rot12
    return np.array([r[0], r[1], r[2], r[4], r[5], r[6], r[8], r[9], r[10]],
                    dtype=np.float32)


def encode_state_full(my_mr: pf.ModelRecord, other_mr: pf.ModelRecord) -> np.ndarray:
    """Encoder ampliado: 44 features con TODA la telemetría disponible.

    Esquema:
        [0:3]   mi pos (x, y, z) normalizada
        [3:12]  mi rotation matrix 3x3 (9 floats, ya en [-1,1])
        [12:14] mi cos/sin(azimuth)
        [14]    mi health/1000
        [15]    mi power/1000
        [16:19] mi landingPos relativo a mi pos (x,y,z) — info del último impacto
        [19:22] pos enemigo (x, y, z) normalizada
        [22:31] enemigo rotation matrix 3x3
        [31:33] enemigo cos/sin(azimuth)
        [33]    enemigo health/1000
        [34]    enemigo power/1000
        [35:38] enemigo landingPos relativo a mi pos
        [38:41] delta pos enemigo - mi pos (dx, dy, dz)
        [41]    distancia horizontal
        [42:44] cos/sin(bearing relativo)
    """
    return encode_state_full_from_arrays(
        pos_me=my_mr.pos, rot_me=my_mr.rotation, az_me_deg=float(my_mr.azimuth),
        h_me=float(my_mr.health), p_me=float(my_mr.power),
        land_me=my_mr.landingPos,
        pos_oth=other_mr.pos, rot_oth=other_mr.rotation,
        az_oth_deg=float(other_mr.azimuth),
        h_oth=float(other_mr.health), p_oth=float(other_mr.power),
        land_oth=other_mr.landingPos,
    )


def _safe_landing_rel(land_pos, my_pos) -> np.ndarray:
    """LandingPos relativo a my_pos con saneo defensivo.

    El sim deja landingPos sin inicializar antes del primer disparo, mandando
    valores arbitrarios (NaN, Inf, o memoria basura > 10^30). Si detectamos
    eso, devolvemos rel=0 (= "landing en mi posición actual" = no info útil).
    """
    lx = float(land_pos[0]); ly = float(land_pos[1]); lz = float(land_pos[2])
    # Si cualquier componente es no-finito o absurdamente grande, ignorar
    if (not (math.isfinite(lx) and math.isfinite(ly) and math.isfinite(lz))
            or abs(lx) > 1e6 or abs(ly) > 1e6 or abs(lz) > 1e6):
        return np.zeros(3, dtype=np.float32)
    return np.array([
        (lx - float(my_pos[0])) / POS_SCALE,
        (ly - float(my_pos[1])) / Y_SCALE,
        (lz - float(my_pos[2])) / POS_SCALE,
    ], dtype=np.float32)


def encode_state_full_from_arrays(pos_me, rot_me, az_me_deg, h_me, p_me, land_me,
                                  pos_oth, rot_oth, az_oth_deg, h_oth, p_oth,
                                  land_oth) -> np.ndarray:
    """Versión con arrays sueltos (para load desde HDF5 sin ModelRecord)."""
    az_me_rad = float(az_me_deg) * math.pi / 180.0
    az_oth_rad = float(az_oth_deg) * math.pi / 180.0

    # Deltas
    dx = float(pos_oth[0]) - float(pos_me[0])
    dy = float(pos_oth[1]) - float(pos_me[1])
    dz = float(pos_oth[2]) - float(pos_me[2])
    dist_xz = math.sqrt(dx * dx + dz * dz)
    bearing_world = math.atan2(dz, dx)
    bearing_rel = bearing_world - az_me_rad

    # Rotaciones (extraer 9 valores reales de los 12)
    R_me = _rotation_3x3_from_12(rot_me)
    R_oth = _rotation_3x3_from_12(rot_oth)

    # LandingPos relativo a mi pos (info de "donde aterrizó el último tiro")
    # IMPORTANTE: el sim manda NaN o valores absurdos (memoria basura, |v|>10^30)
    # antes del primer disparo. Sanitizar: si es NaN/Inf o módulo gigante,
    # reemplazar por la propia pos (rel = 0). Sin esto el training da loss=NaN.
    land_me_rel = _safe_landing_rel(land_me, pos_me)
    land_oth_rel = _safe_landing_rel(land_oth, pos_me)

    return np.concatenate([
        # Mi info (0:19)
        np.array([
            float(pos_me[0]) / POS_SCALE,
            float(pos_me[1]) / Y_SCALE,
            float(pos_me[2]) / POS_SCALE,
        ], dtype=np.float32),                # 3
        R_me,                                # 9
        np.array([math.cos(az_me_rad), math.sin(az_me_rad)], dtype=np.float32),  # 2
        np.array([
            max(-1.0, min(1.5, float(h_me) / 1000.0)),
            max(0.0, min(1.5, float(p_me) / 1000.0)),
        ], dtype=np.float32),                # 2
        land_me_rel,                         # 3
        # Info enemigo (19:38)
        np.array([
            float(pos_oth[0]) / POS_SCALE,
            float(pos_oth[1]) / Y_SCALE,
            float(pos_oth[2]) / POS_SCALE,
        ], dtype=np.float32),                # 3
        R_oth,                               # 9
        np.array([math.cos(az_oth_rad), math.sin(az_oth_rad)], dtype=np.float32),  # 2
        np.array([
            max(-1.0, min(1.5, float(h_oth) / 1000.0)),
            max(0.0, min(1.5, float(p_oth) / 1000.0)),
        ], dtype=np.float32),                # 2
        land_oth_rel,                        # 3
        # Relativos (38:44)
        np.array([
            dx / POS_SCALE,
            dy / Y_SCALE,
            dz / POS_SCALE,
            max(0.0, min(3.0, dist_xz / POS_SCALE)),
            math.cos(bearing_rel),
            math.sin(bearing_rel),
        ], dtype=np.float32),                # 6
    ]).astype(np.float32)


def encode_action(thrust: float, steering: float, turret_decl: float,
                  turret_bearing_deg: float, fire: bool) -> np.ndarray:
    """De acción "humana" (unidades del simulador) a vector 6D en [-1, 1]."""
    tb_rad = float(turret_bearing_deg) * math.pi / 180.0
    return np.array([
        max(-1.0, min(1.0, float(thrust) / THRUST_MAX)),
        max(-1.0, min(1.0, float(steering))),
        max(-1.0, min(1.0, float(turret_decl) / TURRET_DECL_MAX)),
        math.cos(tb_rad),
        math.sin(tb_rad),
        1.0 if fire else -1.0,
    ], dtype=np.float32)


def decode_action(action_vec: np.ndarray, my_mr: pf.ModelRecord) -> pf.ControlStructure2:
    """Vector 6D en [-1, 1] → ControlStructure2 listo para enviar por UDP.

    action[0]: thrust / 10   → thrust en [-10, 10]
    action[1]: steering      → roll en [-1, 1]
    action[2]: turret_decl   → pitch en [-0.4, 0.4]
    action[3]: cos(turret_bearing)
    action[4]: sin(turret_bearing) → precesion en deg
    action[5]: fire (>0 → disparar)

    `sourcetimer` se setea con `my_mr.recordtimer` para respetar el check del
    sim de comandos antiguos (testcase_131.cpp:405).
    """
    a = np.asarray(action_vec, dtype=np.float32)
    thrust = float(np.clip(a[0], -1.0, 1.0)) * THRUST_MAX
    steering = float(np.clip(a[1], -1.0, 1.0))
    decl = float(np.clip(a[2], -1.0, 1.0)) * TURRET_DECL_MAX
    tb_deg = math.atan2(float(a[4]), float(a[3])) * 180.0 / math.pi
    fire = bool(a[5] > 0)

    return pf.ControlStructure2(
        controllingid=my_mr.number,
        thrust=thrust,
        roll=steering,
        pitch=decl,
        yaw=0.0,
        precesion=float(tb_deg),
        bank=0.0,
        faction=my_mr.number,
        command=pf.CMD_FIRE if fire else pf.CMD_NONE,
        sourcetimer=int(my_mr.recordtimer) & 0xFFFFFFFF,
    )


def build_command(vid: int, thrust: float, steering: float,
                  turret_decl: float, turret_bearing_deg: float,
                  fire: bool, sim_timer: int) -> pf.ControlStructure2:
    """Helper directo para construir un ControlStructure2 desde la política scripted.

    Lo usan observe.py / collect_vs_cheater.py (políticas que ya producen
    valores en unidades del simulador, sin pasar por el encoding [-1,1]).
    """
    return pf.ControlStructure2(
        controllingid=vid,
        thrust=float(thrust),
        roll=float(steering),
        pitch=float(turret_decl),
        yaw=0.0,
        precesion=float(turret_bearing_deg),
        bank=0.0,
        faction=vid,
        command=pf.CMD_FIRE if fire else pf.CMD_NONE,
        sourcetimer=int(sim_timer) & 0xFFFFFFFF,
    )
