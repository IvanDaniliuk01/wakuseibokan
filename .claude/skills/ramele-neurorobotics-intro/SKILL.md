---
name: ramele-neurorobotics-intro
description: Presentación del curso Neurorobotics de Rodrigo Ramele (ITBA, Lab Neurotrónica / Centro de Inteligencia Computacional). 55 slides que ubican Wakuseibokan dentro del curso, definen neurorobótica, taxonomías de robótica, IoRT, casos de uso. Invocar cuando se pregunte sobre el marco conceptual del curso, la filosofía del enfoque, qué es neurorobótica, o por qué se usa este simulador.
---

# Ramele — Neurorobotics Intro

**Archivo:** `docs/bibliografía/1 - Neurorobots.pdf` (33 MB, 55 slides)
**Autor:** Rodrigo Ramele — Lab Neurotrónica / Centro de Inteligencia Computacional, Departamento de Ingeniería Informática, ITBA
**Tipo:** Presentación introductoria del curso

## Filosofía / lema del curso

> **"There is no intelligence, without action."**

Embodied cognition — la inteligencia emerge de la interacción agente-entorno, no del razonamiento abstracto. Por eso el curso usa un simulador físico (ODE) y no un solver de planificación simbólica.

## Estructura del curso (4 bloques / 8 días)

| Bloque | Contenido | Días |
|--------|-----------|------|
| Block 1 | Mechatronics / Agents / Sensing / Actuation / Robotics Intro | 1-2 |
| Block 2 | Neuroscience / Neurons / Action Potential / Modelling / Wearables / BCI | 3-4 |
| Block 3 | Human-Centred Robotics / Human Augmentation | 5-6 |
| Block 4 | Real World Robots / Simulation and Combat | **7-8** |

| Día | Tema |
|-----|------|
| 1 | Introduction to Neurorobotics |
| 2 | Robotics and Mechatronics |
| 3 | Reinforcement Learning |
| 4 | Brain-Computer Interfaces |
| 5 | Practical Internet of Robotic Things |
| 6 | Virtual: Rehabilitation Robotics |
| **7** | **Robot Simulation Practice** ← Wakuseibokan |
| **8** | **Robot Simulation Arena** ← evaluación final |

## Evaluación (slide "Marking and Passing")

> **"Beat the other mobile robots in the Robot Simulator. Winner takes all!"**

El agente UDP que se desarrolla en este repo es la entrega de evaluación.

## Taxonomía de neurorobótica (slide 10-11)

```
Cognitive Robotics (conjunto grande)
  ├── Developmental Robotics
  └── Reactive Robotics
```

## Conceptos clave por slide

### Biomimesis (slide 12) — acota expectativas de complejidad

Tabla de neuronas por especie:
- Nematodo: **302 neuronas**
- Mosca: 100.000
- Abeja: 960.000
- Ratón: 75M
- Gato: 1B
- Humano: 85B

**Implicancia:** una red neuronal de cientos a pocos miles de neuronas debería sobrar para un Otter (orientarse, perseguir, disparar). No hace falta arquitectura tipo LLM.

### Digital Automation (slide 21)

Arcos concéntricos: Human Capacity ⊂ AI ⊂ Superhuman Capacity. Para dominios acotados como el simulador, el agente puede operar en la franja superhuman.

### Stack IoRT (slide 19)

```
Application      ← acá vive el agente neuronal
Infrastructure   ← Python runtime / framework NN
Internet         ← UDP (implementado)
Network          ← UDP (implementado)
Hardware         ← simulador ODE (implementado)
```

### Use cases (slide 28)

Primer caso de uso listado: **Telemetry — "Access data and control anything virtually from anywhere"**. Es exactamente lo que implementa `src/networking/telemetry.cpp`.

### Gaming and Computer Graphics (slide 38) — justificación del simulador

> **Simulated World**: "an agent needs to be able to play alongside humans, even beat them in a controlled environment."
>
> **3D Motion**: "Gaming shares the problem of direct kinematic, dynamics, translations and rotations."

Esto justifica usar un juego: los problemas de gaming = problemas de robótica real (cinemática, dinámica, rotaciones — de ahí la matriz `R[12]` 3×4 de ODE en la telemetría).

### Disciplinas que se cruzan (slide 6)

Pentágono: **Neuroscience + Control + Mechanics + Informatics + Electronics**.

### Mechatronics (slide 8)

Definición clásica (Yaskawa, 1969): **Electrónica + Control + Informática + Mecánica**.

## Conclusiones (slide 52)

1. **Robotics is Data Actuation. IoRT is a way forward to implement this actuation.**
2. Pushes ahead the digital frontier.
3. Can be used as a human-augmentation strategy.
4. Security is a major concern, but properly handled they can be overcome.

## Bibliografía oficial del curso (slides 54-55)

Lista oficial de 7 libros (ver `bibliografia-curso` skill para detalle):

1. Hwu & Krichmar — Neurorobotics: Connecting the Brain, Body, and Environment
2. Anandan et al — Human Communication Technology / IoRT
3. Murphy — Introduction to AI Robotics
4. Siegwart & Nourbakhsh — Introduction to Autonomous Mobile Robots
5. Bishop — Mechatronics: An Introduction
6. **Arkin — Behavior-Based Robotics**
7. Bräunl — Embedded Robotics

## Conexión con el código de Wakuseibokan

| Slide | Conecta con |
|-------|-------------|
| 19 (IoRT stack) | `src/networking/` — UDP en Network+Internet layers |
| 28 (Telemetry use case) | `src/networking/telemetry.cpp` |
| 38 (3D Motion: kinematic, rotations) | `R[12]` en `ModelRecord` — matriz 3×4 ODE |
| 12 (Biomimesis) | Define escala de NN: cientos-miles de neuronas, no millones |

## Cuándo usar este recurso

- Cualquier pregunta sobre **por qué** se hace algo en el curso de Ramele.
- Para entender la filosofía embodied cognition aplicada.
- Para ubicar dónde está cada tema en el outline del curso.
- Antes de empezar a diseñar el agente — leer al menos los slides 6, 10-12, 19, 28, 38.
