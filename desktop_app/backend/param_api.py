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


def resolve_drive_profiles_user_dir() -> Path:
    """
    Writable overlay for technician edits / imports.

    Priority:
      1) MULTI_VDF_DRIVE_PROFILES_USER
      2) MULTI_VDF_CONFIG_DIR/../drive_profiles
      3) ~/.config/VarioField/drive_profiles
      4) desktop_app/drive_profiles_user (dev)
    """
    env = os.environ.get("MULTI_VDF_DRIVE_PROFILES_USER", "").strip()
    if env:
        return Path(env)
    cfg = os.environ.get("MULTI_VDF_CONFIG_DIR", "").strip()
    if cfg:
        return (Path(cfg).resolve().parent / "drive_profiles")
    home = Path.home() / ".config" / "VarioField" / "drive_profiles"
    return home if getattr(sys, "frozen", False) else (_APP / "drive_profiles_user")


def get_drive_profiles_user_dir() -> Path:
    d = resolve_drive_profiles_user_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _profile_rel_dir(profile_id: str) -> Path:
    parts = profile_id.strip().split(".")
    if len(parts) < 2:
        raise ValueError("invalid drive profile id")
    return Path(parts[0]) / parts[1]


VARIANT_FILES = {
    "active": "profile.json",
    "live_draft": "profile.live_draft.json",
    "merged": "profile.merged.json",
}


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


def _read_profile_file(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def list_drive_profiles() -> List[Dict[str, Any]]:
    """Index of drive profiles (user overlay wins over packaged/repo)."""
    packaged = get_drive_profiles_dir()
    user = resolve_drive_profiles_user_dir()
    by_id: Dict[str, Dict[str, Any]] = {}

    def _ingest(root: Path, source: str) -> None:
        if not root.is_dir():
            return
        for p in sorted(root.glob("**/profile.json")):
            try:
                data = _read_profile_file(p)
                pid = str(data.get("id") or p.parent.name)
                params = data.get("parameters") or []
                by_id[pid] = {
                    "id": pid,
                    "vendor": data.get("vendor"),
                    "family": data.get("family"),
                    "model": data.get("model"),
                    "version": data.get("version"),
                    "status": data.get("status"),
                    "param_count": len(params) if isinstance(params, list) else 0,
                    "path": str(p),
                    "source": source,
                    "writable": source == "user",
                }
            except Exception:
                continue

    _ingest(packaged, "packaged")
    _ingest(user, "user")
    return [by_id[k] for k in sorted(by_id.keys())]


def _candidate_paths(profile_id: str, filename: str) -> List[Path]:
    rel = _profile_rel_dir(profile_id)
    return [
        get_drive_profiles_user_dir() / rel / filename,
        get_drive_profiles_dir() / rel / filename,
    ]


def load_drive_profile(
    profile_id: str, variant: str = "active"
) -> Dict[str, Any]:
    """Load catalog JSON. variant: active | live_draft | merged."""
    pid = (profile_id or "").strip()
    if not pid or not SAFE_PROFILE_ID.match(pid):
        raise ValueError("invalid drive profile id")
    fname = VARIANT_FILES.get(variant or "active")
    if not fname:
        raise ValueError(f"unknown variant {variant!r}")

    for candidate in _candidate_paths(pid, fname):
        if candidate.is_file():
            data = _read_profile_file(candidate)
            data["_meta"] = {
                "profile_id": pid,
                "variant": variant,
                "path": str(candidate),
                "source": "user"
                if str(get_drive_profiles_user_dir()) in str(candidate)
                else "packaged",
            }
            return data

    if variant != "active":
        raise FileNotFoundError(f"{pid}/{fname}")

    # fallback scan packaged for active only
    root = get_drive_profiles_dir()
    if root.is_dir():
        for p in root.glob("**/profile.json"):
            try:
                data = _read_profile_file(p)
                if str(data.get("id")) == pid:
                    data["_meta"] = {
                        "profile_id": pid,
                        "variant": "active",
                        "path": str(p),
                        "source": "packaged",
                    }
                    return data
            except Exception:
                continue
    raise FileNotFoundError(pid)


def list_drive_profile_variants(profile_id: str) -> List[Dict[str, Any]]:
    pid = (profile_id or "").strip()
    if not pid or not SAFE_PROFILE_ID.match(pid):
        raise ValueError("invalid drive profile id")
    out: List[Dict[str, Any]] = []
    for key, fname in VARIANT_FILES.items():
        found = None
        source = None
        for candidate in _candidate_paths(pid, fname):
            if candidate.is_file():
                found = candidate
                source = (
                    "user"
                    if str(get_drive_profiles_user_dir()) in str(candidate)
                    else "packaged"
                )
                break
        out.append(
            {
                "variant": key,
                "filename": fname,
                "exists": found is not None,
                "path": str(found) if found else None,
                "source": source,
            }
        )
    return out


def save_drive_profile(
    profile_id: str,
    data: Dict[str, Any],
    variant: str = "active",
) -> Dict[str, Any]:
    """Write profile JSON into the user overlay (never into AppImage resources)."""
    pid = (profile_id or "").strip()
    if not pid or not SAFE_PROFILE_ID.match(pid):
        raise ValueError("invalid drive profile id")
    fname = VARIANT_FILES.get(variant or "active")
    if not fname:
        raise ValueError(f"unknown variant {variant!r}")
    if not isinstance(data, dict):
        raise ValueError("body must be a JSON object")
    # Strip UI meta; force id
    body = {k: v for k, v in data.items() if not str(k).startswith("_")}
    body["id"] = pid
    params = body.get("parameters")
    if not isinstance(params, list) or not params:
        raise ValueError("parameters must be a non-empty list")

    dest = get_drive_profiles_user_dir() / _profile_rel_dir(pid) / fname
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return load_drive_profile(pid, variant)


def apply_drive_profile_variant(
    profile_id: str, source_variant: str = "merged"
) -> Dict[str, Any]:
    """Copy live_draft/merged → active (user overlay), with .bak of previous active."""
    if source_variant not in ("merged", "live_draft"):
        raise ValueError("source_variant must be merged or live_draft")
    src = load_drive_profile(profile_id, source_variant)
    # backup current active if present in user overlay
    active_user = (
        get_drive_profiles_user_dir()
        / _profile_rel_dir(profile_id)
        / "profile.json"
    )
    if active_user.is_file():
        bak = active_user.with_suffix(".json.bak")
        bak.write_text(active_user.read_text(encoding="utf-8"), encoding="utf-8")
    return save_drive_profile(profile_id, src, "active")
