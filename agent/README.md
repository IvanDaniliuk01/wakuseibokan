# Agent — Otter Physical AI

Agente Python que controla un Otter en Wakuseibokan vía UDP y aprende a combatir
contra otro Otter usando Reinforcement Learning (SAC).

## Estructura

```
agent/
├── packet_format.py    # Parse/pack de ModelRecord, ControlStructure2, TickRecord
├── udp_io.py           # Cliente UDP: telemetría individual + Lobby
├── state_encoder.py    # Convierte ModelRecord crudo en vector de features
├── dispatcher.py       # Acción → ControlStructure2 + trigger discipline
├── map_belief.py       # (PENDIENTE) Belief incremental del city center
├── state_estimator.py  # (PENDIENTE) LSTM que infiere belief enemigo
├── env.py              # (PENDIENTE) Gymnasium env wrapper
├── train.py            # (PENDIENTE) Script de entrenamiento SAC
├── eval.py             # (PENDIENTE) Script de evaluación
├── tests/              # Tests unitarios
└── requirements.txt
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
make
```

### 2. Levantar el simulador con testcase 131

```bash
./testcase -mute -nointro -testcase 131
```

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

### 4. Probar el state encoder con datos falsos

```bash
python -m agent.state_encoder
```

### 5. Probar el dispatcher

```bash
python -m agent.dispatcher
```

## Roadmap de implementación

### Semana 1 — Pipeline mínimo + dataset

- [x] `packet_format.py` — structs UDP
- [x] `udp_io.py` — cliente UDP
- [x] `state_encoder.py` — encoder básico (18 floats)
- [x] `dispatcher.py` — comando + trigger discipline
- [ ] Capturar paquetes reales del Lobby para confirmar formato del TickRecord
- [ ] `env.py` — Gymnasium env mínimo (con random policy)
- [ ] Recolectar 200-500 episodios para dataset

### Semana 2 — Imitation learning + State Estimator

- [ ] `state_estimator.py` — LSTM para belief del enemigo
- [ ] `map_belief.py` — belief del city center
- [ ] Entrenar State Estimator supervisado con GT del Lobby
- [ ] Imitation learning warm-start de la política

### Semana 3 — SAC

- [ ] `train.py` — script SAC con stable-baselines3
- [ ] Training offline con CQL en Colab
- [ ] Eval vs baseline

### Semana 4 — Refinement + entrega

- [ ] Opcional: self-play
- [ ] Eval final
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
