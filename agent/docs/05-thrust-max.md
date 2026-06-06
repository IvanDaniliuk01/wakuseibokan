# Decisión 05: subir THRUST_MAX de 10 a 50

**Fecha**: 2026-06-02
**Estado**: Aplicado coordinadamente en todo el sistema. Pendiente validación
empírica del usuario.

## Contexto

Observación empírica del usuario durante grabación de demos humanos:
**"siento que es muy lento"** — los Otters tardaban mucho en cruzar el
mapa, los combates eran lentos, y el control humano no se sentía ágil.

El valor `THRUST_MAX = 10` que veníamos usando en `encoders.py` era
arbitrario (heredado del seek_policy original). No estaba calibrado contra
los límites reales del simulador.

## Investigación

Verificación en código C++ del simulador:

1. **`src/units/Vehicle.cpp:406`** — `setThrottle(throttle)` solo asigna,
   **no clampa**.
2. **`src/units/Otter.cpp:143-146`** — `Otter::doControl` pasa el thrust
   directo a las 4 ruedas con `setThrottle()`. Tampoco clampa.
3. **`src/units/Wheel.cpp:86`** — el throttle se setea como
   `dParamVel2` (velocidad angular target del joint Hinge2 de la rueda).
   Es VELOCIDAD ANGULAR, no fuerza.
4. **`src/entities.cpp:90`** — las Wheels se instancian con
   `Wheel(faction, 0.001, 30.0)`, donde el tercer parámetro es
   `maxtorque = 30 N·m`. **Esto limita la aceleración**, no la velocidad.

**Conclusión**: el Otter no tiene clamp explícito de thrust en software.
El límite es físico (torque de las wheels, masa del vehículo, drag).
Pedir `thrust=50` produce que las wheels intenten alcanzar 50 rad/s con
un torque máximo de 30 N·m — alcanzable en estado estable, solo limita
qué tan rápido aceleramos.

## Decisión

Subir `THRUST_MAX = 50` (5× el valor anterior) coordinadamente en TODO
el sistema para mantener coherencia:

| Archivo | Variable | Antes | Ahora |
|---|---|---|---|
| `agent/encoders.py` | `THRUST_MAX` | 10.0 | **50.0** |
| `agent/human_control.py` | `HUMAN_THRUST_MAX` | 10.0 (después 30.0) | **50.0** |
| `agent/cheater_policy.py` EASY | `thrust_max` | 7.0 | 35.0 |
| `agent/cheater_policy.py` MEDIUM | `thrust_max` | 9.0 | 45.0 |
| `agent/cheater_policy.py` HARD/IMPOSSIBLE/PREDATOR/V2 | `thrust_max` | 10.0 | **50.0** |
| `agent/seek_policy.py` | `thrust_max` (rng) | uniform(7, 10) | **uniform(35, 50)** |

EASY/MEDIUM mantienen ratios relativos (70%/90% del max) para preservar
la "torpeza" relativa entre niveles.

## Tradeoffs documentados

| Tradeoff | Mitigación elegida |
|---|---|
| Control humano más violento con WASD digital | Aceptado — el humano aprende a modular |
| `dist_fire` queda "chiquito" relativo a velocidad | Mantenido a 500m — vamos a re-tunear empírico |
| Lead aim del cheater queda mal | `prediction_horizon_ticks=8` sigue funcionando porque el sim ya proyecta velocidades altas |
| Te caés al agua más fácil | Safety belts del cheater (`MAP_RECOVERY_DIST=1500`) mitigan |
| Datos viejos no son comparables | Re-recolectar dataset desde cero con thrust_max=50 |

## Validación pendiente

- Probar humano vs cheater HARD con thrust_max=50 ambos.
- Si el Otter se siente mucho más rápido visualmente → cambio queda.
- Si te chocás demasiado (control desbordado) → bajar a 35-40.
- Si no notás diferencia → hay un cuello físico (fricción, drag) y
  habría que bajar a 30 (no vale la pena más).

## Si después queremos volver atrás

Restaurar `THRUST_MAX = 10` en encoders.py y bajar proporcionalmente
todos los demás. Trivial reversión, los archivos están todos editados
en este commit.
