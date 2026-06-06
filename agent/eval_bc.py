"""Eval del modelo BC entrenado vs un cheater como oponente.

El Otter 1 (vid=1) lo controla el modelo BC entrenado (cargado desde .pt).
El Otter 2 (vid=2) lo controla un cheater configurable (default: predator_v2).

USO:
    # Terminal A: ./testcase -mute -nointro -episodes
    # Terminal B:
    python -m agent.eval_bc --model models/bc_otter.pt \\
        --opponent predator_v2 --episodes 30
"""
import argparse
import math
import time
from threading import Event, Lock, Thread
from typing import Optional

import numpy as np
import torch

from .calibrate_cheaters import CheaterArenaLoop, DualClient
from .cheater_policy import (
    DifficultyLevel, params_for_level, init_state as init_cheater_state,
    decide as cheater_decide,
)
from .encoders import (
    OBS_DIM, OBS_DIM_FULL, ACT_DIM, THRUST_MAX,
    encode_state, encode_state_full, decode_action, build_command,
)
from .train_bc import BCPolicy


# ============================================================
# Loop del agente BC controlando Otter 1
# ============================================================

class BCAgentLoop:
    """Controla el Otter `vid` con un modelo BC PyTorch.

    Si `target_mode == "movement"`, el BC predice sólo [thrust, steering] y
    el aim+fire los aporta el cheater scripted (preset configurable). Útil
    cuando el dataset no tiene señal de combate suficiente para aprender aim.
    """

    def __init__(self, dual: DualClient, vid: int, opponent_vid: int,
                 model: BCPolicy, encoder: str = "full",
                 target_mode: str = "full",
                 aim_assist_level: str = "predator_v2",
                 tick_dt: float = 0.05, seed: int = 0):
        self.dual = dual
        self.vid = vid
        self.opponent_vid = opponent_vid
        self.model = model
        self.encoder = encoder
        self.target_mode = target_mode
        self.tick_dt = tick_dt
        self._stop = Event()
        self._thread: Optional[Thread] = None
        self.last_action = None  # debug
        # Cheater para aim+fire cuando target_mode == "movement"
        if target_mode == "movement":
            self.aim_params = params_for_level(aim_assist_level)
            self.aim_state = init_cheater_state(self.aim_params)
            self.aim_rng = np.random.default_rng(seed)
        else:
            self.aim_params = self.aim_state = self.aim_rng = None

    def start(self):
        self._stop.clear()
        # Reset cheater state al arrancar episodio
        if self.target_mode == "movement":
            self.aim_state = init_cheater_state(self.aim_params)
        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self):
        self.model.eval()
        while not self._stop.is_set():
            time.sleep(self.tick_dt)
            snap = self.dual.all_latest()
            if self.vid not in snap or self.opponent_vid not in snap:
                continue
            my = snap[self.vid]
            other = snap[self.opponent_vid]
            if my.health <= 0 or other.health <= 0:
                continue

            if self.encoder == "full":
                obs = encode_state_full(my, other)
            else:
                obs = encode_state(my, other)
            with torch.no_grad():
                x = torch.from_numpy(obs).float().unsqueeze(0)
                action = self.model(x).cpu().numpy()[0]

            self.last_action = action

            if self.target_mode == "movement":
                # BC: thrust + steering. Cheater scripted: turret + fire.
                bc_thrust = float(np.clip(action[0], -1.0, 1.0)) * THRUST_MAX
                bc_steering = float(np.clip(action[1], -1.0, 1.0))
                # Llamar al cheater sólo para obtener turret_decl, turret_bearing, fire.
                # Descartamos thrust/steering del cheater (los reemplaza el BC).
                _, _, td, tb, fire, _mode = cheater_decide(
                    my.pos, float(my.azimuth), float(my.health),
                    other.pos, float(other.health),
                    self.aim_params, self.aim_state, self.aim_rng,
                    my_landing_pos=tuple(my.landingPos),  # closed-loop aim correction
                )
                cmd = build_command(self.vid, bc_thrust, bc_steering,
                                     td, tb, fire, int(my.recordtimer))
            else:
                cmd = decode_action(action, my)
            self.dual.send_to_vid(self.vid, cmd.to_bytes())


# ============================================================
# Loop principal: corre N eps BC vs cheater
# ============================================================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", type=str, required=True,
                   help="Path al checkpoint .pt del BC")
    p.add_argument("--opponent", type=str, default="predator_v2",
                   choices=["easy", "medium", "hard", "impossible",
                            "predator", "predator_v2"])
    p.add_argument("--episodes", type=int, default=20)
    p.add_argument("--max-seconds", type=int, default=120)
    p.add_argument("--tick-dt", type=float, default=0.05)
    p.add_argument("--inter-episode-wait", type=float, default=4.0)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    # Cargar modelo
    print(f"Cargando modelo: {args.model}")
    ckpt = torch.load(args.model, map_location="cpu", weights_only=False)
    encoder = ckpt.get("encoder", "simple")
    target_mode = ckpt.get("target_mode", "full")  # default full para compat
    hidden = ckpt.get("hidden", 128)
    dropout = ckpt.get("dropout", 0.0)
    model = BCPolicy(obs_dim=ckpt.get("obs_dim", OBS_DIM),
                     act_dim=ckpt.get("act_dim", ACT_DIM),
                     hidden=hidden, dropout=dropout)
    model.load_state_dict(ckpt["state_dict"])
    print(f"  encoder: {encoder}  obs_dim: {model.obs_dim}  hidden: {hidden}")
    print(f"  target_mode: {target_mode}  act_dim: {model.act_dim}")
    print(f"  args originales: {ckpt.get('args', {})}")
    print(f"  meta: {ckpt.get('meta', {})}\n")

    opponent_level = DifficultyLevel(args.opponent)
    print(f"BC agent (Otter 1) vs {args.opponent} (Otter 2) — {args.episodes} eps\n")

    dual = DualClient()
    dual.start()

    print("Esperando telemetría...")
    deadline = time.time() + 15
    while time.time() < deadline:
        snap = dual.all_latest()
        if 1 in snap and 2 in snap:
            break
        time.sleep(0.1)
    if not (1 in dual.all_latest() and 2 in dual.all_latest()):
        print("⚠️  Sin telemetría. ¿Sim corriendo?")
        dual.stop()
        return
    print("✓ OK\n")

    wins = losses = draws = 0
    bc_agent: Optional[BCAgentLoop] = None
    cheater: Optional[CheaterArenaLoop] = None

    try:
        for i in range(args.episodes):
            print(f"=== Ep {i+1}/{args.episodes} vs {args.opponent} ===")

            # Reset loops
            if bc_agent is not None: bc_agent.stop()
            if cheater is not None: cheater.stop()

            bc_agent = BCAgentLoop(dual, vid=1, opponent_vid=2,
                                   model=model, encoder=encoder,
                                   target_mode=target_mode,
                                   aim_assist_level="predator_v2",
                                   tick_dt=args.tick_dt,
                                   seed=args.seed + i)
            cheater = CheaterArenaLoop(
                dual, opponent_level, vehicle_id=2,
                tick_dt=args.tick_dt,
                rng_seed=args.seed + 100 * i + 50,
                episode_idx=i + 1,
            )

            # Esperar arranque
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
                print("  ⚠️  No arrancó. Skip.")
                time.sleep(args.inter_episode_wait)
                continue

            bc_agent.start()
            cheater.start()

            start = time.time()
            last_timer = -1
            no_update = 0
            while time.time() - start < args.max_seconds:
                time.sleep(0.1)
                snap = dual.all_latest()
                if not snap:
                    continue
                if any(mr.health <= 0 for mr in snap.values()):
                    break
                cur_t = max(mr.recordtimer for mr in snap.values())
                if cur_t == last_timer:
                    no_update += 1
                    if no_update > 50:
                        break
                else:
                    no_update = 0; last_timer = cur_t

            bc_agent.stop()
            cheater.stop()

            snap = dual.all_latest()
            a = snap.get(1); b = snap.get(2)
            won = a is not None and b is not None and a.health > 0 and b.health <= 0
            lost = a is not None and a.health <= 0
            outcome = "WIN " if won else ("LOSS" if lost else "DRAW")
            if won: wins += 1
            elif lost: losses += 1
            else: draws += 1

            ticks = int((time.time() - start) / args.tick_dt)
            print(f"  [{outcome}]  h_a={a.health if a else '?':.0f}  "
                  f"h_b={b.health if b else '?':.0f}  ticks~{ticks}")
            time.sleep(args.inter_episode_wait)

    except KeyboardInterrupt:
        print("\nInterrumpido.")
    finally:
        if bc_agent: bc_agent.stop()
        if cheater: cheater.stop()
        dual.stop()

    n = wins + losses + draws
    print("\n" + "=" * 50)
    if n == 0:
        print("Sin episodios completados.")
        return
    print(f"Eval: BC vs {args.opponent}")
    print(f"  Episodios: {n}")
    print(f"  Wins:   {wins:3d} ({100*wins/n:.0f}%)")
    print(f"  Losses: {losses:3d} ({100*losses/n:.0f}%)")
    print(f"  Draws:  {draws:3d} ({100*draws/n:.0f}%)")


if __name__ == "__main__":
    main()
