---
name: bibliografia-curso
description: Índice maestro de la bibliografía del curso Neurorobotics (ITBA, Ramele) que usa Wakuseibokan como plataforma. Invocar cuando se necesite ubicar qué libro/recurso cubre un tema específico (cinemática, behavior-based, RL, etc.) antes de consultar la skill específica de cada libro.
---

# Bibliografía del curso Neurorobotics — Índice

Curso de Rodrigo Ramele (Lab Neurotrónica / Centro de Inteligencia Computacional, ITBA). Wakuseibokan es la plataforma de evaluación del curso.

Cuando alguien pregunte sobre un tema, **primero consultá este índice** para saber qué skill específica invocar.

## Recursos disponibles en `docs/bibliografía/`

### Skills creadas

| Skill | Recurso | Tema | Status |
|-------|---------|------|--------|
| `ramele-neurorobotics-intro` | Ramele — Neurorobotics Intro (PDF curso) | Marco conceptual completo del curso | ✓ |
| `murphy-ai-robotics` | Murphy — Introduction to AI Robotics | Arquitecturas deliberativa/reactiva/híbrida | ✓ |
| `siegwart-mobile-robots` | Siegwart — Autonomous Mobile Robots | Cinemática, locomoción, percepción, planning | ✓ |
| `braunl-embedded-robotics` | Bräunl — Embedded Robotics | Robots embebidos, control de motores, behaviors | ✓ |
| `thrun-probabilistic-robotics` | Thrun — Probabilistic Robotics | Filtros bayesianos, Kalman, SLAM | ✓ |
| `sutton-barto-rl` | Sutton & Barto — Reinforcement Learning | RL desde cero | ✓ |
| `singh-levine-e2e-rl` | Singh & Levine — paper End-to-End RL | RL aplicado a robots sin reward engineering | ✓ |
| `corke-robotics-toolbox` | Corke — Robotics Toolbox for MATLAB | Manual del toolbox, kinemática/dinámica con código | ✓ |

### Skills pendientes (PDFs no conseguidos al 2026-05-23)

| Skill | Recurso | Por qué importa |
|-------|---------|-----------------|
| `hwu-krichmar-neurorobotics` | Hwu & Krichmar — Neurorobotics (MIT 2022) | **EL libro central del enfoque del curso. Prioridad máxima.** |
| `arkin-behavior-based-robotics` | Arkin — Behavior-Based Robotics (MIT 1998) | Subsumption, behaviors. Conecta con `scripts/Subsumption.py` |

### Descartados por irrelevantes para este proyecto

- **Bishop — Mechatronics: An Introduction**: el simulador abstrae todo el hardware (motores, sensores, encoders). Si surge un tema mecatrónico puntual, Siegwart cap 2 lo cubre.
- **Anandan et al — Human Communication Technology / IoRT**: cubre arquitecturas IoRT complejas (MQTT, brokers, edge/cloud). Wakuseibokan resuelve la red con UDP a `127.0.0.1` — no necesitamos esa capa.

## Routing por tema

Cuando aparezca uno de estos temas, **invocar la skill correspondiente**:

| Tema | Skill principal | Apoyo |
|------|----------------|-------|
| ¿Qué enfoque uso para el agente? | `ramele-neurorobotics-intro` | — |
| Arquitectura de agente (deliberativa/reactiva/híbrida) | `murphy-ai-robotics` | `arkin-behavior-based-robotics` (pendiente) |
| Behaviors, subsumption, schemas | `arkin-behavior-based-robotics` (pendiente) | `braunl-embedded-robotics` |
| Cinemática de vehículos con ruedas (Otter) | `siegwart-mobile-robots` cap 3 | `corke-robotics-toolbox` |
| Planning de trayectorias | `siegwart-mobile-robots` cap 6 | — |
| Localización del oponente con ruido | `thrun-probabilistic-robotics` | — |
| Entrenar política con RL | `sutton-barto-rl` | `singh-levine-e2e-rl` |
| Diseño de redes neuronales para control | `hwu-krichmar-neurorobotics` (pendiente) | `sutton-barto-rl` cap 9-13 |
| Rotaciones, quaterniones (matriz R[12] de telemetría) | `corke-robotics-toolbox` | `siegwart-mobile-robots` |

## Contexto del proyecto

- El agente recibe telemetría UDP en puerto `4600+tank` (formato `ModelRecord` 96 bytes — ver `src/networking/telemetry.cpp:27-55`).
- El agente envía comandos UDP a puerto `4500+tank` (formato `ControlStructure2` — ver `src/commandorder.h:103-117`).
- Scripts de referencia en `scripts/Controller.py`, `scripts/Subsumption.py`, `scripts/ControlPID.py`.
- Scenario competitivo: `src/tests/testcase_131.cpp` (combate de Otters).
