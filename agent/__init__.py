"""Wakuseibokan Otter Agent — Physical AI con offline RL + online SAC.

Estructura:
    packet_format    : parse/pack de ModelRecord y ControlStructure2
    udp_io           : cliente UDP base + SharedTelemetryHub (telemetría thread-safe)
    encoders         : encode_state (12-D) y decode_action (6-D) — single source
                       of truth para training y deployment
    reward           : reward shaping del combate (función pura)
    policy_utils     : helpers compartidos entre seek y cheater (azimuth, bearing)
    seek_policy      : política scripted con 4 modos (engage/escape/evasive/noise)
                       — usada como "fábrica de datos" del Otter 1
    cheater_policy   : oponente con información privilegiada y 4 niveles de
                       dificultad — usado como Otter 2 en training
    env              : Gymnasium env wrapper (online RL con SAC)
    collect_vs_cheater: recolector con cheater oponente en proceso único
    eval             : evaluación de modelos entrenados contra oponente externo
"""
