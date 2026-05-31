"""Wakuseibokan Otter Agent — Physical AI con SAC.

Estructura:
    packet_format    : parse/pack de ModelRecord y ControlStructure2
    udp_io           : cliente UDP (recv telemetría, send comandos)
    state_encoder    : convierte telemetría cruda a vector de features
    map_belief       : belief incremental del city center
    state_estimator  : LSTM que infiere belief del enemigo
    dispatcher       : trigger discipline + envío de comandos
    env              : Gymnasium environment wrapper
    train            : script de entrenamiento SAC
    eval             : script de evaluación
"""
