"""Arena: enfrentar dos cheaters de cualquier nivel y reportar win-rate.

Útil para calibrar dificultad ANTES del run de recolección masivo. No graba
nada — solo dos threads de cheater compitiendo + score al final.

Uso típico:
    # Terminal A:
    ./testcase -mute -nointro -episodes
    # Terminal B (validar que predator > hard):
    python -m agent.calibrate_cheaters --a predator --b hard --episodes 10

Argumentos:
    --a, --b      nivel de cada cheater (easy/medium/hard/impossible/predator)
    --episodes    cuántos episodios correr
"""
import argparse
import math
import os
import time
from datetime import datetime
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Optional, TextIO

import numpy as np

from . import packet_format as pf
from .udp_io import UDPClient
from .cheater_policy import (
    DifficultyLevel,
    decide as cheater_decide,
    init_state as cheater_init_state,
    params_for_level,
)
from .encoders import build_command
from .policy_utils import relative_bearing_deg


# ============================================================
# Cliente UDP dual (igual patrón que collect_vs_cheater)
# ============================================================

class DualClient:
    def __init__(self, recv_port_1=4601, send_port_1=4501,
                 recv_port_2=4602, send_port_2=4502,
                 send_host="127.0.0.1"):
        self.c1 = UDPClient(recv_port_1, send_host, send_port_1, buffer_size=128)
        self.c2 = UDPClient(recv_port_2, send_host, send_port_2, buffer_size=128)
        self._lock = Lock()
        self.latest = {}

    def _handler(self, data):
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

    def send_to_vid(self, vid: int, data: bytes):
        if vid == 1:
            self.c1.send_bytes(data)
        else:
            self.c2.send_bytes(data)

    def stop(self):
        self.c1.stop()
        self.c2.stop()


# ============================================================
# Cheater loop genérico (vehicle_id parametrizable)
# ============================================================

class LogSink:
    """Sink thread-safe que escribe al archivo y/o stdout."""

    def __init__(self, file_handle: Optional[TextIO] = None, to_stdout: bool = False):
        self.fh = file_handle
        self.to_stdout = to_stdout
        self._lock = Lock()

    def write(self, line: str):
        with self._lock:
            if self.fh:
                self.fh.write(line + "\n")
                self.fh.flush()
            if self.to_stdout:
                print(line)


class CheaterArenaLoop:
    """Controla UN vehículo con un cheater. Parametrizable por vid."""

    def __init__(self, dual: DualClient, level: DifficultyLevel,
                 vehicle_id: int, tick_dt: float, rng_seed: int,
                 log_sink: Optional[LogSink] = None, debug_every: int = 10,
                 episode_idx: int = 0,
                 aim_noise_override: Optional[float] = None):
        self.dual = dual
        self.params = params_for_level(level)
        # Override de aim_noise — crea una copia del params para no mutar el preset
        if aim_noise_override is not None:
            from dataclasses import replace
            self.params = replace(self.params, aim_noise_deg=aim_noise_override)
        self.state = cheater_init_state(self.params)
        self.vid = vehicle_id
        self.opponent_vid = 2 if vehicle_id == 1 else 1
        self.tick_dt = tick_dt
        self.rng = np.random.default_rng(rng_seed)
        self.level_name = level.value
        self.log_sink = log_sink
        self.debug_every = debug_every
        self.episode_idx = episode_idx
        self._tick = 0
        # Tracking de inestabilidad: azimuth + matriz de rotación previos
        self._last_logged_az: Optional[float] = None
        self._last_logged_R: Optional["np.ndarray"] = None
        self._stop = Event()
        self._thread: Optional[Thread] = None

    def start(self):
        self._stop.clear()
        self._tick = 0
        self._last_logged_az = None
        self._last_logged_R = None
        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            time.sleep(self.tick_dt)
            snap = self.dual.all_latest()
            if self.vid not in snap or self.opponent_vid not in snap:
                continue
            my = snap[self.vid]
            other = snap[self.opponent_vid]
            if my.health <= 0 or other.health <= 0:
                continue
            thrust, steering, td, tb, fire, mode_tag = cheater_decide(
                my.pos, float(my.azimuth), float(my.health),
                other.pos, float(other.health),
                self.params, self.state, self.rng,
                my_landing_pos=tuple(my.landingPos),  # closed-loop aim correction
            )
            cmd = build_command(self.vid, thrust, steering, td, tb, fire, my.recordtimer)
            self.dual.send_to_vid(self.vid, cmd.to_bytes())
            self._tick += 1

            if self.log_sink and self._tick % self.debug_every == 0:
                # Bearing relativo al cuerpo — usa la MISMA fórmula del cheater
                dx = float(other.pos[0]) - float(my.pos[0])
                dz = float(other.pos[2]) - float(my.pos[2])
                dy = float(other.pos[1]) - float(my.pos[1])
                dist = math.sqrt(dx * dx + dz * dz)
                bearing_rel = relative_bearing_deg(
                    float(my.pos[0]), float(my.pos[2]), float(my.azimuth),
                    float(other.pos[0]), float(other.pos[2]),
                )

                # Inestabilidad rotacional
                # 1. daz = cambio de azimuth desde el último log (normalizado a [-180,180])
                cur_az = float(my.azimuth)
                if self._last_logged_az is not None:
                    raw_daz = cur_az - self._last_logged_az
                    daz = (raw_daz + 180.0) % 360.0 - 180.0
                    daz_per_tick = daz / self.debug_every
                else:
                    daz_per_tick = 0.0
                self._last_logged_az = cur_az

                # 2. tilt: derivado de la matriz. Si el "up" del cuerpo (R[1])
                # no está alineado con el +Y mundial, el cuerpo está inclinado.
                # tilt_x = inclinación lateral (roll), tilt_z = adelante/atrás (pitch)
                R = my.rotation_matrix_3x3()
                up = R[1]  # asumimos row-major: segunda fila = eje Y del cuerpo en world
                tilt_x_deg = math.degrees(math.atan2(up[0], abs(up[1]) + 1e-6))
                tilt_z_deg = math.degrees(math.atan2(up[2], abs(up[1]) + 1e-6))

                fire_marker = "FIRE" if fire else "    "
                line = (
                    f"[ep{self.episode_idx:02d} t{self._tick:4d}] "
                    f"OTTER{self.vid}({self.level_name:10s})  "
                    f"pos=({my.pos[0]:+7.0f},{my.pos[1]:+5.0f},{my.pos[2]:+7.0f}) "
                    f"az={cur_az:+6.1f}  daz/tk={daz_per_tick:+5.2f}  "
                    f"tilt=({tilt_x_deg:+5.1f},{tilt_z_deg:+5.1f})  "
                    f"h={my.health:4.0f}  pw={my.power:4d}  "
                    f"| enemy: dx={dx:+6.0f} dz={dz:+6.0f} dy={dy:+5.0f} dist={dist:5.0f} bearing={bearing_rel:+6.1f}  "
                    f"| cmd: thr={thrust:+5.1f} str={steering:+4.1f} "
                    f"td={td:+5.2f} tb={tb:+6.1f} {fire_marker} mode={mode_tag}"
                )
                self.log_sink.write(line)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def reset_state(self):
        self.state = cheater_init_state(self.params)


# ============================================================
# Run de un episodio: trackear outcome
# ============================================================

def run_episode(dual: DualClient, max_seconds: int, tick_dt: float):
    """Bloquea hasta que alguien muera o time-out. Devuelve dict con outcome."""
    start = time.time()
    last_timer = -1
    no_update = 0
    h_a_final = h_b_final = None
    h_a_min = h_b_min = 1000.0   # mínimo health observado (para detectar daño real)
    min_dist = float("inf")
    ticks = 0

    while time.time() - start < max_seconds:
        time.sleep(tick_dt)
        snap = dual.all_latest()
        if 1 not in snap or 2 not in snap:
            continue
        a = snap[1]
        b = snap[2]
        h_a_final, h_b_final = a.health, b.health
        # Trackear mínimos para detectar combate real (no hundimiento)
        if 0 < a.health < h_a_min:
            h_a_min = a.health
        if 0 < b.health < h_b_min:
            h_b_min = b.health
        # Distancia mínima entre los dos
        dx = float(a.pos[0]) - float(b.pos[0])
        dz = float(a.pos[2]) - float(b.pos[2])
        d = math.sqrt(dx * dx + dz * dz)
        if d < min_dist:
            min_dist = d
        ticks += 1

        if a.health <= 0 or b.health <= 0:
            break

        cur_t = max(a.recordtimer, b.recordtimer)
        if cur_t == last_timer:
            no_update += 1
            if no_update > 100:
                break
        else:
            no_update = 0
            last_timer = cur_t

    a_won = h_a_final is not None and h_a_final > 0 and h_b_final is not None and h_b_final <= 0
    b_won = h_b_final is not None and h_b_final > 0 and h_a_final is not None and h_a_final <= 0

    if a_won:
        result = "a_won"
    elif b_won:
        result = "b_won"
    else:
        result = "draw"

    # had_combat = alguno recibió daño "normal" (no por hundimiento catastrófico).
    # h_min entre 1 y 999 significa que recibió disparos del oponente.
    had_combat = (h_a_min < 1000) or (h_b_min < 1000)

    return {
        "result": result,
        "ticks": ticks,
        "h_a_final": h_a_final,
        "h_b_final": h_b_final,
        "h_a_min": h_a_min,
        "h_b_min": h_b_min,
        "min_dist": min_dist if min_dist != float("inf") else -1.0,
        "had_combat": had_combat,
    }


# ============================================================
# Main
# ============================================================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--a", type=str, required=True,
                   choices=["easy", "medium", "hard", "impossible", "predator", "predator_v2"],
                   help="Nivel del Otter 1")
    p.add_argument("--b", type=str, required=True,
                   choices=["easy", "medium", "hard", "impossible", "predator", "predator_v2"],
                   help="Nivel del Otter 2")
    p.add_argument("--episodes", type=int, default=10)
    p.add_argument("--max-seconds", type=int, default=95,
                   help="Timeout del cliente. El sim corta el match a 100s "
                        "(DEFAULT_MATCH_DURATION=5000 ticks @ 50Hz). 95 deja margen.")
    p.add_argument("--tick-dt", type=float, default=0.05)
    p.add_argument("--inter-episode-wait", type=float, default=6.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--debug", action="store_true",
                   help="Imprimir telemetría + comando UDP cada N ticks por vehículo a stdout.")
    p.add_argument("--debug-every", type=int, default=10,
                   help="Cada cuántos ticks loguear (default 10 = ~0.5s).")
    p.add_argument("--log-file", type=str, default=None,
                   help="Path a archivo donde escribir el log. Usar 'auto' para nombre "
                        "auto-generado en data/arena_<a>_vs_<b>_<timestamp>.log")
    # Overrides para tests pareados — útil para aislar el efecto de heurísticas
    # vs aim_noise (sin tener que tocar los presets de los niveles).
    p.add_argument("--a-aim-noise", type=float, default=None,
                   help="Override aim_noise_deg del Otter 1. Útil para comparaciones pareadas.")
    p.add_argument("--b-aim-noise", type=float, default=None,
                   help="Override aim_noise_deg del Otter 2.")
    args = p.parse_args()

    level_a = DifficultyLevel(args.a)
    level_b = DifficultyLevel(args.b)

    print(f"[arena] {level_a.value} (Otter 1) vs {level_b.value} (Otter 2)")
    print(f"        episodes={args.episodes}, max_seconds={args.max_seconds}")
    if args.a_aim_noise is not None:
        print(f"        OVERRIDE: A aim_noise_deg = {args.a_aim_noise}")
    if args.b_aim_noise is not None:
        print(f"        OVERRIDE: B aim_noise_deg = {args.b_aim_noise}")

    # Setup del log file
    log_fh: Optional[TextIO] = None
    log_path: Optional[str] = None
    if args.log_file:
        if args.log_file == "auto":
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_path = f"data/arena_{level_a.value}_vs_{level_b.value}_{ts}.log"
        else:
            log_path = args.log_file
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(log_path, "w")
        print(f"        log file: {log_path}")
        log_fh.write(f"# arena {level_a.value} vs {level_b.value}  episodes={args.episodes}\n")
        log_fh.write(f"# started: {datetime.now().isoformat()}\n")
        log_fh.flush()

    log_sink = LogSink(file_handle=log_fh, to_stdout=args.debug) if (log_fh or args.debug) else None
    print()

    dual = DualClient()
    dual.start()

    print("Esperando telemetría de ambos vehículos...")
    deadline = time.time() + 15
    while time.time() < deadline:
        snap = dual.all_latest()
        if 1 in snap and 2 in snap:
            break
        time.sleep(0.1)
    if not (1 in dual.all_latest() and 2 in dual.all_latest()):
        print("⚠️  No llegó telemetría. ¿Sim corriendo con -episodes?")
        dual.stop()
        return
    print("✓ Conexión OK.\n")

    a_wins = 0
    b_wins = 0
    draws = 0
    total_ticks = 0
    # Métricas filtradas por "combate real" (excluye episodios donde nunca se encontraron)
    a_wins_combat = 0
    b_wins_combat = 0
    draws_combat = 0
    combat_episodes = 0
    loop_a: Optional[CheaterArenaLoop] = None
    loop_b: Optional[CheaterArenaLoop] = None

    try:
        for i in range(args.episodes):
            # Re-instanciar para resetear estado (lead-aim history, etc.)
            if loop_a is not None:
                loop_a.stop()
            if loop_b is not None:
                loop_b.stop()
            loop_a = CheaterArenaLoop(dual, level_a, vehicle_id=1,
                                      tick_dt=args.tick_dt,
                                      rng_seed=args.seed + 100 * i,
                                      log_sink=log_sink,
                                      debug_every=args.debug_every,
                                      episode_idx=i + 1,
                                      aim_noise_override=args.a_aim_noise)
            loop_b = CheaterArenaLoop(dual, level_b, vehicle_id=2,
                                      tick_dt=args.tick_dt,
                                      rng_seed=args.seed + 100 * i + 50,
                                      log_sink=log_sink,
                                      debug_every=args.debug_every,
                                      episode_idx=i + 1,
                                      aim_noise_override=args.b_aim_noise)
            loop_a.start()
            loop_b.start()

            # Esperar arranque del episodio
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
                print(f"Ep {i + 1:2d}: ⚠️  no arrancó. Skip.")
                if log_sink:
                    log_sink.write(f"### EP {i + 1} SKIPPED (no start)")
                time.sleep(args.inter_episode_wait)
                continue

            if log_sink:
                log_sink.write(f"### EP {i + 1} START — {level_a.value} (OTTER1) vs {level_b.value} (OTTER2)")
            res = run_episode(dual, args.max_seconds, args.tick_dt)
            total_ticks += res["ticks"]
            if res["result"] == "a_won":
                a_wins += 1
                tag = f"{level_a.value} WIN"
            elif res["result"] == "b_won":
                b_wins += 1
                tag = f"{level_b.value} WIN"
            else:
                draws += 1
                tag = "DRAW"

            # Métricas filtradas por combate real
            if res["had_combat"]:
                combat_episodes += 1
                if res["result"] == "a_won":
                    a_wins_combat += 1
                elif res["result"] == "b_won":
                    b_wins_combat += 1
                else:
                    draws_combat += 1
                combat_flag = "C"
            else:
                combat_flag = "-"

            summary = (f"Ep {i + 1:2d}: [{tag}] [{combat_flag}] "
                       f"ticks={res['ticks']:4d}  h_a={res['h_a_final']:.0f}  "
                       f"h_b={res['h_b_final']:.0f}  min_dist={res['min_dist']:.0f}m")
            print(summary)
            if log_sink:
                log_sink.write(f"### EP {i + 1} END — {tag}  ticks={res['ticks']}  "
                               f"h_a={res['h_a_final']:.0f}  h_b={res['h_b_final']:.0f}")

            time.sleep(args.inter_episode_wait)

    except KeyboardInterrupt:
        print("\nInterrumpido.")
    finally:
        if loop_a:
            loop_a.stop()
        if loop_b:
            loop_b.stop()
        dual.stop()
        if log_fh:
            log_fh.write(f"# ended: {datetime.now().isoformat()}\n")
            log_fh.close()
            print(f"\nLog escrito en: {log_path}")

    total = a_wins + b_wins + draws
    if total == 0:
        print("\n⚠️  No se completó ningún episodio.")
        return

    print("\n" + "=" * 60)
    print(f"  TOTAL  ({total} eps)")
    print(f"    {level_a.value:12s} wins:  {a_wins:3d}  ({a_wins/total:.0%})")
    print(f"    {level_b.value:12s} wins:  {b_wins:3d}  ({b_wins/total:.0%})")
    print(f"    draws:              {draws:3d}  ({draws/total:.0%})")
    print(f"    avg ticks/ep:       {total_ticks/total:.0f}")
    print(f"    eps con combate:    {combat_episodes}/{total}  ({combat_episodes/total:.0%})")

    if combat_episodes > 0:
        print(f"\n  CONDICIONAL — solo episodios con combate ({combat_episodes} eps)")
        print(f"    {level_a.value:12s} wins:  {a_wins_combat:3d}  ({a_wins_combat/combat_episodes:.0%})")
        print(f"    {level_b.value:12s} wins:  {b_wins_combat:3d}  ({b_wins_combat/combat_episodes:.0%})")
        print(f"    draws:              {draws_combat:3d}  ({draws_combat/combat_episodes:.0%})")
        print(f"    ↑ Este es el número que importa para evaluar la política")
    else:
        print(f"\n  ⚠️  NINGÚN episodio tuvo combate real (todos terminaron sin")
        print(f"     que los Otters se encontraran). Re-correr o revisar setup.")
    print("=" * 60)


if __name__ == "__main__":
    main()
