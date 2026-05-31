# Concepto 13 — Redes neuronales en una página

Versión MUY condensada. Solo lo que necesitás saber para entender qué hace SAC adentro. Si querés profundidad, hay miles de libros — para nuestro caso esto alcanza.

---

## La idea más básica

Una **red neuronal** es una función matemática que toma un vector de entrada y produce un vector de salida. Es **aprendible**: ajustás millones de parámetros internos para que la función haga lo que querés.

```
input (R^N) ───▶ red neuronal ───▶ output (R^M)
```

Para nuestro Otter:
- **Política π**: input = estado del Otter (78 floats), output = acción (5 valores).
- **Critic Q**: input = estado + acción (83 floats), output = valor escalar (1 número).
- **State Estimator**: input = secuencia de observaciones, output = pose enemiga estimada.

Todo son redes neuronales con la misma estructura general.

---

## Anatomía de una NN feed-forward

Una **capa** transforma un vector en otro vector con esta operación:

```
h = σ(W·x + b)
```

- `x`: input de la capa (vector)
- `W`: matriz de pesos (aprendible)
- `b`: vector de bias (aprendible)
- `σ`: función de activación NO lineal (ReLU, tanh, etc.)
- `h`: output de la capa

Una **red profunda** apila varias capas:

```
input ──▶ capa 1 ──▶ capa 2 ──▶ ... ──▶ capa N ──▶ output
```

Cada capa puede tener tamaño distinto. Típico para SAC en nuestro caso:

```
estado (78) ──▶ FC 256 ReLU ──▶ FC 256 ReLU ──▶ FC 5 (output)
```

Donde "FC 256" = capa "fully connected" con 256 neuronas, y "ReLU" = activación.

---

## Funciones de activación (las dos que importan)

| Activación | Fórmula | Cuándo se usa |
|------------|---------|---------------|
| **ReLU** | `max(0, x)` | En capas internas. Rápida y funciona bien. Standard. |
| **tanh** | `(eˣ - e⁻ˣ) / (eˣ + e⁻ˣ)` | En outputs que tienen que estar en [-1, 1] (e.g., thrust, steering del Otter) |
| **sigmoid** | `1 / (1 + e⁻ˣ)` | En outputs binarios (e.g., probabilidad de `fire`) |

Sin activación NO lineal, todas las capas colapsan en una sola transformación lineal (la red se vuelve trivial). Por eso son **esenciales**.

---

## Cómo aprende: backpropagation

El proceso de aprendizaje tiene 3 pasos por cada minibatch:

### 1. Forward pass

Pasás los inputs por la red y obtenés outputs. **Computación normal**.

### 2. Loss

Comparás los outputs con lo que querías que produjera. La diferencia es la **loss** (un número escalar).

Ejemplo: si la red predijo `(0.5, 0.3)` pero querías `(0.6, 0.4)`:

```
loss = (0.5 - 0.6)² + (0.3 - 0.4)² = 0.02   (MSE)
```

### 3. Backward pass (backpropagation)

Calculás cómo cambiar cada parámetro de la red (cada W y b) para que la próxima vez la loss sea menor. **Esto es el gradient** y se computa con la regla de la cadena del cálculo.

PyTorch hace esto automáticamente:

```python
loss.backward()           # calcula los gradientes
optimizer.step()          # actualiza los parámetros
```

No tenés que derivar nada a mano. Es magia (con costo computacional).

---

## Hiperparámetros típicos

| Parámetro | Valor típico para SAC | Qué controla |
|-----------|----------------------|--------------|
| **Learning rate** | 3e-4 (= 0.0003) | Cuánto se mueven los parámetros en cada step. Muy alto = inestable. Muy bajo = lento. |
| **Batch size** | 256 | Cuántas tuplas del replay buffer procesás por update |
| **Hidden size** | 256 | Cuántas neuronas en cada capa interna |
| **Num layers** | 2 o 3 | Cuántas capas |
| **Optimizer** | Adam | Variante de gradient descent. Standard. |

---

## ¿Cuánta data necesito?

Regla de bolsillo: con SAC en problemas continuos como el nuestro, **convergencia razonable** se logra con:

- **100k - 1M transiciones** en el replay buffer.
- Equivalente a **100-1000 episodios completos** (de 5000 ticks).

Con hardware modesto (Colab T4), entrenar 500k steps puede tardar **6-12 horas**.

---

## Por qué importa para nuestro proyecto

Necesitás entender:

1. **Estructura básica**: capas, pesos, bias, activación.
2. **Forward / loss / backward**: el ciclo de update.
3. **Hiperparámetros importantes**: lr, batch_size, hidden_size.
4. **Magnitudes**: 256 hidden, 2-3 capas, 1M buffer.

Con eso podés leer y modificar el código de `stable-baselines3` (que es lo que vamos a usar). No vas a implementar redes desde cero.

---

## Las redes específicas del agente Otter

| Red | Tamaño aprox | Input → Output | Propósito |
|-----|--------------|----------------|-----------|
| **Actor (política π)** | 3 × 256 | estado (78) → acción (5) | La que decide qué hacer |
| **Critic Q1, Q2** | 3 × 256 cada una | estado + acción (83) → Q (1) | Evalúan la acción |
| **State Estimator (LSTM)** | 2 × 128 | secuencia de obs → belief enemigo | Inferir pose enemiga (POMDP) |
| **HPE** | 2 × 128 | estado + aim → P(hit) | Estimar probabilidad de acierto |

Total: ~500k parámetros. Modesto comparado con cualquier modelo de visión moderno (millones a billones).

---

## Lo que NO te explico

- Convolutional NN (no las usamos, no hay imágenes).
- Transformer / atención (over-kill).
- Dropout, BatchNorm, regularización (PyTorch defaults alcanzan).
- Inicialización de pesos (defaults de PyTorch funcionan).

Si en algún momento querés profundizar, podés ir al libro de Goodfellow "Deep Learning" o cursos de Andrew Ng.

---

## Resumen para llevarse

| Concepto | Qué es |
|----------|--------|
| **Red neuronal** | Función parametrizada R^N → R^M |
| **Capa** | `h = σ(Wx + b)`. Apilás varias. |
| **ReLU** | Activación standard para capas internas |
| **tanh** | Para outputs en [-1, 1] |
| **Backprop** | Cálculo automático de gradientes (PyTorch lo hace) |
| **Loss** | Lo que querés minimizar. Define qué aprende la red. |
| **Adam** | Optimizer standard |
| **Para SAC del Otter** | 3 capas × 256 neuronas. ~500k parámetros totales. |

---

## Lo que viene

**Concepto 14**: SAC en práctica con `stable-baselines3`. Cómo entrenar el agente del Otter sin reimplementar nada.
