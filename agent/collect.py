"""Recolección de dataset offline para entrenamiento.

Corre el simulador, conecta el agente con una política dada (random, scripted, o cargada),
graba todas las transiciones (s, a, r, s', done) a un archivo HDF5.

Uso:
    # Random policy, 100 episodios
    python -m agent.collect --policy random --episodes 100 --output data/random_v1.h5

    # Con simulador autolaunched
    python -m agent.collect --policy random --episodes 10 --launch-sim \\
        --sim-path ./testcase --testcase 131
"""
import argparse
import os
import time
import subprocess
import signal
import numpy as np
import h5py
from pathlib import Path

from . import packet_format as pf
from .udp_io import TelemetryClient, LobbyClient
from .state_encoder import StateEncoder, OBS_DIM_BASIC
from .dispatcher import action_to_command


def random_policy(obs: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Política random: muestrea acción uniforme en [-1, 1]^5."""
    return rng.uniform(-1, 1, size=5).astype(np.float32)


def run_episode(
    tel_client: TelemetryClient,
    encoder: StateEncoder,
    policy_fn,
    rng: np.random.Generator,
    max_ticks: int = 5000,
    tick_dt: float = 0.02,
    vehicle_id: int = 1,
):
    """Corre un episodio y devuelve tuplas (s, a, r, s', done).

    Reward dummy (placeholder) por ahora. Después se reemplaza por R real
    cuando tengamos el TickRecord del Lobby parseado.
    """
    encoder.reset()

    obs_list = []
    act_list = []
    rew_list = []
    next_obs_list = []
    done_list = []

    # Esperar primera telemetría
    mr = tel_client.wait_for_first(timeout=10.0)
    if mr is None:
        print("  ⚠️  Sin telemetría. Episodio descartado.")
        return None

    last_obs = encoder.encode(mr, last_action_fire=False)
    last_health = mr.health
    last_action_fire = False

    for tick in range(max_ticks):
        # 1. Política decide
        action = policy_fn(last_obs, rng)

        # 2. Construir y enviar comando
        cmd = action_to_command(action, controlling_id=vehicle_id, current_state=mr)
        tel_client.send_command(cmd)
        last_action_fire = (cmd.command == pf.CMD_FIRE)

        # 3. Esperar tick
        time.sleep(tick_dt)

        # 4. Recibir nueva telemetría
        mr = tel_client.latest()
        if mr is None:
            done = True
            break
        obs = encoder.encode(mr, last_action_fire=last_action_fire)

        # 5. Reward (versión muy básica, sin Lobby por ahora)
        delta_h = last_health - mr.health
        extra_dmg = max(0.0, delta_h - 1.0)  # restar desgaste de 1/tick
        reward = -5.0 * extra_dmg + 0.04  # daño extra + step bonus

        # Penalty por disparar
        if last_action_fire:
            reward -= 0.3

        # Terminal por health
        done = mr.health <= 0
        if done:
            reward -= 500
        last_health = mr.health

        # Almacenar transición
        obs_list.append(last_obs)
        act_list.append(action)
        rew_list.append(reward)
        next_obs_list.append(obs)
        done_list.append(done)

        last_obs = obs

        if done:
            break

    return {
        "observations": np.array(obs_list, dtype=np.float32),
        "actions": np.array(act_list, dtype=np.float32),
        "rewards": np.array(rew_list, dtype=np.float32),
        "next_observations": np.array(next_obs_list, dtype=np.float32),
        "terminals": np.array(done_list, dtype=bool),
        "n_ticks": len(obs_list),
        "total_reward": float(np.sum(rew_list)),
    }


def save_dataset_hdf5(episodes, output_path):
    """Guarda lista de episodios en HDF5 (formato compatible con d3rlpy)."""
    # Concatenar todos los episodios en arrays planos
    obs = np.concatenate([ep["observations"] for ep in episodes])
    actions = np.concatenate([ep["actions"] for ep in episodes])
    rewards = np.concatenate([ep["rewards"] for ep in episodes])
    next_obs = np.concatenate([ep["next_observations"] for ep in episodes])
    terminals = np.concatenate([ep["terminals"] for ep in episodes])

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(output_path, "w") as f:
        f.create_dataset("observations", data=obs, compression="gzip")
        f.create_dataset("actions", data=actions, compression="gzip")
        f.create_dataset("rewards", data=rewards, compression="gzip")
        f.create_dataset("next_observations", data=next_obs, compression="gzip")
        f.create_dataset("terminals", data=terminals, compression="gzip")
        f.attrs["n_episodes"] = len(episodes)
        f.attrs["obs_dim"] = obs.shape[1]
        f.attrs["action_dim"] = actions.shape[1]
        f.attrs["total_transitions"] = len(obs)

    print(f"✓ Dataset guardado: {output_path}")
    print(f"  Episodios: {len(episodes)}")
    print(f"  Total transiciones: {len(obs)}")
    print(f"  Tamaño en disco: {os.path.getsize(output_path) / 1e6:.1f} MB")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", choices=["random"], default="random")
    parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--output", type=str, default="data/dataset.h5")
    parser.add_argument("--max-ticks", type=int, default=5000)
    parser.add_argument("--tick-dt", type=float, default=0.02)
    parser.add_argument("--telemetry-port", type=int, default=4501)
    parser.add_argument("--vehicle-id", type=int, default=1)
    parser.add_argument("--launch-sim", action="store_true",
                        help="Lanzar el simulador automáticamente entre episodios")
    parser.add_argument("--sim-path", type=str, default="./testcase",
                        help="Path al ejecutable del simulador")
    parser.add_argument("--testcase", type=int, default=131)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)

    policy_fn = {
        "random": random_policy,
    }[args.policy]

    encoder = StateEncoder()

    print(f"Recolectando {args.episodes} episodios con política '{args.policy}'")
    print(f"Output: {args.output}")

    sim_process = None
    episodes = []

    try:
        for ep_idx in range(args.episodes):
            print(f"\n=== Episodio {ep_idx + 1}/{args.episodes} ===")

            # Lanzar simulador si se pidió
            if args.launch_sim:
                if sim_process:
                    sim_process.terminate()
                    sim_process.wait()
                sim_process = subprocess.Popen([
                    args.sim_path, "-mute", "-nointro",
                    "-testcase", str(args.testcase),
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(2.0)  # esperar inicialización

            # Conectar
            tel = TelemetryClient(
                recv_port=args.telemetry_port,
                send_port=args.telemetry_port,
            )
            tel.start()

            # Correr episodio
            ep_data = run_episode(
                tel, encoder, policy_fn, rng,
                max_ticks=args.max_ticks,
                tick_dt=args.tick_dt,
                vehicle_id=args.vehicle_id,
            )

            tel.stop()

            if ep_data is not None:
                episodes.append(ep_data)
                print(f"  ✓ {ep_data['n_ticks']} ticks, "
                      f"G = {ep_data['total_reward']:.1f}")
            else:
                print(f"  ✗ Episodio fallido")

    except KeyboardInterrupt:
        print("\n\nInterrumpido. Guardando lo recolectado hasta acá...")
    finally:
        if sim_process:
            sim_process.terminate()
            try:
                sim_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                sim_process.kill()

    if episodes:
        save_dataset_hdf5(episodes, args.output)
    else:
        print("⚠️  No se recolectaron episodios.")


if __name__ == "__main__":
    main()
