# Workflow Google Colab

Cómo entrenar el agente del Otter en Colab y traer el modelo a tu máquina.

---

## Paso 1: Setup en tu máquina local

```bash
# Activar venv
source .venv/bin/activate

# Instalar dependencias
pip install -r agent/requirements.txt

# Adicional para Colab workflow
pip install h5py
```

---

## Paso 2: Recolectar dataset localmente

El simulador corre en tu máquina, el script de recolección lo controla y graba todo.

```bash
# Compilar simulador (si no está)
make

# En una terminal: levantar simulador
make TC=131 testcase    # compilar con TC 131 hardcoded
./testcase -mute -nointro

# En otra terminal: recolectar 100 episodios con política random
python -m agent.collect \
    --policy random \
    --episodes 100 \
    --output data/dataset_v1.h5
```

**Tiempo esperado**: cada episodio dura hasta 5000 ticks (~100s con tick=20ms).
100 episodios ≈ 3-4 horas en background.

Para acelerar, podés correr múltiples instancias en paralelo (en puertos distintos):

```bash
# Terminal 1
make TC=131 testcase    # compilar con TC 131 hardcoded
./testcase -mute -nointro -port 4501
python -m agent.collect --telemetry-port 4501 --output data/ds_1.h5 ...

# Terminal 2
make TC=131 testcase    # compilar con TC 131 hardcoded
./testcase -mute -nointro -port 4502
python -m agent.collect --telemetry-port 4502 --output data/ds_2.h5 ...
```

Después concatenás los datasets.

**Output esperado**: `data/dataset_v1.h5` de ~50-100 MB.

---

## Paso 3: Subir dataset a Drive

```bash
# Opción A: web Drive
# Subir manualmente desde drive.google.com → carpeta wakuseibokan/

# Opción B: rclone (si lo tenés instalado)
rclone copy data/dataset_v1.h5 gdrive:wakuseibokan/

# Opción C: gdrive CLI
gdrive upload data/dataset_v1.h5 --parent <folder_id>
```

---

## Paso 4: Entrenar en Colab

### 4a. Abrir Colab

1. Ir a https://colab.research.google.com
2. New notebook
3. **Importante**: Runtime → Change runtime type → GPU (T4)

### 4b. Pegar el código de entrenamiento

Opción 1 — Notebook desde cero, pegar el contenido de `train_offline_colab.py`
en celdas (cada `# %%` es una celda nueva).

Opción 2 — Subir el script:
```python
# En la primera celda de Colab
from google.colab import files
files.upload()  # subir train_offline_colab.py
!python train_offline_colab.py
```

### 4c. Ejecutar celdas en orden

1. **Setup**: instala dependencias (5 min).
2. **Mount Drive**: monta tu Drive (te pide permisos).
3. **Cargar dataset**: verifica que se carga bien.
4. **Train CQL**: el grueso del tiempo. ~500k steps en ~3-6 horas con T4.

Mientras entrena, podés monitorear con:

```python
# En otra celda
!tensorboard --logdir d3rlpy_logs/
```

### 4d. Descargar modelo

```python
from google.colab import files
files.download("models/otter_cql_v1.pt")
```

O guardarlo a Drive directo (el script ya lo hace si `OUTPUT_DIR` está en Drive).

---

## Paso 5: Eval local

Bajás el `otter_cql_v1.pt` a tu máquina y lo cargás:

```python
# En tu máquina local
import torch
from agent.env import WakuseibokanEnv  # cuando esté implementado

checkpoint = torch.load("otter_cql_v1.pt", map_location="cpu")
# Reconstruir la política y cargar pesos
# ... (depende de la arquitectura final)

env = WakuseibokanEnv()
obs = env.reset()
for _ in range(5000):
    action = policy(obs)
    obs, reward, done, _, _ = env.step(action)
    if done:
        break
```

---

## Limitaciones de Colab

| Cosa | Detalle |
|------|---------|
| **Sesión max** | 12 horas (free tier) |
| **GPU usage limits** | Te pueden cortar si abusás |
| **RAM** | ~12 GB (T4) — suficiente para nuestro tamaño |
| **Disco** | ~100 GB temporal — suficiente |
| **No persiste entre sesiones** | Por eso guardamos en Drive |

**Workaround**: Kaggle Notebooks te da P100 + 30h/semana (más generoso). Mismo workflow.

---

## Estructura sugerida en Drive

```
MyDrive/
└── wakuseibokan/
    ├── datasets/
    │   ├── dataset_v1.h5       (random policy, semana 1)
    │   ├── dataset_v2.h5       (mixed, semana 2)
    │   └── dataset_v3.h5       (final, semana 3)
    ├── models/
    │   ├── otter_cql_v1.pt
    │   ├── otter_cql_v2.pt
    │   └── state_estimator_v1.pt
    ├── logs/
    │   └── tensorboard/
    └── notebooks/
        ├── train_offline.ipynb
        ├── train_state_estimator.ipynb
        └── analyze_dataset.ipynb
```

---

## Iteración rápida

```
LOCAL                              COLAB
─────                              ─────
collect.py (1h, dataset)
   ↓
Sube a Drive (5min)
   ↓
                                   train (3-6h)
                                   ↓
Bajá modelo (5min)                 ↑
   ↓
eval.py (5min, contra simulador)
   ↓
Decidir: refinar reward? cambiar arquitectura? más data?
   ↓
collect.py de nuevo
```

Por semana, podés hacer 2-3 iteraciones de este ciclo. Suficiente para llegar
a un agente decente en 4 semanas.

---

## Tips para no perder tiempo

1. **Empieza con dataset chico** (50 episodios) para verificar pipeline antes
   de tirar 500 episodios.
2. **Smoke test del notebook** con 10k steps antes de los 500k completos.
3. **Usá tensorboard** para detectar problemas temprano (loss no baja, divergencia).
4. **Guardá checkpoints intermedios** (cada 50k steps), no solo el final.
5. **Si CQL diverge**: bajá `conservative_weight` de 5 a 1; bajá `learning_rate` a 1e-4.
