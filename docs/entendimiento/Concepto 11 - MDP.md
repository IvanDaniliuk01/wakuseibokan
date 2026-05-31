# Concepto 11 — MDP (el formalismo del Reinforcement Learning)

> 💡 **Visualización 3D acompañante**: `Concepto 11 - Visualizacion MDP.html`
>
> ```bash
> xdg-open "/home/itba/wakuseibokan/docs/entendimiento/Concepto 11 - Visualizacion MDP.html"
> ```

> 📚 **Referencia del curso**: PDF 4 "AprendizajeXRefuerzo" (Ramele). Es el material oficial del curso para esta sección. Lo que vemos acá es exactamente lo que está en esas slides, pero explicado más despacio.

---

## ¿Por qué necesitamos un formalismo?

Hasta ahora hablamos del agente de forma intuitiva: "el agente toma decisiones, recibe recompensas, aprende". Eso está bien para charlar, pero para programar y para que la matemática funcione, necesitamos un **lenguaje preciso**.

Ese lenguaje se llama **MDP** (Markov Decision Process). Es el formalismo de **prácticamente todo el reinforcement learning**. Si entendés MDP, entendés el vocabulario que se usa en cualquier paper, libro o curso de RL.

---

## La idea central en 5 segundos

El RL describe la interacción **agente ↔ mundo** en un loop:

```
   ┌─────────┐       acción a_t      ┌─────────┐
   │         │ ────────────────────▶│         │
   │ AGENTE  │                       │  MUNDO  │
   │         │ ◀──────────────────── │         │
   └─────────┘   estado s_{t+1}      └─────────┘
                 recompensa r_t
```

- El **agente** observa el **estado** del mundo.
- El **agente** elige una **acción**.
- El **mundo** responde: cambia de estado y le da una **recompensa** al agente.
- Loop.

El MDP es la formalización matemática de este loop.

---

## Los 5 ingredientes del MDP

Un MDP se define con **5 elementos**, escritos como una tupla `⟨S, A, P, R, γ⟩`:

### 1. S — el espacio de estados

**S** es el conjunto de **todas las situaciones posibles** del mundo.

Para el Otter en Wakuseibokan, un estado es algo como:

```
s_t = (
    posición del Otter,
    orientación (matriz / cuaternión),
    velocidad,
    health,
    power,
    posición del enemigo (si la vemos),
    health del enemigo,
    ...
)
```

S es **enorme** (combinaciones infinitas de números reales). Pero es solo "la lista de todas las cosas que el agente puede ver y que importan para la decisión".

### 2. A — el espacio de acciones

**A** es el conjunto de **todas las acciones que el agente puede tomar**.

Para el Otter:

```
a_t = (
    thrust ∈ [-1, 1],
    steering ∈ [-1, 1],
    turret_bearing ∈ [-π, π],
    turret_declination ∈ [0, π/2],
    fire ∈ {True, False}
)
```

A diferencia de muchos ejemplos de RL clásicos (donde las acciones son discretas: "arriba", "abajo", "izquierda", "derecha"), las nuestras son **continuas** (un número real en un rango). Eso restringe qué algoritmos podemos usar — SAC es perfecto para esto.

### 3. P — la función de transición

**P** te dice qué pasa cuando tomás una acción en un estado:

```
P(s_{t+1} | s_t, a_t) = "probabilidad de terminar en s_{t+1} si estoy en s_t y hago a_t"
```

**Es una distribución de probabilidad** porque el mundo puede ser ruidoso. Para el Otter, P es **toda la física del simulador ODE** + las decisiones del enemigo. **No la conocemos explícitamente**, pero existe.

En RL **no necesitamos** conocer P explícitamente — solo necesitamos poder **observar muestras** de P (correr el simulador, ver qué pasa). Esto se llama **RL model-free**, que es lo que vamos a usar.

### 4. R — la función de recompensa

**R** te dice cuán bueno o malo es el resultado de una acción:

```
R(s_t, a_t, s_{t+1}) = recompensa numérica
```

**Esta la definimos nosotros.** Es la parte más creativa del diseño del agente, y la que más importa para que funcione.

Ejemplo para el Otter:

```python
def reward(s_t, a_t, s_t_next):
    r = 0
    # Daño al enemigo
    r += 10 * (s_t.enemy_health - s_t_next.enemy_health)
    # Daño recibido (penalty)
    r -= 5 * (s_t.self_health - s_t_next.self_health)
    # Penalty por tick (incentivar terminar)
    r -= 0.01
    # Bonus por victoria
    if s_t_next.enemy_health <= 0:
        r += 1000
    # Penalty por muerte
    if s_t_next.self_health <= 0:
        r -= 500
    return r
```

**Reward shaping** (ajustar la función) es **arte**: si está mal definida, el agente aprende cosas raras (por ejemplo, quedarse quieto si no hay penalty por tiempo).

### 5. γ — el factor de descuento

**γ** (gamma) es un número entre 0 y 1 que dice **cuánto valoramos el futuro**.

```
Retorno = r_t + γ·r_{t+1} + γ²·r_{t+2} + γ³·r_{t+3} + ...
```

Si γ = 0, el agente solo le importa la recompensa inmediata (cortoplacista). Si γ = 1, le importa todo el futuro por igual (puede causar problemas matemáticos de divergencia).

Típicamente γ ≈ 0.99 — al agente le importa el futuro, pero le da un poco menos de peso a cada paso más lejano.

| γ | Después de... | Multiplicador |
|---|---------------|---------------|
| 0.99 | 100 ticks | 0.99¹⁰⁰ ≈ 0.37 |
| 0.99 | 500 ticks | 0.99⁵⁰⁰ ≈ 0.007 (casi cero) |
| 0.9 | 50 ticks | 0.9⁵⁰ ≈ 0.005 |

Esto define el **horizonte efectivo**: con γ=0.99, el agente "ve" unos 100 ticks adelante. Más allá, los rewards futuros le importan poco.

---

## La política π

La **política** es lo que el agente **aprende**. Es una función:

```
π(s) = a
```

"Dado un estado, ¿qué acción tomo?"

Hay dos tipos:

- **Determinista**: `π(s) = a` (siempre la misma acción para el mismo estado).
- **Estocástica**: `π(a | s)` = probabilidad de tomar acción `a` dado estado `s`. Permite exploración (no siempre lo mismo).

En SAC (que vamos a usar) la política es estocástica: la red neural produce una **distribución gaussiana** de la cual se muestrea la acción.

---

## El objetivo del agente

Maximizar el **retorno esperado**:

```
J(π) = E[ r_0 + γ·r_1 + γ²·r_2 + ... ]
       cuando seguimos política π
```

En palabras: "encontrá la política π que, en promedio sobre muchos episodios, dé la mayor suma descontada de recompensas".

Esto es **lo único que el agente quiere**. Todo lo demás (cómo aprende, qué arquitectura tiene, qué algoritmo usa) es **medio para este fin**.

---

## La propiedad markoviana

El "M" de MDP significa **markoviano**. Es una propiedad clave:

> *El futuro solo depende del presente, no del pasado.*

Formalmente:

```
P(s_{t+1} | s_t, a_t) = P(s_{t+1} | s_t, a_t, s_{t-1}, a_{t-1}, ..., s_0, a_0)
```

Es decir: si conocés el estado actual `s_t`, no necesitás saber cómo llegaste ahí — toda la info relevante ya está en `s_t`.

### ¿Vale para el Otter?

**A medias**. Si el estado incluye la posición, velocidad, orientación y todo lo relevante, entonces sí — el futuro solo depende del presente.

Pero si el estado **solo** es la posición actual, sin velocidad, entonces NO es markoviano: necesitás saber a qué velocidad ibas (info del pasado) para predecir dónde estará el Otter después.

**Regla práctica**: si tu agente parece "olvidar cosas importantes", probablemente tu estado no es markoviano. Solución: agregar más features al estado, o usar una LSTM que mantiene memoria (Concepto 15).

---

## Episodios

El loop del agente se divide en **episodios**:

- Cada episodio empieza en un estado inicial (`s_0`).
- El agente toma acciones, recibe recompensas.
- Termina cuando se cumple alguna condición:
  - Victoria (matar al enemigo)
  - Derrota (te matan)
  - Timeout (pasan 5000 ticks sin definirse)
- El **retorno del episodio** es la suma descontada de todas las recompensas.

El entrenamiento consiste en **correr miles de episodios** y ajustar la política para que el retorno promedio sea cada vez más alto.

---

## ¿Cómo lo aprende el agente?

Ese es el tema del **Concepto 12**. Por ahora la idea es: el agente prueba cosas, ve qué funcionó, y ajusta su política para hacer más de lo que funcionó (y menos de lo que no funcionó).

Hay varias **familias de algoritmos** que vimos por encima en el PDF 4:

| Familia | Idea | Ejemplos |
|---------|------|----------|
| **Value-based** | Aprender Q(s, a) = "cuán bueno es tomar a en s" | Q-Learning, DQN |
| **Policy-based** | Aprender π directamente | REINFORCE, PPO |
| **Actor-Critic** | Combinar las dos cosas | A2C, SAC, TD3 |
| **Model-based** | Aprender un modelo del mundo y planear | MuZero, World Models |

**Nosotros vamos a usar SAC** (Soft Actor-Critic), que es Actor-Critic con maximum entropy. Lo vemos en el Concepto 14.

---

## MDP aplicado al Otter (la tabla resumen)

| Elemento del MDP | Para el agente del Otter |
|------------------|--------------------------|
| **S** (estados) | Posición, orientación, velocidad, health, power propios + del enemigo + radar |
| **A** (acciones) | `(thrust, steering, turret_b, turret_d, fire)` |
| **P** (transición) | La física del simulador ODE + decisiones del enemigo. No la conocemos pero la podemos muestrear. |
| **R** (recompensa) | La definimos: daño al enemigo (+), daño recibido (−), step penalty (−), victoria (++), muerte (−−) |
| **γ** (descuento) | 0.99 típicamente |
| **π** (política) | La red neural que aprendemos con SAC |
| **Markovianidad** | Casi se cumple (si el estado incluye velocidad). Cuando no se cumple → POMDP (Concepto 15). |

---

## Probá la visualización

En el HTML acompañante vas a ver un mini-MDP funcionando:

- Una **arena** con el Otter y un **objetivo** (cubo amarillo).
- El Otter se mueve con thrust/steering (lo del Concepto 10).
- **Rewards en tiempo real**:
  - −0.1 por tick (penaliza demorarse)
  - +100 por llegar al objetivo (victoria)
  - −20 por chocar con una pared
- **Display**: estado actual, acción actual, reward del tick, **retorno acumulado** (con γ).
- **Slider γ** para que veas cómo cambia el retorno al cambiar el horizonte.
- **Modo "Random Policy"**: el agente toma acciones random. Vas a ver que el retorno es bajo o muy variable.
- **Modo "Manual"**: vos controlás con los sliders.

### Lo importante que tenés que ver

1. **Modo Manual**: andá al objetivo lo más rápido posible. Vas a ver el retorno acumulado crecer.
2. **Modo Random**: vas a ver que el Otter da vueltas sin sentido. Retornos muy bajos o negativos. **Eso es lo que vence el RL — encontrar una política mejor que random**.
3. **Cambiá γ**: con γ=0.5 (cortoplacista) el agente no debería "ahorrar" rewards lejanos. Con γ=0.99 sí.
4. **Mirá el estado y la acción**: el estado es el vector de números que recibís. La acción es lo que decidís. Eso es **todo** el formalismo MDP en una pantalla.

---

## Resumen para llevarse

| Concepto | Qué es |
|----------|--------|
| **MDP** | Tupla ⟨S, A, P, R, γ⟩ que formaliza la interacción agente-mundo. |
| **S** | Espacio de estados (lo que el agente ve). |
| **A** | Espacio de acciones (lo que el agente puede hacer). |
| **P** | Función de transición (cómo cambia el mundo). No la conocemos en model-free. |
| **R** | Función de recompensa (lo que premia/penaliza). La diseñamos nosotros. |
| **γ** | Factor de descuento (cuánto valora el futuro). Típicamente 0.99. |
| **π** | Política — lo que el agente aprende. |
| **Retorno** | `G = r₀ + γ·r₁ + γ²·r₂ + ...` — la suma descontada que queremos maximizar. |
| **Markoviano** | El futuro solo depende del presente, no del pasado. Si no se cumple → POMDP. |
| **Episodio** | Una partida completa, desde inicio hasta terminación. |

---

## Lo que viene después

- **Concepto 12**: el **bucle de RL** — cómo el agente aprende concretamente: episodios, rollouts, gradient updates, exploration vs exploitation.
- Después: redes neuronales, SAC, POMDP, pipeline completo.
