"""Recolección de dataset con un cheater como oponente.

Corre dos threads de control en el mismo proceso:
- Otter 1: controlado por seek_policy (la "fábrica de datos" — el que GRABAMOS).
- Otter 2: controlado por cheater_policy con dificultad configurable.

El simulador debe estar corriendo con `-mute -nointro -episodes` antes.

Uso típico — dataset mezclado:
    # Terminal A: ./testcase -mute -nointro -episodes
    # Terminal B:
    python -m agent.collect_vs_cheater --difficulty mixed \\
        --mix-plan "easy:150,medium:300,hard:300,impossible:75" \\
        --output data/dataset_v2.h5

Uso para calibrar dificultad de un solo nivel:
    python -m agent.collect_vs_cheater --difficulty hard --episodes 10 \\
        --output data/calib_hard.h5
"""
import argparse
import math
import os
import signal
import subprocess
import time
from pathlib import Path
from threading import Lock, Thread, Event
from typing import List, Optional, Tuple

import h5py
import numpy as np

from . import packet_format as pf
from .udp_io import UDPClient
from .seek_policy import sample_episode_params, init_state as seek_init_state, decide as seek_decide
from .cheater_policy import (
    DifficultyLevel, params_for_level,
    init_state as cheater_init_state,
    decide as cheater_decide,
)
from .human_control import SimLauncher
# params_for_level también lo importamos para que run_recording_episode pueda
# usarlo cuando args.player_level está seteado (modo BC).
from .encoders import build_command


# ============================================================
# HDF5 I/O — guardar lista de episodios al disco
# ============================================================

# Mapeo de modo a int (para guardar como columna en HDF5).
# Incluye modos de seek_policy (legacy) y de cheater_policy (cuando el Otter 1
# se controla con cheater por --player-level).
_MODE_TO_INT = {
    # seek_policy
    "engage": 0, "noise": 1, "escape": 2, "evasive": 3,
    # cheater_policy
    "cheater_engage": 10, "cheater_evade": 11, "cheater_noise": 12,
    "cheater_recovery": 13, "cheater_standoff": 14, "cheater_bait": 15,
    "cheater_chaos": 16, "cheater_too_close": 17,
    "cheater_engage_jiggle": 18, "cheater_swerve_burst": 19,
    "cheater_escape_rotate": 20, "cheater_escape_advance": 21,
    "cheater_water_guard": 22,
}


def records_to_arrays(records, actions_log, mode_counts, params):
    """Convierte la lista cruda de (timestamp, snapshot) a un dict de numpy arrays
    listo para guardar como un grupo HDF5 por episodio.

    `records[t]` es `(timestamp, {vehicle_id: ModelRecord})`. `actions_log[t]`
    es el dict con la acción que ejecutó el otter controlado en ese tick.
    """
    if not records:
        return None
    all_ids = sorted({vid for _, snap in records for vid in snap})
    n_ticks = len(records)
    n_veh = len(all_ids)
    id_to_idx = {vid: i for i, vid in enumerate(all_ids)}

    pos = np.zeros((n_ticks, n_veh, 3), dtype=np.float32)
    rot = np.zeros((n_ticks, n_veh, 12), dtype=np.float32)
    health = np.zeros((n_ticks, n_veh), dtype=np.float32)
    power = np.zeros((n_ticks, n_veh), dtype=np.int32)
    az = np.zeros((n_ticks, n_veh), dtype=np.float32)
    land = np.zeros((n_ticks, n_veh, 3), dtype=np.float32)
    timer = np.zeros((n_ticks, n_veh), dtype=np.uint32)
    valid_arr = np.zeros((n_ticks, n_veh), dtype=bool)

    for t, (_, snap) in enumerate(records):
        for vid, mr in snap.items():
            i = id_to_idx[vid]
            pos[t, i] = mr.pos
            rot[t, i] = mr.rotation
            health[t, i] = mr.health
            power[t, i] = mr.power
            az[t, i] = mr.azimuth
            land[t, i] = mr.landingPos
            timer[t, i] = mr.recordtimer
            valid_arr[t, i] = True

    mode_int = np.array([_MODE_TO_INT.get(a["mode"], -1) for a in actions_log], dtype=np.int8)

    return {
        "vehicle_ids": np.array(all_ids, dtype=np.int32),
        "pos": pos, "rotation": rot, "health": health, "power": power,
        "azimuth": az, "landingPos": land, "recordtimer": timer, "valid": valid_arr,
        "act_thrust": np.array([a["thrust"] for a in actions_log], dtype=np.float32),
        "act_steering": np.array([a["steering"] for a in actions_log], dtype=np.float32),
        "act_turret_decl": np.array([a["turret_decl"] for a in actions_log], dtype=np.float32),
        "act_turret_bearing": np.array([a["turret_bearing"] for a in actions_log], dtype=np.float32),
        "act_fire": np.array([a["fire"] for a in actions_log], dtype=bool),
        "act_mode": mode_int,
        "_params_dist_fire": params.dist_fire,
        "_params_dist_engage": params.dist_engage,
        "_params_thrust_max": params.thrust_max,
        "_params_noise_prob": params.noise_prob,
    }


def save_episodes_hdf5(episodes, path):
    """Guarda una lista de episodios (cada uno dict de arrays) en HDF5.

    Convención: keys que empiezan con "_" se guardan como attrs del grupo
    (sin el guion bajo). El resto se guardan como datasets comprimidos.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        n = 0
        for i, ep in enumerate(episodes):
            if ep is None:
                continue
            g = f.create_group(f"episode_{i:04d}")
            for k, v in ep.items():
                if k.startswith("_"):
                    g.attrs[k[1:]] = v
                else:
                    g.create_dataset(k, data=v, compression="gzip")
            g.attrs["n_ticks"] = ep["pos"].shape[0]
            g.attrs["n_vehicles"] = ep["pos"].shape[1]
            n += 1
        f.attrs["n_episodes"] = n
    print(f"✓ Dataset guardado en {path}", flush=True)


def append_episode_hdf5(ep: dict, path: str, ep_index: int):
    """Append-write incremental: un solo episodio por llamada.

    Si el archivo no existe lo crea. Cada llamada agrega un grupo
    `episode_{ep_index:04d}` y actualiza el attr `n_episodes`. Así, si el
    proceso muere por LCP error o pkill, lo que ya quedó grabado se conserva.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if Path(path).exists() else "w"
    with h5py.File(path, mode) as f:
        g_name = f"episode_{ep_index:04d}"
        if g_name in f:
            del f[g_name]  # idempotente: sobreescribe si re-corremos
        g = f.create_group(g_name)
        for k, v in ep.items():
            if k.startswith("_"):
                g.attrs[k[1:]] = v
            else:
                g.create_dataset(k, data=v, compression="gzip")
        g.attrs["n_ticks"] = ep["pos"].shape[0]
        g.attrs["n_vehicles"] = ep["pos"].shape[1]
        f.attrs["n_episodes"] = len([k for k in f.keys() if k.startswith("episode_")])


# ============================================================
# Plan de mezcla
# ============================================================

def parse_mix_plan(spec: str) -> List[Tuple[DifficultyLevel, int]]:
    """Parsea 'easy:100,medium:200,hard:200,impossible:50' a [(level, n), ...]."""
    plan = []
    for chunk in spec.split(","):
        name, count = chunk.split(":")
        plan.append((DifficultyLevel(name.strip().lower()), int(count.strip())))
    return plan


# ============================================================
# Cliente compartido entre los dos threads
# ============================================================

class DualClient:
    """Maneja UN socket de recepción (cualquier endpoint recibe todos los
    vehículos por broadcast) y DOS sockets de envío, uno por puerto de comandos."""

    def __init__(self, recv_port_1: int, send_port_1: int,
                 recv_port_2: int, send_port_2: int,
                 send_host: str = "127.0.0.1"):
        # Cliente del otter 1
        self.c1 = UDPClient(recv_port_1, send_host, send_port_1, buffer_size=128)
        # Cliente del otter 2
        self.c2 = UDPClient(recv_port_2, send_host, send_port_2, buffer_size=128)

        self._lock = Lock()
        self.latest = {}  # vid → ModelRecord
        self._stop = Event()

    def _handler(self, data: bytes):
        if len(data) != pf.MODEL_RECORD_SIZE:
            return
        try:
            mr = pf.ModelRecord.from_bytes(data)
        except Exception:
            return
        with self._lock:
            self.latest[mr.number] = mr

    def start(self):
        self.c1.start(self._handler)
        self.c2.start(self._handler)

    def all_latest(self):
        with self._lock:
            return dict(self.latest)

    def clear(self):
        with self._lock:
            self.latest.clear()

    def send_to_1(self, data: bytes):
        self.c1.send_bytes(data)

    def send_to_2(self, data: bytes):
        self.c2.send_bytes(data)

    def stop(self):
        self._stop.set()
        self.c1.stop()
        self.c2.stop()


# ============================================================
# Cheater loop (corre en thread separado)
# ============================================================

class CheaterLoop:
    def __init__(self, dual: DualClient, level: DifficultyLevel,
                 tick_dt: float, rng_seed: int):
        self.dual = dual
        self.params = params_for_level(level)
        self.state = cheater_init_state(self.params)
        self.tick_dt = tick_dt
        self.rng = np.random.default_rng(rng_seed)
        self._stop = Event()
        self._thread: Optional[Thread] = None

    def start(self):
        self._stop.clear()
        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            time.sleep(self.tick_dt)
            snap = self.dual.all_latest()
            if 2 not in snap or 1 not in snap:
                continue
            my = snap[2]
            other = snap[1]
            if my.health <= 0 or other.health <= 0:
                continue
            thrust, steering, td, tb, fire, _mode = cheater_decide(
                my.pos, float(my.azimuth), float(my.health),
                other.pos, float(other.health),
                self.params, self.state, self.rng,
            )
            cmd = build_command(2, thrust, steering, td, tb, fire, my.recordtimer)
            self.dual.send_to_2(cmd.to_bytes())

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def reset_state(self):
        self.state = cheater_init_state(self.params)


# ============================================================
# Episodio del agente que graba (Otter 1)
# ============================================================

def run_recording_episode(dual: DualClient, args, rng):
    """Corre un episodio grabando el Otter 1.

    Si args.player_level es None → usa seek_policy (legacy, comportamiento original).
    Si args.player_level es un DifficultyLevel → usa cheater_policy con ese nivel
        (modo BC: queremos clonar al cheater, así que es el Otter 1 quien tiene
        info perfecta y comportamiento "experto").

    Devuelve (records, actions_log, mode_counts, params, episode_stats).
    """
    records = []
    actions_log = []
    start = time.time()
    last_timer = -1
    no_update = 0
    episode_started = False
    min_dist = float("inf")

    use_cheater_as_player = args.player_level is not None
    if use_cheater_as_player:
        params = params_for_level(args.player_level)
        state = cheater_init_state(params)
        # mode_counts genérico, las claves van a llenarse al vuelo
        mode_counts = {}
    else:
        params = sample_episode_params(rng, base_noise_prob=args.noise_prob)
        state = seek_init_state()
        mode_counts = {"engage": 0, "noise": 0, "escape": 0, "evasive": 0}

    while time.time() - start < args.max_seconds:
        time.sleep(args.tick_dt)
        snapshot = dual.all_latest()
        if not snapshot:
            continue

        valid = {vid: mr for vid, mr in snapshot.items() if mr.health > -1000}
        if 1 not in valid or 2 not in valid:
            continue

        my_mr = valid[1]
        other_mr = valid[2]

        if not episode_started:
            if all(mr.health > 0 for mr in valid.values()):
                episode_started = True
            else:
                continue

        # Distancia para filtro de "encuentro mínimo"
        dx = float(other_mr.pos[0]) - float(my_mr.pos[0])
        dz = float(other_mr.pos[2]) - float(my_mr.pos[2])
        dist = math.sqrt(dx * dx + dz * dz)
        if dist < min_dist:
            min_dist = dist

        if use_cheater_as_player:
            thrust, steering, td, tb, fire, mode_tag = cheater_decide(
                my_pos=my_mr.pos, my_az_deg=float(my_mr.azimuth),
                my_health=float(my_mr.health),
                other_pos=other_mr.pos, other_health=float(other_mr.health),
                params=params, state=state, rng=rng,
            )
        else:
            thrust, steering, td, tb, fire, mode_tag = seek_decide(
                my_mr.pos, float(my_mr.azimuth), float(my_mr.health),
                other_mr.pos, params, state, rng,
            )
        mode_counts[mode_tag] = mode_counts.get(mode_tag, 0) + 1

        cmd = build_command(1, thrust, steering, td, tb, fire, my_mr.recordtimer)
        dual.send_to_1(cmd.to_bytes())

        records.append((time.time(), valid))
        actions_log.append({
            "thrust": thrust, "steering": steering,
            "turret_decl": td, "turret_bearing": tb,
            "fire": fire, "mode": mode_tag,
        })

        if any(mr.health <= 0 for mr in valid.values()):
            break

        cur_t = max(mr.recordtimer for mr in valid.values())
        if cur_t == last_timer:
            no_update += 1
            if no_update > 50:
                break
        else:
            no_update = 0
            last_timer = cur_t

    stats = {
        "min_dist": min_dist if min_dist != float("inf") else -1.0,
        "had_encounter": min_dist < args.min_encounter_distance,
    }
    return records, actions_log, mode_counts, params, stats


# ============================================================
# Main
# ============================================================

def build_episode_plan(args) -> List[DifficultyLevel]:
    """Devuelve la lista de niveles a recolectar, uno por episodio."""
    if args.difficulty != "mixed":
        level = DifficultyLevel(args.difficulty)
        return [level] * args.episodes

    plan = parse_mix_plan(args.mix_plan)
    out = []
    for lvl, n in plan:
        out.extend([lvl] * n)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--difficulty",
                   choices=["easy", "medium", "hard", "impossible",
                            "predator", "predator_v2", "mixed"],
                   default="mixed")
    p.add_argument("--mix-plan", type=str,
                   default="easy:80,medium:200,hard:300,impossible:50,predator:170",
                   help="Solo aplica si --difficulty mixed. Formato 'name:N,name:N,...'")
    p.add_argument("--episodes", type=int, default=10,
                   help="Solo aplica si --difficulty NO es mixed.")
    p.add_argument("--output", type=str, default="data/dataset_vs_cheater.h5")
    p.add_argument("--min-encounter-distance", type=float, default=800.0,
                   help="Episodios con min_dist > esto se marcan had_encounter=False.")
    p.add_argument("--noise-prob", type=float, default=0.0,
                   help="noise_prob de seek_policy. Default 0 (sin noise por tick — "
                        "rompe rotaciones). La diversidad viene de los episodios.")
    p.add_argument("--max-seconds", type=int, default=90)
    p.add_argument("--tick-dt", type=float, default=0.05)
    p.add_argument("--inter-episode-wait", type=float, default=6.0,
                   help="Segundos entre episodios (>= endtimer del sim = 300 ticks).")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--player-level", type=str, default=None,
                   choices=[None, "easy", "medium", "hard", "impossible",
                            "predator", "predator_v2"],
                   help="Si se setea, el Otter 1 (el que se GRABA) se controla "
                        "con cheater_policy en este nivel en lugar de seek_policy. "
                        "Recomendado para BC: --player-level predator_v2.")
    # Relanzamiento del sim para diversidad de mapas (como human_control)
    p.add_argument("--launch-sim", action="store_true",
                   help="Lanzar y manejar el sim como subprocess. Permite "
                        "relanzarlo entre episodios para variar el mapa.")
    p.add_argument("--sim-binary", type=str, default="./testcase")
    p.add_argument("--sim-cwd", type=str, default=None)
    p.add_argument("--relaunch-every", type=int, default=25,
                   help="Relanzar el sim cada N episodios (default 25). Solo "
                        "aplica con --launch-sim. 0=nunca.")
    p.add_argument("--sim-startup-wait", type=float, default=3.0,
                   help="Segundos a esperar tras lanzar el sim antes de "
                        "esperar telemetría.")
    p.add_argument("--recv-port-1", type=int, default=4601)
    p.add_argument("--send-port-1", type=int, default=4501)
    p.add_argument("--recv-port-2", type=int, default=4602)
    p.add_argument("--send-port-2", type=int, default=4502)
    p.add_argument("--send-host", type=str, default="127.0.0.1")
    args = p.parse_args()

    rng = np.random.default_rng(args.seed)
    # Convertir player_level string → DifficultyLevel (o None)
    if args.player_level is not None:
        args.player_level = DifficultyLevel(args.player_level)
    plan = build_episode_plan(args)
    total_eps = len(plan)

    print(f"[collect_vs_cheater] Plan total: {total_eps} episodios")
    if args.player_level is not None:
        print(f"  PLAYER (Otter 1, grabado): {args.player_level.value} (cheater)")
    else:
        print(f"  PLAYER (Otter 1, grabado): seek_policy (legacy)")
    if args.difficulty == "mixed":
        from collections import Counter
        counts = Counter(plan)
        for lvl, n in counts.items():
            print(f"  {lvl.value:12s} {n} eps")
    print(f"  output: {args.output}")

    # Sim launcher (opcional). Si activo, relanzamos cada relaunch_every eps
    # para diversidad de mapa (el sim siembra con time(NULL) al arrancar).
    launcher: Optional[SimLauncher] = None
    if args.launch_sim:
        launcher = SimLauncher(
            binary=args.sim_binary,
            args=("-mute", "-nointro", "-episodes"),
            cwd=args.sim_cwd,
        )
        launcher.launch()
        print(f"\nEsperando arranque del sim ({args.sim_startup_wait}s)...")
        time.sleep(args.sim_startup_wait)

    dual = DualClient(
        recv_port_1=args.recv_port_1, send_port_1=args.send_port_1,
        recv_port_2=args.recv_port_2, send_port_2=args.send_port_2,
        send_host=args.send_host,
    )
    dual.start()

    print("\nEsperando telemetría de ambos vehículos...")
    deadline = time.time() + 15
    while time.time() < deadline:
        snap = dual.all_latest()
        if 1 in snap and 2 in snap:
            break
        time.sleep(0.1)
    if not (1 in dual.all_latest() and 2 in dual.all_latest()):
        print("⚠️  No llegó telemetría de ambos vehículos. ¿Sim corriendo con -episodes?")
        dual.stop()
        return
    print("✓ Conexión establecida.\n")

    all_episodes = []
    win_count = {lvl: 0 for lvl in DifficultyLevel}
    loss_count = {lvl: 0 for lvl in DifficultyLevel}
    draw_count = {lvl: 0 for lvl in DifficultyLevel}

    current_cheater: Optional[CheaterLoop] = None

    try:
        for i, level in enumerate(plan):
            print(f"=== Ep {i + 1}/{total_eps} vs {level.value} ===")

            # Relanzar sim para mapa nuevo si corresponde (igual lógica que
            # human_control --relaunch-every). No en i=0 porque ya se lanzó.
            if (launcher is not None and args.relaunch_every > 0
                    and i > 0 and i % args.relaunch_every == 0):
                print(f"  → relanzando sim (cada {args.relaunch_every} eps) para mapa nuevo...")
                if current_cheater is not None:
                    current_cheater.stop()
                    current_cheater = None
                dual.stop()
                launcher.kill()
                time.sleep(1.5)
                launcher.launch()
                time.sleep(args.sim_startup_wait)
                dual = DualClient(
                    recv_port_1=args.recv_port_1, send_port_1=args.send_port_1,
                    recv_port_2=args.recv_port_2, send_port_2=args.send_port_2,
                    send_host=args.send_host,
                )
                dual.start()
                deadline = time.time() + 15
                while time.time() < deadline:
                    snap = dual.all_latest()
                    if 1 in snap and 2 in snap:
                        break
                    time.sleep(0.1)
                if not (1 in dual.all_latest() and 2 in dual.all_latest()):
                    print("  ⚠️  Sin telemetría tras relanzar. Skip.")
                    continue

            # Re-instanciar cheater con el nivel correcto (params + state nuevos)
            if current_cheater is not None:
                current_cheater.stop()
            current_cheater = CheaterLoop(
                dual=dual, level=level,
                tick_dt=args.tick_dt,
                rng_seed=args.seed + 1000 + i,
            )
            current_cheater.start()

            # Esperar que arranque el episodio del sim (health=1000 ambos)
            deadline = time.time() + 20
            ready = False
            while time.time() < deadline:
                snap = dual.all_latest()
                if (1 in snap and 2 in snap and
                        snap[1].health > 990 and snap[2].health > 990):
                    ready = True
                    break
                time.sleep(0.1)
            if not ready:
                print("  ⚠️  No arrancó el episodio (health no llegó a 1000). Skip.")
                time.sleep(args.inter_episode_wait)
                continue

            records, actions, modes, ep_params, stats = run_recording_episode(
                dual, args, rng,
            )

            if not records:
                print("  ⚠️  Sin records.")
                time.sleep(args.inter_episode_wait)
                continue

            # Resultado del episodio
            last_snap = records[-1][1]
            h1 = last_snap.get(1)
            h2 = last_snap.get(2)
            won = h1 is not None and h2 is not None and h1.health > 0 and h2.health <= 0
            lost = h1 is not None and h1.health <= 0
            if won:
                win_count[level] += 1
                tag = "WIN "
            elif lost:
                loss_count[level] += 1
                tag = "LOSS"
            else:
                draw_count[level] += 1
                tag = "DRAW"

            print(f"  [{tag}] ticks={len(records):4d}  min_dist={stats['min_dist']:.0f}m  "
                  f"had_encounter={stats['had_encounter']}  modes={modes}")

            ep_arr = records_to_arrays(records, actions, modes, ep_params)
            if ep_arr is None:
                continue

            # Metadata extra del episodio (van como attrs por la convención "_")
            ep_arr["_opponent_level"] = level.value
            ep_arr["_min_distance_observed"] = float(stats["min_dist"])
            ep_arr["_had_encounter"] = bool(stats["had_encounter"])
            ep_arr["_outcome"] = "win" if won else ("loss" if lost else "draw")

            all_episodes.append(ep_arr)
            # Guardado incremental: grabamos este ep al disco antes de seguir.
            # Si el proceso muere (LCP, pkill, OOM), lo recolectado se conserva.
            append_episode_hdf5(ep_arr, args.output, ep_index=i)
            print(f"  → ep guardado incrementalmente ({len(all_episodes)} eps en total)",
                  flush=True)

            time.sleep(args.inter_episode_wait)

    except KeyboardInterrupt:
        print("\nInterrumpido.")
    finally:
        if current_cheater is not None:
            current_cheater.stop()
        dual.stop()
        if launcher is not None:
            launcher.kill()

    # NOTA: el HDF5 ya tiene todos los episodios escritos incrementalmente.
    # No re-escribimos aquí.
    if all_episodes:
        print(f"\nTotal grabado en {args.output}: {len(all_episodes)} episodios")
        print("Resumen por nivel:")
        for lvl in DifficultyLevel:
            total = win_count[lvl] + loss_count[lvl] + draw_count[lvl]
            if total == 0:
                continue
            print(f"  {lvl.value:12s} W:{win_count[lvl]:3d} L:{loss_count[lvl]:3d} "
                  f"D:{draw_count[lvl]:3d}  WR={win_count[lvl]/total:.0%}")
    else:
        print("⚠️  No se grabó nada.")


if __name__ == "__main__":
    main()
