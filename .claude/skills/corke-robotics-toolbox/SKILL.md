---
name: corke-robotics-toolbox
description: Peter Corke — Robotics Toolbox for MATLAB, Release 9.10 manual (Feb 2015). Es el manual de referencia (auto-generado) del Robotics Toolbox de MATLAB, NO el libro pedagógico "Robotics, Vision and Control". Útil principalmente como referencia técnica para conversiones de rotación (matriz/Euler/RPY/quaternion), algoritmos de path planning clásicos (Bug2, D*, PRM, RRT), y clases para vehículos no-holonómicos. Invocar para consultas puntuales sobre rotaciones, transformaciones homogéneas, o algoritmos de planning como referencia.
---

# Corke — Robotics Toolbox for MATLAB (Release 9.10, Feb 2015) — Manual

**Archivo:** `docs/bibliografía/robot.pdf` (7.3 MB)
**Autor:** Peter Corke (peter.i.corke@gmail.com — http://www.petercorke.com)
**Release:** 9.10
**Fecha:** February 2015
**Licencia:** LGPL
**Toolbox home:** http://www.petercorke.com/robot
**Tipo:** **Manual de referencia auto-generado** (NO es el libro)

## Importante: NO confundir con el libro

Hay **dos cosas distintas**:

1. **"Robotics, Vision and Control" — Peter Corke (Springer, 2da ed 2017 / 3ra ed 2022)** — **libro pedagógico de 600 páginas con explicaciones, casi 400 figuras, 1000 ejemplos de código**. ESTE ES EL LIBRO. **NO lo tenemos en PDF.**
2. **Robotics Toolbox for MATLAB Release 9.10 Manual (lo que tenemos)** — Manual de referencia de funciones MATLAB, auto-generado del código fuente. NO tiene explicaciones pedagógicas. Solo es API reference.

El manual lo dice claro en el preface:
> "This manual is now essentially auto-generated from the comments in the MATLAB® code itself... the downside is that there are no worked examples and figures in the manual. However the book *Robotics, Vision & Control* provides a detailed discussion of how to use the Toolbox functions to solve many types of problems in robotics."

## Por qué importa para Wakuseibokan

Aunque es un manual MATLAB, los **conceptos y nombres de funciones** son una guía universal para operaciones de robótica. Útil principalmente para:

1. **Conversiones de rotación** — la telemetría manda `R[12]` (matriz 3×4 ODE). Para convertirla a Euler/RPY/quaternion, los nombres de operaciones de Corke son canónicos.
2. **Path planning** — Bug2, D*, PRM, RRT — algoritmos clásicos que podemos reimplementar en Python.
3. **Vehículos no-holonómicos** — clase `Vehicle` que modela exactamente lo que es un Otter.

**No vamos a usar MATLAB**, pero las definiciones y nombres ayudan a saber qué buscar.

## Estructura del manual

| Cap | Tema | Página |
|-----|------|--------|
| Preface | — | 4 |
| Functions by category | Índice categórico | 10 |
| 1 | Introduction (releases, install, etc.) | 13 |
| 2 | Functions and classes (lista alfabética) | 22 |

## Funciones por categoría (lo más útil)

### 3D Transforms — para procesar la `R[12]` de la telemetría ⭐

| Función | Qué hace | Aplicación a Wakuseibokan |
|---------|----------|---------------------------|
| `rotx`, `roty`, `rotz` | Matriz de rotación elemental | Conversión Euler → matriz |
| `eul2r`, `eul2tr` | Euler angles → rot matrix / transform | |
| `rpy2r`, `rpy2tr` | Roll-Pitch-Yaw → rot / transform | |
| `r2t`, `t2r` | Conversión entre rotation y transform homogéneo | |
| `tr2eul`, `tr2rpy` | Inversa: transform → Euler/RPY | **Para extraer yaw/pitch/roll de `R[12]`** |
| `tr2angvec` | Transform → axis-angle | |
| `angvec2r` | Axis-angle → rotation | |
| `Quaternion` | Clase de quaternion | Alternativa a Euler para componer rotaciones |
| `trplot` | Visualizar transform | |
| `tranimate` | Animar transformación | |

### Trajectory generation

| Función | Qué hace |
|---------|----------|
| `ctraj`, `jtraj` | Trayectorias en espacio cartesiano/articular |
| `mstraj`, `mtraj` | Multi-segment trajectory |
| `tpoly` | Polynomial trajectory |
| `lspb` | Linear segment with parabolic blend |
| `trinterp` | Interpolar entre transforms |

### Mobile Robot ⭐

| Clase/función | Qué hace |
|--------------|----------|
| `Vehicle` | Modelo de vehículo (incluye non-holonomic — el Otter) |
| `Map` | Mapa de obstáculos |
| `Navigation` | Clase base para algoritmos de navegación |
| `RandomPath` | Generador de trayectoria aleatoria |
| `RangeBearingSensor` | Sensor de rango/bearing |
| `Sensor` | Clase base de sensores |
| `makemap` | Crear mapa de prueba |

### Localization

| Función | Qué hace |
|---------|----------|
| `EKF` | Extended Kalman Filter |
| `ParticleFilter` | Particle filter |

(Para nuestro caso saltables — telemetría da pose exacta. Ver `thrun-probabilistic-robotics` skill.)

### Path planning ⭐⭐

| Algoritmo | Qué es | Relevancia para el Otter |
|-----------|--------|--------------------------|
| `Bug2` | Bug algorithm (Lumelsky) | Simple obstacle avoidance |
| `DXform` | Distance transform | Path planning sobre grid |
| `Dstar` | D* algorithm (Stentz) | Replanning dinámico |
| `PRM` | Probabilistic Roadmap | Sampling-based planner |
| `RRT` | Rapidly-exploring Random Tree | Kinodynamic planning — **muy útil para Ackermann** |

### Quaternion

`Quaternion` class — operaciones de cuaterniones (multiplicación, inversa, slerp, conversiones).

### Serial-link manipulator (NO aplica al Otter)

`SerialLink`, `Link`, `Revolute`, `Prismatic` — para brazos robóticos manipuladores. Saltable.

### Interfacing — para conectar con simuladores

| Función | Qué hace |
|---------|----------|
| `VREP`, `VREP_arm`, `VREP_camera`, `VREP_mirror`, `VREP_obj` | Bridge a V-REP (CoppeliaSim) |
| `Arbotix` | Bridge a hardware Arbotix |
| `RobotArm` | Interfaz genérica |
| `joystick`, `joy2tr` | Control con joystick |

## Aplicación al Otter — operaciones útiles

### Convertir la matriz R[12] de telemetría

`R[12]` es 3×4 de ODE = rotation 3×3 + position 1×3. En Corke terms:

```matlab
% MATLAB
R = [r1 r2 r3; r4 r5 r6; r7 r8 r9];   % rotation 3x3
t = [r10; r11; r12];                   % position
T = rt2tr(R, t);                       % build 4x4 transform
rpy = tr2rpy(T);                       % extract roll/pitch/yaw
yaw = rpy(3);                          % heading angle
```

En Python sería similar usando `scipy.spatial.transform.Rotation`:

```python
from scipy.spatial.transform import Rotation
R_mat = np.array([[r1,r2,r3],[r4,r5,r6],[r7,r8,r9]])
yaw_pitch_roll = Rotation.from_matrix(R_mat).as_euler('zyx')
```

## Limitaciones de este manual

- **No tiene teoría** — solo lista funciones. Para entender por qué funcionan, hay que ir al libro.
- **Es de 2015** — anterior a la 2da edición del libro (2017) y la 3ra (2022). Algunas funciones nuevas pueden faltar.
- **Es MATLAB** — los nombres son pista, pero hay que reimplementar en Python.

## Alternativas en Python

Si necesitamos las funciones de Corke en Python:

- **Spatial Math Toolbox** (Python, también de Corke) — port directo en Python
- **scipy.spatial.transform.Rotation** — conversiones de rotación estándar
- **roboticstoolbox-python** (Corke) — port del toolbox a Python

## Cuándo invocar esta skill

- Convertir `R[12]` de ODE a Euler/RPY/quaternion
- Necesitar nombre canónico de una operación de rotación
- Path planning clásico (Bug2, D*, PRM, RRT) como referencia
- Modelar `Vehicle` non-holonomic (el Otter)
- Cualquier consulta sobre transformaciones homogéneas 4×4

## Cuándo NO invocar esta skill

- Si la pregunta es teórica/conceptual → ir al libro de Corke (no lo tenemos), o a `siegwart-mobile-robots`
- Si es sobre cinemática del Otter → `siegwart-mobile-robots` cap 3
- Si es sobre control → `braunl-embedded-robotics` cap 4
