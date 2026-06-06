"""Reward shaping del combate Otter vs Otter.

Función pura (sin estado) para que la usen `env.py` (online) y el script de
training offline. Magnitudes chicas para que la Q-function no explote: |r| ≤ 5
salvo terminales.
"""
import numpy as np
from typing import Tuple


# Coeficientes — exponerlos como constantes para que sean fáciles de retunear.
# Versión vigente desde train_otter_cql.py: incentivo agresivo (0.01 en vez de
# 0.001) y SIN penalty por fire (queremos que aprenda a disparar).
STEP_COST = -0.001
DAMAGE_DEALT_COEF = 0.01
DAMAGE_RECEIVED_COEF = -0.01
FIRE_COST = 0.0           # actualmente desactivado
KILL_BONUS = 5.0
DEATH_PENALTY = -5.0

# Cada vehículo pierde 1 health/tick mientras está SAILING/OFFSHORING. Eso es
# "desgaste natural" que NO viene de daño del enemigo. Descontamos.
NATURAL_DECAY_PER_TICK = 1.0


def compute_step_reward(prev_h_me: float, h_me: float,
                        prev_h_oth: float, h_oth: float,
                        fired: bool) -> Tuple[float, bool]:
    """Devuelve (reward, terminal) para un paso.

    Args:
        prev_h_me: health del agente en t-1
        h_me: health del agente en t
        prev_h_oth: health del oponente en t-1
        h_oth: health del oponente en t
        fired: True si el agente disparó en t

    Returns:
        (reward, terminal) — terminal=True si alguien murió en ese tick.
    """
    r = STEP_COST

    # Diferencia de daño, descontando desgaste natural
    dmg_dealt = max(0.0, (prev_h_oth - h_oth) - NATURAL_DECAY_PER_TICK)
    dmg_received = max(0.0, (prev_h_me - h_me) - NATURAL_DECAY_PER_TICK)
    r += DAMAGE_DEALT_COEF * dmg_dealt + DAMAGE_RECEIVED_COEF * dmg_received

    if fired:
        r += FIRE_COST

    terminal = False
    if h_oth <= 0 and prev_h_oth > 0:
        r += KILL_BONUS
        terminal = True
    if h_me <= 0 and prev_h_me > 0:
        r += DEATH_PENALTY
        terminal = True

    return float(r), terminal


def compute_episode_rewards(h_me_arr: np.ndarray, h_oth_arr: np.ndarray,
                            fired_arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Versión vectorizada para procesar un episodio entero offline.

    Args:
        h_me_arr: shape (T,)
        h_oth_arr: shape (T,)
        fired_arr: shape (T,) bool

    Returns:
        rewards: shape (T,)
        terminals: shape (T,) bool — el último siempre True
    """
    n = len(h_me_arr)
    rewards = np.zeros(n, dtype=np.float32)
    terminals = np.zeros(n, dtype=bool)

    for t in range(n):
        prev_me = h_me_arr[t - 1] if t > 0 else h_me_arr[t]
        prev_oth = h_oth_arr[t - 1] if t > 0 else h_oth_arr[t]
        r, term = compute_step_reward(
            prev_me, h_me_arr[t], prev_oth, h_oth_arr[t], bool(fired_arr[t]),
        )
        rewards[t] = r
        terminals[t] = term

    terminals[-1] = True
    return rewards, terminals
