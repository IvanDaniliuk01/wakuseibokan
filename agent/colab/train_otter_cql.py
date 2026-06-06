"""Entrenamiento Offline RL del Otter con CQL — Colab T4.

Carga el dataset HDF5 generado por `agent/observe.py` (formato por episodios con
telemetría completa + log de acciones), construye el MDP (s, a, r, s', done) y
entrena un agente CQL con d3rlpy.

USO EN COLAB:
1. Subir `dataset_v1.h5` a Drive: `MyDrive/wakuseibokan/dataset_v1.h5`
2. File → Upload notebook → train_otter_cql.ipynb
3. Runtime → Change runtime type → GPU T4
4. Ejecutar las celdas en orden (Shift+Enter) o Runtime → Run all
"""

# %% ---------- Celda 1: Setup ----------
# !pip install -q d3rlpy h5py
import os
import numpy as np
import h5py
import torch
from pathlib import Path
from typing import Dict, List, Tuple

print(f"PyTorch: {torch.__version__}")
print(f"CUDA: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")

DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu:0"


# %% ---------- Celda 2: Paths ----------
# En Colab descomentá las 4 líneas siguientes:
# from google.colab import drive
# drive.mount('/content/drive')
# DATASET_PATH = "/content/drive/MyDrive/wakuseibokan/dataset_v1.h5"
# OUTPUT_DIR  = "/content/drive/MyDrive/wakuseibokan/models/"

# Para correr local (smoke test):
DATASET_PATH = "data/dataset_v2.h5"
OUTPUT_DIR = "models/"

Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)


# %% ---------- Celda 3: TODAS las funciones helper (consolidado) ----------
# Encoders y reward los importamos desde agent/ (single source of truth con env.py).
# En Colab montar el repo o subir agent/ a sys.path antes de esta celda.

import sys
sys.path.insert(0, "..")  # ajustá según donde montés el repo en Colab

from agent.encoders import (
    OBS_DIM, ACT_DIM, POS_SCALE,
    encode_state_from_arrays, encode_action as _encode_action_human,
)
from agent.reward import compute_episode_rewards


def load_episodes(path: str) -> Tuple[List[Dict], Dict]:
    """Carga episodios desde HDF5 con telemetría completa + log de acciones."""
    episodes = []
    with h5py.File(path, "r") as f:
        for name in sorted(f.keys()):
            g = f[name]
            ep = {k: g[k][:] for k in g.keys()}
            ep["_attrs"] = dict(g.attrs)
            episodes.append(ep)
        meta = dict(f.attrs)
    return episodes, meta


def encode_state(my_idx: int, other_idx: int, ep: Dict, t: int) -> np.ndarray:
    """Wrapper sobre encoders.encode_state_from_arrays para encoding offline."""
    return encode_state_from_arrays(
        pos_me=ep["pos"][t, my_idx],
        az_me_deg=float(ep["azimuth"][t, my_idx]),
        h_me=float(ep["health"][t, my_idx]),
        p_me=float(ep["power"][t, my_idx]),
        pos_oth=ep["pos"][t, other_idx],
        h_oth=float(ep["health"][t, other_idx]),
    )


def encode_action(ep: Dict, t: int) -> np.ndarray:
    """6 dims continuas en [-1, 1]: thrust, steering, turret_decl, cos+sin bearing, fire."""
    return _encode_action_human(
        thrust=float(ep["act_thrust"][t]),
        steering=float(ep["act_steering"][t]),
        turret_decl=float(ep["act_turret_decl"][t]),
        turret_bearing_deg=float(ep["act_turret_bearing"][t]),
        fire=bool(ep["act_fire"][t]),
    )


def compute_rewards_and_terminals(my_idx: int, other_idx: int,
                                   ep: Dict) -> Tuple[np.ndarray, np.ndarray]:
    """Wrapper sobre agent.reward.compute_episode_rewards.

    Magnitudes chicas (|r| ≤ 5) para que la Q-function no explote.
    """
    return compute_episode_rewards(
        h_me_arr=ep["health"][:, my_idx].astype(np.float32),
        h_oth_arr=ep["health"][:, other_idx].astype(np.float32),
        fired_arr=ep["act_fire"].astype(bool),
    )


def build_mdp_arrays(episodes: List[Dict], controlled_vid: int = 1):
    """Aplana episodios a (obs, actions, rewards, terminals)."""
    all_obs, all_act, all_rew, all_term = [], [], [], []

    for ep in episodes:
        vids = list(ep["vehicle_ids"])
        if controlled_vid not in vids:
            continue
        my_idx = vids.index(controlled_vid)
        if len(vids) == 2:
            other_idx = 1 - my_idx
        else:
            others = [v for v in vids if v != controlled_vid]
            other_idx = vids.index(others[0])

        n = ep["pos"].shape[0]
        n_act = len(ep["act_thrust"])
        usable = min(n, n_act)
        if usable < 2:
            continue

        rewards, terminals = compute_rewards_and_terminals(my_idx, other_idx, ep)

        for t in range(usable):
            all_obs.append(encode_state(my_idx, other_idx, ep, t))
            all_act.append(encode_action(ep, t))
            all_rew.append(rewards[t])
            all_term.append(terminals[t])

    obs_arr  = np.stack(all_obs).astype(np.float32)
    act_arr  = np.stack(all_act).astype(np.float32)
    rew_arr  = np.array(all_rew, dtype=np.float32)
    term_arr = np.array(all_term, dtype=bool)
    return obs_arr, act_arr, rew_arr, term_arr


print("✓ Helpers definidos: load_episodes, encode_state, encode_action, "
      "compute_rewards_and_terminals, build_mdp_arrays")


# %% ---------- Celda 4: Cargar dataset + construir MDP ----------
episodes, meta = load_episodes(DATASET_PATH)
print(f"Cargados {len(episodes)} episodios. Meta: {meta}")
for i, ep in enumerate(episodes[:3]):
    print(f"  Ep {i}: {ep['_attrs'].get('n_ticks', '?')} ticks, "
          f"vehicles={list(ep['vehicle_ids'])}, "
          f"dist_fire={ep['_attrs'].get('params_dist_fire', '?'):.0f}m, "
          f"final_health={ep['health'][-1]}")

obs, actions, rewards, terminals = build_mdp_arrays(episodes, controlled_vid=1)
print(f"\nTransiciones totales: {len(obs)}")
print(f"  obs: {obs.shape}  actions: {actions.shape}")
print(f"  rewards: mean={rewards.mean():.3f} min={rewards.min():.1f} max={rewards.max():.1f}")
print(f"  terminals: {terminals.sum()}")

from d3rlpy.dataset import MDPDataset
mdp = MDPDataset(observations=obs, actions=actions, rewards=rewards, terminals=terminals)
print(f"MDPDataset construido: {len(mdp.episodes)} episodios")


# %% ---------- Celda 5: Entrenar CQL ----------
from d3rlpy.algos import CQLConfig

cql_config = CQLConfig(
    actor_learning_rate=1e-4,         # bajado de 3e-4 para estabilidad
    critic_learning_rate=1e-4,
    temp_learning_rate=1e-4,
    batch_size=256,
    gamma=0.95,                       # bajado de 0.99 → menos peso al futuro lejano
    tau=0.005,
    n_critics=2,
    initial_temperature=1.0,
    initial_alpha=1.0,
    alpha_threshold=10.0,
    conservative_weight=1.0,          # bajado de 5.0 → CQL menos agresivo
    n_action_samples=10,
)
cql = cql_config.create(device=DEVICE)

# 50k pasos para smoke test con dataset chico. Subir a 200k–500k después.
N_STEPS = 50_000
N_STEPS_PER_EPOCH = 5_000

print(f"Entrenando CQL por {N_STEPS} pasos ({N_STEPS // N_STEPS_PER_EPOCH} épocas)...")
cql.fit(
    mdp,
    n_steps=N_STEPS,
    n_steps_per_epoch=N_STEPS_PER_EPOCH,
    save_interval=10,
    experiment_name="otter_cql_v1",
)


# %% ---------- Celda 6: Guardar modelo ----------
out_d3 = os.path.join(OUTPUT_DIR, "otter_cql_v1.d3")
out_pt = os.path.join(OUTPUT_DIR, "otter_cql_v1.pt")
cql.save_model(out_d3)
print(f"✓ Modelo d3rlpy: {out_d3}")

torch.save({
    "policy_state_dict": cql.impl.policy.state_dict() if cql.impl else None,
    "obs_dim": OBS_DIM,
    "action_dim": ACT_DIM,
    "config": {k: v for k, v in cql_config.__dict__.items()
               if isinstance(v, (int, float, str, bool))},
}, out_pt)
print(f"✓ State dict PyTorch: {out_pt}")

# Descargar (Colab):
# from google.colab import files
# files.download(out_pt)
