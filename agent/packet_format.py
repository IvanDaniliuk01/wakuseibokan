"""Parse/pack de los structs UDP del simulador Wakuseibokan.

Referencias al código del simulador:
- ModelRecord:       src/networking/telemetry.cpp:27-54  (96 bytes, packed)
- ControlStructure2: src/commandorder.h:103-116           (68 bytes, packed)
- TickRecord:        src/units/Vehicle.h:59-79            (variable, depende del sistema)

Convenciones:
- Todos los structs usan #pragma pack(push, 1) en C++, por eso usamos '<' en struct format.
- Little-endian (típico en x86/x64 Linux).
"""
import struct
from dataclasses import dataclass, field
from typing import List
import numpy as np


# ============================================================
# ModelRecord (telemetría individual, puerto 4501+)
# Tamaño: 96 bytes
# ============================================================

MODEL_RECORD_FORMAT = "<IIifif3f3f12f"
MODEL_RECORD_SIZE = struct.calcsize(MODEL_RECORD_FORMAT)
assert MODEL_RECORD_SIZE == 96, f"ModelRecord debe ser 96 bytes, no {MODEL_RECORD_SIZE}"


@dataclass
class ModelRecord:
    """Telemetría de un vehículo. Lo que recibimos por UDP por cada tick."""
    recordtimer: int             # uint32 — timer del simulador
    lastUpdateTimer: int         # uint32 — último update del vehículo
    number: int                  # int32 — ID del vehículo
    health: float                # [0, 1000]
    power: int                   # int32 — munición [0, 1000]
    azimuth: float               # rad
    landingPos: List[float]      # [x, y, z] — último impacto detectado (radar)
    pos: List[float]             # [x, y, z] — posición world
    rotation: List[float]        # [r1..r12] — matriz 3x4 (12 floats)

    @classmethod
    def from_bytes(cls, data: bytes) -> "ModelRecord":
        if len(data) != MODEL_RECORD_SIZE:
            raise ValueError(f"ModelRecord esperaba {MODEL_RECORD_SIZE} bytes, recibió {len(data)}")
        unpacked = struct.unpack(MODEL_RECORD_FORMAT, data)
        return cls(
            recordtimer=unpacked[0],
            lastUpdateTimer=unpacked[1],
            number=unpacked[2],
            health=unpacked[3],
            power=unpacked[4],
            azimuth=unpacked[5],
            landingPos=list(unpacked[6:9]),
            pos=list(unpacked[9:12]),
            rotation=list(unpacked[12:24]),
        )

    def rotation_matrix_3x3(self) -> np.ndarray:
        """Reconstruye la matriz 3x3 ignorando padding cada 4 floats.

        Layout R[12]:
            [r0  r1  r2  PAD]
            [r4  r5  r6  PAD]
            [r8  r9  r10 PAD]
        Notar que NO hay padding en este struct (es 3x4 contiguo en memoria sin gaps,
        porque está packed). Los índices son directos.
        """
        r = self.rotation
        return np.array([
            [r[0], r[1], r[2]],
            [r[4], r[5], r[6]],
            [r[8], r[9], r[10]],
        ], dtype=np.float32)

    def position_array(self) -> np.ndarray:
        return np.array(self.pos, dtype=np.float32)

    def landing_array(self) -> np.ndarray:
        return np.array(self.landingPos, dtype=np.float32)

    def has_radar_event(self) -> bool:
        """True si el landingPos es no-cero (hubo evento de radar reciente)."""
        return any(abs(x) > 1e-6 for x in self.landingPos)


# ============================================================
# ControlStructure2 (comando del agente al simulador, puerto 4501+)
# Tamaño: 68 bytes
# ============================================================

CONTROL_STRUCT2_FORMAT = "<i6fii iiifff iiI"
# Desglose:
#   <i           controllingid (int32)
#   6f           thrust, roll, pitch, yaw, precesion, bank (controlregister2)
#   i            faction (int32)
#   i            command (int32)
#   i            spawnid (int32)
#   i            typeofisland (int32)
#   fff          x, y, z (3 floats)
#   i            target_type (int32)
#   i            weapon (int32)
#   I            sourcetimer (uint32)
CONTROL_STRUCT2_SIZE = struct.calcsize(CONTROL_STRUCT2_FORMAT)
assert CONTROL_STRUCT2_SIZE == 68, f"ControlStructure2 debe ser 68 bytes, no {CONTROL_STRUCT2_SIZE}"


# Command codes (subset relevante; del enum Command en src/commandorder.h:4-25)
CMD_NONE = 0
CMD_FIRE = 11


@dataclass
class ControlStructure2:
    controllingid: int           # int32 — vehículo a controlar
    thrust: float = 0.0          # R+, F- (acelera adelante/atrás)
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0             # steering (ModAngleZ)
    precesion: float = 0.0
    bank: float = 0.0
    faction: int = 1             # [1, 2, ...]
    command: int = CMD_NONE      # 11 = FIRE
    spawnid: int = 0
    typeofisland: int = 0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    target_type: int = 0
    weapon: int = 0
    sourcetimer: int = 0         # uint32 — timestamp del cliente

    def to_bytes(self) -> bytes:
        return struct.pack(
            CONTROL_STRUCT2_FORMAT,
            self.controllingid,
            self.thrust, self.roll, self.pitch, self.yaw, self.precesion, self.bank,
            self.faction, self.command, self.spawnid, self.typeofisland,
            self.x, self.y, self.z,
            self.target_type, self.weapon, self.sourcetimer,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "ControlStructure2":
        if len(data) != CONTROL_STRUCT2_SIZE:
            raise ValueError(f"ControlStructure2 esperaba {CONTROL_STRUCT2_SIZE} bytes, recibió {len(data)}")
        u = struct.unpack(CONTROL_STRUCT2_FORMAT, data)
        return cls(
            controllingid=u[0],
            thrust=u[1], roll=u[2], pitch=u[3], yaw=u[4], precesion=u[5], bank=u[6],
            faction=u[7], command=u[8], spawnid=u[9], typeofisland=u[10],
            x=u[11], y=u[12], z=u[13],
            target_type=u[14], weapon=u[15], sourcetimer=u[16],
        )


# ============================================================
# JoinOrder — para registrarse en el Lobby (puerto 5000)
# Esta es una ControlStructure2 con command=JoinOrder (13)
# ============================================================

CMD_JOIN = 13  # del enum Command, posición 13 = JoinOrder


def make_join_order(faction: int = 1, sourcetimer: int = 0) -> bytes:
    """Construye el paquete JoinOrder para registrarse en el Lobby."""
    cmd = ControlStructure2(
        controllingid=0,
        faction=faction,
        command=CMD_JOIN,
        sourcetimer=sourcetimer,
    )
    return cmd.to_bytes()


# ============================================================
# TickRecord (Lobby broadcast, puerto 4500) — PENDIENTE
# ============================================================

# La estructura TickRecord tiene `unsigned long` y `size_t` cuyo tamaño
# depende del sistema (8 bytes en Linux x86_64). Hay que verificar empíricamente
# el tamaño real recibido por UDP antes de hardcodear el formato.
# TODO: capturar un paquete real con tcpdump o equivalente y derivar el formato.

# Esqueleto tentativo asumiendo Linux x86_64 (unsigned long=8, size_t=8):
TICK_RECORD_FORMAT_GUESS = (
    "<Q"      # timerparam (unsigned long, 8 bytes en 64-bit Linux)
    "Q"       # id (size_t, 8 bytes)
    "iiiif"   # typeId, type, subtype, faction (4×int32), health (float)
    "iii"     # power, status, ttl (int32×3)
    "ii"      # number, cargo[1] (int32×2)
    "ff"      # elevation, azimuth (float×2)
    # ModelRecord location: 72 bytes según Vehicle.h struct
    "3f12f3f" # pos(3), r(12), vel(3)
    "f"       # orientation
    "Q"       # islandId (size_t)
)
# TICK_RECORD_SIZE_GUESS = struct.calcsize(TICK_RECORD_FORMAT_GUESS)
# print(f"TickRecord guess size: {TICK_RECORD_SIZE_GUESS}")  # verificar con tamaño real

# Cuando tengamos un paquete real, ajustar y descomentar:
# @dataclass
# class TickRecord:
#     ...
