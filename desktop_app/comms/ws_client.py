"""LEGACY — WebSocket transport (abandoned; dump saturation / multiplatform friction).

Do not use for new clients. Prefer MQTT (docs/PROTOCOL.md). Kept only for
reference; may move to desktop_app/legacy/.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from .base import CommsClient, ConnectionState


class WebSocketClient(CommsClient):
    def __init__(self) -> None:
        super().__init__()
        self._ws = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._url = ""

    def connect(self, url: str = "ws://192.168.4.1/ws", **_) -> None:
        self.disconnect()
        self._url = url
        self._set_state(ConnectionState.CONNECTING, f"WS {url}…")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ws-client", daemon=True)
        self._thread.start()
        # Wait briefly for handshake (non-UI if called from worker)
        deadline = time.time() + 8.0
        while time.time() < deadline:
            if self.state in (ConnectionState.CONNECTED, ConnectionState.ERROR):
                break
            time.sleep(0.05)
        if self.state != ConnectionState.CONNECTED:
            raise RuntimeError(f"WebSocket connect timeout/failed: {url}")

    def disconnect(self) -> None:
        self._stop.set()
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            pass
        self._ws = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        if self.state != ConnectionState.DISCONNECTED:
            self._set_state(ConnectionState.DISCONNECTED, "WebSocket closed")

    def send_line(self, line: str) -> None:
        if self._ws is None:
            raise RuntimeError("WebSocket not connected")
        text = line.rstrip("\r\n")
        self._ws.send(text)

    def _run(self) -> None:
        try:
            import websocket  # websocket-client
        except ImportError as e:
            self._set_state(ConnectionState.ERROR, "pip install websocket-client")
            self._emit_error(str(e))
            return

        def on_message(_ws, message: str):
            if isinstance(message, bytes):
                message = message.decode("utf-8", errors="replace")
            for part in message.replace("\r", "").split("\n"):
                part = part.strip()
                if not part or part == ">":
                    continue
                if part.startswith("> "):
                    part = part[2:]
                self._emit_line(part)

        def on_error(_ws, error):
            self._emit_error(f"WS error: {error}")

        def on_close(_ws, *args):
            if not self._stop.is_set():
                self._set_state(ConnectionState.DISCONNECTED, "WS closed by peer")

        def on_open(_ws):
            self._set_state(ConnectionState.CONNECTED, self._url)

        self._ws = websocket.WebSocketApp(
            self._url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
        )
        # run_forever blocks this worker thread only
        self._ws.run_forever(ping_interval=20, ping_timeout=10)
