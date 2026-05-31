# Concepto 14 — SAC en práctica (con stable-baselines3)

Este es el algoritmo que vamos a usar. Te explico **qué hace adentro** en una página, y después **cómo usarlo** con la librería sin tener que reimplementarlo.

---

## SAC en una página

**SAC** = Soft Actor-Critic. Es un algoritmo off-policy de RL para acciones continuas. Lo desarrolló Berkeley en 2018 y se volvió standard para robótica.

### Las 3 ideas clave

1. **Actor-Critic**: tiene una política (actor) y dos funciones Q (critics).
2. **Maximum Entropy RL**: el objetivo no es solo maximizar recompensa, sino también **mantener la política con alta entropía** (estocástica).

   ```
   Objetivo SAC = E[Σ γᵗ (rᵗ + α · H(π(·|sᵗ)))]
                  ↑                   ↑
                  retorno           bonus por entropía
   ```

3. **α auto-tuning**: el coeficiente de entropía α se ajusta solo durante el entrenamiento (no es un hiperparámetro fijo).

### ¿Por qué dos critics?

Para evitar **overestimation bias**: si solo tenés un Q, tiende a sobreestimar el valor real (por el max en el target). Con dos Q y tomar el mínimo (`min(Q1, Q2)`), reducís ese sesgo.

### El loop de SAC (simplificado)

```
Por cada paso del environment:
    1. Sample a ~ π(·|s), ejecutar, observar (s', r)
    2. Guardar (s, a, r, s', done) en replay buffer

Por cada gradient step (cada N steps de env):
    Sample minibatch B del buffer
    
    3. Update critics:
       Target: y = r + γ · (min Q_target(s', a') − α · log π(a'|s'))
              donde a' ~ π(·|s')
       Loss: ||Q(s, a) − y||²
    
    4. Update policy:
       Maximize: E[α · log π(a|s) − min Q(s, a)]
              donde a ~ π(·|s) (con reparametrization trick)
    
    5. Update α (auto-tuning):
       Maximize: E[−α · (log π(a|s) + target_entropy)]
    
    6. Soft update targets:
       Q_target ← τ · Q + (1 − τ) · Q_target
```

No te asustes con la matemática. Lo importante:

- **Critics aprenden a estimar el retorno** (con regularización por entropía).
- **Policy aprende a maximizar el critic** (con bonus por mantenerse estocástica).
- **α se ajusta** para que la entropía promedio sea cercana a un target.

---

## Hiperparámetros típicos para nuestro problema

Estos son **defaults razonables** que después podés tunear:

| Parámetro | Valor | Comentario |
|-----------|-------|------------|
| `learning_rate` | 3e-4 | Standard SAC |
| `buffer_size` | 1_000_000 | Replay buffer |
| `batch_size` | 256 | Minibatch por update |
| `gamma` | 0.99 | Factor de descuento |
| `tau` | 0.005 | Soft update rate de targets |
| `train_freq` | 1 | Update cada step de env |
| `gradient_steps` | 1 | 1 gradient step por env step |
| `learning_starts` | 10_000 | Steps random antes de empezar a entrenar |
| `policy_kwargs` | `{"net_arch": [256, 256]}` | 2 capas hidden de 256 |
| `ent_coef` | `"auto"` | Auto-tuning del α |
| `target_entropy` | `-action_dim` | Heurística standard |

Con esos defaults entrenás un agente decente en **~500k-1M timesteps**.

---

## stable-baselines3 — la implementación que vamos a usar

`stable-baselines3` es una librería Python con implementaciones de los algoritmos de RL más populares (SAC, PPO, TD3, DQN, etc.) listas para usar.

### Instalación

```bash
pip install stable-baselines3[extra]
pip install gymnasium  # interfaz de environment
```

### Esqueleto del entrenamiento

```python
from stable_baselines3 import SAC
from stable_baselines3.common.vec_env import DummyVecEnv

# Tu environment custom (lo definimos abajo)
env = WakuseibokanEnv()

# Crear el agente SAC
model = SAC(
    policy="MlpPolicy",
    env=env,
    learning_rate=3e-4,
    buffer_size=1_000_000,
    batch_size=256,
    gamma=0.99,
    tau=0.005,
    learning_starts=10_000,
    train_freq=1,
    gradient_steps=1,
    ent_coef="auto",
    policy_kwargs={"net_arch": [256, 256]},
    tensorboard_log="./logs/",
    verbose=1,
)

# Entrenar
model.learn(total_timesteps=1_000_000, log_interval=10)

# Guardar
model.save("otter_sac_v1")

# Cargar y usar
model = SAC.load("otter_sac_v1")
obs, _ = env.reset()
for _ in range(5000):
    action, _states = model.predict(obs, deterministic=True)
    obs, reward, done, truncated, info = env.step(action)
    if done or truncated:
        break
```

**Eso es todo el código de SAC**. La librería se encarga de todo lo demás (replay buffer, critics, gradients, α-tuning, etc.).

---

## El environment custom (donde tenemos que trabajar)

Lo que nosotros tenemos que escribir es el **environment** — el wrapper que conecta el simulador Wakuseibokan al protocolo de `gymnasium`.

```python
import gymnasium as gym
import numpy as np
from gymnasium import spaces

class WakuseibokanEnv(gym.Env):
    metadata = {"render_modes": []}
    
    def __init__(self):
        super().__init__()
        
        # Espacio de observación: 78 floats normalizados en [-1, 1]
        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(78,), dtype=np.float32
        )
        
        # Espacio de acción: 5 dimensiones continuas en [-1, 1]
        # (thrust, steering, turret_b, turret_d, fire_prob)
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(5,), dtype=np.float32
        )
        
        # Cliente UDP (lo definimos en otro archivo)
        self.client = WakuseibokanUDPClient()
        self.state_encoder = StateEncoder()
        
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.client.restart_simulator()  # reinicia el simulador
        raw_telemetry = self.client.wait_for_telemetry()
        obs = self.state_encoder.encode(raw_telemetry)
        info = {}
        return obs, info
    
    def step(self, action):
        # 1. Mandar comandos al simulador
        cmd = self._action_to_command(action)
        self.client.send_command(cmd)
        
        # 2. Recibir nueva telemetría
        raw_telemetry = self.client.wait_for_telemetry()
        obs = self.state_encoder.encode(raw_telemetry)
        
        # 3. Calcular reward
        reward = self._compute_reward(self.last_telemetry, raw_telemetry, action)
        
        # 4. Detectar terminal
        terminated = self._is_terminated(raw_telemetry)
        truncated = self._is_timeout(raw_telemetry)
        
        info = {"raw_telemetry": raw_telemetry}
        self.last_telemetry = raw_telemetry
        
        return obs, reward, terminated, truncated, info
    
    def _action_to_command(self, action):
        """Convierte acción [-1,1]^5 al ControlStructure2 del simulador."""
        ...
    
    def _compute_reward(self, prev, curr, action):
        """Implementa la función R del Diseño 01."""
        ...
    
    def _is_terminated(self, tel):
        return tel.self_health <= 0 or tel.enemy_health <= 0  # del Lobby
    
    def _is_timeout(self, tel):
        return tel.tick >= 5000
```

Después de definir esto, **SAC se entrena solo**.

---

## El truco para training: usar Lobby para reward, telemetría para obs

Como vimos en el Diseño 01:

```python
def _compute_reward(self, prev, curr, action):
    """
    prev y curr son TickRecords completos (Lobby data) que incluyen
    enemy_health, enemy_pos, etc.
    Solo se usan en TRAINING para shaping; la política nunca los ve.
    """
    r = 0
    
    # Mi daño (extra al desgaste)
    extra_dmg = max(0, (prev.self_health - curr.self_health) - 1)
    r -= 5 * extra_dmg
    
    # Daño al enemigo (GT del Lobby!)
    enemy_dmg = max(0, prev.enemy_health - curr.enemy_health)
    r += 10 * enemy_dmg
    
    # Otros componentes ... (ver Diseño 01)
    
    # Terminal
    if curr.enemy_health <= 0:
        r += 1000  # victoria
    if curr.self_health <= 0:
        r -= 500   # muerte
    
    return r
```

**El obs que el state_encoder devuelve NO incluye los datos del Lobby** — solo lo que tendríamos en evaluación. Así la política aprende a jugar sin GT del enemigo.

---

## Plan de entrenamiento (4 semanas, del plan original)

| Semana | Objetivo | Algoritmo | Hardware |
|--------|----------|-----------|----------|
| 1 | Pipeline + dataset recording | Random + scripted policy | Local |
| 2 | Imitation learning warm-start | Supervised (no SAC todavía) | Colab T4 |
| 3 | SAC fine-tuning offline (CQL/IQL) | SAC con replay buffer del dataset | Colab T4 |
| 4 | Eval + (opcional) self-play | SAC + snapshots anteriores | Colab T4 |

### ¿Por qué offline RL en Semana 3?

Porque correr SAC online requiere **el environment funcionando en el mismo proceso que el training**. Eso significaría compilar Wakuseibokan en Colab, lo cual es delicado.

**Solución**: recolectar dataset grande LOCALMENTE en Semana 1, y entrenar SAC sobre ese dataset en Colab usando **offline RL** (variantes de SAC como CQL = Conservative Q-Learning, o IQL = Implicit Q-Learning).

`stable-baselines3-contrib` y `d3rlpy` tienen implementaciones de CQL/IQL listas.

---

## Cómo monitorear el training

`stable-baselines3` integra con **TensorBoard** automáticamente:

```bash
tensorboard --logdir ./logs/
```

Métricas que tenés que mirar:

- **`rollout/ep_rew_mean`**: retorno promedio. Tiene que SUBIR a lo largo del training.
- **`rollout/ep_len_mean`**: duración del episodio. Si el agente mejora, debería **aumentar** (sobrevive más) hasta llegar a victorias rápidas.
- **`train/actor_loss`**: si oscila mucho → inestabilidad. Si converge → bien.
- **`train/critic_loss`**: idem.
- **`train/entropy_coef` (α)**: en SAC se auto-ajusta. Empieza alto y baja gradualmente.

---

## Cosas que pueden salir mal y cómo detectarlas

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| Retorno NO sube | Reward mal diseñado | Revisar R, debug con visualización |
| Retorno sube pero el agente hace cosas raras | Reward hackeable | Refinar R, agregar penalties |
| Loss del critic explota | Learning rate muy alto | Bajar lr a 1e-4 |
| Episodios terminan instantáneo | Penalty terminal muy fuerte sin counter-rewards | Ajustar magnitudes |
| Replay buffer no se llena | `learning_starts` muy alto o env crashes | Verificar conexión UDP |

---

## Resumen para llevarse

| Concepto | Qué es |
|----------|--------|
| **SAC** | Off-policy actor-critic con max entropy. Ideal para acciones continuas. |
| **3 ideas** | Actor + 2 critics, max entropy, α auto-tuning |
| **stable-baselines3** | Librería que implementa SAC. Solo escribimos el environment. |
| **gymnasium.Env** | Interfaz para conectar el simulador a la librería |
| **Defaults razonables** | lr=3e-4, buffer=1M, batch=256, hidden=[256,256], γ=0.99 |
| **Training plan** | 1M timesteps, ~6-12h en Colab T4 |
| **Reward usa Lobby (GT)** | Pero la política no |
| **Offline RL en Semana 3** | CQL/IQL para evitar correr environment en Colab |

---

## Lo que viene

- **Concepto 15**: POMDP + LSTM. Cómo hacemos para inferir la pose del enemigo sin verla.
- **Concepto 16**: pipeline completo del agente. El código real conectando todo.
