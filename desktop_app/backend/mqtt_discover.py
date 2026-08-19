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
    found: Dict[str, Dict[str, Any]] = {}
    lock = threading.Lock()
    done = threading.Event()

    def on_connect(client, userdata, flags, rc):
        if rc != 0:
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
    client = mqtt.Client(client_id=cid, protocol=mqtt.MQTTv311, clean_session=True)
    if username:
        client.username_pw_set(username, password or "")
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(host, int(port), keepalive=20)
    except Exception as e:
        raise RuntimeError(f"MQTT discover connect failed: {e}") from e

    t = threading.Thread(target=client.loop_forever, daemon=True)
    t.start()
    time.sleep(max(0.8, float(seconds)))
    try:
        client.disconnect()
    except Exception:
        pass
    done.set()

    with lock:
        rows = list(found.values())
    rows.sort(key=lambda r: (0 if r.get("online") else 1, str(r.get("edge_id") or "")))
    return rows
