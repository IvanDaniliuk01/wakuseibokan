# Concepto 5 — Conversión completa entre frames (cualquier punto, en 2D)

> 💡 **Visualización 3D acompañante**: `Concepto 5 - Visualizacion Conversion.html`
>
> ```bash
> xdg-open "/home/itba/wakuseibokan/docs/entendimiento/Concepto 5 - Visualizacion Conversion.html"
> ```

---

## Lo que ya sabíamos hasta acá

En el Concepto 4 hicimos una conversión: tomamos el **morro del Otter** (que en body siempre es `(0, 0, R)_B`) y lo expresamos en world frame con la fórmula:

```
forward_W = (R · sin(yaw), 0, R · cos(yaw))
```

Pero el morro del Otter es un caso **muy especial**: empieza siempre en el origen del body y siempre apunta a +Z_B. Lo único que cambia es R.

**En la realidad vas a querer convertir cualquier punto**, no solo el morro. Por ejemplo:

- El simulador te dice "el enemigo está en `(120, 0, -80)_W`". Vos querés saber "¿dónde está respecto a mí, el Otter, según mis propios ejes?" → necesitás world → body.
- Vos decidís "me quiero mover 30 metros adelante y 10 a mi derecha". Eso es un punto en body. Pero el simulador necesita un comando en world → necesitás body → world.

**Las dos conversiones usan la misma fórmula**, solo que en sentidos opuestos. Vamos a derivarlas.

---

## El problema, descompuesto en dos pasos

Imaginá que el Otter está en `(50, 0, 30)_W`, rotado con yaw = 45°, y querés saber dónde está la warehouse — que en world está en `(200, 0, -70)_W` — desde el punto de vista del Otter.

La conversión world → body se hace en **dos pasos**:

### Paso A: Traslación (mover el origen al Otter)

Primero le restás al punto la posición del Otter. Eso te da el **vector relativo**: cuánto tendrías que moverte desde el Otter para llegar al punto, **medido todavía con los ejes del world**.

```
dx = warehouse.x − otter.x = 200 − 50 = 150
dy = warehouse.y − otter.y = 0 − 0   = 0
dz = warehouse.z − otter.z = −70 − 30 = −100
```

El vector relativo es `(150, 0, -100)_W`. Esto te dice: "la warehouse está 150 unidades al este y 100 unidades al norte de donde está el Otter".

**Esto todavía NO es body frame** — los ejes que usamos siguen siendo los del world (este, sur, etc.). Solo movimos el "punto desde donde se mide" al Otter.

### Paso B: Rotación (rotar los ejes para alinearlos con el body)

Ahora hay que **expresar el mismo vector relativo en los ejes del body**. Acordate que los ejes del body están rotados un ángulo `yaw` respecto al world.

La fórmula que vimos en el Concepto 4 era para rotar **de body a world**. Acá necesitamos lo opuesto. Resulta que la conversión world → body de un vector relativo `(dx, 0, dz)` es:

```
x_B = dx · cos(yaw) − dz · sin(yaw)
z_B = dx · sin(yaw) + dz · cos(yaw)
```

(la componente Y no cambia porque el yaw solo rota en el plano del piso).

Aplicado al ejemplo (yaw = 45°, sin(45°) = cos(45°) ≈ 0.707):

```
x_B = 150 · 0.707 − (−100) · 0.707 = 150·0.707 + 100·0.707 = 250 · 0.707 ≈ 176.8
z_B = 150 · 0.707 + (−100) · 0.707 = 50 · 0.707 ≈ 35.4
```

Resultado: **la warehouse está en `(176.8, 0, 35.4)_B`** desde el punto de vista del Otter. Es decir: 176.8 unidades en la dirección +X_B y 35.4 unidades adelante (en +Z_B).

---

## Las dos fórmulas, una al lado de la otra

Tenelas a mano. Son las dos operaciones fundamentales de cualquier agente robótico.

### World → Body (la más usada)

> *"El simulador me dice dónde está algo en el mapa. ¿Cómo lo veo yo, desde mi cabeza?"*

```
dx = punto.x − otter.x           ← Paso A: traslación
dz = punto.z − otter.z

x_B = dx · cos(yaw) − dz · sin(yaw)    ← Paso B: rotación
z_B = dx · sin(yaw) + dz · cos(yaw)
y_B = punto.y − otter.y                ← Y no se rota con yaw
```

### Body → World (la inversa)

> *"Quiero ir 30m adelante y 10m a mi costado. ¿A qué coordenada del mapa tengo que ir?"*

```
x_W_rel = x_B · cos(yaw) + z_B · sin(yaw)   ← Paso B inverso: rotación opuesta
z_W_rel = −x_B · sin(yaw) + z_B · cos(yaw)

punto.x = otter.x + x_W_rel              ← Paso A inverso: trasladar de vuelta
punto.z = otter.z + z_W_rel
punto.y = otter.y + y_B
```

**Notá la simetría**: solo cambian los signos del seno. Eso es porque rotar `+yaw` en una dirección y `−yaw` en la otra son operaciones inversas.

---

## Verificación con casos conocidos

Antes de avanzar, verifiquemos que las fórmulas funcionan con casos que ya entendemos bien.

### Caso 1: Otter en el origen, yaw = 0°, warehouse al norte

- `otter = (0, 0, 0)_W`
- `warehouse = (0, 0, -100)_W` (norte)
- yaw = 0° → sin(0°) = 0, cos(0°) = 1

Cálculo:
```
dx = 0 − 0 = 0
dz = −100 − 0 = −100
x_B = 0 · 1 − (−100) · 0 = 0
z_B = 0 · 0 + (−100) · 1 = −100
```

Resultado: `(0, 0, -100)_B`. ✓ Coincide con lo que ya sabíamos del Concepto 2: la warehouse está detrás del Otter (Z negativo en body = atrás del morro).

### Caso 2: Mismo setup pero el Otter mira al este

- yaw = 90° → sin(90°) = 1, cos(90°) = 0

Cálculo:
```
dx = 0, dz = −100
x_B = 0 · 0 − (−100) · 1 = 100
z_B = 0 · 1 + (−100) · 0 = 0
```

Resultado: `(100, 0, 0)_B`. ✓ Coincide con lo que veíamos en la visualización del Concepto 2 (la warehouse está al costado del Otter, sobre el eje X_B).

---

## Por qué esto es el corazón del agente

Cada tick (cada 20 milisegundos) el simulador te va a mandar la posición de todo en world frame. Lo primero que va a hacer tu código, **siempre**, es convertir todo a body frame:

```python
# Pseudocódigo del agente
def each_tick(telemetry):
    otter_pos = telemetry.self_pos
    otter_yaw = extract_yaw(telemetry.self_R)
    enemy_pos_W = telemetry.enemy_pos
    
    # Conversión world → body del enemigo
    dx = enemy_pos_W[0] - otter_pos[0]
    dz = enemy_pos_W[2] - otter_pos[2]
    enemy_x_B = dx * cos(otter_yaw) - dz * sin(otter_yaw)
    enemy_z_B = dx * sin(otter_yaw) + dz * cos(otter_yaw)
    
    # Ahora la red neural decide qué hacer:
    # "enemy_z_B positivo grande" = está adelante mío → avanzo
    # "enemy_x_B positivo grande" = está a mi costado X_B → giro hacia ahí
    action = policy(enemy_x_B, enemy_z_B, ...)
    return action
```

**La red neural piensa en body frame**. Eso la hace **invariante a la rotación**: no importa hacia dónde esté mirando el Otter, "el enemigo adelante a la derecha" siempre significa lo mismo. Si la red recibiera coordenadas world, tendría que aprender a interpretar cada combinación posible de orientación, lo cual sería muchísimo más difícil.

---

## Probá la visualización

Abrí el HTML acompañante y vas a ver:

- El Otter en el centro (movible con sliders).
- Una warehouse en algún punto (también movible).
- **Una flecha naranja punteada** del Otter a la warehouse: este es el **vector relativo** en world coords (después del Paso A: traslación).
- **Un triángulo rectángulo descompuesto en ejes del BODY**:
  - **Cateto rojo** en dirección **+X_B** del Otter, con longitud `x_B`.
  - **Cateto azul** en dirección **+Z_B** del Otter, con longitud `z_B`.
  - Los dos catetos suman vectorialmente para llegar de la warehouse.
- El panel derecho te muestra los **6 números clave**: posición de cada uno en world, vector relativo, y posición de la warehouse en body.

### Lo importante que tenés que ver

- **Mové solo el yaw del Otter** (sin mover posiciones). La warehouse en world NO cambia (los inputs del Paso A son iguales), pero la warehouse en body SÍ cambia (porque los ejes body rotaron en el Paso B). El triángulo rojo/azul se reorienta.
- **Mové solo la posición del Otter** (sin tocar el yaw). El vector relativo cambia (cambia el dx, dz), y por lo tanto las coords body también cambian — pero la **orientación** del triángulo body queda igual.
- **Probá el preset "Caso 1" y "Caso 2"** para verificar los ejemplos numéricos del documento.

---

## Trampa frecuente: el orden de las operaciones

Es **crucial** que sigas el orden **traslación → rotación** (cuando vas de world a body) y **rotación → traslación** (cuando vas de body a world). Si los hacés al revés, te da números totalmente equivocados.

¿Por qué? Imaginá que primero rotás y después trasladás:

1. Rotás el punto (200, 0, -70)_W por -45° alrededor del origen del world → el punto va a otro lugar arbitrario.
2. Después le restás la posición del Otter.

Esto no tiene sentido porque la rotación se hace **alrededor del origen del Otter**, no del origen del world. La traslación primero "pone el origen en el Otter", y después la rotación gira "alrededor del Otter".

**Regla mnemotécnica**: cuando vas a body, lo primero que tenés que hacer es **ponerte en el lugar del Otter** (traslación). Después podés mirar para donde mira el Otter (rotación).

---

## En código real (Python)

```python
import math

def world_to_body(point_W, otter_pos, otter_yaw_rad):
    """Convierte un punto de world frame a body frame del Otter."""
    # Paso A: traslación
    dx = point_W[0] - otter_pos[0]
    dy = point_W[1] - otter_pos[1]
    dz = point_W[2] - otter_pos[2]
    
    # Paso B: rotación
    c = math.cos(otter_yaw_rad)
    s = math.sin(otter_yaw_rad)
    x_B = dx * c - dz * s
    z_B = dx * s + dz * c
    y_B = dy
    
    return (x_B, y_B, z_B)


def body_to_world(point_B, otter_pos, otter_yaw_rad):
    """Convierte un punto de body frame a world frame."""
    # Paso B inverso: rotación opuesta
    c = math.cos(otter_yaw_rad)
    s = math.sin(otter_yaw_rad)
    x_rel = point_B[0] * c + point_B[2] * s
    z_rel = -point_B[0] * s + point_B[2] * c
    y_rel = point_B[1]
    
    # Paso A inverso: trasladar de vuelta
    x_W = otter_pos[0] + x_rel
    y_W = otter_pos[1] + y_rel
    z_W = otter_pos[2] + z_rel
    
    return (x_W, y_W, z_W)


# Verificación: ida y vuelta debería dar lo original
original = (200, 0, -70)
otter = (50, 0, 30)
yaw = math.radians(45)

b = world_to_body(original, otter, yaw)
w = body_to_world(b, otter, yaw)
print(b)              # (176.8, 0, 35.4)
print(w)              # (200, 0, -70) ← idéntico al original
```

---

## Resumen para llevarse

| Concepto | Qué es |
|----------|--------|
| **Conversión world → body** | Dos pasos: trasladar (restar otter_pos) y rotar (con sin y cos del yaw). |
| **Conversión body → world** | Inversa: rotar (con signos opuestos) y trasladar (sumar otter_pos). |
| **Vector relativo** | El resultado del Paso A: punto menos otter_pos. Está medido con ejes del world, no es body todavía. |
| **Orden importa** | World → body: traslación primero. Body → world: rotación primero. |
| **Y no cambia con yaw** | La componente vertical es invariante ante una rotación de yaw. |
| **Para qué sirve** | Es la primera operación de cada tick del agente. Convertís todo a body para que la red neural piense en términos del Otter. |

---

## Lo que viene después

- **Concepto 6**: la **matriz de rotación 2D** — una forma compacta de escribir las dos fórmulas de seno/coseno usando una "tabla" de 4 números. No es magia nueva: es notación más concisa para lo que ya sabés.
- **Concepto 7**: rotaciones 3D completas. El Otter no solo rota en el piso (yaw): también puede inclinarse al subir una pendiente (pitch) o ladearse al volcar (roll). Ahí aparece el problema del **gimbal lock**.
- **Concepto 8**: **cuaterniones**, la representación de rotación 3D que va a recibir la red neural (porque evita gimbal lock y es más estable matemáticamente).
- **Concepto 9**: cómo se decodifica la **matriz R[12]** que llega por UDP del simulador en cada tick.
