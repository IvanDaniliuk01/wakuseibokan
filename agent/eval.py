"""Evaluación de un modelo entrenado contra el simulador.

Carga un modelo (.pt de d3rlpy o .zip de stable-baselines3) y lo corre
contra el simulador, midiendo win rate, retorno promedio, etc.

Uso:
    python -m agent.eval --model models/otter_cql_v1.pt --episodes 50
"""
import argparse
import time
import numpy as np
import torch
from pathlib import Path

from . import packet_format as pf
from .udp_io import TelemetryClient
from .state_encoder import StateEncoder, OBS_DIM_BASIC
from .dispatcher import action_to_command


def load_d3rlpy_model(path: str):
    """Carga un modelo .pt guardado desde d3rlpy.

    Devuelve una función `policy(obs) -> action`.
    """
    checkpoint = torch.load(path, map_location="cpu")
    print(f"Modelo cargado de {path}")
    print(f"  obs_dim: {checkpoint['obs_dim']}")
    print(f"  action_dim: {checkpoint['action_dim']}")

    # TODO: reconstruir la policy desde state_dict
    # Por ahora devolvemos random como placeholder
    def policy(obs):
        return np.random.uniform(-1, 1, size=checkpoint["action_dim"]).astype(np.float32)
    return policy


def load_sb3_model(path: str):
    """Carga un modelo .zip de stable-baselines3."""
    from stable_baselines3 import SAC
    model = SAC.load(path, device="cpu")

    def policy(obs):
        action, _ = model.predict(obs, deterministic=True)
        return action
    return policy


def run_eval_episode(
    tel_client: TelemetryClient,
    encoder: StateEncoder,
    policy_fn,
    max_ticks: int = 5000,
    tick_dt: float = 0.02,
    vehicle_id: int = 1,
):
    """Corre un episodio de evaluación."""
    encoder.reset()
    total_reward = 0.0
    n_ticks = 0
    initial_health = 1000.0
    final_health = 0.0
    won = False

    mr = tel_client.wait_for_first(timeout=10.0)
    if mr is None:
        return {"error": "no_telemetry"}

    obs = encoder.encode(mr, last_action_fire=False)
    last_health = mr.health
    initial_health = mr.health

    for tick in range(max_ticks):
        # Política
        action = policy_fn(obs)

        # Comando
        cmd = action_to_command(action, controlling_id=vehicle_id, current_state=mr)
        tel_client.send_command(cmd)
        last_action_fire = (cmd.command == pf.CMD_FIRE)

        time.sleep(tick_dt)
        mr = tel_client.latest()
        if mr is None:
            break

        obs = encoder.encode(mr, last_action_fire=last_action_fire)

        # Reward (mismo cálculo que collect.py para comparabilidad)
        delta_h = last_health - mr.health
        extra_dmg = max(0.0, delta_h - 1.0)
        r = -5.0 * extra_dmg + 0.04
        if last_action_fire:
            r -= 0.3
        if mr.health <= 0:
            r -= 500
            total_reward += r
            break

        total_reward += r
        last_health = mr.health
        n_ticks += 1

    final_health = mr.health if mr else 0
    won = final_health > 0 and n_ticks < max_ticks  # heurística: sobrevivimos

    return {
        "ticks": n_ticks,
        "total_reward": total_reward,
        "initial_health": initial_health,
        "final_health": final_health,
        "won": won,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, required=True,
                        help="Path al modelo (.pt de d3rlpy o .zip de SB3)")
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--telemetry-port", type=int, default=4501)
    parser.add_argument("--vehicle-id", type=int, default=1)
    parser.add_argument("--tick-dt", type=float, default=0.02)
    args = parser.parse_args()

    # Cargar modelo
    if args.model.endswith(".zip"):
        policy_fn = load_sb3_model(args.model)
    else:
        policy_fn = load_d3rlpy_model(args.model)

    encoder = StateEncoder()

    # Conectar
    tel = TelemetryClient(
        recv_port=args.telemetry_port,
        send_port=args.telemetry_port,
    )
    tel.start()

    # Correr episodios
    results = []
    wins = 0
    print(f"\nEvaluando modelo en {args.episodes} episodios...")
    print("=" * 60)

    for ep in range(args.episodes):
        result = run_eval_episode(
            tel, encoder, policy_fn,
            tick_dt=args.tick_dt,
            vehicle_id=args.vehicle_id,
        )
        if "error" in result:
            print(f"Ep {ep + 1}: ERROR {result['error']}")
            continue

        if result["won"]:
            wins += 1
        results.append(result)
        win_rate = wins / (ep + 1)
        print(f"Ep {ep + 1:2d}: ticks={result['ticks']:4d}  "
              f"G={result['total_reward']:7.1f}  "
              f"final_health={result['final_health']:.0f}  "
              f"{'✓ WIN' if result['won'] else '✗ LOSS'}  "
              f"win_rate={win_rate:.2%}")

    tel.stop()

    # Stats finales
    if results:
        rewards = [r["total_reward"] for r in results]
        ticks = [r["ticks"] for r in results]
        print("\n" + "=" * 60)
        print(f"Stats finales:")
        print(f"  Win rate:    {wins / len(results):.2%}  ({wins}/{len(results)})")
        print(f"  Retorno:     {np.mean(rewards):.1f} ± {np.std(rewards):.1f}")
        print(f"  Duración:    {np.mean(ticks):.0f} ± {np.std(ticks):.0f} ticks")


if __name__ == "__main__":
    main()
