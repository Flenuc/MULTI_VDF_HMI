"""
Abstract communications client for the SAJ PDM-30 Edge ESP32 CLI.

GUI code depends only on this interface — never on pyserial / websocket details.
All I/O happens off the UI thread; inbound lines are delivered via callbacks.
"""

from __future__ import annotations

import enum
import queue
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


class ConnectionState(enum.Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class CommsEvent:
    """Inbound event for the UI thread to drain."""

    kind: str  # "line" | "json" | "status" | "error" | "raw"
    payload: Any = None
    meta: Dict[str, Any] = field(default_factory=dict)


# Callback signatures (invoked from worker threads — GUI must marshal to main)
LineHandler = Callable[[str], None]
JsonHandler = Callable[[dict], None]
StatusHandler = Callable[[ConnectionState, str], None]


class CommsClient(ABC):
    """
    Base client: send CLI text lines, receive responses asynchronously.

    Implementations push events into an internal queue; the GUI polls
    ``poll_events()`` from the Tk main loop (e.g. every 50 ms via after()).
    """

    def __init__(self) -> None:
        self._events: queue.Queue[CommsEvent] = queue.Queue()
        self._state = ConnectionState.DISCONNECTED
        self._lock = threading.Lock()

    # ----- state -----
    @property
    def state(self) -> ConnectionState:
        with self._lock:
            return self._state

    def _set_state(self, st: ConnectionState, msg: str = "") -> None:
        with self._lock:
            self._state = st
        self._events.put(CommsEvent("status", st, {"message": msg}))

    @property
    def connected(self) -> bool:
        return self.state == ConnectionState.CONNECTED

    # ----- queue for UI -----
    def poll_events(self) -> list[CommsEvent]:
        """Non-blocking drain — call from the GUI thread only."""
        out: list[CommsEvent] = []
        while True:
            try:
                out.append(self._events.get_nowait())
            except queue.Empty:
                break
        return out

    def _emit_line(self, line: str) -> None:
        line = line.rstrip("\r\n")
        if not line:
            return
        # Telemetry JSON from firmware starts with '{'
        if line.startswith("{") and line.endswith("}"):
            try:
                import json

                obj = json.loads(line)
                self._events.put(CommsEvent("json", obj, {"raw": line}))
                return
            except Exception:
                pass
        self._events.put(CommsEvent("line", line))

    def _emit_error(self, msg: str) -> None:
        self._events.put(CommsEvent("error", msg))

    # ----- API -----
    @abstractmethod
    def connect(self, **kwargs) -> None:
        """Open transport (blocking OK — call from worker or accept short block)."""

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @abstractmethod
    def send_line(self, line: str) -> None:
        """Queue/send one CLI command line (no trailing newline required)."""

    def send_command(self, cmd: str) -> None:
        self.send_line(cmd.strip())
