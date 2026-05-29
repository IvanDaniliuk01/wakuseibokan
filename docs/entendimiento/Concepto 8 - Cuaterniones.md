# Concepto 8 — Cuaterniones (la rotación sin gimbal lock)

> 💡 **Visualización 3D acompañante**: `Concepto 8 - Visualizacion Cuaterniones.html`
>
> ```bash
> xdg-open "/home/itba/wakuseibokan/docs/entendimiento/Concepto 8 - Visualizacion Cuaterniones.html"
> ```

---

## El problema que vamos a resolver

En el Concepto 7 vimos que los ángulos de Euler (yaw, pitch, roll) tienen dos problemas:

1. **Gimbal lock** cuando pitch = ±90°: dos ejes se alinean, perdés un grado de libertad, los números saltan.
2. **No se puede interpolar suavemente** entre dos orientaciones (porque los ángulos se mueven en "saltos" cerca de los polos).

Para el agente queremos una representación de orientación que:

- No tenga singularidades (no se rompa nunca).
- Sea **continua**: pequeños cambios físicos → pequeños cambios en los números.
- Permita **interpolar suavemente** entre dos orientaciones.
- Sea fácil de componer (rotar y después rotar).

**Los cuaterniones cumplen las cuatro cosas.** A cambio, usan **4 números en vez de 3**.

---

## La intuición clave (lo más importante del concepto)

**Cualquier rotación 3D, por más complicada que parezca, se puede describir como:**

> *"Girá X grados alrededor de este eje específico"*

Eso es todo. Una rotación = **un eje + un ángulo**.

### Ejemplo

- "Rotá 90° alrededor del eje Y" → este caso es fácil, ya lo vimos como yaw=90°.
- "Rotá 45° alrededor del eje (1, 1, 0)/√2" → un eje raro, oblicuo, no alineado con ningún eje del world. Pero igual define una rotación válida.

**Cualquier rotación 3D puede expresarse así**, no importa cuán complicada sea. Esto es un teorema (Euler, 1775). Hasta una rotación que vos pensás como "yaw 30° + pitch 45° + roll 20°" en realidad es **equivalente a un único giro alrededor de algún eje específico**.

### ¿Cuántos números necesitamos para describir esto?

- 3 números para el eje (un vector 3D)
- 1 número para el ángulo

Total: **4 números**. Eso es lo que codifica un cuaternión.

---

## La estructura del cuaternión

Un cuaternión es un conjunto de **4 números**: `(w, x, y, z)`.

Pero **NO** son directamente "eje + ángulo". Son una **codificación** un poco distinta, que tiene propiedades matemáticas más lindas. La conversión es:

```
Dado un eje (ax, ay, az) (unitario) y un ángulo θ:

  w = cos(θ / 2)
  x = ax · sin(θ / 2)
  y = ay · sin(θ / 2)
  z = az · sin(θ / 2)
```

**Sí, es el ángulo dividido 2.** Eso parece raro pero es necesario para que las matemáticas funcionen. No te preocupes por el "por qué" — es la receta, y nunca vas a tener que calcularla a mano (scipy lo hace).

### Propiedad clave: norma unitaria

Los 4 números siempre cumplen:

```
w² + x² + y² + z² = 1
```

Es decir, el "vector 4D" `(w, x, y, z)` tiene **largo 1**. Si por errores numéricos se desvía un poquito, hay que **renormalizar** (dividir todo por la norma) para que vuelva a cumplirse.

### Ejemplos concretos para anclar la intuición

| Rotación | Eje | Ángulo | Cuaternión (w, x, y, z) |
|----------|-----|--------|--------------------------|
| Identidad (no rotar) | cualquiera | 0° | **(1, 0, 0, 0)** |
| Yaw 90° (girar alrededor de Y) | (0, 1, 0) | 90° | (cos 45°, 0, sin 45°, 0) ≈ **(0.707, 0, 0.707, 0)** |
| Yaw 180° | (0, 1, 0) | 180° | (cos 90°, 0, sin 90°, 0) = **(0, 0, 1, 0)** |
| Pitch 90° (alrededor de X) | (1, 0, 0) | 90° | **(0.707, 0.707, 0, 0)** |
| Roll 180° (alrededor de Z) | (0, 0, 1) | 180° | **(0, 0, 0, 1)** |

**Observación**: cuando `(x, y, z)` son cero, no hay rotación (es la identidad). Cuando `w` es cero, la rotación es de 180° exactos. Los valores intermedios son rotaciones intermedias.

---

## La propiedad rara: doble cobertura

Acá hay un detalle que te puede confundir si no lo sabés:

**El cuaternión `q` y su negativo `-q` representan la MISMA rotación física.**

Es decir:

```
( 0.707, 0, 0.707, 0)   ←┐
                          ├─ Las dos describen "yaw 90°"
(-0.707, 0,-0.707, 0)   ←┘
```

¿Por qué? Por la mitad del ángulo en la fórmula. Si rotás 90° o rotás 90° + 360° = 450°, llegás al mismo lugar físico. Pero el cuaternión de 450° = `(cos 225°, 0, sin 225°, 0) = (-0.707, 0, -0.707, 0)` — exactamente el negativo del otro.

### Por qué importa

Para una **red neural** esto es un problema. Si la red ve dos veces el mismo Otter en la misma orientación pero recibe `q` una vez y `-q` la otra, **piensa que son situaciones distintas** y aprende cualquier cosa.

**Solución estándar**: **canonicalizar** el cuaternión. La regla más común es **forzar que `w ≥ 0`**:

```python
def canonicalize(q):
    if q[0] < 0:  # w es negativo
        return -q  # invertir todo el cuaternión
    return q
```

Una línea de código. Siempre que recibas un cuaternión del simulador o de scipy, canonicalizalo antes de pasarlo a la red.

---

## ¿Por qué evita el gimbal lock?

Esto es lo más importante para entender el "porqué" de los cuaterniones.

**El gimbal lock pasaba porque** la representación de Euler tiene "polos" — puntos donde dos ejes coinciden y la representación se rompe. Geométricamente: los ángulos de Euler intentan mapear el conjunto de todas las rotaciones 3D al espacio R³ (tres números reales), pero **eso es matemáticamente imposible sin singularidades** (es un teorema topológico — el espacio de rotaciones no es "como" R³).

**El cuaternión usa 4 números en vez de 3.** Esa dimensión extra es lo que permite cubrir todas las rotaciones **sin polos, sin singularidades, sin discontinuidades**. Un movimiento físico suave del Otter siempre produce un cambio suave en los 4 números del cuaternión.

Es análogo a esto:

- **Latitud/longitud (Euler)** en la Tierra: 2 números, pero los polos rompen la representación.
- **Coordenadas (x, y, z) en el espacio 3D, restringidas a la superficie de la esfera (Cuaternión)**: 3 números con una restricción de norma. **No hay polos**. Funciona en todo lado.

Es una **sobre-parametrización** (más números de los teóricamente necesarios) **a cambio de** eliminar las singularidades. Vale la pena pagar ese precio.

---

## Operaciones útiles (lo que vas a usar en código)

No vas a programar la matemática de cuaterniones a mano. scipy/numpy ya tienen todo. Lo que tenés que saber es **qué función llamar**:

### 1. Aplicar un cuaternión a un vector (rotar un punto)

```python
from scipy.spatial.transform import Rotation
import numpy as np

q = np.array([0.707, 0, 0.707, 0])  # ordenado [x, y, z, w] en scipy
r = Rotation.from_quat(q)
v = np.array([1, 0, 0])  # punto a rotar

v_rotated = r.apply(v)
```

### 2. Componer dos rotaciones (rotar y después rotar)

En vez de multiplicar dos matrices, multiplicás dos cuaterniones:

```python
q_total = (r2 * r1).as_quat()   # primero r1, después r2
```

(Esto es **mucho más rápido** que multiplicar dos matrices 3×3.)

### 3. Conjugado / inversa

Para invertir una rotación (rotar al revés), simplemente negás las componentes `(x, y, z)` y dejás `w` igual:

```
si q = (w, x, y, z), entonces q⁻¹ = (w, -x, -y, -z)
```

(Esto es **muchísimo más rápido** que invertir una matriz.)

### 4. Slerp — interpolación esférica

**La operación más linda** de los cuaterniones. Si tenés dos orientaciones q₀ y q₁, el slerp te da una rotación intermedia `q(t)` para `t ∈ [0, 1]`:

```python
from scipy.spatial.transform import Slerp

key_times = [0, 1]
key_rots = Rotation.from_quat([q0, q1])
slerp = Slerp(key_times, key_rots)

q_intermedio = slerp(0.5).as_quat()  # mitad del camino entre q0 y q1
```

Es como interpolar entre dos puntos en una **esfera**: el camino más corto y suave. Útil para animaciones, predicción de orientación futura, etc.

### 5. Conversiones a/desde otras representaciones

```python
from scipy.spatial.transform import Rotation

# De matriz 3×3 a cuaternión
R_matrix = np.array([...])  # 3x3
q = Rotation.from_matrix(R_matrix).as_quat()  # [x, y, z, w]

# De Euler a cuaternión
q = Rotation.from_euler('yxz', [yaw, pitch, roll], degrees=True).as_quat()

# De cuaternión a matriz 3×3
R_matrix = Rotation.from_quat(q).as_matrix()

# De cuaternión a Euler (puede dar gimbal lock!)
yaw, pitch, roll = Rotation.from_quat(q).as_euler('yxz', degrees=True)
```

**Detalle de convención que te va a hacer perder horas si no lo sabés**: scipy usa el orden `(x, y, z, w)` (escalar al final). Otras librerías (ROS, Three.js) usan `(w, x, y, z)` (escalar primero). Si copiás un cuaternión de una librería a otra, vas a tener bugs invisibles. **Anotalo bien**.

---

## Para el agente: la pipeline real

Esto es lo que va a hacer el agente en cada tick:

```python
# 1. El simulador manda una matriz 3×3 por UDP (R[12])
R_matrix = decode_R12_from_udp(packet)

# 2. Convertir a cuaternión
q = Rotation.from_matrix(R_matrix).as_quat()  # [x, y, z, w]

# 3. Canonicalizar (forzar w >= 0)
if q[3] < 0:
    q = -q

# 4. Pasar a la red neural
state_vector = np.concatenate([
    self_pos,
    q,           # ← los 4 números del cuaternión van directo a la red
    velocity,
    enemy_features,
    ...
])
action = policy_network(state_vector)
```

**Los 4 floats del cuaternión van directos como features a la red**. No los descomponés en Euler, no los conviertes a nada. La red aprende qué significa cada combinación de los 4 números.

¿Por qué cuaternión y no la matriz 3×3 entera (9 floats)?

- **Compacto**: 4 floats vs 9 floats → menos parámetros.
- **Sin restricción difícil**: cumplir `w² + x² + y² + z² = 1` es fácil; cumplir `R · Rᵀ = I` (matriz ortogonal) en una red neural es muy difícil.
- **Smooth para gradient descent**: pequeños cambios físicos = pequeños cambios en los 4 floats.

---

## Resumen para llevarse

| Concepto | Qué es |
|----------|--------|
| **Idea central** | Cualquier rotación = **un eje + un ángulo**. |
| **Cuaternión** | 4 números (w, x, y, z) que codifican eje + ángulo de forma compacta. |
| **Fórmula** | `w = cos(θ/2)`, `(x, y, z) = sin(θ/2) · eje_unitario`. |
| **Restricción** | `w² + x² + y² + z² = 1` (norma unitaria). |
| **Doble cobertura** | `q` y `-q` son la misma rotación. Canonicalizar con `w ≥ 0`. |
| **Sin gimbal lock** | Topológicamente no tiene polos, a diferencia de Euler. |
| **Composición** | Multiplicar cuaterniones. Más rápido que multiplicar matrices. |
| **Inversa** | Conjugado: negar `(x, y, z)`, dejar `w`. Trivial y rápido. |
| **Slerp** | Interpolación esférica entre dos orientaciones. Suave y bien definida. |
| **Convención** | scipy usa `[x, y, z, w]`. ROS y Three.js usan `[w, x, y, z]`. ¡Cuidado! |
| **Para la red neural** | 4 floats directos como input, canonicalizados. |

---

## Lo que viene después

- **Concepto 9** (último de esta serie): la **matriz R[12]** que llega del simulador. Cómo se decodifica (12 floats, de los cuales 9 son rotación y 3 son padding), cómo se convierte a cuaternión, y cómo se integra en el pipeline del agente.

Después de eso terminamos toda la Parte I del plan (sistemas de coordenadas y rotaciones), y ya tenés todas las herramientas para empezar a procesar la telemetría real del simulador.
