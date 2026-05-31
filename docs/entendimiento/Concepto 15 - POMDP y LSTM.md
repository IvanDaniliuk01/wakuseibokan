# Concepto 15 — POMDP y LSTM (el problema de no ver al enemigo)

---

## El problema

En el Concepto 11 hablamos de MDP, donde el agente **observa el estado completo**. En la realidad nuestra:

- **No vemos al enemigo directamente** (en evaluación, sin Lobby).
- Solo tenemos pistas indirectas: radar events, daños recibidos, ausencia de eventos.

Eso es un **POMDP** (Partially Observable MDP).

## La diferencia formal

| MDP | POMDP |
|-----|-------|
| s ∈ S es lo que el agente recibe | s ∈ S **existe** pero el agente NO lo ve |
| El agente toma a a partir de s | El agente toma a a partir de **observaciones o** que son una función ruidosa de s |
| `π(a | s)` | `π(a | historial de observaciones)` |

El POMDP tiene un componente extra: **función de observación** `O(o | s)` que dice "qué ve el agente dado el estado real".

---

## La solución estándar: belief state

En POMDP, en lugar de un estado, el agente mantiene una **distribución de probabilidad** sobre estados posibles. Eso es el **belief**.

```
belief_t(s) = P(estado real = s | observaciones hasta t)
```

Con el belief en vez del estado, el POMDP se vuelve un MDP "virtual" (el belief es markoviano respecto a sí mismo). Pero el belief vive en un espacio infinito-dimensional.

**Aproximación práctica**: representar el belief con una red neuronal con memoria. Eso es **LSTM**.

---

## LSTM en una página

**LSTM** = Long Short-Term Memory. Es una red neuronal **recurrente** que mantiene un "estado oculto" h_t a lo largo del tiempo.

```
o_t (observación) ──▶ LSTM ──▶ h_t (estado oculto)
                       ▲          │
                       │          │
                       └──────────┘
                       h_{t-1} (memoria de antes)
```

En cada tick, la LSTM:
1. Recibe la observación actual `o_t`.
2. Combina con su memoria `h_{t-1}`.
3. Produce nuevo estado oculto `h_t`.
4. Pasa `h_t` a la siguiente etapa (más capas, output, etc.).

**El estado oculto `h_t` es nuestro belief aproximado**. Captura toda la información histórica relevante.

### Estructura básica

```python
import torch.nn as nn

class StateEstimator(nn.Module):
    def __init__(self, obs_dim=30, hidden_dim=128, num_layers=2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=obs_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True
        )
        # Cabeza para predecir pose enemiga (μ y σ)
        self.head_pos_mean = nn.Linear(hidden_dim, 2)  # (x, z)
        self.head_pos_std = nn.Linear(hidden_dim, 2)
        # Cabeza para predecir velocidad enemiga
        self.head_vel = nn.Linear(hidden_dim, 2)
    
    def forward(self, obs_seq, hidden=None):
        # obs_seq: (batch, seq_len, obs_dim)
        output, hidden = self.lstm(obs_seq, hidden)
        last = output[:, -1, :]  # último timestep
        pos_mean = self.head_pos_mean(last)
        pos_std = torch.exp(self.head_pos_std(last))  # positivo
        vel = self.head_vel(last)
        return pos_mean, pos_std, vel, hidden
```

---

## Cómo entrenamos al State Estimator

Acá usamos el truco del Lobby (Sección F del Diseño 01).

### Setup de training

```python
# Tenemos un dataset recolectado del Lobby (training)
# Cada tupla: (obs_propias_secuencia, gt_enemy_pos, gt_enemy_vel)

for batch in dataloader:
    obs_seq, gt_pos, gt_vel = batch
    
    pos_mean, pos_std, vel_pred, _ = estimator(obs_seq)
    
    # Loss: log-likelihood gaussiana
    loss_pos = -gaussian_log_prob(gt_pos, mean=pos_mean, std=pos_std)
    loss_vel = mse_loss(vel_pred, gt_vel)
    
    loss = loss_pos + loss_vel
    loss.backward()
    optimizer.step()
```

**Key**: el modelo solo recibe `obs_seq` (lo que el agente vería en eval), pero el loss usa GT del Lobby. Esto le enseña a inferir lo no observable.

### Inferencia (en eval, sin Lobby)

```python
# El estimator mantiene hidden state a través de los ticks
hidden = None
for tick in range(MAX_TICKS):
    obs = receive_telemetry()  # solo propia, no Lobby
    obs_t = encode(obs)
    
    # Inferimos pose enemiga
    pos_mean, pos_std, vel, hidden = estimator(
        obs_t.unsqueeze(0).unsqueeze(0),  # batch=1, seq=1
        hidden=hidden
    )
    
    # Pasamos belief a la política
    belief_features = torch.cat([pos_mean, pos_std, vel])
    action = policy(state_features, belief_features)
```

---

## Por qué LSTM y no frame-stacking

**Alternativa simple**: concatenar las últimas K observaciones como input. Esto se llama **frame stacking** y funciona para problemas con horizonte corto.

| Frame stacking | LSTM |
|----------------|------|
| Memoria fija de K ticks | Memoria potencialmente infinita |
| Simple, sin entrenar parámetros extra | Tiene parámetros propios, hay que entrenar |
| Falla si la info relevante es viejo (> K) | Maneja info de cualquier antigüedad |

Para nuestro caso: el enemigo puede ser observado al inicio del episodio y después desaparecer por varios minutos. Necesitamos memoria larga → **LSTM**.

---

## Active perception (bonus avanzado)

Si tu belief es muy incierto, el agente puede **actuar para reducir esa incertidumbre**. Esto se llama **active perception** o **active inference** (Friston).

Implementación práctica: agregar al reward un bonus por **reducir la entropía del belief**:

```python
entropy_change = belief_entropy_prev - belief_entropy_now
r += 0.1 * entropy_change  # positivo si redujo incertidumbre
```

Esto incentiva al agente a buscar info (provocar al enemigo a disparar, moverse a posiciones con LOS, etc.).

**Cuándo agregarlo**: Semana 3-4, después de que SAC base esté funcionando.

---

## Integración con SAC

```python
class POMDPPolicy(nn.Module):
    def __init__(self, obs_dim=30, action_dim=5, hidden=256):
        super().__init__()
        self.state_estimator = StateEstimator(obs_dim, hidden_dim=128)
        # Política recibe obs + belief
        self.policy_input_dim = obs_dim + 6  # 6 = pos(2) + std(2) + vel(2)
        self.policy = SACMlpPolicy(self.policy_input_dim, action_dim, hidden)
    
    def forward(self, obs, hidden=None):
        pos_mean, pos_std, vel, hidden_new = self.state_estimator(obs, hidden)
        belief = torch.cat([pos_mean, pos_std, vel], dim=-1)
        policy_input = torch.cat([obs[..., -1, :], belief], dim=-1)
        action = self.policy(policy_input)
        return action, hidden_new
```

**Detalle técnico**: integrar LSTM con SAC en `stable-baselines3` requiere usar `RecurrentPPO` (de `sb3-contrib`) o codear la política custom. Para SAC con LSTM, ver `sb3-contrib RecurrentSAC` o implementarlo manualmente.

---

## Plan práctico

| Fase | Qué hacemos |
|------|-------------|
| **Semana 1** | Recolectar dataset con Lobby. Guardar `(obs_propias_seq, gt_enemy)`. |
| **Semana 2** | Entrenar StateEstimator supervisado (loss = NLL gaussiana). |
| **Semana 3** | Integrar StateEstimator a la política. Entrenar SAC. Si LSTM da problemas, fallback a frame-stacking. |
| **Semana 4** | Refinar, agregar active perception si hay tiempo. |

---

## Alternativa pragmática (si LSTM no funciona)

Si entrenar LSTM resulta inestable, usá **frame stacking simple**:

```python
# En el state encoder, mantener una cola de K=10 observaciones
self.obs_history = collections.deque(maxlen=K)

def encode(self, raw_telemetry):
    obs = self._encode_single(raw_telemetry)
    self.obs_history.append(obs)
    # Concatenar últimas K
    return np.concatenate(list(self.obs_history))
```

Espacio de obs pasa de N a K·N (e.g., 30 → 300). Más simple, menos potente, pero funciona.

---

## Resumen para llevarse

| Concepto | Qué es |
|----------|--------|
| **POMDP** | MDP donde no observás el estado completo |
| **Belief state** | Distribución sobre estados posibles dado el historial |
| **LSTM** | Red recurrente que mantiene memoria → aproxima belief |
| **State Estimator** | LSTM entrenado supervisado con GT del Lobby (training) → infiere belief en eval |
| **Frame stacking** | Alternativa simple: últimas K obs como input |
| **Active perception** | Reward por reducir entropía del belief. Bonus avanzado. |
| **Plan** | LSTM si funciona, frame-stacking como fallback |

---

## Lo que viene

**Concepto 16**: el pipeline completo. Código real del agente, conectando todo.
