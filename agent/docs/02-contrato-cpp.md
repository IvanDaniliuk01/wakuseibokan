# Decisión 02: contrato Python ↔ C++ verificado

**Fecha**: 2026-05-31
**Estado**: Verificado contra el código fuente del simulador. Dos signos
pendientes de calibración empírica (ver al final).

## Contexto

Antes de invertir tiempo en training, necesitamos certeza de que las
convenciones que asumen los encoders Python (`agent/encoders.py`,
`agent/policy_utils.py`) coinciden exactamente con lo que el sim hace al
vehículo. Si una asunción está mal, la red aprende un mapping incorrecto y
todo el dataset queda comprometido.

El Otter NO es un Walrus — es su propia clase que hereda de `AdvancedWalrus`.
Tiene control específico en `src/units/Otter.cpp`. Eso significa que el
mapeo de campos del `ControlStructure2` para el Otter es **distinto** del
que tienen otros vehículos. La verdad ground truth está en
`src/units/Otter.cpp:134-159` (`Otter::doControl`) y
`src/units/AdvancedWalrus.cpp:705-749` (`fire`).

## Tabla de contrato — verificada

### Comandos del agente (ControlStructure2 → Otter)

Activo solo cuando `status == SailingStatus::ROLLING` (que es el estado
normal del Otter en testcase 131 desde el tick 1).

| Campo Python | Campo C++ | Unidad | Cómo se aplica | Fuente |
|---|---|---|---|---|
| `thrust ∈ [-10, 10]` | `controller.registers.thrust` | escalar | `setThrottle()` a las 4 ruedas | Otter.cpp:143-146 |
| `roll ∈ [-1, 1]` | `controller.registers.roll` | escalar | `roll/10.0` → `setAzimuth()` de las 2 ruedas delanteras (steering Ackermann) | Otter.cpp:151-152 |
| `pitch ∈ [-0.4, 0.4]` | `controller.registers.pitch` | grados | asignado a `elevation` de la torreta | Otter.cpp:139 |
| `precesion ∈ [-180, 180]` | `controller.registers.precesion` | grados | asignado a `azimuth` de la torreta, **interpretado como bearing RELATIVO al heading del vehículo** | Otter.cpp:138 + AdvancedWalrus.cpp:717-719 (`dBodyVectorToWorld`) |
| `command = 11` | `mesg.command` | int | dispara con `fire(0, world, space)` si `power > 0` | testcase_131.cpp:428-438 |
| `sourcetimer = mr.recordtimer` | `mesg.sourcetimer` | uint32 | filtra si `timer - sourcetimer > 30000` | testcase_131.cpp:405 |

Notas:
- **El sim NO clampa el thrust del Otter** (a diferencia del Walrus, que sí
  clampa a ±200). Pero usamos `THRUST_MAX=10` porque seek_policy fue
  calibrado a esta velocidad y los presets del cheater (`dist_engage`,
  `dist_fire`) están armados asumiendo esto.
- **`roll/10` es Ackermann**: el rango efectivo de giro de ruedas es ±0.1 rad
  (5.7°). El Otter no puede girar en el lugar como tanque — tiene que andar
  en círculos. Esto explica por qué seek_policy a veces queda "atascada" y
  necesita el modo escape (`stuck_threshold_m`).
- **`precesion` es relativo al vehículo**: cuando seek_policy o cheater
  calculan `bearing = relative_bearing_deg(my, my_az, other)` y lo pasan
  como `turret_bearing`, está produciendo exactamente el formato que el sim
  espera. Verificado por `dBodyVectorToWorld` en AdvancedWalrus.cpp:719.

### Telemetría (Otter → ModelRecord)

| Campo Python | Unidad | Cómo se llena | Fuente |
|---|---|---|---|
| `pos = [x, y, z]` | metros, y=altura | spawn con `Vec3f(x, terrainHeight + 5, z)` | testcase_131.cpp:124 |
| `azimuth` | **grados** (0=norte, 90=este, 180=sur, 270=oeste) | `getAzimuth(forward, 30.0f)` con offset +270/-90 | telemetry.cpp:153, yamathutil.cpp:88-97 |
| `health ∈ [0, 1000]` | escalar | `clipped(_b->getHealth(), 1, 1000)`. Pierde 1/tick en SAILING/OFFSHORING | testcase_131.cpp:450, 453-456 |
| `power ∈ [0, 1000]` | escalar | munición; baja por cada disparo | testcase_131.cpp:436 |

### Geometría — `policy_utils.azimuth_deg` vs `getAzimuth` del sim

**Es literalmente la misma fórmula.** En yamathutil.cpp:88-97:

```cpp
float val = atan2(aim[2], aim[0]) * 180.0/PI;
if (val >= 90) val -= 90;
else val += 270;
```

Y nuestra Python en policy_utils.py:9-19 hace exactamente eso. ✓

### Disparo (fire) — convención de apuntado

En AdvancedWalrus.cpp:705-749:

```cpp
forward = toVectorInFixedSystem(0, 0, 1, azimuth, elevation);
dBodyVectorToWorld(me, forward[0], forward[1], forward[2], result);
// result es el vector mundial; el proyectil sale en esa dirección a velocidad firepower=600
```

Esto confirma que **el disparo sale donde apunta la torreta**, no donde mira
el vehículo. Toda la lógica de bearing/pitch del cheater es válida.

## Puntos que SIGUEN abiertos (pendiente calibración empírica)

### A. Signo de `elevation` (pitch)

`setAim(toVectorInFixedSystem(0, 0, 1, azimuth, -elevation))` — **nota el
signo negativo de elevation**. Esto significa que el sim interpreta el
elevation con signo opuesto al "intuitivo".

Nuestra función `pitch_to_target_rad(my_y, other_y, dist)` asume que
`pitch > 0` apunta hacia arriba. Combinado con el signo negativo interno
del sim, hay que verificar si la convención total queda correcta o
invertida.

**Test empírico para validarlo**: cuando el cheater HARD/IMPOSSIBLE
enfrente a un enemigo en una colina (alturas diferentes en el dataset_v2),
medir si el win-rate es mejor o peor con el signo actual vs invertido.

### B. Signo de `roll` (steering)

`setAzimuth(roll/10.0)` — el sim no documenta si positivo gira a izquierda
o derecha. Como seek_policy ya funciona, **la convención que asume es
consistente con la del sim** (signo válido). Pero no sabemos cuál es.

**No requiere acción** mientras la red use el mismo mapping que seek_policy.
Solo importa si manualmente comparamos behavior con otro origen.

## Conclusión

Todas las convenciones críticas (azimuth en grados, fórmula del bearing,
coordenadas (x, y, z), thrust positivo = adelante, precesion relativa al
vehículo) están correctas. El espacio de acción 6-D del agente es válido
en todas sus dimensiones — ningún campo es ruido inútil.

Dos signos pendientes (pitch y roll) no bloquean training, pero conviene
calibrarlos empíricamente antes de declarar el sistema "production-ready".
