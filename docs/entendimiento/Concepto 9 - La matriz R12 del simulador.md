# Concepto 9 — La matriz R[12] del simulador (cierre de la Parte I)

> 💡 **Visualización 3D acompañante**: `Concepto 9 - Visualizacion R12.html`
>
> ```bash
> xdg-open "/home/itba/wakuseibokan/docs/entendimiento/Concepto 9 - Visualizacion R12.html"
> ```

---

## El último paso

Llegaste al final de la Parte I. Tenés todas las piezas teóricas:

1. Sistemas de coordenadas (Concepto 1)
2. Body vs World frame (Concepto 2)
3. Yaw (Concepto 3)
4. Seno y coseno (Concepto 4)
5. Conversión world ↔ body con cuentas (Concepto 5)
6. Matriz de rotación 2D (Concepto 6)
7. Rotaciones 3D y gimbal lock (Concepto 7)
8. Cuaterniones (Concepto 8)

Lo que falta es **conectar todo esto con lo que realmente llega del simulador** por UDP en cada tick. Ese paquete trae la orientación del Otter en una forma específica: una **matriz de 12 floats** que se llama `R[12]`.

Este concepto explica:
- Por qué son 12 floats y no 9.
- Cómo se decodifica.
- Cómo se conecta con cuaternión (lo del Concepto 8) y body/world frame (Concepto 2).
- El **pipeline completo** del agente: desde el byte que llega por UDP hasta el input de la red neural.

---

## ¿Por qué una matriz y no directamente un cuaternión?

El simulador usa **ODE (Open Dynamics Engine)**, una librería de simulación física escrita en C++. Internamente, ODE representa todas las orientaciones como **matrices 3×3**. Eso es una decisión de diseño de ODE — los desarrolladores eligieron matrices porque son más fáciles de aplicar a vectores (un solo producto matricial) en el cálculo de colisiones y dinámicas.

Cuando el simulador exporta la orientación del Otter por UDP, lo más simple es mandar lo que ya tiene en memoria: la matriz. No la convierte a cuaternión antes.

Vos como cliente del agente vas a hacer la conversión a cuaternión **del lado tuyo** después de recibir el paquete.

---

## El layout R[12]: por qué 12 floats si la rotación necesita 9

Acá viene el detalle interesante. Una matriz 3×3 tiene **9 entradas**. ¿Por qué entonces R[12] tiene **12 floats**?

Respuesta: **padding** por **alineación SIMD**.

### ¿Qué es SIMD?

**SIMD** = "Single Instruction Multiple Data". Es una optimización de hardware donde el procesador hace **4 operaciones en paralelo** en lugar de una sola. Los registros SIMD modernos (SSE, AVX) trabajan en bloques de **128 bits = 4 floats de 32 bits**.

Para que SIMD funcione eficientemente, los datos tienen que estar **alineados** en memoria a múltiplos de 16 bytes (4 floats). Si están desalineados, el procesador se vuelve lento o directamente crashea.

### ¿Qué hace ODE?

ODE guarda su matriz 3×3 de forma **alineada a 16 bytes**. Cada fila ocupa 4 floats: los 3 datos + 1 float de **padding** (relleno, no usado). Total: 3 filas × 4 floats = **12 floats**.

```
índice:   0   1   2   3   4   5   6   7   8   9  10  11
        ┌──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┐
R[12] = │r0│r1│r2│ P│r4│r5│r6│ P│r8│r9│r10│ P│
        └──┴──┴──┴──┴──┴──┴──┴──┴──┴──┴──┴──┘
         fila 0       fila 1       fila 2
        ↑ datos    ↑ padding (basura)
```

Los **floats en índices 3, 7, 11 son padding** — pueden tener cualquier valor (basura no inicializada). **Ignoralos siempre**.

### El error clásico

Si tratás de leer la matriz como si fuera contigua (`R[0..8]` para los 9 datos), vas a tomar `R[3]` como si fuera una entrada de la matriz, pero `R[3]` es basura.

**Layout correcto** para reconstruir la matriz 3×3:

```python
import numpy as np

# Asumiendo R12 es un array/lista de 12 floats
R_3x3 = np.array([
    [R12[0],  R12[1],  R12[2]],
    [R12[4],  R12[5],  R12[6]],
    [R12[8],  R12[9],  R12[10]],
])
```

Los índices saltean cada **+4**, no **+3**. Este es uno de los bugs más comunes al integrar con ODE.

---

## Cómo decodificar el paquete UDP

Asumiendo que el simulador manda los 12 floats como **little-endian float32** (32 bits cada uno):

```python
import struct
import numpy as np

# packet es el bytes del UDP que contiene los 12 floats consecutivos
# (en algún offset del paquete más grande)

# Opción 1: struct
R12 = struct.unpack('<12f', packet[offset:offset+48])  # 12 floats × 4 bytes = 48 bytes
# (el '<' es little-endian, '12f' son 12 floats)

# Opción 2: numpy (más rápido si hacés esto muchas veces)
R12 = np.frombuffer(packet, dtype='<f4', count=12, offset=offset)

# Después reconstruyo la matriz 3x3 ignorando el padding
R_3x3 = np.array([
    [R12[0],  R12[1],  R12[2]],
    [R12[4],  R12[5],  R12[6]],
    [R12[8],  R12[9],  R12[10]],
])
```

### El offset depende del paquete completo

En Wakuseibokan, cada `ModelRecord` del paquete UDP tiene varios campos: número de vehículo, posición, rotación, salud, etc. La matriz R[12] está en algún offset específico. Tenés que mirar la estructura exacta para saber dónde empieza.

Eso lo vamos a ver en detalle cuando lleguemos a la Parte II (implementación), no ahora.

---

## Cómo convertir a cuaternión (la línea mágica)

Con scipy es una línea:

```python
from scipy.spatial.transform import Rotation

q = Rotation.from_matrix(R_3x3).as_quat()  # [x, y, z, w]
```

Listo. Ya tenés el cuaternión listo para alimentar a la red neural.

### Pero antes: canonicalizar

Como vimos en el Concepto 8, `q` y `-q` representan la misma rotación. Hay que canonicalizar:

```python
if q[3] < 0:  # w está en el índice 3 en convención scipy [x, y, z, w]
    q = -q
```

---

## El pipeline completo del agente (una vista de pájaro)

Acá está el código completo, conectando todo lo que aprendiste:

```python
import struct
import numpy as np
from scipy.spatial.transform import Rotation

def process_tick(udp_packet):
    """
    Procesa un paquete UDP de telemetría del Otter y devuelve
    features listos para alimentar a la red neural.
    """

    # 1. Decodificar campos del paquete
    # (estructura del paquete simplificada — la real tiene más campos)
    self_pos    = np.frombuffer(udp_packet, dtype='<f4', count=3, offset=POS_OFFSET)
    R12         = np.frombuffer(udp_packet, dtype='<f4', count=12, offset=ROT_OFFSET)
    self_health = struct.unpack('<f', udp_packet[HEALTH_OFFSET:HEALTH_OFFSET+4])[0]
    enemy_pos   = np.frombuffer(udp_packet, dtype='<f4', count=3, offset=ENEMY_POS_OFFSET)

    # 2. Reconstruir la matriz 3x3 desde R[12] (ignorando padding)
    R_matrix = np.array([
        [R12[0],  R12[1],  R12[2]],
        [R12[4],  R12[5],  R12[6]],
        [R12[8],  R12[9],  R12[10]],
    ])

    # 3. Convertir a cuaternión y canonicalizar
    q = Rotation.from_matrix(R_matrix).as_quat()  # [x, y, z, w]
    if q[3] < 0:
        q = -q

    # 4. Pasar el enemigo a body frame (lo que aprendimos en Concepto 5)
    rel = enemy_pos - self_pos
    enemy_body = R_matrix.T @ rel   # R.T = inversa (porque es ortogonal)

    # 5. Armar el feature vector para la red
    features = np.concatenate([
        self_pos / 1400.0,           # posición world, normalizada
        q,                            # cuaternión (4 floats sin gimbal lock)
        enemy_body / 1400.0,         # enemigo en body frame, normalizado
        [self_health / 1000.0],      # salud normalizada
    ])

    return features
```

**Ese código es esencialmente la primera capa del agente.** Todo lo que viste en los Conceptos 1-8 está acá adentro:

- Línea 2: la **posición** (Concepto 1).
- Líneas 2 y 4: el **vector relativo** y la conversión **world → body** (Concepto 5).
- Línea 3: la **R[12]** decodificada (este concepto).
- Línea 6-10: la **matriz 3×3** reconstruida (Concepto 6, generalizado a 3D).
- Línea 13: la **conversión a cuaternión** (Concepto 8).
- Línea 14-15: la **canonicalización** (Concepto 8).
- Línea 18: la **inversa de la matriz** = transpuesta (Concepto 6).

Todos los conceptos teóricos se materializan en unas 15 líneas de código.

---

## Validación: ¿está bien la matriz que llegó?

Por errores numéricos del simulador o por bugs de red, a veces la matriz que recibís puede estar **levemente corrupta**. Vale la pena chequear:

```python
def validate_rotation_matrix(R, tol=1e-3):
    """Verifica que R sea una matriz de rotación válida."""

    # Test 1: ortogonalidad → R · R.T ≈ identidad
    should_be_I = R @ R.T
    if not np.allclose(should_be_I, np.eye(3), atol=tol):
        return False, "no es ortogonal"

    # Test 2: determinante ≈ +1 (no -1, eso sería rotación con reflejo)
    det = np.linalg.det(R)
    if not np.isclose(det, 1.0, atol=tol):
        return False, f"determinante {det} ≠ +1"

    return True, "ok"
```

Si la matriz está corrupta, podés **renormalizarla** con SVD:

```python
def renormalize(R):
    """Proyecta R a la matriz de rotación más cercana."""
    U, _, Vt = np.linalg.svd(R)
    return U @ Vt
```

En la práctica, las matrices del simulador suelen estar bien y no necesitás esto. Pero conviene tenerlo a mano para debug.

---

## Casos sanity check

Acordate de que la convención del simulador es: yaw=0 → Otter mira al sur. Probá decodificar estos casos conocidos:

| Caso | Matriz esperada | Cuaternión esperado |
|------|-----------------|---------------------|
| Identidad (yaw=0, pitch=0, roll=0) | `[[1,0,0],[0,1,0],[0,0,1]]` | `(1, 0, 0, 0)` |
| Yaw=90° (Otter mira al este) | `[[0,0,1],[0,1,0],[-1,0,0]]` | `(0.707, 0, 0.707, 0)` |
| Yaw=180° (norte) | `[[-1,0,0],[0,1,0],[0,0,-1]]` | `(0, 0, 1, 0)` |

(El cuaternión está en orden `(w, x, y, z)`; recordá que scipy lo devuelve como `(x, y, z, w)`.)

---

## Resumen y cierre de la Parte I

Te dejo un mapa completo de lo que recorriste:

```
                     PARTE I: SISTEMAS DE COORDENADAS
                              Y ROTACIONES
                                    │
                ┌───────────────────┼─────────────────────┐
                │                   │                     │
            COORDENADAS        ROTACIONES 2D         ROTACIONES 3D
                │                   │                     │
        ┌───────┼────────┐     ┌────┼────┐         ┌──────┼──────┐
        ▼       ▼        ▼     ▼    ▼    ▼         ▼      ▼      ▼
       (1)     (2)      (3)   (4)  (5)  (6)       (7)    (8)    (9)
       Coor  Body/   Yaw    Sin  Conv  Matriz   Euler   Cuat   R[12]
        d.   World         /Cos  W↔B    rot 2D    +GL     .       .
                                                          
              └────────────── todo este lenguaje se
                              convierte en código del
                              agente ─────────────────┘
```

**Concretamente, después de estos 9 conceptos podés**:

- Recibir un paquete UDP del simulador y entender qué significa cada byte.
- Decodificar la R[12] correctamente (sabiendo del padding).
- Convertir entre matrices, cuaterniones y Euler con seguridad.
- Saber por qué nunca pasás Euler a la red neural.
- Convertir cualquier punto del world frame al body frame del Otter.
- Pensar en por qué el agente "ve mejor" en body frame.

---

## Lo que viene en la Parte II

Ahora que tenés la base matemática, lo que sigue es:

- **Cinemática del Otter** — cómo se mueve un vehículo Ackermann (4 ruedas con dirección).
- **MDP / Reinforcement Learning** — el formalismo de "estado, acción, recompensa".
- **POMDP** — qué pasa cuando no observás todo el estado (no sabés exactamente dónde está el enemigo).
- **Redes neuronales** — desde lo más básico hasta SAC (Soft Actor-Critic).
- **Opponent modeling** — predecir qué va a hacer el enemigo.

Toda la parte de **toma de decisiones** del agente. La parte de "geometría 3D" ya la dominás.

¡Felicitaciones por llegar hasta acá! Es mucho material y mucha disciplina para hacerlo desde fundamentos.
