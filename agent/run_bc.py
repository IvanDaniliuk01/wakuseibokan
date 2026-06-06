"""Corre el modelo BC (.pt) controlando un vehículo del sim.

Setup esperado en el EXAMEN (LAN):
    - Servidor del profe (192.168.0.105) corre `./testcase`.
    - Servidor tiene `conf/telemetry.endpoints.ini` con tu IP (192.168.0.112)
      asignada al endpoint del puerto que vas a controlar (típicamente 4601 si
      sos vehículo 1, o 4602 si sos vehículo 2).
    - Vos corrés este script en tu máquina (192.168.0.112).

USO (examen):
    python3 -m agent.run_bc --model models/bc_movement.pt --vehicle-id 1

USO (test local, sim en localhost):
    python3 -m agent.run_bc --model models/bc_movement.pt --vehicle-id 1 \\
        --send-host 127.0.0.1

Ctrl-C para salir.
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch

from .calibrate_cheaters import DualClient
from .cheater_policy import DifficultyLevel
from .eval_bc import BCAgentLoop
from .encoders import OBS_DIM, ACT_DIM
from .train_bc import BCPolicy


# IP por defecto del servidor del profe (Configuration.py del repo).
# Si no se pasa --send-host, intentamos leerla de scripts/Configuration.py.
def _default_send_host() -> str:
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import Configuration  # type: ignore
        return getattr(Configuration, "ip", "127.0.0.1")
    except Exception:
        return "127.0.0.1"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", type=str, default="models/bc_movement.pt",
                   help="Checkpoint .pt entrenado con agent.train_bc")
    p.add_argument("--vehicle-id", type=int, default=1, choices=[1, 2],
                   help="Qué vehículo controlás vos.")
    p.add_argument("--send-host", type=str, default=None,
                   help="IP del servidor (donde corre el sim). Default = "
                        "scripts/Configuration.py:ip o 127.0.0.1.")
    p.add_argument("--aim-assist-level", type=str, default="predator_v2",
                   choices=["easy", "medium", "hard", "impossible",
                            "predator", "predator_v2"],
                   help="Preset del cheater scripted para aim+fire en modo movement.")
    p.add_argument("--tick-dt", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--rounds", type=int, default=0,
                   help="Cantidad de rounds a jugar (0 = infinito, Ctrl-C para salir).")
    args = p.parse_args()

    send_host = args.send_host or _default_send_host()

    # --- Cargar modelo ---
    print(f"Cargando modelo: {args.model}")
    ckpt = torch.load(args.model, map_location="cpu", weights_only=False)
    encoder = ckpt.get("encoder", "simple")
    target_mode = ckpt.get("target_mode", "full")
    hidden = ckpt.get("hidden", 128)
    dropout = ckpt.get("dropout", 0.0)
    model = BCPolicy(obs_dim=ckpt.get("obs_dim", OBS_DIM),
                     act_dim=ckpt.get("act_dim", ACT_DIM),
                     hidden=hidden, dropout=dropout)
    model.load_state_dict(ckpt["state_dict"])
    print(f"  encoder={encoder}  obs_dim={model.obs_dim}  "
          f"hidden={hidden}  target_mode={target_mode}")
    if target_mode == "movement":
        print(f"  → BC predice [thrust, steering]; aim+fire scripted ({args.aim_assist_level})")

    # --- Conectar al servidor ---
    print(f"\nConfig de red:")
    print(f"  Servidor (sim):      {send_host}")
    print(f"  Mi rol:              vehículo #{args.vehicle_id}")
    print(f"  Escucha local:       UDP 4601, 4602")
    print(f"  Comandos a:          UDP {send_host}:4501, {send_host}:4502")
    print(f"  (recibo telemetría del puerto que el profe me asignó en su "
          f"telemetry.endpoints.ini)\n")

    dual = DualClient(send_host=send_host)
    dual.start()

    # Esperar a recibir telemetría de AMBOS vehículos
    print("Esperando telemetría de ambos vehículos...")
    deadline = time.time() + 30
    while time.time() < deadline:
        snap = dual.all_latest()
        if 1 in snap and 2 in snap:
            break
        time.sleep(0.2)
    snap = dual.all_latest()
    if not (1 in snap and 2 in snap):
        got = sorted(snap.keys())
        print(f"⚠️  Sin telemetría completa (recibí: {got}). Verificá:")
        print(f"   - El sim del profe está corriendo en {send_host}")
        print(f"   - Tu IP está en su conf/telemetry.endpoints.ini")
        print(f"   - El compañero oponente está conectado")
        dual.stop()
        return
    print("✓ Telemetría OK.\n")

    # --- Loop del BC ---
    opponent_vid = 2 if args.vehicle_id == 1 else 1
    rounds_jugados = 0
    try:
        while args.rounds == 0 or rounds_jugados < args.rounds:
            rounds_jugados += 1
            print(f"=== Round {rounds_jugados} ===")
            # Esperar arranque del round (health 1000)
            for _ in range(50):
                snap = dual.all_latest()
                a = snap.get(args.vehicle_id); b = snap.get(opponent_vid)
                if a and b and a.health > 990 and b.health > 990:
                    break
                time.sleep(0.1)

            agent = BCAgentLoop(
                dual, vid=args.vehicle_id, opponent_vid=opponent_vid,
                model=model, encoder=encoder, target_mode=target_mode,
                aim_assist_level=args.aim_assist_level,
                tick_dt=args.tick_dt, seed=args.seed + rounds_jugados,
            )
            agent.start()

            # Tickear hasta que alguien muera
            last_log = time.time()
            while True:
                time.sleep(0.5)
                snap = dual.all_latest()
                a = snap.get(args.vehicle_id); b = snap.get(opponent_vid)
                if not (a and b):
                    continue
                if time.time() - last_log > 2.0:
                    print(f"  yo(h{args.vehicle_id})={a.health:.0f}  "
                          f"enemigo(h{opponent_vid})={b.health:.0f}")
                    last_log = time.time()
                if a.health <= 0 or b.health <= 0:
                    outcome = "WIN " if (a.health > 0 and b.health <= 0) else (
                        "LOSS" if a.health <= 0 else "DRAW")
                    print(f"  [{outcome}]  final: yo={a.health:.0f}  enemigo={b.health:.0f}\n")
                    break
            agent.stop()
            # Pequeña pausa entre rounds (el sim auto-resetea si está -episodes)
            if args.rounds == 0 or rounds_jugados < args.rounds:
                time.sleep(5)
    except KeyboardInterrupt:
        print("\nInterrumpido.")
    finally:
        try:
            agent.stop()
        except Exception:
            pass
        dual.stop()


if __name__ == "__main__":
    main()
