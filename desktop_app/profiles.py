"""
Persistent Wi-Fi + MQTT connection profiles for the desktop app.

Dev: desktop_app/config/connection_profiles.json
Packaged Electron: $MULTI_VDF_CONFIG_DIR/connection_profiles.json
  (typically ~/.config/VarioField/config/ on Linux).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


def _default_dev_config_dir() -> Path:
    return Path(__file__).resolve().parent / "config"


def resolve_config_dir() -> Path:
    """
    Writable config directory for connection profiles.

    Priority:
      1) MULTI_VDF_CONFIG_DIR (Electron userData/config)
      2) next to frozen executable ../config or ./config
      3) desktop_app/config (dev source tree)
    """
    env = (os.environ.get("MULTI_VDF_CONFIG_DIR") or "").strip()
    if env:
        return Path(env)

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        # resources/backend → resources/config, or userData already set via env
        for c in (
            exe_dir / "config",
            exe_dir.parent / "config",
            Path.home() / ".config" / "VarioField" / "config",
        ):
            try:
                c.mkdir(parents=True, exist_ok=True)
                # Prefer an existing profiles file if present
                if (c / "connection_profiles.json").exists():
                    return c
            except OSError:
                continue
        # Fall back to first writable candidate
        for c in (
            Path.home() / ".config" / "VarioField" / "config",
            exe_dir / "config",
        ):
            try:
                c.mkdir(parents=True, exist_ok=True)
                return c
            except OSError:
                continue

    return _default_dev_config_dir()


def resolve_profiles_path() -> Path:
    return resolve_config_dir() / "connection_profiles.json"


# Resolved at import; Electron sets MULTI_VDF_CONFIG_DIR before spawning backend.
CONFIG_DIR = resolve_config_dir()
PROFILES_PATH = resolve_profiles_path()


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


def _example_candidates() -> List[Path]:
    """Bundled example may live in resources, next to exe, or in source tree."""
    out: List[Path] = []
    env = (os.environ.get("MULTI_VDF_RESOURCES") or "").strip()
    if env:
        out.append(Path(env) / "config" / "connection_profiles.example.json")
    out.append(CONFIG_DIR / "connection_profiles.example.json")
    out.append(_default_dev_config_dir() / "connection_profiles.example.json")
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        exe_dir = Path(sys.executable).resolve().parent
        out.extend(
            [
                exe_dir / "config" / "connection_profiles.example.json",
                exe_dir.parent / "config" / "connection_profiles.example.json",
                meipass / "config" / "connection_profiles.example.json",
            ]
        )
    return out


def load_store(path: Optional[Path] = None) -> ConnectionStore:
    path = path or resolve_profiles_path()
    if not path.exists():
        for example in _example_candidates():
            if example.exists():
                with example.open("r", encoding="utf-8") as f:
                    st = ConnectionStore.from_dict(json.load(f))
                # Example may contain placeholders — still better than empty auth
                save_store(st, path)
                return st
        st = ConnectionStore()
        st.mqtt_profiles.append(
            MqttProfile(
                name="Local Mosquitto",
                host="127.0.0.1",
                port=1883,
                username="variofield",
                password="",
                topic_prefix="saj/pdm30/vf-XXXXXX",
                notes=(
                    "Completá la contraseña MQTT (setup Mosquitto) y el "
                    "prefijo saj/pdm30/vf-… (wifi status / Buscar módulos)."
                ),
            )
        )
        st.last_mqtt = "Local Mosquitto"
        save_store(st, path)
        return st
    with path.open("r", encoding="utf-8") as f:
        return ConnectionStore.from_dict(json.load(f))


def save_store(store: ConnectionStore, path: Optional[Path] = None) -> None:
    path = path or resolve_profiles_path()
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
