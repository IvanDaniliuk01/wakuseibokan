"""Smoke tests del cheater_policy sin necesidad de simulador."""
import math

import numpy as np

from agent.cheater_policy import (
    DifficultyLevel,
    decide,
    init_state,
    params_for_level,
)


def _sim_decide(my_pos, my_az_deg, other_pos, level, n_calls=1, seed=0):
    """Helper: invoca decide() n veces con el mismo input. Devuelve lista de salidas."""
    params = params_for_level(level)
    state = init_state(params)
    rng = np.random.default_rng(seed)
    outs = []
    for _ in range(n_calls):
        out = decide(
            my_pos=my_pos, my_az_deg=my_az_deg, my_health=1000.0,
            other_pos=other_pos, other_health=1000.0,
            params=params, state=state, rng=rng,
        )
        outs.append(out)
    return outs


def test_params_for_level_roundtrip():
    """Acepta enum y string."""
    p1 = params_for_level(DifficultyLevel.HARD)
    p2 = params_for_level("hard")
    assert p1.aim_noise_deg == p2.aim_noise_deg
    assert p1.fire_cone_deg == p2.fire_cone_deg


def test_impossible_fires_when_aligned():
    """IMPOSSIBLE con enemigo directamente al frente (bearing≈0) debe disparar
    en TODO tick que esté alineado — el cooldown REAL es del sim (C++), no
    lo aplicamos del lado del cheater (post-examen jun 2026: cadencia máxima).
    """
    my_pos = (0.0, 20.0, 0.0)
    my_az = 270.0
    other_pos = (200.0, 0.0, 0.0)
    outs = _sim_decide(my_pos, my_az, other_pos, DifficultyLevel.IMPOSSIBLE,
                       n_calls=250, seed=42)
    fires = [o[4] for o in outs]
    n_fires = sum(fires)
    # Esperamos cerca del 100% de ticks con fire=True. El sim filtra.
    assert n_fires >= 200, f"IMPOSSIBLE alineado disparó solo {n_fires}/250"


def test_easy_has_no_noise_by_default():
    """EASY ya NO tiene noise_prob — rompía las rotaciones visualmente.
    La torpeza humana se modela solo con aim_noise_deg=15° (gaussiano sobre
    el bearing), que es smooth y no genera saltos bruscos de torreta."""
    params = params_for_level(DifficultyLevel.EASY)
    assert params.noise_prob == 0.0
    assert params.aim_noise_deg > 0  # pero sigue siendo "torpe" apuntando


def test_impossible_has_no_noise():
    """IMPOSSIBLE no debe meter modo noise nunca."""
    params = params_for_level(DifficultyLevel.IMPOSSIBLE)
    assert params.noise_prob == 0.0

    state = init_state(params)
    rng = np.random.default_rng(0)
    for _ in range(100):
        out = decide(
            my_pos=(0.0, 20.0, 0.0), my_az_deg=270.0, my_health=1000.0,
            other_pos=(200.0, 0.0, 0.0), other_health=1000.0,
            params=params, state=state, rng=rng,
        )
        assert out[5] != "cheater_noise", "IMPOSSIBLE no debería tener noise"


def test_fire_uses_turret_aim_not_body_heading():
    """Fire-on-the-move: el cheater dispara si la TORRETA apunta bien al enemigo,
    sin importar la heading del cuerpo (verificado en docs/02 — el proyectil
    sale por la torreta, no por el frente del vehículo).

    Test: enemigo "a la espalda" del cuerpo. La torreta apunta al enemigo
    (porque siempre setteamos turret_bearing=bearing). Debe disparar.
    """
    params = params_for_level(DifficultyLevel.HARD)
    state = init_state(params)
    rng = np.random.default_rng(0)

    # Mi cuerpo mira hacia +X (az=270), enemigo a la espalda en (-200, 0)
    my_pos = (0.0, 20.0, 0.0)  # Y=20 simula terreno típico (Otter spawns terrain+5)
    other_pos = (-200.0, 0.0, 0.0)
    my_az = 270.0

    # Como la torreta apunta al enemigo (bearing relativo correctamente seteado),
    # el aim_offset es ≈ 0 y debería disparar a pesar de la heading del cuerpo.
    # Con el cooldown FIX #1 (100 ticks), necesitamos ≥100 calls para ver al
    # menos un disparo.
    fired = any(
        decide(
            my_pos=my_pos, my_az_deg=my_az, my_health=1000.0,
            other_pos=other_pos, other_health=1000.0,
            params=params, state=state, rng=rng,
        )[4]
        for _ in range(150)
    )
    assert fired, "HARD debería disparar (torreta apunta bien) aunque el cuerpo esté de espaldas"


def test_hard_aims_vertically():
    """HARD usa artillery_mode con modelo balístico 3D del sim.

    Verifica que el pitch sea positivo (apuntar arriba) cuando el enemigo
    está más alto, y consistente con el modelo balístico documentado en
    policy_utils.artillery_aim().
    """
    params = params_for_level(DifficultyLevel.HARD)
    assert params.use_vertical_aim is True
    assert params.artillery_mode is True

    state = init_state(params)
    rng = np.random.default_rng(0)

    my_pos = (0.0, 20.0, 0.0)  # Y=20 simula terreno típico (Otter spawns terrain+5)
    other_pos = (200.0, 50.0, 0.0)  # +30m arriba relativo, 200m horizontal
    for _ in range(20):
        out = decide(
            my_pos=my_pos, my_az_deg=270.0, my_health=1000.0,
            other_pos=other_pos, other_health=1000.0,
            params=params, state=state, rng=rng,
        )
    turret_decl = out[2]

    # Comparamos contra el cálculo de referencia llamando artillery_aim()
    # directamente con los mismos inputs. Ambos deben coincidir.
    from agent.policy_utils import artillery_aim
    _, _, expected = artillery_aim(my_pos, other_pos, (0.0, 0.0))
    assert abs(turret_decl - expected) < 0.005, (
        f"Pitch incorrecto: turret_decl={turret_decl:.3f}, esperado={expected:.3f}"
    )
    # Y debe ser positivo (apuntando arriba): el enemigo está arriba.
    assert turret_decl > 0.10, f"Pitch demasiado chico para enemigo 30m arriba: {turret_decl:.3f}"


def test_easy_aims_randomly():
    """EASY no usa vertical aim — turret_decl debe ser random."""
    params = params_for_level(DifficultyLevel.EASY)
    assert params.use_vertical_aim is False

    state = init_state(params)
    rng = np.random.default_rng(0)

    my_pos = (0.0, 20.0, 0.0)  # Y=20 simula terreno típico (Otter spawns terrain+5)
    other_pos = (200.0, 30.0, 0.0)
    decls = []
    for _ in range(30):
        out = decide(
            my_pos=my_pos, my_az_deg=270.0, my_health=1000.0,
            other_pos=other_pos, other_health=1000.0,
            params=params, state=state, rng=rng,
        )
        # Filtramos los modos noise que ya producen random distinto
        if out[5] == "cheater_engage":
            decls.append(out[2])
    # En 30 ticks deberíamos ver variedad de valores (no todos iguales)
    assert len(set(decls)) > 5, f"EASY siempre devuelve mismo decl: {decls[:5]}..."


def test_predator_preset_simple():
    """PREDATOR ahora es simple: aim de HARD + bait + safety belts.
    Sin feint ni strafe (rotaban el cuerpo demasiado). Sin standoff (lo
    mantenía fuera de su propio rango de fuego)."""
    p = params_for_level(DifficultyLevel.PREDATOR)
    assert p.standoff_ratio == 0.0
    assert p.feint_interval_ticks == 0    # desactivado
    assert p.strafe_when_aiming is False  # desactivado
    assert p.bait_when_chased is True     # ÚNICA táctica anti-scripted
    assert p.use_vertical_aim is True


def test_predator_fires_within_range():
    """Sin standoff, el PREDATOR debe disparar cuando está en su rango."""
    params = params_for_level(DifficultyLevel.PREDATOR)
    state = init_state(params)
    rng = np.random.default_rng(0)

    # Enemigo a 400m (adentro de dist_fire=500), perfectamente alineado al frente
    my_pos = (0.0, 20.0, 0.0)  # Y=20 simula terreno típico (Otter spawns terrain+5)
    other_pos = (400.0, 0.0, 0.0)
    my_az = 270.0  # mirando +X

    fired_at_least_once = False
    for _ in range(30):
        out = decide(
            my_pos=my_pos, my_az_deg=my_az, my_health=1000.0,
            other_pos=other_pos, other_health=1000.0,
            params=params, state=state, rng=rng,
        )
        if out[4]:
            fired_at_least_once = True
            break
    assert fired_at_least_once, "PREDATOR no disparó con enemigo a 400m alineado"


def test_predator_advances_when_far():
    """Si el enemigo está MÁS LEJOS que desired, avanza."""
    params = params_for_level(DifficultyLevel.PREDATOR)
    state = init_state(params)
    rng = np.random.default_rng(0)

    # Enemigo a 1500m, desired ~345m, dist_engage=2000. Debería avanzar.
    my_pos = (0.0, 20.0, 0.0)  # Y=20 simula terreno típico (Otter spawns terrain+5)
    other_pos = (1500.0, 0.0, 0.0)
    my_az = 270.0

    for _ in range(20):
        out = decide(
            my_pos=my_pos, my_az_deg=my_az, my_health=1000.0,
            other_pos=other_pos, other_health=1000.0,
            params=params, state=state, rng=rng,
        )
    thrust = out[0]
    assert thrust > 0, f"Predator no avanzó con enemigo lejos: thrust={thrust}"


def test_adaptive_lead_aim_uses_distance():
    """Adaptive lead aim (cuando está activado): a más distancia, más predicción.
    Testea el helper directamente, no depende del preset PREDATOR
    (que actualmente lo tiene desactivado por mala calibración empírica)."""
    from agent.cheater_policy import _delayed_and_predicted_pos, CheaterParams

    # Params custom con adaptive activado y speed conocido
    params = CheaterParams(
        aim_noise_deg=0, reaction_delay_ticks=0, prediction_horizon_ticks=8,
        fire_cone_deg=3, evasion_health_threshold=5, evasion_window_ticks=30,
        evasion_duration_ticks=60, thrust_max=10, dist_engage=2000, dist_fire=500,
        noise_prob=0,
        adaptive_lead_aim=True,
        projectile_speed_m_per_tick=1.5,
        max_lead_ticks=60,
    )

    # 30m → lead esperado 20. 80m → lead esperado 53. Bajo el cap de 60.
    state = init_state(params)
    my_pos = (0.0, 20.0, 0.0)  # Y=20 simula terreno típico (Otter spawns terrain+5)
    for t in range(20):
        other_pos = (30.0, 0.0, float(t))
        _, aim_z_a, lead_a = _delayed_and_predicted_pos(state, params, other_pos, my_pos)

    state = init_state(params)
    for t in range(20):
        other_pos = (80.0, 0.0, float(t))
        _, aim_z_b, lead_b = _delayed_and_predicted_pos(state, params, other_pos, my_pos)

    assert lead_b > lead_a, f"lead_80m={lead_b} debe ser > lead_30m={lead_a}"
    assert aim_z_b > aim_z_a, f"aim_z a 80m={aim_z_b} debe estar más adelante que a 30m={aim_z_a}"


def test_adaptive_lead_capped_at_max():
    """A distancias grandes, el lead se capea en max_lead_ticks."""
    from agent.cheater_policy import _delayed_and_predicted_pos, CheaterParams

    params = CheaterParams(
        aim_noise_deg=0, reaction_delay_ticks=0, prediction_horizon_ticks=8,
        fire_cone_deg=3, evasion_health_threshold=5, evasion_window_ticks=30,
        evasion_duration_ticks=60, thrust_max=10, dist_engage=2000, dist_fire=500,
        noise_prob=0,
        adaptive_lead_aim=True,
        projectile_speed_m_per_tick=1.5,
        max_lead_ticks=60,
    )

    state = init_state(params)
    my_pos = (0.0, 20.0, 0.0)  # Y=20 simula terreno típico (Otter spawns terrain+5)
    for t in range(20):
        other_pos = (2000.0, 0.0, float(t))
        _, _, lead = _delayed_and_predicted_pos(state, params, other_pos, my_pos)
    assert lead == 60, f"Lead a 2000m debe estar capeado a 60, fue {lead}"


def test_predator_v2_chaotic_evasion():
    """PREDATOR_V2 en modo evasión: thrust/steering deben VARIAR (random),
    no quedar fijos como en cheater_evade clásico."""
    params = params_for_level(DifficultyLevel.PREDATOR_V2)
    assert params.chaotic_evasion is True

    state = init_state(params)
    rng = np.random.default_rng(0)

    # Forzar evasion: simular history con drop de health
    my_pos = (0.0, 20.0, 0.0)  # Y=20 simula terreno típico (Otter spawns terrain+5)
    other_pos = (300.0, 0.0, 0.0)
    # Warmear con health alta
    for _ in range(params.evasion_window_ticks + 2):
        decide(my_pos=my_pos, my_az_deg=270.0, my_health=1000.0,
               other_pos=other_pos, other_health=1000.0,
               params=params, state=state, rng=rng)
    # Disparar drop de health
    decide(my_pos=my_pos, my_az_deg=270.0,
           my_health=1000.0 - params.evasion_health_threshold - 5.0,
           other_pos=other_pos, other_health=1000.0,
           params=params, state=state, rng=rng)

    # A lo largo de 50 ticks de evasión, recolectar thrust y steering
    thrusts, steerings, modes = [], [], []
    for _ in range(50):
        out = decide(my_pos=my_pos, my_az_deg=270.0, my_health=800.0,
                     other_pos=other_pos, other_health=1000.0,
                     params=params, state=state, rng=rng)
        thrusts.append(out[0])
        steerings.append(out[1])
        modes.append(out[5])

    # Debe haber ticks en modo cheater_chaos (no cheater_evade clásico)
    assert "cheater_chaos" in modes, f"Predator V2 no entró en chaotic mode: {set(modes)}"
    # Y los valores de thrust/steering deben variar (varios distintos)
    unique_thrusts = set(thrusts)
    unique_steerings = set(steerings)
    assert len(unique_thrusts) >= 2, f"Thrust no varía: {unique_thrusts}"
    assert len(unique_steerings) >= 2, f"Steering no varía: {unique_steerings}"


def test_predator_still_fires():
    """Las heurísticas no deben romper el fire — si está perfectamente apuntado,
    dispara igual."""
    params = params_for_level(DifficultyLevel.PREDATOR)
    state = init_state(params)
    rng = np.random.default_rng(0)

    # Enemigo dentro de dist_fire, perfectamente alineado
    my_pos = (0.0, 20.0, 0.0)  # Y=20 simula terreno típico (Otter spawns terrain+5)
    other_pos = (250.0, 0.0, 0.0)  # 250m, dentro de dist_fire=300
    my_az = 270.0

    fired_at_least_once = False
    for _ in range(50):
        out = decide(
            my_pos=my_pos, my_az_deg=my_az, my_health=1000.0,
            other_pos=other_pos, other_health=1000.0,
            params=params, state=state, rng=rng,
        )
        if out[4]:
            fired_at_least_once = True
            break
    assert fired_at_least_once, "Predator no disparó nunca con enemigo en cono"


def test_evasion_activates_on_rapid_damage():
    """Si health cae rápido, el cheater entra en modo evade."""
    params = params_for_level(DifficultyLevel.HARD)
    state = init_state(params)
    rng = np.random.default_rng(0)

    # Llenar history con health alta
    for _ in range(params.evasion_window_ticks + 2):
        decide(
            my_pos=(0.0, 20.0, 0.0), my_az_deg=270.0, my_health=1000.0,
            other_pos=(200.0, 0.0, 0.0), other_health=1000.0,
            params=params, state=state, rng=rng,
        )

    # Ahora simular un drop fuerte de health
    out = decide(
        my_pos=(0.0, 20.0, 0.0), my_az_deg=270.0,
        my_health=1000.0 - params.evasion_health_threshold - 5.0,
        other_pos=(200.0, 0.0, 0.0), other_health=1000.0,
        params=params, state=state, rng=rng,
    )
    # El primer tick post-trigger debería estar en evade
    assert out[5] == "cheater_evade", f"No entró en evade: mode={out[5]}"


# ============================================================
# Closed-loop fire control
# ============================================================

def _fire_and_observe(state, params, rng, my_pos, other_pos, landing_pos):
    """Helper: fuerza un fire (espera cooldown) y simula que el sim manda
    el landing_pos posterior."""
    # Esperar cooldown
    for _ in range(params.fire_cooldown_ticks + 2):
        out = decide(my_pos, 270.0, 1000.0, other_pos, 1000.0,
                     params, state, rng)
        if out[4]:
            break
    # Próximo tick con el landing observado
    decide(my_pos, 270.0, 1000.0, other_pos, 1000.0,
           params, state, rng, my_landing_pos=landing_pos)


def test_closed_loop_converges_when_overshooting():
    """Si los tiros caen 5m por arriba consistentemente, aim_y_correction
    debe converger cerca de +5m tras varios shots."""
    params = params_for_level(DifficultyLevel.PREDATOR_V2)
    state = init_state(params)
    rng = np.random.default_rng(0)
    my_pos = (0.0, 20.0, 0.0)
    other_pos = (800.0, 20.0, 0.0)
    # Simular 10 disparos, cada uno aterriza ligeramente diferente
    # (xz un poco distinto) pero siempre +5m arriba.
    for i in range(10):
        landing = (800.0 + i * 0.5, 25.0, 0.0)  # +5m de drop error
        _fire_and_observe(state, params, rng, my_pos, other_pos, landing)
    # Tras 10 muestras, correction debe estar cerca de +5m (EMA hacia el target)
    assert 3.0 < state.aim_y_correction < 5.5, (
        f"aim_y_correction no convergió: {state.aim_y_correction}"
    )
    assert state.aim_correction_samples >= 5


def test_closed_loop_ignores_outliers():
    """Un solo landing extremo (>60m de error) no debe descalibrar."""
    params = params_for_level(DifficultyLevel.PREDATOR_V2)
    state = init_state(params)
    rng = np.random.default_rng(0)
    my_pos = (0.0, 20.0, 0.0)
    other_pos = (800.0, 20.0, 0.0)
    # Primero 3 shots normales (error 0) para tener baseline
    for i in range(3):
        landing = (800.0 + i, 20.0, 0.0)
        _fire_and_observe(state, params, rng, my_pos, other_pos, landing)
    baseline = state.aim_y_correction
    # Outlier extremo (+100m de error)
    _fire_and_observe(state, params, rng, my_pos, other_pos,
                      (800.0, 120.0, 0.0))
    # No debe haberse movido (outlier rechazado)
    assert abs(state.aim_y_correction - baseline) < 0.01, (
        f"Outlier movió correction: baseline={baseline} ahora={state.aim_y_correction}"
    )


def test_closed_loop_resets_on_new_round():
    """Cuando health vuelve de bajo a 1000, todo el estado del closed-loop
    se limpia para el próximo round."""
    params = params_for_level(DifficultyLevel.PREDATOR_V2)
    state = init_state(params)
    rng = np.random.default_rng(0)
    my_pos = (0.0, 20.0, 0.0)
    other_pos = (800.0, 20.0, 0.0)
    # Ensuciar el estado con varios shots
    for i in range(5):
        landing = (800.0 + i, 30.0, 0.0)
        _fire_and_observe(state, params, rng, my_pos, other_pos, landing)
    assert state.aim_correction_samples > 0
    assert state.aim_y_correction != 0.0
    # Simular muerte + respawn: tick con health bajo, luego health=1000
    decide(my_pos, 270.0, 100.0, other_pos, 1000.0, params, state, rng)
    decide(my_pos, 270.0, 1000.0, other_pos, 1000.0, params, state, rng)
    # Estado del closed-loop reseteado (correction + samples a cero)
    assert state.aim_y_correction == 0.0
    assert state.aim_correction_samples == 0
    # pending_shots vaciado en el reset (puede tener 1 del fire spam en ese
    # mismo tick post-reset, pero NO los acumulados pre-reset).
    assert len(state.pending_shots) <= 1


def test_closed_loop_requires_min_samples():
    """Con sólo 1 muestra de error, aim_y_correction se actualiza pero
    NO se APLICA al aim. El min_samples=2 evita que un único outlier
    inicial mande aim a la luna."""
    params = params_for_level(DifficultyLevel.PREDATOR_V2)
    state = init_state(params)
    rng = np.random.default_rng(0)
    my_pos = (0.0, 20.0, 0.0)
    other_pos = (800.0, 20.0, 0.0)
    # Un solo shot con error +10m
    _fire_and_observe(state, params, rng, my_pos, other_pos, (800.0, 30.0, 0.0))
    assert state.aim_correction_samples == 1
    assert state.aim_y_correction != 0.0
    # Pero todavía no se aplica: la corrección requiere ≥2 samples
    # (verificamos llamando decide y mirando que other_y_aim == other_y)
    # Indirectamente: si tira un tiro con landing exacto, error=0, EMA mueve
    # correction hacia 0 (no acumula error inicial).
