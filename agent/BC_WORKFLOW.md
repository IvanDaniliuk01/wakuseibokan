# BC Workflow — 1 día para entregar

Pipeline para entrenar un agente Otter por Behavioral Cloning (clonando al
cheater PREDATOR_V2), evaluarlo, y entregar.

**Importante**: corré los 3 pasos en orden. Cada uno espera una ÚNICA instancia
del sim corriendo. Si tenés varios sims abiertos, cerralos todos primero.

---

## Paso 1: Recolectar el dataset (~1.5–4 h dependiendo de eps)

Lanza el sim automáticamente (con `--launch-sim`), graba 150 eps con el
PREDATOR_V2 como Otter 1 (lo que la red va a clonar) contra un mix balanceado
de oponentes (EASY/MEDIUM/HARD/IMPOSSIBLE/PREDATOR_V2), relanzando el sim
cada 30 eps para diversidad de mapa.

```bash
python3 -u -m agent.collect_vs_cheater \
  --difficulty mixed \
  --mix-plan "easy:30,medium:30,hard:30,impossible:30,predator_v2:30" \
  --player-level predator_v2 \
  --output data/train/bc_dataset.h5 \
  --launch-sim \
  --relaunch-every 30 \
  --max-seconds 300 \
  --inter-episode-wait 4 \
  --seed 42
```

**El archivo se guarda incrementalmente** (cada ep), entonces si se corta
por error/Ctrl-C el dataset hasta ese punto se conserva.

Mientras corre, mirá el progreso con:
```bash
tail -f /tmp/collect.log  # o redirigís stdout vos
```

Output esperado por ep:
```
=== Ep 47/150 vs hard ===
  [WIN ] ticks=812  min_dist=294m  had_encounter=True  modes={'cheater_engage': ...}
  → ep guardado incrementalmente (47 eps en total)
```

---

## Paso 2: Entrenar la red (~5 min local CPU, ~1 min GPU Colab)

```bash
python3 -m agent.train_bc \
  --dataset data/train/bc_dataset.h5 \
  --output  models/bc_otter.pt \
  --epochs  30 \
  --batch   256 \
  --lr      3e-4
```

Output esperado:
```
Cargando dataset: data/train/bc_dataset.h5
  Eps totales:    150
  Eps válidos:    142     ← descarta los sin combate
  Samples (s,a):  124_580

  Ep   1/30  tr_loss=0.182  va_loss=0.165  fire_acc=0.91 (0.4s)
  Ep   2/30  tr_loss=0.094  va_loss=0.087  fire_acc=0.94 (0.3s)
  ...
  Ep  30/30  tr_loss=0.018  va_loss=0.022  fire_acc=0.98 (0.3s)

✓ Modelo guardado en models/bc_otter.pt
```

**Si querés correrlo en Colab GPU**: subí el .h5 a Drive, abrí Colab con
GPU, cloná el repo o subí `agent/train_bc.py` + `agent/encoders.py`, y
corré el mismo comando.

---

## Paso 3: Evaluar el modelo (~10 min, 20 eps vs predator_v2)

Antes de correr eval, **lanzá el sim a mano** en otra terminal:
```bash
./testcase -mute -nointro -episodes
```

Y en otra terminal:
```bash
python3 -m agent.eval_bc \
  --model models/bc_otter.pt \
  --opponent predator_v2 \
  --episodes 20 \
  --max-seconds 120
```

Output esperado:
```
Cargando modelo: models/bc_otter.pt
BC agent (Otter 1) vs predator_v2 (Otter 2) — 20 eps

=== Ep 1/20 vs predator_v2 ===
  [WIN ]  h_a=120  h_b=-40  ticks~890
=== Ep 2/20 vs predator_v2 ===
  [LOSS]  h_a=-200  h_b=640  ticks~520
...

==================================================
Eval: BC vs predator_v2
  Episodios: 20
  Wins:    9 (45%)
  Losses:  8 (40%)
  Draws:   3 (15%)
```

**Target**: ≥ 40% win rate vs predator_v2. Si está peor, posibles fixes:
- Recolectar más datos (300+ eps en vez de 150)
- Más épocas de training (50+)
- Cambiar la red a hidden=256

---

## Atajos útiles

### Inspeccionar dataset rápido
```bash
python3 -c "
import h5py
with h5py.File('data/train/bc_dataset.h5') as f:
    print('eps:', f.attrs['n_episodes'])
    n_combat = sum(1 for k in f if f[k].attrs.get('had_encounter', False))
    print('eps con combate:', n_combat)
    outcomes = [f[k].attrs.get('outcome', '?') for k in f]
    from collections import Counter
    print('outcomes:', Counter(outcomes))
"
```

### Si algo se cuelga
```bash
# Matar todo:
pkill -f 'agent.collect\|agent.train_bc\|agent.eval_bc\|testcase'
```

### Cambiar el oponente del eval
```bash
python3 -m agent.eval_bc --model models/bc_otter.pt --opponent hard
python3 -m agent.eval_bc --model models/bc_otter.pt --opponent impossible
```

---

## Estructura de archivos

```
agent/
├── collect_vs_cheater.py    # Paso 1: recolección
├── train_bc.py              # Paso 2: training BC
├── eval_bc.py               # Paso 3: eval
├── cheater_policy.py        # PREDATOR_V2 y otros niveles
├── encoders.py              # state/action encoders (SOT)
├── policy_utils.py          # artillery_aim, etc.
└── human_control.py         # SimLauncher (reutilizado por collect)

data/train/
├── bc_dataset.h5            # Output paso 1
└── ...

models/
└── bc_otter.pt              # Output paso 2
```
