"""
Persistent Wi-Fi + MQTT connection profiles for the desktop app.

Stored in desktop_app/config/connection_profiles.json
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

CONFIG_DIR = Path(__file__).resolve().parent / "config"
PROFILES_PATH = CONFIG_DIR / "connection_profiles.json"


@dataclass
class WifiProfile:
    name: str
    ssid: str
    password: str = ""
    notes: str = ""


@dataclass
class MqttProfile:
    name: str
    host: str = "127.0.0.1"
    port: int = 1883
    username: str = ""
    password: str = ""
    topic_prefix: str = "saj/pdm30/vf-XXXXXX"
    notes: str = ""


@dataclass
class ConnectionStore:
    wifi_profiles: List[WifiProfile] = field(default_factory=list)
    mqtt_profiles: List[MqttProfile] = field(default_factory=list)
    last_mode: str = "MQTT"
    last_wifi: str = ""
    last_mqtt: str = ""
    last_serial_port: str = ""
    last_serial_baud: int = 115200
    last_bt_address: str = ""
    last_bt_name: str = ""

    def to_dict(self) -> dict:
        return {
            "wifi_profiles": [asdict(p) for p in self.wifi_profiles],
            "mqtt_profiles": [asdict(p) for p in self.mqtt_profiles],
            "last_mode": self.last_mode,
            "last_wifi": self.last_wifi,
            "last_mqtt": self.last_mqtt,
            "last_serial_port": self.last_serial_port,
            "last_serial_baud": self.last_serial_baud,
            "last_bt_address": self.last_bt_address,
            "last_bt_name": self.last_bt_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConnectionStore":
        st = cls()
        st.last_mode = str(data.get("last_mode", "MQTT"))
        st.last_wifi = str(data.get("last_wifi", ""))
        st.last_mqtt = str(data.get("last_mqtt", ""))
        st.last_serial_port = str(data.get("last_serial_port", ""))
        st.last_serial_baud = int(data.get("last_serial_baud", 115200))
        st.last_bt_address = str(data.get("last_bt_address", ""))
        st.last_bt_name = str(data.get("last_bt_name", ""))
        for w in data.get("wifi_profiles", []):
            st.wifi_profiles.append(
                WifiProfile(
                    name=str(w.get("name", "")),
                    ssid=str(w.get("ssid", "")),
                    password=str(w.get("password", "")),
                    notes=str(w.get("notes", "")),
                )
            )
        for m in data.get("mqtt_profiles", []):
            st.mqtt_profiles.append(
                MqttProfile(
                    name=str(m.get("name", "")),
                    host=str(m.get("host", "127.0.0.1")),
                    port=int(m.get("port", 1883)),
                    username=str(m.get("username", "")),
                    password=str(m.get("password", "")),
                    topic_prefix=str(m.get("topic_prefix", "saj/pdm30/vf-XXXXXX")),
                    notes=str(m.get("notes", "")),
                )
            )
        return st


def load_store(path: Path = PROFILES_PATH) -> ConnectionStore:
    if not path.exists():
        example = CONFIG_DIR / "connection_profiles.example.json"
        if example.exists():
            # First run: clone example (no secrets) then user edits locally
            with example.open("r", encoding="utf-8") as f:
                st = ConnectionStore.from_dict(json.load(f))
            save_store(st, path)
            return st
        st = ConnectionStore()
        st.mqtt_profiles.append(
            MqttProfile(name="Local Mosquitto", host="127.0.0.1", port=1883)
        )
        st.last_mqtt = "Local Mosquitto"
        save_store(st, path)
        return st
    with path.open("r", encoding="utf-8") as f:
        return ConnectionStore.from_dict(json.load(f))


def save_store(store: ConnectionStore, path: Path = PROFILES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store.to_dict(), f, indent=2, ensure_ascii=False)


def upsert_wifi(store: ConnectionStore, prof: WifiProfile) -> None:
    for i, p in enumerate(store.wifi_profiles):
        if p.name == prof.name:
            store.wifi_profiles[i] = prof
            return
    store.wifi_profiles.append(prof)


def upsert_mqtt(store: ConnectionStore, prof: MqttProfile) -> None:
    for i, p in enumerate(store.mqtt_profiles):
        if p.name == prof.name:
            store.mqtt_profiles[i] = prof
            return
    store.mqtt_profiles.append(prof)


def get_wifi(store: ConnectionStore, name: str) -> Optional[WifiProfile]:
    for p in store.wifi_profiles:
        if p.name == name:
            return p
    return None


def get_mqtt(store: ConnectionStore, name: str) -> Optional[MqttProfile]:
    for p in store.mqtt_profiles:
        if p.name == name:
            return p
    return None
