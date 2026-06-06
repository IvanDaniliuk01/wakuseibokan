# Decisión 03: observabilidad en eval — tenemos telemetría del enemigo

**Fecha**: 2026-05-31
**Estado**: Confirmada con Ramele. El diseño actual del encoder es válido.

## Contexto

Antes de invertir tiempo en training, hubo que resolver una pregunta crítica:
¿qué telemetría va a tener disponible el agente durante la evaluación final
del curso? Hay dos escenarios extremos:

- **A — Telemetría completa**: el agente ve también la pose y health del
  oponente. Problema es un MDP. El encoder se puede construir directamente
  con esa info.
- **B — Solo telemetría propia (POMDP)**: el agente solo conoce su propia
  pose, health, power y `landingPos` (señales indirectas de "me dispararon
  desde acá"). Hay que inferir al enemigo. Requiere history en el estado o
  state estimator LSTM.

La diferencia entre A y B es brutal: A es "RL clásico", B es "RL en partial
observability" y agrega complejidad y tiempo de entrenamiento de 5-10x.

## Decisión

**Ramele confirmó que la evaluación final del curso provee telemetría
completa de ambos vehículos al agente.** Por lo tanto:

- El agente puede usar pose, azimuth, health y power del enemigo directamente.
- El problema es un MDP, no un POMDP.
- No hace falta state estimator (LSTM) ni frame stacking para inferir al
  enemigo.

## Consecuencias para el código

El `encode_state` actual en `agent/encoders.py:23-56` es **correcto** y se
mantiene. Sus 12 features incluyen:

```
pos_me_x, pos_me_z, cos(az_me), sin(az_me), health_me, power_me,
dx, dz, dist, cos(bearing_rel), sin(bearing_rel), health_oth
```

Las 6 features que dependen del enemigo (`dx`, `dz`, `dist`,
`cos(bearing_rel)`, `sin(bearing_rel)`, `health_oth`) son **legítimas en
deployment** porque la eval va a proporcionar esa info.

## Por qué esto facilita TODO el resto del proyecto

1. **Sin state estimator**: no hay que implementar ni entrenar una LSTM
   adicional para inferir la pose del enemigo. Ahorro estimado: 1-2 semanas.
2. **Sin frame stacking complicado**: el estado actual de 12-D alcanza. La
   red puede ser un MLP simple [256, 256] sin necesidad de RNN.
3. **El dataset existente sirve tal cual**: los HDF5 que ya generamos con
   `observe.py` y los que generemos con `collect_vs_cheater.py` tienen la
   telemetría de ambos vehículos, que es exactamente lo que se va a usar
   tanto en training como en eval.
4. **El reward es exacto**: `compute_step_reward` necesita ambos healths
   para calcular kill bonus / death penalty. Con telemetría completa esto
   se calcula en tiempo real sin estimación.
5. **El cheater como oponente sigue válido**: la asimetría no es que el
   cheater "ve más" — los dos ven todo. La asimetría es que el cheater
   APLICA esa info con scripts perfectos (lead aim, fire cone angosto),
   mientras que el agente aprendido tiene que descubrir cómo usarla.

## Lo que sigue NO siendo necesario

- `agent/state_estimator.py` (LSTM para belief del enemigo)
- `agent/map_belief.py` (inferir city center) — el city center solo importa
  si el enemigo es invisible y hay que buscarlo. Con telemetría completa,
  vamos directo al enemigo.
- Frame stacking en `encode_state`
- Cualquier history-based feature de `landingPos`

Estos archivos pueden borrarse del roadmap. Ahorra trabajo y simplifica
el agente.

## Confirmación pendiente

Si en algún momento las reglas de eval cambian o se aclara algún detalle
(por ej. "telemetría completa pero con 200ms de delay" o "telemetría sin
health del enemigo"), revisar esta decisión y actualizar `encode_state`
acordemente.
