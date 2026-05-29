# Concepto 7 — Rotaciones 3D completas (yaw, pitch, roll) y gimbal lock

> 💡 **Visualización 3D acompañante**: `Concepto 7 - Visualizacion Euler.html`
>
> ```bash
> xdg-open "/home/itba/wakuseibokan/docs/entendimiento/Concepto 7 - Visualizacion Euler.html"
> ```

---

## Lo que ya teníamos y lo que falta

Hasta el Concepto 6 dimos por sentado algo importante sin decirlo:

> El Otter está **apoyado en el piso, derecho**, y solo puede girar alrededor del eje vertical.

Con esa suposición, una sola rotación (yaw) describe toda su orientación. Pero en el simulador real eso no es siempre cierto:

- Cuando el Otter sube una colina, el morro se levanta → **el Otter está inclinado hacia arriba**.
- Cuando va atravesando una pendiente lateral, se ladea → **el Otter está inclinado de costado**.
- Cuando vuelca, se da vuelta → **el techo deja de mirar al cielo**.

Para describir todas estas orientaciones necesitamos **tres ángulos**, no uno. Y la matriz pasa de ser 2×2 (con 4 entradas) a 3×3 (con 9 entradas).

---

## Los tres ángulos: yaw, pitch, roll

Tomados de la aviación, son los nombres estándar para las 3 rotaciones independientes en 3D:

| Ángulo | Eje de rotación | Movimiento físico | Nombre en castellano |
|--------|-----------------|-------------------|----------------------|
| **Yaw** (ψ) | Eje vertical (Y) | "Girar la cabeza" — izquierda/derecha | Guiñada |
| **Pitch** (θ) | Eje lateral (X) | "Asentir/Negar con la cabeza" — arriba/abajo | Cabeceo |
| **Roll** (φ) | Eje longitudinal (Z) | "Inclinar la cabeza hacia el hombro" | Alabeo |

### Visualización mental con la mano

Estiráte la mano derecha con la palma hacia abajo, dedos apuntando al frente.

- **Yaw**: girá la mano izquierda/derecha como saludando. El pulgar y el meñique se mueven horizontalmente.
- **Pitch**: levantá/bajá los dedos. La palma sigue mirando "abajo-adelante" o "abajo-atrás".
- **Roll**: girá la muñeca como si dieras vuelta la mano. La palma pasa a mirar a un costado, después arriba, después al otro costado.

Cada uno es **independiente de los otros dos**. Esos 3 números (yaw, pitch, roll) describen completamente la orientación.

### Para el Otter

| Ángulo | Significado físico para el Otter |
|--------|----------------------------------|
| **Yaw** | Para dónde apunta el morro en el plano del piso. Lo que ya conocíamos. |
| **Pitch** | Cuánto se levanta o baja el morro (positivo = sube, negativo = baja). |
| **Roll** | Cuánto se ladea sobre el morro (positivo = se inclina hacia un lado, negativo al otro). |

En terreno plano, pitch y roll son ≈ 0 y solo importa el yaw. Pero en colinas y pendientes los tres son distintos de cero.

---

## La matriz 3D como producto de tres matrices

En 2D la matriz de rotación era una sola tabla 2×2 que dependía de un solo ángulo. En 3D la matriz es 3×3 y se construye **multiplicando tres matrices**, una por cada ángulo.

Cada matriz individual rota alrededor de **un solo eje** (los otros dos quedan quietos):

### Rotación alrededor de Y (yaw)

```
         |  cos(ψ)   0   sin(ψ) |
R_y(ψ) = |    0      1     0    |
         | −sin(ψ)   0   cos(ψ) |
```

Notá que la fila/columna del medio (la del eje Y) tiene un 1 y dos 0 — significa "Y no cambia". Las otras dos filas/columnas tienen el sin/cos de antes (es esencialmente la matriz 2D del Concepto 6, embedida en una 3D).

### Rotación alrededor de X (pitch)

```
         |  1     0          0    |
R_x(θ) = |  0   cos(θ)   −sin(θ) |
         |  0   sin(θ)    cos(θ) |
```

Acá la fila/columna del eje X tiene el 1 fijo, y sin/cos están en el plano Y-Z.

### Rotación alrededor de Z (roll)

```
         |  cos(φ)   −sin(φ)   0 |
R_z(φ) = |  sin(φ)    cos(φ)   0 |
         |    0          0     1 |
```

Acá la fila/columna del eje Z tiene el 1 fijo.

### La matriz total

La rotación completa del Otter se obtiene **multiplicando las tres**:

```
R_total = R_y(yaw) · R_x(pitch) · R_z(roll)
```

(El orden de los productos depende de la convención; esta es una de las más comunes pero hay 12 posibles).

El resultado es una matriz 3×3 con 9 entradas. Cada entrada es una expresión que combina varios senos y cosenos de los tres ángulos. **No vale la pena memorizarlas**: las computa numpy en una línea, o las recibís directamente del simulador.

---

## El problema del orden (y por qué hay 12 convenciones)

Acá viene una complicación nueva que en 2D no existía: **el orden en que aplicás las rotaciones importa**.

Probá esto físicamente con un libro:

1. **Versión A**: empezá con el libro plano sobre la mesa. Primero rotalo 90° sobre el eje vertical (yaw). Después rotalo 90° hacia adelante (pitch).
2. **Versión B**: empezá igual. Primero rotalo 90° hacia adelante (pitch). Después 90° sobre el eje vertical (yaw).

**Te van a quedar en orientaciones distintas.** Aunque hiciste los mismos dos giros, el resultado final depende del orden.

Por eso existen las **12 convenciones de Euler**:

- Convenciones XYZ, XZY, YXZ, YZX, ZXY, ZYX
- Cada una con dos modos: **intrínseco** (los ejes rotan con el cuerpo) o **extrínseco** (los ejes son los fijos del world)
- 6 × 2 = 12 combinaciones posibles

Cuando alguien dice "RPY" en un código, **siempre tenés que averiguar cuál convención específica usa**. Mezclarlas es una fuente clásica de bugs.

En Python con scipy se especifica como string:

```python
from scipy.spatial.transform import Rotation

# Convención: yaw alrededor de Y, pitch alrededor de X, roll alrededor de Z
# extrínseca (minúsculas) o intrínseca (mayúsculas)
r = Rotation.from_euler('yxz', [yaw, pitch, roll], degrees=True)
```

---

## El problema serio: GIMBAL LOCK

Esta es la sección clave del concepto. La explicación corta no suele alcanzar para entenderlo bien, así que vamos despacio.

### Primero: ¿qué es un "grado de libertad"?

Un **grado de libertad** (DOF, "degree of freedom") es **una dirección independiente** en la que algo puede moverse o cambiar. Ejemplos cotidianos:

| Objeto | Grados de libertad | Por qué |
|--------|--------------------|---------|
| Tren en su vía | **1** | Solo puede ir adelante o atrás |
| Pieza de ajedrez en el tablero | **2** | Se mueve en X y en Y |
| Drone en el aire | **3** | Sube/baja, izquierda/derecha, adelante/atrás |
| Manija de la puerta | **1** | Solo gira |

Para describir la **orientación** de un objeto 3D necesitás **3 grados de libertad independientes**. Esos son justamente yaw, pitch y roll. Son tres cosas que podés ajustar **por separado**, y combinándolas alcanzás cualquier orientación posible.

### La analogía clave: el GPS en los polos

Esta es la misma idea que el gimbal lock, pero con algo que sí entendés intuitivamente.

Para describir tu posición en la Tierra necesitás 2 números: **latitud y longitud**. Funciona perfecto en casi todo el planeta. Pero:

> *¿Cuál es la **longitud** del Polo Norte?*

Respuesta: **es indefinida**. Cualquier valor entre 0° y 360° es "igual de válido", porque todos los meridianos se juntan en el polo. Si estás parado en el polo, **la longitud dejó de tener sentido**.

Y peor: si caminás **1 metro al sur** desde el polo:

- Si fuiste hacia Argentina, tu longitud es ~58° oeste.
- Si fuiste hacia España, tu longitud es ~3° oeste.
- Si fuiste hacia Australia, tu longitud es ~133° este.

**Mismo movimiento físico de 1 metro, números totalmente distintos.** El GPS "salta" según hacia dónde te muevas. Eso es porque cerca del polo, la coordenada longitud **se rompe**.

### El gimbal lock es exactamente lo mismo, pero con orientación

- **En condiciones normales** (pitch entre -89° y 89°): yaw, pitch y roll son 3 cosas independientes. Movés cada uno y cambia algo distinto.
- **Cuando pitch llega a ±90°** (morro apuntando al cielo o al suelo): **yaw y roll se vuelven la misma cosa físicamente**.

### ¿Por qué pasa eso geométricamente?

Pensalo así. El Otter tiene un morro. Para describir hacia dónde apunta el morro necesitás 2 números (es como elegir un punto en una esfera, igual que latitud + longitud):

- yaw + pitch → te dicen hacia dónde apunta el morro.

Y el tercer número (roll) te dice **cuánto está rotado el cuerpo alrededor del morro**. Pensalo como "el Otter mira en esa dirección, ¿pero está derecho o de costado?".

```
Pitch normal (morro horizontal):
   morro apunta al norte
   ↑
   ○━━━━━●  ← roll dice cómo está orientado el cuerpo
   ↓
                  yaw y roll giran alrededor de EJES DIFERENTES:
                  - yaw → alrededor del eje vertical (Y world)
                  - roll → alrededor del morro (Z del Otter, horizontal)
                  → son independientes ✓
```

```
Pitch = 90° (morro al cielo):
                 ↑ morro
                 │
                 ●
                 ○  ← cuerpo del Otter vertical

                 ahora:
                 - yaw → gira alrededor del eje vertical (Y world)
                 - roll → gira alrededor del morro (Z del Otter)
                 PERO el morro AHORA TAMBIÉN es vertical
                 → los dos ejes coinciden → es la misma rotación
```

Cuando el morro apunta al cielo, **rotar el cuerpo alrededor del eje vertical** y **rotar el cuerpo alrededor del morro** son **la misma operación física**, porque los dos ejes son el mismo.

Resultado: tenés **3 sliders pero solo 2 efectos visibles distintos**. **Perdiste un grado de libertad**.

### Las dos implicancias concretas

#### Problema 1: ambigüedad (varios "nombres" para la misma orientación)

Para una misma orientación física hay **infinitas combinaciones de (yaw, pitch, roll)** que la describen.

Ejemplo con el Otter apuntando al cielo, techo apuntando al norte:

| yaw | pitch | roll | ¿Describe la misma orientación? |
|-----|-------|------|-------------------------------|
| 0° | 90° | 0° | Sí ✓ |
| 45° | 90° | -45° | Sí ✓ |
| 90° | 90° | -90° | Sí ✓ |
| 180° | 90° | -180° | Sí ✓ |

El simulador y la red neural **no pueden elegir cuál de todos esos triples mandar**. Diferentes implementaciones pueden mandar distintos, y nada te avisa.

#### Problema 2: discontinuidad (el más grave para el agente)

Imaginá esta secuencia de ticks del simulador con el Otter casi vertical (pitch ≈ 89°):

```
Tick 100:  yaw=  45°  pitch=89°  roll=  10°    ← todo OK
Tick 101:  yaw=  45°  pitch=89°  roll=  10°    ← Otter quieto
Tick 102:  yaw=  45°  pitch=90°  roll=  10°    ← apenas se inclinó un poquito más
Tick 103:  yaw= 225°  pitch=89°  roll= 190°    ← ¡¡¡SALTO ENORME!!!
Tick 104:  yaw= 225°  pitch=89°  roll= 190°    ← otra vez quieto
```

**Físicamente el Otter no hizo nada raro entre tick 102 y 103**. Solo se balanceó levemente. Pero los números yaw y roll **saltaron 180°** porque la representación es ambigua cerca del polo.

¿Qué hace la red neural ante esto? **Cree que pasó algo enorme**. El input cambió drásticamente:

```
red.input = [yaw=45°, ...] → red.acción = "doblar suave a la izquierda"
red.input = [yaw=225°, ...] → red.acción = "girar bruscamente porque está dado vuelta"
```

La red reacciona de forma descontrolada a un cambio que físicamente no existió. **El entrenamiento se desestabiliza** porque la red trata de "explicar" cambios enormes en el input que no corresponden a cambios físicos del mundo.

Es el equivalente exacto a un GPS reportando saltos de 100 km cuando estás caminando a 1 m/s.

### El "grado de libertad perdido" en términos prácticos

Es como si tu auto tuviera volante, palanca de cambios y freno de mano. Tres controles independientes. Pero de repente, en cierta situación, **el volante y el freno de mano hacen exactamente lo mismo**. Te queda un auto "manejable" pero perdiste una herramienta de control real.

### Origen del nombre: los gimbals mecánicos

El nombre viene de los **gimbals** mecánicos (anillos de un giroscopio o de una cardán):

```
   anillo externo (yaw)
      ┌──────────────┐
      │  anillo      │
      │  medio       │
      │  (pitch)     │
      │  ┌────────┐  │
      │  │ anillo │  │
      │  │ interno│  │ ← el objeto está en el centro
      │  │ (roll) │  │
      │  └────────┘  │
      └──────────────┘
```

Cuando el anillo medio gira 90°, el anillo interno queda en el mismo plano que el externo. Los dos giran "alrededor del mismo eje" y ya no podés controlar las 3 rotaciones independientes.

Famoso ejemplo histórico: la misión Apollo 11 estuvo cerca de perder el control de su sistema de guía por gimbal lock. Los astronautas tenían un procedimiento de emergencia para evitarlo.

### Para el Otter

El riesgo parece bajo (un Otter terrestre no suele apuntar al cielo)... **hasta que se vuelca, cae en una pendiente extrema, o el ODE simula físicas raras**. Y ahí explota el agente. Por eso siempre se evita usar Euler como representación de orientación dentro de la red.

---

## La solución: cuaterniones (próximo concepto)

El gimbal lock es **una limitación fundamental de cualquier representación con 3 ángulos**. No es un bug que se pueda arreglar — es un teorema topológico (no se puede mapear suavemente las rotaciones 3D a R³ sin singularidades).

La salida estándar es usar **4 números en vez de 3**. La representación se llama **cuaternión** y la vamos a ver en el **Concepto 8**. Las propiedades clave:

- Sin singularidades (no hay gimbal lock).
- Interpolación suave entre dos orientaciones.
- Es la representación que va a entrar a la red neural.
- El simulador internamente probablemente trabaja con cuaterniones.

---

## Para el agente: implicancias prácticas

| Situación | Qué hacés |
|-----------|-----------|
| Vas a guardar la orientación del Otter en una variable | Cuaternión (Concepto 8) o matriz 3×3 — **nunca** ángulos de Euler. |
| Vas a alimentar la orientación a la red neural | Cuaternión (4 floats, sin singularidades). |
| Querés mostrar la orientación en un debug log para vos | Yaw/pitch/roll, porque son interpretables para humanos. Pero solo para mostrar, no para cálculos. |
| Querés rotar un vector | Aplicás directamente la matriz 3×3 que sale del simulador (es R[12]). No necesitás pasar por Euler en ningún momento. |

**Regla de oro**: ángulos de Euler son para humanos, no para cálculos numéricos.

---

## Probá la visualización

En el HTML acompañante vas a ver un Otter abstracto con sliders para los 3 ángulos (yaw, pitch, roll). Algunas cosas que tenés que observar:

1. **Mové cada slider por separado** con los otros dos en 0. Vas a ver cada rotación pura.
2. **Pitch a 90°**: el morro apunta al cielo. Ahora mové yaw y roll. **Vas a notar que producen el mismo efecto visual** — esto es gimbal lock.
3. La matriz 3×3 se muestra en el panel y vas a ver que las 9 entradas oscilan según los tres ángulos.

---

## Resumen para llevarse

| Concepto | Qué es |
|----------|--------|
| **Yaw** | Rotación alrededor de Y (eje vertical). "Girar la cabeza". |
| **Pitch** | Rotación alrededor de X (eje lateral). "Asentir". |
| **Roll** | Rotación alrededor de Z (eje longitudinal). "Inclinar al hombro". |
| **Matriz 3×3** | Producto de R_y, R_x, R_z. 9 entradas que combinan los 3 ángulos. |
| **Orden importa** | Hay 12 convenciones distintas (XYZ, ZYX, etc., intrínseco/extrínseco). |
| **Gimbal lock** | Cuando el ángulo medio llega a ±90°, dos ejes se alinean y perdés 1 DOF. Catastrófico para interpolación y para NN. |
| **Solución** | Cuaterniones (4 números sin singularidades). Concepto 8. |
| **Regla práctica** | Euler para humanos, cuaternión para cálculos. |

---

## Lo que viene después

- **Concepto 8**: **cuaterniones**. La representación de rotación 3D con 4 números que evita el gimbal lock. Va a parecer raro al principio (un "número" con 4 componentes) pero es lo que entra a la red neural.
- **Concepto 9**: la **matriz R[12]** que llega del simulador. Cómo se decodifica, cómo se convierte a cuaternión y por qué tiene 12 floats en vez de 9.
