---
name: singh-levine-e2e-rl
description: Paper de Avi Singh, Larry Yang, Kristian Hartikainen, Chelsea Finn, Sergey Levine (UC Berkeley, arXiv 1904.07854v2, May 2019). "End-to-End Robotic Reinforcement Learning without Reward Engineering" — aprende skills robóticos desde imágenes sin diseñar manualmente la función de reward, usando un clasificador entrenado con outcome examples + active queries binarias del usuario. Usa Soft Actor-Critic (SAC) como base. Invocar cuando se discuta diseño de reward function, alternativas a hand-engineered rewards, o algoritmos RL modernos para robots (SAC, maximum entropy RL).
---

# Singh, Yang, Hartikainen, Finn, Levine — End-to-End Robotic RL without Reward Engineering (2019)

**Archivo:** `docs/bibliografía/1904.07854v2.pdf` (7.8 MB)
**ID:** arXiv:1904.07854v2 [cs.LG]
**Fecha:** 16 May 2019
**Autores:** Avi Singh, Larry Yang, Kristian Hartikainen, **Chelsea Finn**, **Sergey Levine** (University of California, Berkeley)
**Tipo:** Paper de conferencia (Robotics: Science and Systems / RSS 2019)
**Sitio:** sites.google.com/view/reward-learning-rl/

## Por qué importa para Wakuseibokan

Este paper resuelve **el problema más práctico de RL en robótica**: cómo definir la función de reward. Para nuestro Otter, la reward "obvia" (+ por daño al enemigo, − por daño recibido) **puede no ser suficiente** — el agente puede aprender a campear, esquivar pero no atacar, etc. El enfoque del paper:

> Entrenar un clasificador sobre **ejemplos de outcomes exitosos** + hacer **active queries binarias** al usuario ("¿esto es una victoria?") → usar el clasificador como reward function.

Para nuestro caso podría traducirse a: en vez de reward analítica, mostrar al usuario screenshots/states "esto es una buena posición de combate" vs "esto es mala" → el agente aprende la noción de "buena estrategia" sin que la formalicemos.

**El paper usa Soft Actor-Critic (SAC)** — algoritmo moderno de RL que probablemente conviene como base para nuestro agente.

## Estructura del paper

| Sección | Contenido |
|---------|-----------|
| **I. Introduction** | Plantea el problema: hand-engineering reward functions es costoso y específico a cada task |
| **II. Related Work** | RL en manipulación robótica (grasping, in-hand manipulation, fluid manipulation, door opening, cloth folding). Data-driven reward specification. Active learning para inverse RL. Classifier-based rewards (VICE). |
| **III. Preliminaries** | |
| III.a | **Maximum Entropy RL**: objetivo `J(π) = Σ E[r(s,a) − log π(a|s)]` |
| III.a | **Soft Actor-Critic (SAC)** — Algorithm 1 en el paper |
| III.b | Classifier-Based Rewards — Algorithm 2 |
| **IV. Reinforcement Learning with Active Queries (RAQ)** | Su contribución principal: clasificador + active queries binarias, extendido a off-policy |
| **V. Experiments** | Tasks reales: draping cloth, placing books, pushing mugs onto coaster |
| **VI. Conclusion** | 1-4 horas de interacción real bastan |

## Conceptos clave para el agente Otter

### Maximum Entropy RL

```
J(π) = Σ_t E[ r(s_t, a_t) − log π(a_t | s_t) ]
```

A diferencia de RL clásico que maximiza solo retorno esperado, **maximum entropy RL** suma un término de entropía. Beneficios:
- **Robustez**: políticas no muy "puntudas" — generaliza mejor a ruido
- **Exploración**: la entropía empuja a explorar
- **Combinable con classifier-based rewards** sin colapsar

### Soft Actor-Critic (SAC) — Algorithm 1

```
1: Initialize policy π, critic Q
2: Initialize replay buffer R
3: for each iteration do
4:   for each environment step do
5:     a_t ~ π(a_t | s_t)
6:     s_{t+1} ~ p(s_{t+1} | s_t, a_t)
7:     R ← R ∪ {(s_t, a_t, r(s_t, a_t), s_{t+1})}
8:   for each gradient step do
9:     Sample from R
10:    Update π and Q (Haarnoja et al.)
```

Es **off-policy** (usa replay buffer) y **actor-critic** (entrena policy `π` y critic `Q` en paralelo).

### Classifier-based Rewards — Algorithm 2

```
Require: D_τ := {(s_n, y_n)}    # estados con label éxito/fracaso
1: Update parameters of g (classifier) to minimize Σ L(g(s_n), y_n)
2: Run RL or planning, using reward derived from log p_g(y | s)
```

El clasificador `g` da `p(éxito | s)`. La reward es `log p_g(y | s)`.

### Active Queries (RAQ)

En lugar de fijar el dataset `D_τ` al principio, durante el training el agente **pregunta al usuario**: "¿este estado es éxito?". El usuario responde **binario** (sí/no). Esto es:
- Mucho más barato que demonstrations
- Mucho más barato que reward shaping manual

Sus experiments: **75 queries** vs **miles** de queries que necesitan métodos comparables.

## Aplicación al Otter

| Pieza del paper | Cómo aplicaría al Otter |
|-----------------|--------------------------|
| State `s_t` (imagen) | Telemetría — `ModelRecord` o sus features |
| Action `a_t` | `ControlStructure2` — thrust/roll/pitch/yaw/fire |
| Outcome examples | Estados de "victoria buena" (enemigo destruido, propio sano) |
| Active queries | Usuario marca "esto es buena estrategia / mala" mirando los episodios |
| SAC actor-critic | Política neuronal + Q-network — exactamente lo que necesitamos |
| Replay buffer | Almacenar `(s, a, r, s')` de episodios pasados |

## Por qué el agente del Otter podría usar este enfoque

- La reward "intuitiva" (daño al enemigo) es **sparse**: pasan muchos pasos sin daño.
- La reward de "buena posición estratégica" es **densa pero difícil de formalizar** (ángulo de fuego, distancia óptima, terreno, etc.).
- Un clasificador entrenado por humanos puede capturar nociones "blandas" que escapan a una fórmula.

## Limitaciones del enfoque para nuestro caso

- El paper trabaja con **manipulation** (cloth, books, mugs) — tareas con outcomes claros.
- En **combat**, el outcome es claro (victoria/derrota) pero la calidad de cada step es menos clara.
- Necesita usuario disponible para queries — para nosotros eso podría ser **vos respondiendo durante el training**.

## Conexión con otros recursos

- **`sutton-barto-rl`** — base teórica de RL, especialmente caps 6 (TD), 9 (function approximation), 11 (actor-critic). SAC está en la edición 2018 final.
- **`braunl-embedded-robotics` cap 19, 22** — neural network como function approximator
- **`hwu-krichmar-neurorobotics`** (pendiente) — enfoque alineado con neurorobótica embodied
- Sergey Levine tiene un curso completo de Deep RL en Berkeley (CS285) — todo en YouTube y disponible online

## Citas relacionadas en el paper (de Related Work)

Listo las más importantes que el paper cita y podrían interesar:

- **VICE** (Variational Inverse Control with Events) — predecesor que extienden
- **SAC** (Haarnoja et al.) — el algoritmo base
- **Deep RL from human preferences** (Christiano et al.) — alternativa con queries de comparación trayectoria-vs-trayectoria
- Inverse Reinforcement Learning (varios)

## Cuándo invocar esta skill

- Discutir cómo diseñar la reward function del Otter
- Si la reward analítica no funciona y queremos clasificador
- Elegir algoritmo RL: **SAC** es probablemente el mejor punto de partida moderno
- Maximum entropy RL como alternativa a Q-Learning clásico
- Active learning para reducir el costo de supervisión
- Function approximation con redes neuronales en RL
