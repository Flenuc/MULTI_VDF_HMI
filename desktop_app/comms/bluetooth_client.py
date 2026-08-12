"""
Bluetooth Classic SPP (RFCOMM) transport — wireless serial port.

Uses BlueZ AF_BLUETOOTH sockets on Linux (no rfcomm bind / root required
for connect-to-paired). Discovery via ``bluetoothctl`` when available.

The Edge advertises SPP name: SAJ-PDM30-Edge (ESP32 classic only).
"""

from __future__ import annotations

import re
import socket
import subprocess
import threading
import time
from typing import List, Optional, Tuple

from .base import CommsClient, ConnectionState

# Serial Port Profile RFCOMM channel (BluetoothSerial default is 1)
DEFAULT_RFCOMM_CHANNEL = 1


def _run(cmd: list[str], timeout: float = 12.0) -> Tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 1, str(e)


def list_bluetooth_devices(scan_seconds: float = 0.0) -> List[dict]:
    """
    Return paired / known devices from bluetoothctl.
    Optional short scan if scan_seconds > 0 (may require agent).
    Each item: {address, name, paired, trusted}
    """
    if scan_seconds > 0:
        _run(["bluetoothctl", "scan", "on"], timeout=2.0)
        time.sleep(min(scan_seconds, 10.0))
        _run(["bluetoothctl", "scan", "off"], timeout=2.0)

    rc, out = _run(["bluetoothctl", "devices"], timeout=8.0)
    devices: List[dict] = []
    if rc != 0:
        return devices

    for line in out.splitlines():
        # Device AA:BB:CC:DD:EE:FF Name here
        m = re.match(r"Device\s+([0-9A-Fa-f:]{17})\s+(.*)$", line.strip())
        if not m:
            continue
        addr, name = m.group(1).upper(), m.group(2).strip()
        info_rc, info = _run(["bluetoothctl", "info", addr], timeout=5.0)
        paired = "Paired: yes" in info if info_rc == 0 else False
        trusted = "Trusted: yes" in info if info_rc == 0 else False
        devices.append(
            {
                "address": addr,
                "name": name or addr,
                "paired": paired,
                "trusted": trusted,
            }
        )

    # Prefer SAJ devices first
    devices.sort(
        key=lambda d: (
            0 if "SAJ" in d["name"].upper() or "PDM" in d["name"].upper() else 1,
            0 if d["paired"] else 1,
            d["name"].lower(),
        )
    )
    return devices


def ensure_paired(address: str, timeout: float = 30.0) -> None:
    """Best-effort pair + trust (user may need to confirm on agent)."""
    address = address.upper()
    _run(["bluetoothctl", "power", "on"], timeout=5.0)
    _run(["bluetoothctl", "agent", "on"], timeout=5.0)
    _run(["bluetoothctl", "default-agent"], timeout=5.0)
    _run(["bluetoothctl", "pairable", "on"], timeout=5.0)
    rc, out = _run(["bluetoothctl", "pair", address], timeout=timeout)
    if rc != 0 and "AlreadyExists" not in out and "already" not in out.lower():
        # still try trust/connect
        pass
    _run(["bluetoothctl", "trust", address], timeout=8.0)


class BluetoothClient(CommsClient):
    """
    Classic Bluetooth SPP client.

    Byte stream is line-oriented CLI identical to USB Serial.
    """

    def __init__(self) -> None:
        super().__init__()
        self._sock: Optional[socket.socket] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._write_lock = threading.Lock()
        self._address = ""
        self._channel = DEFAULT_RFCOMM_CHANNEL

    def connect(
        self,
        address: str = "",
        channel: int = DEFAULT_RFCOMM_CHANNEL,
        pair: bool = True,
        **_,
    ) -> None:
        if not address or len(address) < 12:
            raise RuntimeError("Seleccioná un dispositivo Bluetooth (MAC)")

        self.disconnect()
        address = address.strip().upper()
        self._address = address
        self._channel = int(channel) if channel else DEFAULT_RFCOMM_CHANNEL
        self._set_state(
            ConnectionState.CONNECTING,
            f"BT SPP {address} ch{self._channel}…",
        )

        try:
            if pair:
                ensure_paired(address)
        except Exception as e:
            # pairing is best-effort; connect may still work if already paired
            self._emit_error(f"BT pair aviso: {e}")

        try:
            if not hasattr(socket, "AF_BLUETOOTH"):
                raise RuntimeError(
                    "Este Python/SO no expone AF_BLUETOOTH (¿BlueZ en Linux?)"
                )
            sock = socket.socket(
                socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM  # type: ignore[attr-defined]
            )
            sock.settimeout(20.0)
            sock.connect((address, self._channel))
            sock.settimeout(0.2)
            self._sock = sock
        except Exception as e:
            self._sock = None
            self._set_state(ConnectionState.ERROR, str(e))
            self._emit_error(f"BT connect failed: {e}")
            raise RuntimeError(
                f"No se pudo abrir SPP con {address}.\n"
                f"Detalle: {e}\n\n"
                "Comprobá: Edge con firmware BT (ESP32 classic), "
                "emparejado, y nombre SAJ-PDM30-Edge."
            ) from e

        self._stop.clear()
        self._rx_thread = threading.Thread(
            target=self._rx_loop, name="bt-spp-rx", daemon=True
        )
        self._rx_thread.start()
        self._set_state(
            ConnectionState.CONNECTED,
            f"BT SPP {address}",
        )
        time.sleep(0.2)

    def disconnect(self) -> None:
        self._stop.set()
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.5)
        self._rx_thread = None
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self.state != ConnectionState.DISCONNECTED:
            self._set_state(ConnectionState.DISCONNECTED, "BT closed")

    def send_line(self, line: str) -> None:
        if self._sock is None:
            raise RuntimeError("Bluetooth no conectado")
        data = (line.rstrip("\r\n") + "\n").encode("utf-8")
        with self._write_lock:
            self._sock.sendall(data)

    def _rx_loop(self) -> None:
        buf = ""
        while not self._stop.is_set():
            try:
                if self._sock is None:
                    break
                try:
                    chunk = self._sock.recv(512)
                except socket.timeout:
                    continue
                if not chunk:
                    if not self._stop.is_set():
                        self._emit_error("BT: conexión cerrada por el peer")
                        self._set_state(ConnectionState.DISCONNECTED, "BT peer closed")
                    break
                buf += chunk.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip("\r")
                    if line and line != ">":
                        if line.startswith("> "):
                            line = line[2:]
                        self._emit_line(line)
            except Exception as e:
                if not self._stop.is_set():
                    self._emit_error(f"BT RX: {e}")
                break
