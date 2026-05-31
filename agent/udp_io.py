"""Cliente UDP para Wakuseibokan.

Dos canales:
- Telemetría individual (puerto 4501+i): recibe ModelRecord (96 bytes) de NUESTRO vehículo.
- Lobby (puerto 4500): recibe TickRecord broadcast de TODOS los vehículos. Requiere JoinOrder al puerto 5000.

Para training usamos el Lobby (tenemos GT del enemigo). Para eval usamos Telemetría individual.
"""
import socket
import struct
import threading
import time
from collections import deque
from typing import Optional, Dict, Callable

from . import packet_format as pf


class UDPClient:
    """Cliente UDP base con thread de recepción."""

    def __init__(self, recv_port: int, send_host: str = "127.0.0.1", send_port: int = 5000,
                 buffer_size: int = 1024):
        self.recv_port = recv_port
        self.send_addr = (send_host, send_port)
        self.buffer_size = buffer_size

        # Socket recv
        self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.recv_sock.bind(("", recv_port))
        self.recv_sock.settimeout(0.5)

        # Socket send
        self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Stop flag
        self._stop = threading.Event()
        self._packet_handler: Optional[Callable[[bytes], None]] = None
        self._thread: Optional[threading.Thread] = None

    def start(self, packet_handler: Callable[[bytes], None]):
        """Inicia el thread de recepción. packet_handler(bytes) se llama por cada paquete."""
        self._packet_handler = packet_handler
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

    def _recv_loop(self):
        while not self._stop.is_set():
            try:
                data, _addr = self.recv_sock.recvfrom(self.buffer_size)
                if self._packet_handler:
                    try:
                        self._packet_handler(data)
                    except Exception as e:
                        print(f"[UDPClient] handler error: {e}")
            except socket.timeout:
                continue
            except OSError:
                break

    def send_bytes(self, data: bytes):
        self.send_sock.sendto(data, self.send_addr)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        try:
            self.recv_sock.close()
        except Exception:
            pass
        try:
            self.send_sock.close()
        except Exception:
            pass


class TelemetryClient:
    """Cliente para telemetría individual (puerto 4501+).

    Recibe ModelRecord (96 bytes) y mantiene un buffer circular de los últimos
    K=30 ticks. Para enviar comandos usar el método send_command().
    """

    def __init__(self, recv_port: int = 4501, send_host: str = "127.0.0.1",
                 send_port: int = 4501, buffer_size: int = 30):
        # En testcase 131 el agente Python envía comandos al MISMO puerto donde
        # recibe telemetría (4501+i), porque ahí escucha el simulador. Verificar.
        self.client = UDPClient(recv_port, send_host, send_port, buffer_size=128)
        self.history: deque = deque(maxlen=buffer_size)
        self._last_lock = threading.Lock()

    def start(self):
        self.client.start(self._handle_packet)

    def _handle_packet(self, data: bytes):
        if len(data) != pf.MODEL_RECORD_SIZE:
            return  # ignorar paquetes de tamaño inesperado
        try:
            mr = pf.ModelRecord.from_bytes(data)
        except Exception:
            return
        with self._last_lock:
            self.history.append(mr)

    def latest(self) -> Optional[pf.ModelRecord]:
        """Devuelve el último ModelRecord recibido, o None si no hay."""
        with self._last_lock:
            if len(self.history) == 0:
                return None
            return self.history[-1]

    def history_list(self) -> list:
        with self._last_lock:
            return list(self.history)

    def wait_for_first(self, timeout: float = 5.0) -> Optional[pf.ModelRecord]:
        """Bloquea hasta recibir la primera telemetría o timeout."""
        start = time.time()
        while time.time() - start < timeout:
            tr = self.latest()
            if tr is not None:
                return tr
            time.sleep(0.02)
        return None

    def send_command(self, cmd: pf.ControlStructure2):
        # Actualizar sourcetimer si no fue setteado
        if cmd.sourcetimer == 0:
            cmd.sourcetimer = int(time.time() * 1000) & 0xFFFFFFFF
        self.client.send_bytes(cmd.to_bytes())

    def stop(self):
        self.client.stop()


class LobbyClient:
    """Cliente para el Lobby (puerto 4500).

    Recibe broadcast de TickRecord de TODOS los vehículos. Para registrarse hay
    que enviar un JoinOrder al puerto 5000 al inicio.

    NOTA: el parseo de TickRecord está PENDIENTE de confirmar el formato exacto
    capturando un paquete real (ver packet_format.py:TICK_RECORD_FORMAT_GUESS).
    """

    def __init__(self, recv_port: int = 4500, join_host: str = "127.0.0.1",
                 join_port: int = 5000, faction: int = 1):
        self.client = UDPClient(recv_port, join_host, join_port, buffer_size=512)
        self.faction = faction
        self.raw_packets: deque = deque(maxlen=500)  # guardamos crudos por ahora
        self.by_vehicle: Dict[int, deque] = {}
        self._lock = threading.Lock()

    def start(self):
        self.client.start(self._handle_packet)
        # Enviar JoinOrder para registrarnos
        join_pkt = pf.make_join_order(faction=self.faction)
        self.client.send_bytes(join_pkt)
        print(f"[LobbyClient] JoinOrder enviado a {self.client.send_addr}")

    def _handle_packet(self, data: bytes):
        # Por ahora solo guardamos los bytes crudos para análisis
        with self._lock:
            self.raw_packets.append((time.time(), data))

    def raw_packet_sizes(self):
        """Útil para descubrir el tamaño real del TickRecord."""
        with self._lock:
            return [(t, len(d)) for t, d in self.raw_packets]

    def latest_raw(self) -> Optional[bytes]:
        with self._lock:
            if len(self.raw_packets) == 0:
                return None
            return self.raw_packets[-1][1]

    def stop(self):
        self.client.stop()


# ============================================================
# Smoke test (para correr directo)
# ============================================================
if __name__ == "__main__":
    print("Iniciando smoke test del cliente UDP...")
    print("(Asegurate de que el simulador está corriendo con testcase 131)")

    # Telemetría individual
    tel = TelemetryClient(recv_port=4501, send_port=4501)
    tel.start()
    print(f"Escuchando telemetría en puerto 4501...")

    first = tel.wait_for_first(timeout=10.0)
    if first is None:
        print("⚠️  No se recibió ninguna telemetría. ¿El simulador está corriendo?")
    else:
        print(f"✓ Primer ModelRecord recibido:")
        print(f"  vehicle #{first.number} pos={first.pos} health={first.health}")
        print(f"  rotation matrix:")
        print(f"  {first.rotation_matrix_3x3()}")

    # Lobby
    lobby = LobbyClient(recv_port=4500, join_port=5000)
    lobby.start()
    print(f"Escuchando Lobby en puerto 4500...")
    time.sleep(3.0)
    sizes = lobby.raw_packet_sizes()
    if sizes:
        unique_sizes = set(s for _, s in sizes)
        print(f"✓ {len(sizes)} paquetes recibidos del Lobby. Tamaños: {unique_sizes}")
    else:
        print("⚠️  No se recibieron paquetes del Lobby.")

    # Cleanup
    tel.stop()
    lobby.stop()
    print("Listo.")
