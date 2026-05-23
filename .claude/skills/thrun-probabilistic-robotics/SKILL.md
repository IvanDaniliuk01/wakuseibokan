---
name: thrun-probabilistic-robotics
description: Sebastian Thrun, Wolfram Burgard, Dieter Fox — Probabilistic Robotics (MIT Press, 2005). Libro de referencia para filtros bayesianos, Kalman/EKF, particle filters, SLAM, MDP y POMDP. NO está en la lista oficial del curso Ramele pero Ivan lo sumó. Para Wakuseibokan tiene relevancia limitada porque la telemetría ya da pose resuelta; útil principalmente para MDP/POMDP (caps 15-16) si se formaliza el agente como decisor, o para tracking del oponente con observaciones ruidosas.
---

# Thrun, Burgard, Fox — Probabilistic Robotics (Early Draft 1999-2000)

**Archivo:** `docs/bibliografía/ProbabilisticRobotics.pdf` (15 MB) — **EARLY DRAFT (NOT FOR DISTRIBUTION)**, copyright 1999-2000
**Autores:** Sebastian Thrun (Stanford), Wolfram Burgard (Freiburg), Dieter Fox (Washington)
**Editorial:** MIT Press, 2005 (la edición publicada) — pero **el PDF que tenemos es un draft anterior**
**Estatus en el curso:** **NO oficial**. Ivan lo sumó por reputación general del libro, pero Ramele no lo lista en su bibliografía.

## Por qué la relevancia es LIMITADA para Wakuseibokan

Este libro es **EL libro de la incertidumbre en robótica**: filtros bayesianos, Kalman, particle filters, SLAM. **Casi todo eso está abstraído por el simulador**:

- La telemetría nos da `pos` y `R[12]` **resueltas**, sin ruido → no hace falta estimar pose (caps 7-8)
- No estamos haciendo mapping → caps 9-14 saltables
- No hay sensores ruidosos en el formato de telemetría → caps 6 saltable

**Lo único que se rescata:** Cap 15-16 (MDP / POMDP) — útil si formalizamos el agente como un decisor bajo incertidumbre del oponente.

## Tabla de contenidos completa

| Cap | Tema | Página | Relevancia agente |
|-----|------|--------|-------------------|
| 1 | Introduction | 1 | Lectura general |
| 2 | **Recursive State Estimation** | 9 | Bayes Filters — base teórica de todo el libro |
| 3 | **Gaussian Filters** | 33 | **Kalman**, EKF, Information Filter. Base de tracking. |
| 4 | Nonparametric Filters | 67 | Histogram, **Particle Filter** |
| 5 | Robot Motion | 91 | Velocity Motion Model, Odometry Motion Model |
| 6 | Measurements | 121 | Beam Models, Likelihood Fields |
| 7 | Mobile Robot Localization | 157 | Markov, EKF Localization, Multi-Hypothesis Tracking |
| 8 | Grid and Monte Carlo Localization | 187 | MCL |
| 9 | Occupancy Grid Mapping | 221 | |
| 10 | SLAM | 245 | SLAM con EKF |
| 11 | Extended Information Form Algorithm | 267 | SLAM eficiente |
| 12 | Sparse Extended Information Filter | 303 | SEIF SLAM |
| 13 | Mapping with Unknown Data Association | 353 | EM Mapping |
| 14 | Fast Incremental Mapping Algorithms | 393 | |
| 15 | **Markov Decision Processes** ⭐ | 421 | Value Iteration, control policies |
| 16 | **Partially Observable MDPs** ⭐ | 437 | POMDPs — el problema real cuando el oponente no es totalmente observable |

## Capítulos prioritarios para nuestro agente

**Útiles (si surgen):**

1. **Cap 15 (MDP)** — formalizar el problema del agente como Markov Decision Process. Útil si el agente termina siendo de RL, porque Sutton & Barto también usa MDP como formalismo central.
2. **Cap 16 (POMDP)** — más realista: el agente no ve **completamente** al oponente (sus intenciones son ocultas). Formalizar como POMDP da pie a estrategias más sofisticadas.
3. **Cap 7.7 (Multi-Hypothesis Tracking)** — si queremos trackear posibles trayectorias futuras del oponente.

**Saltables (casi todo el resto):**
- Caps 2-4 (filtros): nice to know, no aplicable
- Caps 5-6 (motion + measurements): el simulador ya los resuelve
- Caps 7-14 (localization + mapping): innecesario, telemetría da pose exacta

## Conceptos clave (por si surgen)

- **Belief state**: distribución de probabilidad sobre estados
- **Bayes Filter**: recursión `bel(x_t) = η · p(z_t | x_t) · ∫ p(x_t | u_t, x_{t-1}) · bel(x_{t-1}) dx_{t-1}`
- **Kalman Filter**: caso lineal-gaussiano
- **Extended Kalman Filter (EKF)**: linealización por Taylor
- **Particle Filter (MCL)**: representación por muestras
- **Markov assumption**: estado actual contiene toda la info relevante
- **MDP**: ⟨S, A, T, R, γ⟩ — base de RL
- **POMDP**: MDP con observaciones parciales

## Conexión con Sutton & Barto

El cap 15 (MDP) de Thrun **se solapa con caps 3-5 de Sutton & Barto**. Si necesitamos formalismo MDP para el agente, **preferir Sutton & Barto** (más didáctico y orientado a learning). Thrun cap 15 es más para planning con MDP conocido.

## Cuándo invocar esta skill

- Formalizar el problema del agente como MDP (cap 15) o POMDP (cap 16)
- Si en algún momento necesitamos trackear al oponente con observaciones ruidosas
- Si extendemos el simulador para que la telemetría tenga ruido (no es el caso ahora)
- Referencia matemática para algoritmos bayesianos (raro que aplique)

## Por qué NO invocar esta skill

- Cualquier cosa que tenga que ver con cinemática del Otter → `siegwart-mobile-robots`
- Diseño de arquitectura del agente → `murphy-ai-robotics`
- Implementación de red neuronal → `braunl-embedded-robotics`
- RL → `sutton-barto-rl`
