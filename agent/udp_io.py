"""Cliente UDP para Wakuseibokan.

Dos clases:
- UDPClient: motor base. Un socket recv en thread aparte, un socket send.
- SharedTelemetryHub: wrapper que parsea ModelRecord y mantiene `{vid: ModelRecord}`
  compartido entre threads. Cada endpoint de telemetría recibe broadcast de
  TODOS los vehículos — un solo hub alcanza para ver al agente y al enemigo.

Tick budget — IMPORTANTE para el diseño de la política
=======================================================
El sim corre a 50 Hz (tick=20 ms). Cada tick nuestro código tiene que:
    1. recv telemetría (asíncrono — ya está en el thread)
    2. inferir acción (esto es lo que hay que medir cuando metamos la red NN)
    3. enviar comando

Si la inferencia + serialización tarda > 20 ms, los comandos llegan tarde y
desincronizados. El sim los filtra (testcase_131.cpp:405 descarta si
`timer - sourcetimer > 30000`) pero ese es un protector, no la solución.

Política a seguir:
- "Latest wins": al recibir telemetría nueva, se sobreescribe el dict. Si la
  política está pensando, descarta lo viejo y usa lo último. Eso lo hace el
  hub automáticamente.
- Dimensionar la red neuronal para que `forward()` quepa cómodamente en 20 ms
  en el hardware donde se va a deployar (CPU típicamente — la latencia de
  trasladar a GPU + traer back puede ser peor).
- Medir FPS reales del sim (min/max) antes de fijar el tick_dt del agente.

Puertos del sim (testcase 131):
- Telemetría OUT (sim → agente):  4601 (veh 1),  4602 (veh 2)
- Comandos IN  (agente → sim):    4501 (veh 1),  4502 (veh 2)
- Lobby broadcast (no usado hoy):  4500 — requiere JoinOrder a :5000 para
  suscribirse. Parseo del TickRecord pendiente. Por ahora la telemetría
  individual ya broadcastea todos los vehículos, así que no hace falta.
"""
import socket
import threading
import time
from typing import Optional, Dict, Callable

from . import packet_format as pf


class UDPClient:
    """Cliente UDP base: un socket recv en thread aparte, un socket send.

    Para usarlo se le pasa un callback `packet_handler(bytes)` que se invoca
    por cada paquete recibido. El handler debe ser rápido (corre en el thread
    de recepción).
    """

    def __init__(self, recv_port: int, send_host: str = "127.0.0.1", send_port: int = 5000,
                 buffer_size: int = 1024):
        self.recv_port = recv_port
        self.send_addr = (send_host, send_port)
        self.buffer_size = buffer_size

        self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.recv_sock.bind(("", recv_port))
        # Timeout permite chequear el flag _stop cada 0.5s y salir limpio.
        self.recv_sock.settimeout(0.5)

        self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

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


class SharedTelemetryHub:
    """Hub de telemetría con un dict `{vehicle_id: ModelRecord}` thread-safe.

    Modelo "latest wins": cada paquete sobreescribe el record anterior del
    mismo vehículo. Si la política está pensando una acción cuando llega un
    paquete nuevo, ese viejo se descarta. Eso es lo que queremos para
    respetar el tick budget de 20 ms del sim (ver docstring del módulo).
    """

    def __init__(self, recv_port: int, send_host: str = "127.0.0.1",
                 send_port: int = 4501):
        self.client = UDPClient(recv_port, send_host, send_port, buffer_size=128)
        self.latest: Dict[int, pf.ModelRecord] = {}
        self._lock = threading.Lock()

    def start(self):
        self.client.start(self._on_packet)

    def _on_packet(self, data: bytes):
        if len(data) != pf.MODEL_RECORD_SIZE:
            return
        try:
            mr = pf.ModelRecord.from_bytes(data)
        except Exception:
            return
        with self._lock:
            self.latest[mr.number] = mr

    def all_latest(self) -> Dict[int, pf.ModelRecord]:
        with self._lock:
            return dict(self.latest)

    def get(self, vehicle_id: int) -> Optional[pf.ModelRecord]:
        with self._lock:
            return self.latest.get(vehicle_id)

    def clear(self):
        """Borra el estado conocido. Útil tras un hard reset del sim."""
        with self._lock:
            self.latest.clear()

    def send_bytes(self, data: bytes):
        self.client.send_bytes(data)

    def wait_for_vehicles(self, vehicle_ids: list, timeout: float = 15.0) -> bool:
        """Bloquea hasta ver telemetría de todos los vehículos dados o timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if all(vid in self.latest for vid in vehicle_ids):
                    return True
            time.sleep(0.02)
        return False

    def wait_for_health_reset(self, vehicle_ids: list, target_health: float = 999.0,
                              timeout: float = 15.0) -> bool:
        """Espera hasta que TODOS los vehículos tengan health ≥ target_health.

        Usado tras un soft reset del sim para detectar que arrancó el episodio
        nuevo (testcase resetea health a 1000).
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                ok = all(
                    vid in self.latest and self.latest[vid].health >= target_health
                    for vid in vehicle_ids
                )
            if ok:
                return True
            time.sleep(0.05)
        return False

    def stop(self):
        self.client.stop()


# ============================================================
# Smoke test: confirmar que la telemetría llega
# ============================================================
if __name__ == "__main__":
    print("Smoke test del cliente UDP. Necesita el sim corriendo con testcase 131.")

    hub = SharedTelemetryHub(recv_port=4601, send_port=4501)
    hub.start()
    print("Escuchando telemetría en 4601 (envío comandos a 4501)...")

    ok = hub.wait_for_vehicles([1, 2], timeout=10.0)
    if not ok:
        print("⚠️  No llegó telemetría de ambos vehículos.")
    else:
        snap = hub.all_latest()
        for vid, mr in snap.items():
            print(f"  veh #{vid}  pos={mr.pos}  health={mr.health}  "
                  f"recordtimer={mr.recordtimer}")

    hub.stop()
    print("Listo.")
