# Agent — Otter Physical AI

Agente Python que controla un Otter en Wakuseibokan vía UDP y aprende a combatir
contra otro Otter usando Reinforcement Learning (SAC).

## Estructura

```
agent/
├── packet_format.py        # Parse/pack de ModelRecord, ControlStructure2, TickRecord
├── udp_io.py               # Cliente UDP base + SharedTelemetryHub (telemetría thread-safe)
├── encoders.py             # encode_state (12-D) + decode_action (6-D) compartidos
├── reward.py               # Reward shaping del combate (función pura)
├── policy_utils.py         # Helpers compartidos (azimuth, bearing relativo)
├── seek_policy.py          # Política scripted con 4 modos (engage/escape/evasive/noise)
├── cheater_policy.py       # Oponente privilegiado con 4 niveles de dificultad
├── env.py                  # Gymnasium env wrapper (soft/hard reset, cheater integrado)
├── collect_vs_cheater.py   # Recolector con cheater oponente en proceso único
├── eval.py                 # Evalúa un modelo entrenado contra el simulador
├── colab/
│   ├── train_otter_cql.py      # Script para entrenar CQL en Colab
│   └── COLAB_WORKFLOW.md       # Workflow paso a paso de Colab
├── map_belief.py           # (PENDIENTE) Belief incremental del city center
├── state_estimator.py      # (PENDIENTE) LSTM que infiere belief enemigo
├── tests/                  # Tests unitarios (sin sim)
└── requirements.txt
```

## Estrategia de entrenamiento

1. **Fábrica de datos**: `agent.collect_vs_cheater` corre dos threads en el
   mismo proceso. Otter 1 controlado por `seek_policy` (con variación por
   episodio + noise) es el que GRABAMOS. Otter 2 es un `cheater_policy` con
   información privilegiada (telemetría de ambos vehículos).
2. **Mix de oponentes**: 4 niveles de dificultad (EASY → IMPOSSIBLE) calibrados
   para que el dataset tenga victorias y derrotas en proporciones útiles para
   offline RL. Default sugerido: `easy:150,medium:300,hard:300,impossible:75`.
3. **Filtro de calidad**: episodios donde los tanques nunca se cruzaron
   (`min_dist > 800m` en toda la trayectoria) se marcan con `had_encounter=False`
   y se descartan en el training.
4. **Training offline**: `colab/train_otter_cql.py` carga el HDF5, construye
   el MDP y entrena CQL (d3rlpy) en Colab T4.
5. **Fine-tuning online (opcional)**: `agent.env.OtterEnv` cumple Gymnasium API
   estándar; se puede enchufar a stable-baselines3 SAC con `reset_mode="hard"`
   para variar el mapa entre episodios.

## Workflow Colab (training pesado en GPU remota)

Ver detalle completo en [colab/COLAB_WORKFLOW.md](colab/COLAB_WORKFLOW.md). Resumen:

```
LOCAL (tu máquina)              REMOTE (Colab T4)
──────────────────              ─────────────────
1. collect.py (~3h)
   → dataset.h5
2. Sube a Drive (5min)  ─────▶  3. train_offline_colab.py (~3-6h)
                                   → modelo.pt en Drive
                        ◀─────  4. Descarga modelo (5min)
5. eval.py (~10min)
   ↓
Iterar
```

## Documentación de fondo

Toda la teoría y el diseño están en `../docs/entendimiento/`:

- **Conceptos 1-9**: Coordenadas, rotaciones, R[12], cuaterniones.
- **Conceptos 10-16**: Cinemática, MDP, RL, redes neuronales, SAC, POMDP, pipeline.
- **Diseño 01**: Espacio de estados y función de recompensa concreta para el Otter.

## Setup

```bash
# Crear venv
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r agent/requirements.txt
```

## Quick start (smoke test)

### 1. Compilar el simulador

```bash
# Desde la raíz del repo
# IMPORTANTE: el testcase queda hardcoded en el binario al compilar.
# Hay que especificar TC=131 explícitamente.
make TC=131 testcase
```

### 2. Levantar el simulador

```bash
./testcase -mute -nointro
```

El binario ya tiene el testcase 131 compilado adentro, no hace falta pasarlo
como argumento. Si quisieras cambiar de testcase tenés que recompilar con otro
TC (ej: `make TC=121 testcase`).

Verificá que en el HUD del simulador aparece "TC131:". Si dice otro número
(ej "TC111"), recompilá con `make clean && make TC=131 testcase`.

(En otra terminal:)

### 3. Probar el cliente UDP

```bash
python -m agent.udp_io
```

Deberías ver mensajes tipo:
```
✓ Primer ModelRecord recibido:
  vehicle #1 pos=[...] health=1000.0
```

### 4. Recolectar dataset vs cheater

```bash
python -m agent.collect_vs_cheater --difficulty mixed \
    --mix-plan "easy:150,medium:300,hard:300,impossible:75" \
    --output data/dataset_v2.h5
```

### 5. Smoke tests (sin sim)

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from agent.tests.test_cheater_policy import *
from agent.tests.test_env_smoke import *
"
```

## Roadmap de implementación

### Bloque actual (en curso) — Datos vs cheater + env.py

- [x] `packet_format.py`, `udp_io.py` — base UDP
- [x] `encoders.py`, `reward.py`, `policy_utils.py` — single source of truth
- [x] `seek_policy.py` — política de "fábrica de datos" con 4 modos
- [x] `cheater_policy.py` — oponente privilegiado con 4 niveles
- [x] `collect_vs_cheater.py` — recolector dual-thread
- [x] `env.py` — Gymnasium wrapper con soft/hard reset
- [x] Tests del cheater + smoke tests del env
- [ ] Recolectar ~800-1000 episodios mixed → `data/dataset_v2.h5`
- [ ] Verificar win-rates por nivel (calibración del cheater)

### Próximo — State Estimator + State of map

- [ ] `state_estimator.py` — LSTM para belief del enemigo
- [ ] `map_belief.py` — belief del city center

### Después — Training serio

- [ ] Training offline CQL/IQL en Colab con `data/dataset_v2.h5`
- [ ] Fine-tuning online SAC con `env.OtterEnv(reset_mode="hard")`
- [ ] Eval matriz (modelo × nivel de cheater)
- [ ] Video demo

## Convenciones del código

- **Python 3.10+** (typing moderno).
- **Type hints** donde aporten claridad.
- **Docstrings** en español.
- **Tests** en `tests/`, ejecutables con `pytest`.
- **Numpy** para vectores; PyTorch solo para redes neuronales.

## Notas críticas

### Lobby vs Telemetría individual

El simulador expone dos canales UDP:

| Canal | Puerto | Qué da | Cuándo usar |
|-------|--------|--------|-------------|
| Telemetría individual | 4501+i | Solo nuestro vehículo (96 bytes) | **Eval (asumido)** |
| Lobby | 4500 | TODOS los vehículos (broadcast) | **Training (para GT)** |

La política nunca debe recibir GT del enemigo directamente — solo a través del
State Estimator (LSTM). Ver `Diseño 01.md` Sección F.

### El mapa es aleatorio cada partida

- City center: aleatorio en [-500, 500] cada run (`time(NULL)` seed).
- Terreno: Cellular Automata seeded random.
- Warehouses: offsets fijos relativos al city center.

Necesitamos el módulo `map_belief.py` para inferir el city center en cada run.

### Desgaste natural

Cada vehículo pierde **1 health/tick** mientras está en `SAILING`/`OFFSHORING`.
Esto significa que en ~20s sin combate ya perdiste 1000 health (te morís solo).

El reward shaping debe **descontar este desgaste** del Δhealth observado:

```python
extra_damage = max(0, (health_prev - health_now) - 1)  # restar el desgaste
```
