# Concepto 16 — Pipeline completo del agente (cierre de la Parte II)

Este concepto cierra la teoría conectando TODO en código real. Después de leer esto deberías poder empezar a codear el agente.

---

## La arquitectura final

```
┌────────────────────────────────────────────────────────────────┐
│                          AGENTE OTTER                          │
└────────────────────────────────────────────────────────────────┘

UDP IN                                                  UDP OUT
(puerto 4500 Lobby                              (puerto 5000+
 training; 4501+i              ┌────────┐         para comandos)
 eval)                         │        │              │
     │                         │        │              ▲
     ▼                         │        │              │
┌─────────────┐                │        │      ┌──────────────┐
│ L1: UDP I/O │                │        │      │ L5: Dispatcher│
│  (recv loop)│                │        │      │  + trigger    │
└─────────────┘                │        │      │  discipline   │
     │                         │        │      └──────────────┘
     ▼                         │        │              ▲
┌─────────────┐                │        │              │
│ L2: State    │                │ Replay │      ┌──────────────┐
│ Encoder     │──── (s_t) ──────│ Buffer │     │ L4: Policy    │
│ (POMDP obs) │                │        │      │   (SAC actor) │
└─────────────┘                │        │      └──────────────┘
     │                         │        │              ▲
     │ obs_seq                 │        │              │
     ▼                         │        │              │ (s_t ⊕ belief)
┌─────────────┐                │        │              │
│ L3: State    │                │        │      ┌──────────────┐
│ Estimator   │── (belief) ────┼────────┼─────▶│ Concat        │
│  (LSTM)     │                │        │      │ obs + belief  │
└─────────────┘                │        │      └──────────────┘
                               │        │
                               │        │
                               │  (s, a, r, s')
                               │        │
                               ▼        ▼
                          ┌──────────────────┐
                          │  SAC Trainer      │
                          │  (en training)    │
                          └──────────────────┘
```

---

## Capa 1: UDP I/O

Cliente que recibe telemetría y manda comandos.

```python
# udp_io.py
import socket
import struct
import threading
from collections import deque

class WakuseibokanUDPClient:
    def __init__(self, recv_port=4500, send_host="127.0.0.1", send_port=5000):
        # Socket de recepción
        self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.recv_sock.bind(("", recv_port))
        self.recv_sock.settimeout(0.5)
        
        # Socket de envío
        self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.send_addr = (send_host, send_port)
        
        # Buffer circular de últimos K=30 ticks
        self.telemetry_buffer = {}  # vehicle_id -> deque of TickRecord
        
        # Thread de recepción
        self._stop = threading.Event()
        self.recv_thread = threading.Thread(target=self._recv_loop)
        self.recv_thread.daemon = True
        self.recv_thread.start()
    
    def _recv_loop(self):
        while not self._stop.is_set():
            try:
                data, addr = self.recv_sock.recvfrom(1024)
                self._handle_packet(data)
            except socket.timeout:
                continue
    
    def _handle_packet(self, data):
        # Parsear TickRecord o ModelRecord según tamaño
        if len(data) == 96:
            tr = parse_model_record(data)
        else:
            tr = parse_tick_record(data)
        
        vid = tr.id
        if vid not in self.telemetry_buffer:
            self.telemetry_buffer[vid] = deque(maxlen=30)
        self.telemetry_buffer[vid].append(tr)
    
    def get_latest(self, vehicle_id):
        if vehicle_id not in self.telemetry_buffer:
            return None
        return self.telemetry_buffer[vehicle_id][-1]
    
    def send_command(self, cmd: 'ControlStructure2'):
        data = cmd.pack()  # struct.pack
        self.send_sock.sendto(data, self.send_addr)
    
    def stop(self):
        self._stop.set()
        self.recv_thread.join()
```

---

## Capa 2: State Encoder

Convierte el TickRecord crudo en vector de observación.

```python
# state_encoder.py
import numpy as np
from scipy.spatial.transform import Rotation

class StateEncoder:
    """
    Encoder POMDP: solo usa info propia (lo que tendríamos en eval).
    """
    def __init__(self, map_belief=None):
        self.map_belief = map_belief or MapBelief()
        self.last_obs = None
        self.fire_history = deque(maxlen=100)
        self.radar_history = deque(maxlen=100)
    
    def encode(self, my_tickrecord):
        feats = []
        
        # B.1 Self direct
        pos = np.array([my_tickrecord.pos.x, my_tickrecord.pos.y, my_tickrecord.pos.z])
        feats.extend(pos / 1400.0)
        
        R = my_tickrecord.rotation_matrix()  # reconstruir 3x3
        q = Rotation.from_matrix(R).as_quat()
        if q[3] < 0: q = -q
        feats.extend(q)
        
        feats.append(my_tickrecord.health / 1000.0)
        feats.append(my_tickrecord.power / 1000.0)
        feats.append(my_tickrecord.azimuth / np.pi)
        feats.append(min(1.0, my_tickrecord.timer / 5000.0))
        
        # B.2 Events
        delta_health = 0
        if self.last_obs:
            delta_health = my_tickrecord.health - self.last_obs.health
        feats.append(delta_health / 100.0)
        
        # Radar
        radar_active = (my_tickrecord.landingPos != [0, 0, 0])
        feats.append(float(radar_active))
        if radar_active:
            self.radar_history.append((my_tickrecord.timer, my_tickrecord.landingPos))
        
        # ... (más features según Diseño 01) ...
        
        # B.3 Mapa (usando belief)
        cc = self.map_belief.estimate()
        feats.extend(self._warehouse_features(cc, pos, R))
        
        # B.5 Belief enemigo (vacío acá; lo agrega el wrapper)
        # Será llenado por la State Estimator (LSTM)
        
        self.last_obs = my_tickrecord
        return np.array(feats, dtype=np.float32)
    
    def _warehouse_features(self, city_center, my_pos, R):
        # Computar dist y LOS a las 18 warehouses dadas el belief
        ...
```

---

## Capa 3: State Estimator (LSTM)

Infiere belief del enemigo. Ver Concepto 15.

```python
# state_estimator.py
import torch
import torch.nn as nn

class StateEstimator(nn.Module):
    def __init__(self, obs_dim=30, hidden_dim=128, num_layers=2):
        super().__init__()
        self.lstm = nn.LSTM(obs_dim, hidden_dim, num_layers, batch_first=True)
        self.pos_head = nn.Linear(hidden_dim, 4)  # μ_x, μ_z, σ_x, σ_z
        self.vel_head = nn.Linear(hidden_dim, 2)
    
    def forward(self, obs_seq, hidden=None):
        out, hidden = self.lstm(obs_seq, hidden)
        last = out[:, -1, :]
        pos_params = self.pos_head(last)
        mean = pos_params[..., :2]
        log_std = pos_params[..., 2:].clamp(-2, 2)
        std = torch.exp(log_std)
        vel = self.vel_head(last)
        return mean, std, vel, hidden
```

---

## Capa 4: Policy SAC

La librería se encarga; solo configuramos.

```python
# policy.py
from stable_baselines3 import SAC

def create_sac_agent(env, log_dir="./logs/"):
    return SAC(
        policy="MlpPolicy",
        env=env,
        learning_rate=3e-4,
        buffer_size=1_000_000,
        batch_size=256,
        gamma=0.99,
        tau=0.005,
        learning_starts=10_000,
        ent_coef="auto",
        policy_kwargs={"net_arch": [256, 256]},
        tensorboard_log=log_dir,
        verbose=1,
    )
```

---

## Capa 5: Dispatcher con Trigger Discipline

Filtra acciones inválidas antes de mandarlas.

```python
# dispatcher.py
import struct

def action_to_command(action, current_state, controlling_id):
    """
    Convierte action [-1,1]^5 a ControlStructure2 bytes.
    Aplica trigger discipline para 'fire'.
    """
    thrust, steering, turret_b, turret_d, fire_logit = action
    
    # Trigger discipline
    fire = False
    if fire_logit > 0:
        # Sample bernoulli con prob = sigmoid(fire_logit)
        prob = 1 / (1 + np.exp(-fire_logit))
        fire = np.random.random() < prob
        
        # Gate: no disparar si no hay LOS, no hay power, etc.
        if current_state.power <= 0:
            fire = False
        if not current_state.los_clear_to_target:
            fire = False
        # (HPE check si está disponible)
    
    # Empaquetar ControlStructure2 (68 bytes)
    cmd = struct.pack(
        "<i6fii i fff iii I",  # formato según commandorder.h
        controlling_id,
        thrust,
        0.0,        # roll
        0.0,        # pitch
        steering * 30.0,  # yaw mapeado a grados
        0.0,        # precesion
        0.0,        # bank
        1,          # faction
        11 if fire else 0,  # command (11 = FIRE)
        0,          # spawnid
        0,          # typeofisland
        0.0, 0.0, 0.0,  # x, y, z (no usado en este modo)
        0, 0,       # target_type, weapon
        int(time.time() * 1000) & 0xFFFFFFFF,  # sourcetimer
    )
    return cmd
```

---

## El environment Gymnasium completo

Esto es lo que `SAC.learn()` consume.

```python
# env.py
import gymnasium as gym
from gymnasium import spaces
import numpy as np
import subprocess
import time

class WakuseibokanEnv(gym.Env):
    metadata = {"render_modes": []}
    
    def __init__(self, sim_executable="/path/to/testcase", testcase=131):
        super().__init__()
        self.observation_space = spaces.Box(-1, 1, (78,), dtype=np.float32)
        self.action_space = spaces.Box(-1, 1, (5,), dtype=np.float32)
        
        self.sim_executable = sim_executable
        self.testcase = testcase
        self.sim_process = None
        
        self.client = WakuseibokanUDPClient()
        self.encoder = StateEncoder()
        self.estimator = StateEstimator()
        self.estimator_hidden = None
        
        self.my_vehicle_id = 1
        self.enemy_vehicle_id = 2
        
        self.last_tickrecord = None
        self.tick = 0
        
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        
        # Restart simulator
        if self.sim_process:
            self.sim_process.terminate()
            self.sim_process.wait()
        self.sim_process = subprocess.Popen([
            self.sim_executable, "-mute", "-nointro",
            "-testcase", str(self.testcase)
        ])
        time.sleep(1)  # esperar inicialización
        
        # Esperar primera telemetría
        for _ in range(100):
            tr = self.client.get_latest(self.my_vehicle_id)
            if tr is not None:
                break
            time.sleep(0.05)
        
        self.last_tickrecord = tr
        self.tick = 0
        self.estimator_hidden = None
        
        obs = self._build_obs(tr)
        return obs, {}
    
    def step(self, action):
        # Send command
        cmd = action_to_command(action, self.last_tickrecord, self.my_vehicle_id)
        self.client.send_command(cmd)
        
        # Wait for telemetry
        time.sleep(0.02)  # ~50 Hz tick
        tr = self.client.get_latest(self.my_vehicle_id)
        if tr is None:
            tr = self.last_tickrecord  # fallback
        
        # Lobby data for reward (training only)
        enemy_tr = self.client.get_latest(self.enemy_vehicle_id)
        
        # Build obs (POMDP — solo info propia + belief)
        obs = self._build_obs(tr)
        
        # Reward (training: usa Lobby; eval: HPE)
        reward = self._compute_reward(self.last_tickrecord, tr, enemy_tr, action)
        
        # Terminal conditions
        terminated = (tr.health <= 0) or (enemy_tr and enemy_tr.health <= 0)
        truncated = (self.tick >= 5000)
        
        self.last_tickrecord = tr
        self.tick += 1
        
        return obs, reward, terminated, truncated, {}
    
    def _build_obs(self, tr):
        base_obs = self.encoder.encode(tr)
        
        # Belief enemigo via LSTM
        with torch.no_grad():
            obs_t = torch.from_numpy(base_obs[:30]).unsqueeze(0).unsqueeze(0).float()
            mean, std, vel, self.estimator_hidden = self.estimator(
                obs_t, hidden=self.estimator_hidden
            )
            belief_feats = torch.cat([mean, std, vel], dim=-1).squeeze().numpy()
        
        return np.concatenate([base_obs, belief_feats]).astype(np.float32)
    
    def _compute_reward(self, prev, curr, enemy_curr, action):
        r = 0
        # Damage extra (descontando desgaste)
        extra_dmg = max(0, (prev.health - curr.health) - 1)
        r -= 5 * extra_dmg
        # Damage to enemy (Lobby GT, solo training)
        if enemy_curr and prev.enemy_health is not None:
            enemy_dmg = max(0, prev.enemy_health - enemy_curr.health)
            r += 10 * enemy_dmg
        # Fire penalty
        if action[4] > 0:
            r -= 0.3
        # Step + alive
        r += 0.04
        # Terminal
        if curr.health <= 0:
            r -= 500
        if enemy_curr and enemy_curr.health <= 0:
            r += 1000
        return r
    
    def close(self):
        if self.sim_process:
            self.sim_process.terminate()
        self.client.stop()
```

---

## Training script (top-level)

```python
# train.py
from stable_baselines3 import SAC
from stable_baselines3.common.callbacks import CheckpointCallback
from env import WakuseibokanEnv

env = WakuseibokanEnv()
model = SAC(
    "MlpPolicy",
    env,
    learning_rate=3e-4,
    buffer_size=1_000_000,
    batch_size=256,
    gamma=0.99,
    tau=0.005,
    learning_starts=10_000,
    ent_coef="auto",
    policy_kwargs={"net_arch": [256, 256]},
    tensorboard_log="./logs/",
    verbose=1,
)

checkpoint_cb = CheckpointCallback(
    save_freq=50_000,
    save_path="./checkpoints/",
    name_prefix="otter_sac",
)

model.learn(
    total_timesteps=1_000_000,
    callback=checkpoint_cb,
    log_interval=10,
)
model.save("otter_sac_final")
```

---

## Eval script

```python
# eval.py
from stable_baselines3 import SAC
from env import WakuseibokanEnv

env = WakuseibokanEnv()
model = SAC.load("otter_sac_final")

n_episodes = 100
wins = 0
for ep in range(n_episodes):
    obs, _ = env.reset()
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, _ = env.step(action)
        done = terminated or truncated
    if reward > 500:  # victoria approximada
        wins += 1
    print(f"Ep {ep}: reward = {reward}, win_rate = {wins/(ep+1):.2%}")
```

---

## Estructura de directorios sugerida

```
wakuseibokan/
├── agent/                       # NUEVO
│   ├── __init__.py
│   ├── udp_io.py               # Capa 1
│   ├── packet_format.py        # Definiciones struct
│   ├── state_encoder.py        # Capa 2
│   ├── state_estimator.py      # Capa 3 (LSTM)
│   ├── map_belief.py           # Belief incremental del mapa
│   ├── dispatcher.py           # Capa 5
│   ├── env.py                  # Gymnasium wrapper
│   ├── train.py                # Script entrenamiento
│   ├── eval.py                 # Script evaluación
│   └── tests/                  # Tests unitarios
│       ├── test_packet.py
│       ├── test_encoder.py
│       └── test_env.py
├── data/                        # Datasets recolectados
├── checkpoints/                 # Modelos guardados
├── logs/                        # TensorBoard logs
└── docs/                        # Lo que ya tenemos
```

---

## Plan de implementación (4 semanas)

| Semana | Día | Qué hacer |
|--------|-----|-----------|
| **1** | 1-2 | `udp_io.py` + `packet_format.py` + smoke test |
| | 3 | `state_encoder.py` + `map_belief.py` (versión simple) |
| | 4 | `env.py` con encoder + smoke test con SAC random |
| | 5 | Recolectar dataset 200 episodios (random + scripted) |
| **2** | 1-2 | Imitation learning supervisado |
| | 3-4 | `state_estimator.py` LSTM + training supervisado |
| | 5 | Integrar estimator a env. Eval vs baseline |
| **3** | 1-2 | Offline RL con CQL en Colab |
| | 3-4 | Training de 500k steps |
| | 5 | Eval, debug, tuning |
| **4** | 1-2 | (opcional) Self-play |
| | 3-4 | Eval final, README, video |
| | 5 | Entrega |

---

## Resumen — la lista de "qué codear"

1. ✅ Conceptos teóricos terminados (1-16)
2. ⏳ `agent/udp_io.py` — cliente UDP
3. ⏳ `agent/packet_format.py` — parse/pack de TickRecord y ControlStructure2
4. ⏳ `agent/state_encoder.py` — vector de observación POMDP
5. ⏳ `agent/map_belief.py` — belief incremental del city center
6. ⏳ `agent/state_estimator.py` — LSTM para belief enemigo
7. ⏳ `agent/env.py` — Gymnasium environment
8. ⏳ `agent/dispatcher.py` — trigger discipline + envío
9. ⏳ `agent/train.py` — script de entrenamiento
10. ⏳ Recolección de dataset
11. ⏳ Training en Colab
12. ⏳ Eval + entrega

---

## Cierre

Con esto cerramos la teoría. Tenés todo lo necesario para empezar a codear:

- **Parte I (Conceptos 1-9)**: rotaciones, frames, R[12]
- **Parte II (Conceptos 10-16)**: cinemática, MDP, RL, NN, SAC, POMDP, pipeline
- **Diseño 01**: aplicación concreta al Otter

Próximo paso: empezar por `agent/udp_io.py` y construir el pipeline desde abajo hacia arriba.
