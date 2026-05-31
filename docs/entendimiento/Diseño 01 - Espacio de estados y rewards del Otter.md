# Diseño 01 — Espacio de estados S y función de recompensa R del agente Otter

> 📌 **Tipo de documento**: trabajo de diseño aplicado al proyecto. NO es un concepto teórico nuevo — es la **aplicación concreta** del Concepto 11 (MDP) al agente del Otter.

> ⚠️ **Realidad**: estrictamente esto es un **POMDP** desde la perspectiva de **evaluación**. No asumimos info del enemigo. Pero para no anticipar el Concepto 15, acá lo tratamos como MDP con un "belief estimado" del enemigo como input.

> 🟢 **Hallazgo importante** (actualización post-revisión del código de networking):
> El simulador expone **DOS canales UDP**:
> 1. **Telemetry individual** (puerto 4501+): solo nuestra propia telemetría (96 bytes, ModelRecord).
> 2. **Lobby** (puerto 4500): broadcast SIN FILTRO de TickRecord de **todos** los vehículos.
>
> En **training** usamos el Lobby para tener GT (ground truth) del enemigo y entrenar módulos auxiliares (State Estimator + HPE supervisado).
> En **evaluation** asumimos solo telemetría individual.
> Este es el "truco" arquitectural más importante: **la política nunca recibe GT directa, por eso funciona igual en ambos contextos**.
> Detalles completos en la nueva **Sección F**.

> 🔴 **Corrección del plan original** (actualizado tras inspección del código):
> El plan original asumía que las posiciones de las 18 warehouses podían **hardcodearse** porque eran las mismas cada partida. **NO es así**:
> - El **city center** se genera con `getRandomInteger(-500, 500)` para X y Z, con seed `time(NULL)` → **cambia entre runs**.
> - El **terreno** se genera con Cellular Automata seeded random → **desniveles distintos cada vez**.
> - **NO hay canal UDP** para info del escenario (solo recibimos nuestra propia telemetría).
>
> **Lo único determinístico** es el patrón relativo de warehouses respecto al city center (offsets fijos de 130/180/360m). Una vez que sabemos dónde está el city center, las 18 warehouses se derivan algebraicamente.
>
> **Estrategia elegida (A + B)**: el agente mantiene un **belief incremental del city center** que se actualiza con cada evento informativo (colisiones, landings del radar, exploración). Dedicamos los primeros ~500 ticks de cada run a exploración prioritaria. Detalles en la nueva Sección B.7.

---

## Sección A — Inventario real del simulador

Esto está sacado **del código real** (no inventado). Si tenés dudas, las fuentes son `src/networking/telemetry.h` y `src/units/Vehicle.h`.

### A.1 Lo que llega por UDP en cada tick (ModelRecord, 96 bytes)

**Importante**: cada agente abre un puerto (4501 o 4502) y recibe **SOLO la telemetría de SU vehículo**. La del enemigo no llega.

| Campo | Tipo | Bytes | Rango | Qué es |
|-------|------|-------|-------|--------|
| `recordtimer` | uint32 | 4 | — | Timer del simulador en este tick |
| `lastUpdateTimer` | uint32 | 4 | — | Último update del vehículo |
| `number` | int32 | 4 | — | ID del vehículo |
| `health` | float | 4 | [0, 1000] | Salud propia |
| `power` | int32 | 4 | [0, 1000] | "Munición/energía" propia |
| `azimuth` | float | 4 | [-π, π] | Orientación pre-computada (yaw) |
| `landingPos[3]` | float × 3 | 12 | world coords | Radar: último impacto de proyectil ≤500m |
| `pos[3]` | float × 3 | 12 | world coords | Posición XYZ propia |
| `R[12]` | float × 12 | 48 | matriz 3×4 | Rotación 3×3 + padding |
| **TOTAL** | | **96** | | |

### A.2 Lo que mandamos al simulador (ControlStructure2, 68 bytes)

| Campo | Tipo | Qué hace |
|-------|------|----------|
| `controllingid` | int32 | ID del vehículo que controlamos |
| `thrust` | float | [-1, 1] adelante/atrás |
| `roll, pitch, yaw` | float × 3 | comandos de orientación (steering body) |
| `precesion, bank` | float × 2 | precisión / giro |
| `command` | int32 | 11 = FIRE; otros comandos |
| `x, y, z` | float × 3 | destino opcional (modo waypoint) |
| `weapon, target_type` | int32 × 2 | tipo de arma |
| `sourcetimer` | uint32 | timestamp del cliente (rechaza > 30000 ticks viejos) |

### A.3 El radar — qué nos dice y qué no nos dice

- Se actualiza cuando un proyectil impacta el terreno **≤500m de nuestro Otter**.
- Reporta la **ubicación del impacto** (no la del shooter).
- Conclusión: nos dice "alguien disparó por ahí y la bala cayó acá". Para inferir desde dónde disparó, hay que hacer **back-tracing** del cono de tiro.
- **No diferencia entre balas propias y enemigas** — el radar reporta cualquier impacto cercano. Si vos mismo disparás y tu bala cae cerca tuyo, lo vas a ver también.

### A.4 Eventos terminales del episodio

| Condición | Qué pasa |
|-----------|----------|
| `health ≤ 0` | El Otter sigue existiendo pero reporta health negativa. El simulador marca el inicio del fin: `endtimer = timertick + 300`. |
| `timertick > endtimer` (post-muerte) | El episodio termina (~15 segundos después de la muerte). |
| `timertick > 5000` (sin muerte) | Timeout. `haspassed = false`. |
| Reset | Si `episodesmode=true`, reinicia automáticamente. |

### A.5 Daño por desgaste — cuidado con esto

**Importante** y poco intuitivo: en `testcase_131.cpp:L455` cada vehículo recibe `damage(1)` por tick mientras está navegando. Es desgaste continuo. Esto significa:

- Si no pasa nada, **igual perdés 1 health/tick = 50 health/segundo (con tick 20ms)**.
- A los **20 segundos**, sin combate, ya perdiste 1000 health → **muerte por inanición**.
- En la práctica, el episodio dura unos **~5000 ticks máx (250 s)**. Sin daño activo, llegarías a ese tiempo con health = 1000 - 5000 = -4000. **Te morís solo**.

**Implicación para el reward**: el step penalty NO es necesario incentivo de "terminar rápido" — la mecánica misma del juego ya lo penaliza. Pero hay que **modelar este desgaste** o el agente no entiende por qué pierde salud.

### A.6 City of Warehouses (escenario fijo)

- 18 warehouses con tamaño y posiciones **deterministas dentro del episodio** (la ubicación del centro de la ciudad sí es aleatoria entre episodios, ±500m del origen).
- 2 filas principales × 5 warehouses + 4 bloques cruzados.
- Tamaño aprox: 40×50×70 unidades cada uno.
- Mapa total: [-1400, 1400]² (XZ).
- Otters spawnan **fuera de un círculo de radio 680** alrededor del centro de la ciudad.

---

## Sección B — Diseño del espacio de estados S

El estado que le pasamos a la red neural es un **vector concatenado** de varias categorías de features. Cada tick computamos este vector desde la telemetría más todo lo que podemos derivar.

### B.1 Features observables directamente (12 floats)

Lo más fácil — viene tal cual del UDP, solo normalizamos.

| Feature | Dimensión | Cómo se obtiene | Normalización |
|---------|-----------|-----------------|---------------|
| `self_pos` | 3 | `ModelRecord.pos[3]` | `/1400` |
| `self_quaternion` | 4 | `from_matrix(R[12]).as_quat()`, canonicalizado | norma 1 ya |
| `self_health` | 1 | `ModelRecord.health` | `/1000` |
| `self_power` | 1 | `ModelRecord.power` | `/1000` |
| `self_azimuth` | 1 | `ModelRecord.azimuth` | `/π` |
| `tick_normalized` | 1 | `recordtimer / 5000` | "fracción de episodio transcurrida" |
| `health_delta_last` | 1 | `health_t - health_{t-1}` | / 100 (escala típica) |

### B.2 Features de eventos recientes (8 floats)

Lo que pasó hace poco. Cambian rápido — son la "memoria de corto plazo" del agente.

| Feature | Dimensión | Significado |
|---------|-----------|-------------|
| `radar_active` | 1 | bool — ¿hubo evento de radar en los últimos N ticks? |
| `radar_age_ticks` | 1 | cuántos ticks pasaron desde el último evento (normalizado / 100) |
| `radar_pos_relative_body` | 3 | posición del impacto **expresada en body frame** (Concepto 5) |
| `radar_freq` | 1 | eventos por segundo (ventana móvil de 100 ticks) |
| `ticks_since_fire` | 1 | cuántos ticks pasaron desde nuestro último `fire` (normalizado) |
| `i_was_hit_recently` | 1 | bool — Δhealth < 0 en últimos 5 ticks (excluyendo desgaste) |

**Detalle**: `radar_pos_relative_body` es CLAVE. Te dice "el impacto del enemigo cayó adelante mío a la derecha, a 80 metros". Es interpretable en body frame.

### B.3 Features espaciales del mapa (~22 floats, DEPENDIENTES del belief del mapa)

⚠️ **Estos features NO son gratis** como pensábamos: dependen del **belief estimado del city center** (Sección B.7), no del city center real (que no conocemos).

Mientras el belief tenga baja incertidumbre, estos features son útiles. Mientras tenga alta incertidumbre (al inicio del run), son ruido y la red debería ignorarlos.

| Feature | Dimensión | Significado |
|---------|-----------|-------------|
| `dist_to_each_warehouse_body` | 18 | distancia a cada warehouse **según el belief**, en body frame |
| `dist_to_nearest_edge` | 1 | qué tan cerca estoy del borde del mapa (peligro de salida) — este SÍ es gratis, los bordes son fijos en ±1400 |
| `dist_to_city_center_belief` | 1 | distancia al **belief** del centro de la ciudad |
| `am_inside_city_belief` | 1 | bool — el belief indica que estoy en zona urbana |
| `los_to_each_warehouse_belief` | 18 (bool) | LOS a cada warehouse **según el belief** |
| `map_belief_confidence` | 1 | confianza del belief del mapa (0 = no sé nada, 1 = sé exacto) |

Total: 18 + 1 + 1 + 1 + 18 + 1 = **40 floats**.

**La feature `map_belief_confidence` es CRÍTICA**: le dice a la red "cuánto confiar en las otras features del mapa". Con confianza baja, la red aprende a ignorar las distancias/LOS.

(Si esto es demasiado, podemos reducir a las **5 warehouses más cercanas según el belief** en vez de las 18.)

### B.4 Features de cobertura / defilade (5 floats)

¿Estoy tapado o expuesto?

| Feature | Dimensión | Significado |
|---------|-----------|-------------|
| `defilade_score` | 1 | qué fracción de mi 360° está bloqueada por warehouses |
| `behind_cover_north/south/east/west` | 4 | en qué cuadrantes tengo cover |

**Cómo se calcula**: traza rayos de 360° desde tu posición y mira cuántos chocan con un warehouse antes de N metros. La fracción que chocan = defilade.

### B.5 Belief del enemigo (8 floats) — clave del POMDP

**Esto NO viene del simulador**. Lo estima un módulo aparte (state estimator, LSTM) que vamos a ver en el Concepto 15.

| Feature | Dimensión | Significado |
|---------|-----------|-------------|
| `enemy_pos_mean_body` | 3 | media estimada de la posición del enemigo, en body frame |
| `enemy_pos_std` | 2 | desviación estándar (incertidumbre) en X y Z |
| `enemy_vel_mean_body` | 3 | velocidad estimada del enemigo |
| `enemy_pos_age` | 1 | hace cuánto fue la última observación útil del enemigo |
| `enemy_in_los` | 1 | bool — el belief actual indica que tengo LOS con él |

### B.7 Belief del mapa (5 floats) — el nuevo módulo

Este módulo es **propio del agente**, no viene del simulador. Mantiene una estimación del city center que se actualiza con cada evento informativo.

| Feature | Dimensión | Significado |
|---------|-----------|-------------|
| `city_center_mean` | 2 | (x, z) estimado del centro de la ciudad |
| `city_center_std` | 2 | desviación estándar (incertidumbre) en X y Z |
| `n_observations` | 1 | cuántos eventos informativos hemos integrado (normalizado / 50) |

**Cómo se actualiza el belief**:

1. **Inicialización**: prior uniforme `(0, 0)` con `std = (500, 500)` (toda la zona donde puede caer el city center).
2. **Eventos informativos** (cada uno mueve el belief):
   - **Colisión contra obstáculo**: si la velocidad cae abruptamente sin que estemos cerca de un borde, asumimos colisión con warehouse → posición del obstáculo es muy probablemente parte de la grilla de warehouses. Actualizar belief.
   - **Landing del radar en zona urbana**: si recibimos un radar event en una zona aún no excluida, hint de zona urbana.
   - **Movimiento sin colisión en una zona**: descarta que esa zona contenga warehouses, reduce incertidumbre por exclusión.
3. **Implementación inicial simple**: filtro de partículas con N=50 partículas, cada una hipotética del city center. Cada evento reduce la varianza de las partículas.
4. **Más avanzado**: filtro bayesiano + máxima verosimilitud sobre los offsets fijos de las 18 warehouses.

**Trade-off**: este módulo agrega complejidad pero hace al agente robusto a la aleatoriedad del mapa entre runs.

### B.8 Total revisado

Sumando: **12 + 8 + 40 + 5 + 8 + 5 = 78 floats** (aprox).

Versión mínima:
- Reducir warehouses a las 5 más cercanas: -36 floats.
- Quitar defilade granular: -4 floats.
- Versión mínima con belief del mapa: ~38 floats.

---

## Sección C — Función de recompensa R

Acá viene el arte. Voy a separar por **categoría de evento** y dar valores tentativos. **Todos son ajustables** — esperá iterar mucho en la Semana 3-4 del proyecto.

### C.1 Principio de diseño

1. **Reward sparso = malo**. Si solo das +1000 al ganar y -500 al perder, la red no tiene señal en el 99% de los ticks → no aprende.
2. **Reward shaping** = darle pistas en los ticks intermedios.
3. **Cuidado con shaping mal**: si rewardás "estar cerca del enemigo", el agente puede aprender a perseguirlo sin disparar. Si rewardás "disparar", aprende a tirar al aire.

La estrategia es: **muchos rewards pequeños alineados con la victoria**, más los grandes terminales.

### C.2 Categoría 1 — Health (lo más fuerte)

```python
r_health = 0

# Recibir daño del enemigo (señal fuerte negativa)
# El daño "natural" de desgaste es 1/tick. Cualquier daño extra = enemigo.
extra_damage = max(0, (health_prev - health_now) - 1)
r_health -= 5.0 * extra_damage  # cada punto de daño extra = -5 reward

# Estar vivo es bueno (counter al step penalty)
if health_now > 0:
    r_health += 0.05
```

### C.3 Categoría 2 — Power (munición)

```python
r_power = 0

# Disparar tiene costo pequeño (penaliza spray-and-pray)
if action.fire:
    r_power -= 0.1

# Quedarse sin munición es desastroso
if power_now <= 0:
    r_power -= 1.0  # penalty cada tick sin munición
```

### C.4 Categoría 3 — Disparos y radar

Acá es donde más cuidado hay que tener.

```python
r_combat = 0

# Recibimos radar event → enemigo nos disparó cerca. Estamos expuestos.
if radar_event_this_tick:
    distance_to_impact = norm(radar_pos - self_pos)
    proximity_factor = max(0, 1 - distance_to_impact / 500)
    r_combat -= 0.5 * proximity_factor  # más cerca el impacto, mayor penalty

# Disparamos: delatás tu posición. Pequeña penalty.
if action.fire:
    r_combat -= 0.2
```

**Lo que SÍ podemos hacer en training (vía Lobby)**: rewardear "acertar" directamente leyendo el Δenemy_health del Lobby.

```python
# Solo durante TRAINING (el Lobby está disponible)
if training_mode:
    enemy_damage = max(0, enemy_health_prev - enemy_health_now)
    r_combat += 10 * enemy_damage  # reward directo por daño causado
```

**En eval** (sin Lobby) tenemos que aproximarlo con el HPE entrenado offline:

```python
# Solo en EVAL (no hay Lobby)
if not training_mode and action.fire:
    p_hit = hpe_network(state, aim_target)  # red entrenada con GT del Lobby en train
    r_combat += 10 * p_hit  # estimación, no GT
```

El HPE se entrena así: en cada dataset de entrenamiento donde tenemos el Lobby, marcamos los ticks donde hubo `fire=True` y vemos en los siguientes ~50 ticks si `enemy_health` bajó. Eso da el label binario `hit ∈ {0, 1}`. Después la red aprende a predecirlo.

**Importante**: la diferencia entre el reward de training (con GT) y el reward de eval (con HPE) crea un pequeño **train/eval gap**. Lo aceptamos como costo necesario porque el HPE es nuestro mejor proxy en eval.

### C.5 Categoría 4 — Posición y cobertura

```python
r_position = 0

# Salir del mapa = muerte
if abs(self_pos.x) > 1400 or abs(self_pos.z) > 1400:
    r_position -= 10  # grande, pero no terminal
    # (el simulador puede matar al Otter por salir, eso lo veríamos en health)

# Pequeño bonus por estar en cobertura
if defilade_score > 0.5:
    r_position += 0.05

# Pequeño bonus por moverse (incentiva no quedarse quieto)
if velocity_magnitude > 1.0:
    r_position += 0.02
```

### C.6 Categoría 5 — Eventos terminales (los grandes)

```python
r_terminal = 0

# Muerte propia: muy malo
if health_now <= 0 and health_prev > 0:
    r_terminal = -500

# Victoria: el episodio terminó y NO morimos
# Sabemos que ganamos si:
#   1. El episodio terminó (recibimos señal del runner)
#   2. self_health > 0 al final
# Esto solo se aplica al ÚLTIMO tick del episodio.
if episode_ended_now and health_now > 0:
    r_terminal = +1000

# Timeout sin victoria (5000 ticks, ambos vivos)
if timeout_now and health_now > 0:
    r_terminal = -50  # mejor que perder, peor que ganar
```

### C.7 Categoría 6 — Step penalty

```python
# Pequeña penalty por tick para incentivar resolver rápido
r_step = -0.01
```

(Recordá que el desgaste natural ya penaliza demorarse — esto es por las dudas.)

### C.8 Categoría 7 — Active perception (avanzado)

```python
r_info = 0

# Reducir incertidumbre del belief enemigo = bueno (active perception)
entropy_change = belief_entropy_prev - belief_entropy_now
r_info += 0.1 * entropy_change  # positivo si redujimos incertidumbre
```

Esto solo aplica si tenés el state estimator funcionando (Concepto 15). Útil para Semana 3-4.

### C.9 Fórmula completa (versión 1)

```python
def compute_reward(s_prev, s_now, action, episode_info):
    r = 0
    r += r_health(s_prev, s_now)        # daño, recuperación
    r += r_power(s_prev, action)        # munición
    r += r_combat(s_now, action)        # disparos, radar
    r += r_position(s_now)              # cobertura, bordes
    r += r_terminal(s_prev, s_now, episode_info)  # muerte, victoria
    r += r_step()                       # penalty por tick
    # r += r_info(s_prev, s_now)        # opcional (Concepto 15+)
    return r
```

### C.10 Tabla resumen de magnitudes

| Evento | Reward típico | Frecuencia esperada |
|--------|---------------|---------------------|
| Tick "normal" (sin nada raro) | -0.01 + 0.05 - 0.01 ≈ +0.03 | cada tick |
| Recibimos 5 de daño extra | -25 | esporádico |
| Disparamos | -0.3 | varias veces por minuto |
| Radar muy cercano | -0.5 | esporádico |
| Bonus por cover | +0.05 | sostenido si vamos cubiertos |
| **MUERTE** | **-500** | una vez al final |
| **VICTORIA** | **+1000** | una vez al final |

**Observación**: las magnitudes de los terminales (±500-1000) son mucho mayores que las de los rewards intermedios (±0.01-25). Esto es **intencional** — los terminales deben dominar el retorno para que el agente aprenda a priorizar ganar.

---

## Sección D — Casos extremos y consideraciones

### D.1 ¿Cómo sabemos que ganamos sin telemetría enemiga?

El simulador, cuando termina el episodio, te avisa por el flag `haspassed` (o `isdone`). Pero esto **no viene en cada ModelRecord** — necesitás otro canal de comunicación, o lo asumís a partir de que **el episodio termina y vos seguís vivo**.

**Decisión práctica**: si el episodio termina antes del timeout y `self_health > 0`, asumís victoria. Si termina con `self_health ≤ 0`, perdiste. Si llega al timeout y los dos seguimos vivos, empate.

### D.2 ¿Cómo distinguís daño del enemigo del desgaste?

Difícil pero hacible:

- Desgaste = exactamente -1/tick.
- Daño del enemigo = -N donde N depende del arma. Suele ser > 5 por impacto.

```python
total_damage = health_prev - health_now
attrition_damage = 1  # constant
enemy_damage = max(0, total_damage - attrition_damage)
```

### D.3 El reward de "acertar al enemigo" — el agujero negro del diseño

Sin telemetría enemiga, no sabemos si nuestro disparo dio en el blanco. **Esto es estructural** del POMDP. Opciones:

1. **Proxy temporal**: si después de tu fire el radar enemigo (la frecuencia con la que te disparan) baja, hint de daño.
2. **HPE supervisado**: entrenar en data offline donde sí sabés. Esto da P(hit | s, a) que después rewardea como `+10 * P(hit)`.
3. **Self-play con simulador modificado**: en training, exponer ambas telemetrías a un módulo de scoring que sí ve todo. Pero la política solo ve lo parcial.

**Recomendación inicial**: empezar SIN reward de acierto (solo penalizar disparar y rewardear el outcome final). Después agregar proxy o HPE en Semana 3-4.

### D.4 Reward shaping iterativo

**NO** intentes calibrar todos los coeficientes el primer día. La estrategia es:

1. Semana 1: solo terminales (+1000 victoria, -500 muerte). Resultado: agente no aprende nada interesante (reward muy sparso).
2. Semana 2: agregar health damage tracking y step penalty. Resultado: agente aprende a no morirse, pero no a ganar.
3. Semana 3: agregar cobertura y disparos. Resultado: agente empieza a tener comportamiento táctico.
4. Semana 4: refinement de coeficientes según resultados.

---

## Sección E — Pendientes RESUELTOS (decisiones tomadas)

| Pregunta | Respuesta | Implicancia |
|----------|-----------|-------------|
| ¿El simulador puede mandarnos un flag de "ganaste/perdiste/timeout"? | **Sí, vía Lobby** (puerto 4500). El TickRecord incluye `status` + `health` del que se infiere. **Estrategia confirmada**: terminal antes del timeout + self_health>0 = victoria; self_health≤0 = derrota; timeout con ambos vivos = empate. | Reward terminal preciso |
| ¿Hay un puerto para recibir info de eventos globales (no solo nuestra telemetría)? | **SÍ — el Lobby en puerto 4500 broadcastea TickRecord de TODOS los vehículos a TODOS los clientes, SIN filtro de faction.** Ver Sección F sobre la estrategia híbrida training/eval. | Decisión arquitectural mayor: training puede usar GT del enemigo |
| ¿El desgaste es siempre 1/tick o depende de la velocidad/movimiento? | **Siempre 1/tick exactamente** cuando `status ∈ {SAILING, OFFSHORING}`. En otros estados (`ROLLING`, `DOCKED`, etc.) NO se aplica. Ubicación: `testcase_131.cpp:L453-456`. | Podemos restar 1 al Δhealth para aislar el daño "real" del enemigo cuando estamos navegando. Cuidado con cambios de status. |
| ¿Hay alguna forma de saber cuándo el ENEMIGO dispara (no solo cuando su bala impacta cerca)? | **NO** (decisión del usuario). Solo sabemos cuando el impacto cae cerca nuestro (radar event). | El timing del shoot-and-scoot lo inferimos por radar events, no por evento directo de "enemigo disparó". |
| Si los dos agentes corren en la misma máquina, ¿comparten recursos? | **No, van en máquinas/procesos distintos** (decisión del usuario). | Tenemos el budget de inferencia completo. Podemos usar `medium` o `large` del plan. |
| ¿`heat` existe en el código? | **Probablemente no** (decisión del usuario), y **probablemente no vamos a saber si acertamos** disparos sin extra trabajo. | No usar `heat` como feature. Para "acertamos?", usar la estrategia híbrida (Sección F): GT en training, inferir en eval. |
| ¿Hay forma de fijar el seed del simulador para evaluación? | **No** (decisión del usuario). | Sí o sí necesitamos el módulo de belief del mapa (Sección B.7). |
| ¿Hay forma de leer las posiciones reales de las warehouses en runtime? | **No** (decisión del usuario). | Idem anterior. |

---

## Sección F — La estrategia híbrida training-vs-eval (NUEVA, crítica)

Esta sección sale del hallazgo de que el **Lobby broadcastea info de todos los vehículos sin filtro**. Es la diferencia entre tener "ground truth" del enemigo en training pero no en eval.

### F.1 Los dos canales disponibles

| Canal | Puerto | Qué nos da | Uso típico |
|-------|--------|------------|------------|
| **Telemetría individual** (`telemetryme`) | 4501, 4502, ... | Solo nuestro ModelRecord (96 bytes) | **Lo que asumimos en evaluación** |
| **Lobby** (`notify`) | 4500 | TickRecord de **todos** los vehículos (sin filtro) | **Lo que usamos en training** |

### F.2 Por qué usamos los dos en distintas fases

**En training (controlamos el ambiente)**:
- Conectamos al **Lobby** para tener GT (ground truth) del enemigo.
- Usamos esa GT para entrenar **módulos auxiliares** (no la política directa):
  - **State Estimator (LSTM)**: aprende a predecir la pose enemiga usando solo lo que el agente vería en eval. Loss supervisado contra GT del Lobby.
  - **HPE (Hit Probability Estimator)**: aprende `P(hit | s, a)`. Loss supervisado: para cada `fire` registrado, vemos en los siguientes ~50 ticks si `enemy_health` bajó en el Lobby. Eso da la label.
  - **Reward shaping**: agregamos al reward un componente por daño efectivamente causado (`+10 * Δenemy_health` calculado del Lobby).

**En evaluation (no controlamos el ambiente)**:
- **Asumimos** que solo tenemos telemetría individual.
- El state estimator (ya entrenado) infiere la pose enemiga.
- El HPE (ya entrenado) estima `P(hit)`.
- La política consume lo mismo que en training (la salida del estimator + HPE) → comportamiento idéntico.

### F.3 El truco clave de la arquitectura

```
┌──────────────────────────────────────────────────────────┐
│  Política π (red neural principal — la que vamos a usar  │
│  en evaluación)                                          │
│                                                          │
│  Inputs:                                                 │
│    - Telemetría propia (siempre disponible)              │
│    - belief enemigo (output del State Estimator)         │
│    - P(hit) (output del HPE)                             │
│                                                          │
│  NUNCA recibe directamente la GT del enemigo.            │
│  Por eso funciona igual en training y en eval.           │
└──────────────────────────────────────────────────────────┘
                          ▲
                          │
          ┌───────────────┴────────────────┐
          │                                │
┌──────────────────────┐         ┌────────────────────┐
│  State Estimator     │         │  HPE               │
│  (LSTM)              │         │  (MLP)             │
│  Entrenado supervis. │         │  Entrenado superv. │
│  con GT del Lobby    │         │  con GT del Lobby  │
│  → inference solo    │         │  → inference solo  │
│    con telemetría    │         │    con telemetría  │
│    propia            │         │    propia          │
└──────────────────────┘         └────────────────────┘
```

### F.4 Implicancias para el plan de implementación

| Fase | Canal UDP usado | Para qué |
|------|-----------------|----------|
| Semana 1 — recolección de datos | **Lobby** | Recopilar datasets con GT del enemigo para entrenamiento supervisado |
| Semana 2 — imitation learning + entrenamiento estimadores | **Lobby** (offline desde dataset) | Entrenar State Estimator + HPE supervisado |
| Semana 3 — SAC fine-tuning | **Lobby** (para loss, no para input de política) | Reward shaping con info de daño causado, sin contaminar la política |
| Semana 4 — eval / preparación entrega | **Telemetry individual** (puerto 4501) | Simular las condiciones reales de evaluación |

### F.5 Riesgo a mitigar

Si por error la política llega a "ver" la GT del enemigo durante training, va a aprender a depender de ella y **en eval va a fallar catastróficamente**. Por eso es CRUCIAL mantener la separación clara entre:

- **Lo que la política recibe**: solo lo que está disponible en eval.
- **Lo que el sistema de training calcula como loss**: puede usar GT.

Esta es la **disciplina más importante** del entrenamiento. Cualquier feature derivada del Lobby debe pasar por State Estimator o HPE, no ir directo a la política.

---

## Resumen ejecutivo

| | Tamaño / valor |
|---|----------------|
| **Espacio de estados S** | ~78 floats (versión completa, incluye belief del mapa) o ~38 floats (mínima) |
| **Espacio de acciones A** | 5 dims: thrust, steering, turret_b, turret_d, fire (4 continuos + 1 binario) |
| **Reward por tick típico** | ~0.03 (suma de small bonuses) |
| **Reward de muerte** | -500 |
| **Reward de victoria** | +1000 |
| **Duración episodio** | ~5000 ticks (250 s) |
| **Daño por desgaste** | 1/tick (importante distinguir del daño enemigo) |
| **Info del enemigo en telemetría** | **NINGUNA directa** → POMDP, requiere state estimator |
| **Info del mapa en telemetría** | **NINGUNA directa** → mapa aleatorio cada run, requiere belief estimator |

Este documento es **vivo**: lo vamos a refinar en cada concepto siguiente. Especialmente:
- **Concepto 15 (POMDP)** va a definir cómo computamos el `belief enemigo` (Sección B.5).
- **Concepto 14 (SAC)** va a definir cómo la red consume estos features.
- **Concepto 16 (Pipeline)** va a juntar todo en código.
