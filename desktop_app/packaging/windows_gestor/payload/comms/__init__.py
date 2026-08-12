"""Transport layer: Serial USB + Bluetooth SPP + MQTT (WebSocket deprecated)."""

from .base import CommsClient, CommsEvent, ConnectionState
from .serial_client import SerialClient
from .mqtt_client import MqttClient
from .dummy_client import DummyClient
from .bluetooth_client import BluetoothClient, list_bluetooth_devices
from .ble_nus_client import BleNusClient, list_ble_nus_devices

# Keep WS import optional for legacy
try:
    from .ws_client import WebSocketClient
except Exception:  # pragma: no cover
    WebSocketClient = None  # type: ignore

__all__ = [
    "CommsClient",
    "CommsEvent",
    "ConnectionState",
    "SerialClient",
    "MqttClient",
    "DummyClient",
    "BluetoothClient",
    "list_bluetooth_devices",
    "BleNusClient",
    "list_ble_nus_devices",
    "WebSocketClient",
]
