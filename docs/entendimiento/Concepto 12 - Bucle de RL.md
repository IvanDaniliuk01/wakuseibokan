# Concepto 12 — El bucle de RL (cómo aprende el agente)

> 📚 **Referencia del curso**: PDF 4 "AprendizajeXRefuerzo", secciones de Q-Learning y exploración.

---

## La idea central

El Concepto 11 te dijo **qué quiere** el agente (maximizar G = Σγᵗrᵗ). Este te dice **cómo lo consigue**: por **trial and error**, ajustando su política a partir de la experiencia.

```
┌───────────────────────────────────────────────────┐
│  Loop de entrenamiento de RL                      │
│                                                   │
│  1. El agente actúa en el ambiente                │
│     (usa su política actual π)                    │
│  2. Observa qué pasó (estado nuevo, reward)       │
│  3. Guarda la experiencia (s, a, r, s')           │
│  4. Ajusta π para hacer más de lo que             │
│     produjo buenos rewards                        │
│  5. Repetir miles/millones de veces               │
└───────────────────────────────────────────────────┘
```

Esto es **lo único que hace cualquier algoritmo de RL**. Las diferencias entre algoritmos están en **cómo hacen el paso 4** (cómo ajustan π).

---

## Episodios y rollouts

- **Episodio** = una "partida" completa, desde estado inicial hasta terminal.
- **Rollout** = los datos generados durante un episodio (lista de tuplas `(s, a, r, s')`).

Para el Otter: un episodio dura hasta 5000 ticks (250s). Cada episodio te da hasta 5000 tuplas.

Entrenamiento típico: miles a millones de episodios. Eso son **millones de tuplas**.

---

## Exploration vs Exploitation (dilema fundamental)

Si el agente siempre toma la mejor acción que **conoce** (greedy), nunca prueba alternativas que podrían ser mejores. Si siempre prueba al azar, nunca aprovecha lo que aprendió. **Balance: clave**.

Tres estrategias clásicas:

| Estrategia | Cómo | Para qué |
|------------|------|----------|
| **ε-greedy** | Con prob. ε toma acción random, con prob. (1-ε) la mejor conocida | Simple, funciona bien con acciones discretas |
| **Softmax / Boltzmann** | Toma acción con prob. proporcional a exp(Q(s,a)/τ) | Más suave que ε-greedy. τ controla cuán random |
| **Maximum entropy** (SAC) | La política es estocástica de fábrica; agrega bonus por mantener entropía alta | Lo que vamos a usar. Exploración "natural" sin tener que ajustar ε |

**Decay**: típicamente arrancás con mucha exploración (ε=1, todo random) y la bajás gradualmente (ε→0.05) a medida que aprendés. Razonamiento: al principio no sabés nada, después confías más en tu política.

Para SAC esto no se aplica directamente porque la entropía se ajusta automáticamente.

---

## Las dos preguntas centrales del RL

Cualquier algoritmo de RL trata de responder una (o ambas) de estas preguntas:

### Pregunta 1: "¿Qué tan bueno es esto?" (Value-based)

Aprende una **función de valor**:
- `V(s)` = retorno esperado si estás en estado s y seguís la política.
- `Q(s, a)` = retorno esperado si tomás acción a en estado s y después seguís la política.

Con Q bien aprendida, la política óptima es trivial: `π(s) = argmax_a Q(s, a)`.

**Ejemplos**: Q-Learning, DQN, Double DQN.

### Pregunta 2: "¿Qué debería hacer?" (Policy-based)

Aprende **directamente la política** π(a|s), sin pasar por Q.

**Ejemplos**: REINFORCE, PPO.

### La combinación: Actor-Critic

Aprende **las dos cosas al mismo tiempo**:
- **Actor**: la política π (decide qué hacer).
- **Critic**: la función Q (evalúa qué tan bueno fue lo que hizo).

El critic le pasa señal al actor para que mejore.

**Ejemplos**: A2C, A3C, SAC, TD3. SAC es lo que vamos a usar.

---

## On-policy vs Off-policy (decisión arquitectural)

| | On-policy | Off-policy |
|--|-----------|------------|
| **Datos usados para entrenar** | Solo datos generados por la política actual | Datos de cualquier política previa |
| **Replay buffer** | No usable (o muy limitado) | Sí, central al algoritmo |
| **Sample efficiency** | Baja (descartás datos viejos) | Alta (reusás datos) |
| **Estabilidad** | Más estable | Menos estable (cuidado con datos muy viejos) |
| **Algoritmos** | PPO, A2C | DQN, SAC, TD3 |

**Para nuestro caso (Otter)**: vamos con **off-policy** (SAC) porque:
1. **Sample efficiency**: con 4 semanas de deadline y hardware limitado, no podemos darnos el lujo de descartar episodios.
2. **Replay buffer**: nos permite mezclar datos de varias fuentes (imitation, random, SAC actual) en el mismo training.

---

## Replay buffer (concepto clave de off-policy)

Es simplemente **una memoria circular** donde guardás todas las tuplas `(s, a, r, s', done)` que recolectaste. Tamaño típico: 1 millón de transiciones.

```python
class ReplayBuffer:
    def __init__(self, capacity=1_000_000):
        self.buffer = collections.deque(maxlen=capacity)
    
    def add(self, s, a, r, s_next, done):
        self.buffer.append((s, a, r, s_next, done))
    
    def sample(self, batch_size=256):
        return random.sample(self.buffer, batch_size)
```

**Por qué funciona**: cada vez que querés actualizar la red, en vez de usar solo el último episodio, **muestreás un minibatch random del buffer**. Eso:
- Rompe la correlación temporal entre samples.
- Permite reusar la misma experiencia muchas veces.
- Estabiliza el entrenamiento.

---

## El ciclo concreto de entrenamiento (en pseudocódigo)

```python
# Setup
env = WakuseibokanEnv()
policy = SACPolicy(state_dim=78, action_dim=5)
buffer = ReplayBuffer()

# Loop principal
for episode in range(NUM_EPISODES):
    s = env.reset()
    done = False
    
    while not done:
        # 1. ACT: el agente actúa
        a = policy.sample_action(s)  # con exploración (SAC es estocástico)
        
        # 2. OBSERVE: el ambiente responde
        s_next, r, done = env.step(a)
        
        # 3. STORE: guardar en buffer
        buffer.add(s, a, r, s_next, done)
        
        # 4. UPDATE (cada N ticks)
        if buffer.size() > MIN_BUFFER_SIZE and tick % UPDATE_FREQ == 0:
            batch = buffer.sample(BATCH_SIZE)
            policy.update(batch)  # gradient step
        
        s = s_next
    
    # Log retorno del episodio
    print(f"Episode {episode}: G = {total_return}")
```

**El paso 4 (UPDATE)** es donde está la "magia" del algoritmo específico. Para SAC veremos cómo en el Concepto 14.

---

## Curva de aprendizaje típica

Lo que vas a ver durante el entrenamiento (ojalá):

```
Reward
  ↑
  │              ╱──── plateau (convergencia)
  │           ╱─
  │        ╱─
  │     ╱─
  │  ╱─
  │╱─
  ●─────────────────────→  Episodios
  ↑
  inicio: random, retornos bajos/negativos
```

**Pero la realidad es más fea**:

```
Reward
  ↑          ╲     ╱─╲
  │       ╱──── ╲╱    ╲────
  │    ╱─   ↑ instability
  │  ╱
  │╱
  ●─────────────────────→
```

Variabilidad enorme entre episodios. El éxito se mide por **promedio en ventanas de 100 episodios**, no por episodio individual.

---

## Por qué SAC para el Otter

| Requisito | Por qué SAC lo cumple |
|-----------|----------------------|
| **Acciones continuas** | SAC nativo continuo (DQN no sirve) |
| **Sample efficient** | Off-policy + replay buffer |
| **Estable** | Maximum entropy auto-ajustado |
| **Exploración natural** | Política estocástica de fábrica |
| **Disponible en stable-baselines3** | Implementación lista, no hay que codear |

PPO sería la otra opción razonable pero es on-policy → menos sample efficient.

---

## Resumen para llevarse

| Concepto | Qué es |
|----------|--------|
| **Trial and error** | El RL aprende probando y corrigiendo |
| **Episodio** | Una partida completa |
| **Rollout** | Los datos generados durante un episodio |
| **Exploration vs exploitation** | El balance fundamental. SAC lo resuelve con max-entropy |
| **Value-based** | Aprende Q(s,a) → política es argmax |
| **Policy-based** | Aprende π directo |
| **Actor-Critic** | Las dos cosas. SAC entra acá |
| **On-policy** | Solo datos actuales. PPO |
| **Off-policy** | Cualquier dato. SAC, DQN |
| **Replay buffer** | Memoria de transiciones, sample random |
| **Update step** | El "núcleo" del algoritmo: gradient step para mejorar π |
| **Para nosotros**: SAC | Off-policy + continuous + max-entropy = ideal |

---

## Lo que viene

- **Concepto 13**: redes neuronales en una página. Solo lo que necesitás para entender qué hay adentro de SAC.
- **Concepto 14**: SAC en práctica con stable-baselines3.
