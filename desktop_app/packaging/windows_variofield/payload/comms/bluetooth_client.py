"""
Bluetooth Classic SPP (RFCOMM) transport — wireless serial port.

Uses BlueZ AF_BLUETOOTH sockets on Linux (no rfcomm bind / root required
for connect). Discovery prefers Classic inquiry (hcitool / bluetoothctl
BREDR) so ESP32 SPP appears **without** prior manual pairing.

The Edge advertises SPP name: SAJ-PDM30-Edge (ESP32 classic only).
"""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
import threading
import time
from typing import Dict, List, Optional, Tuple

from .base import CommsClient, ConnectionState

# Serial Port Profile RFCOMM channel (BluetoothSerial default is 1)
DEFAULT_RFCOMM_CHANNEL = 1
PREFERRED_NAMES = ("SAJ-PDM30-Edge", "SAJ-PDM30", "SAJ")


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


def _merge_device(
    bag: Dict[str, dict],
    address: str,
    name: str = "",
    *,
    paired: Optional[bool] = None,
    trusted: Optional[bool] = None,
    source: str = "",
) -> None:
    address = address.strip().upper()
    if not re.match(r"^[0-9A-F:]{17}$", address):
        return
    cur = bag.get(address)
    if cur is None:
        bag[address] = {
            "address": address,
            "name": (name or address).strip() or address,
            "paired": bool(paired) if paired is not None else False,
            "trusted": bool(trusted) if trusted is not None else False,
            "source": source,
        }
        return
    if name and (cur["name"] == cur["address"] or not cur["name"]):
        cur["name"] = name.strip()
    if paired is not None:
        cur["paired"] = paired
    if trusted is not None:
        cur["trusted"] = trusted
    if source and source not in (cur.get("source") or ""):
        cur["source"] = f"{cur.get('source', '')}+{source}".strip("+")


def _scan_hcitool(scan_seconds: float) -> Dict[str, dict]:
    """Classic inquiry — finds ESP32 SPP without prior pairing."""
    bag: Dict[str, dict] = {}
    if not shutil.which("hcitool"):
        return bag
    # hcitool scan runs inquiry until done (~10s); timeout must cover it
    timeout = max(14.0, float(scan_seconds) + 8.0)
    rc, out = _run(["hcitool", "scan"], timeout=timeout)
    if rc != 0 and not out.strip():
        # some systems need hci0 up
        _run(["hciconfig", "hci0", "up"], timeout=5.0)
        rc, out = _run(["hcitool", "scan"], timeout=timeout)
    for line in out.splitlines():
        # "\tAA:BB:CC:DD:EE:FF\tName" or "AA:BB:... Name"
        m = re.search(
            r"([0-9A-Fa-f:]{17})\s+(\S.*\S|\S)\s*$",
            line.strip(),
        )
        if not m:
            continue
        addr, name = m.group(1), m.group(2).strip()
        if name.lower() in ("scanning", "...") or name.startswith("Scanning"):
            continue
        _merge_device(bag, addr, name, source="hcitool")
    return bag


def _scan_bluetoothctl_bredr(scan_seconds: float) -> None:
    """
    Start a Classic-only scan so devices enter the BlueZ cache.
    Default ``bluetoothctl scan on`` is often LE-biased and misses SPP.
    """
    if not shutil.which("bluetoothctl"):
        return
    seconds = min(max(float(scan_seconds), 5.0), 20.0)
    try:
        p = subprocess.Popen(
            ["bluetoothctl"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert p.stdin is not None
        for line in (
            "power on",
            "agent NoInputNoOutput",
            "default-agent",
            "pairable on",
            "menu scan",
            "transport bredr",
            "duplicate-data on",
            "back",
            "scan on",
        ):
            p.stdin.write(line + "\n")
        p.stdin.flush()
        time.sleep(seconds)
        p.stdin.write("scan off\nquit\n")
        p.stdin.flush()
        try:
            p.communicate(timeout=6)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate(timeout=3)
    except Exception:
        # Fallback: plain scan (may still catch some Classic devices)
        _run(["bluetoothctl", "power", "on"], timeout=5.0)
        _run(["bluetoothctl", "scan", "on"], timeout=3.0)
        time.sleep(seconds)
        _run(["bluetoothctl", "scan", "off"], timeout=3.0)


def _devices_from_bluetoothctl() -> Dict[str, dict]:
    bag: Dict[str, dict] = {}
    rc, out = _run(["bluetoothctl", "devices"], timeout=8.0)
    if rc != 0:
        return bag
    for line in out.splitlines():
        m = re.match(r"Device\s+([0-9A-Fa-f:]{17})\s+(.*)$", line.strip())
        if not m:
            continue
        addr, name = m.group(1).upper(), m.group(2).strip()
        info_rc, info = _run(["bluetoothctl", "info", addr], timeout=5.0)
        paired = "Paired: yes" in info if info_rc == 0 else False
        trusted = "Trusted: yes" in info if info_rc == 0 else False
        _merge_device(
            bag,
            addr,
            name,
            paired=paired,
            trusted=trusted,
            source="bluetoothctl",
        )
    return bag


def list_bluetooth_devices(scan_seconds: float = 10.0) -> List[dict]:
    """
    Discover Classic Bluetooth devices for SPP.

    Does **not** require prior system pairing. Uses:
      1) hcitool inquiry (best for ESP32 Classic SPP)
      2) bluetoothctl BREDR scan (fills BlueZ cache)
      3) bluetoothctl known device list + pair/trust flags

    Each item: {address, name, paired, trusted, source?}
    """
    _run(["bluetoothctl", "power", "on"], timeout=5.0)
    # Some desktops soft-block BT
    if shutil.which("rfkill"):
        _run(["rfkill", "unblock", "bluetooth"], timeout=3.0)

    bag: Dict[str, dict] = {}

    # Classic inquiry first (works even if never paired)
    for addr, d in _scan_hcitool(scan_seconds).items():
        bag[addr] = d

    # BREDR scan — helps BlueZ + finds devices hcitool missed
    _scan_bluetoothctl_bredr(scan_seconds)

    for addr, d in _devices_from_bluetoothctl().items():
        if addr in bag:
            _merge_device(
                bag,
                addr,
                d.get("name", ""),
                paired=d.get("paired"),
                trusted=d.get("trusted"),
                source="bluetoothctl",
            )
        else:
            bag[addr] = d

    devices = list(bag.values())

    def rank(d: dict) -> tuple:
        name_u = (d.get("name") or "").upper()
        pref = 0
        for i, needle in enumerate(PREFERRED_NAMES):
            if needle.upper() in name_u:
                pref = i
                break
        else:
            pref = 50
        return (
            pref,
            0 if d.get("paired") else 1,
            (d.get("name") or "").lower(),
        )

    devices.sort(key=rank)
    return devices


def ensure_paired(address: str, timeout: float = 25.0) -> None:
    """
    Best-effort trust + pair (Just Works / NoInputNoOutput agent).

    SPP often works without full bond; RFCOMM connect is what matters.
    """
    address = address.upper()
    _run(["bluetoothctl", "power", "on"], timeout=5.0)
    # Register a non-interactive agent so passkey prompts don't hang
    try:
        p = subprocess.Popen(
            ["bluetoothctl"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert p.stdin is not None
        for line in (
            "agent NoInputNoOutput",
            "default-agent",
            "pairable on",
            f"trust {address}",
            f"pair {address}",
        ):
            p.stdin.write(line + "\n")
        p.stdin.flush()
        time.sleep(min(timeout, 18.0))
        p.stdin.write("quit\n")
        p.stdin.flush()
        try:
            p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    except Exception:
        _run(["bluetoothctl", "trust", address], timeout=8.0)
        _run(["bluetoothctl", "pair", address], timeout=timeout)


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

        # Soft pair/trust — optional; SPP often works without full bond
        if pair:
            try:
                ensure_paired(address)
            except Exception as e:
                self._emit_error(f"BT pair aviso: {e}")

        try:
            if not hasattr(socket, "AF_BLUETOOTH"):
                raise RuntimeError(
                    "Este Python/SO no expone AF_BLUETOOTH (¿BlueZ en Linux?)"
                )
            sock = socket.socket(
                socket.AF_BLUETOOTH,
                socket.SOCK_STREAM,
                socket.BTPROTO_RFCOMM,  # type: ignore[attr-defined]
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
                "visible al escanear «SAJ-PDM30-Edge», y BT del PC encendido.\n"
                "No hace falta emparejar a mano en el sistema: usá «Escanear BT»."
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
                        self._set_state(
                            ConnectionState.DISCONNECTED, "BT peer closed"
                        )
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
