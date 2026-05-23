---
name: siegwart-mobile-robots
description: Roland Siegwart & Illah R. Nourbakhsh — Introduction to Autonomous Mobile Robots (MIT Press, 2004, 1ra ed). Libro oficial del curso Ramele. Cubre locomoción, cinemática de vehículos con ruedas, percepción, localización, planning y navegación. Invocar cuando se trate de cinemática del Otter (car-like 4 wheels), maneuverability, motion control con feedback, path planning, u obstacle avoidance.
---

# Siegwart & Nourbakhsh — Introduction to Autonomous Mobile Robots (2004)

**Archivo:** `docs/bibliografía/Introduction to Autonomous Mobile Robots book.pdf` (7.9 MB)
**Capítulo suelto:** `docs/bibliografía/Ch4_AMRobots.pdf` (Perception)
**Autores:** Roland Siegwart, Illah R. Nourbakhsh
**Editorial:** MIT Press, A Bradford Book, 2004 — ISBN 0-262-19502-X
**Edición:** 1ra (la 2da de 2011 agrega Scaramuzza con visión/SLAM moderno — **esta es la 1ra**)
**Sitio web complementario:** http://www.mobilerobots.org (slides y ejercicios)
**Estatus en el curso:** Oficial #4 (Ramele slide 54)

## Por qué importa para Wakuseibokan

Este es **el libro de cinemática del Otter**. El Otter es un vehículo car-like con 4 ruedas (2 delanteras steering) — exactamente la configuración que cubre Siegwart cap 2.3 y cap 3. Si necesitamos saber cómo se mueve el tanque, cómo se calculan trayectorias o cómo evita obstáculos, es acá.

## Tabla de contenidos completa

| Cap | Tema | Página | Relevancia agente |
|-----|------|--------|-------------------|
| 1 | Introduction | 1 | Background |
| 2 | **Locomotion** | 13 | 2.3 Wheeled Mobile Robots — diseño del Otter |
| | 2.1 Key issues for locomotion | 16 | |
| | 2.2 Legged Mobile Robots | 17 | Saltable (Otter no tiene patas) |
| | 2.3 **Wheeled Mobile Robots** | 30 | **Clave** |
| 3 | **Mobile Robot Kinematics** | 47 | **EL capítulo más importante** |
| | 3.2 Kinematic Models and Constraints | 48 | Forward kinematics, wheel & robot constraints |
| | 3.3 **Mobile Robot Maneuverability** | 67 | Degree of mobility, steerability, maneuverability |
| | 3.4 Mobile Robot Workspace | 74 | Holonomic vs non-holonomic |
| | 3.6 **Motion Control (Kinematic Control)** | 81 | Open-loop (trajectory) + **Feedback control** |
| 4 | Perception | 89 | Telemetría abstrae casi todo, pero útil para entender qué hay "debajo" |
| | 4.1 Sensors for Mobile Robots | 89 | Tipos de sensores (ojeada general) |
| | 4.2 Representing Uncertainty | 145 | Stats, error propagation |
| | 4.3 Feature Extraction | 151 | Range-based + visual |
| 5 | Mobile Robot Localization | 181 | **Saltable** — telemetría nos da pose exacta |
| | 5.6 Probabilistic Map-Based Localization | 212 | Markov, Kalman (ver Thrun si hace falta) |
| | 5.8 Autonomous Map Building (SLAM) | 250 | No aplica |
| 6 | **Planning and Navigation** | 257 | **Muy útil** |
| | 6.2 Competences for Navigation: Planning and Reacting | 258 | |
| | 6.2.1 **Path planning** | 259 | Para perseguir oponente |
| | 6.2.2 **Obstacle avoidance** | 272 | Evadir warehouses de la city del scenario 131 |
| | 6.3 Navigation Architectures | 291 | Modular, tiered architectures |

## Capítulos prioritarios para nuestro agente

**Esenciales:**
1. **Cap 2.3** (Wheeled Mobile Robots) — entender la configuración del Otter
2. **Cap 3** completo — cinemática, especialmente:
   - 3.2.3 Wheel kinematic constraints
   - 3.2.4 Robot kinematic constraints
   - 3.3 Maneuverability (degree of mobility, steerability)
   - 3.6 Motion control (feedback control)
3. **Cap 6.2.1** Path planning
4. **Cap 6.2.2** Obstacle avoidance — la city de warehouses en scenario 131 lo necesita

**Útiles para consulta:**
- Cap 6.3 Navigation architectures — para diseñar el agente híbrido

**Saltables:**
- Cap 2.2 (Legged Mobile Robots) — no aplica
- Cap 4 (Perception) — telemetría lo abstrae
- Cap 5 (Localization) — telemetría da pose

## Conceptos clave que aparecen

- **Holonomic vs Non-holonomic**: el Otter es non-holonomic (no puede moverse lateral). Constraint clave.
- **Degree of mobility (δm)**: grados de libertad instantáneos
- **Degree of steerability (δs)**: ruedas direccionables
- **Maneuverability (δM = δm + δs)**: para car-like típicamente 2
- **Forward kinematic model**: dado un input de ruedas, predice movimiento
- **Inverse kinematic model**: dada una trayectoria deseada, calcula ruedas
- **Feedback control**: cerrar el lazo con el error de posición
- **Bug algorithms**: clásicos de obstacle avoidance (Bug1, Bug2, etc.)
- **Vector Field Histogram (VFH)**: técnica popular de evasión
- **Roadmap, cell decomposition, potential fields**: enfoques de path planning

## Conexión con código existente del repo

| Concepto Siegwart | Archivo Wakuseibokan |
|------------------|----------------------|
| Wheeled car-like robot (cap 2.3, 3) | [src/units/Otter.cpp](src/units/Otter.cpp) + [src/units/Wheel.cpp](src/units/Wheel.cpp) |
| Wheels attached to body (4 ruedas, front steering) | [src/tests/testcase_131.cpp:142-179](src/tests/testcase_131.cpp#L142-L179) |
| Motion control feedback (cap 3.6) | [scripts/ControlPID.py](scripts/ControlPID.py) |
| Obstacle avoidance (cap 6.2.2) | (a implementar — warehouses en testcase_131) |
| Path planning (cap 6.2.1) | (a implementar) |

## Relación con la matriz R[12] de la telemetría

El paquete `ModelRecord` envía `R[12]` que es la **matriz de rotación 3×4 de ODE** (rotación 3×3 + posición 1×3). Para usarla:
- Las primeras 9 componentes son la rotación
- Se pueden convertir a ángulos de Euler (yaw/pitch/roll) usando las fórmulas de Siegwart 3.2.1

## Cuándo invocar esta skill

- Modelar la cinemática del Otter (mobility, steerability)
- Diseñar feedback control de posición/orientación
- Path planning del agente
- Obstacle avoidance (la city de warehouses)
- Convertir entre representaciones de orientación (Euler, matriz, quaternion)
- Calcular trayectorias hacia el oponente
