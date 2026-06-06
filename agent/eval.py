"""Eval del modelo CQL entrenado contra SeekAndDestroy o cheater.

Setup esperado:
    # Terminal A: ./testcase -mute -nointro -episodes
    # Terminal B: cd scripts && python3 SeekAndDestroy.py 2   # rival
    # Terminal C: python -m agent.eval --model models/otter_cql_v1.d3 --episodes 10

Carga el modelo formato `.d3` (nativo de d3rlpy) bajado de Colab.

Los encoders están en agent/encoders.py (compartidos con env.py y training).
"""
import argparse
import time
import numpy as np
from threading import Lock

from . import packet_format as pf
from .udp_io import UDPClient
from .encoders import OBS_DIM, ACT_DIM, encode_state, decode_action


# ============================================================
# Cargar modelo CQL
# ============================================================

def load_cql_model(path: str):
    """Carga modelo .d3 de d3rlpy y devuelve fn predict(obs) -> action."""
    try:
        import torch as _torch
        import d3rlpy
    except ImportError:
        raise SystemExit(
            "Falta d3rlpy. Instalá con:\n"
            "    pip install d3rlpy torch\n"
            "(torch ~750 MB)"
        )
    # PyTorch 2.6+ default weights_only=True rompe carga de d3rlpy.
    _orig_load = _torch.load
    def _patched_load(*a, **kw):
        kw.setdefault("weights_only", False)
        return _orig_load(*a, **kw)
    _torch.load = _patched_load

    # Los .d3 de checkpoint son formato compuesto de d3rlpy (metadata + weights).
    # Hay que usar load_learnable, NO cql.load_model().
    cql = d3rlpy.load_learnable(path, device="cpu:0")
    print(f"✓ Modelo {path} cargado (action_size={cql.action_size})")

    def predict(obs: np.ndarray) -> np.ndarray:
        return cql.predict(obs.reshape(1, -1))[0]

    return predict


# ============================================================
# Episodio
# ============================================================

def run_episode(mini, predict_fn, vehicle_id, max_seconds=90, tick_dt=0.05):
    start = time.time()
    last_timer = -1
    no_update = 0
    episode_started = False
    n_ticks = 0
    h0_me = h0_oth = None
    hf_me = hf_oth = None

    while time.time() - start < max_seconds:
        time.sleep(tick_dt)
        snap = mini.all_latest()
        if not snap:
            continue

        valid = {vid: mr for vid, mr in snap.items() if mr.health > -1000}
        if vehicle_id not in valid:
            continue
        others = [v for v in valid if v != vehicle_id]
        if not others:
            continue

        my_mr = valid[vehicle_id]
        other_mr = valid[others[0]]

        if not episode_started:
            if all(mr.health > 0 for mr in valid.values()):
                episode_started = True
                h0_me, h0_oth = my_mr.health, other_mr.health
            else:
                continue

        n_ticks += 1
        obs = encode_state(my_mr, other_mr)
        action = predict_fn(obs)
        cmd = decode_action(action, my_mr)
        mini.send_bytes(cmd.to_bytes())

        hf_me, hf_oth = my_mr.health, other_mr.health

        if any(mr.health <= 0 for mr in valid.values()):
            break

        cur_t = max(mr.recordtimer for mr in valid.values())
        if cur_t == last_timer:
            no_update += 1
            if no_update > 100:
                break
        else:
            no_update = 0
            last_timer = cur_t

    won = hf_me is not None and hf_me > 0 and hf_oth is not None and hf_oth <= 0
    lost = hf_me is not None and hf_me <= 0
    return {
        "ticks": n_ticks,
        "h0_me": h0_me, "hf_me": hf_me,
        "h0_oth": h0_oth, "hf_oth": hf_oth,
        "won": won, "lost": lost,
        "draw": not won and not lost,
    }


# ============================================================
# Main
# ============================================================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", type=str, required=True,
                   help="Path al .d3 entrenado en Colab")
    p.add_argument("--episodes", type=int, default=10)
    p.add_argument("--vehicle-id", type=int, default=1)
    p.add_argument("--recv-port", type=int, default=None)
    p.add_argument("--send-port", type=int, default=None)
    p.add_argument("--send-host", type=str, default="127.0.0.1")
    p.add_argument("--max-seconds", type=int, default=90)
    p.add_argument("--tick-dt", type=float, default=0.05)
    p.add_argument("--inter-episode-wait", type=float, default=3.0)
    args = p.parse_args()

    if args.recv_port is None:
        args.recv_port = 4600 + args.vehicle_id
    if args.send_port is None:
        args.send_port = 4500 + args.vehicle_id

    print(f"[Eval CQL] Otter #{args.vehicle_id}  recv:{args.recv_port} send:{args.send_port}")
    print(f"  model: {args.model}")
    print(f"  Asegurate de que SeekAndDestroy controla al Otter #"
          f"{2 if args.vehicle_id == 1 else 1}.\n")

    predict = load_cql_model(args.model)

    client = UDPClient(recv_port=args.recv_port, send_host=args.send_host,
                       send_port=args.send_port)
    latest = {}
    lock = Lock()

    def on_packet(data):
        if len(data) != pf.MODEL_RECORD_SIZE:
            return
        try:
            mr = pf.ModelRecord.from_bytes(data)
        except Exception:
            return
        with lock:
            latest[mr.number] = mr

    class Mini:
        def all_latest(self_):
            with lock:
                return dict(latest)
        def send_bytes(self_, data):
            client.send_bytes(data)

    client.start(on_packet)
    mini = Mini()

    print("Esperando telemetría...")
    deadline = time.time() + 15
    while time.time() < deadline and not mini.all_latest():
        time.sleep(0.1)
    if not mini.all_latest():
        print("⚠️  No llega telemetría.")
        client.stop()
        return
    print(f"✓ Vehículos vistos: {sorted(mini.all_latest().keys())}\n")

    results = []
    w = l = d = 0
    try:
        for i in range(args.episodes):
            print(f"=== Ep {i + 1}/{args.episodes} ===")
            res = run_episode(mini, predict, args.vehicle_id,
                               max_seconds=args.max_seconds, tick_dt=args.tick_dt)
            tag = "WIN " if res["won"] else ("LOSS" if res["lost"] else "DRAW")
            w += int(res["won"]); l += int(res["lost"]); d += int(res["draw"])
            print(f"  [{tag}] ticks={res['ticks']:4d}  "
                  f"me {res['h0_me']:.0f}→{res['hf_me']:.0f}  "
                  f"oth {res['h0_oth']:.0f}→{res['hf_oth']:.0f}")
            results.append(res)
            time.sleep(args.inter_episode_wait)
    except KeyboardInterrupt:
        print("\nInterrumpido.")
    finally:
        client.stop()

    n = len(results)
    if n:
        print("\n" + "=" * 50)
        print(f"Win rate:  {w / n:.1%}  ({w}/{n})")
        print(f"Loss rate: {l / n:.1%}  ({l}/{n})")
        print(f"Draw rate: {d / n:.1%}  ({d}/{n})")
        avg_ticks = float(np.mean([r["ticks"] for r in results]))
        print(f"Duración promedio: {avg_ticks:.0f} ticks (~{avg_ticks * 0.05:.0f}s)")


if __name__ == "__main__":
    main()
