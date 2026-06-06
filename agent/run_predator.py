"""Corre PREDATOR_V2 standalone controlando un vehículo del sim.

El vehículo opuesto lo controla un agente remoto (otra máquina).
Usalo para el match LAN: sim local + predator_v2 (vos) vs agente remoto.

Setup esperado:
    Terminal A:  ./testcase -mute -nointro
    Terminal B:  python -m agent.run_predator --vehicle-id 1

Para el EXAMEN (sim en otra máquina, ej. 192.168.0.105):
    python -m agent.run_predator --vehicle-id 1   # default toma IP de
                                                  # scripts/Configuration.py

Ctrl-C para salir.
"""
import argparse
import sys
import time
from pathlib import Path

from .calibrate_cheaters import CheaterArenaLoop, DualClient
from .cheater_policy import DifficultyLevel


def _default_send_host() -> str:
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import Configuration  # type: ignore
        return getattr(Configuration, "ip", "127.0.0.1")
    except Exception:
        return "127.0.0.1"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--vehicle-id", type=int, default=1, choices=[1, 2])
    p.add_argument("--level", type=str, default="predator_v2",
                   choices=["easy", "medium", "hard", "impossible",
                            "predator", "predator_v2"])
    p.add_argument("--send-host", type=str, default=None,
                   help="IP del servidor (sim). Default = scripts/Configuration.py o 127.0.0.1.")
    p.add_argument("--tick-dt", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    send_host = args.send_host or _default_send_host()
    dual = DualClient(send_host=send_host)
    dual.start()
    print(f"Escuchando telemetría en 4601/4602, mando comandos a {send_host}:4501/4502.")
    print(f"Yo controlo vehículo #{args.vehicle_id} con {args.level}.")

    deadline = time.time() + 15
    while time.time() < deadline:
        snap = dual.all_latest()
        if 1 in snap and 2 in snap:
            break
        time.sleep(0.1)
    if not (1 in dual.all_latest() and 2 in dual.all_latest()):
        print("⚠️  Sin telemetría de ambos vehículos. ¿Sim arriba? ¿Compañero conectado?")
        dual.stop()
        return
    print("✓ Telemetría OK. Arrancando loop.\n")

    loop = CheaterArenaLoop(
        dual, DifficultyLevel(args.level),
        vehicle_id=args.vehicle_id,
        tick_dt=args.tick_dt,
        rng_seed=args.seed,
    )
    loop.start()

    try:
        while True:
            time.sleep(1.0)
            snap = dual.all_latest()
            a = snap.get(1); b = snap.get(2)
            if a and b:
                print(f"  h1={a.health:.0f}  h2={b.health:.0f}")
                if a.health <= 0 or b.health <= 0:
                    print("Fin del round.")
                    break
    except KeyboardInterrupt:
        print("\nInterrumpido.")
    finally:
        loop.stop()
        dual.stop()


if __name__ == "__main__":
    main()
