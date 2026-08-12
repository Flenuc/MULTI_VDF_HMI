"""Simulated Edge device for GUI tests without hardware."""

from __future__ import annotations

import json
import threading
import time
from typing import Dict, Tuple

from .base import CommsClient, CommsEvent, ConnectionState


class DummyClient(CommsClient):
    def __init__(self) -> None:
        super().__init__()
        self._regs: Dict[Tuple[int, int], float] = {
            (0, 0): 1.0,
            (0, 3): 10.0,
            (0, 1): 0.4,
            (1, 5): 60.0,
            (1, 35): 1.0,
        }
        self._stream = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = "stop"
        self._freq = 0.0
        self._amp = 0.0
        self._vdc = 310.0

    def connect(self, **_) -> None:
        self.disconnect()
        self._stop.clear()
        self._set_state(ConnectionState.CONNECTED, "Dummy Edge")
        self._thread = threading.Thread(target=self._telemetry_loop, daemon=True)
        self._thread.start()
        self._emit_line("SAJ PDM-30 Edge ready (DUMMY). Type help")

    def disconnect(self) -> None:
        self._stop.set()
        self._stream = False
        if self._thread:
            self._thread.join(timeout=1.0)
        self._thread = None
        self._set_state(ConnectionState.DISCONNECTED, "Dummy closed")

    def send_line(self, line: str) -> None:
        if not self.connected:
            raise RuntimeError("Dummy not connected")
        cmd = line.strip()
        if not cmd:
            return
        parts = cmd.split()
        op = parts[0].lower()

        if op == "stream":
            self._stream = len(parts) > 1 and parts[1].lower() == "on"
            self._emit_line(f"stream {'ON' if self._stream else 'OFF'}")
            return
        if op == "ping":
            self._emit_line("status=3 (stop)")
            self._emit_line("freq=0.00 Hz")
            self._emit_line("Link OK")
            return
        if op == "start":
            self._status = "run"
            self._freq = 45.0
            self._amp = 1.8
            self._emit_line("OK op raw=1")
            return
        if op == "stop":
            self._status = "stop"
            self._freq = 0.0
            self._amp = 0.0
            self._emit_line("OK op raw=6")
            return
        if op == "set" and len(parts) >= 2:
            self._emit_line(f"OK op raw={int(float(parts[1])*100)}")
            return
        if op in ("r0", "r1") and len(parts) >= 2:
            g = 0 if op == "r0" else 1
            i = int(parts[1])
            v = self._regs.get((g, i), 0.0)
            self._emit_line(f"P{g}-{i:02d} @0x{(g<<8)|i:04X} = {v}  (raw={int(v*10)})")
            return
        if op in ("w0", "w1") and len(parts) >= 3:
            g = 0 if op == "w0" else 1
            i = int(parts[1])
            v = float(parts[2])
            self._regs[(g, i)] = v
            self._emit_line(f"OK write P{g}-{i:02d} eng={v} raw={int(v*10)}")
            return
        if op == "dump":
            self._emit_line("DUMP begin (eng scale)")
            self._emit_line("CSV:param,addr,eng,raw,unit")
            for (g, i), v in sorted(self._regs.items()):
                raw = int(v * 10)
                self._emit_line(f"CSV:P{g}-{i:02d},0x{(g<<8)|i:04X},{v},{raw},")
            # fill missing as zeros for demo span
            for g in (0, 1):
                for i in range(48):
                    if (g, i) not in self._regs:
                        self._emit_line(f"CSV:P{g}-{i:02d},0x{(g<<8)|i:04X},0,0,")
            self._emit_line("CSV:END")
            self._emit_line("DUMP done")
            return
        if op == "help":
            self._emit_line("help | ping | dump | stream on|off | r0|w0 …")
            return
        self._emit_line(f"ERR: unknown (dummy) {cmd}")

    def _telemetry_loop(self) -> None:
        while not self._stop.is_set():
            if self._stream and self.connected:
                # slight animation
                if self._status == "run":
                    self._freq = 45.0 + (time.time() % 5)
                    self._amp = 1.5 + (time.time() % 2) * 0.3
                payload = {
                    "freq": round(self._freq, 2),
                    "amp": round(self._amp, 2),
                    "vdc": self._vdc,
                    "vout": 220.0 if self._status == "run" else 0.0,
                    "pset": 2.0,
                    "pfb": 0.0 if self._status != "run" else 1.8,
                    "status": self._status,
                }
                self._events.put(CommsEvent("json", payload))
            time.sleep(1.0)
