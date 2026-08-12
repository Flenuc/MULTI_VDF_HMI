"""
Serial communication layer with ESP32 running saj_pdm30_cli firmware.

Commands used (USB 115200 by default):
  w0 <ii> <raw> / w1 <ii> <raw>
  r0 <ii> / r1 <ii>
  ping

Includes DummySerialClient for GUI testing without hardware.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from models import Parameter

log = logging.getLogger(__name__)

# P0-00 @0x0000 = 10 (0x000A)  "Pressure setting"
_RE_PARAM = re.compile(
    r"P(\d+)-(\d+)\s+@0x[0-9A-Fa-f]+\s+=\s+(\d+)",
    re.IGNORECASE,
)
_RE_OK_WRITE = re.compile(
    r"OK write P(\d+)-(\d+)\s+@0x[0-9A-Fa-f]+\s+=\s+(\d+)",
    re.IGNORECASE,
)
_RE_ERR = re.compile(r"^ERR:", re.MULTILINE)


@dataclass
class SerialResult:
    ok: bool
    message: str
    value: Optional[int] = None
    raw_response: str = ""


class SerialBackend(ABC):
    """Abstract serial transport."""

    @abstractmethod
    def is_open(self) -> bool: ...

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def exchange(self, command: str, timeout: float = 3.0) -> str:
        """Send one CLI line, return text until prompt."""
        ...


class RealSerialBackend(SerialBackend):
    """pyserial backend talking to ESP32 USB CDC."""

    def __init__(self, port: str, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self._ser = None
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def open(self) -> None:
        import serial  # lazy import

        self.close()
        self._ser = serial.Serial(self.port, self.baudrate, timeout=0.2)
        time.sleep(0.4)  # USB settle / optional ESP reset on DTR
        self._ser.reset_input_buffer()
        # Wake CLI
        self._ser.write(b"\n")
        self._read_until_prompt(timeout=2.0)

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def exchange(self, command: str, timeout: float = 3.0) -> str:
        with self._lock:
            if not self.is_open():
                raise RuntimeError("Serial port is not open")
            assert self._ser is not None
            self._ser.reset_input_buffer()
            line = (command.strip() + "\n").encode("utf-8")
            self._ser.write(line)
            self._ser.flush()
            return self._read_until_prompt(timeout=timeout)

    def _read_until_prompt(self, timeout: float) -> str:
        assert self._ser is not None
        buf = ""
        t0 = time.time()
        last = time.time()
        while time.time() - t0 < timeout:
            chunk = self._ser.read(4096)
            if chunk:
                buf += chunk.decode("utf-8", errors="replace")
                last = time.time()
                if buf.endswith("> ") or buf.rstrip().endswith(">"):
                    time.sleep(0.05)
                    extra = self._ser.read(4096)
                    if extra:
                        buf += extra.decode("utf-8", errors="replace")
                    return buf
            else:
                if buf and (buf.endswith("> ") or buf.rstrip().endswith(">")):
                    if time.time() - last > 0.15:
                        return buf
            time.sleep(0.01)
        return buf


class DummySerialBackend(SerialBackend):
    """
    Simulated ESP32/VFD for UI development.

    Holds an in-memory register map keyed by (group, index).
    """

    def __init__(self, latency_s: float = 0.05):
        self._open = False
        self._latency = latency_s
        # Seed with some plausible PDM-30 values from discovery
        self._regs: Dict[Tuple[int, int], int] = {
            (0, 0): 10,
            (0, 1): 4,
            (0, 3): 100,
            (0, 43): 8,
            (1, 5): 6000,
            (1, 35): 1,
            (1, 36): 1,
            (1, 37): 0,
        }
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def exchange(self, command: str, timeout: float = 3.0) -> str:
        if not self._open:
            raise RuntimeError("Dummy serial is not open")
        time.sleep(self._latency)
        cmd = command.strip()
        parts = cmd.split()
        if not parts:
            return "> "
        op = parts[0].lower()

        with self._lock:
            if op in ("help", "h"):
                return "help (dummy)\n> "
            if op == "ping":
                return (
                    "Status 0x3000 = 3 (STOP)\n"
                    "Run freq 0x1001 = 0.00 Hz\n"
                    "Set press 0x100F = 1.0 bar\n"
                    "Fb  press 0x1010 = 0.0 bar\n"
                    "Link OK\n> "
                )
            if op in ("r0", "r1") and len(parts) >= 2:
                g = 0 if op == "r0" else 1
                i = int(parts[1])
                val = self._regs.get((g, i), 0)
                return (
                    f'P{g}-{i:02d} @0x{(g << 8) | i:04X} = {val} (0x{val:04X})  '
                    f'"(dummy)"\n> '
                )
            if op in ("w0", "w1") and len(parts) >= 3:
                g = 0 if op == "w0" else 1
                i = int(parts[1])
                val = int(parts[2], 0) & 0xFFFF
                self._regs[(g, i)] = val
                return f"OK write P{g}-{i:02d} @0x{(g << 8) | i:04X} = {val}\n> "
            return f"ERR: unknown command (dummy) — {cmd}\n> "


class Esp32Client:
    """
    High-level API for parameter R/W via ESP32 CLI.
    Thread-safe enough for background worker + UI callbacks.
    """

    def __init__(self) -> None:
        self._backend: Optional[SerialBackend] = None
        self.mode: str = "disconnected"  # real | dummy | disconnected

    @property
    def connected(self) -> bool:
        return self._backend is not None and self._backend.is_open()

    def connect_real(self, port: str, baudrate: int = 115200) -> None:
        self.disconnect()
        be = RealSerialBackend(port, baudrate)
        be.open()
        self._backend = be
        self.mode = "real"

    def connect_dummy(self) -> None:
        self.disconnect()
        be = DummySerialBackend()
        be.open()
        self._backend = be
        self.mode = "dummy"

    def disconnect(self) -> None:
        if self._backend is not None:
            try:
                self._backend.close()
            except Exception:
                pass
        self._backend = None
        self.mode = "disconnected"

    def ping(self) -> SerialResult:
        text = self._exchange("ping", timeout=5.0)
        ok = "Link OK" in text or "0x3000" in text
        return SerialResult(ok=ok, message=text.strip(), raw_response=text)

    def read_param(self, group: int, index: int) -> SerialResult:
        cmd = f"r{group} {index}"
        text = self._exchange(cmd, timeout=3.0)
        if _RE_ERR.search(text):
            return SerialResult(ok=False, message=text.strip(), raw_response=text)
        m = _RE_PARAM.search(text)
        if not m:
            return SerialResult(
                ok=False,
                message=f"No parseable value in response:\n{text}",
                raw_response=text,
            )
        val = int(m.group(3))
        return SerialResult(ok=True, message=text.strip(), value=val, raw_response=text)

    def write_param(self, group: int, index: int, value: int) -> SerialResult:
        cmd = f"w{group} {index} {int(value) & 0xFFFF}"
        text = self._exchange(cmd, timeout=3.0)
        if _RE_ERR.search(text):
            return SerialResult(ok=False, message=text.strip(), raw_response=text)
        m = _RE_OK_WRITE.search(text)
        if m:
            return SerialResult(
                ok=True,
                message=text.strip(),
                value=int(m.group(3)),
                raw_response=text,
            )
        # Some firmwares may still be OK without exact echo
        if "OK write" in text:
            return SerialResult(ok=True, message=text.strip(), value=value, raw_response=text)
        return SerialResult(ok=False, message=text.strip(), raw_response=text)

    def write_list(
        self,
        params: List[Parameter],
        on_progress: Optional[Callable[[int, int, Parameter, SerialResult], None]] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ) -> List[SerialResult]:
        """Write all non-manual parameters. Calls on_progress(i, total, param, result)."""
        writable = [p for p in params if not p.manual_only]
        results: List[SerialResult] = []
        total = len(writable)
        for i, p in enumerate(writable):
            if stop_flag and stop_flag():
                break
            res = self.write_param(p.group, p.index, p.value)
            results.append(res)
            if on_progress:
                on_progress(i + 1, total, p, res)
        return results

    def read_list(
        self,
        params: List[Parameter],
        on_progress: Optional[Callable[[int, int, Parameter, SerialResult], None]] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ) -> List[SerialResult]:
        results: List[SerialResult] = []
        total = len(params)
        for i, p in enumerate(params):
            if stop_flag and stop_flag():
                break
            res = self.read_param(p.group, p.index)
            results.append(res)
            if on_progress:
                on_progress(i + 1, total, p, res)
        return results

    def _exchange(self, command: str, timeout: float = 3.0) -> str:
        if not self.connected or self._backend is None:
            raise RuntimeError("Not connected to ESP32 (use Connect or Dummy mode)")
        log.debug("TX: %s", command)
        text = self._backend.exchange(command, timeout=timeout)
        log.debug("RX: %s", text[:200])
        return text


def list_serial_ports() -> List[str]:
    """Return available serial device paths."""
    try:
        from serial.tools import list_ports

        ports = [p.device for p in list_ports.comports()]
        return ports if ports else []
    except Exception:
        return []
