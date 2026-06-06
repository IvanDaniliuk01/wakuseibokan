"""Exporta un dataset HDF5 a CSV para inspección humana.

Dos formatos disponibles:
  --format flat:    una fila por (episodio, tick). Útil para ver trayectorias
                    y acciones en Excel/pandas.
  --format summary: una fila por episodio con stats agregados. Útil para
                    ver win rate, hit rate, distribuciones por nivel.

USO:
    python -m agent.inspect_dataset \\
        --dataset data/train/bc_dataset.h5 \\
        --format flat \\
        --output data/train/bc_dataset_flat.csv

    python -m agent.inspect_dataset \\
        --dataset data/train/bc_dataset.h5 \\
        --format summary \\
        --output data/train/bc_dataset_summary.csv
"""
import argparse
import csv
import math
from pathlib import Path

import h5py
import numpy as np


def export_flat(path_in: str, path_out: str, max_eps: int = None,
                stride: int = 1):
    """Una fila por (ep, tick) con: pos+health+az+acciones humanas.

    `stride`: muestrear cada N ticks (1=todo, 5=cada 5 ticks). Útil para
    reducir tamaño cuando hay muchos eps largos.
    """
    Path(path_out).parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "ep_id", "outcome", "opponent_level", "tick",
        "my_x", "my_y", "my_z", "my_az_deg", "my_health", "my_power",
        "oth_x", "oth_y", "oth_z", "oth_az_deg", "oth_health",
        "dist_xz", "dy",
        "act_thrust", "act_steering", "act_turret_decl", "act_turret_bearing", "act_fire",
        "act_mode",
    ]
    n_eps = n_rows = 0
    with h5py.File(path_in, "r") as f, open(path_out, "w", newline="") as out:
        w = csv.writer(out)
        w.writerow(cols)
        for ep_name in sorted(f.keys()):
            if max_eps and n_eps >= max_eps:
                break
            ep = f[ep_name]
            attrs = dict(ep.attrs)
            ids = ep["vehicle_ids"][:]
            i_me = int(np.where(ids == 1)[0][0])
            i_oth = 1 - i_me

            pos = ep["pos"][:]
            az = ep["azimuth"][:]
            health = ep["health"][:]
            power = ep["power"][:]
            thrust = ep["act_thrust"][:]
            steering = ep["act_steering"][:]
            t_decl = ep["act_turret_decl"][:]
            t_bear = ep["act_turret_bearing"][:]
            fire = ep["act_fire"][:]
            mode = ep["act_mode"][:]
            n = pos.shape[0]

            for t in range(0, n, stride):
                dx = pos[t, i_oth, 0] - pos[t, i_me, 0]
                dz = pos[t, i_oth, 2] - pos[t, i_me, 2]
                dist = math.sqrt(dx * dx + dz * dz)
                dy = pos[t, i_oth, 1] - pos[t, i_me, 1]
                w.writerow([
                    ep_name, attrs.get("outcome", "?"),
                    attrs.get("opponent_level", "?"), t,
                    f"{pos[t,i_me,0]:.2f}", f"{pos[t,i_me,1]:.2f}", f"{pos[t,i_me,2]:.2f}",
                    f"{az[t,i_me]:.2f}", f"{health[t,i_me]:.1f}", int(power[t,i_me]),
                    f"{pos[t,i_oth,0]:.2f}", f"{pos[t,i_oth,1]:.2f}", f"{pos[t,i_oth,2]:.2f}",
                    f"{az[t,i_oth]:.2f}", f"{health[t,i_oth]:.1f}",
                    f"{dist:.1f}", f"{dy:.2f}",
                    f"{thrust[t]:.2f}", f"{steering[t]:.2f}",
                    f"{t_decl[t]:.4f}", f"{t_bear[t]:.2f}",
                    int(fire[t]), int(mode[t]),
                ])
                n_rows += 1
            n_eps += 1
    print(f"✓ CSV flat: {n_rows} filas de {n_eps} episodios → {path_out}")


def export_summary(path_in: str, path_out: str):
    """Una fila por episodio con stats agregados."""
    Path(path_out).parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "ep_id", "outcome", "opponent_level", "n_ticks",
        "had_combat", "min_dist",
        "h_a_final", "h_b_final",
        "n_fires", "n_hits_dealt", "n_hits_taken",
        "dmg_dealt", "dmg_taken", "hit_rate_pct",
        "modes_used",
    ]
    n_eps = wins = losses = draws = 0
    with h5py.File(path_in, "r") as f, open(path_out, "w", newline="") as out:
        w = csv.writer(out)
        w.writerow(cols)
        for ep_name in sorted(f.keys()):
            ep = f[ep_name]
            attrs = dict(ep.attrs)
            ids = ep["vehicle_ids"][:]
            i_me = int(np.where(ids == 1)[0][0])
            i_oth = 1 - i_me

            pos = ep["pos"][:]
            health = ep["health"][:]
            fire = ep["act_fire"][:]
            mode = ep["act_mode"][:]
            n = pos.shape[0]

            d_oth = -np.diff(health[:, i_oth], prepend=health[0, i_oth])
            d_me = -np.diff(health[:, i_me], prepend=health[0, i_me])
            n_hits_dealt = int((d_oth >= 30).sum())
            n_hits_taken = int((d_me >= 30).sum())
            dmg_dealt = float(d_oth.clip(min=0).sum())
            dmg_taken = float(d_me.clip(min=0).sum())
            n_fires = int(fire.sum())
            hit_rate = 100.0 * n_hits_dealt / max(1, n_fires)

            from collections import Counter
            modes_count = Counter(int(m) for m in mode)
            modes_str = ";".join(f"{k}:{v}" for k, v in sorted(modes_count.items()))

            outcome = attrs.get("outcome", "?")
            if outcome == "win": wins += 1
            elif outcome == "loss": losses += 1
            else: draws += 1

            w.writerow([
                ep_name, outcome, attrs.get("opponent_level", "?"), n,
                int(bool(attrs.get("had_encounter", False))),
                f"{attrs.get('min_distance_observed', -1):.1f}",
                f"{health[-1,i_me]:.0f}", f"{health[-1,i_oth]:.0f}",
                n_fires, n_hits_dealt, n_hits_taken,
                f"{dmg_dealt:.0f}", f"{dmg_taken:.0f}", f"{hit_rate:.1f}",
                modes_str,
            ])
            n_eps += 1
    print(f"✓ CSV summary: {n_eps} eps → {path_out}")
    print(f"  Wins: {wins} ({100*wins/max(1,n_eps):.0f}%)  "
          f"Losses: {losses} ({100*losses/max(1,n_eps):.0f}%)  "
          f"Draws: {draws} ({100*draws/max(1,n_eps):.0f}%)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True, help="Path al HDF5")
    p.add_argument("--format", choices=["flat", "summary", "both"],
                   default="summary",
                   help="flat=fila por (ep, tick), summary=fila por ep, both=ambos")
    p.add_argument("--output", default=None,
                   help="Path del CSV. Si no se especifica, se autogenera.")
    p.add_argument("--max-eps", type=int, default=None,
                   help="Limitar a primeros N eps (debug). Solo aplica a --format flat.")
    p.add_argument("--stride", type=int, default=1,
                   help="Muestrear cada N ticks (solo flat). 1=todo, 10=10%% del tamaño.")
    args = p.parse_args()

    if args.format in ("flat", "both"):
        out = args.output or args.dataset.replace(".h5", "_flat.csv")
        if args.format == "both":
            out = args.dataset.replace(".h5", "_flat.csv")
        export_flat(args.dataset, out, max_eps=args.max_eps, stride=args.stride)

    if args.format in ("summary", "both"):
        out = args.output or args.dataset.replace(".h5", "_summary.csv")
        if args.format == "both":
            out = args.dataset.replace(".h5", "_summary.csv")
        export_summary(args.dataset, out)


if __name__ == "__main__":
    main()
