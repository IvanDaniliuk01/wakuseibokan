"""Smoke test ligero del pipeline de preprocessing — sin d3rlpy/torch.

Valida que el HDF5 se carga, que el encoder funciona, y que los rewards son
razonables ANTES de subir a Colab. Solo requiere numpy + h5py.

Uso:
    python3 -m agent.colab.smoke_test_local data/dataset_v1.h5
"""
import sys
import numpy as np
import h5py
from pathlib import Path


# Copiamos las funciones del notebook (sin importar torch/d3rlpy)
POS_SCALE = 2000.0
OBS_DIM = 12
ACT_DIM = 6


def load_episodes(path):
    episodes = []
    with h5py.File(path, "r") as f:
        for name in sorted(f.keys()):
            g = f[name]
            ep = {k: g[k][:] for k in g.keys()}
            ep["_attrs"] = dict(g.attrs)
            episodes.append(ep)
        meta = dict(f.attrs)
    return episodes, meta


def encode_state(my_idx, other_idx, ep, t):
    pos_me  = ep["pos"][t, my_idx]
    pos_oth = ep["pos"][t, other_idx]
    az_me   = ep["azimuth"][t, my_idx]
    h_me    = ep["health"][t, my_idx]
    p_me    = ep["power"][t, my_idx]
    h_oth   = ep["health"][t, other_idx]

    dx = pos_oth[0] - pos_me[0]
    dz = pos_oth[2] - pos_me[2]
    dist = np.sqrt(dx * dx + dz * dz)
    bearing_world = np.arctan2(dz, dx)
    bearing_rel = bearing_world - az_me * np.pi / 180.0

    return np.array([
        pos_me[0] / POS_SCALE,
        pos_me[2] / POS_SCALE,
        np.cos(az_me * np.pi / 180.0),
        np.sin(az_me * np.pi / 180.0),
        np.clip(h_me / 1000.0, -1.0, 1.5),
        np.clip(p_me / 1000.0, 0.0, 1.5),
        dx / POS_SCALE,
        dz / POS_SCALE,
        np.clip(dist / POS_SCALE, 0.0, 3.0),
        np.cos(bearing_rel),
        np.sin(bearing_rel),
        np.clip(h_oth / 1000.0, -1.0, 1.5),
    ], dtype=np.float32)


def encode_action(ep, t):
    tb_rad = ep["act_turret_bearing"][t] * np.pi / 180.0
    return np.array([
        np.clip(ep["act_thrust"][t] / 10.0, -1.0, 1.0),
        np.clip(ep["act_steering"][t], -1.0, 1.0),
        np.clip(ep["act_turret_decl"][t] / 0.4, -1.0, 1.0),
        np.cos(tb_rad),
        np.sin(tb_rad),
        1.0 if ep["act_fire"][t] else -1.0,
    ], dtype=np.float32)


def compute_rewards(my_idx, other_idx, ep):
    h_me  = ep["health"][:, my_idx].astype(np.float32)
    h_oth = ep["health"][:, other_idx].astype(np.float32)
    fire  = ep["act_fire"].astype(bool)
    n = len(h_me)
    rewards = np.zeros(n, dtype=np.float32)
    terminals = np.zeros(n, dtype=bool)

    for t in range(n):
        r = -0.01
        if t > 0:
            dmg_dado = max(0.0, h_oth[t - 1] - h_oth[t])
            dmg_recib = max(0.0, h_me[t - 1] - h_me[t])
            r += 0.1 * dmg_dado - 0.1 * dmg_recib
        if t < len(fire) and fire[t]:
            r -= 0.05
        if h_oth[t] <= 0 and (t == 0 or h_oth[t - 1] > 0):
            r += 500.0
            terminals[t] = True
        if h_me[t] <= 0 and (t == 0 or h_me[t - 1] > 0):
            r -= 500.0
            terminals[t] = True
        rewards[t] = r
    terminals[-1] = True
    return rewards, terminals


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m agent.colab.smoke_test_local <dataset.h5>")
        sys.exit(1)
    path = sys.argv[1]
    print(f"=== Smoke test: {path} ===\n")

    # 1) Carga
    episodes, meta = load_episodes(path)
    n_eps = len(episodes)
    assert n_eps > 0, "No hay episodios"
    print(f"[OK] Cargados {n_eps} episodios. Meta: {meta}")

    # 2) Inspección por episodio
    n_died = 0
    total_ticks = 0
    for i, ep in enumerate(episodes):
        n_ticks = ep["pos"].shape[0]
        n_veh = ep["pos"].shape[1]
        final_h = ep["health"][-1]
        attrs = ep["_attrs"]
        died = any(h <= 0 for h in final_h)
        if died:
            n_died += 1
        total_ticks += n_ticks
        print(f"  Ep {i}: {n_ticks} ticks, vehicles={list(ep['vehicle_ids'])}, "
              f"final_h={[f'{h:.0f}' for h in final_h]}, died={died}, "
              f"dist_fire={attrs.get('params_dist_fire', '?'):.0f}m, "
              f"noise={attrs.get('params_noise_prob', 0):.2f}")
    print(f"\n[Stats] {n_died}/{n_eps} episodios con muerte (combate real), "
          f"{total_ticks} ticks totales ({total_ticks * 0.05:.0f}s a 50ms)\n")

    # 3) Encoders smoke test (primer episodio, varios ticks)
    ep = episodes[0]
    vids = list(ep["vehicle_ids"])
    assert len(vids) == 2, f"Esperaba 2 vehículos por episodio, vi {vids}"
    my_idx = vids.index(1)
    other_idx = vids.index(2)

    sample_ts = [0, len(ep["pos"]) // 2, len(ep["pos"]) - 1]
    for t in sample_ts:
        s = encode_state(my_idx, other_idx, ep, t)
        a = encode_action(ep, min(t, len(ep["act_thrust"]) - 1))
        assert s.shape == (OBS_DIM,), f"shape state: {s.shape}"
        assert a.shape == (ACT_DIM,), f"shape action: {a.shape}"
        assert not np.any(np.isnan(s)), f"NaN en state en t={t}: {s}"
        assert not np.any(np.isnan(a)), f"NaN en action en t={t}: {a}"
        print(f"  t={t}: state[:4]={s[:4].round(3)}  action={a.round(2)}")
    print(f"[OK] Encoders sin NaN, shapes correctos\n")

    # 4) Reward shaping
    rewards, terminals = compute_rewards(my_idx, other_idx, ep)
    print(f"[Rewards ep 0] mean={rewards.mean():.3f} std={rewards.std():.3f} "
          f"min={rewards.min():.1f} max={rewards.max():.1f} sum={rewards.sum():.1f}")
    print(f"  Terminals: {terminals.sum()} marcados")
    n_big_pos = int((rewards > 50).sum())
    n_big_neg = int((rewards < -50).sum())
    print(f"  Ticks con reward >50 (hit dado): {n_big_pos}, "
          f"con reward <-50 (hit recibido): {n_big_neg}")

    # 5) Aplanar todo el dataset
    all_obs, all_act, all_rew, all_term = [], [], [], []
    for ep in episodes:
        vids = list(ep["vehicle_ids"])
        if 1 not in vids:
            continue
        my_idx = vids.index(1)
        other_idx = 1 - my_idx if len(vids) == 2 else None
        if other_idx is None:
            continue
        n = ep["pos"].shape[0]
        n_act = len(ep["act_thrust"])
        usable = min(n, n_act)
        rew, term = compute_rewards(my_idx, other_idx, ep)
        for t in range(usable):
            all_obs.append(encode_state(my_idx, other_idx, ep, t))
            all_act.append(encode_action(ep, t))
            all_rew.append(rew[t])
            all_term.append(term[t])

    obs_arr = np.stack(all_obs)
    act_arr = np.stack(all_act)
    rew_arr = np.array(all_rew)
    term_arr = np.array(all_term)
    print(f"\n[Dataset full]")
    print(f"  obs:       {obs_arr.shape}  dtype={obs_arr.dtype}")
    print(f"  actions:   {act_arr.shape}  dtype={act_arr.dtype}")
    print(f"  rewards:   {rew_arr.shape}  min={rew_arr.min():.1f} max={rew_arr.max():.1f} mean={rew_arr.mean():.3f}")
    print(f"  terminals: {term_arr.sum()}/{len(term_arr)}")
    print(f"  obs range por dim:")
    for d in range(OBS_DIM):
        print(f"    [{d}] min={obs_arr[:, d].min():.3f}  max={obs_arr[:, d].max():.3f}  mean={obs_arr[:, d].mean():.3f}")
    print(f"\n[OK] Pipeline completo. Listo para Colab.")


if __name__ == "__main__":
    main()
