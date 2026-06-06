"""Entrenamiento Behavioral Cloning del Otter.

Toma un dataset HDF5 (formato de collect_vs_cheater) donde el Otter 1 fue
controlado por un experto (PREDATOR_V2) y entrena una red MLP a predecir
las acciones del experto dado el estado.

Setup:
- Estado: 12 features (encoders.encode_state_from_arrays)
- Acción: 6 features [thrust/50, steering, td/0.4, cos(tb), sin(tb), fire±1]
- Red:    MLP 12 → 128 → 128 → 6
- Loss:   MSE para outputs continuos + BCE para fire
- Optim:  Adam lr=3e-4, batch=256

USO:
    python -m agent.train_bc \\
        --dataset data/train/bc_predator_v2_mixed_250.h5 \\
        --output  models/bc_otter.pt \\
        --epochs  20

Para Colab GPU: subir el .h5 a Drive, modificar paths arriba en if __name__.
"""
import argparse
import math
import time
from pathlib import Path
from typing import Tuple

import h5py
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from .encoders import (
    OBS_DIM, OBS_DIM_FULL, ACT_DIM, THRUST_MAX, TURRET_DECL_MAX,
    encode_state_from_arrays, encode_state_full_from_arrays,
)


# ============================================================
# Dataset loader: HDF5 → tensores (obs, act)
# ============================================================

def encode_action_arrays(thrust, steering, turret_decl, turret_bearing_deg, fire,
                          target_mode: str = "full"):
    """Vector idem encoders.encode_action pero vectorizado para batch.

    target_mode:
        "full":     6 outputs [thrust, steering, td, cos(tb), sin(tb), fire]
        "movement": 2 outputs [thrust, steering] — el resto lo aporta el
                    cheater scripted en eval. Útil cuando el dataset no tiene
                    señal de aim/fire (eps con pocos disparos), pero sí señal
                    de posicionamiento/esquive.
    """
    if target_mode == "movement":
        return np.stack([
            np.clip(thrust / THRUST_MAX, -1.0, 1.0),
            np.clip(steering, -1.0, 1.0),
        ], axis=-1).astype(np.float32)
    tb_rad = turret_bearing_deg * math.pi / 180.0
    return np.stack([
        np.clip(thrust / THRUST_MAX, -1.0, 1.0),
        np.clip(steering, -1.0, 1.0),
        np.clip(turret_decl / TURRET_DECL_MAX, -1.0, 1.0),
        np.cos(tb_rad),
        np.sin(tb_rad),
        np.where(fire, 1.0, -1.0),
    ], axis=-1).astype(np.float32)


# Modos del cheater_policy considerados "combate real" (vs escape/recovery).
# Ver _MODE_TO_INT en collect_vs_cheater.py.
COMBAT_MODE_INTS = {10, 15, 16, 17, 18, 19}  # engage, bait, chaos, too_close, jiggle, swerve_burst
# Modos "escape/recovery" — no combate. Útil para diagnóstico.
ESCAPE_MODE_INTS = {13, 20, 21, 22}  # recovery, escape_rotate, escape_advance, water_guard


def load_dataset(paths, min_dist_filter: float = 1500.0,
                 min_ticks: int = 50,
                 encoder: str = "full",
                 target_mode: str = "full",
                 upsample_combat: int = 1) -> Tuple[torch.Tensor, torch.Tensor, dict]:
    """Carga 1 o más HDF5 → (obs[N,D], act[N,K], metadata).

    Args:
        paths: str con un path único, o lista de paths (para unificar varios .h5).
        encoder: "simple" (D=12) o "full" (D=44).
        target_mode: "full" (act 6D) o "movement" (act 2D [thrust, steering]).
        upsample_combat: factor (≥1) por el que se REPLICAN los samples de modos
                         de combate. 1 = sin upsample. 5 = combate cuenta 5x.
                         Útil cuando el dataset tiene muchos escape modes que
                         dominan la señal.

    Filtra episodios donde nunca se encontraron (min_dist_filter) y los
    demasiado cortos (min_ticks).
    """
    if isinstance(paths, str):
        paths = [paths]

    obs_list, act_list, mode_list = [], [], []
    n_eps_total = n_eps_kept = 0

    for path in paths:
        with h5py.File(path, "r") as f:
            for ep_name in sorted(f.keys()):
                ep = f[ep_name]
                attrs = dict(ep.attrs)
                n_eps_total += 1

                if attrs.get("min_distance_observed", 9999) > min_dist_filter:
                    continue
                if attrs.get("n_ticks", 0) < min_ticks:
                    continue

                n_eps_kept += 1
                ids = ep["vehicle_ids"][:]
                i_me = int(np.where(ids == 1)[0][0])
                i_oth = 1 - i_me

                pos = ep["pos"][:]
                az = ep["azimuth"][:]
                health = ep["health"][:]
                power = ep["power"][:]
                n = pos.shape[0]

                if encoder == "full":
                    rotation = ep["rotation"][:]
                    land = ep["landingPos"][:]

                # Vectorizar valid mask por episodio
                valid_t = np.where((health[:, i_me] > 0) & (health[:, i_oth] > 0))[0]
                ep_obs = []
                for t in valid_t:
                    if encoder == "simple":
                        ob = encode_state_from_arrays(
                            pos_me=pos[t, i_me], az_me_deg=float(az[t, i_me]),
                            h_me=float(health[t, i_me]), p_me=float(power[t, i_me]),
                            pos_oth=pos[t, i_oth], h_oth=float(health[t, i_oth]),
                        )
                    else:
                        ob = encode_state_full_from_arrays(
                            pos_me=pos[t, i_me], rot_me=rotation[t, i_me],
                            az_me_deg=float(az[t, i_me]),
                            h_me=float(health[t, i_me]), p_me=float(power[t, i_me]),
                            land_me=land[t, i_me],
                            pos_oth=pos[t, i_oth], rot_oth=rotation[t, i_oth],
                            az_oth_deg=float(az[t, i_oth]),
                            h_oth=float(health[t, i_oth]), p_oth=float(power[t, i_oth]),
                            land_oth=land[t, i_oth],
                        )
                    ep_obs.append(ob)
                obs_list.append(np.stack(ep_obs) if ep_obs else np.zeros((0, 1)))

                acts = encode_action_arrays(
                    ep["act_thrust"][:][valid_t],
                    ep["act_steering"][:][valid_t],
                    ep["act_turret_decl"][:][valid_t],
                    ep["act_turret_bearing"][:][valid_t],
                    ep["act_fire"][:][valid_t],
                    target_mode=target_mode,
                )
                act_list.append(acts)
                mode_list.append(ep["act_mode"][:][valid_t])

    obs_all = np.concatenate(obs_list, axis=0)
    act_all = np.concatenate(act_list, axis=0)
    mode_all = np.concatenate(mode_list, axis=0)

    # Upsample de combat modes (replicar samples)
    n_pre_up = len(obs_all)
    n_combat_pre = int(np.isin(mode_all, list(COMBAT_MODE_INTS)).sum())
    if upsample_combat > 1:
        combat_idx = np.where(np.isin(mode_all, list(COMBAT_MODE_INTS)))[0]
        extra_obs = np.tile(obs_all[combat_idx], (upsample_combat - 1, 1))
        extra_act = np.tile(act_all[combat_idx], (upsample_combat - 1, 1))
        obs_all = np.concatenate([obs_all, extra_obs], axis=0)
        act_all = np.concatenate([act_all, extra_act], axis=0)
        # mode_all también, para reporting post-upsample
        extra_modes = np.tile(mode_all[combat_idx], upsample_combat - 1)
        mode_all = np.concatenate([mode_all, extra_modes])

    obs_t = torch.from_numpy(obs_all).float()
    act_t = torch.from_numpy(act_all).float()
    assert obs_t.shape[0] == act_t.shape[0]

    n_combat_post = int(np.isin(mode_all, list(COMBAT_MODE_INTS)).sum())
    n_escape = int(np.isin(mode_all, list(ESCAPE_MODE_INTS)).sum())
    meta = {
        "n_files": len(paths),
        "n_eps_total": n_eps_total,
        "n_eps_kept": n_eps_kept,
        "n_samples_pre_upsample": n_pre_up,
        "n_samples": obs_t.shape[0],
        "n_combat_pre": n_combat_pre,
        "n_combat_post": n_combat_post,
        "n_escape": n_escape,
        "upsample_combat": upsample_combat,
        "combat_ratio_post": n_combat_post / max(1, obs_t.shape[0]),
    }
    return obs_t, act_t, meta


# ============================================================
# Modelo MLP
# ============================================================

class BCPolicy(nn.Module):
    def __init__(self, obs_dim=OBS_DIM, act_dim=ACT_DIM, hidden=128,
                 dropout: float = 0.0):
        super().__init__()
        layers = [
            nn.Linear(obs_dim, hidden), nn.ReLU(),
        ]
        if dropout > 0:
            layers.append(nn.Dropout(dropout))
        layers += [
            nn.Linear(hidden, hidden), nn.ReLU(),
        ]
        if dropout > 0:
            layers.append(nn.Dropout(dropout))
        layers += [
            nn.Linear(hidden, act_dim),
        ]
        self.net = nn.Sequential(*layers)
        self.obs_dim = obs_dim
        self.act_dim = act_dim
        # Saturamos cada output al rango correcto:
        # [0:5] van por tanh → [-1, 1]; [5] (fire) va por tanh también
        # (al decodificar, fire = act[5] > 0).

    def forward(self, x):
        return torch.tanh(self.net(x))


# ============================================================
# Training loop
# ============================================================

def train(obs: torch.Tensor, act: torch.Tensor, args) -> nn.Module:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Training en {device}")

    # Split 90/10 train/val
    n = obs.shape[0]
    perm = torch.randperm(n, generator=torch.Generator().manual_seed(args.seed))
    n_train = int(0.9 * n)
    train_idx, val_idx = perm[:n_train], perm[n_train:]
    obs_tr, act_tr = obs[train_idx].to(device), act[train_idx].to(device)
    obs_va, act_va = obs[val_idx].to(device), act[val_idx].to(device)

    # Dimensiones de la red según el encoder + target_mode elegidos
    obs_dim = obs.shape[1]
    act_dim = act.shape[1]   # 6 si full, 2 si movement
    model = BCPolicy(obs_dim=obs_dim, act_dim=act_dim,
                     hidden=args.hidden, dropout=args.dropout).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)

    ds_tr = TensorDataset(obs_tr, act_tr)
    dl_tr = DataLoader(ds_tr, batch_size=args.batch, shuffle=True)

    best_val = float("inf")
    best_state = None

    for ep in range(args.epochs):
        model.train()
        t0 = time.time()
        tr_loss = 0.0; n_b = 0
        for x, y in dl_tr:
            pred = model(x)
            # Loss MSE en todos los outputs. El fire podría ir aparte con BCE
            # pero MSE sobre tanh con target ±1 ya empuja al lado correcto.
            loss = ((pred - y) ** 2).mean()
            opt.zero_grad(); loss.backward(); opt.step()
            tr_loss += loss.item(); n_b += 1
        tr_loss /= max(1, n_b)

        # Eval
        model.eval()
        with torch.no_grad():
            pred_va = model(obs_va)
            va_loss = ((pred_va - act_va) ** 2).mean().item()
            # Fire accuracy sólo aplica en target_mode=full (act_dim=6).
            if act_va.shape[1] >= 6:
                fire_pred = (pred_va[:, 5] > 0).float()
                fire_true = (act_va[:, 5] > 0).float()
                fire_acc = (fire_pred == fire_true).float().mean().item()
                extra = f"fire_acc={fire_acc:.3f}"
            else:
                # Para movement: error medio en thrust + steering por separado
                err_thrust = (pred_va[:, 0] - act_va[:, 0]).abs().mean().item()
                err_steer = (pred_va[:, 1] - act_va[:, 1]).abs().mean().item()
                extra = f"|err_thr|={err_thrust:.3f} |err_str|={err_steer:.3f}"

        if va_loss < best_val:
            best_val = va_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

        dt = time.time() - t0
        print(f"  Ep {ep+1:3d}/{args.epochs}  tr_loss={tr_loss:.4f}  "
              f"va_loss={va_loss:.4f}  {extra}  ({dt:.1f}s)")

    # Cargar el mejor checkpoint
    if best_state is not None:
        model.load_state_dict(best_state)
    return model


# ============================================================
# Main
# ============================================================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=str, nargs="+", required=True,
                   help="Uno o más HDF5 (se concatenan). Ej: --dataset data/train/*.h5")
    p.add_argument("--output", type=str, default="models/bc_otter.pt")
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--batch", type=int, default=256)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--min-dist-filter", type=float, default=1500.0,
                   help="Filtrar eps donde nunca se acercaron a esto.")
    p.add_argument("--min-ticks", type=int, default=50)
    p.add_argument("--encoder", choices=["simple", "full"], default="full",
                   help="simple=12 features (legacy), full=44 features con TODA "
                        "la telemetría UDP (pos xyz, rotation 3x3, landingPos, etc.)")
    p.add_argument("--target-mode", choices=["full", "movement"], default="full",
                   help="full=6 outputs (thrust,steering,td,cos(tb),sin(tb),fire). "
                        "movement=2 outputs (thrust,steering) — aim+fire los aporta "
                        "el cheater scripted en eval. Útil cuando el dataset no tiene "
                        "señal de aim/fire (pocos disparos / pocos hits).")
    p.add_argument("--upsample-combat", type=int, default=1,
                   help="Replica samples de modos de combate este factor. "
                        "1 = sin upsample. 5 = combate cuenta 5x. Útil para balancear "
                        "datasets dominados por escape modes.")
    p.add_argument("--hidden", type=int, default=256,
                   help="Hidden size de la MLP. 128 alcanza para simple, "
                        "256 mejor para full.")
    p.add_argument("--dropout", type=float, default=0.1,
                   help="Dropout para regularizar. 0 = sin, 0.1 = leve, 0.3 = fuerte.")
    p.add_argument("--preview", action="store_true",
                   help="Solo mostrar stats del dataset, no entrenar.")
    args = p.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    print(f"Cargando {len(args.dataset)} dataset(s)  "
          f"(encoder={args.encoder}, target_mode={args.target_mode}, "
          f"upsample_combat={args.upsample_combat})")
    for d in args.dataset:
        print(f"  - {d}")
    obs, act, meta = load_dataset(
        args.dataset, args.min_dist_filter, args.min_ticks,
        encoder=args.encoder, target_mode=args.target_mode,
        upsample_combat=args.upsample_combat,
    )
    print(f"\n=== Resumen del dataset de entrenamiento ===")
    print(f"  Eps totales:                {meta['n_eps_total']}")
    print(f"  Eps válidos (pasan filtro): {meta['n_eps_kept']}")
    print(f"  Samples pre-upsample:       {meta['n_samples_pre_upsample']:,}")
    print(f"  Samples combate pre:        {meta['n_combat_pre']:,}  "
          f"({100*meta['n_combat_pre']/max(1,meta['n_samples_pre_upsample']):.1f}%)")
    print(f"  Samples escape (no combat): {meta['n_escape']:,}  "
          f"({100*meta['n_escape']/max(1,meta['n_samples_pre_upsample']):.1f}%)")
    print(f"  --upsample-combat = {meta['upsample_combat']}")
    print(f"  Samples post-upsample:      {meta['n_samples']:,}")
    print(f"  Samples combate post:       {meta['n_combat_post']:,}  "
          f"({100*meta['combat_ratio_post']:.1f}%)")
    print(f"  obs shape:                  {tuple(obs.shape)}")
    print(f"  act shape:                  {tuple(act.shape)}")

    if args.preview:
        print(f"\n✓ Preview only. Para entrenar, sacá --preview.")
        return

    if obs.shape[0] < 1000:
        print("⚠️  Dataset muy chico (<1000 samples). Recolectá más episodios.")
        return

    model = train(obs, act, args)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "state_dict": model.state_dict(),
        "obs_dim": model.obs_dim, "act_dim": model.act_dim,
        "encoder": args.encoder,        # CRÍTICO: eval_bc tiene que usar el mismo
        "target_mode": args.target_mode, # CRÍTICO: eval_bc decide arquitectura
        "hidden": args.hidden,
        "dropout": args.dropout,
        "meta": meta, "args": vars(args),
    }, args.output)
    print(f"\n✓ Modelo guardado en {args.output}")
    print(f"  Para eval: --encoder {args.encoder}  (target_mode={args.target_mode})")


if __name__ == "__main__":
    main()
