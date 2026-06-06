"""Gymnasium environment wrapper para Wakuseibokan Otter combat.

Permite hacer fine-tuning online con SAC partiendo de un checkpoint offline.
El env controla el otter 1 (el agente RL) y corre un cheater scripted en thread
separado controlando otter 2.

Dos modos de reset:
- "soft": espera al reset automático del sim con `-episodes`. Mismo mapa
  durante toda la sesión.
- "hard": mata y relanza el binario en cada reset. Mapa nuevo cada episodio
  (city center sembrado con time(NULL) al arrancar). Más lento (~3s extra
  por reset) pero necesario para robustez de mapa.

Uso:
    from agent.env import OtterEnv
    env = OtterEnv(difficulty="hard", reset_mode="hard")
    obs, info = env.reset()
    for _ in range(1800):
        action = policy(obs)
        obs, r, term, trunc, info = env.step(action)
        if term or trunc:
            break
    env.close()
"""
import os
import signal
import subprocess
import time
from threading import Event, Thread
from typing import Any, Dict, Optional, Tuple

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from . import packet_format as pf
from .cheater_policy import (
    DifficultyLevel,
    init_state as cheater_init_state,
    decide as cheater_decide,
    params_for_level,
)
from .encoders import (
    OBS_DIM, ACT_DIM,
    encode_state, decode_action, build_command,
)
from .reward import compute_step_reward
from .udp_io import SharedTelemetryHub


# Constantes del simulador (verificado en testcase_131.cpp:460)
SIM_TICK_DT = 0.02         # 50 Hz
END_GRACE_TICKS = 300      # ticks entre muerte y cleanall()
END_GRACE_S = END_GRACE_TICKS * SIM_TICK_DT  # ~6s


class OtterEnv(gym.Env):
    """Wakuseibokan 1v1 combat env."""

    metadata = {"render_modes": []}

    def __init__(self,
                 difficulty: str = "hard",
                 sim_binary: str = "./testcase",
                 sim_args: Tuple[str, ...] = ("-mute", "-nointro", "-episodes"),
                 tick_dt: float = 0.05,
                 max_steps: int = 1800,
                 reset_mode: str = "hard",
                 episode_timeout_s: float = 90.0,
                 controlled_vehicle_id: int = 1,
                 recv_port: int = 4601,
                 send_port: int = 4501,
                 cheater_recv_port: int = 4602,
                 cheater_send_port: int = 4502,
                 send_host: str = "127.0.0.1",
                 sim_cwd: Optional[str] = None,
                 seed: Optional[int] = None):
        super().__init__()

        assert reset_mode in ("hard", "soft"), f"reset_mode inválido: {reset_mode}"
        assert controlled_vehicle_id in (1, 2)

        self.difficulty = DifficultyLevel(difficulty)
        self.sim_binary = sim_binary
        self.sim_args = tuple(sim_args)
        self.sim_cwd = sim_cwd
        self.tick_dt = tick_dt
        self.max_steps = max_steps
        self.reset_mode = reset_mode
        self.episode_timeout_s = episode_timeout_s
        self.controlled_vid = controlled_vehicle_id
        self.opponent_vid = 2 if controlled_vehicle_id == 1 else 1
        self.recv_port = recv_port
        self.send_port = send_port
        self.cheater_recv_port = cheater_recv_port
        self.cheater_send_port = cheater_send_port
        self.send_host = send_host

        self.observation_space = spaces.Box(
            low=-3.0, high=3.0, shape=(OBS_DIM,), dtype=np.float32,
        )
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(ACT_DIM,), dtype=np.float32,
        )

        self._rng = np.random.default_rng(seed)
        self._cheater_rng = np.random.default_rng(None if seed is None else seed + 1)

        # Inicializadas en reset()
        self.sim_proc: Optional[subprocess.Popen] = None
        self.hub: Optional[SharedTelemetryHub] = None
        self.cheater_hub: Optional[SharedTelemetryHub] = None
        self._cheater_thread: Optional[Thread] = None
        self._cheater_stop = Event()
        self.t = 0
        self.last_h_me = 1000.0
        self.last_h_oth = 1000.0
        self._episode_start_time = 0.0

    # =========================================================
    # Gym API
    # =========================================================

    def reset(self, seed: Optional[int] = None, options: Optional[Dict] = None
              ) -> Tuple[np.ndarray, Dict[str, Any]]:
        if seed is not None:
            self._rng = np.random.default_rng(seed)
            self._cheater_rng = np.random.default_rng(seed + 1)

        if self.reset_mode == "hard":
            self._hard_reset()
        else:
            self._soft_reset()

        self.t = 0
        self._episode_start_time = time.time()

        snap = self.hub.all_latest()
        my = snap[self.controlled_vid]
        oth = snap[self.opponent_vid]
        self.last_h_me = float(my.health)
        self.last_h_oth = float(oth.health)

        obs = encode_state(my, oth)
        info = {
            "opponent_level": self.difficulty.value,
            "reset_mode": self.reset_mode,
        }
        return obs, info

    def step(self, action: np.ndarray
             ) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        if self.hub is None:
            raise RuntimeError("Llamá a env.reset() antes de step().")

        snap = self.hub.all_latest()
        if self.controlled_vid not in snap or self.opponent_vid not in snap:
            # Sin telemetría completa — terminamos el episodio
            obs = np.zeros(OBS_DIM, dtype=np.float32)
            return obs, 0.0, True, False, {"error": "no_telemetry"}

        my_mr = snap[self.controlled_vid]

        # Construir y enviar comando
        cmd = decode_action(action, my_mr)
        # Forzamos el controlling_id/faction si se pidió controlar otter 2
        if self.controlled_vid != my_mr.number:
            cmd.controllingid = self.controlled_vid
            cmd.faction = self.controlled_vid
        self.hub.send_bytes(cmd.to_bytes())
        fired = (cmd.command == pf.CMD_FIRE)

        # Esperar tick
        time.sleep(self.tick_dt)
        self.t += 1

        # Nuevo snapshot
        snap = self.hub.all_latest()
        if self.controlled_vid not in snap or self.opponent_vid not in snap:
            obs = np.zeros(OBS_DIM, dtype=np.float32)
            return obs, 0.0, True, False, {"error": "no_telemetry"}

        my_mr = snap[self.controlled_vid]
        oth_mr = snap[self.opponent_vid]
        h_me = float(my_mr.health)
        h_oth = float(oth_mr.health)

        reward, terminal = compute_step_reward(
            self.last_h_me, h_me, self.last_h_oth, h_oth, fired,
        )

        # Timeout interno (truncated, no terminated)
        truncated = (self.t >= self.max_steps) or (
            time.time() - self._episode_start_time > self.episode_timeout_s
        )

        obs = encode_state(my_mr, oth_mr)
        info = {
            "opponent_level": self.difficulty.value,
            "health_me": h_me,
            "health_oth": h_oth,
            "fired": fired,
            "step": self.t,
        }

        self.last_h_me = h_me
        self.last_h_oth = h_oth

        return obs, float(reward), bool(terminal), bool(truncated), info

    def close(self):
        self._stop_cheater()
        if self.hub is not None:
            self.hub.stop()
            self.hub = None
        if self.cheater_hub is not None:
            self.cheater_hub.stop()
            self.cheater_hub = None
        self._kill_sim()

    # =========================================================
    # Reset implementations
    # =========================================================

    def _hard_reset(self):
        """Mata el sim si está vivo y lo relanza desde cero. Mapa nuevo."""
        self._stop_cheater()
        if self.hub is not None:
            self.hub.stop()
            self.hub = None
        if self.cheater_hub is not None:
            self.cheater_hub.stop()
            self.cheater_hub = None
        self._kill_sim()

        # Lanzar nuevo proceso
        env_vars = os.environ.copy()
        self.sim_proc = subprocess.Popen(
            [self.sim_binary, *self.sim_args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=self.sim_cwd,
            preexec_fn=os.setsid,  # grupo de proceso propio (para killpg)
            env=env_vars,
        )

        # Hubs nuevos
        self._setup_hubs()
        self._wait_for_episode_start(timeout=20.0)
        self._start_cheater()

        # Esperar 2 ticks para que el sourcetimer del primer comando no sea
        # descartado (testcase_131.cpp:405 ignora si timer - sourcetimer > 30000,
        # y tras un reset timer vuelve a 0)
        time.sleep(2 * self.tick_dt)

    def _soft_reset(self):
        """Espera al reset automático del sim (-episodes). Mismo mapa."""
        first_time = self.hub is None
        if first_time:
            # No hay sim corriendo y no lo vamos a lanzar — el usuario debe
            # haberlo iniciado a mano si está en soft mode sin sim_proc previo.
            # Levantamos hubs y a esperar.
            self._setup_hubs()
            self._wait_for_episode_start(timeout=20.0)
            self._start_cheater()
            time.sleep(2 * self.tick_dt)
            return

        # Sim ya corriendo. Detenemos el cheater para no confundir el sim
        # mientras transiciona entre episodios.
        self._stop_cheater()

        # Esperamos a que el sim haga cleanall() (~6s tras la muerte) y vuelva
        # con health=1000.
        ok = self.hub.wait_for_health_reset(
            [self.controlled_vid, self.opponent_vid],
            target_health=999.0,
            timeout=END_GRACE_S + 10.0,
        )
        if not ok:
            # Fallback: si el soft reset no llegó, hacer hard reset
            self._hard_reset()
            return

        self._start_cheater()
        time.sleep(2 * self.tick_dt)

    def _setup_hubs(self):
        """Crea los SharedTelemetryHub para el agente y para el cheater."""
        self.hub = SharedTelemetryHub(
            recv_port=self.recv_port,
            send_host=self.send_host,
            send_port=self.send_port,
        )
        self.hub.start()

        self.cheater_hub = SharedTelemetryHub(
            recv_port=self.cheater_recv_port,
            send_host=self.send_host,
            send_port=self.cheater_send_port,
        )
        self.cheater_hub.start()

    def _wait_for_episode_start(self, timeout: float = 20.0):
        """Bloquea hasta ver ambos vehículos con health>0."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            snap = self.hub.all_latest() if self.hub else {}
            if (self.controlled_vid in snap and self.opponent_vid in snap and
                    snap[self.controlled_vid].health > 0 and
                    snap[self.opponent_vid].health > 0):
                return
            time.sleep(0.1)
        raise TimeoutError(
            f"No llegó telemetría de ambos vehículos en {timeout}s. "
            f"¿Sim corriendo? Binario: {self.sim_binary}"
        )

    # =========================================================
    # Cheater management
    # =========================================================

    def _start_cheater(self):
        """Lanza el thread que controla otter 2 con cheater_policy."""
        self._cheater_stop = Event()
        params = params_for_level(self.difficulty)
        state = cheater_init_state(params)

        def loop():
            while not self._cheater_stop.is_set():
                time.sleep(self.tick_dt)
                snap = self.cheater_hub.all_latest()
                if self.opponent_vid not in snap or self.controlled_vid not in snap:
                    continue
                my = snap[self.opponent_vid]
                other = snap[self.controlled_vid]
                if my.health <= 0 or other.health <= 0:
                    continue
                thrust, steering, td, tb, fire, _mode = cheater_decide(
                    my.pos, float(my.azimuth), float(my.health),
                    other.pos, float(other.health),
                    params, state, self._cheater_rng,
                )
                cmd = build_command(
                    self.opponent_vid, thrust, steering, td, tb, fire,
                    my.recordtimer,
                )
                self.cheater_hub.send_bytes(cmd.to_bytes())

        self._cheater_thread = Thread(target=loop, daemon=True)
        self._cheater_thread.start()

    def _stop_cheater(self):
        if self._cheater_thread is not None:
            self._cheater_stop.set()
            self._cheater_thread.join(timeout=2.0)
            self._cheater_thread = None

    # =========================================================
    # Sim process management
    # =========================================================

    def _kill_sim(self):
        if self.sim_proc is None:
            return
        try:
            os.killpg(os.getpgid(self.sim_proc.pid), signal.SIGTERM)
            try:
                self.sim_proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(self.sim_proc.pid), signal.SIGKILL)
                self.sim_proc.wait(timeout=2.0)
        except (ProcessLookupError, OSError):
            pass
        finally:
            self.sim_proc = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
