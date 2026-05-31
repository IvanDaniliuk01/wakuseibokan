# Concepto 10 — Cinemática del Otter (cómo se mueve cuando le mandás comandos)

> 💡 **Visualización 3D acompañante**: `Concepto 10 - Visualizacion Cinematica.html`
>
> ```bash
> xdg-open "/home/itba/wakuseibokan/docs/entendimiento/Concepto 10 - Visualizacion Cinematica.html"
> ```

---

## Arrancamos la Parte II

Ya tenés todo el lenguaje de coordenadas y rotaciones. Ahora vamos a la parte de **toma de decisiones del agente**. Pero antes de hablar de "qué decisión tomar", tenemos que entender **qué pasa cuando tomás una decisión** — es decir, cómo se mueve físicamente el Otter cuando le mandás un comando.

Este concepto es corto pero importante: si no entendés la cinemática, vas a mandar comandos que no hacen lo que esperás y vas a debuggear ciegamente.

---

## ¿Qué es cinemática?

**Cinemática** = estudio del movimiento **sin importar las fuerzas** que lo causan.

Comparado con **dinámica**, que sí incluye fuerzas:

| | Cinemática | Dinámica |
|--|------------|----------|
| ¿Qué describe? | Posición, velocidad, aceleración | Lo mismo + fuerzas, masas, torques |
| Pregunta típica | "Si me muevo así, ¿dónde voy a estar?" | "Si aplico esta fuerza al Otter, ¿cómo se mueve?" |
| ¿La usamos? | **Sí, mucho** | El simulador ODE la maneja por dentro. Nosotros no necesitamos. |

Para el agente: trabajamos casi siempre con **cinemática**. Las fuerzas las simula ODE; nosotros pensamos en términos de velocidades y posiciones.

---

## Vehículos holonómicos vs no-holonómicos

Esta distinción te va a aparecer en cualquier libro de robótica. Es importante porque define qué puede y qué no puede hacer un vehículo.

### Holonómico

Puede moverse **en cualquier dirección desde el estado quieto**. No tiene restricciones de movimiento.

Ejemplos:
- **Drone** (cuadricóptero): puede moverse al norte, al este, hacia arriba, en diagonal — todo desde quieto.
- **Robot con ruedas omnidireccionales (omniwheels)**: las ruedas mismas pueden deslizar lateralmente.
- **Personaje de videojuego típico**: apretás "arriba" y va al norte instantáneamente.

### No-holonómico

Tiene **restricciones físicas** sobre cómo puede moverse. No puede moverse en cualquier dirección desde quieto.

Ejemplos:
- **Auto**: no puede moverse de costado. Para ir a la derecha tenés que avanzar y doblar.
- **Bicicleta**: igual.
- **El Otter del simulador**: igual.

### ¿Por qué importa la distinción?

Porque cambia **qué políticas son posibles** para el agente. Un dron puede "esquivar lateralmente" una bala. El Otter no — tiene que avanzar y doblar al mismo tiempo.

**Si tu red neural intenta aprender "moverse de costado" sin entender que es no-holonómico, va a fracasar**.

---

## El Otter es un vehículo Ackermann

**Ackermann** = el tipo de configuración de un auto convencional:

```
         ╔════════════════╗
         ║                ║
         ║   ─┐          ┌─ ← ruedas delanteras (steering)
         ║    │          │     orientan según el volante
         ║    │   Otter  │
         ║    │          │
         ║   ─┴──────────┴─ ← ruedas traseras (tracción)
         ║                    siguen rectas, no orientan
         ╚════════════════╝
```

- **Ruedas delanteras**: orientables (steering).
- **Ruedas traseras**: fijas, dan tracción (thrust).
- **Restricciones**:
  - No se puede mover de costado.
  - No se puede girar en el lugar (sin avanzar).
  - Tiene un **radio de giro mínimo** dado por la distancia entre ejes (`wheelbase`).

---

## El bicycle model (la matemática del Ackermann)

Para hacer las cuentas más simples, se usa una simplificación llamada **bicycle model**: asumimos que en lugar de tener 4 ruedas, hay solo 2 (como una bicicleta), una en cada eje:

```
              ╱  ← rueda delantera, orientada con ángulo δ (steering)
             ╱
           ●━━━━━━━━━━━━━━━━●
                                 ← wheelbase L (distancia entre ejes)
                                 ← rueda trasera, fija, da tracción
```

Las variables del modelo:

| Símbolo | Qué es | Unidad |
|---------|--------|--------|
| `x`, `z` | Posición del Otter en world frame | metros |
| `θ` (yaw) | Orientación del Otter | radianes |
| `v` | Velocidad lineal | m/s |
| `δ` | Ángulo de steering (de las ruedas delanteras) | radianes |
| `L` | Wheelbase (distancia entre ejes) | metros |

### Las ecuaciones (las únicas tres que vas a necesitar)

```
dx/dt = v · sin(θ)        ← la velocidad en X depende de v y la dirección
dz/dt = v · cos(θ)        ← la velocidad en Z depende de v y la dirección
dθ/dt = (v / L) · tan(δ)  ← la velocidad angular depende de v, L y steering
```

(Recordá: convención del simulador, `forward = +Z` cuando yaw=0. La fórmula es consistente con `forward_W = (sin(yaw), 0, cos(yaw))` del Concepto 4.)

### Qué te dicen estas ecuaciones

**Lo más importante**: la **velocidad angular** (cuán rápido gira el Otter) depende de la velocidad lineal `v`.

```
dθ/dt = (v / L) · tan(δ)
```

Si `v = 0` (Otter parado), `dθ/dt = 0` — **el Otter no puede girar parado**. Sí podés cambiar el ángulo de las ruedas delanteras, pero el Otter no rota hasta que empiece a moverse.

Esto es **muy distinto** a un dron, donde podés rotar sin trasladarte.

### Radio de giro mínimo

```
R_min = L / tan(δ_max)
```

Si las ruedas máximo se pueden orientar a 30°, y la wheelbase es 2 metros:

```
R_min = 2 / tan(30°) ≈ 3.5 metros
```

El Otter no puede hacer un círculo más cerrado que 3.5 metros de radio. Esto importa porque significa que **no puede pasar por gaps angostos** sin maniobras complejas.

---

## Los comandos que le mandás al Otter en Wakuseibokan

Recordá el `ControlStructure2` (del plan original):

| Comando | Rango | Qué hace |
|---------|-------|----------|
| `thrust` | [-1, 1] | Aceleración: positivo = adelante, negativo = atrás |
| `steering` | [-1, 1] | Ángulo de las ruedas delanteras: positivo = un lado, negativo = el otro |
| `turret_bearing` | [-π, π] | Hacia dónde apunta la torreta (independiente del cuerpo) |
| `turret_declination` | [0, π/2] | Elevación de la torreta (0 = horizontal, π/2 = vertical) |
| `fire` | bool | Disparar el cañón |

Notá dos cosas:

1. **La torreta es independiente del cuerpo**. El Otter puede ir hacia un lado y apuntar hacia otro al mismo tiempo. Esto es un grado extra de libertad muy útil para el combate.
2. **Thrust y steering NO son posición/orientación deseada** — son **velocidades** (o más bien, comandos que se traducen a velocidades vía ODE). Si querés que el Otter llegue a `(100, 0, 100)_W`, no podés simplemente "mandar esa posición". Tenés que descomponer en una secuencia de thrust + steering.

---

## Implicancias prácticas para el agente

### Implicancia 1: La red neural va a aprender la cinemática sola... si la dejás

Si entrenás con RL desde cero, la red eventualmente aprende que "para ir al norte cuando estoy mirando al este, hay que doblar a la izquierda". Pero esto **toma muchas iteraciones**. Puede tardar miles de episodios solo para descubrir lo básico.

**Por eso a veces conviene "warm-start" con imitation learning**: grabás episodios de un controlador scripted (que ya sabe cinemática) y entrenás la red para imitarlo. Después fine-tuneás con RL.

### Implicancia 2: Reward shaping consciente de cinemática

Si tu reward es solo "llegar al objetivo", el agente puede frustrarse porque el camino más corto (línea recta) **no es alcanzable** si requiere movimiento lateral.

Mejor: rewardear acciones que aprovechen la cinemática (alinear morro con objetivo, después avanzar; mantener velocidad alta cuando el path es recto; reducir velocidad antes de doblar).

### Implicancia 3: Acciones discretas vs continuas

Algunos algoritmos de RL trabajan con acciones discretas ("adelante", "izquierda", "derecha", "frenar"). Otros con continuas (thrust ∈ [-1, 1]).

Para el Otter, **continuas son mejores** porque el control suave produce trayectorias más eficientes. SAC (que vamos a usar) maneja acciones continuas nativamente.

### Implicancia 4: La torreta es UN grado de libertad extra

Pensá esto: cuerpo y torreta pueden apuntar en direcciones distintas. El agente puede:

- Huir (cuerpo hacia atrás) mientras dispara (torreta hacia adelante al enemigo).
- Patrullar lateralmente (cuerpo de lado) mientras la torreta barre 360°.

**Esto agrega complejidad pero también capacidad estratégica**. Es lo que separa al Otter de un dron de combate convencional.

---

## Probá la visualización

En el HTML acompañante vas a ver el Otter en una arena vacía. Hay 2 sliders:

- **Thrust** (-1 a 1): adelante / atrás.
- **Steering** (-1 a 1): izquierda / derecha de las ruedas delanteras.

El Otter se mueve continuamente según los valores actuales. Verás:

- **Estela amarilla** (trail): la trayectoria que va dejando. Te muestra visualmente el efecto cinemático.
- **Display de velocidad, yaw, y radio de giro instantáneo**.

### Lo importante para experimentar

1. **Thrust=1, Steering=0**: Otter va recto. La estela es una línea.
2. **Thrust=1, Steering=0.5**: Otter va describiendo un círculo. Mirá la estela.
3. **Thrust=0.5, Steering=0.5**: Otter va describiendo un círculo **más pequeño** que el anterior. El radio depende de `v / tan(δ)`... no, depende solo de `tan(δ)` para la curvatura, pero la **velocidad angular** (qué rápido completa el círculo) sí depende de v.

   Wait — geométricamente el radio es `L / tan(δ)`, **independiente de v**. Pero el tiempo para completar el círculo sí depende de v.

4. **Thrust=0, Steering=cualquiera**: Otter **no rota**. Aunque las ruedas delanteras estén giradas, sin velocidad no hay rotación.
5. **Thrust=-1, Steering=0.5**: Otter retrocede mientras dobla. **El sentido del giro se invierte** con la velocidad negativa (como en un auto cuando hacés marcha atrás torcido).

---

## En código real

```python
import math

class OtterKinematics:
    def __init__(self, wheelbase=2.0):
        self.L = wheelbase
        self.x = 0
        self.z = 0
        self.yaw = 0
        self.v = 0

    def step(self, thrust, steering, dt=0.02):
        """
        Avanza el Otter dt segundos con los comandos dados.
        thrust ∈ [-1, 1], steering ∈ [-1, 1]
        """
        # Simplificación: thrust se traduce directo a velocidad
        # (en la realidad ODE simula aceleración, masa, fricción)
        target_v = thrust * 20.0  # 20 m/s velocidad máxima
        self.v += (target_v - self.v) * 0.1  # suavizado

        # Steering se traduce a ángulo de ruedas
        delta = steering * math.radians(30)  # máximo 30°

        # Bicycle model
        self.x += self.v * math.sin(self.yaw) * dt
        self.z += self.v * math.cos(self.yaw) * dt
        self.yaw += (self.v / self.L) * math.tan(delta) * dt

        return self.x, self.z, self.yaw
```

**Esto es una SIMULACIÓN simplificada de la cinemática** — el simulador real (ODE) calcula esto con fricción, masa, terreno irregular, colisiones, etc. Pero esta versión te da una intuición correcta del comportamiento.

---

## Resumen para llevarse

| Concepto | Qué es |
|----------|--------|
| **Cinemática** | Estudio del movimiento (posición, velocidad) sin fuerzas. |
| **Holonómico** | Puede moverse en cualquier dirección desde quieto. Drone, omniwheels. |
| **No-holonómico** | Tiene restricciones. Auto, Otter, bicicleta. |
| **Ackermann** | Config de 4 ruedas: delanteras orientables (steering), traseras tracción (thrust). |
| **Bicycle model** | Simplificación a 2 ruedas, con ecuaciones cerradas. Lo que usamos para razonar. |
| **Comandos del Otter** | `thrust`, `steering`, `turret_bearing`, `turret_declination`, `fire`. |
| **Restricción clave** | Sin velocidad lineal NO hay rotación del cuerpo. |
| **Torreta independiente** | El Otter puede apuntar a un lado y moverse a otro. |

---

## Lo que viene después

- **Concepto 11**: **MDP** — el formalismo del reinforcement learning. Estado, acción, reward, política. La base de todo lo que viene en RL.
- Después: bucle de RL, redes neuronales, SAC, POMDP, y al final el pipeline completo del agente.
