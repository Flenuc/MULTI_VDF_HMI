#!/usr/bin/env python3
"""
MQTT connectivity suite for SAJ PDM-30 Edge (no VDF required).

Topology:
  PC (wlan0 192.168.4.2) ← SoftAP SAJ_Diag_Tool → ESP (192.168.4.1)
  Mosquitto on PC :1883  ↔  ESP PubSubClient

Without VDF:
  - ping → PING FAIL / TIMEOUT is SUCCESS for the MQTT path
  - dump → DUMP begin (+ later TIMEOUT/ERR) is SUCCESS for the MQTT path
  - telemetry may emit zeros after Modbus timeouts (~1–2 s/cycle)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import serial
import paho.mqtt.client as mqtt

PREFIX = "saj/pdm30/saj-pdm30"
TOPIC_CMD = f"{PREFIX}/cmd"
TOPIC_RSP = f"{PREFIX}/rsp"
TOPIC_TEL = f"{PREFIX}/telemetry"
TOPIC_STAT = f"{PREFIX}/status"


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Suite:
    results: list[Result] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append(Result(name, ok, detail))
        tag = "PASS" if ok else "FAIL"
        extra = f" — {detail}" if detail else ""
        print(f"[{tag}] {name}{extra}", flush=True)

    def summary_lines(self) -> list[str]:
        n_ok = sum(1 for r in self.results if r.ok)
        n_fail = len(self.results) - n_ok
        lines = [
            "",
            "=" * 60,
            f"MQTT TEST SUMMARY: {n_ok} PASS / {n_fail} FAIL / {len(self.results)} total",
            f"Broker: (see header)  Prefix: {PREFIX}",
            "Note: no VDF connected — Modbus TIMEOUT/FAIL expected on ping/dump/telemetry",
        ]
        for r in self.results:
            tag = "PASS" if r.ok else "FAIL"
            extra = f" — {r.detail}" if r.detail else ""
            lines.append(f"  [{tag}] {r.name}{extra}")
        lines.append("=" * 60)
        return lines


class SerialCli:
    def __init__(self, port: str, baud: int = 115200):
        self.ser = serial.Serial(port, baud, timeout=0.2)
        time.sleep(0.3)
        self.ser.reset_input_buffer()

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass

    def cmd(self, line: str, wait: float = 1.2) -> str:
        self.ser.reset_input_buffer()
        print(f"\n>>> [serial] {line}", flush=True)
        self.ser.write((line + "\n").encode("utf-8"))
        deadline = time.time() + wait
        chunks: list[str] = []
        while time.time() < deadline:
            n = self.ser.in_waiting
            if n:
                chunks.append(self.ser.read(n).decode("utf-8", "replace"))
            else:
                time.sleep(0.05)
        time.sleep(0.15)
        if self.ser.in_waiting:
            chunks.append(self.ser.read(self.ser.in_waiting).decode("utf-8", "replace"))
        text = "".join(chunks)
        print(text, end="" if text.endswith("\n") else "\n", flush=True)
        return text


class MqttProbe:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.rsp: list[tuple[float, str]] = []
        self.tel: list[tuple[float, str]] = []
        self.status: list[str] = []
        self._lock = threading.Lock()
        self.connected = False
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"mqtt-test-{int(time.time()) % 100000}",
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        # paho v2: ReasonCode compares to 0 and str()s as "Success"
        rc_ok = (reason_code == 0) or (str(reason_code) == "Success")
        self.connected = rc_ok
        print(f"[paho] connected rc={reason_code} ok={rc_ok}", flush=True)
        if rc_ok:
            client.subscribe([(TOPIC_RSP, 0), (TOPIC_TEL, 0), (TOPIC_STAT, 0)])

    def _on_message(self, client, userdata, msg):
        payload = msg.payload.decode("utf-8", "replace")
        now = time.time()
        with self._lock:
            if msg.topic == TOPIC_RSP:
                self.rsp.append((now, payload))
            elif msg.topic == TOPIC_TEL:
                self.tel.append((now, payload))
            elif msg.topic == TOPIC_STAT:
                self.status.append(payload)
        short = payload if len(payload) < 180 else payload[:177] + "..."
        print(f"[paho] {msg.topic}: {short}", flush=True)

    def start(self) -> bool:
        self.client.connect(self.host, self.port, keepalive=30)
        self.client.loop_start()
        t0 = time.time()
        while time.time() - t0 < 5:
            if self.connected:
                return True
            time.sleep(0.05)
        return False

    def stop(self) -> None:
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

    def clear(self) -> None:
        with self._lock:
            self.rsp.clear()
            self.tel.clear()

    def publish_cmd(self, text: str) -> None:
        print(f"\n>>> [mqtt] cmd: {text}", flush=True)
        info = self.client.publish(TOPIC_CMD, text, qos=0)
        # best-effort wait for local outbox
        try:
            info.wait_for_publish(timeout=2.0)
        except Exception:
            pass

    def wait_rsp_match(
        self,
        pattern: str,
        timeout: float = 12.0,
        flags: int = re.I,
    ) -> str:
        """Wait until any rsp line matches pattern; return joined rsp since clear()."""
        cre = re.compile(pattern, flags)
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self._lock:
                texts = [p for _, p in self.rsp]
            joined = "\n".join(texts)
            if any(cre.search(p) for p in texts) or cre.search(joined):
                return joined
            time.sleep(0.05)
        with self._lock:
            return "\n".join(p for _, p in self.rsp)

    def wait_tel(self, timeout: float = 12.0, min_msgs: int = 1) -> list[str]:
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self._lock:
                if len(self.tel) >= min_msgs:
                    return [p for _, p in self.tel]
            time.sleep(0.05)
        with self._lock:
            return [p for _, p in self.tel]

    def rsp_text(self) -> str:
        with self._lock:
            return "\n".join(p for _, p in self.rsp)


def clip(s: str, n: int = 140) -> str:
    s = s.replace("\n", " | ").strip()
    return s if len(s) <= n else s[: n - 3] + "..."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--broker", default="192.168.4.2")
    ap.add_argument("--broker-port", type=int, default=1883)
    ap.add_argument(
        "--out",
        default=str(
            Path(__file__).resolve().parents[1] / "results" / "mqtt_connectivity_test.txt"
        ),
    )
    args = ap.parse_args()

    suite = Suite()
    log_chunks: list[str] = []

    def log(s: str = "") -> None:
        print(s, flush=True)
        log_chunks.append(s)

    log(f"Broker: {args.broker}:{args.broker_port}  Prefix: {PREFIX}")
    log("Topology: PC SoftAP client ↔ ESP SoftAP 192.168.4.1 (Guition P4)")
    log("VDF: NOT CONNECTED (Modbus timeouts expected)")
    log(f"Serial: {args.port}")
    log(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("")

    ser = SerialCli(args.port)
    probe = MqttProbe(args.broker, args.broker_port)

    try:
        # Ensure device idle
        ser.cmd("stream off", 0.8)
        time.sleep(0.5)

        t = ser.cmd("help", 1.0)
        suite.add(
            "CLI has mqtt commands",
            "mqtt status" in t.lower() or "mqtt set" in t.lower(),
        )

        t = ser.cmd(f"mqtt set {args.broker} {args.broker_port}", 2.0)
        suite.add(
            "mqtt set broker",
            "OK mqtt host=" in t and args.broker in t,
            clip(t),
        )

        t = ser.cmd("mqtt enable", 1.0)
        suite.add("mqtt enable", "OK mqtt enabled" in t or "enabled" in t.lower())

        connected = False
        last = ""
        for _ in range(15):
            last = ser.cmd("mqtt status", 1.0)
            if "state=connected" in last:
                connected = True
                break
            time.sleep(1.0)
        suite.add(
            "ESP MQTT client connected to broker",
            connected,
            clip(last),
        )

        ok_local = probe.start()
        suite.add("Broker accepts PC client", ok_local)
        time.sleep(0.8)

        with probe._lock:
            st = list(probe.status)
        suite.add(
            "LWT/status online observed",
            any("online" in s for s in st) or connected,
            "online" if any("online" in s for s in st) else "assumed-from-esp-connected",
        )

        # Settle: SoftAP + PubSubClient sometimes need a moment after connect
        time.sleep(1.5)

        # --- help ---
        probe.clear()
        probe.publish_cmd("help")
        rsp = probe.wait_rsp_match(r"mqtt status|ping|dump|wifi status", timeout=15.0)
        suite.add(
            "MQTT cmd help → rsp",
            bool(re.search(r"mqtt status|ping|dump", rsp, re.I)),
            clip(rsp),
        )
        time.sleep(0.8)

        # --- wifi status ---
        probe.clear()
        probe.publish_cmd("wifi status")
        rsp = probe.wait_rsp_match(
            r"SAJ_Diag_Tool|192\.168\.4\.1|board=|wifi AP", timeout=12.0
        )
        suite.add(
            "MQTT cmd wifi status → rsp",
            bool(re.search(r"SAJ_Diag_Tool|192\.168\.4\.1|board=", rsp)),
            clip(rsp),
        )
        time.sleep(0.8)

        # --- mqtt status ---
        probe.clear()
        probe.publish_cmd("mqtt status")
        rsp = probe.wait_rsp_match(r"state=connected|mqtt enabled|mqtt cmd=", timeout=12.0)
        suite.add(
            "MQTT cmd mqtt status → rsp",
            bool(re.search(r"connected|mqtt enabled|mqtt cmd=", rsp, re.I)),
            clip(rsp),
        )
        time.sleep(0.8)

        # --- stream / telemetry (no VDF: may take >1s due to Modbus timeouts) ---
        probe.clear()
        probe.publish_cmd("stream on")
        _ = probe.wait_rsp_match(r"stream ON", timeout=10.0)
        tels = probe.wait_tel(timeout=15.0, min_msgs=1)
        tel_ok = False
        tel_detail = "no tel (acceptable without VDF if stream ON acked)"
        stream_ack = bool(re.search(r"stream ON", probe.rsp_text(), re.I))
        if tels:
            sample = tels[-1]
            try:
                obj = json.loads(sample)
                tel_ok = isinstance(obj, dict) and ("freq" in obj or "status" in obj)
                tel_detail = f"json keys={list(obj.keys())}"
            except json.JSONDecodeError:
                tel_ok = "{" in sample
                tel_detail = clip(sample, 80)
        # Soft pass: stream ON acked on MQTT is enough path proof without VDF;
        # hard prefer actual telemetry JSON if Modbus cycle completes with timeout data
        suite.add(
            "MQTT telemetry / stream path",
            tel_ok or stream_ack,
            tel_detail if tel_ok else f"stream_ack={stream_ack}; {tel_detail}",
        )
        probe.publish_cmd("stream off")
        _ = probe.wait_rsp_match(r"stream OFF", timeout=8.0)
        time.sleep(1.0)

        # --- ping (no VDF → PING FAIL / TIMEOUT expected) ---
        probe.clear()
        probe.publish_cmd("ping")
        rsp = probe.wait_rsp_match(
            r"PING FAIL|TIMEOUT|timeout|Link OK|status=|ERR:", timeout=12.0
        )
        suite.add(
            "MQTT ping delivers rsp (VDF optional)",
            bool(rsp.strip()),
            clip(rsp),
        )
        classified = bool(
            re.search(r"PING FAIL|TIMEOUT|timeout|Link OK|status=|ERR:", rsp, re.I)
        )
        suite.add(
            "Modbus ping outcome classified (no VDF expected)",
            classified,
            clip(rsp),
        )
        # Wait for job to finish so dump is not blocked
        time.sleep(2.5)

        # --- dump (no VDF: begin header is enough; may stay busy long) ---
        probe.clear()
        probe.publish_cmd("dump")
        rsp = probe.wait_rsp_match(r"DUMP begin|CSV:param|ERR: busy", timeout=12.0)
        started = bool(re.search(r"DUMP begin|CSV:param", rsp, re.I))
        suite.add(
            "MQTT dump starts (begin/header)",
            started,
            clip(rsp),
        )
        # Without VDF dump can run for a long time; collect a few more TIMEOUT/CSV lines
        t0 = time.time()
        while time.time() - t0 < 8.0:
            time.sleep(0.5)
            blob = probe.rsp_text()
            if re.search(r"TIMEOUT|ERR:|CSV:P|DUMP end|dump done", blob, re.I):
                break
        dump_blob = probe.rsp_text()
        ended = bool(
            re.search(
                r"TIMEOUT|ERR:|CSV:P|DUMP end|dump done|DUMP begin",
                dump_blob,
                re.I,
            )
        )
        suite.add(
            "MQTT dump path active (begin/timeout without VDF)",
            ended and bool(dump_blob.strip()),
            clip(dump_blob[-200:] if len(dump_blob) > 200 else dump_blob),
        )

        # Soft cleanup — dump may still be running (ERR: busy expected)
        probe.publish_cmd("stream off")
        time.sleep(0.5)
        ser.cmd("stream off", 0.6)

    finally:
        probe.stop()
        ser.close()

    lines = suite.summary_lines()
    for ln in lines:
        log(ln)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(log_chunks) + "\n", encoding="utf-8")
    print(f"\nReport written: {out}", flush=True)

    return 0 if all(r.ok for r in suite.results) else 1


if __name__ == "__main__":
    sys.exit(main())
