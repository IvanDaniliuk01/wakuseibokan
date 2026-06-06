"""Smoke tests del env.py que NO requieren simulador corriendo.

Solo testea la parte estática: spaces, encoders, reward. Para tests que
necesitan sim real, ver el bloque __main__ al final (correr manualmente).
"""
import numpy as np

from agent.env import OtterEnv
from agent.encoders import OBS_DIM, ACT_DIM, encode_action, decode_action
from agent import packet_format as pf


def test_action_observation_spaces():
    """Validar las definiciones de spaces sin necesidad de sim."""
    # No llamamos a reset(), solo inspeccionamos el constructor.
    env = OtterEnv(difficulty="easy", reset_mode="soft")
    assert env.observation_space.shape == (OBS_DIM,)
    assert env.action_space.shape == (ACT_DIM,)
    assert env.observation_space.dtype == np.float32
    assert env.action_space.dtype == np.float32
    # Sampleo dentro de bounds
    a = env.action_space.sample()
    assert a.shape == (ACT_DIM,)
    assert np.all(a >= -1.0) and np.all(a <= 1.0)


def test_encode_decode_action_roundtrip():
    """encode_action(decode_action) preserva la acción modulo el formato sim."""
    fake_model = pf.ModelRecord(
        recordtimer=100, lastUpdateTimer=100, number=1,
        health=1000.0, power=1000, azimuth=0.0,
        landingPos=[0.0, 0.0, 0.0],
        pos=[0.0, 0.0, 0.0],
        rotation=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
    )

    # Acción "humana"
    thrust, steering, td, tb_deg, fire = 5.0, 0.5, 0.2, 45.0, True
    enc = encode_action(thrust, steering, td, tb_deg, fire)
    assert enc.shape == (ACT_DIM,)

    # Decodear de vuelta → ControlStructure2
    cmd = decode_action(enc, fake_model)
    assert abs(cmd.thrust - thrust) < 0.01
    assert abs(cmd.roll - steering) < 0.01
    assert abs(cmd.pitch - td) < 0.01
    # Bearing tiene roundtrip por cos/sin
    assert abs(cmd.precesion - tb_deg) < 1.0
    assert cmd.command == pf.CMD_FIRE


def test_decode_action_clips_input():
    """Acciones fuera de [-1, 1] se clampean."""
    fake_model = pf.ModelRecord(
        recordtimer=0, lastUpdateTimer=0, number=1,
        health=1000.0, power=1000, azimuth=0.0,
        landingPos=[0.0, 0.0, 0.0],
        pos=[0.0, 0.0, 0.0],
        rotation=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
    )
    out_of_range = np.array([5.0, -3.0, 7.0, 0.5, 0.5, 1.0], dtype=np.float32)
    cmd = decode_action(out_of_range, fake_model)
    from agent.encoders import THRUST_MAX
    assert -THRUST_MAX - 0.01 <= cmd.thrust <= THRUST_MAX + 0.01
    assert -1.01 <= cmd.roll <= 1.01
    assert -0.41 <= cmd.pitch <= 0.41


def test_reward_module():
    """compute_step_reward responde a daño y muertes."""
    from agent.reward import compute_step_reward, KILL_BONUS, DEATH_PENALTY

    # Sin cambios: solo step cost
    r, term = compute_step_reward(1000, 999, 1000, 999, fired=False)
    assert term is False
    # 999-1000=-1 = solo desgaste natural, dmg neto = 0
    # r ≈ STEP_COST = -0.001
    assert -0.002 < r < 0

    # Daño dealt extra
    r, term = compute_step_reward(1000, 999, 1000, 800, fired=False)
    assert term is False
    assert r > 0  # ganamos por dañar al enemigo

    # Muerte enemigo
    r, term = compute_step_reward(1000, 999, 100, 0, fired=True)
    assert term is True
    assert r > KILL_BONUS * 0.9

    # Nuestra muerte
    r, term = compute_step_reward(100, 0, 999, 998, fired=False)
    assert term is True
    assert r < DEATH_PENALTY * 0.9
