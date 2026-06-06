"""Cheater IMPOSSIBLE standalone — Wakuseibokan testcase 131.

Versión simplificada del CheaterParams.IMPOSSIBLE de agent/cheater_policy.py,
sin dependencias del repo. Sólo stdlib.

Asume que el simulador corre en otra máquina (LAN). El sim manda telemetría
de AMBOS vehículos a tu puerto local, y este script controla uno.

USO:
    python3 impossible.py --my-tank 2 --sim-ip 192.168.0.221

Ctrl-C para salir.

Comportamiento:
- aim perfecto (sin ruido), reacción instantánea
- lead aim de 12 ticks
- pitch de torreta calculado al centro del enemigo
- engage hasta 2000m, dispara hasta 500m (sweet spot 700m)
- cooldown real del cañón: 2.0s (100 ticks)
- evade caótico cuando recibe >3 health en 25 ticks
"""
import argparse
import math
import socket
import struct
import sys
import time
from collections import deque


# ============================================================
# Wire formats (idéntico a packet_format.py)
# ============================================================

# ModelRecord = 96 bytes:
#   <IIifif3f3f12f
#   recordtimer(u32), lastUpdateTimer(u32), number(i32), health(f),
#   power(i32), azimuth(f), landingPos(3f), pos(3f), rotation(12f)
MR_FMT = "<IIifif3f3f12f"
MR_SIZE = struct.calcsize(MR_FMT)
assert MR_SIZE == 96

# ControlStructure2 = 68 bytes:
#   <i6fiiii3fiiI
CS2_FMT = "<i6fiiii3fiiI"
CS2_SIZE = struct.calcsize(CS2_FMT)
assert CS2_SIZE == 68

CMD_NONE = 0
CMD_FIRE = 11


def parse_modelrecord(data):
    u = struct.unpack(MR_FMT, data)
    return {
        "recordtimer": u[0],
        "number": u[2],
        "health": u[3],
        "azimuth": u[5],
        "pos": (u[9], u[10], u[11]),
    }


def pack_control(controllingid, faction, thrust, steering, precesion,
                 fire, sourcetimer):
    """precesion = pitch de torreta (rad). steering = yaw."""
    return struct.pack(
        CS2_FMT,
        controllingid,
        float(thrust),   # thrust
        0.0,             # roll
        0.0,             # pitch del cuerpo (no usado)
        float(steering), # yaw → steering ModAngleZ
        float(precesion),# precesion → torreta pitch
        0.0,             # bank
        int(faction),
        int(CMD_FIRE if fire else CMD_NONE),
        0, 0,            # spawnid, typeofisland
        0.0, 0.0, 0.0,   # x, y, z
        0, 0,            # target_type, weapon
        int(sourcetimer),
    )


# ============================================================
# Geometría (idéntico a policy_utils.py)
# ============================================================

def azimuth_deg(x1, z1, x2, z2):
    """Ángulo (x1,z1)→(x2,z2) en convención del sim."""
    val = math.degrees(math.atan2(z2 - z1, x2 - x1))
    return (val - 90) if val >= 90 else (val + 270)


def relative_bearing_deg(my_x, my_z, my_az_deg, other_x, other_z):
    raw = azimuth_deg(my_x, my_z, other_x, other_z) - my_az_deg
    return (raw + 180.0) % 360.0 - 180.0


# Cañón está físicamente 2.3m sobre el centro del Otter
GUN_OFFSET_Y = 2.3


def pitch_to_target_rad(my_y, other_y, horiz_dist):
    real_dy = (other_y - my_y) - GUN_OFFSET_Y
    return math.atan2(real_dy, max(horiz_dist, 1.0))


# ============================================================
# Política IMPOSSIBLE
# ============================================================

# Params IMPOSSIBLE (de cheater_policy.py:175-188)
THRUST_MAX = 50.0
DIST_ENGAGE = 2000.0
DIST_FIRE = 500.0
DIST_FIRE_EFFECTIVE = 700.0   # más allá de esto el sim no impacta
FIRE_CONE_DEG = 2.0
REACTION_DELAY_TICKS = 0
PREDICTION_HORIZON_TICKS = 12
EVASION_HEALTH_THRESHOLD = 3.0
EVASION_WINDOW_TICKS = 25
EVASION_DURATION_TICKS = 70
FIRE_COOLDOWN_TICKS = 100      # = setTtl(100) = 2.0s
BEARING_RATE_SUPPRESS_DEG = 6.0
BEARING_RATE_WINDOW = 5
TOO_CLOSE_M = 60.0             # proyectil spawnea 40m adelante


class State:
    def __init__(self):
        # historiales con suficiente largo para delay + lead + suppression
        maxlen = max(REACTION_DELAY_TICKS + PREDICTION_HORIZON_TICKS + 5, 10)
        self.enemy_pos_history = deque(maxlen=maxlen)
        self.health_history = deque(maxlen=EVASION_WINDOW_TICKS + 5)
        self.bearing_history = deque(maxlen=BEARING_RATE_WINDOW + 2)
        self.evasion_left = 0
        self.evasion_dir = 1.0
        self.ticks_since_fire = FIRE_COOLDOWN_TICKS  # arranca listo
        self._rng_state = 0xC0FFEE                    # LCG simple

    def rand_choice_pm1(self):
        # No queremos numpy. LCG → ±1
        self._rng_state = (self._rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        return 1.0 if (self._rng_state >> 16) & 1 else -1.0


def decide(my_x, my_y, my_z, my_az_deg, my_health,
           other_x, other_y, other_z, other_health, state: State):
    """Devuelve (thrust, steering, precesion_pitch, fire)."""
    state.health_history.append(float(my_health))

    # 1) Detectar daño rápido → evade
    if state.evasion_left == 0 and len(state.health_history) > EVASION_WINDOW_TICKS:
        h_old = state.health_history[-EVASION_WINDOW_TICKS]
        if (h_old - my_health) > EVASION_HEALTH_THRESHOLD:
            state.evasion_left = EVASION_DURATION_TICKS
            state.evasion_dir = state.rand_choice_pm1()

    # 2) Posición efectiva del enemigo (delay + lead aim)
    state.enemy_pos_history.append((other_x, other_z))
    hist = list(state.enemy_pos_history)
    n = len(hist)
    delay_idx = max(0, n - 1 - REACTION_DELAY_TICKS)
    seen_x, seen_z = hist[delay_idx]

    if PREDICTION_HORIZON_TICKS > 0 and delay_idx > 0:
        prev_idx = max(0, delay_idx - 3)
        prev_x, prev_z = hist[prev_idx]
        dt = max(1, delay_idx - prev_idx)
        vx = (seen_x - prev_x) / dt
        vz = (seen_z - prev_z) / dt
        aim_x = seen_x + vx * PREDICTION_HORIZON_TICKS
        aim_z = seen_z + vz * PREDICTION_HORIZON_TICKS
    else:
        aim_x, aim_z = seen_x, seen_z

    bearing = relative_bearing_deg(my_x, my_z, my_az_deg, aim_x, aim_z)
    target_dist = math.sqrt((aim_x - my_x) ** 2 + (aim_z - my_z) ** 2)
    polar_d = math.sqrt(my_x ** 2 + my_z ** 2)

    # Pitch de torreta (use_vertical_aim=True en IMPOSSIBLE)
    precesion = pitch_to_target_rad(my_y, other_y, max(target_dist, 1.0))
    precesion = max(-0.4, min(0.4, precesion))

    # 3) Modo evasivo predecible (IMPOSSIBLE no usa chaotic)
    if state.evasion_left > 0:
        state.evasion_left -= 1
        state.ticks_since_fire += 1
        return (-THRUST_MAX * 0.7, state.evasion_dir, precesion, False)

    # 4) Engage normal
    real_dx = other_x - my_x
    real_dz = other_z - my_z
    real_dist = math.sqrt(real_dx * real_dx + real_dz * real_dz)
    too_close = real_dist < TOO_CLOSE_M

    if too_close:
        thrust = -THRUST_MAX
        steering = 1.0 if bearing > 0 else -1.0
        state.ticks_since_fire += 1
        return (thrust, steering, precesion, False)

    if polar_d < DIST_ENGAGE:
        thrust = THRUST_MAX
    else:
        thrust = 0.0

    if bearing > 0:
        steering = 1.0
    elif bearing < 0:
        steering = -1.0
    else:
        steering = 0.0

    # 5) Fire decision (cono + cooldown + suppression + sweet spot)
    aim_dx = aim_x - my_x
    aim_dz = aim_z - my_z
    cross = aim_dx * real_dz - aim_dz * real_dx
    dot = aim_dx * real_dx + aim_dz * real_dz
    aim_offset_deg = math.degrees(math.atan2(cross, dot))

    # Bearing rate suppression: si el enemigo gira rápido relativo a mí,
    # el aim se va a desfasar antes de impactar
    world_az_to_enemy = azimuth_deg(my_x, my_z, other_x, other_z)
    state.bearing_history.append(world_az_to_enemy)
    bearing_rate_high = False
    if len(state.bearing_history) >= BEARING_RATE_WINDOW + 1:
        recent = list(state.bearing_history)[-(BEARING_RATE_WINDOW + 1):]
        d_b = (recent[-1] - recent[0] + 180.0) % 360.0 - 180.0
        if abs(d_b) > BEARING_RATE_SUPPRESS_DEG:
            bearing_rate_high = True

    state.ticks_since_fire += 1
    cooldown_ready = state.ticks_since_fire >= FIRE_COOLDOWN_TICKS
    too_far = real_dist > DIST_FIRE_EFFECTIVE

    fire = (real_dist < DIST_FIRE and
            abs(aim_offset_deg) < FIRE_CONE_DEG and
            cooldown_ready and
            not bearing_rate_high and
            not too_far)
    if fire:
        state.ticks_since_fire = 0

    return (thrust, steering, precesion, fire)


# ============================================================
# Main loop
# ============================================================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--my-tank", type=int, required=True, choices=[1, 2],
                   help="Vehículo a controlar (1 o 2)")
    p.add_argument("--sim-ip", type=str, required=True,
                   help="IP de la máquina donde corre el simulador")
    p.add_argument("--tick-dt", type=float, default=0.05,
                   help="20 ms = 50 Hz del sim")
    args = p.parse_args()

    my_vid = args.my_tank
    other_vid = 2 if my_vid == 1 else 1
    recv_port = 4600 + my_vid
    send_port = 4500 + my_vid

    sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_recv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock_recv.bind(("0.0.0.0", recv_port))
    sock_recv.settimeout(0.5)

    sock_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send_addr = (args.sim_ip, send_port)

    print(f"IMPOSSIBLE cheater controlando vehículo #{my_vid}")
    print(f"  recv 0.0.0.0:{recv_port}  →  send {args.sim_ip}:{send_port}")
    print("Esperando telemetría...")

    state = State()
    latest = {}        # vid → dict
    start_t = time.time()
    last_send = 0.0
    saw_both = False

    try:
        while True:
            try:
                data, _ = sock_recv.recvfrom(256)
            except socket.timeout:
                if time.time() - start_t > 15 and not latest:
                    print("⚠️  No llega telemetría. ¿Sim arriba? ¿IP/puerto OK?")
                continue

            if len(data) != MR_SIZE:
                continue
            mr = parse_modelrecord(data)
            latest[mr["number"]] = mr

            if my_vid not in latest or other_vid not in latest:
                continue
            if not saw_both:
                saw_both = True
                print(f"✓ Telemetría OK (veh {sorted(latest.keys())})")

            now = time.time()
            if now - last_send < args.tick_dt:
                continue
            last_send = now

            me = latest[my_vid]
            other = latest[other_vid]

            if me["health"] <= 0 or other["health"] <= 0:
                continue

            my_pos = me["pos"]
            other_pos = other["pos"]
            thrust, steering, precesion, fire = decide(
                my_pos[0], my_pos[1], my_pos[2],
                math.degrees(me["azimuth"]),
                me["health"],
                other_pos[0], other_pos[1], other_pos[2],
                other["health"],
                state,
            )

            packet = pack_control(
                controllingid=my_vid,
                faction=my_vid,
                thrust=thrust,
                steering=steering,
                precesion=precesion,
                fire=fire,
                sourcetimer=me["recordtimer"],
            )
            sock_send.sendto(packet, send_addr)

    except KeyboardInterrupt:
        print("\nInterrumpido.")
    finally:
        sock_recv.close()
        sock_send.close()


if __name__ == "__main__":
    sys.exit(main())
