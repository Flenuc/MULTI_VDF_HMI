"""Parameter lists + connection profiles for the HTTP API."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from models import Parameter, ParameterList
from profiles import (
    ConnectionStore,
    MqttProfile,
    WifiProfile,
    get_mqtt,
    get_wifi,
    load_store,
    save_store,
    upsert_mqtt,
    upsert_wifi,
)
from storage import load_json, save_json

_APP = Path(__file__).resolve().parents[1]
_ROOT = _APP.parent  # repo root (VF patron) in source tree
LISTS_DIR = _APP / "param_lists"
CONFIG_DIR = _APP / "config"
SAFE_NAME = re.compile(r"^[\w .\-()\[\]]+$")
SAFE_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.I)


def resolve_drive_profiles_dir() -> Path:
    """
    Locate drive_profiles/ in dev and packaged layouts.

    Priority:
      1) MULTI_VDF_DRIVE_PROFILES
      2) MULTI_VDF_RESOURCES/drive_profiles  (Electron)
      3) next to frozen executable / _MEIPASS
      4) repo root / desktop_app/drive_profiles / cwd
    """
    candidates: List[Path] = []
    env = os.environ.get("MULTI_VDF_DRIVE_PROFILES", "").strip()
    if env:
        candidates.append(Path(env))
    res = os.environ.get("MULTI_VDF_RESOURCES", "").strip()
    if res:
        candidates.append(Path(res) / "drive_profiles")

    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                exe_dir / "drive_profiles",
                exe_dir.parent / "drive_profiles",  # resources/ when binary in resources/backend
                meipass / "drive_profiles",
            ]
        )
    else:
        candidates.extend(
            [
                _ROOT / "drive_profiles",
                _APP / "drive_profiles",
                _APP / "electron" / "resources" / "drive_profiles",
                Path.cwd() / "drive_profiles",
                Path.cwd().parent / "drive_profiles",
            ]
        )

    for c in candidates:
        try:
            if c.is_dir() and any(c.glob("**/profile.json")):
                return c.resolve()
        except OSError:
            continue
    # Default (may be empty until packaged)
    if env:
        return Path(env)
    if res:
        return (Path(res) / "drive_profiles").resolve()
    return (_ROOT / "drive_profiles").resolve()


# Resolved at import; refresh via get_drive_profiles_dir() if env changes late
DRIVE_PROFILES_DIR = resolve_drive_profiles_dir()


def get_drive_profiles_dir() -> Path:
    """Re-resolve so Electron-spawned env is always honoured."""
    global DRIVE_PROFILES_DIR
    DRIVE_PROFILES_DIR = resolve_drive_profiles_dir()
    return DRIVE_PROFILES_DIR


def lists_dir() -> Path:
    LISTS_DIR.mkdir(parents=True, exist_ok=True)
    return LISTS_DIR


def list_param_files() -> List[Dict[str, Any]]:
    out = []
    for p in sorted(lists_dir().glob("*.json")):
        try:
            pl = load_json(p)
            n = len(pl.parameters)
            name = pl.name or p.stem
            drive = pl.drive_profile_id or "saj.pdm30"
        except Exception:
            n = -1
            name = p.stem
            drive = ""
        out.append(
            {
                "filename": p.name,
                "stem": p.stem,
                "name": name,
                "count": n,
                "drive_profile_id": drive,
            }
        )
    return out


def load_param_list(filename: str) -> Dict[str, Any]:
    path = _safe_list_path(filename)
    if not path.exists():
        raise FileNotFoundError(filename)
    pl = load_json(path)
    pl.sort_by_id()
    return {"filename": path.name, "list": pl.to_dict()}


def save_param_list(filename: str, data: Dict[str, Any]) -> Dict[str, Any]:
    path = _safe_list_path(filename)
    pl = ParameterList.from_dict(data)
    pl.sort_by_id()
    save_json(pl, path)
    return {"filename": path.name, "list": pl.to_dict()}


def delete_param_list(filename: str) -> None:
    path = _safe_list_path(filename)
    if path.exists():
        path.unlink()


def _safe_list_path(filename: str) -> Path:
    name = Path(filename).name
    if not name.endswith(".json"):
        name = name + ".json"
    if ".." in name or "/" in name or "\\" in name:
        raise ValueError("invalid filename")
    if not SAFE_NAME.match(name.replace(".json", "")) and not name.endswith(".json"):
        raise ValueError("invalid filename")
    # allow unicode spaces in names like "MAX PRESS 30VF.json"
    return lists_dir() / name


def get_profiles() -> Dict[str, Any]:
    st = load_store()
    return st.to_dict()


def put_profiles(data: Dict[str, Any]) -> Dict[str, Any]:
    st = ConnectionStore.from_dict(data)
    save_store(st)
    return st.to_dict()


def upsert_mqtt_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    st = load_store()
    prof = MqttProfile(
        name=str(data.get("name") or "mqtt").strip(),
        host=str(data.get("host") or "").strip(),
        port=int(data.get("port") or 1883),
        username=str(data.get("username") or ""),
        password=str(data.get("password") or ""),
        topic_prefix=str(data.get("topic_prefix") or "saj/pdm30/vf-XXXXXX"),
        notes=str(data.get("notes") or ""),
    )
    if not prof.host:
        raise ValueError("host required")
    upsert_mqtt(st, prof)
    st.last_mqtt = prof.name
    save_store(st)
    return st.to_dict()


def upsert_wifi_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    st = load_store()
    prof = WifiProfile(
        name=str(data.get("name") or "wifi").strip(),
        ssid=str(data.get("ssid") or "").strip(),
        password=str(data.get("password") or ""),
        notes=str(data.get("notes") or ""),
    )
    if not prof.ssid:
        raise ValueError("ssid required")
    upsert_wifi(st, prof)
    st.last_wifi = prof.name
    save_store(st)
    return st.to_dict()


def update_lasts(
    *,
    last_mode: Optional[str] = None,
    last_mqtt: Optional[str] = None,
    last_wifi: Optional[str] = None,
    last_serial_port: Optional[str] = None,
    last_serial_baud: Optional[int] = None,
    last_bt_address: Optional[str] = None,
    last_bt_name: Optional[str] = None,
) -> Dict[str, Any]:
    st = load_store()
    if last_mode is not None:
        st.last_mode = last_mode
    if last_mqtt is not None:
        st.last_mqtt = last_mqtt
    if last_wifi is not None:
        st.last_wifi = last_wifi
    if last_serial_port is not None:
        st.last_serial_port = last_serial_port
    if last_serial_baud is not None:
        st.last_serial_baud = int(last_serial_baud)
    if last_bt_address is not None:
        st.last_bt_address = last_bt_address
    if last_bt_name is not None:
        st.last_bt_name = last_bt_name
    save_store(st)
    return st.to_dict()


def get_mqtt_by_name(name: str) -> Optional[Dict[str, Any]]:
    st = load_store()
    p = get_mqtt(st, name)
    if not p:
        return None
    return {
        "name": p.name,
        "host": p.host,
        "port": p.port,
        "username": p.username,
        "password": p.password,
        "topic_prefix": p.topic_prefix,
        "notes": p.notes,
    }


def get_wifi_by_name(name: str) -> Optional[Dict[str, Any]]:
    st = load_store()
    p = get_wifi(st, name)
    if not p:
        return None
    return {
        "name": p.name,
        "ssid": p.ssid,
        "password": p.password,
        "notes": p.notes,
    }


def list_drive_profiles() -> List[Dict[str, Any]]:
    """Index of drive_profiles/**/profile.json (dev or packaged)."""
    root = get_drive_profiles_dir()
    out: List[Dict[str, Any]] = []
    if not root.is_dir():
        return out
    for p in sorted(root.glob("**/profile.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            pid = str(data.get("id") or p.parent.name)
            params = data.get("parameters") or []
            out.append(
                {
                    "id": pid,
                    "vendor": data.get("vendor"),
                    "family": data.get("family"),
                    "model": data.get("model"),
                    "version": data.get("version"),
                    "status": data.get("status"),
                    "param_count": len(params) if isinstance(params, list) else 0,
                    "path": str(p.relative_to(root)),
                }
            )
        except Exception:
            continue
    return out


def load_drive_profile(profile_id: str) -> Dict[str, Any]:
    """Load full catalog JSON for a drive profile id (e.g. saj.pdh30)."""
    pid = (profile_id or "").strip()
    if not pid or not SAFE_PROFILE_ID.match(pid):
        raise ValueError("invalid drive profile id")
    root = get_drive_profiles_dir()
    # id "saj.pdh30" → drive_profiles/saj/pdh30/profile.json
    parts = pid.split(".")
    if len(parts) >= 2:
        vendor, model = parts[0], parts[1]
        candidate = root / vendor / model / "profile.json"
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    # fallback: scan
    if root.is_dir():
        for p in root.glob("**/profile.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if str(data.get("id")) == pid:
                    return data
            except Exception:
                continue
    raise FileNotFoundError(pid)
