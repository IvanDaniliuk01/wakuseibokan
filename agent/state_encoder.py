"""State Encoder: convierte ModelRecord crudo en vector de features para la red neural.

Sigue el diseño de la Sección B del documento `Diseño 01 - Espacio de estados y rewards`.

Versión inicial SIMPLIFICADA (~30 floats). Después se va a expandir.
"""
import numpy as np
from collections import deque
from typing import Optional

from . import packet_format as pf

# Constantes del mapa (testcase 131)
MAP_SIZE = 1400.0        # extensión del mapa: [-1400, 1400]
MAX_HEALTH = 1000.0
MAX_POWER = 1000.0
MAX_EPISODE_TICKS = 5000

# Tamaños del vector de observación
OBS_DIM_BASIC = 18       # versión mínima sin warehouses ni LSTM belief
OBS_DIM_FULL = 78        # versión con warehouses + belief enemigo (futura)


class StateEncoder:
    """Encoder POMDP: solo usa info propia del vehículo (lo que tenemos en eval).

    Para versión inicial mantiene historia corta de health y radar.
    No incluye warehouses ni belief LSTM todavía — eso se agrega después.
    """

    def __init__(self, history_size: int = 100):
        self.last_mr: Optional[pf.ModelRecord] = None
        self.health_history: deque = deque(maxlen=history_size)
        self.radar_events: deque = deque(maxlen=history_size)
        self.fire_history: deque = deque(maxlen=history_size)
        self.tick_count = 0

    def reset(self):
        """Llamar al inicio de cada episodio."""
        self.last_mr = None
        self.health_history.clear()
        self.radar_events.clear()
        self.fire_history.clear()
        self.tick_count = 0

    def encode(self, mr: pf.ModelRecord, last_action_fire: bool = False) -> np.ndarray:
        """Convierte un ModelRecord en vector de features.

        Args:
            mr: telemetría cruda del simulador.
            last_action_fire: True si la última acción enviada fue disparo.

        Returns:
            np.ndarray de tamaño OBS_DIM_BASIC, dtype=float32, normalizado.
        """
        feats = []

        # ===== B.1 Self direct (12 floats) =====
        pos = mr.position_array()
        feats.extend(pos / MAP_SIZE)                          # 3: pos normalizada

        R = mr.rotation_matrix_3x3()
        # Cuaternión canonicalizado [w, x, y, z]
        q = _matrix_to_quaternion(R)
        feats.extend(q)                                       # 4: quat

        feats.append(np.clip(mr.health / MAX_HEALTH, -1, 1))  # 1: health
        feats.append(np.clip(mr.power / MAX_POWER, 0, 1))     # 1: power
        feats.append(mr.azimuth / np.pi)                      # 1: azimuth
        feats.append(min(1.0, self.tick_count / MAX_EPISODE_TICKS))  # 1: progress
        feats.append(0.0)  # delta_health placeholder, se llena abajo  # 1: Δhealth

        # ===== B.2 Events (6 floats) =====
        if self.last_mr is not None:
            # Δhealth desde el último tick (positivo si nos dañaron)
            dh = self.last_mr.health - mr.health
            # Restar 1 por desgaste natural en SAILING
            extra_dmg = max(0.0, dh - 1.0)
            feats[-1] = np.clip(extra_dmg / 100.0, 0, 1)

        # Radar
        has_radar = mr.has_radar_event()
        feats.append(float(has_radar))                        # 1: radar_active
        if has_radar:
            self.radar_events.append((self.tick_count, mr.landing_array()))

        # Tiempo desde último radar
        if self.radar_events:
            last_tick, _ = self.radar_events[-1]
            age = self.tick_count - last_tick
            feats.append(min(1.0, age / 100.0))                # 1: radar_age
        else:
            feats.append(1.0)

        # Radar position relativa al Otter en world coords (NO body por ahora)
        if has_radar:
            rel = mr.landing_array() - pos
            feats.extend(rel / 500.0)                          # 3: radar_rel
        else:
            feats.extend([0.0, 0.0, 0.0])

        # Bookkeeping
        self.last_mr = mr
        if last_action_fire:
            self.fire_history.append(self.tick_count)
        self.health_history.append((self.tick_count, mr.health))
        self.tick_count += 1

        arr = np.array(feats, dtype=np.float32)
        assert arr.shape == (OBS_DIM_BASIC,), f"Encoder devolvió {arr.shape}, esperaba {OBS_DIM_BASIC}"
        return arr


def _matrix_to_quaternion(R: np.ndarray) -> np.ndarray:
    """Convierte matriz de rotación 3x3 a cuaternión [w, x, y, z], canonicalizado.

    Implementación equivalente a scipy.spatial.transform.Rotation.from_matrix().as_quat()
    pero sin la dependencia (y reordenando a [w, x, y, z] en vez de [x, y, z, w]).
    """
    trace = R[0, 0] + R[1, 1] + R[2, 2]
    if trace > 0:
        s = 0.5 / np.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (R[2, 1] - R[1, 2]) * s
        y = (R[0, 2] - R[2, 0]) * s
        z = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s

    # Canonicalizar: w >= 0
    if w < 0:
        w, x, y, z = -w, -x, -y, -z
    return np.array([w, x, y, z], dtype=np.float32)


# ============================================================
# Smoke test
# ============================================================
if __name__ == "__main__":
    # Fake ModelRecord para test
    mr = pf.ModelRecord(
        recordtimer=100, lastUpdateTimer=99, number=1,
        health=950.0, power=900, azimuth=0.5,
        landingPos=[100.0, 0.0, -50.0],
        pos=[200.0, 0.0, 300.0],
        rotation=[1, 0, 0, 0,  0, 1, 0, 0,  0, 0, 1, 0],  # identidad
    )
    enc = StateEncoder()
    obs = enc.encode(mr, last_action_fire=False)
    print(f"obs shape: {obs.shape}")
    print(f"obs: {obs}")
    assert obs.shape == (OBS_DIM_BASIC,)
    print("✓ Encoder funcionando")
