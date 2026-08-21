"""Edge CLI transports for Catalog Builder live extract (serial + MQTT)."""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Iterable, List, Optional, Protocol


def strip_line(line: str) -> str:
    s = line.rstrip("\r\n")
    if s.startswith(">"):
        s = s[1:].lstrip()
    return s


def is_noise(line: str) -> bool:
    return (
        line.startswith("[mqtt]")
        or line.startswith("[wifi]")
        or line.startswith("[mdns]")
        or line.startswith("[status]")
        or line.startswith("[eth]")
    )


def parse_csv_line(s: str) -> Optional[dict]:
    """Parse Edge dump line: CSV:<id>,<addr>,<eng>,<raw>."""
    if not s.startswith("CSV:"):
        return None
    if s.startswith("CSV:param") or s.startswith("CSV:END"):
        return None
    parts = s[4:].split(",")
    if len(parts) < 3:
        return None
    pid = parts[0].strip()
    addr = parts[1].strip()
    eng_s = parts[2].strip()
    raw_s = parts[3].strip() if len(parts) > 3 else ""
    ok = eng_s != "ERROR" and raw_s != "ERROR"
    eng = None
    raw_v = None
    if ok:
        try:
            eng = float(eng_s)
        except ValueError:
            ok = False
        try:
            raw_v = int(float(raw_s)) if raw_s != "" else None
        except ValueError:
            ok = False
            raw_v = None
    try:
        reg = int(addr, 16) if addr.lower().startswith("0x") else int(addr)
    except ValueError:
        reg = None
    return {
        "id": pid,
        "addr": addr,
        "reg": reg,
        "eng": eng,
        "raw": raw_v,
        "ok": ok,
    }


class EdgeTransport(Protocol):
    def send(self, cmd: str) -> None: ...

    def read_line(self, timeout: float = 0.2) -> Optional[str]: ...

    def close(self) -> None: ...


class SerialTransport:
    def __init__(self, port: str, baud: int = 115200):
        import serial

        self.ser = serial.Serial(port, baud, timeout=0.15)
        time.sleep(0.8)
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass

    def send(self, cmd: str) -> None:
        self.ser.write((cmd + "\n").encode("utf-8"))
        self.ser.flush()

    def read_line(self, timeout: float = 0.2) -> Optional[str]:
        old = self.ser.timeout
        self.ser.timeout = timeout
        try:
            raw = self.ser.readline()
        finally:
            self.ser.timeout = old
        if not raw:
            return None
        return strip_line(raw.decode("utf-8", errors="replace"))

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass


class MqttTransport:
    """Publish CLI to <prefix>/cmd; collect lines from <prefix>/rsp."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 1883,
        prefix: str = "saj/pdm30/vf-XXXXXX",
        username: str = "",
        password: str = "",
    ):
        try:
            import paho.mqtt.client as mqtt
        except ImportError as e:
            raise RuntimeError("pip install paho-mqtt") from e

        self._prefix = prefix.rstrip("/")
        self._q: queue.Queue[str] = queue.Queue()
        self._connected = threading.Event()
        self._connect_err: list[str] = []
        cid = f"vf-extract-{int(time.time()) % 100000}"
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
        if username:
            self._client.username_pw_set(username, password or "")

        def on_connect(client, userdata, flags, rc):
            code = int(rc) if not hasattr(rc, "value") else int(getattr(rc, "value", rc))
            if code != 0:
                self._connect_err.append(f"MQTT connect rejected rc={code}")
                self._connected.set()
                return
            client.subscribe(f"{self._prefix}/rsp", qos=0)
            self._connected.set()

        def on_message(client, userdata, msg):
            try:
                payload = msg.payload.decode("utf-8", errors="replace")
            except Exception:
                return
            for part in payload.replace("\r", "").split("\n"):
                part = strip_line(part.strip())
                if part:
                    self._q.put(part)

        self._client.on_connect = on_connect
        self._client.on_message = on_message
        self._client.connect(str(host), int(port), keepalive=30)
        self._client.loop_start()
        if not self._connected.wait(8.0):
            self.close()
            raise RuntimeError(f"MQTT connect timeout to {host}:{port}")
        if self._connect_err:
            self.close()
            raise RuntimeError(self._connect_err[0])

    def send(self, cmd: str) -> None:
        self._client.publish(f"{self._prefix}/cmd", cmd.rstrip("\r\n"), qos=0)

    def read_line(self, timeout: float = 0.2) -> Optional[str]:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:
            pass


def drain(tr: EdgeTransport, seconds: float) -> List[str]:
    out: List[str] = []
    t0 = time.time()
    while time.time() - t0 < seconds:
        line = tr.read_line(0.05)
        if line:
            if not is_noise(line):
                out.append(line)
        else:
            time.sleep(0.01)
    return out


def run_dump(
    tr: EdgeTransport,
    profile_id: str,
    timeout: float = 240.0,
    on_progress: Optional[Callable[[int, float], None]] = None,
) -> dict:
    """
    stream off → profile set → dump → collect CSV rows until DUMP done.
    Returns {started, done, rows, raw_lines, elapsed_s}.
    """
    raw_lines: List[str] = []
    rows: List[dict] = []

    tr.send("stream off")
    drain(tr, 0.5)
    # Prove the cmd/rsp path before a long dump
    tr.send("ping")
    ping_lines = drain(tr, 2.5)
    raw_lines.extend(ping_lines)
    if not ping_lines:
        raise RuntimeError(
            "sin eco MQTT/serial a 'ping' — revisá prefix/puerto, auth y que el Edge esté CONNECTED"
        )

    tr.send(f"profile set {profile_id}")
    for L in drain(tr, 1.5):
        raw_lines.append(L)
    tr.send("profile get")
    for L in drain(tr, 1.0):
        raw_lines.append(L)

    started = False
    done = False
    t0 = time.time()
    tr.send("dump")

    while time.time() - t0 < timeout:
        line = tr.read_line(0.2)
        if line is None:
            continue
        raw_lines.append(line)
        if is_noise(line):
            continue
        if line.startswith("DUMP begin"):
            started = True
            continue
        if line.startswith("CSV:param"):
            continue
        if line.startswith("CSV:END") or line == "DUMP done":
            done = True
            if line == "DUMP done":
                break
            continue
        if line.startswith("ERR:"):
            continue
        parsed = parse_csv_line(line)
        if not parsed:
            continue
        rows.append(parsed)
        if on_progress and len(rows) % 25 == 0:
            on_progress(len(rows), time.time() - t0)

    for L in drain(tr, 1.2):
        raw_lines.append(L)
        if L == "DUMP done" or L.startswith("CSV:END"):
            done = True

    return {
        "started": started,
        "done": done,
        "rows": rows,
        "raw_lines": raw_lines,
        "elapsed_s": round(time.time() - t0, 2),
    }
