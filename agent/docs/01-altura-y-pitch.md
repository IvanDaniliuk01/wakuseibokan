# Decisión 01: tratamiento del eje Y (altura) y pitch de torreta

**Fecha**: 2026-05-31
**Estado**: Aceptada y aplicada al cheater. Pendiente revisar para la red RL.

## Contexto

El simulador Wakuseibokan tiene terreno con relieve. El plano horizontal usa
las coordenadas `(x, z)` y `y` es la altura. Las funciones geométricas en
`agent/policy_utils.py` (`azimuth_deg`, `relative_bearing_deg`) usan solo
`(x, z)` y descartan `y`. El estado que ve la red neuronal (`encode_state` en
`agent/encoders.py`) también descarta `y`.

La pregunta: ¿esta simplificación es razonable, o estamos perdiendo
información que importa para el combate?

## Evidencia empírica

Análisis de `data/dataset_v2.h5` (28 episodios, 5609 ticks):

| Métrica | Valor |
|---|---|
| Variación de altura por episodio (mean / max) | 2-4m / 46m |
| Diferencia de altura entre tanques `\|dy\|` (mediana) | 15.5m |
| Diferencia de altura entre tanques `\|dy\|` (p90 / max) | 34m / 39m |
| Error relativo `dist3D` vs `dist2D` (max) | **0.09 %** |
| Pitch para apuntar al enemigo (mean / max) | 1.14° / **2.40°** |

## Conclusiones

### 1. Distancia: 2D alcanza

Las distancias horizontales típicas son del orden de 1000 m y las verticales
del orden de 30 m. El error relativo de usar `sqrt(dx² + dz²)` en vez de la
distancia 3D real es **< 0.1 %**. Despreciable para rango de fuego (200-500 m).

**Acción**: mantener `dist = sqrt(dx² + dz²)` en `encode_state` y en las
políticas.

### 2. Bearing horizontal: Y no afecta

El bearing es un ángulo horizontal por definición. Si el enemigo está 30 m
más arriba, sigue estando "a las 3 en punto" cuando vos lo enfrentás. No
importa Y para decidir si girás a izquierda o derecha.

**Acción**: mantener `relative_bearing_deg` ignorando `y`.

### 3. Pitch de torreta: SÍ importa para HARD/IMPOSSIBLE

El pitch máximo observado es 2.4°. Comparado con los conos de fuego del
cheater:

| Nivel | `fire_cone_deg` | ¿Pitch máximo 2.4° lo excede? |
|---|---|---|
| EASY | 8° | No, irrelevante |
| MEDIUM | 5° | No, irrelevante |
| HARD | 3° | Marginal — bordea el límite |
| IMPOSSIBLE | 2° | **Sí — el cheater falla por pitch erróneo** |

Hoy `seek_policy.py` y `cheater_policy.py` ponen `turret_decl = rng.uniform(-0.4, 0.4)`,
o sea pitch random. Para los niveles fáciles eso da igual (el cono es amplio).
Para HARD/IMPOSSIBLE es la razón por la cual el cheater "no es tan imposible"
como su nombre sugiere.

**Acción tomada**: agregar `pitch_to_target_rad` a `policy_utils.py` y
modificar `cheater_policy.py` para que **HARD e IMPOSSIBLE** usen el pitch
calculado correcto (`atan(dy / dist_horizontal)`). EASY/MEDIUM siguen con
pitch random para que mantengan su "torpeza humana".

### 4. Encoder de la red: por ahora seguir sin Y

Con pitch máximo de 2.4° en este dataset, agregar `y` al estado le daría a
la red una señal débil. El costo (3 features extra, red ligeramente mayor,
re-entrenamiento) supera el beneficio esperado.

**Acción**: `encode_state` queda igual (12 features, sin `y`). Cláusula de
revisión: si en eval real vemos que el agente falla cuando el enemigo está
en altura distinta, agregamos `pos_me[1]/scale`, `pos_oth[1]/scale`,
`dy/scale` (pasa a 15 features).

## Riesgos asumidos

- Si el sim genera mapas mucho más accidentados en algún testcase futuro
  (montañas, capital island con altura > 100 m), las conclusiones de
  distancia y pitch máximo pueden cambiar. Re-evaluar con nuevo dataset si
  cambiamos de testcase.
- El cheater corregido con pitch real puede volverse demasiado letal en
  niveles donde antes apuntaba mal — verificar empíricamente que el
  win-rate vs cheater HARD/IMPOSSIBLE no cae por debajo de targets útiles
  (~15 % / ~3 %).

## Actualización 2026-06-02: gun offset

Observación empírica del usuario durante calibración:
**"los tiros suelen estar por encima"** del enemigo cuando ambos están al
mismo nivel Y.

Causa identificada en C++ (`src/units/AdvancedWalrus.cpp:40`):
```cpp
firingpos[1] = 2.3;
```

El cañón del Otter está **2.3m por encima del centro físico del vehículo**.
El proyectil spawnea en `pos + (0, 2.3, 0)` (línea 749 del mismo archivo).

Implicación: si calculáramos `pitch = atan(dy/dist)` directamente, con
`dy=0` (mismo nivel), pitch=0 → tiro horizontal → proyectil sale 2.3m
arriba del centro del enemigo → pasa por encima.

**Fix aplicado en `agent/policy_utils.py`**: el helper `pitch_to_target_rad`
ahora compensa el offset del cañón:

```python
real_dy = (other_y - my_y) - GUN_OFFSET_Y_M  # GUN_OFFSET_Y_M = 2.3
return math.atan2(real_dy, max(horizontal_dist, 1.0))
```

Magnitud de la corrección: a 500m de distancia, son 0.26° hacia abajo.
Pequeño pero suficiente para acertar a un Otter de ~5m de alto en lugar
de errar por encima.
