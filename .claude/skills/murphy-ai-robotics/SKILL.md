---
name: murphy-ai-robotics
description: Robin R. Murphy — Introduction to AI Robotics (MIT Press, 2000). Libro oficial del curso Ramele. Cubre los tres paradigmas robóticos clásicos (jerárquico, reactivo, híbrido), behaviors, subsumption, potential fields, y navegación. Invocar cuando se trate de decidir arquitectura del agente, behaviors, sensor fusion, path planning para el Otter, o multi-agentes.
---

# Murphy — Introduction to AI Robotics (2000)

**Archivo:** `docs/bibliografía/Introduction to AI Robotics - Murphy R.R.pdf` (13.5 MB)
**Autor:** Robin R. Murphy
**Editorial:** MIT Press, A Bradford Book, 2000 — ISBN 0-262-13383-0
**Serie:** Intelligent Robots and Autonomous Agents (Ronald C. Arkin, editor)
**Estatus en el curso:** Oficial #3 (Ramele slide 54)

## Por qué importa para Wakuseibokan

Este libro **enmarca toda la discusión de arquitectura del agente**. Los tres paradigmas que define (jerárquico, reactivo, híbrido) son las opciones reales de diseño. El enfoque neurorobótico que elegimos vive **dentro** de uno de estos paradigmas (probablemente híbrido o reactivo+aprendizaje).

Murphy es **alumna de Arkin** (su editor de serie) — esto explica por qué `arkin-behavior-based-robotics` (pendiente) será un complemento natural.

## Tabla de contenidos

### Part I — Robotic Paradigms (p 1)

| Cap | Tema | Página | Relevancia agente |
|-----|------|--------|-------------------|
| 1 | From Teleoperation To Autonomy | 13 | Contexto histórico |
| 2 | **The Hierarchical Paradigm** | 41 | STRIPS, Nested Hierarchical Controller, NIST RCS. Paradigma "viejo" (sense-plan-act). |
| 3 | **Biological Foundations of the Reactive Paradigm** | 67 | Behaviors animales, schemas (Arbib), Gibson ecological approach, Neisser two-perceptual-systems. Base teórica de behaviors. |
| 4 | **The Reactive Paradigm** | 105 | **Subsumption Architecture (Brooks)** + **Potential Fields**. Capítulo clave. |
| 5 | **Designing a Reactive Implementation** | 155 | Behaviors como objetos OOP, FSA, ensamblajes, scripts. **Cómo se programan**. |
| 6 | Common Sensing Techniques for Reactive Robots | 195 | Sensor fusion, logical sensors. |
| 7 | **The Hybrid Deliberative/Reactive Paradigm** | 257 | El paradigma moderno: combina planning + reacción. **Probablemente lo que necesita nuestro agente**. |
| 8 | Multi-agents | 293 | Para cuando haya múltiples Otters aliados. |

### Part II — Navigation (p 315)

| Cap | Tema | Página | Relevancia agente |
|-----|------|--------|-------------------|
| 9 | Topological Path Planning | 325 | Navegación por grafos/landmarks. |
| 10 | **Metric Path Planning** | 351 | Planificación en coordenadas. Útil para perseguir oponente. |
| 11 | Localization and Map Making | 375 | (Menos útil — el simulador nos da pose) |
| 12 | On the Horizon | 435 | Outlook. |

## Capítulos prioritarios para nuestro agente

**Empezar por:**
1. **Cap 4 (Reactive Paradigm)** — entender subsumption + potential fields antes de diseñar nada
2. **Cap 5 (Designing Reactive Implementation)** — patrón OOP para behaviors. Mirá cómo encaja con `scripts/Subsumption.py` ya existente
3. **Cap 7 (Hybrid Paradigm)** — la arquitectura más probable para nuestro agente neuronal
4. **Cap 10 (Metric Path Planning)** — para targeting del oponente

**Saltar/ojear:**
- Cap 1 (histórico)
- Cap 2 (paradigma jerárquico — ya superado)
- Cap 11 (localización — innecesario, telemetría nos da pose)

## Conceptos clave que aparecen

- **Sense-Plan-Act vs Sense-Act**: paradigma jerárquico vs reactivo
- **Subsumption Architecture**: behaviors en capas con inhibición/supresión
- **Potential Fields**: campos atractivos/repulsivos
- **Schemas (Arbib)**: alternativa OO a subsumption
- **Action-Perception Cycle (Gibson)**: percepción tied to action
- **Releasers (innate releasing mechanisms)**: trigger de behaviors
- **Behaviors como objetos OOP**: implementación práctica
- **FSA para coordinación**: ensamblar behaviors

## Conexión con código existente del repo

| Concepto Murphy | Archivo Wakuseibokan |
|----------------|----------------------|
| Subsumption Architecture (cap 4) | [scripts/Subsumption.py](scripts/Subsumption.py) |
| Hybrid paradigm (cap 7) | [scripts/Controller.py](scripts/Controller.py) (mixto) |
| PID-style control reactivo | [scripts/ControlPID.py](scripts/ControlPID.py) |
| Seek and destroy behavior | [scripts/SeekAndDestroy.py](scripts/SeekAndDestroy.py) |

## Cuándo invocar esta skill

- Diseñar la arquitectura del agente (¿reactivo? ¿híbrido? ¿deliberativo?)
- Implementar behaviors específicos (seguir, evadir, atacar)
- Combinar múltiples behaviors (subsumption vs schemas vs potential fields)
- Diseñar sensor fusion sobre los campos de la telemetría
- Path planning del Otter hacia un objetivo
