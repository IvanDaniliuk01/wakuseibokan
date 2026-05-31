"""Script de entrenamiento offline RL para Google Colab.

Este archivo está estructurado en CELDAS marcadas con '# %%' para que se pueda
ejecutar en Colab célula por célula. También se puede correr como script Python.

USO EN COLAB:
1. Subir este archivo a Colab (o pegar el contenido en celdas)
2. Subir el dataset HDF5 a Drive
3. Ejecutar celda por celda
4. Descargar el modelo entrenado al final

WORKFLOW:
- Recolectás el dataset LOCALMENTE con `python -m agent.collect ...`
- Subís el .h5 a Drive
- Corres este notebook en Colab con GPU T4
- Bajás el modelo .pt o .zip
- Lo cargás localmente con `eval.py` o `inference.py`
"""

# %% Celda 1: Setup
# !pip install -q stable-baselines3[extra] d3rlpy h5py
# !pip install -q torch torchvision  # Colab ya lo tiene pero por las dudas

import os
import numpy as np
import torch
import h5py
from pathlib import Path

print(f"PyTorch: {torch.__version__}")
print(f"CUDA disponible: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")


# %% Celda 2: Mount Drive (solo en Colab)
# from google.colab import drive
# drive.mount('/content/drive')
# DATASET_PATH = "/content/drive/MyDrive/wakuseibokan/dataset_v1.h5"
# OUTPUT_DIR = "/content/drive/MyDrive/wakuseibokan/models/"

# Si corres local (sin Drive):
DATASET_PATH = "data/dataset_v1.h5"
OUTPUT_DIR = "models/"

Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)


# %% Celda 3: Cargar dataset
def load_hdf5_dataset(path):
    """Carga dataset HDF5 en formato d3rlpy."""
    with h5py.File(path, "r") as f:
        data = {
            "observations": f["observations"][:],
            "actions": f["actions"][:],
            "rewards": f["rewards"][:],
            "terminals": f["terminals"][:],
        }
        # next_observations también
        if "next_observations" in f:
            data["next_observations"] = f["next_observations"][:]
        # Metadata
        meta = dict(f.attrs)
    return data, meta


data, meta = load_hdf5_dataset(DATASET_PATH)
print(f"Dataset cargado: {meta}")
print(f"  observations: {data['observations'].shape}")
print(f"  actions: {data['actions'].shape}")
print(f"  rewards: {data['rewards'].shape}")
print(f"  reward stats: mean={data['rewards'].mean():.3f}, "
      f"std={data['rewards'].std():.3f}, min={data['rewards'].min():.1f}, "
      f"max={data['rewards'].max():.1f}")


# %% Celda 4: Entrenamiento con d3rlpy (offline RL)
# d3rlpy es la librería más madura para offline RL en Python
# Implementa CQL, IQL, AWAC, BC, BCQ, etc.

from d3rlpy.dataset import MDPDataset
from d3rlpy.algos import CQLConfig

# Construir MDPDataset
mdp_dataset = MDPDataset(
    observations=data["observations"],
    actions=data["actions"],
    rewards=data["rewards"],
    terminals=data["terminals"],
)
print(f"MDPDataset: {len(mdp_dataset)} transiciones, "
      f"{mdp_dataset.size()} episodios")


# %% Celda 5: Configurar y entrenar CQL
# CQL = Conservative Q-Learning, ideal para offline RL
# Es una variante de SAC que penaliza Q-values en acciones fuera de distribución

cql_config = CQLConfig(
    actor_learning_rate=3e-4,
    critic_learning_rate=3e-4,
    temp_learning_rate=3e-4,
    batch_size=256,
    gamma=0.99,
    tau=0.005,
    n_critics=2,
    initial_temperature=1.0,
    initial_alpha=1.0,
    alpha_threshold=10.0,
    conservative_weight=5.0,  # peso de la regularización CQL
    n_action_samples=10,
)

cql = cql_config.create(device="cuda:0" if torch.cuda.is_available() else "cpu:0")

# Entrenamiento
N_STEPS = 500_000
EVAL_INTERVAL = 10_000
SAVE_INTERVAL = 50_000

print(f"Entrenando CQL por {N_STEPS} pasos...")
cql.fit(
    mdp_dataset,
    n_steps=N_STEPS,
    n_steps_per_epoch=EVAL_INTERVAL,
    save_interval=SAVE_INTERVAL,
    experiment_name="otter_cql_v1",
)


# %% Celda 6: Guardar el modelo
model_path = os.path.join(OUTPUT_DIR, "otter_cql_v1.d3")
cql.save_model(model_path)
print(f"✓ Modelo guardado en: {model_path}")

# Convertir a formato portable (PyTorch state_dict)
import torch
torch.save({
    "policy_state_dict": cql.impl.policy.state_dict() if cql.impl else None,
    "config": cql_config.__dict__,
    "obs_dim": data["observations"].shape[1],
    "action_dim": data["actions"].shape[1],
}, os.path.join(OUTPUT_DIR, "otter_cql_v1.pt"))

print(f"✓ State dict guardado en: {OUTPUT_DIR}otter_cql_v1.pt")


# %% Celda 7: Descargar a tu máquina local (Colab)
# from google.colab import files
# files.download(os.path.join(OUTPUT_DIR, "otter_cql_v1.pt"))


# %% Celda 8 (opcional): Entrenamiento alternativo con stable-baselines3 SAC online
# Si lográs compilar Wakuseibokan en Colab (con flags -mute -nointro -headless),
# podés entrenar SAC online en vez de CQL offline.
# Pero compilar OpenGL/X11 en Colab es delicado. Mejor mantener offline RL.

# from stable_baselines3 import SAC
# import sys
# sys.path.append("/content/drive/MyDrive/wakuseibokan")
# from agent.env import WakuseibokanEnv
# env = WakuseibokanEnv()  # ← requiere el simulador corriendo, complicado en Colab
# model = SAC("MlpPolicy", env, ...)
# model.learn(total_timesteps=1_000_000)
