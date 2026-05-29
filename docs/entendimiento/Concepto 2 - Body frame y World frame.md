# Concepto 2 — Body frame y World frame (dos sistemas a la vez)

> 💡 **Visualización 3D acompañante**: `Concepto 2 - Visualizacion 3D.html` — abrila en el browser mientras leés esto. Probar los sliders mientras leés vale más que tres explicaciones escritas.

xdg-open "/home/itba/wakuseibokan/docs/entendimiento/Concepto 2 - Visualizacion 3D.html"


---

## ¿Por qué necesitamos dos sistemas?

En el Concepto 1 vimos **un** sistema de coordenadas. Con eso solo podemos decir cosas como "el Otter está en la posición `(50, 0, 30)` de la isla". Útil, pero limitado.

El problema aparece cuando querés describir cosas **desde el punto de vista del Otter**, no desde el punto de vista de la isla. Y eso vas a necesitar todo el tiempo.

Te lo muestro con una analogía simple.

---

## Analogía: vos en un auto

Imaginate que estás manejando un auto por la ciudad. Tu celular está apoyado sobre el asiento del acompañante.

Dos preguntas distintas:

**Pregunta 1**: ¿Dónde está tu celular **respecto al auto**?

> *"Está a mi derecha, a 50 cm de distancia, a la altura del asiento."*

Esta respuesta **nunca cambia** mientras vos manejes. No importa si vas para el norte, doblás en una esquina, o estás parado en un semáforo. El celular sigue estando "a tu derecha, 50 cm" respecto al auto.

**Pregunta 2**: ¿Dónde está tu celular **respecto a la ciudad**?

> *"Está en la esquina de Corrientes y Callao."*

Esta respuesta **cambia cada segundo** porque el auto se mueve por la ciudad. Si manejás 10 minutos, el celular ya está en otro barrio, aunque para vos siga estando "a tu derecha, 50 cm".

Acabás de usar **dos sistemas de coordenadas distintos al mismo tiempo**:

| Sistema | Origen | ¿Se mueve? | Para qué sirve |
|---------|--------|------------|----------------|
| **El de la ciudad** | Una esquina fija (por ejemplo el Obelisco) | No, está clavado al piso | Saber dónde estás en el mapa |
| **El del auto** | El centro de tu auto | Sí, se mueve y gira con el auto | Saber dónde están las cosas adentro tuyo |

**El mismo celular tiene dos pares de coordenadas distintos según el sistema que uses para describirlo.** Y los dos son correctos al mismo tiempo.

---

## Los nombres técnicos

Los nombres formales que usa la robótica son:

- **World frame** (frame del mundo) = el sistema de la ciudad. Fijo, no se mueve.
- **Body frame** (frame del cuerpo) = el sistema del auto. Pegado al objeto que se mueve, gira y se traslada con él.

"Frame" en inglés acá significa "marco de referencia" o "sistema de coordenadas". No es el frame de un cuadro ni el frame de un video. Es un sinónimo de "sistema de coordenadas". Vas a leer "world frame" mil veces en la documentación, por eso te uso el término en inglés desde el principio.

---

## El caso del Otter

Aplicamos lo mismo al simulador:

| Frame | Origen | Ejes | Comportamiento |
|-------|--------|------|----------------|
| **WORLD (W)** — la isla | Un punto fijo de la isla (centro) | X_W = este, Y_W = arriba, Z_W = sur | Nunca cambia |
| **BODY (B)** — el Otter | El centro del Otter | X_B = lado del Otter, Y_B = techo del Otter, Z_B = morro del Otter | Gira y se mueve con el Otter |

Usamos un **subíndice** para no confundirnos: `X_W` es "X en el world frame", `X_B` es "X en el body frame".

> 🔎 **Detalle**: la dirección física exacta de **+X_B** (si es a la derecha del Otter, a la izquierda, etc.) depende de una convención matemática que vamos a aclarar más adelante (Concepto 3/4 — rotaciones). Por ahora alcanza con saber que hay **tres ejes pegados al Otter, perpendiculares entre sí, que giran cuando el Otter gira**. En la visualización 3D los ves clarísimo.

---

## Ejemplo concreto — abrí la visualización al lado

**Setup inicial** (preset "Otter al sur"):

- Otter parado en el centro de la isla (`(0, 0, 0)_W`)
- Otter mirando hacia el sur (yaw = 0°)
- Warehouse 100 metros al norte del Otter

**Posición de la warehouse en world frame** (respecto a la isla):

En la convención de la isla, el norte es **menos Z** (porque Z apunta al sur). Entonces:

```
warehouse en world = (0, 0, -100)_W
```

**Posición de la warehouse en body frame** (respecto al Otter):

El Otter mira al sur, la warehouse está al norte → **detrás** del Otter. En el body frame, "atrás" es menos Z (porque +Z_B es el morro). Entonces:

```
warehouse en body = (0, 0, -100)_B
```

🔵 **En este caso particular las coordenadas coinciden** porque el Otter está perfectamente alineado con el mundo (su morro apunta al sur, igual que +Z_W).

---

### Ahora rotemos al Otter (preset "Otter al este")

Misma warehouse, misma posición en la isla. Pero ahora el Otter gira 90° hacia la izquierda y queda **mirando al este**.

**En world frame, la warehouse no se movió**: sigue en `(0, 0, -100)_W`. La isla no cambia.

**En body frame, sí cambia**. La warehouse pasa a estar en:

```
warehouse en body = (100, 0, 0)_B
```

Apretá el preset **"Otter al este"** en la visualización y comprobalo en el panel derecho. Vas a ver:

- `World: (0, 0, -100)_W` — no se movió
- `Body: (100, 0, 0)_B` — cambió completamente

**¿Por qué cambió?** Porque el Otter rotó. Su morro (+Z_B) ahora apunta al este, no al sur. La warehouse, que está al norte, ya no está "detrás" del Otter sino "al costado". Eso es lo que dicen las coordenadas body: cero en Z (no está ni adelante ni atrás del morro) y un valor positivo en X (está al costado del Otter).

**La misma warehouse, en el mismo lugar físico, tiene dos coordenadas totalmente distintas según el frame que usemos.** Ninguna es "más verdadera" que la otra, son dos descripciones válidas del mismo punto físico.

> 🔎 **Cómo se calcula la conversión** entre world y body cuando el Otter está rotado — eso es exactamente el **Concepto 3/4** que viene después. Por ahora alcanza con que **veas que cambia** y entiendas **por qué** (porque los ejes del body rotaron, mientras que el mundo no).

---

## ¿Por qué importa esto para el agente?

Cuando el simulador te manda telemetría, te dice cosas en **world frame**:

- "El Otter está en `(50, 0, 30)_W`"
- "El enemigo está en `(120, 0, -80)_W`"

Pero para tomar decisiones, vos vas a querer pensar en **body frame**:

- "El enemigo está adelante mío y a la derecha" → body frame.
- "Hay una warehouse 30 metros a mi izquierda" → body frame.

Porque las decisiones del Otter (acelerar adelante, doblar a la derecha) son naturales en **body frame**, no en world frame.

Si el Otter pensara en world frame, tendría que hacer cálculos del estilo "para alcanzar al enemigo que está al norte, y como yo apunto al este, tengo que girar -90 grados...". En body frame es directo: "el enemigo está adelante a la izquierda, doblo a la izquierda".

**Convertir entre los dos frames** es la operación que vamos a hacer todo el tiempo. Esa conversión es lo que viene en los próximos conceptos.

---

## Resumen para llevarse

| Concepto | Qué es |
|----------|--------|
| **World frame (W)** | Sistema de coordenadas fijo en la isla. Nunca cambia. |
| **Body frame (B)** | Sistema de coordenadas pegado al Otter. Se mueve y gira con él. |
| **Mismo punto, dos descripciones** | Un mismo lugar físico tiene coordenadas distintas en W y en B. Las dos son correctas. |
| **¿Para qué cada uno?** | World: para ubicarse en el mapa. Body: para tomar decisiones de movimiento. |
| **Conversión entre frames** | Es la operación más usada del agente. La vamos a aprender en los próximos conceptos. |

---

## Lo que viene después

- **Concepto 3**: cómo describir matemáticamente que el Otter está **rotado** (orientación, ángulo de yaw, rotaciones en el plano).
- **Concepto 4**: cómo se convierte un punto de world a body (y viceversa) usando ese ángulo.
- **Concepto 5**: el mismo problema pero en 3D completo, donde el Otter puede inclinarse (pitch, roll), no solo girar (yaw). Acá aparecen las **matrices** de rotación.
