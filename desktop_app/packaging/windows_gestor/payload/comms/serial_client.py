"""USB Serial transport to ESP32 Edge CLI (115200 default)."""

from __future__ import annotations

import threading
import time
from typing import Optional

from .base import CommsClient, ConnectionState


class SerialClient(CommsClient):
    def __init__(self) -> None:
        super().__init__()
        self._ser = None
        self._rx_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._write_lock = threading.Lock()

    def connect(self, port: str = "/dev/ttyACM0", baudrate: int = 115200, **_) -> None:
        import serial

        self.disconnect()
        self._set_state(ConnectionState.CONNECTING, f"Opening {port}…")
        try:
            # Prefer not forcing DTR/RTS toggles that reset USB-CDC MCUs.
            ser = serial.Serial()
            ser.port = port
            ser.baudrate = int(baudrate)
            ser.timeout = 0.05
            ser.write_timeout = 2.0
            ser.dsrdtr = False
            ser.rtscts = False
            ser.open()
            try:
                ser.dtr = False
                ser.rts = False
            except Exception:
                pass

            self._ser = ser
            # Opening ACM often still resets ESP32-P4 USB Serial/JTAG — wait for boot.
            self._wait_boot_ready(timeout=5.0)
            try:
                self._ser.reset_input_buffer()
            except Exception:
                pass

            self._stop.clear()
            self._rx_thread = threading.Thread(
                target=self._rx_loop, name="serial-rx", daemon=True
            )
            self._rx_thread.start()
            self._set_state(ConnectionState.CONNECTED, f"{port} @ {baudrate}")
            # Wake CLI without a fake command that becomes "ERR: unknown"
            time.sleep(0.15)
        except Exception as e:
            self._ser = None
            self._set_state(ConnectionState.ERROR, str(e))
            self._emit_error(f"Serial connect failed: {e}")
            raise

    def _wait_boot_ready(self, timeout: float = 5.0) -> None:
        """Drain boot noise; stop early if banner / prompt appears."""
        if not self._ser:
            return
        deadline = time.time() + timeout
        buf = ""
        while time.time() < deadline:
            try:
                chunk = self._ser.read(512)
            except Exception:
                break
            if chunk:
                buf += chunk.decode("utf-8", errors="replace")
                low = buf.lower()
                if (
                    "saj pdm-30" in low
                    or "edge" in low
                    or "\n> " in buf
                    or buf.rstrip().endswith(">")
                ):
                    # small settle after banner
                    time.sleep(0.25)
                    return
            else:
                time.sleep(0.05)
        # Even without banner, give USB-CDC a moment after open/reset
        time.sleep(0.4)

    def disconnect(self) -> None:
        self._stop.set()
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.0)
        self._rx_thread = None
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        if self.state != ConnectionState.DISCONNECTED:
            self._set_state(ConnectionState.DISCONNECTED, "Serial closed")

    def send_line(self, line: str) -> None:
        if not self._ser or not self._ser.is_open:
            raise RuntimeError("Serial not connected")
        data = (line.rstrip("\r\n") + "\n").encode("utf-8")
        with self._write_lock:
            self._ser.write(data)
            self._ser.flush()

    def _rx_loop(self) -> None:
        buf = ""
        while not self._stop.is_set():
            try:
                if self._ser is None or not self._ser.is_open:
                    break
                chunk = self._ser.read(512)
                if not chunk:
                    continue
                buf += chunk.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip("\r")
                    if line and line != ">":
                        # strip prompt prefixes
                        if line.startswith("> "):
                            line = line[2:]
                        self._emit_line(line)
            except Exception as e:
                if not self._stop.is_set():
                    self._emit_error(f"Serial RX: {e}")
                break
