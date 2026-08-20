"""
Local MQTT broker helpers (Mosquitto) for VarioField field PCs.

- Status: is something listening on 1883 / is mosquitto present?
- Setup: run packaged setup_mosquitto.sh|.ps1 (may need elevation).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_PORT = int(os.environ.get("VARIOFIELD_MQTT_PORT", "1883"))


def _script_dirs() -> List[Path]:
    """Candidate folders that may contain setup_mosquitto.*"""
    here = Path(__file__).resolve()
    roots: List[Path] = []
    # desktop_app/backend → desktop_app/scripts
    roots.append(here.parents[1] / "scripts")
    # Packaged Electron: resources/scripts or resources/pyapp/../scripts
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve().parent
        roots.extend(
            [
                exe / "scripts",
                exe.parent / "scripts",
                exe.parent / "pyapp" / "scripts",
            ]
        )
    env = os.environ.get("MULTI_VDF_SCRIPTS_DIR", "").strip()
    if env:
        roots.insert(0, Path(env))
    # resourcesPath style (set by Electron)
    res = os.environ.get("MULTI_VDF_RESOURCES", "").strip()
    if res:
        roots.insert(0, Path(res) / "scripts")
    out: List[Path] = []
    seen = set()
    for r in roots:
        try:
            rp = r.resolve()
        except Exception:
            rp = r
        if str(rp) not in seen:
            seen.add(str(rp))
            out.append(rp)
    return out


def find_setup_script() -> Optional[Path]:
    name = "setup_mosquitto.ps1" if sys.platform == "win32" else "setup_mosquitto.sh"
    for d in _script_dirs():
        p = d / name
        if p.is_file():
            return p
    return None


def port_open(host: str = "127.0.0.1", port: int = DEFAULT_PORT, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def mosquitto_on_path() -> Optional[str]:
    return shutil.which("mosquitto")


def broker_status(port: int = DEFAULT_PORT) -> Dict[str, Any]:
    listening = port_open("127.0.0.1", port)
    path = mosquitto_on_path()
    script = find_setup_script()
    service = _service_state()
    return {
        "ok": listening,
        "listening": listening,
        "host": "127.0.0.1",
        "port": port,
        "mosquitto_path": path or "",
        "installed": bool(path) or listening,
        "service": service,
        "setup_script": str(script) if script else "",
        "platform": sys.platform,
        "hint": _hint(listening, path, script),
    }


def _service_state() -> str:
    if sys.platform == "win32":
        try:
            r = subprocess.run(
                ["sc", "query", "mosquitto"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            out = (r.stdout or "") + (r.stderr or "")
            if "RUNNING" in out:
                return "running"
            if "STOPPED" in out or "STOP_PENDING" in out:
                return "stopped"
            if r.returncode != 0:
                return "unknown"
        except Exception:
            return "unknown"
        return "unknown"
    # Linux systemd
    for unit in ("mosquitto", "mosquitto.service"):
        try:
            r = subprocess.run(
                ["systemctl", "is-active", unit],
                capture_output=True,
                text=True,
                timeout=4,
            )
            st = (r.stdout or "").strip()
            if st:
                return st  # active / inactive / failed
        except Exception:
            continue
    return "unknown"


def _hint(listening: bool, path: Optional[str], script: Optional[Path]) -> str:
    if listening:
        return "Broker local respondiendo. Podés usar el perfil «Local Mosquitto» (127.0.0.1)."
    if script:
        if sys.platform == "win32":
            return (
                "Mosquitto no responde en el puerto. "
                f"Ejecutá como administrador: powershell -ExecutionPolicy Bypass -File \"{script}\""
            )
        return (
            "Mosquitto no responde en el puerto. "
            f"En una terminal: sudo bash \"{script}\""
        )
    if path:
        return "Mosquitto está instalado pero no escucha. Revisá el servicio o reinicialo."
    return (
        "Mosquitto no está instalado. "
        "Linux: sudo apt install mosquitto mosquitto-clients && sudo systemctl enable --now mosquitto. "
        "Windows: winget install EclipseFoundation.Mosquitto"
    )


def run_setup(port: int = DEFAULT_PORT, timeout: float = 300.0) -> Dict[str, Any]:
    """
    Attempt automated Mosquitto install/config.
    May fail without elevation; then returns needs_elevation + command.
    """
    if port_open("127.0.0.1", port):
        st = broker_status(port)
        st["detail"] = "already_listening"
        st["ran"] = False
        return st

    script = find_setup_script()
    if not script:
        st = broker_status(port)
        st["ok"] = False
        st["ran"] = False
        st["detail"] = "setup_script_missing"
        return st

    env = {**os.environ, "VARIOFIELD_MQTT_PORT": str(port)}
    if sys.platform == "win32":
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ]
        elev_cmd = (
            f'powershell -ExecutionPolicy Bypass -File "{script}"'
        )
    else:
        # Prefer passwordless sudo if configured; else plain bash (may fail)
        if shutil.which("sudo"):
            cmd = ["sudo", "-n", "bash", str(script)]
            elev_cmd = f'sudo bash "{script}"'
        else:
            cmd = ["bash", str(script)]
            elev_cmd = f'sudo bash "{script}"'

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        listening = port_open("127.0.0.1", port)
        return {
            **broker_status(port),
            "ok": listening,
            "ran": True,
            "exit_code": proc.returncode,
            "output": out[-4000:],
            "detail": "ok" if listening else "setup_finished_but_not_listening",
            "needs_elevation": (not listening) and proc.returncode != 0,
            "elevated_command": elev_cmd,
        }
    except subprocess.TimeoutExpired:
        return {
            **broker_status(port),
            "ok": False,
            "ran": True,
            "detail": "timeout",
            "needs_elevation": True,
            "elevated_command": elev_cmd,
            "output": "timeout",
        }
    except Exception as e:
        return {
            **broker_status(port),
            "ok": False,
            "ran": False,
            "detail": f"error:{e}",
            "needs_elevation": True,
            "elevated_command": elev_cmd if script else "",
            "output": str(e),
        }


def ensure_local_mqtt_profile() -> Dict[str, Any]:
    """Upsert default «Local Mosquitto» profile if missing."""
    try:
        from backend import param_api
        from profiles import get_mqtt, load_store
    except Exception as e:
        return {"ok": False, "detail": str(e)}

    try:
        store = load_store()
        existing = get_mqtt(store, "Local Mosquitto")
    except Exception:
        existing = None

    if existing is None:
        try:
            param_api.upsert_mqtt_profile(
                {
                    "name": "Local Mosquitto",
                    "host": "127.0.0.1",
                    "port": DEFAULT_PORT,
                    "username": "variofield",
                    "password": "",
                    "topic_prefix": "saj/pdm30/vf-XXXXXX",
                    "notes": (
                        "Broker en este PC (Mosquitto + auth). "
                        "Completá la contraseña del setup y usá «Buscar módulos» "
                        "o el prefijo visto por BT (saj/pdm30/vf-…). "
                        f"En el Edge: mqtt set <IP_LAN_PC> {DEFAULT_PORT}"
                    ),
                }
            )
            return {"ok": True, "detail": "profile_created"}
        except Exception as e:
            return {"ok": False, "detail": str(e)}
    return {"ok": True, "detail": "profile_exists"}
