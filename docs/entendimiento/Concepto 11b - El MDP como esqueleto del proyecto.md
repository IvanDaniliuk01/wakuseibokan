# Concepto 11b — El MDP como esqueleto del proyecto Physical AI

> 📌 Extensión profunda del Concepto 11. Mientras el Concepto 11 te dio el formalismo abstracto, este te muestra **cómo el MDP es la columna vertebral concreta del agente Otter**. Cada decisión de diseño que vamos a tomar en lo que queda del proyecto va a estar enmarcada en los 5 ingredientes del MDP.

---

## Por qué el MDP es la columna vertebral

### Idea central

El MDP no es solo "una forma de describir el problema". Es **el lenguaje en el que están escritos**:

1. **Todos los algoritmos de RL** (DQN, PPO, SAC, etc.) suponen MDP.
2. **Toda decisión de diseño** se traduce a "agregar/cambiar algo en S, A, R, P o γ".
3. **Todos los conceptos avanzados** (POMDP, self-play, opponent modeling, imitation learning, belief state) son **extensiones o variantes** del MDP.

Si vos pensás claramente en términos de "¿qué estoy cambiando en S? ¿qué en R?", todas las decisiones del proyecto se ordenan. Si no, vas a tomar decisiones intuitivas que se contradicen entre sí.

### El "Physical AI" en términos de MDP

El término **"Physical AI"** (lo que apunta tu plan) significa:

> *Un agente que entiende su propio cuerpo físico, las consecuencias físicas de sus acciones, y razona en términos de embodiment.*

En MDP esto se traduce literalmente:

| Aspecto del "Physical AI" | Componente del MDP donde se encarna |
|---------------------------|-------------------------------------|
| Entiende su cuerpo | **S** incluye self_health, self_power, posición, orientación |
| Conoce restricciones físicas | **A** está limitado a lo que el Otter puede hacer (Ackermann, no holonómico) |
| Razona sobre consecuencias físicas | **R** refleja daño, victoria, exposición |
| Aprende del mundo físico | **P** es el simulador ODE que él muestrea |
| Considera el futuro | **γ** alto (0.99) para planear varios segundos adelante |

**Conclusión**: "Physical AI" = MDP donde S es la **telemetría del cuerpo**, A son **comandos físicos al cuerpo**, y R son **consecuencias físicas**. No hay misterio.

---

## Cada componente del MDP, encarnado en el agente

Vamos uno por uno con detalle máximo.

### Encarnando S (estado)

El estado **es lo que el agente sabe del mundo en cada momento**. Decisión de diseño central: **¿qué metés en S?**

Reglas para diseñar bien S:

1. **Tiene que ser markoviano** (o al menos casi). Si te falta una variable importante, la red no puede aprender porque "el futuro depende de algo que no le das".

2. **Cada feature tiene un costo**:
   - Más features → red más grande → más datos para entrenar.
   - Pero menos features → posiblemente no-markoviano → no aprende.
   - Trade-off real.

3. **Las features tienen que ser invariantes a lo que NO importa**. Por ejemplo, si rotás el mundo 180°, el problema sigue siendo el mismo. Por eso usamos **body frame** para muchos features (el enemigo "adelante a la derecha" es lo mismo siempre).

4. **Normalizar todo a [-1, 1] o [0, 1]**. Las redes neuronales aprenden mejor con inputs normalizados.

#### Decisiones concretas que vienen de "diseñar S"

| Decisión | Está en el MDP como |
|----------|---------------------|
| "Convertimos la R[12] a cuaternión antes de pasar a la red" | Feature transformation dentro de S |
| "Pasamos posiciones del enemigo a body frame, no world" | Invariancia rotacional en S |
| "No usamos Euler porque tiene gimbal lock" | Continuidad del espacio S |
| "Agregamos `ticks_since_fire` como feature" | Hacer S markoviano (sin esto, no sabés en qué fase de "post-fire" estás) |
| "Estimamos belief del enemigo con LSTM" | Aproximar S verdadero desde observaciones parciales (POMDP→MDP virtual) |

### Encarnando A (acciones)

A es **todo lo que el agente puede hacer**. Para el Otter:

```
A = {(thrust, steering, turret_bearing, turret_declination, fire) :
     thrust ∈ [-1, 1], steering ∈ [-1, 1],
     turret_bearing ∈ [-π, π], turret_declination ∈ [0, π/2],
     fire ∈ {0, 1}}
```

#### Decisiones concretas que vienen de "diseñar A"

| Decisión | Está en el MDP como |
|----------|---------------------|
| "Usamos SAC en vez de DQN" | SAC soporta A continuo; DQN solo discreto |
| "La torreta es independiente del cuerpo" | A tiene 5 dimensiones, no 3 |
| "El fire es Bernoulli, no continuo" | A es híbrido (4 continuos + 1 discreto) |
| "Trigger discipline filtra fires inválidos" | Restringimos A condicionalmente: si no hay LOS, fire=0 forzado |

### Encarnando P (transiciones)

P es **la física del mundo + el comportamiento del enemigo**. Decisiones:

- **No la modelamos explícitamente** → "model-free RL" → usamos solo muestras (simulador como caja negra).
- **La muestreamos miles de veces** entrenando millones de episodios.
- **El comportamiento del enemigo es parte de P** desde la perspectiva del agente. Si el enemigo cambia, P cambia.

#### Decisiones concretas que vienen de "considerar P"

| Decisión | Está en el MDP como |
|----------|---------------------|
| "Usamos self-play" | Hacemos P más estable: el enemigo es siempre una versión nuestra |
| "Usamos opponent modeling" | Modelamos parcialmente P (la parte del enemigo) para mejorar la política |
| "Usamos curriculum learning" | Empezamos con un P más fácil (enemigo simple) y subimos la dificultad |
| "No usamos model-based RL" | Decisión: no aprender un modelo de P explícito, solo muestrear |

### Encarnando R (recompensa)

R es **lo que premia o penaliza**. Es el componente con **más libertad creativa** y también el más riesgoso de diseñar.

La regla más importante:

> *El agente va a optimizar EXACTAMENTE lo que R define. Si lo definís mal, va a hacer cosas raras.*

Ejemplos clásicos de mal diseño:

- Reward = "minimizar tiempo del episodio" → agente aprende a suicidarse rápido.
- Reward = "maximizar disparos" → agente aprende a tirar al aire constantemente.
- Reward = "estar cerca del enemigo" → agente se acerca y se queda mirándolo sin disparar.

#### Decisiones concretas que vienen de "diseñar R"

| Decisión | Está en el MDP como |
|----------|---------------------|
| "Penalizamos `fire` con -0.3 cada vez" | Componente de R que desalienta delatarse |
| "Bonus por estar en cobertura" | Componente de R que alinea con doctrina táctica |
| "Reward de victoria +1000, muerte -500" | Componentes terminales de R |
| "Mantenemos un Hit Probability Estimator separado" | Workaround porque R no puede observar "acierto" directamente |
| "Reward shaping con bonus por reducir entropía del belief" | Componente de "active perception" en R |

### Encarnando γ (descuento)

γ es **cuán lejos al futuro mira el agente**. Para combate de Otter:

- Bala vuela ~0.7s al impacto. Eso son ~35 ticks.
- Movimiento del Otter en 5 segundos ≈ 100m. Eso son ~250 ticks.
- Episodio dura 5000 ticks máx.

Con γ = 0.99: horizonte efectivo ≈ 100 ticks ≈ 2 segundos. Eso cubre el ciclo "decidir disparar → ver impacto → reaccionar".

Con γ = 0.999: horizonte ≈ 1000 ticks ≈ 20 segundos. Cubre estrategias más largas pero hace el entrenamiento más lento.

#### Decisiones concretas que vienen de "elegir γ"

| Decisión | Está en el MDP como |
|----------|---------------------|
| "Usamos γ = 0.99" | Compromiso entre cortoplacista y larga vista |
| "Episodios pueden ser largos pero rewards terminales dominan" | γ alto + magnitudes terminales grandes balancean |

---

## Walkthrough: una pelea contada en términos de MDP

Vamos a recorrer una situación real de combate **tick por tick**, mostrando exactamente qué es S, A, R en cada momento. Esto es lo que mejor te va a hacer internalizar el formalismo.

**Contexto inicial**: el Otter spawneó en `(1000, 0, 800)_W` mirando al norte (yaw=180°). El enemigo está en `(-500, 0, -200)_W` pero no lo vemos.

### Tick 0 — primer estado

**S₀** (lo que el agente recibe, simplificado):

```
self_pos:     (0.71, 0, 0.57)        ← normalizado por /1400
self_quat:    (0.0, 0.0, 1.0, 0.0)   ← yaw=180°
self_health:  1.0
self_power:   1.0
radar_active: False
los_to_wh:    [F, F, F, F, T, ...]   ← 18 bool
defilade:     0.1                     ← muy expuesto
belief_enemy_pos: (0, 0)              ← incertidumbre máxima, sin info aún
belief_enemy_std: (1.0, 1.0)
ticks_since_fire: ∞
```

**A₀**: la red mira S₀ y produce:

```
thrust=0.6, steering=0.2, turret_b=0, turret_d=0, fire=False
```

(empieza a moverse hacia el centro del mapa para encontrar cobertura)

**r₀**: 
```
- Sin daño → 0
- Sin disparo → 0
- defilade bajo → 0
- step penalty → -0.01
- bonus por estar vivo → +0.05
TOTAL: +0.04
```

### Tick 50 — moviéndonos a cubierto

**S₅₀**: ahora hay info en algunas features:

```
self_pos:     (0.62, 0, 0.45)         ← se movió
self_quat:    similar
self_health:  0.95                     ← perdimos 50 (desgaste natural)
los_to_wh:    [F, F, T, T, T, ...]
defilade:     0.55                     ← más cubierto
```

**A₅₀**:
```
thrust=0.5, steering=-0.1, turret_b=0.3, ...
```

(sigue acercándose a cobertura, empieza a barrer la torreta)

**r₅₀**: similar a tick 0, sin eventos especiales.

### Tick 120 — primer contacto

Recibimos un **radar event**: el enemigo disparó y la bala impactó a 200m al oeste nuestro.

**S₁₂₀**:

```
self_pos:     (0.55, 0, 0.40)
self_health:  0.88                     ← Δhealth = -7 (1 desgaste + 6 daño extra!)
radar_active: True
radar_pos_relative_body: (-0.3, 0, 0.1)  ← impacto al oeste en world = mi izquierda
radar_age_ticks: 0
i_was_hit_recently: True               ← ⚠️
belief_enemy_pos: (-0.4, -0.2)         ← actualizado por el state estimator!
belief_enemy_std: (0.3, 0.3)           ← incertidumbre BAJÓ
```

**r₁₂₀**:
```
- Daño extra de 6 → -30
- Radar muy cercano (200m) → -0.5 * (1 - 200/500) = -0.3
- Reduce incertidumbre belief → +0.1 * Δentropy ≈ +0.5
- step + bonus vivo → +0.04
TOTAL: -29.76     ← evento fuerte, el agente sabe que algo malo pasó
```

**A₁₂₀** (la red, después de ver S₁₂₀ con i_was_hit_recently=True):
```
thrust=0.7, steering=0.8, turret_b=-1.5, ...
```

(maniobra evasiva: acelera fuerte y dobla. La torreta se orienta hacia el origen estimado del fuego)

### Tick 180 — contraataque

Ahora estamos en cubierto detrás de un warehouse. Asomamos la torreta y vemos al enemigo (en el belief).

**S₁₈₀**:

```
defilade: 0.75                         ← bien cubiertos
belief_enemy_pos: (-0.45, -0.3)        ← consistente, baja incertidumbre
belief_enemy_std: (0.15, 0.15)
ticks_since_fire: ∞
```

**A₁₈₀**:
```
thrust=0.0, steering=0.0, turret_b=-1.6, turret_d=0.05, fire=True
```

(disparamos, primera vez en el episodio. Apuntamos al belief estimado)

**r₁₈₀**:
```
- fire → -0.3 (penalty por delación)
- power → -0.1 (costo de munición)
- defilade alto → +0.05
TOTAL: -0.35
```

Notá: el "acertaste/erraste" NO está en r₁₈₀. **No lo sabemos en este tick** (la bala todavía está en vuelo).

### Tick 215 — efecto del disparo

35 ticks después (la bala llegó), si acertamos, el enemigo deja de dispararnos.

**S₂₁₅**:

```
radar_freq: 0.0     ← bajó de 0.3 a 0
i_was_hit_recently: False
belief_enemy_pos: probablemente la inferencia del estimator se actualiza
```

**r₂₁₅**: no hay reward directo de "acertaste" — el agente solo nota que el peligro bajó. Si entrenamos con HPE (Hit Probability Estimator), ahí sí podemos agregar **+10 * P(hit)** post-fire.

### Tick 4500 — final del episodio

Llevamos 4500 ticks. Yo health = 0.4, enemigo (estimamos) muerto.

**S₄₅₀₀**: episodio termina. Recibimos señal terminal.

**r₄₅₀₀**:
```
- step penalty + bonus → +0.04
- VICTORIA → +1000
TOTAL: +1000.04
```

### Retorno total del episodio

Sumando los rewards descontados (γ=0.99):

```
G = Σ γᵗ rₜ
  ≈ Σ rₜ pequeños positivos durante exploración
  + rewards negativos por daños recibidos
  + costos pequeños por cada disparo
  + +1000 al final
  
Total aprox: +500 a +800 (depende del descuento de los terminales)
```

**Comparado con random**: un agente random típicamente moriría en ~1500 ticks → -500 sin bonus. Diferencia entre random y nuestro agente: ~+1000 a +1300.

**Esa diferencia es lo que el RL aprende a maximizar.**

---

## Cómo encajan las decisiones futuras del proyecto

Toda decisión que tomemos de acá en adelante se va a explicar en términos del MDP. Acá te muestro las próximas decisiones que vamos a ver y dónde caen:

### SAC (Concepto 14)

- **Encaja en**: algoritmo que aprende π óptima para nuestro MDP.
- **Qué supone**: A continuo, MDP, off-policy.
- **Qué agrega al diseño**: política estocástica con entropía → favorece exploración.

### POMDP y LSTM (Concepto 15)

- **Encaja en**: extensión de S porque no es observable directo.
- **Qué supone**: S verdadero no es lo que recibimos por UDP → necesitamos un estimador.
- **Qué agrega al diseño**: LSTM que mantiene historia → estimación de belief enemigo.

### Self-play

- **Encaja en**: estabilización de P.
- **Qué supone**: el enemigo es una copia/versión anterior de nuestra política.
- **Qué agrega al diseño**: no necesitamos un enemigo "scripted" externo, autoaprendizaje.

### Opponent modeling

- **Encaja en**: modelado parcial de P (la parte del enemigo).
- **Qué supone**: podemos predecir comportamiento del enemigo.
- **Qué agrega al diseño**: una segunda red que predice "qué va a hacer el enemigo".

### Imitation learning como warm-start

- **Encaja en**: inicialización de π.
- **Qué supone**: tenemos un controlador scripted (no óptimo pero razonable) que genera datos.
- **Qué agrega al diseño**: arrancamos el SAC desde una política decente, no random.

### Curriculum learning

- **Encaja en**: secuencia de MDPs progresivamente más difíciles.
- **Qué supone**: podemos variar P (dificultad) durante el entrenamiento.
- **Qué agrega al diseño**: el agente aprende lo fácil primero, después lo difícil.

### Reward shaping iterativo

- **Encaja en**: refinamiento de R.
- **Qué supone**: la R inicial es subóptima y la mejoramos con experiencia.
- **Qué agrega al diseño**: ciclo de "entrenar → observar comportamientos raros → ajustar R".

---

## Lo que el MDP NO cubre

Es importante saber los límites del formalismo:

### Lo que MDP no te dice

1. **Cómo aprende el agente**. Eso es algoritmo (DQN, PPO, SAC, etc.). MDP solo dice "hay que maximizar el retorno esperado".
2. **Qué arquitectura tiene la red neural**. Eso es ingeniería (cuántas capas, qué tipo, etc.).
3. **Cuán rápido converge el entrenamiento**. Depende del algoritmo, hardware, datos, hiperparámetros.
4. **Por qué la política funciona**. Las redes neuronales son cajas negras. Tenemos la política pero no necesariamente sabemos "por qué decide X".
5. **Cómo dividir un problema grande en sub-problemas** (hierarchical RL). Hay extensiones pero no es nativo del MDP.

### Cuándo el MDP es insuficiente

| Problema | Solución |
|----------|----------|
| El estado no es markoviano | Expandir S (más features) o usar memoria (LSTM) |
| No vemos el estado completo | POMDP + belief state |
| El mundo no es estacionario | Online learning, meta-RL |
| Las acciones tienen consecuencias muy demoradas | γ alto + algoritmos con bootstrap (TD) |
| El espacio de acciones es enorme | Hierarchical RL, descomposición |

Para nuestro Otter, el problema principal del MDP puro es la **observabilidad parcial** → vamos a usar POMDP + LSTM (Concepto 15).

---

## Conexión con tu pregunta original sobre "estrategia"

Cuando dijiste "vayamos pensando la estrategia", lo que estás pidiendo es exactamente:

> *Diseñar S y R de modo que la política óptima, cuando la encontremos, exhiba comportamiento estratégico interesante.*

La "estrategia" emerge de la interacción entre:

1. **S** → qué puede percibir el agente.
2. **R** → qué premia/penaliza.
3. **A** → qué puede hacer.
4. **P** → cómo responde el mundo.

**Si diseñás bien S y R, no necesitás programar la estrategia explícitamente. Emerge sola del entrenamiento.**

Ejemplos:

- **Si R penaliza disparar Y rewardea cover** → el agente aprende **shoot-and-scoot**.
- **Si S incluye `radar_freq`** → el agente aprende a **detectar agresividad del enemigo** y reaccionar.
- **Si R penaliza el daño cerca del límite del mapa** → el agente aprende a **no acorralarse**.
- **Si R tiene un bonus por reducir entropía del belief** → el agente aprende **exploración activa** ("provocar al enemigo a disparar para localizarlo").

**Esta es la potencia del enfoque Physical AI con RL**: la estrategia no se programa, se **diseña al diseñar S, R, y la arquitectura**. La política la encuentra el optimizador.

---

## Resumen ejecutivo

| Concepto | Lo importante |
|----------|---------------|
| **MDP = esqueleto** | Toda decisión del proyecto se traduce a "qué cambio en S/A/R/P/γ" |
| **Physical AI = MDP con cuerpo** | S incluye self-state, A son comandos físicos, R refleja consecuencias físicas |
| **Diseñar S es lo más importante** | Si S no captura lo relevante, ningún algoritmo aprende |
| **Diseñar R es donde están los bugs** | El agente optimiza EXACTAMENTE lo que ponés en R, sin sentido común |
| **La estrategia emerge** | No se programa explícitamente, surge de S + R + entrenamiento |
| **Límites del MDP** | No cubre cómo aprende, qué arquitectura, cuándo converge |

---

## Próximos pasos

Cuando avancemos al **Concepto 12** vas a ver el **bucle de entrenamiento**: cómo el agente, episodio tras episodio, ajusta su política para maximizar el retorno. Ahí también vamos a entender por qué SAC es el algoritmo que elegimos.

Pero ya tenés en la cabeza el lenguaje en el que está escrito todo: **MDP**. Y sabés exactamente qué decisiones de diseño afectan cada componente.
