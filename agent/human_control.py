"""Control humano del Otter 1 con auto-aim + auto-fire para imitation learning.

El humano controla SOLO el movimiento del cuerpo (thrust + steering Ackermann)
con WASD. La torreta apunta automáticamente al enemigo y dispara cuando está
en el cono de fuego (default 4°). Otter 2 lo controla un cheater configurable.

Cada episodio se graba en HDF5 con el mismo formato que `collect_vs_cheater`
para que el dataset sea compatible.

Uso típico:
    # Terminal A: sim
    ./testcase -mute -nointro -episodes
    # Terminal B (este script):
    python -m agent.human_control --opponent hard --episodes 10 \\
        --output data/human_demos_v1.h5

Controles:
    W = adelante       S = atrás
    A = girar izq      D = girar der
    Esc / Ctrl+C = salir

Nota sobre pynput: captura teclado a NIVEL DE SISTEMA (no requiere foco de
ventana). En Linux puede pedir permisos de input o necesitar correr como
parte del grupo input. Si no captura, verificar `groups | grep input`.
"""
import argparse
import math
import os
import signal
import subprocess
import time
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Optional

import h5py
import numpy as np

try:
    from pynput import keyboard
except ImportError:
    raise SystemExit(
        "Falta pynput. Instalá con:\n"
        "    python3 -m pip install --user pynput"
    )

from . import packet_format as pf
from .calibrate_cheaters import CheaterArenaLoop, DualClient
from .cheater_policy import DifficultyLevel
from collections import deque

from .encoders import build_command
from .policy_utils import (
    artillery_aim, azimuth_deg, estimate_velocity_from_history,
    estimate_vy_from_history,
    pitch_to_target_rad, relative_bearing_deg, should_use_high_arc,
)


# ============================================================
# SimLauncher: lanza/mata el sim como subprocess para cambiar mapa
# ============================================================

class SimLauncher:
    """Maneja el ciclo de vida del binario del sim. Cada `launch()` nueva
    instancia genera un mapa nuevo (porque el sim siembra con time(NULL)
    al arrancar).
    """

    def __init__(self, binary: str = "./testcase",
                 args: tuple = ("-mute", "-nointro", "-episodes"),
                 cwd: Optional[str] = None):
        self.binary = binary
        self.args = tuple(args)
        self.cwd = cwd
        self.proc: Optional[subprocess.Popen] = None

    def launch(self):
        env = os.environ.copy()
        self.proc = subprocess.Popen(
            [self.binary, *self.args],
            cwd=self.cwd,
            preexec_fn=os.setsid,  # grupo propio para killpg limpio
            env=env,
        )
        print(f"[sim] lanzado pid={self.proc.pid}")

    def kill(self):
        if self.proc is None:
            return
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            try:
                self.proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                self.proc.wait(timeout=2.0)
        except (ProcessLookupError, OSError):
            pass
        finally:
            print(f"[sim] terminado")
            self.proc = None

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None


# ============================================================
# Human loop: WASD → comandos UDP + auto-aim + auto-fire + grabación
# ============================================================

class HumanLoop:
    """Controla el Otter `vid` con teclado humano + auto-aim + auto-fire."""

    # Cooldown real del cañón en el sim: setTtl(100) en AdvancedWalrus.cpp:660.
    # 100 ticks × dWorldStep(0.05) = 2.0s. Mandar fire=True más rápido no
    # produce más disparos — el sim los descarta por `if (getTtl()>0) return`.
    FIRE_COOLDOWN_TICKS = 100

    # Si el bearing al enemigo cambia más de esto en 5 ticks, no dispares:
    # el enemigo está girando y vamos a fallar (el proyectil tarda 50 ticks
    # a 1500m). Mejor guardar el cooldown para un tiro mejor.
    BEARING_RATE_SUPPRESS_DEG = 6.0
    BEARING_RATE_WINDOW = 5

    # Auto-evasión: si la salud cae mucho en una ventana corta, sobreescribo
    # el steering del humano con dirección aleatoria que va cambiando.
    EVASION_DAMAGE_THRESHOLD = 5.0
    EVASION_WINDOW_TICKS = 30
    EVASION_DURATION_TICKS = 30
    EVASION_RESAMPLE_EVERY = 8

    # Velocidad enemiga: lookback corto → más reactivo a cambios de rumbo
    VEL_LOOKBACK = 3

    def __init__(self, dual: DualClient, vid: int, opponent_vid: int,
                 fire_cone_deg: float = 4.0, dist_fire: float = 2000.0,
                 tick_dt: float = 0.05):
        self.dual = dual
        self.vid = vid
        self.opponent_vid = opponent_vid
        self.fire_cone_deg = fire_cone_deg
        self.dist_fire = dist_fire
        self.tick_dt = tick_dt

        self.pressed: set = set()
        self._lock = Lock()
        self._stop = Event()
        self._thread: Optional[Thread] = None
        self._listener: Optional[keyboard.Listener] = None

        # Buffers de grabación del episodio actual
        self.records: list = []   # [(timestamp, {vid: ModelRecord})]
        self.actions: list = []   # [{thrust, steering, ...}]

        # Tracking del enemigo Y de MÍ MISMO para lead aim relativo:
        # cuando yo me muevo, también tengo que compensar mi propia velocidad
        # en el cálculo de dónde apuntar. Trackamos también Y para lead aim
        # vertical (parábola con target en pendiente).
        self.enemy_pos_history: deque = deque(maxlen=20)
        self.my_pos_history: deque = deque(maxlen=20)
        self.enemy_y_history: deque = deque(maxlen=20)
        self.my_y_history: deque = deque(maxlen=20)

        # Estado de cooldown / supresión / evasión
        self.ticks_since_fire: int = self.FIRE_COOLDOWN_TICKS  # arranca "listo"
        self.bearing_history: deque = deque(maxlen=self.BEARING_RATE_WINDOW + 1)
        self.health_history: deque = deque(maxlen=self.EVASION_WINDOW_TICKS + 5)
        self.evasion_left: int = 0
        self.evasion_steering: float = 0.0
        self.evasion_thrust_mult: float = 1.0
        self._evade_rng = np.random.default_rng(12345)

    # ---------- keyboard ----------

    def _on_press(self, key):
        try:
            ch = key.char
            if ch is not None:
                ch = ch.lower()
        except AttributeError:
            ch = None
        with self._lock:
            if ch is not None:
                self.pressed.add(ch)
            self.pressed.add(key)

    def _on_release(self, key):
        try:
            ch = key.char
            if ch is not None:
                ch = ch.lower()
        except AttributeError:
            ch = None
        with self._lock:
            if ch is not None:
                self.pressed.discard(ch)
            self.pressed.discard(key)

    def is_pressed(self, ch_or_key) -> bool:
        with self._lock:
            return ch_or_key in self.pressed

    # ---------- lifecycle ----------

    def set_dual(self, dual: DualClient):
        """Actualizar la referencia al DualClient (necesario tras relaunch del sim)."""
        self.dual = dual

    def start(self):
        """Arranca el listener de teclado + el loop de control."""
        self._stop.clear()
        self.records = []
        self.actions = []
        self.enemy_pos_history.clear()
        self.my_pos_history.clear()
        self.enemy_y_history.clear()
        self.my_y_history.clear()
        self.bearing_history.clear()
        self.health_history.clear()
        self.ticks_since_fire = self.FIRE_COOLDOWN_TICKS
        self.evasion_left = 0
        self.evasion_steering = 0.0
        self.evasion_thrust_mult = 1.0
        self._indicator_tick = 0
        # Limpiar pressed: si alguna tecla quedó "atascada" entre episodios
        # (porque el listener viejo se mató antes de recibir el release),
        # arrancamos de cero.
        with self._lock:
            self.pressed.clear()
        self._listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release,
        )
        self._listener.start()
        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._listener:
            self._listener.stop()
            self._listener = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    # ---------- main control loop ----------

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

            # Read keyboard → cuerpo (thrust + steering)
            # thrust_max=50 (coordinado con encoders/cheater/seek). Ver
            # agent/docs/05-thrust-max.md
            HUMAN_THRUST_MAX = 50.0
            thrust = 0.0
            steering = 0.0
            if self.is_pressed('w'):
                thrust += HUMAN_THRUST_MAX
            if self.is_pressed('s'):
                thrust -= HUMAN_THRUST_MAX
            if self.is_pressed('a'):
                steering -= 1.0
            if self.is_pressed('d'):
                steering += 1.0
            thrust = max(-HUMAN_THRUST_MAX, min(HUMAN_THRUST_MAX, thrust))
            steering = max(-1.0, min(1.0, steering))

            # Tracking del enemigo Y de mí mismo para lead aim relativo (XZ + Y).
            # Las velocidades salen en m/s (estimate_velocity_from_history
            # ahora retorna m/s, no m/tick).
            self.enemy_pos_history.append(
                (float(other.pos[0]), float(other.pos[2]))
            )
            self.my_pos_history.append(
                (float(my.pos[0]), float(my.pos[2]))
            )
            self.enemy_y_history.append(float(other.pos[1]))
            self.my_y_history.append(float(my.pos[1]))
            enemy_v_xz = estimate_velocity_from_history(
                list(self.enemy_pos_history), lookback=self.VEL_LOOKBACK,
            )
            my_v_xz = estimate_velocity_from_history(
                list(self.my_pos_history), lookback=self.VEL_LOOKBACK,
            )
            enemy_vy = estimate_vy_from_history(
                list(self.enemy_y_history), lookback=self.VEL_LOOKBACK,
            )
            my_vy = estimate_vy_from_history(
                list(self.my_y_history), lookback=self.VEL_LOOKBACK,
            )

            # Auto-aim de ARTILLERÍA: modelo balístico 3D real del sim.
            # Compensa: spawn del proyectil 40m adelante + firingpos_y=2.3m,
            # velocidad 600 m/s en dirección del cañón (incluye pitch),
            # lead aim relativo (enemigo + mi propia velocidad),
            # drop por gravedad (9.81 m/s² real).
            # Auto-selecciona arco alto cuando el enemigo está mucho más
            # abajo + a media distancia (terreno probable entre medio).
            dx_pre = float(other.pos[0]) - float(my.pos[0])
            dz_pre = float(other.pos[2]) - float(my.pos[2])
            d_pre = math.sqrt(dx_pre * dx_pre + dz_pre * dz_pre)
            arc_high = should_use_high_arc(
                float(my.pos[1]), float(other.pos[1]), d_pre,
            )
            aim_x, aim_z, pitch = artillery_aim(
                my_pos=(float(my.pos[0]), float(my.pos[1]), float(my.pos[2])),
                other_pos=(float(other.pos[0]), float(other.pos[1]), float(other.pos[2])),
                other_vel_xz=enemy_v_xz,
                my_vel_xz=my_v_xz,
                other_vel_y=enemy_vy,
                my_vel_y=my_vy,
                arc_high=arc_high,
            )
            bearing = relative_bearing_deg(
                float(my.pos[0]), float(my.pos[2]), float(my.azimuth),
                aim_x, aim_z,
            )
            # Distancia al PUNTO PREDICHO (no al enemigo actual) para fire trigger
            dx = aim_x - float(my.pos[0])
            dz = aim_z - float(my.pos[2])
            dist = math.sqrt(dx * dx + dz * dz)

            # FIX #3: auto-evasión por daño recibido.
            # Si la salud cayó > THRESHOLD en la ventana corta, activamos
            # evasión: el steering humano se reemplaza por random + steering
            # nuestro, y el thrust se modula. La torreta no se toca — sigue
            # apuntando bien (la torreta es independiente del cuerpo).
            self.health_history.append(float(my.health))
            if (self.evasion_left == 0 and
                    len(self.health_history) > self.EVASION_WINDOW_TICKS):
                h_old = self.health_history[-self.EVASION_WINDOW_TICKS]
                if (h_old - my.health) > self.EVASION_DAMAGE_THRESHOLD:
                    self.evasion_left = self.EVASION_DURATION_TICKS

            if self.evasion_left > 0:
                # Resample dirección random cada N ticks (~160ms) — imita
                # un humano panicqueado pegando volantazos.
                if (self.evasion_left % self.EVASION_RESAMPLE_EVERY) == 0:
                    self.evasion_steering = float(self._evade_rng.choice(
                        [-1.0, -0.5, 0.5, 1.0]))
                    self.evasion_thrust_mult = float(self._evade_rng.choice(
                        [-1.0, -0.5, 0.5, 1.0]))
                # Reemplazar input humano por la evasión
                steering = self.evasion_steering
                thrust = HUMAN_THRUST_MAX * self.evasion_thrust_mult
                self.evasion_left -= 1

            # FIX #2: supresión de fire cuando el ENEMIGO está girando fuerte.
            # CRÍTICO: usamos el azimuth ABSOLUTO (world frame) al enemigo, NO
            # el bearing relativo al cuerpo. Sino, cuando yo giro (WASD o auto-
            # evasión) el bearing cambia aunque el enemigo esté quieto, y nos
            # auto-suprimimos los disparos cuando más necesitamos disparar.
            world_az_to_enemy = azimuth_deg(
                float(my.pos[0]), float(my.pos[2]),
                float(other.pos[0]), float(other.pos[2]),
            )
            self.bearing_history.append(world_az_to_enemy)
            bearing_rate_high = False
            if len(self.bearing_history) >= self.BEARING_RATE_WINDOW + 1:
                d_b = self.bearing_history[-1] - self.bearing_history[0]
                d_b = (d_b + 180.0) % 360.0 - 180.0
                if abs(d_b) > self.BEARING_RATE_SUPPRESS_DEG:
                    bearing_rate_high = True

            # FIRE SPAM (post-examen jun 2026): pedimos fire=True en CADA tick
            # alineado y en rango. El sim filtra por su cooldown interno
            # (setTtl(100) en AdvancedWalrus.cpp:660). Así no perdemos ningún
            # disparo disponible. Mantenemos el counter solo para el indicador.
            self.ticks_since_fire += 1
            in_range = dist < self.dist_fire

            # FIX TOO-CLOSE: proyectil spawnea 40m adelante (AdvancedWalrus.cpp:732)
            # → si dist real al enemigo < 50m, el proyectil sale PASADO el enemigo
            # y nunca lo toca.
            real_dx_close = float(other.pos[0]) - float(my.pos[0])
            real_dz_close = float(other.pos[2]) - float(my.pos[2])
            real_dist_close = math.sqrt(real_dx_close ** 2 + real_dz_close ** 2)
            too_close = real_dist_close < 50.0

            # Sin cooldown local, sin bearing_rate_suppress — el sim manda.
            fire = (in_range and not too_close)
            if fire:
                self.ticks_since_fire = 0  # reset counter para el indicador
            cooldown_ready = True   # vestigial — siempre listo

            # ────── INDICADOR DE DISPARO (para el humano) ──────
            # Avisamos en stdout cuándo el sistema va a disparar y por qué NO
            # dispara, así el usuario sabe cuándo ir en línea recta.
            # Lo imprimimos cada ~10 ticks (5Hz) para no saturar la terminal.
            self._indicator_tick = getattr(self, "_indicator_tick", 0) + 1
            if self._indicator_tick % 10 == 0:
                ticks_left = max(0, self.FIRE_COOLDOWN_TICKS - self.ticks_since_fire)
                t_left_s = ticks_left * self.tick_dt
                if fire:
                    flag = "🔫 FIRE"
                elif too_close:
                    flag = f"⚠ MUY PEGADO ({real_dist_close:.0f}m < 50m) — retrocedé"
                elif not cooldown_ready:
                    flag = f"⏳ cooldown {t_left_s:.1f}s"
                elif bearing_rate_high:
                    flag = "↻ enemigo girando — no dispara"
                elif not in_range:
                    flag = f"📏 fuera de rango ({dist:.0f}m > {self.dist_fire:.0f})"
                else:
                    flag = "  ready"
                arc_tag = "HIGH⛰" if arc_high else "low"
                print(f"  [{flag}] dist={dist:.0f}m  pitch={math.degrees(pitch):+.1f}°  "
                      f"arc={arc_tag}  v_enemy={enemy_v_xz[0]:+.1f},{enemy_v_xz[1]:+.1f} m/s  "
                      f"ΔY={(other.pos[1] - my.pos[1]):+.1f}m")

            # Send cmd
            cmd = build_command(
                self.vid, thrust, steering, pitch, bearing, fire,
                my.recordtimer,
            )
            self.dual.send_to_vid(self.vid, cmd.to_bytes())

            # Grabar (estado completo + acción humana)
            self.records.append((time.time(), {vid: mr for vid, mr in snap.items()}))
            self.actions.append({
                "thrust": thrust, "steering": steering,
                "turret_decl": pitch, "turret_bearing": bearing,
                "fire": fire, "mode": "human",
            })


# ============================================================
# Grabación a HDF5 — formato compatible con el del cheater
# ============================================================

_MODE_HUMAN_INT = 99  # tag arbitrario para distinguir "human" en el HDF5


def human_records_to_arrays(records, actions, opponent_level: str,
                            outcome: str, min_dist: float, had_combat: bool):
    """Convierte (records, actions) del HumanLoop a dict de arrays para HDF5."""
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

    mode_int = np.full(len(actions), _MODE_HUMAN_INT, dtype=np.int8)

    return {
        "vehicle_ids": np.array(all_ids, dtype=np.int32),
        "pos": pos, "rotation": rot, "health": health, "power": power,
        "azimuth": az, "landingPos": land, "recordtimer": timer, "valid": valid_arr,
        "act_thrust": np.array([a["thrust"] for a in actions], dtype=np.float32),
        "act_steering": np.array([a["steering"] for a in actions], dtype=np.float32),
        "act_turret_decl": np.array([a["turret_decl"] for a in actions], dtype=np.float32),
        "act_turret_bearing": np.array([a["turret_bearing"] for a in actions], dtype=np.float32),
        "act_fire": np.array([a["fire"] for a in actions], dtype=bool),
        "act_mode": mode_int,
        "_human_player": True,
        "_opponent_level": opponent_level,
        "_outcome": outcome,
        "_min_distance_observed": float(min_dist),
        "_had_combat": bool(had_combat),
    }


def save_human_episodes(episodes, path):
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
        f.attrs["source"] = "human"
    print(f"✓ Dataset humano guardado en {path}  ({n} episodios)")


# ============================================================
# Main: orquesta sim ⇄ cheater oponente ⇄ human ⇄ grabación
# ============================================================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--opponent", type=str, default="hard",
                   choices=["easy", "medium", "hard", "impossible",
                            "predator", "predator_v2"],
                   help="Nivel del cheater que controla Otter 2")
    p.add_argument("--episodes", type=int, default=10)
    p.add_argument("--output", type=str, default="data/human_demos.h5")
    p.add_argument("--max-seconds", type=int, default=95)
    p.add_argument("--tick-dt", type=float, default=0.05)
    p.add_argument("--inter-episode-wait", type=float, default=6.0)
    p.add_argument("--fire-cone-deg", type=float, default=4.0,
                   help="Cono de auto-fire (default 4°)")
    p.add_argument("--dist-fire", type=float, default=700.0,
                   help="Rango máximo de auto-fire (m). Default 700 — empíricamente "
                        ">700m da 0%% hit rate por el chaotic_evasion del enemigo, "
                        "y cada miss desperdicia 2s de cooldown. Mejor reservar.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--opponent-aim-noise", type=float, default=None,
                   help="Override aim_noise_deg del cheater oponente")
    # Relanzamiento automático del sim para diversidad de mapas
    p.add_argument("--launch-sim", action="store_true",
                   help="Lanzar y manejar el sim como subprocess. Permite "
                        "relanzarlo entre episodios para variar el mapa.")
    p.add_argument("--sim-binary", type=str, default="./testcase",
                   help="Path al binario del sim (default ./testcase)")
    p.add_argument("--sim-cwd", type=str, default=None,
                   help="cwd para el sim (default: directorio actual)")
    p.add_argument("--relaunch-every", type=int, default=1,
                   help="Relanzar el sim cada N episodios (1=cada uno, 0=nunca). "
                        "Solo aplica con --launch-sim.")
    p.add_argument("--sim-startup-wait", type=float, default=3.0,
                   help="Segundos a esperar después de lanzar el sim antes de "
                        "esperar telemetría.")
    args = p.parse_args()

    opponent_level = DifficultyLevel(args.opponent)

    print("=" * 64)
    print(" HUMAN CONTROL  —  Otter 1 (vos) vs", args.opponent, "(cheater)")
    print(" Controles:  W/S  adelante/atrás  |  A/D  giro izq/der")
    print(f" Auto-fire:  cono {args.fire_cone_deg}°, rango {args.dist_fire}m")
    print(f" Output:     {args.output}")
    print(f" Episodios:  {args.episodes}")
    if args.launch_sim:
        print(f" Sim:        AUTO-LAUNCH ({args.sim_binary})")
        if args.relaunch_every > 0:
            print(f"             Relanza cada {args.relaunch_every} ep (mapa nuevo)")
    print(" Ctrl+C para terminar (graba lo que tenga hasta ahora)")
    print("=" * 64)

    # Setup del sim launcher (si está activo)
    launcher: Optional[SimLauncher] = None
    if args.launch_sim:
        launcher = SimLauncher(
            binary=args.sim_binary,
            args=("-mute", "-nointro", "-episodes"),
            cwd=args.sim_cwd,
        )
        launcher.launch()
        print(f"\nEsperando que el sim arranque ({args.sim_startup_wait}s)...")
        time.sleep(args.sim_startup_wait)

    dual = DualClient()
    dual.start()

    print("\nEsperando telemetría de ambos vehículos...")
    deadline = time.time() + 15
    while time.time() < deadline:
        snap = dual.all_latest()
        if 1 in snap and 2 in snap:
            break
        time.sleep(0.1)
    if not (1 in dual.all_latest() and 2 in dual.all_latest()):
        print("⚠️  Sin telemetría. ¿Sim corriendo con -mute -nointro -episodes?")
        dual.stop()
        if launcher:
            launcher.kill()
        return
    print("✓ Conexión OK. PRESIONÁ ESPACIO para arrancar el primer episodio "
          "(cuando el simulador esté con HUD listo)...\n")

    # Esperar Space para arrancar (le da tiempo al usuario de ubicar manos)
    space_pressed = Event()
    def _on_press_space(key):
        if key == keyboard.Key.space:
            space_pressed.set()
            return False
    waiter = keyboard.Listener(on_press=_on_press_space)
    waiter.start()
    while not space_pressed.is_set():
        time.sleep(0.1)
    waiter.stop()

    all_episodes = []
    current_cheater: Optional[CheaterArenaLoop] = None
    human = HumanLoop(
        dual, vid=1, opponent_vid=2,
        fire_cone_deg=args.fire_cone_deg,
        dist_fire=args.dist_fire,
        tick_dt=args.tick_dt,
    )

    try:
        for i in range(args.episodes):
            print(f"\n=== Ep {i + 1}/{args.episodes} vs {args.opponent} ===")

            # Relanzar sim (mapa nuevo) si está activado y corresponde
            # No en i=0 porque ya se lanzó al inicio.
            if (launcher is not None and args.relaunch_every > 0
                    and i > 0 and i % args.relaunch_every == 0):
                print("  → relanzando sim para mapa nuevo...")
                if current_cheater is not None:
                    current_cheater.stop()
                    current_cheater = None
                dual.stop()
                launcher.kill()
                time.sleep(1.5)  # dejar que el SO libere puertos UDP
                launcher.launch()
                time.sleep(args.sim_startup_wait)
                dual = DualClient()
                dual.start()
                # CRÍTICO: actualizar la referencia del HumanLoop al dual nuevo,
                # sino el control humano queda apuntando al dual viejo (que está
                # stopped) y nunca recibe telemetría.
                human.set_dual(dual)
                # Esperar telemetría tras relanzar
                deadline = time.time() + 15
                while time.time() < deadline:
                    snap = dual.all_latest()
                    if 1 in snap and 2 in snap:
                        break
                    time.sleep(0.1)
                if not (1 in dual.all_latest() and 2 in dual.all_latest()):
                    print("  ⚠️  Sin telemetría tras relanzar. Skip.")
                    continue

            # Iniciar cheater oponente
            if current_cheater is not None:
                current_cheater.stop()
            current_cheater = CheaterArenaLoop(
                dual, opponent_level, vehicle_id=2,
                tick_dt=args.tick_dt,
                rng_seed=args.seed + 100 * i + 50,
                aim_noise_override=args.opponent_aim_noise,
                episode_idx=i + 1,
            )
            current_cheater.start()

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
                print("  ⚠️  No arrancó. Skip.")
                time.sleep(args.inter_episode_wait)
                continue

            # Comenzar control + grabación humanos
            human.start()
            start = time.time()
            last_timer = -1
            no_update = 0
            min_dist = float("inf")
            h_a_min = h_b_min = 1000.0

            while time.time() - start < args.max_seconds:
                time.sleep(0.1)
                snap = dual.all_latest()
                if not snap:
                    continue
                if 1 in snap and 2 in snap:
                    a, b = snap[1], snap[2]
                    if 0 < a.health < h_a_min:
                        h_a_min = a.health
                    if 0 < b.health < h_b_min:
                        h_b_min = b.health
                    dx = float(a.pos[0]) - float(b.pos[0])
                    dz = float(a.pos[2]) - float(b.pos[2])
                    d = math.sqrt(dx * dx + dz * dz)
                    if d < min_dist:
                        min_dist = d
                if any(mr.health <= 0 for mr in snap.values()):
                    break
                cur_t = max(mr.recordtimer for mr in snap.values())
                if cur_t == last_timer:
                    no_update += 1
                    if no_update > 50:
                        break
                else:
                    no_update = 0
                    last_timer = cur_t

            # Stop control humano (mantiene buffers)
            records = list(human.records)
            actions = list(human.actions)
            human.stop()

            # Outcome
            snap = dual.all_latest()
            a = snap.get(1)
            b = snap.get(2)
            won = a is not None and b is not None and a.health > 0 and b.health <= 0
            lost = a is not None and a.health <= 0
            outcome = "win" if won else ("loss" if lost else "draw")
            had_combat = (h_a_min < 1000) or (h_b_min < 1000)
            tag = {"win": "WIN ", "loss": "LOSS", "draw": "DRAW"}[outcome]

            n_fires = sum(1 for act in actions if act["fire"])
            print(f"  [{tag}] {len(records)} ticks  min_dist={min_dist:.0f}m  "
                  f"had_combat={had_combat}  n_fires={n_fires}  "
                  f"h_a={a.health if a else '?':.0f}  h_b={b.health if b else '?':.0f}")

            ep = human_records_to_arrays(
                records, actions,
                opponent_level=args.opponent,
                outcome=outcome,
                min_dist=min_dist if min_dist != float("inf") else -1.0,
                had_combat=had_combat,
            )
            if ep is not None:
                all_episodes.append(ep)

            time.sleep(args.inter_episode_wait)

    except KeyboardInterrupt:
        print("\nInterrumpido. Guardando lo que tengo...")
    finally:
        if current_cheater:
            current_cheater.stop()
        human.stop()
        dual.stop()
        if launcher is not None:
            launcher.kill()

    if all_episodes:
        save_human_episodes(all_episodes, args.output)
        wins = sum(1 for ep in all_episodes if ep["_outcome"] == "win")
        n = len(all_episodes)
        print(f"\nResumen: {wins}/{n} wins ({wins/n:.0%}) vs {args.opponent}")
    else:
        print("⚠️  No se grabó ningún episodio.")


if __name__ == "__main__":
    main()
