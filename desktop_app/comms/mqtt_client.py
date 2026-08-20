"""MQTT transport to SAJ PDM-30 Edge (preferred multiplatform link)."""

from __future__ import annotations

import threading
import time
from typing import Optional

from .base import CommsClient, CommsEvent, ConnectionState


class MqttClient(CommsClient):
    """
    Subscribe rsp + telemetry; publish CLI lines to cmd topic.

    Default topics (per-board serial FW ≥ 0.3.8):
      saj/pdm30/vf-XXXXXX/cmd
      saj/pdm30/vf-XXXXXX/rsp
      saj/pdm30/vf-XXXXXX/telemetry
    """

    def __init__(self) -> None:
        super().__init__()
        self._client = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._host = "127.0.0.1"
        self._port = 1883
        self._prefix = "saj/pdm30/vf-XXXXXX"
        self._user = ""
        self._password = ""
        self._connected_evt = threading.Event()

    def connect(
        self,
        host: str = "127.0.0.1",
        port: int = 1883,
        topic_prefix: str = "saj/pdm30/vf-XXXXXX",
        username: str = "",
        password: str = "",
        **_,
    ) -> None:
        self.disconnect()
        self._host = host
        self._port = int(port)
        self._prefix = topic_prefix.rstrip("/")
        self._user = username or ""
        self._password = password or ""
        self._stop.clear()
        self._connected_evt.clear()
        self._set_state(ConnectionState.CONNECTING, f"mqtt://{host}:{port}")

        try:
            import paho.mqtt.client as mqtt
        except ImportError as e:
            self._set_state(ConnectionState.ERROR, "pip install paho-mqtt")
            self._emit_error(str(e))
            raise

        cid = f"saj-desktop-{int(time.time()) % 100000}"
        try:
            self._client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION1,
                client_id=cid,
                protocol=mqtt.MQTTv311,
                clean_session=True,
            )
        except (AttributeError, TypeError, ValueError):
            self._client = mqtt.Client(
                client_id=cid, protocol=mqtt.MQTTv311, clean_session=True
            )
        if self._user:
            self._client.username_pw_set(self._user, self._password)

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                client.subscribe(f"{self._prefix}/rsp", qos=0)
                client.subscribe(f"{self._prefix}/telemetry", qos=0)
                client.subscribe(f"{self._prefix}/status", qos=0)
                self._set_state(
                    ConnectionState.CONNECTED,
                    f"mqtt://{self._host}:{self._port}  {self._prefix}",
                )
                self._connected_evt.set()
            else:
                self._set_state(ConnectionState.ERROR, f"MQTT rc={rc}")
                self._emit_error(f"MQTT connect failed rc={rc}")

        def on_message(client, userdata, msg):
            try:
                payload = msg.payload.decode("utf-8", errors="replace").strip()
            except Exception:
                return
            if not payload:
                return
            topic = msg.topic or ""
            if topic.endswith("/telemetry") or (
                payload.startswith("{") and payload.endswith("}")
            ):
                self._emit_line(payload)
            elif topic.endswith("/status"):
                self._events.put(CommsEvent("line", f"[status] {payload}"))
            else:
                # rsp may contain multi-line batch
                for part in payload.replace("\r", "").split("\n"):
                    part = part.strip()
                    if part:
                        self._emit_line(part)

        def on_disconnect(client, userdata, rc):
            if not self._stop.is_set():
                self._set_state(ConnectionState.DISCONNECTED, f"MQTT disconnected rc={rc}")

        self._client.on_connect = on_connect
        self._client.on_message = on_message
        self._client.on_disconnect = on_disconnect

        try:
            self._client.connect(self._host, self._port, keepalive=30)
        except Exception as e:
            self._set_state(ConnectionState.ERROR, str(e))
            self._emit_error(str(e))
            raise

        self._thread = threading.Thread(
            target=self._client.loop_forever, name="mqtt-loop", daemon=True
        )
        self._thread.start()

        if not self._connected_evt.wait(timeout=8.0):
            self.disconnect()
            raise RuntimeError(f"MQTT connect timeout to {self._host}:{self._port}")

    def disconnect(self) -> None:
        self._stop.set()
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
            try:
                self._client.loop_stop()
            except Exception:
                pass
        self._client = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        if self.state != ConnectionState.DISCONNECTED:
            self._set_state(ConnectionState.DISCONNECTED, "MQTT closed")

    def send_line(self, line: str) -> None:
        if self._client is None or not self.connected:
            raise RuntimeError("MQTT not connected")
        topic = f"{self._prefix}/cmd"
        self._client.publish(topic, line.rstrip("\r\n"), qos=0)
