# Concepto 6 — Matriz de rotación 2D (la versión compacta del Concepto 5)

> 💡 **Visualización 3D acompañante**: `Concepto 6 - Visualizacion Matriz.html`
>
> ```bash
> xdg-open "/home/itba/wakuseibokan/docs/entendimiento/Concepto 6 - Visualizacion Matriz.html"
> ```

---

## ¿Para qué meterse con matrices?

Las fórmulas del Concepto 5 funcionan perfecto:

```
x_B = dx · cos(yaw) − dz · sin(yaw)
z_B = dx · sin(yaw) + dz · cos(yaw)
```

Pero tienen tres problemas:

1. **Son largas y se repiten**. Cuando pasemos a 3D (Concepto 7), tendrás **nueve** fórmulas así, no dos. Necesitamos una notación más compacta.
2. **No queda claro qué es "la rotación" como objeto**. La rotación es una sola cosa (un giro de yaw grados), pero acá aparece desparramada en dos fórmulas.
3. **Componer rotaciones es feo**. Si querés rotar primero por yaw₁ y después por yaw₂, tenés que sustituir fórmulas dentro de fórmulas, y te queda un quilombo.

**La matriz resuelve los tres problemas**. Es una notación más compacta que dice exactamente lo mismo.

---

## ¿Qué es una matriz?

Una **matriz** es simplemente una **tabla rectangular de números** organizada en filas y columnas. Eso es todo. No tiene magia.

Ejemplo de una matriz 2×2 (se lee "dos por dos"):

```
       columna 0  columna 1
       ─────────  ─────────
fila 0 │   2          3   │
fila 1 │   1          4   │
       ─────────────────
```

La notación de tamaño es siempre **(filas × columnas)**. Una matriz 3×4 tiene 3 filas y 4 columnas. Una matriz 2×2 (cuadrada) tiene 2 filas y 2 columnas.

Cada número adentro de la matriz se llama **elemento** o **entrada**. Se identifica por (fila, columna):

- El elemento `(0, 0)` de la matriz de arriba es **2**.
- El elemento `(1, 0)` es **1**.
- El elemento `(0, 1)` es **3**.

(Empezamos a contar desde 0, como en programación. En matemática clásica empiezan desde 1, pero acá lo hacemos desde 0 para que se parezca al código).

---

## Vector como caso especial de matriz

Un **vector** que ya conocías (algo como `(dx, dz)`) se puede pensar como una matriz de **una sola columna**:

```
| dx |
| dz |
```

Es una matriz 2×1 (dos filas, una columna). Esto importa porque ahora vamos a **multiplicar** una matriz por un vector, y para que la receta funcione el vector tiene que estar en formato columna.

---

## La receta: cómo se multiplica matriz × vector

Esta es la única operación nueva que tenés que aprender en este Concepto. Te la muestro con un ejemplo numérico simple, sin senos ni cosenos.

### Ejemplo numérico

Tenemos esta multiplicación:

```
| 2  3 |   | 1 |     | ? |
| 1  4 | × | 5 |  =  | ? |
```

**La receta**: cada fila de la matriz se multiplica "entrada por entrada" con la columna del vector, y los resultados se suman. Eso te da una entrada del vector resultado.

**Fila 0 de la matriz** (`2  3`) **×** **columna del vector** (`1`, `5`):

```
2 · 1  +  3 · 5  =  2 + 15  =  17
```

**Fila 1 de la matriz** (`1  4`) **×** **columna del vector** (`1`, `5`):

```
1 · 1  +  4 · 5  =  1 + 20  =  21
```

Resultado:

```
| 2  3 |   | 1 |   | 17 |
| 1  4 | × | 5 | = | 21 |
```

Eso es **todo lo que necesitás saber** sobre multiplicación de matrices por vectores. Cada fila de la matriz produce **un** número del resultado, haciendo "multiplicar-entrada-por-entrada y sumar".

### Para que te quede grabado

Visualmente, podés pensarlo como "girar la fila para ponerla vertical, multiplicar de a pares, y sumar":

```
fila 0:   2   3
                       ↓ giro mental
                    2
                    3
                    ↓ multiplico con la columna
              | 1 |
              | 5 |
                    ↓ entrada por entrada
              | 2·1 |
              | 3·5 |
                    ↓ sumo
                17
```

---

## Ahora sí: la matriz de rotación 2D

Volvamos a nuestras fórmulas del Concepto 5:

```
x_B = dx · cos(yaw) − dz · sin(yaw)
z_B = dx · sin(yaw) + dz · cos(yaw)
```

**Fijate la estructura**: cada línea es "algo por dx, más algo por dz". Eso es **exactamente** la receta de multiplicación matriz × vector. Si ponemos los "algos" en una tabla, queda:

```
| x_B |   |  cos(yaw)   −sin(yaw) |   | dx |
|     | = |                       | × |    |
| z_B |   |  sin(yaw)    cos(yaw) |   | dz |
```

Verificá con la receta:

- **Fila 0** (`cos(yaw)  −sin(yaw)`) × **columna** (`dx, dz`):
  ```
  cos(yaw) · dx  +  (−sin(yaw)) · dz  =  dx·cos(yaw) − dz·sin(yaw)   ✓
  ```
- **Fila 1** (`sin(yaw)  cos(yaw)`) × **columna** (`dx, dz`):
  ```
  sin(yaw) · dx  +  cos(yaw) · dz  =  dx·sin(yaw) + dz·cos(yaw)   ✓
  ```

**Dan exactamente las mismas fórmulas que el Concepto 5.** La matriz no agrega nada nuevo: es solo una forma más ordenada de escribir lo mismo.

### Le ponemos nombre

A la matriz `| cos(yaw)  −sin(yaw) ; sin(yaw)  cos(yaw) |` la llamamos **R(yaw)** o **R_world→body**:

```
            |  cos(yaw)   −sin(yaw) |
R(yaw)  =   |                       |
            |  sin(yaw)    cos(yaw) |
```

Y ahora la conversión completa del Concepto 5 se escribe en **una sola línea**:

```
vector_B = R(yaw) × vector_W_relativo
```

(Donde `vector_W_relativo` ya tiene la traslación aplicada, o sea es `(dx, dz)`.)

Mucho más corto, ¿no? Y lo importante: **es lo mismo de antes**. No estamos haciendo cosas nuevas, solo escribiéndolas de forma compacta.

---

## La inversa: para ir de body a world

En el Concepto 5 dimos también las fórmulas inversas (body → world):

```
dx = x_B · cos(yaw) + z_B · sin(yaw)
dz = −x_B · sin(yaw) + z_B · cos(yaw)
```

Como matriz:

```
| dx |   |  cos(yaw)   sin(yaw) |   | x_B |
|    | = |                      | × |     |
| dz |   | −sin(yaw)   cos(yaw) |   | z_B |
```

**Mirá esta matriz y comparala con `R(yaw)` de arriba**. Vas a ver que es **la misma pero con las filas y columnas intercambiadas**:

```
R(yaw):                  R_inversa:
| cos    −sin |          | cos     sin |
| sin     cos |          | −sin    cos |
```

A esta operación de "intercambiar filas por columnas" se la llama **traspuesta** y se escribe `R^T` (R con una T arriba).

### Propiedad mágica de las matrices de rotación

**Para una matriz de rotación, su traspuesta es su inversa**:

```
R(yaw)^T  =  R_inversa  =  R(−yaw)
```

Esto es una propiedad fundamental y **muy útil**:

- En general, invertir una matriz es una operación complicada (computacionalmente costosa).
- Para rotaciones es trivial: solo intercambiás filas y columnas.

Esa propiedad la usamos todo el tiempo en código para ir de body a world sin tener que recalcular nada.

---

## En código real (Python con numpy)

Esto es lo que vas a escribir en el agente, casi tal cual:

```python
import numpy as np

def rotation_matrix(yaw_rad):
    """Devuelve la matriz de rotación 2D para un yaw dado."""
    c = np.cos(yaw_rad)
    s = np.sin(yaw_rad)
    return np.array([
        [c, -s],
        [s,  c],
    ])


def world_to_body_xz(point_W, otter_pos, yaw_rad):
    """Convierte un punto (x, z) de world a body."""
    # Paso A: traslación
    rel = np.array([
        point_W[0] - otter_pos[0],
        point_W[2] - otter_pos[2],
    ])
    
    # Paso B: rotación
    R = rotation_matrix(yaw_rad)
    body_xz = R @ rel   # ← el "@" es multiplicación matricial en numpy
    
    return body_xz


# Uso
yaw = np.radians(90)  # Otter mira al este
otter = (0, 0, 0)
warehouse = (0, 0, -100)  # 100 al norte

body = world_to_body_xz(warehouse, otter, yaw)
print(body)  # [100, 0]  → 100 unidades en +X_B
```

**El operador `@`** en numpy hace multiplicación matriz-matriz o matriz-vector. Una sola línea reemplaza las dos fórmulas largas del Concepto 5.

Para ir de body a world (inversa):

```python
def body_to_world_xz(point_B_xz, otter_pos, yaw_rad):
    R = rotation_matrix(yaw_rad)
    R_inv = R.T   # ← traspuesta (R.T en numpy)
    rel = R_inv @ point_B_xz
    return np.array([
        otter_pos[0] + rel[0],
        otter_pos[2] + rel[1],
    ])
```

Notá `R.T` — en numpy la traspuesta es un atributo, no una función. Súper limpio.

---

## Bonus: componer rotaciones

Una de las razones por las que las matrices son tan útiles es que **componer rotaciones se hace multiplicando matrices**.

Ejemplo: ¿qué pasa si primero rotás un vector por **yaw₁ = 30°** y después por **yaw₂ = 45°**?

Sin matrices, tendrías que aplicar la fórmula del Concepto 5 dos veces, una atrás de la otra. Con matrices:

```
R_total = R(yaw₂) × R(yaw₁)
```

Es **una sola** matriz que ya contiene las dos rotaciones combinadas. Y resulta ser igual a:

```
R_total = R(yaw₁ + yaw₂) = R(75°)
```

Para rotaciones 2D la suma es trivial (solo sumás los ángulos), pero **para 3D va a ser fundamental** porque no podés "sumar" rotaciones 3D directamente — pero sí podés multiplicar las matrices.

**Detalle importante del orden**: en multiplicación de matrices el orden importa. `R(yaw₂) × R(yaw₁)` significa "primero aplicar R(yaw₁), después R(yaw₂)". La matriz que se aplica primero queda **a la derecha**.

---

## ¿Y para qué me sirve toda esta notación si las fórmulas dan lo mismo?

Tres razones grandes:

1. **Compacidad**: una línea de código (`R @ v`) reemplaza dos fórmulas largas. Menos bugs, más legible.
2. **Generalización a 3D**: en el Concepto 7 vamos a tener una matriz 3×3 que generaliza esto. La estructura es la misma, solo cambia el tamaño.
3. **Composición**: rotar dos veces seguidas es multiplicar dos matrices. En 3D esto es **la única forma sensata** de componer rotaciones.

Y una razón práctica más: **toda la robótica y los gráficos 3D del mundo** están escritos en términos de matrices. Si querés leer cualquier código de simulación, motor de juego, o paper de robótica, vas a ver matrices por todos lados. Hay que hablar el idioma.

---

## Resumen para llevarse

| Concepto | Qué es |
|----------|--------|
| **Matriz** | Tabla rectangular de números organizada en filas y columnas. |
| **Vector como matriz columna** | Un vector `(a, b)` se escribe como matriz 2×1. |
| **Multiplicación matriz × vector** | Receta: fila × columna, entrada-por-entrada, sumar. Da otra columna. |
| **Matriz de rotación 2D** | `R(yaw) = [[cos, −sin], [sin, cos]]`. Aplicada a un vector relativo lo convierte de world a body. |
| **Traspuesta** | Intercambiar filas y columnas. Se escribe `R^T`. En numpy: `R.T`. |
| **Propiedad clave** | Para una matriz de rotación, la traspuesta es la inversa: `R^T = R⁻¹ = R(−yaw)`. |
| **Composición** | Rotar dos veces = multiplicar dos matrices. El orden importa: la que se aplica primero va a la derecha. |
| **En numpy** | `R @ v` para aplicar rotación. `R.T` para invertir. |

---

## Lo que viene después

- **Concepto 7**: pasamos a **3D completo**. Hasta ahora todo era en el plano (yaw alrededor del eje vertical). Pero el Otter puede inclinar el morro (pitch) o ladearse (roll) cuando sube una loma. La matriz pasa a ser 3×3 y aparecen 3 ángulos. Acá vamos a ver el famoso problema del **gimbal lock**.
- **Concepto 8**: **cuaterniones**, una representación alternativa de la rotación 3D que evita el gimbal lock. Es lo que va a entrar a la red neural.
- **Concepto 9**: la **matriz R[12]** del simulador. Cómo se decodifica lo que llega por UDP.
