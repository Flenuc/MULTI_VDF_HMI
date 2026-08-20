"""Discover online Edge modules on saj/pdm30/<id>/status (retained online)."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List


def discover_edges(
    host: str = "127.0.0.1",
    port: int = 1883,
    username: str = "",
    password: str = "",
    root: str = "saj/pdm30",
    seconds: float = 2.5,
) -> List[Dict[str, Any]]:
    """
    Subscribe to <root>/+/status and collect retained/live 'online' nodes.
    Returns [{edge_id, topic_prefix, status}, ...] sorted by edge_id.
    """
    try:
        import paho.mqtt.client as mqtt
    except ImportError as e:
        raise RuntimeError("pip install paho-mqtt") from e

    root = root.strip().rstrip("/") or "saj/pdm30"
    if not (username or "").strip():
        raise RuntimeError(
            "MQTT auth: falta usuario/contraseña en el perfil. "
            "Configurá usuario y contraseña del broker en Más → Red del equipo."
        )
    found: Dict[str, Dict[str, Any]] = {}
    lock = threading.Lock()
    done = threading.Event()
    connect_error: list[str] = []

    def on_connect(client, userdata, flags, rc):
        # paho v1: rc is int; reason codes vary
        code = int(rc) if not hasattr(rc, "value") else int(getattr(rc, "value", rc))
        if code != 0:
            connect_error.append(
                f"MQTT auth/conexión rechazada (rc={code}). "
                "Configurá usuario y contraseña del broker en el perfil MQTT."
            )
            done.set()
            return
        client.subscribe(f"{root}/+/status", qos=0)

    def on_message(client, userdata, msg):
        topic = msg.topic or ""
        try:
            payload = msg.payload.decode("utf-8", errors="replace").strip().lower()
        except Exception:
            return
        # topic: saj/pdm30/<edge_id>/status
        parts = topic.split("/")
        if len(parts) < 3 or parts[-1] != "status":
            return
        edge_id = parts[-2]
        if not edge_id:
            return
        with lock:
            found[edge_id] = {
                "edge_id": edge_id,
                "topic_prefix": f"{root}/{edge_id}",
                "status": payload or "unknown",
                "online": payload == "online",
            }

    cid = f"vf-discover-{int(time.time()) % 100000}"
    # Support paho-mqtt v1 and v2 APIs
    try:
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION1,
            client_id=cid,
            protocol=mqtt.MQTTv311,
            clean_session=True,
        )
    except (AttributeError, TypeError, ValueError):
        client = mqtt.Client(client_id=cid, protocol=mqtt.MQTTv311, clean_session=True)
    if username:
        client.username_pw_set(username, password or "")
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(str(host), int(port), keepalive=20)
    except Exception as e:
        raise RuntimeError(f"MQTT discover connect failed: {e}") from e

    client.loop_start()
    try:
        # Wait until connected (or failed) then collect retained status
        deadline = time.time() + max(1.5, float(seconds))
        while time.time() < deadline and not connect_error:
            if found:
                # still wait a bit for more retained msgs
                time.sleep(0.3)
                break
            time.sleep(0.1)
        if not connect_error:
            time.sleep(max(0.5, float(seconds) * 0.4))
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass
        done.set()

    if connect_error:
        raise RuntimeError(connect_error[0])

    with lock:
        rows = list(found.values())
    # Prefer online vf-* modules; keep legacy saj-pdm30 last
    def _key(r: Dict[str, Any]):
        eid = str(r.get("edge_id") or "")
        return (
            0 if r.get("online") else 1,
            0 if eid.startswith("vf-") else 1,
            eid,
        )

    rows.sort(key=_key)
    return rows
