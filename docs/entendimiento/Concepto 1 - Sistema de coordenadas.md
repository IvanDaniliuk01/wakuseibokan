# Concepto 1 — Sistema de coordenadas

## La idea más simple: ubicar cosas

Imaginate que estás parado en una esquina y un amigo te llama por teléfono y te pregunta "¿dónde estás?". Vos podés decirle:

> *"Estoy a 3 cuadras al este de la plaza, y 2 cuadras al norte."*

Acabás de usar un **sistema de coordenadas**. Tiene tres ingredientes:

1. **Un punto de referencia** (la plaza). Se llama **origen**.
2. **Direcciones** para medir (este, norte). Se llaman **ejes**.
3. **Números** que dicen cuánto te moviste en cada dirección (3, 2). Se llaman **coordenadas**.

Un sistema de coordenadas es simplemente eso: un **acuerdo** para describir dónde está cada cosa usando números.

---

## El plano cartesiano (lo del colegio)

En la escuela se ve algo así, con dos ejes que se cruzan:

```
            Y (eje vertical)
            ▲
          4 │
          3 │       ● ← punto P
          2 │       │
          1 │       │
    ───────●────────┼──────▶  X (eje horizontal)
         0 │  1  2  3  4
         -1│
         -2│
            │
```

El **origen** es el punto donde se cruzan los dos ejes (el `●` de abajo). Lo llamamos el punto `(0, 0)`.

El punto P está en `(3, 3)`: significa "moveté 3 hacia la derecha (eje X) y 3 hacia arriba (eje Y)". Los dos números son las **coordenadas** del punto.

Por convención:

- **Eje X** = horizontal (derecha = positivo, izquierda = negativo)
- **Eje Y** = vertical (arriba = positivo, abajo = negativo)

Lo importante es entender que **un sistema de coordenadas es solo un acuerdo de cómo nombrar posiciones con números**. Podríamos haber dicho "eje X hacia la izquierda" en vez de a la derecha y todo funcionaría igual, solo cambian los signos.

---

## Pasamos a 3D: agregamos un eje más

El mundo real no es plano. Si pensás en tu pieza, las cosas tienen **tres** medidas: ancho, profundidad y alto. Necesitás tres números para ubicar algo.

Imaginá tu pieza: parado en un rincón, mirando hacia adentro.

```
                          Y (arriba — al techo)
                          ▲
                          │
                          │
                          │
                          │      ● ← lámpara colgada
                          │
                          │
                          └──────────────▶  X (a la derecha — a la pared)
                         ╱
                        ╱
                       ╱
                      ╱
                     ▼
                    Z (hacia adelante — hacia adentro de la pieza)
```

Ahora un punto necesita **tres** coordenadas: `(X, Y, Z)`. La lámpara podría estar en `(2, 3, 4)`: dos metros a la derecha, tres metros para arriba, cuatro metros hacia adelante.

---

## La convención específica del simulador Wakuseibokan

El simulador (se llama **ODE**, no importa qué es por ahora) eligió esta convención:

- **X** = derecha (este)
- **Y** = arriba (al cielo, opuesto a la gravedad)
- **Z** = "hacia adelante" del que mira (sur)

Esto es **el mismo dibujo** de la pieza de arriba. **El eje Y es el vertical** (apunta al techo).

Importante: en otros programas (por ejemplo, los robots que se ven en investigación con ROS) usan otra convención donde **Z** es el vertical. Cuando leas tutoriales de internet, este detalle te va a confundir si no lo tenés presente.

| Sistema | Eje vertical (arriba) | Eje "hacia adelante" |
|---------|----------------------|----------------------|
| ODE / Wakuseibokan | Y | Z |
| ROS / Gazebo | Z | X |
| Unity | Y | Z |
| Blender | Z | -Y |

---

## ¿Por qué importa todo esto?

Cuando el simulador te diga "el Otter está en `(50, 0, 30)`", vos tenés que saber qué significa cada número:

- 50 → 50 unidades al este desde el origen
- 0 → al nivel del piso (no hay altura)
- 30 → 30 unidades al sur desde el origen

Sin entender la convención, los números son ruido sin sentido.

---

## Resumen para llevarse

| Concepto | Qué es |
|----------|--------|
| **Origen** | El punto de referencia desde donde se mide. Coordenadas `(0, 0, 0)` en 3D. |
| **Ejes** | Las direcciones en las que se mide. En 3D son tres: X, Y, Z. |
| **Coordenadas** | Los números que dicen cuánto te alejaste del origen en cada eje. |
| **Convención del simulador** | X = derecha, **Y = arriba**, Z = adelante. |

---

## Lo que viene después

Hasta acá sabemos describir **un punto que no se mueve**. Lo siguiente es:

- **Concepto 2**: dos sistemas de coordenadas al mismo tiempo (el de la isla y el del Otter). Esto es la idea de "world frame" vs "body frame".
- **Concepto 3**: cómo describir que el Otter está **rotado** (no siempre mira para el mismo lado).
- **Concepto 4**: cómo se hace todo esto con números y "matrices" (que vamos a explicar desde cero).
