# Decisión 04: cheater PREDATOR — extender el cheater con tácticas anti-scripted

**Fecha**: 2026-05-31
**Estado**: Diseño aprobado, implementación en curso.

## Contexto

El cheater_policy.py actual tiene 4 niveles (EASY → IMPOSSIBLE) que escalan
en **skill mecánico**: apuntado más preciso, reacción más rápida, lead aim
más agresivo, cono de fuego más angosto. Pero **NO escalan en sofisticación
táctica** — los 4 niveles siguen el mismo patrón "perseguir, apuntar,
disparar".

Si la red entrenamos contra HARD/IMPOSSIBLE y los oponentes reales del
curso son scripts similares pero con **alguna táctica anti-scripted** (lo
más probable, según conversación con Ramele), nuestra red va a estar
sub-preparada para esos comportamientos.

## Decisión

Crear un **nuevo nivel `PREDATOR`** que tiene el aim de HARD pero agrega
4 heurísticas anti-scripted específicamente diseñadas para explotar las
debilidades típicas de un controlador scripted seek-and-destroy.

## Las 4 heurísticas y qué debilidad explotan

| Heurística | Debilidad típica que explota | Implementación |
|---|---|---|
| **Standoff** | El otro persigue ciegamente sin pensar en distancia óptima | Mantenerse a `1.15 × dist_fire_oponente` — yo disparo, él no |
| **Bait** | El otro avanza siempre que esté en rango | Si detecto que se acerca rápido, retroceder + flanquear |
| **Feint** | El otro hace lead aim con velocidad constante extrapolada | Cambios bruscos de dirección cada N ticks → rompe la predicción |
| **Strafe** | El otro apunta con la torreta donde estoy AHORA | Mientras apunto, moverme lateral → el otro me apunta a donde estuve |

Una quinta táctica (**disparar mientras me alejo**, usando torreta
independiente del cuerpo) queda como nota para futuro — requiere que el
cheater explote la independencia torreta/cuerpo que aún no usa.

## Diseño de implementación

### Estructura

Mantener TODO en `cheater_policy.py` (no crear archivo nuevo). Agregar
parámetros opcionales al `CheaterParams` que **por default están desactivados**.
Los presets actuales (EASY/MEDIUM/HARD/IMPOSSIBLE) no cambian. El nuevo
preset `PREDATOR` los activa.

### `CheaterParams` agregados

```python
standoff_ratio: float = 0.0           # 0 = desactivado. Si > 0:
                                      #   mantenerse a (standoff_ratio × dist_fire)
                                      #   del enemigo (ej: 1.15 = 15% más lejos)

feint_interval_ticks: int = 0         # 0 = desactivado. Si > 0:
                                      #   cada N ticks cambia bruscamente steering_dir

feint_intensity: float = 0.0          # cuán fuerte el feint (0-1)

strafe_when_aiming: bool = False      # mientras apunta, mover lateral

bait_when_chased: bool = False        # si el enemigo se acerca rápido, retroceder
bait_approach_threshold: float = 50.0 # cuántos metros de cambio de dist por segundo cuenta
```

### Preset PREDATOR

```python
DifficultyLevel.PREDATOR: CheaterParams(
    # Aim del HARD (NO de IMPOSSIBLE — el predator no es invencible mecánicamente):
    aim_noise_deg=2.0,
    reaction_delay_ticks=2,
    prediction_horizon_ticks=8,
    fire_cone_deg=3.0,
    use_vertical_aim=True,

    # Defensivo:
    evasion_health_threshold=5.0,
    evasion_window_ticks=30,
    evasion_duration_ticks=60,

    # Movilidad:
    thrust_max=10.0,
    dist_engage=2000.0,
    dist_fire=300.0,        # un poco más largo que HARD
    noise_prob=0.0,

    # NUEVAS heurísticas anti-scripted:
    standoff_ratio=1.15,
    feint_interval_ticks=30,
    feint_intensity=0.7,
    strafe_when_aiming=True,
    bait_when_chased=True,
)
```

### Modificaciones al `decide()`

El flujo nuevo es:

```
1. NOISE override (igual)
2. Trigger evasivo (igual)
3. Calcular aim retrasado/predicho (igual)
4. Calcular bearing + aim noise (igual)
5. Calcular pitch (igual)

6. [NUEVO] Detectar si el enemigo se acerca rápido (para bait)
7. [NUEVO] Decidir si activar feint este tick

8. Modo evasivo (igual)

9. Engage modificado:
   a. Si standoff_ratio > 0:
      - desired_dist = standoff_ratio * dist_fire_propio
      - Si target_dist < desired_dist (estoy demasiado cerca): RETROCEDER
      - Si target_dist > dist_engage: avanzar (igual que antes)
      - Si en el "sweet spot" [desired_dist, dist_engage]: mantener distancia,
        steering según bearing pero sin avanzar
   b. Si bait_when_chased y enemy_approaching: forzar retroceso + steering perpendicular
   c. Si feint_interval_ticks reached: invertir steering_dir
   d. Si strafe_when_aiming y estoy en cono: agregar componente lateral al steering
   e. Disparar si en cono (igual)
```

### Win-rate esperado del PREDATOR

Si la calibración funciona, PREDATOR debería ganarle:
- A seek_policy: **~85%** (vs ~15% que pierde HARD)
- A cheater HARD: **~65%**
- A cheater IMPOSSIBLE: **~30%**
- A otra instancia de sí mismo (PREDATOR vs PREDATOR): ~50%

Estas son hipótesis. Hay que calibrar empíricamente con 10-20 episodios por
matchup antes de incluirlo en el dataset masivo.

## Nuevo mix-plan propuesto para el dataset

Si PREDATOR se calibra como esperamos, agregar al mix sin remover los demás:

```
easy:80,medium:200,hard:300,impossible:50,predator:170 → 800 episodios
```

Razonamiento de proporciones:
- **easy:80** — calentamiento, win fácil para que el dataset tenga victorias
- **medium:200** — oponente realista
- **hard:300** — oponente realista pero competente (volumen alto)
- **impossible:50** — letalidad mecánica (poco, sigue siendo overkill)
- **predator:170** — **lo que probablemente sea el oponente real del curso**.
  Volumen alto para que la red vea muchos casos.

## Cómo conecta con el resto del pipeline

1. `cheater_policy.py` se extiende con nuevos campos + heurísticas.
2. `collect_vs_cheater.py` automáticamente acepta `predator` en el
   `--mix-plan` (porque parsea `DifficultyLevel`).
3. El dataset HDF5 marca `_opponent_level="predator"` por episodio.
4. Durante training, el modelo aprende que el opponent_level no es feature
   directa (no ve qué tipo de oponente tiene) — debe inferirlo por
   comportamiento.

## Tests a agregar

- `test_predator_maintains_standoff`: con enemigo a 100m y `dist_fire=300`,
  el predator debe retroceder (thrust negativo).
- `test_predator_feints`: a lo largo de 100 ticks, la dir de steering debe
  cambiar al menos `100/feint_interval ± 1` veces.
- `test_predator_baits_when_chased`: con enemigo acercándose rápido y
  cerca, el predator retrocede.
- `test_predator_fire_still_works`: el predator igual dispara cuando está
  en cono. Si las heurísticas rompen el fire, está mal.

## Riesgos

- **Calibración delicada**: 4 heurísticas que se influencian entre sí
  (standoff vs avanzar vs bait...) — fácil que se contradigan y el
  predator quede paralizado o errático. Mitigación: priorizar las
  heurísticas (bait > standoff > feint > strafe).
- **Win-rate impredecible**: las hipótesis del win-rate son optimistas.
  La calibración real puede dar números muy distintos. Mitigación: probar
  con 20 episodios contra cada nivel antes del run grande.
- **Más complejidad en el código**: el `decide()` se vuelve largo.
  Mitigación: comentar muy bien cada heurística + tests específicos.
