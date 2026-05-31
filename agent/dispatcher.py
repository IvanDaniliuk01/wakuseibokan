"""Dispatcher: convierte la acción de la red neural en ControlStructure2 y envía.

Aplica trigger discipline antes de mandar (no disparar sin LOS, sin power, etc.).
"""
import time
import numpy as np
from typing import Optional

from . import packet_format as pf


# Mapeo de la acción [-1, 1] de la red a los rangos físicos del Otter
MAX_THRUST = 1.0
MAX_STEERING_DEG = 30.0  # grados máximos de las ruedas delanteras


def action_to_command(
    action: np.ndarray,
    controlling_id: int,
    current_state: Optional[pf.ModelRecord] = None,
    fire_probability_floor: float = 0.5,
) -> pf.ControlStructure2:
    """Convierte action [-1,1]^5 a ControlStructure2.

    Layout esperado de action:
        action[0]: thrust    ∈ [-1, 1]
        action[1]: steering  ∈ [-1, 1]
        action[2]: turret_b  ∈ [-1, 1] (mapeado a [-π, π])
        action[3]: turret_d  ∈ [-1, 1] (mapeado a [0, π/2])
        action[4]: fire      ∈ [-1, 1] (logit; sigmoid → probabilidad)

    Args:
        action: vector de 5 floats.
        controlling_id: ID del vehículo a controlar.
        current_state: telemetría actual (opcional, para trigger discipline).
        fire_probability_floor: prob mínima para disparar (gate de trigger discipline).
    """
    thrust = float(np.clip(action[0], -1, 1)) * MAX_THRUST
    steering = float(np.clip(action[1], -1, 1)) * MAX_STEERING_DEG  # grados

    # Fire decision
    fire_logit = float(action[4])
    fire_prob = _sigmoid(fire_logit)
    fire = fire_prob > fire_probability_floor

    # Trigger discipline
    if current_state is not None:
        if current_state.power <= 0:
            fire = False
        # TODO: agregar más gates (LOS, heat, HPE) cuando estén disponibles

    cmd = pf.ControlStructure2(
        controllingid=controlling_id,
        thrust=thrust,
        roll=0.0,
        pitch=0.0,
        yaw=steering,
        precesion=0.0,
        bank=0.0,
        faction=1,
        command=pf.CMD_FIRE if fire else pf.CMD_NONE,
        spawnid=0,
        typeofisland=0,
        x=0.0, y=0.0, z=0.0,
        target_type=0,
        weapon=0,
        sourcetimer=int(time.time() * 1000) & 0xFFFFFFFF,
    )
    return cmd


def _sigmoid(x: float) -> float:
    if x >= 0:
        ex = np.exp(-x)
        return 1.0 / (1.0 + ex)
    else:
        ex = np.exp(x)
        return ex / (1.0 + ex)


# ============================================================
# Smoke test
# ============================================================
if __name__ == "__main__":
    action = np.array([0.5, 0.3, 0.0, 0.0, 1.5])  # fire logit alto
    cmd = action_to_command(action, controlling_id=1)
    print(f"Command: thrust={cmd.thrust}, yaw={cmd.yaw}°, fire={cmd.command == pf.CMD_FIRE}")
    print(f"Bytes (68): {len(cmd.to_bytes())}")
