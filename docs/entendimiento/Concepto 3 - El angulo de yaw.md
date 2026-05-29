# Concepto 3 — El ángulo de yaw (cómo describir hacia dónde mira el Otter)

> 💡 **Visualización 3D acompañante**: `Concepto 3 - Visualizacion Yaw.html`
>
> ```bash
> xdg-open "/home/itba/wakuseibokan/docs/entendimiento/Concepto 3 - Visualizacion Yaw.html"
> ```

---

## ¿Qué es una rotación?

Es cuando algo **gira sin moverse de lugar**.

- Una rueda gira sobre su eje (sin trasladarse).
- Una puerta gira en sus bisagras.
- Una persona gira sobre su talón cuando cambia de dirección sin caminar.

En todos los casos hay **un eje** alrededor del cual gira, y **una cantidad** de giro.

Para describir cuánto giró usamos un **ángulo**.

---

## ¿Cómo se mide un ángulo? (refresco del colegio)

Un ángulo es **cuánto giro hay entre dos direcciones**.

La unidad que conocés del colegio es el **grado** (símbolo `°`):

```
        90°
         │
         │
   180°──●──── 0°
         │
         │
        270°  (o -90°)
```

Equivalencias importantes:

| Giro | Grados |
|------|--------|
| Una vuelta completa | 360° |
| Media vuelta | 180° |
| Cuarto de vuelta | 90° |
| Octavo de vuelta | 45° |
| Sin girar | 0° |

Y los **negativos** giran al revés:
- +90° = giró en un sentido (por ejemplo, antihorario)
- -90° = giró el mismo cuarto de vuelta pero en sentido contrario

---

## Grados vs Radianes (el otro modo de medir ángulos)

Los humanos preferimos los grados (360 es un número intuitivo, 90 es la mitad de 180, etc.).

Pero la matemática y las computadoras prefieren otra unidad: el **radián**.

¿Qué es un radián? Es solo una unidad distinta para medir lo mismo. Como medir distancia en metros o en pies — son dos unidades que miden la misma cosa.

La equivalencia es:

| Ángulo | Grados | Radianes | Aproximado |
|--------|--------|----------|------------|
| Vuelta completa | 360° | **2π** | ≈ 6.28 |
| Media vuelta | 180° | **π** | ≈ 3.14 |
| Cuarto de vuelta | 90° | **π/2** | ≈ 1.57 |
| Octavo de vuelta | 45° | **π/4** | ≈ 0.78 |

(`π` ≈ 3.14159... el famoso número pi.)

**Fórmula de conversión** (la única que tenés que recordar):

```
radianes = grados × π / 180
grados   = radianes × 180 / π
```

**¿Por qué te lo aclaro?** Porque cuando programes el agente, las funciones de Python (`math.sin`, `math.cos`, `numpy.sin`, etc.) **trabajan con radianes, no con grados**. Si le pasás 90 esperando "noventa grados", la computadora va a entender "noventa radianes" y te va a dar un resultado completamente equivocado.

**Regla práctica**:
- Sliders, interfaces para humanos → grados
- Cálculos internos, fórmulas, funciones de programación → radianes
- Convertís al pasar de uno al otro

---

## El yaw del Otter

**Yaw** es una palabra técnica de aviación y robótica. Significa: **el ángulo de rotación alrededor del eje vertical**.

En nuestro caso (Otter en una isla):
- Eje vertical = +Y_W (apunta al cielo, ya lo vimos en Concepto 1)
- Yaw = cuánto está girado el Otter alrededor de ese eje

### Ojo: ¿desde qué frame estamos describiendo "hacia dónde mira"?

Acá hay una sutileza que vale la pena aclarar (porque es exactamente el tipo de cosa que te puede confundir todo el tiempo si no la tenés clara).

Cuando decimos **"el Otter mira al sur"**, "sur" es una dirección **del world frame** (es una dirección de la isla, fija, no del Otter).

¿Por qué no la describimos desde el body frame? Porque **en el body frame el Otter siempre mira hacia su propio +Z_B**, sin importar el yaw. Eso es la definición misma del eje: +Z_B es, por construcción, el morro del Otter. Decir "el Otter mira a +Z_B" no aporta información — es como decir "mi adelante está adelante mío". Siempre es cierto, no te dice nada nuevo.

Lo que **sí** es informativo es la pregunta:

> *Dado un yaw, ¿en qué dirección **del mundo** está apuntando el morro?*

Esa pregunta sí cambia con el ángulo. Y la respuesta es la convención del simulador:

| yaw | El morro (siempre +Z_B) apunta a esta dirección **del world frame** |
|-----|-----|
| 0° | +Z_W (sur) — orientación de referencia |
| 90° | +X_W (este) |
| 180° | -Z_W (norte) |
| -90° (o 270°) | -X_W (oeste) |

**Resumen**: el yaw es la "conversión" entre body y world para la dirección del morro. Esto es exactamente lo que vamos a formalizar con cuentas concretas en el Concepto 4.

**El yaw, por sí solo, te dice TODO sobre la orientación del Otter en el plano XZ.**

Con un solo número (un ángulo entre -180° y 180°) ya sabés exactamente para dónde mira. Esto es muy potente.

---

## ¿Y los otros dos ángulos? (pitch y roll)

En 3D completo, un objeto puede girar alrededor de **tres ejes distintos**:

| Ángulo | Eje de giro | Qué significa físicamente |
|--------|-------------|---------------------------|
| **Yaw** | Y (vertical) | Girar como una rueda de timón. Cambia "hacia dónde mira" sin inclinarse. |
| **Pitch** | X (lateral) | Asentir con la cabeza ("sí"). Inclinarse hacia adelante o hacia atrás. |
| **Roll** | Z (longitudinal) | Inclinarse de costado, como un avión cuando dobla. |

```
  Yaw:  girar a izquierda/derecha (mantenés la cabeza derecha)
  Pitch: bajar el morro / levantar el morro (como saludar con la cabeza)
  Roll:  ladearse (como cuando un avión dobla en el aire)
```

Para el Otter:
- **Yaw** importa mucho — siempre que el Otter cambie de dirección, cambia el yaw.
- **Pitch** importa cuando sube o baja una pendiente.
- **Roll** importa cuando se ladea en terreno irregular.

**Por ahora trabajamos solo con yaw**, porque la mayor parte del tiempo el Otter está sobre terreno plano y solo va a cambiar de dirección. Cuando el agente tenga que lidiar con colinas pronunciadas, agregamos pitch y roll. Pero la idea es la misma: cada uno es un ángulo más.

---

## Probá la visualización

Abrí el HTML y vas a ver:

- Una **rosa de los vientos** en el suelo con marcas cada 30° y los puntos cardinales (N, S, E, O).
- El Otter en el centro, **solo rota** (no se traslada) — esto es para que te enfoques en el ángulo y nada más.
- Una **flecha amarilla grande** que sale del Otter indicando para dónde mira.
- Un **arco verde** que marca visualmente el ángulo desde la posición de referencia (sur) hasta la dirección actual.
- Un display con el yaw en **grados y en radianes** al mismo tiempo, para que veas la equivalencia.
- Botones de presets para los casos típicos (0°, 90°, 180°, etc.).

**Cosas que tenés que probar**:

1. Mové el slider lentamente y observá cómo:
   - La flecha amarilla rota.
   - El arco verde crece.
   - Los valores en grados y radianes cambian al mismo tiempo (uno es proporcional al otro).
2. Llevá el slider a **90°** → Otter mirando al este. Fijate cuánto es ese ángulo en radianes (1.57 ≈ π/2).
3. Llevalo a **180°** → Otter mirando al norte. Vas a ver que en radianes son 3.14 ≈ π.
4. Probá ángulos negativos. Confirmá que -90° y +270° terminan en la misma dirección (oeste).
5. Llevalo a 360° y vas a ver que vuelve a quedar como en 0° (una vuelta completa).

---

## Resumen para llevarse

| Concepto | Qué es |
|----------|--------|
| **Rotación** | Cambio de orientación sin cambio de posición. |
| **Ángulo** | Cuantifica la rotación. |
| **Grado (°)** | Unidad humana. 360° = vuelta completa. |
| **Radián** | Unidad matemática/computacional. 2π ≈ 6.28 = vuelta completa. |
| **Conversión** | `radianes = grados × π / 180` |
| **Yaw** | Ángulo de rotación alrededor del eje vertical (Y). El único que nos importa por ahora. |
| **Pitch / Roll** | Los otros dos ángulos. Los vemos cuando haga falta. |

---

## Lo que viene después

Hasta acá sabemos **describir** la rotación con un número (el ángulo). Lo que **no** sabemos todavía es **usarlo** para hacer cuentas — por ejemplo, calcular dónde está un punto del world frame visto desde el body frame.

Para hacer esas cuentas necesitamos dos funciones matemáticas: **seno** y **coseno**. Eso viene en el próximo concepto.

- **Concepto 4**: Seno y coseno — la herramienta para conectar ángulos con coordenadas.
- **Concepto 5**: Conversión world ↔ body usando seno y coseno (¡por fin la cuenta concreta!).
- **Concepto 6**: Lo mismo pero con matrices (que es como aparece en el código real del simulador).
