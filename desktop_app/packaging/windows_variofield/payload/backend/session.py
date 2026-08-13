"""
Session manager: one active CommsClient + fan-out of events to WebSocket UIs.

The React Native / web frontend never talks to pyserial/BlueZ directly —
only to this process (HTTP + WebSocket on localhost by default).
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket

# Allow importing desktop_app packages when running from backend/
import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from comms import (  # noqa: E402
    BleNusClient,
    BluetoothClient,
    CommsClient,
    ConnectionState,
    DummyClient,
    MqttClient,
    SerialClient,
    list_ble_nus_devices,
    list_bluetooth_devices,
)
from comms.base import CommsEvent  # noqa: E402


class SessionManager:
    def __init__(self) -> None:
        self._client: Optional[CommsClient] = None
        self._transport: Optional[str] = None
        self._status_msg: str = ""
        self._lock = threading.Lock()
        self._ws: Set[WebSocket] = set()
        self._ws_lock = threading.Lock()
        self._poll_stop = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # last telemetry for REST snapshot
        self.last_telemetry: Dict[str, Any] = {}
        self._start_poller()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _start_poller(self) -> None:
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._poll_stop.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="session-poll", daemon=True
        )
        self._poll_thread.start()

    def _poll_loop(self) -> None:
        while not self._poll_stop.is_set():
            client = self._client
            if client is not None:
                for ev in client.poll_events():
                    self._handle_event(ev)
            time.sleep(0.04)

    def _handle_event(self, ev: CommsEvent) -> None:
        if ev.kind == "json" and isinstance(ev.payload, dict):
            self.last_telemetry = dict(ev.payload)
        if ev.kind == "status":
            st = ev.payload
            msg = (ev.meta or {}).get("message", "")
            if isinstance(st, ConnectionState):
                self._status_msg = msg
        msg = {
            "type": ev.kind,
            "payload": self._serialize_payload(ev.payload),
            "meta": ev.meta or {},
        }
        self._broadcast(msg)

    @staticmethod
    def _serialize_payload(payload: Any) -> Any:
        if isinstance(payload, ConnectionState):
            return payload.value
        if isinstance(payload, (str, int, float, bool, type(None), dict, list)):
            return payload
        return str(payload)

    def _broadcast(self, message: dict) -> None:
        with self._ws_lock:
            sockets = list(self._ws)
        if not sockets:
            return
        loop = self._loop
        if loop is None:
            return
        data = json.dumps(message, default=str)

        async def _send_all() -> None:
            dead: List[WebSocket] = []
            for ws in sockets:
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.append(ws)
            if dead:
                with self._ws_lock:
                    for ws in dead:
                        self._ws.discard(ws)

        try:
            asyncio.run_coroutine_threadsafe(_send_all(), loop)
        except Exception:
            pass

    async def register_ws(self, ws: WebSocket) -> None:
        await ws.accept()
        with self._ws_lock:
            self._ws.add(ws)
        # hello + current status
        await ws.send_json(
            {
                "type": "hello",
                "payload": {"service": "multi-vdf-hmi-backend"},
                "meta": {},
            }
        )
        await ws.send_json(
            {
                "type": "status",
                "payload": self.status()["state"],
                "meta": {"message": self.status()["message"]},
            }
        )
        if self.last_telemetry:
            await ws.send_json(
                {"type": "json", "payload": self.last_telemetry, "meta": {}}
            )

    def unregister_ws(self, ws: WebSocket) -> None:
        with self._ws_lock:
            self._ws.discard(ws)

    def status(self) -> dict:
        with self._lock:
            client = self._client
            transport = self._transport
            msg = self._status_msg
        if client is None:
            return {
                "state": ConnectionState.DISCONNECTED.value,
                "message": msg or "disconnected",
                "transport": transport,
                "connected": False,
            }
        st = client.state
        return {
            "state": st.value if isinstance(st, ConnectionState) else str(st),
            "message": msg,
            "transport": transport,
            "connected": client.connected,
        }

    def connect(self, transport: str, **kwargs) -> None:
        transport = transport.lower().strip()
        self.disconnect()

        if transport == "serial":
            c: CommsClient = SerialClient()
            c.connect(port=kwargs.get("port") or "/dev/ttyACM0", baudrate=int(kwargs.get("baud") or 115200))
        elif transport == "mqtt":
            c = MqttClient()
            # MqttClient.connect signature — check actual
            c.connect(
                host=kwargs.get("host") or "127.0.0.1",
                port=int(kwargs.get("mqtt_port") or kwargs.get("port") or 1883),
                username=kwargs.get("username") or "",
                password=kwargs.get("password") or "",
                topic_prefix=kwargs.get("topic_prefix") or "saj/pdm30/saj-pdm30",
            )
        elif transport == "bluetooth":
            c = BluetoothClient()
            c.connect(
                address=kwargs.get("address") or "",
                channel=int(kwargs.get("channel") or 1),
                pair=bool(kwargs.get("pair", True)),
            )
        elif transport == "ble":
            c = BleNusClient()
            c.connect(address=kwargs.get("address") or "")
        elif transport == "dummy":
            c = DummyClient()
            c.connect()
        else:
            raise ValueError(f"Unknown transport: {transport}")

        with self._lock:
            self._client = c
            self._transport = transport
            self._status_msg = f"connected via {transport}"

        self._broadcast(
            {
                "type": "status",
                "payload": ConnectionState.CONNECTED.value,
                "meta": {"message": self._status_msg, "transport": transport},
            }
        )

    def disconnect(self) -> None:
        with self._lock:
            client = self._client
            self._client = None
            self._transport = None
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                pass
        self._status_msg = "disconnected"
        self.last_telemetry = {}
        self._broadcast(
            {
                "type": "status",
                "payload": ConnectionState.DISCONNECTED.value,
                "meta": {"message": "disconnected"},
            }
        )

    def send_line(self, line: str) -> None:
        with self._lock:
            client = self._client
        if client is None or not client.connected:
            raise RuntimeError("Not connected")
        client.send_line(line)

    @staticmethod
    def list_serial_ports() -> List[dict]:
        try:
            from serial.tools import list_ports
        except Exception:
            return []
        out = []
        for p in list_ports.comports():
            out.append(
                {
                    "device": p.device,
                    "description": p.description or "",
                    "hwid": getattr(p, "hwid", "") or "",
                }
            )
        return out

    @staticmethod
    def list_bt_classic(scan_seconds: float = 10.0) -> List[dict]:
        return list_bluetooth_devices(scan_seconds=scan_seconds)

    @staticmethod
    def list_bt_ble(scan_seconds: float = 6.0) -> List[dict]:
        return list_ble_nus_devices(scan_seconds=scan_seconds)


# Singleton used by FastAPI routes
session = SessionManager()
