# Concepto 4 — Seno y coseno (las componentes de una rotación)

> 💡 **Visualización 3D acompañante**: `Concepto 4 - Visualizacion Seno Coseno.html`
>
> ```bash
> xdg-open "/home/itba/wakuseibokan/docs/entendimiento/Concepto 4 - Visualizacion Seno Coseno.html"
> ```

---

## ¿Por qué necesitamos seno y coseno?

En el Concepto 3 aprendimos a describir hacia dónde mira el Otter con un solo número: el **yaw**. Eso está bien para **describir**, pero todavía no sabemos cómo **usarlo para hacer cuentas**.

Ejemplo concreto: si el Otter mira a **yaw = 45°** (sureste), querés saber:

> *¿Cuánto del "adelante del Otter" es hacia el este y cuánto es hacia el sur?*

Intuitivamente, mitad y mitad — pero ¿cómo lo calculás exactamente? Si el yaw fuera 30°, ¿cuánto va al este y cuánto al sur? Necesitás una herramienta que te diga, para cualquier ángulo, **las componentes en cada eje**.

**Esa herramienta son seno y coseno.**

---

## Refresco: ¿qué es una función?

Una **función** en matemática es una regla que toma un número de entrada y te da un número de salida. Una caja con una boquilla de entrada y una boquilla de salida:

```
        ┌─────────────┐
   x ──▶│  función f  │──▶ f(x)
        └─────────────┘
```

Ejemplos del colegio:
- `f(x) = 2x` → si entrás 3, sale 6.
- `g(x) = x²` → si entrás 4, sale 16.

El **seno** y el **coseno** son funciones que toman un **ángulo** como entrada y devuelven un **número entre -1 y 1**:

```
        ┌─────────────┐
  ángulo ──▶│   seno   │──▶ número entre -1 y 1
        └─────────────┘

        ┌─────────────┐
  ángulo ──▶│  coseno  │──▶ número entre -1 y 1
        └─────────────┘
```

**Lo importante no es la definición formal todavía. Lo importante es entender que dado un ángulo te devuelven números útiles.** Esos números son las "componentes" que vamos a usar.

---

## La definición del colegio: el triángulo rectángulo

Si lo viste alguna vez en secundario, te sonará. Lo refresco en 30 segundos. **Si no te sonó nada, no importa**, saltá a la siguiente sección donde explico la definición que vamos a usar de verdad.

Dado un triángulo rectángulo (uno de cuyos ángulos es de 90°):

```
            ╱│
           ╱ │
          ╱  │
 hipo-   ╱   │  cateto
 tenusa ╱    │  opuesto
       ╱     │
      ╱      │
     ╱_______│
       θ
    cateto adyacente
```

- **Hipotenusa**: el lado más largo (el que está enfrente del ángulo recto).
- **Cateto opuesto**: el lado que está enfrente del ángulo θ.
- **Cateto adyacente**: el lado que está junto al ángulo θ (que no es la hipotenusa).

Las definiciones:

| | Fórmula | Regla mnemotécnica |
|--|---------|--------------------|
| **seno(θ)** | opuesto / hipotenusa | **SOH** |
| **coseno(θ)** | adyacente / hipotenusa | **CAH** |
| **tangente(θ)** | opuesto / adyacente | **TOA** |

Esta definición funciona bien para ángulos entre 0° y 90°. Pero el Otter va a tener yaw de 180°, -90°, 270°... y esta definición no aplica directamente.

**Por eso usamos otra definición, más general:** el círculo unitario.

---

## La definición que usamos: el círculo unitario

Imaginá un círculo de **radio 1** centrado en el origen del plano XZ:

```
              Z
              │
              │     (en este Concepto, ignoramos Y porque
            1 ●     trabajamos en el plano del piso)
              │
       ┌──────┼──────┐
       │      │      │
       │      │      │   ← círculo de radio 1
       │      │      │
       ●──────●──────●──── X
       -1     │     +1
              │
            -1●
              │
```

Ahora hacé esto:

1. Trazá una flecha desde el origen, de longitud 1, con un ángulo θ a partir del eje +Z (la dirección de referencia — yaw=0).
2. La flecha termina en un punto del círculo.
3. **Las coordenadas (X, Z) de ese punto son exactamente (sin(θ), cos(θ)).**

```
              Z
              │
              │       
              │       
              │    ●  ← punto en (sin θ, cos θ)
              │   ╱│
              │  ╱ │
              │ ╱  │ cos(θ)  ← coordenada Z
              │╱θ  │
       ───────●────●──── X
              │ sin(θ)  ← coordenada X
              │
              │
```

**Eso es todo.** Seno y coseno son las **coordenadas** del punto donde termina una flecha de longitud 1 que rotaste un ángulo θ.

### ¿Por qué esta definición es mejor?

Funciona para **cualquier ángulo**:
- En el primer cuadrante (0° < θ < 90°) → ambas componentes son positivas.
- En el segundo cuadrante (90° < θ < 180°) → sin es positivo, cos es negativo.
- En el tercer cuadrante (180° < θ < 270°) → ambas son negativas.
- En el cuarto cuadrante (270° < θ < 360°) → sin es negativo, cos es positivo.

Y vale para ángulos negativos, mayores a 360°, etc.

---

## La fórmula clave para el Otter

Si el Otter está apuntando con yaw = θ, entonces su **vector "hacia adelante"** (forward, +Z_B) expresado en world coords es:

```
forward_W = ( sin(yaw),  0,  cos(yaw) )
```

Esto es **la pieza más importante de toda esta sección**. Memorizala. Es lo que vas a usar todo el tiempo.

Si querés escalar el vector a un largo R (por ejemplo, para apuntar a 100 metros adelante en vez de a 1 metro):

```
forward_W = ( R · sin(yaw),  0,  R · cos(yaw) )
```

### Verificación con casos conocidos

| yaw | sin(yaw) | cos(yaw) | forward_W | Tiene sentido? |
|-----|----------|----------|-----------|----------------|
| 0° (sur) | 0 | 1 | (0, 0, 1) | ✓ todo Z, nada de X |
| 90° (este) | 1 | 0 | (1, 0, 0) | ✓ todo X, nada de Z |
| 180° (norte) | 0 | -1 | (0, 0, -1) | ✓ Z negativo (norte) |
| -90° (oeste) | -1 | 0 | (-1, 0, 0) | ✓ X negativo (oeste) |
| 45° (sureste) | 0.707 | 0.707 | (0.707, 0, 0.707) | ✓ mitad X mitad Z (diagonal) |

**Para el caso 45°, fijate que las dos componentes son iguales (≈ 0.707)**. Eso es porque el Otter está apuntando exactamente en la diagonal entre el sur y el este → la flecha tiene la misma cantidad de "este" que de "sur".

---

## Probá la visualización

Abrí el HTML y vas a ver:

- El Otter en el centro, rotando con el slider de yaw.
- La **flecha amarilla** que sale del Otter (longitud 100) en la dirección de su morro.
- Un **triángulo rectángulo dibujado en el piso**:
  - **Cateto rojo** sobre el eje X: longitud = `sin(yaw) · 100`. Esto es **cuánto de "este" tiene el vector forward**.
  - **Cateto azul** paralelo al eje Z: longitud = `cos(yaw) · 100`. Esto es **cuánto de "sur" tiene el vector forward**.
  - **Hipotenusa amarilla** = la propia flecha forward (longitud 100 siempre).
- Un display lateral con los valores numéricos de seno, coseno y las componentes X y Z.

### Cosas que tenés que probar

1. **Movelo a yaw = 0°**. Vas a ver:
   - El cateto rojo (X) tiene longitud 0 → desaparece.
   - El cateto azul (Z) tiene longitud 100 → coincide con la flecha forward.
   - sin(0°) = 0, cos(0°) = 1.
2. **Movelo a yaw = 90°**. Pasa lo opuesto:
   - El cateto rojo (X) tiene longitud 100.
   - El cateto azul (Z) tiene longitud 0.
   - sin(90°) = 1, cos(90°) = 0.
3. **Movelo a yaw = 45°**. Vas a ver el triángulo "balanceado":
   - Los dos catetos tienen la misma longitud (≈ 70.7).
   - sin(45°) ≈ 0.707, cos(45°) ≈ 0.707.
4. **Movelo a yaw = 180°**. El cateto azul "se invierte" (queda negativo, dibujado al norte).
   - cos(180°) = -1.
   - El concepto de "componente negativa" significa: la dirección es opuesta al eje de referencia.

---

## Valores que vale la pena saber de memoria

Estos aparecen una y otra vez. Memorizalos si podés:

| θ | sin(θ) | cos(θ) |
|---|--------|--------|
| 0° | 0 | 1 |
| 30° | 0.5 | 0.866 |
| 45° | 0.707 | 0.707 |
| 60° | 0.866 | 0.5 |
| 90° | 1 | 0 |
| 180° | 0 | -1 |
| 270° (o -90°) | -1 | 0 |

**Truco mnemotécnico**: para 0°, 30°, 45°, 60°, 90° los valores del seno son `√0/2, √1/2, √2/2, √3/2, √4/2` → siempre raíz de algo, sobre 2. Y el coseno es la lista al revés.

---

## En código real (cómo se escribe en Python)

Cuando programes, vas a hacer esto todo el tiempo:

```python
import math

yaw_deg = 45
yaw_rad = math.radians(yaw_deg)  # convertí grados a radianes!

forward_x = math.sin(yaw_rad)
forward_z = math.cos(yaw_rad)

print(f"forward = ({forward_x:.3f}, 0, {forward_z:.3f})")
# forward = (0.707, 0, 0.707)
```

**Recordá el detalle más importante**: las funciones `math.sin` y `math.cos` esperan **radianes**, no grados. Si le pasás 45 esperando "cuarenta y cinco grados", te va a calcular sin(45 radianes) que es un número totalmente distinto. Por eso siempre conviene convertir con `math.radians()` primero.

---

## Tres preguntas que suelen aparecer (preguntas reales del estudio)

### 1. ¿Qué es R y en qué unidades?

**R es solamente la longitud del vector** — vos elegís qué representa según para qué lo uses. No tiene una unidad fija, es solo un número que **escala** las componentes seno y coseno.

Casos típicos:

| Si R vale... | El vector representa... | Unidad |
|--------------|-------------------------|--------|
| 1 | Una **dirección pura** (vector unitario, sin tamaño) | sin unidad |
| 100 | "100 metros adelante del Otter" | metros |
| 30 | "El Otter avanza 30 m/s en esa dirección" | metros / segundo |
| Distancia al enemigo | "Posición del enemigo a partir del Otter" | metros |

Pensalo así: **sin y cos te dicen "qué proporción del vector va en cada eje"** (siempre entre -1 y 1). **R te dice "qué tan largo es el vector"**. Multiplicás los dos y obtenés las componentes reales.

```
sin(45°) = 0.707         ← proporción que va al eje X
cos(45°) = 0.707         ← proporción que va al eje Z

Si R = 100 metros:
  componente X = 0.707 × 100 = 70.7 metros al este
  componente Z = 0.707 × 100 = 70.7 metros al sur
```

En Wakuseibokan las distancias están en **unidades del simulador que se interpretan como metros** (ODE trabaja en SI por defecto). Así que en la práctica para nosotros R va a ser "metros" casi siempre.

---

### 2. ¿Sin y cos nos dicen cuánto de X y cuánto de Y a partir de una rotación?

**La idea es exactamente esa, sí.** Pero ojo con un detalle de nuestra convención:

En matemática general te enseñan el círculo unitario en el plano **XY**, donde X es horizontal e Y es vertical. Ahí sí seno y coseno te dan "cuánto de X y cuánto de Y".

En **nuestro caso**, el plano del piso es **X-Z** (porque Y es la altura, el eje vertical). Entonces seno y coseno te dan:

- **cuánto de X** (este-oeste)
- **cuánto de Z** (sur-norte)

Y la componente Y (altura) se queda igual, porque el yaw solo rota alrededor del eje vertical — no levanta ni hunde el vector.

Tu intuición es 100% correcta, solo cambiá "Y" por "Z" en la cabeza cuando estés trabajando en este simulador.

---

### 3. ¿Esta rotación es desde el punto de vista del body frame?

Esta es **la pregunta más fina** de las tres y vale la pena desarmarla con cuidado, porque tiene tres lecturas posibles que se confunden fácil.

#### Las tres preguntas escondidas

| Pregunta | Respuesta |
|----------|-----------|
| **¿Quién** rota? | El **body** del Otter (su cuerpo físico) |
| **¿Respecto a qué** se mide el ángulo? | Respecto al **world** (el eje +Z_W = sur es la referencia, yaw=0) |
| **¿En qué frame** están las componentes (sin·R, cos·R) que obtenemos? | En el **world frame** |

Las tres son verdad al mismo tiempo. Si decís solo "la rotación es del body" o solo "es del world", te dejás una parte afuera. **La fórmula `forward_W = (sin(yaw), 0, cos(yaw))` está conectando los dos frames.**

#### Lo que en realidad estás haciendo (esto anticipa el Concepto 5)

La operación que hace seno y coseno es una **conversión body → world** de un vector específico: el vector "adelante" del Otter.

En body frame, el vector forward es siempre el mismo número trivial:

```
forward_B = (0, 0, R)_B    ← "R unidades en mi dirección +Z_B (morro)"
```

En body, no importa cómo esté rotado el Otter — su morro siempre es `(0, 0, R)_B` para él mismo. Es lo mismo que te dije en el Concepto 3: "mi adelante está adelante mío". Es trivial en body.

Lo que seno y coseno hacen es **traducir** ese vector trivial body al mundo:

```
forward_B = (0, 0, R)_B   ─────traducción────▶   forward_W = (R·sin(yaw), 0, R·cos(yaw))_W
                            (usando el yaw)
```

**El yaw es la "instrucción de traducción"** entre los dos frames. Sin el yaw no podés convertir, porque no sabés cómo está orientado el body respecto al world.

#### Por qué importa este detalle

Esta es exactamente la operación que vamos a generalizar en el **Concepto 5**. Ahí no vamos a convertir solo el vector forward (el morro del Otter), sino **cualquier punto** entre body y world. La idea es la misma — usar seno y coseno con el yaw — pero aplicada a algo más útil: por ejemplo, "el enemigo está en `(0, 0, -100)_W`, ¿dónde está en body frame, desde el punto de vista del Otter?".

---

## Resumen para llevarse

| Concepto | Qué es |
|----------|--------|
| **Función** | Una regla que toma un número y devuelve otro. |
| **sin(θ)** | Componente perpendicular a la referencia. Para el Otter: componente X (este-oeste). |
| **cos(θ)** | Componente alineada con la referencia. Para el Otter: componente Z (sur-norte). |
| **R** | La longitud del vector. Solo escala. Unidades = las que vos elijas (metros, m/s, etc.). |
| **Círculo unitario** | La definición moderna: sin y cos son las coordenadas del punto donde apunta una flecha de longitud 1 rotada un ángulo θ. |
| **Fórmula del Otter** | `forward_W = (sin(yaw), 0, cos(yaw))` — esto es una **conversión body → world** del vector forward. |
| **En Python** | `math.sin(radianes)`, `math.cos(radianes)`. **Siempre radianes, nunca grados.** |

---

## Lo que viene después

Ya tenemos todas las piezas:
- Sabemos qué es world y body frame (Concepto 2).
- Sabemos describir la orientación con un yaw (Concepto 3).
- Sabemos descomponer ese yaw en componentes con seno y coseno (Concepto 4).

En el próximo:

- **Concepto 5**: la conversión **completa** de un punto entre world y body frame, usando seno y coseno. Ya con cuentas concretas, no solo intuiciones. Esto es lo que va a usar el agente en cada tick para "pensar en su propio cuerpo".

Después de eso pasamos a matrices (Concepto 6), que es como aparece en el código real del simulador. Pero el corazón de la idea va a estar acá: rotar un vector usando sin y cos.
