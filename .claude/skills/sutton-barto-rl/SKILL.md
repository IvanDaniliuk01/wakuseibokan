---
name: sutton-barto-rl
description: Richard S. Sutton & Andrew G. Barto — Reinforcement Learning: An Introduction (2nd edition, in progress 2014-2015). EL libro fundacional de RL. Invocar para cualquier cosa que involucre aprender una política para el agente (Q-Learning, Sarsa, Actor-Critic, function approximation con redes neuronales), formalizar el problema como MDP, o entender el formalismo state-action-reward.
---

# Sutton & Barto — Reinforcement Learning: An Introduction (2da ed draft)

**Archivo:** `docs/bibliografía/SuttonBartoIPRLBook2ndEd.pdf` (4 MB)
**Autores:** Richard S. Sutton (Universidad de Alberta), Andrew G. Barto (UMass)
**Editorial:** MIT Press, A Bradford Book
**Edición:** 2da, **in progress 2014-2015** (la 2da edición final salió en 2018 — **este PDF es un draft anterior** y no incluye los capítulos finales sobre deep RL)
**Estatus en el curso:** No oficial en lista de Ramele, pero el **Día 3 del curso es "Reinforcement Learning"** — es esencial.

## Por qué importa para Wakuseibokan

El **Día 3 del outline de Ramele** es explícitamente Reinforcement Learning. Si el agente termina aprendiendo por interacción (lo más natural para el problema), este es **el libro de cabecera**. Junto con `braunl-embedded-robotics` cap 19 (Neural Networks), forman el dúo técnico central del proyecto.

El repo ya tiene infraestructura para RL:
- `src/reinforcement.cpp` — código C++ de soporte
- `scripts/EpisodeRecorder.py` — graba episodios para training
- El TestCase 131 tiene modo `episodesmode` que reinicia con `cleanall()` ([src/tests/testcase_131.cpp:298-317](src/tests/testcase_131.cpp#L298-L317))

## Tabla de contenidos completa

| Cap | Tema | Página | Relevancia agente |
|-----|------|--------|-------------------|
| 1 | **The Reinforcement Learning Problem** | 1 | Lectura obligatoria — define el problema |

### Part I — Tabular Solution Methods (p 27)

| Cap | Tema | Página | Relevancia agente |
|-----|------|--------|-------------------|
| 2 | Multi-arm Bandits | 31 | Exploration vs exploitation, ε-greedy, UCB |
| 3 | **Finite Markov Decision Processes** | 53 | **MDP formalism — clave**. Agent-Environment interface, Goals, Rewards, Returns, Value Functions, Optimal Value Functions |
| 4 | Dynamic Programming | 89 | Policy Iteration, Value Iteration |
| 5 | Monte Carlo Methods | 113 | MC Prediction, MC Control, Off-policy via Importance Sampling |
| 6 | **Temporal-Difference Learning** | 143 | **TD(0), Sarsa, Q-Learning (off-policy)** — núcleo de RL |
| 7 | Eligibility Traces | 167 | TD(λ), Sarsa(λ), Watkins's Q(λ) |
| 8 | Planning and Learning with Tabular Methods | 195 | Heuristic Search, **Monte Carlo Tree Search** |

### Part II — Approximate Solution Methods (p 223)

| Cap | Tema | Página | Relevancia agente |
|-----|------|--------|-------------------|
| 9 | **On-policy Approximation of Action Values** | 225 | **Function Approximation, Gradient-Descent — base para usar redes neuronales** |
| 10 | Off-policy Approximation of Action Values | 255 | |
| 11 | **Policy Approximation** | 257 | **Actor-Critic Methods**, R-Learning |

### Part III — Frontiers (p 265)

| Cap | Tema | Página | Relevancia agente |
|-----|------|--------|-------------------|
| 12 | Psychology | 269 | Conexión con animal learning |
| 13 | Neuroscience | 271 | Conexión con dopamina, reward prediction error |
| 14 | **Applications and Case Studies** | 273 | **TD-Gammon**, Samuel's Checkers, **Acrobot**, Elevator Dispatching, Dynamic Channel Allocation, Job-Shop Scheduling |
| 15 | Prospects | 303 | Outlook |

## Lo que falta vs. la 2da edición publicada (2018)

Este draft **no incluye los caps modernos de deep RL** de la edición final. La 2da ed publicada agrega:
- Deep Q-Networks (DQN) — Mnih et al.
- Policy Gradient Methods (REINFORCE)
- Asynchronous methods (A3C)
- AlphaGo / AlphaZero
- Material sobre **deep neural networks como function approximators**

Si necesitamos deep RL serio (PPO, DDPG, SAC), conviene buscar la 2da ed final o ir directo a papers.

## Capítulos prioritarios para nuestro agente

**Camino mínimo recomendado (lectura ~ 1 semana):**

1. **Cap 1** — entender qué es RL y por qué aplica al problema
2. **Cap 3** — formalismo MDP: definir `S`, `A`, `R`, `π` para el Otter
3. **Cap 6** (especialmente **6.5 Q-Learning**) — algoritmo más simple y conocido
4. **Cap 9** — function approximation con NN, base para combinar con `braunl` cap 19
5. **Cap 14.3 (The Acrobot)** — case study con dinámica similar a un robot, útil de referencia

**Útiles para extensiones:**
- Cap 7 (Eligibility Traces) si Q-Learning vanilla es lento
- Cap 11 (Actor-Critic) si vamos a policy methods en vez de value methods
- Cap 8.8 (MCTS) si vamos por planning explícito

## Conceptos clave

| Concepto | Significado en el contexto Otter |
|----------|----------------------------------|
| Estado `S_t` | Telemetría del Otter + del oponente (pos, R, health, power, etc.) |
| Acción `A_t` | Tupla `(thrust, roll, pitch, yaw, command)` del `ControlStructure2` |
| Recompensa `R_t` | + por dañar oponente, − por recibir daño, − por step (eficiencia), + por victoria |
| Política `π(a|s)` | Mapping del estado a acciones — esto es **lo que aprendemos** |
| Valor `v_π(s)` | Retorno esperado desde `s` siguiendo `π` |
| Q-value `q_π(s,a)` | Retorno esperado tomando `a` en `s` y luego siguiendo `π` |
| Episodio | Una pelea completa (hasta que un tanque muere) |
| Return `G_t` | Suma descontada de recompensas futuras |
| γ (gamma) | Discount factor — qué tan miope/largoplacista es el agente |
| ε-greedy | Exploración con probabilidad ε, explotación con 1−ε |
| Bellman equation | La ecuación recursiva de los value functions |

## Diseño concreto del problema RL para nuestro Otter

```
State:  s = [pos_self, R_self, pos_enemy, R_enemy, health_self, power_self, health_enemy, distance_to_landing, ...]
Action: a = [thrust ∈ {-1,0,+1}, steering ∈ {-1,0,+1}, fire ∈ {0,1}]  (puede ser continuo)
Reward: r = +100·hit_enemy + 50·kill_enemy − 10·hit_by_enemy − 100·died − 0.01·step
```

(Es un punto de partida — la función de reward es justamente lo que más cuesta diseñar; ver también `singh-levine-e2e-rl` para enfoques sin reward engineering manual)

## Conexión con código existente del repo

| Concepto Sutton-Barto | Archivo Wakuseibokan |
|----------------------|----------------------|
| Episode | `episodesmode` en [src/tests/testcase_131.cpp:298-317](src/tests/testcase_131.cpp#L298-L317) — `cleanall()` reinicia el escenario |
| Episode recording | [scripts/EpisodeRecorder.py](scripts/EpisodeRecorder.py) |
| RL support | [src/reinforcement.cpp](src/reinforcement.cpp) |
| State observation | `ModelRecord` recibido por UDP en [src/networking/telemetry.cpp:27-55](src/networking/telemetry.cpp#L27-L55) |
| Action execution | `ControlStructure2` enviado por UDP en [src/commandorder.h:103-117](src/commandorder.h#L103-L117) |

## Combinación con otros recursos

- **`braunl-embedded-robotics` cap 19** — backprop / NN como function approximator de cap 9 de Sutton
- **`thrun-probabilistic-robotics` cap 15-16** — MDP/POMDP desde otra perspectiva (más formal, menos didáctica que Sutton)
- **`singh-levine-e2e-rl`** (paper) — caso aplicado a robot manipulator real, evita reward engineering
- **`hwu-krichmar-neurorobotics`** (pendiente) — el cruce neurorobótico + RL

## Cuándo invocar esta skill

- Formalizar el problema del agente (MDP)
- Diseñar la función de reward
- Implementar Q-Learning, Sarsa, Actor-Critic
- Decidir entre tabular methods vs function approximation
- Tunear hyperparams: γ, ε, α, λ
- Análisis on-policy vs off-policy
- Cuando aparezca cualquier término RL: `Bellman`, `value function`, `policy`, `TD-error`, `eligibility trace`, etc.
