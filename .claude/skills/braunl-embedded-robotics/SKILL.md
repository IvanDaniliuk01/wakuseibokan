---
name: braunl-embedded-robotics
description: Thomas Bräunl — Embedded Robotics: Mobile Robot Design and Application with Embedded Systems (Springer, 2da ed 2006). Libro oficial del curso Ramele. Especialmente relevante porque cubre Neural Networks, Behavior-Based Systems con Neural Network Controller, Genetic Algorithms para robot control, Ackermann steering, y Robot Soccer (paralelo directo a nuestra arena de combate). Invocar cuando se trate de implementar el agente neuronal, PID, behaviors, evolutionary methods, o cinemática Ackermann del Otter.
---

# Bräunl — Embedded Robotics (2da ed, 2006)

**Archivo:** `docs/bibliografía/Embedded%20Robotics%20-%20Thomas%20Braunl.pdf` (5.5 MB)
**Autor:** Thomas Bräunl — School of Electrical, Electronic and Computer Engineering, University of Western Australia (UWA), Perth
**Editorial:** Springer Berlin, 2da edición 2006 — ISBN 978-3-540-34318-9
**Subtítulo:** Mobile Robot Design and Applications with Embedded Systems
**Estatus en el curso:** Oficial #7 (Ramele slide 55)
**Sitio web complementario:** http://robotics.ee.uwa.edu.au

## Por qué importa para Wakuseibokan

**Es el libro oficial más útil que tenemos.** Es práctico, tiene código C, y cubre **simultáneamente**:
- **Neural Networks aplicadas a control de robots** (cap 19, 22.7) — directo al enfoque elegido
- **Behavior-Based Systems con Neural Network Controller** (cap 22) — mientras Arkin no esté disponible, este es el reemplazo
- **Genetic Algorithms y Genetic Programming** para entrenar agentes (cap 20-21)
- **Robot Soccer (RoboCup/FIRA)** (cap 18) — paralelo directo a nuestra arena de combate
- **Ackermann steering + drive kinematics** (cap 7) — el Otter
- **Sistemas de simulación EyeSim y SubSim** (cap 13) — Bräunl también desarrolla simuladores

Bräunl es el autor de **EyeBot / EyeSim**, un ecosistema completo de robots + simulador. Es muy probable que Ramele haya tomado inspiración de su enfoque pedagógico.

## Tabla de contenidos

### Part I — Embedded Systems

| Cap | Tema | Página | Relevancia agente |
|-----|------|--------|-------------------|
| 1 | Robots and Controllers | 3 | Background |
| 2 | Sensors | 17 | Bajo nivel — el simulador abstrae |
| 3 | Actuators | 41 | DC Motors, PWM, Servos — abstraído |
| 4 | **Control** | 51 | On-Off, **PID Control**, Velocity/Position Control, **V-Omega Interface** |
| 5 | Multitasking | 69 | Cooperative/Preemptive, scheduling |
| 6 | Wireless Communication | 83 | (Tangencial — usamos UDP) |

### Part II — Mobile Robot Design

| Cap | Tema | Página | Relevancia agente |
|-----|------|--------|-------------------|
| 7 | **Driving Robots** | 97 | **Ackermann Steering (7.5) + Drive Kinematics (7.6) = el Otter** |
| 8 | Omni-Directional Robots | 113 | (Otter no es omni) |
| 9 | Balancing Robots | 123 | (No aplica) |
| 10 | Walking Robots | 131 | (No aplica) |
| 11 | Autonomous Planes | 151 | (No aplica al Otter) |
| 12 | Autonomous Vessels and AUVs | 161 | (No aplica) |
| 13 | **Simulation Systems** | 171 | **EyeSim, SubSim** — referencias de simuladores comparables a Wakuseibokan |

### Part III — Mobile Robot Applications

| Cap | Tema | Página | Relevancia agente |
|-----|------|--------|-------------------|
| 14 | **Localization and Navigation** | 197 | **A*, Dijkstra, Potential Field Method, Wandering Standpoint, DistBug** |
| 15 | Maze Exploration | 217 | Micro Mouse Contest |
| 16 | Map Generation | 229 | (Saltable) |
| 17 | Real-Time Image Processing | 243 | (No tenemos cámara) |
| 18 | **Robot Soccer** | 263 | **RoboCup, FIRA, Team Structure, Trajectory Planning** — paralelo directo a combate de tanques |
| 19 | **Neural Networks** | 277 | **Feed-Forward, Backpropagation, Neural Controller** ⭐ |
| 20 | **Genetic Algorithms** | 291 | **Para entrenar el agente** |
| 21 | Genetic Programming | 307 | Lisp-style evolution, Tracking |
| 22 | **Behavior-Based Systems** | 325 | **Software architecture, Framework, Adaptive Controller, Neural Network Controller** ⭐⭐ |
| 23 | Evolution of Walking Gaits | 345 | (No aplica) |
| 24 | Outlook | 357 | |

### Apéndices

- A: Programming Tools
- B: RoBIOS Operating System
- C: Hardware Description Table
- D: Hardware Specification
- E: Laboratories
- F: Solutions

## Capítulos prioritarios para nuestro agente

**Esenciales (orden recomendado de lectura):**

1. **Cap 7.5-7.6** (Ackermann + Drive Kinematics) — la mecánica del Otter
2. **Cap 4.2** (PID Control) — comparar con [scripts/ControlPID.py](scripts/ControlPID.py)
3. **Cap 19** (Neural Networks) completo — feed-forward + backprop + Neural Controller
4. **Cap 22** (Behavior-Based Systems) completo, **especialmente 22.7 Neural Network Controller** — el cruce neurorobótico+behaviors
5. **Cap 18** (Robot Soccer) — analogía directa con nuestra arena
6. **Cap 20** (Genetic Algorithms) — método alternativo de entrenamiento si backprop no alcanza
7. **Cap 14** (Localization and Navigation) — A* y Potential Field para targeting

**Útiles:**
- Cap 4.5 (V-Omega Interface) — abstracción común para mobile robots (velocidad lineal + angular)

**Saltables:**
- Cap 1-3 (hardware), 8-12 (otras configuraciones), 15-17 (maze, mapping, vision)
- Cap 23 (gaits)

## Conexión con código existente del repo

| Concepto Bräunl | Archivo Wakuseibokan |
|-----------------|----------------------|
| Ackermann steering (cap 7.5) | [src/units/Otter.cpp](src/units/Otter.cpp) — Otter tiene front-wheel steering |
| PID Control (cap 4.2) | [scripts/ControlPID.py](scripts/ControlPID.py) |
| Behavior-Based Systems (cap 22) | [scripts/Subsumption.py](scripts/Subsumption.py) |
| Neural Network Controller (cap 22.7) | A implementar — núcleo del agente |
| Robot Soccer team structure (cap 18) | Multi-Otter strategy (futuro) |
| Potential Field (cap 14.6) | Para evadir warehouses del scenario 131 |
| EyeSim / SubSim (cap 13) | Análogo a Wakuseibokan |

## Conceptos clave que aparecen

- **V-Omega interface**: abstracción (velocidad lineal v, velocidad angular ω) — interfaz universal para mobile robots, independiente del tipo de drive
- **Ackermann steering**: geometría del Otter (4 ruedas, 2 frontales que giran)
- **Drive kinematics**: forward + inverse kinematics
- **Backpropagation**: training de redes feed-forward
- **Neural Controller**: red neuronal que mapea sensores → motores
- **GA operators**: selección, crossover, mutación aplicados a robots
- **Behavior framework**: arquitectura de software para behaviors
- **Adaptive Controller**: behavior que aprende online

## Por qué Bräunl > Murphy/Siegwart para este agente

- **Murphy** te dice qué arquitecturas existen.
- **Siegwart** te da la cinemática rigurosa.
- **Bräunl** te muestra **cómo programar** un agente neuronal+behavior-based con código real. Es el más cercano a "manos a la obra".

## Cuándo invocar esta skill

- Implementar Neural Network Controller (cap 19, 22.7)
- Entrenar agente con Genetic Algorithm (cap 20)
- Modelar Ackermann steering del Otter (cap 7.5)
- Diseñar V-Omega interface para abstraer control (cap 4.5)
- PID tuning (cap 4.2)
- Comparar arquitecturas para nuestra arena (cap 18 Robot Soccer)
- Potential Field para obstacle avoidance (cap 14.6)
