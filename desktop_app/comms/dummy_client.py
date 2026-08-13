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
        # Multi-VDF id → eng (for pget/pset / PDH dump)
        self._id_regs: Dict[str, float] = {
            "P0-00": 1.0,
            "P0-01": 0.4,
            "P0-03": 10.0,
            "P1-05": 60.0,
            "F0.00": 2.6,
            "F0.01": 0.5,
            "F0.03": 0.0,
            "D0.00": 0.0,
        }
        self._profile = "saj.pdm30"
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
        if op == "profile":
            if len(parts) < 2 or parts[1].lower() == "get":
                self._emit_line(f"profile={self._profile}")
                return
            if parts[1].lower() == "list":
                self._emit_line("profiles: saj.pdm30 saj.pdh30")
                return
            if parts[1].lower() == "set" and len(parts) >= 3:
                pid = parts[2].strip().lower()
                if pid in ("saj.pdm30", "pdm30", "pdm"):
                    self._profile = "saj.pdm30"
                elif pid in ("saj.pdh30", "pdh30", "pdh"):
                    self._profile = "saj.pdh30"
                else:
                    self._emit_line("ERR: profile set saj.pdm30|saj.pdh30")
                    return
                self._emit_line(f"OK profile={self._profile}")
                return
            self._emit_line("usage: profile get|list|set <id>")
            return
        if op in ("pget", "pset") and len(parts) >= 2:
            pid = parts[1].strip().upper().replace(" ", "")
            # normalize P0.00 → P0-00
            if pid.startswith("P") and "." in pid:
                pid = pid.replace(".", "-", 1)
            if op == "pget":
                if pid.startswith("P") and "-" in pid:
                    try:
                        g = int(pid[1])
                        i = int(pid.split("-", 1)[1])
                        v = self._regs.get((g, i), self._id_regs.get(pid, 0.0))
                    except ValueError:
                        v = self._id_regs.get(pid, 0.0)
                else:
                    v = self._id_regs.get(pid, 0.0)
                self._id_regs[pid] = v
                self._emit_line(f"{pid} @0x0000 = {v}  (raw={int(v*10)} scale=10)")
                return
            if len(parts) < 3:
                self._emit_line(f"usage: pset {pid} <eng>")
                return
            v = float(parts[2])
            self._id_regs[pid] = v
            if pid.startswith("P") and "-" in pid:
                try:
                    g = int(pid[1])
                    i = int(pid.split("-", 1)[1])
                    self._regs[(g, i)] = v
                except ValueError:
                    pass
            self._emit_line(f"OK write {pid} @0x0000 eng={v} raw={int(v*10)}")
            return
        if op == "dump":
            self._emit_line(f"DUMP begin profile={self._profile}")
            self._emit_line("CSV:param,addr,eng,raw,unit")
            if "pdh" in self._profile:
                for pid, v in sorted(self._id_regs.items()):
                    if pid.startswith("P"):
                        continue
                    raw = int(v * 10)
                    self._emit_line(f"CSV:{pid},0xF000,{v},{raw},")
                # ensure common plant IDs exist
                for pid in ("F0.00", "F0.01", "F0.03", "D0.00"):
                    if pid not in self._id_regs:
                        self._emit_line(f"CSV:{pid},0xF000,0,0,")
            else:
                for (g, i), v in sorted(self._regs.items()):
                    raw = int(v * 10)
                    self._emit_line(f"CSV:P{g}-{i:02d},0x{(g<<8)|i:04X},{v},{raw},")
                for g in (0, 1):
                    for i in range(48):
                        if (g, i) not in self._regs:
                            self._emit_line(f"CSV:P{g}-{i:02d},0x{(g<<8)|i:04X},0,0,")
            self._emit_line("CSV:END")
            self._emit_line("DUMP done")
            return
        if op == "help":
            self._emit_line("help | ping | dump | stream on|off | profile | pget|pset | r0|w0 …")
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
