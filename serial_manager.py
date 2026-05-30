"""
GC-01 Rad Pro — Monitor de Radiación
Módulo de comunicación serial con el dispositivo.
"""
import serial
import serial.tools.list_ports
import threading


class SerialManager:
    BAUD    = 115200
    TIMEOUT = 2.0

    def __init__(self):
        self._port = None
        self._lock = threading.Lock()

    # ── Puertos disponibles ──────────────────────────────────────────────────
    @staticmethod
    def list_ports():
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports] or ["(ninguno)"]

    # ── Conexión ─────────────────────────────────────────────────────────────
    def connect(self, port_name: str):
        self._port = serial.Serial(
            port_name,
            baudrate=self.BAUD,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=self.TIMEOUT,
        )
        self._port.reset_input_buffer()

    def disconnect(self):
        if self._port and self._port.is_open:
            self._port.close()
        self._port = None

    @property
    def connected(self) -> bool:
        return self._port is not None and self._port.is_open

    # ── Protocolo Rad Pro ────────────────────────────────────────────────────
    def send(self, command: str) -> str | None:
        """Envía un comando y devuelve el payload tras 'OK', o None si falla."""
        if not self.connected:
            return None
        with self._lock:
            try:
                self._port.write(f"{command}\r\n".encode())
                raw = self._port.readline().decode(errors="replace").strip()
                print(f"[SERIAL] CMD={command!r}  RAW={raw!r}")
                if raw.startswith("OK"):
                    return raw[2:].strip()   # quita "OK"
                print(f"[SERIAL] Sin 'OK' — respuesta descartada: {raw!r}")
                return None
            except Exception as e:
                print(f"[SERIAL] EXCEPCIÓN en send({command!r}): {e}")
                return None

    # ── Comandos de alto nivel ────────────────────────────────────────────────
    def get_device_id(self) -> dict | None:
        """Retorna {hardware, firmware, device_id} o None."""
        resp = self.send("GET deviceId")
        if resp is None:
            return None
        parts = resp.split(";")
        return {
            "hardware":  parts[0].strip() if len(parts) > 0 else "?",
            "firmware":  parts[1].strip() if len(parts) > 1 else "?",
            "device_id": parts[2].strip() if len(parts) > 2 else "?",
        }

    def get_tube_type(self) -> str | None:
        return self.send("GET tubeType")

    def get_tube_sensitivity(self) -> float | None:
        r = self.send("GET tubeSensitivity")
        try:
            return float(r)
        except (TypeError, ValueError):
            return None

    def get_tube_rate(self) -> float | None:
        r = self.send("GET tubeRate")
        try:
            return float(r)
        except (TypeError, ValueError):
            return None

    def get_tube_pulse_count(self) -> int | None:
        r = self.send("GET tubePulseCount")
        try:
            return int(r)
        except (TypeError, ValueError):
            return None

    def get_battery_voltage(self) -> float | None:
        r = self.send("GET deviceBatteryVoltage")
        try:
            return float(r)
        except (TypeError, ValueError):
            return None

    def set_device_time(self, unix_ts: int) -> bool:
        """Sincroniza el reloj del dispositivo con un timestamp UNIX.
        Retorna True si el dispositivo confirmó con OK."""
        resp = self.send(f"SET deviceTime {unix_ts}")
        # El dispositivo responde 'OK' → send() devuelve '' (cadena vacía) con éxito
        return resp is not None

    def get_datalog(self, start: int = 0) -> list[dict]:
        """Descarga el datalog y devuelve lista de {time, tubePulseCount}."""
        resp = self.send(f"GET datalog {start}")
        if not resp:
            return []
        records = []
        for segment in resp.split(";;"):
            segment = segment.strip()
            if not segment or segment.startswith("time"):
                continue
            for entry in segment.split(";"):
                entry = entry.strip()
                if "," in entry:
                    t, p = entry.split(",", 1)
                    try:
                        records.append({"time": int(t), "pulseCount": int(p)})
                    except ValueError:
                        pass
        return records