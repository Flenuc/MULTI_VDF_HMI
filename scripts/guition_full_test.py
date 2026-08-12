#!/usr/bin/env python3
"""
Full field test suite — Guition JC-ESP32P4-M3-DEV + SAJ PDM-30 VDF + MQTT.

Sections:
  A) Serial CLI baseline
  B) Modbus / VDF (ping, status regs, P0/P1, safe write restore, dump sample)
  C) SoftAP reachability + Wi-Fi status
  D) MQTT (cmd/rsp, stream telemetry, ping over MQTT)

With VDF connected we expect Link OK and real register values.
Without working RS485 we still record FAIL with evidence (not crash).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
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
    section: str = ""


@dataclass
class Suite:
    results: list[Result] = field(default_factory=list)

    def add(self, section: str, name: str, ok: bool, detail: str = "") -> None:
        self.results.append(Result(name, ok, detail, section))
        tag = "PASS" if ok else "FAIL"
        extra = f" — {detail}" if detail else ""
        print(f"[{tag}] [{section}] {name}{extra}", flush=True)

    def summary(self) -> str:
        n_ok = sum(1 for r in self.results if r.ok)
        n_fail = len(self.results) - n_ok
        lines = [
            "",
            "=" * 64,
            f"GUITION FULL TEST: {n_ok} PASS / {n_fail} FAIL / {len(self.results)} total",
        ]
        cur = None
        for r in self.results:
            if r.section != cur:
                cur = r.section
                lines.append(f"  --- {cur} ---")
            tag = "PASS" if r.ok else "FAIL"
            extra = f" — {r.detail}" if r.detail else ""
            lines.append(f"  [{tag}] {r.name}{extra}")
        lines.append("=" * 64)
        return "\n".join(lines)


def clip(s: str, n: int = 160) -> str:
    s = (s or "").replace("\n", " | ").replace("\r", "").strip()
    return s if len(s) <= n else s[: n - 3] + "..."


class SerialCli:
    def __init__(self, port: str, baud: int = 115200):
        self.ser = serial.Serial(port, baud, timeout=0.25)
        time.sleep(0.4)
        self.ser.reset_input_buffer()

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass

    def _drain(self, settle: float = 0.15) -> str:
        time.sleep(settle)
        chunks: list[str] = []
        # quiet period: keep reading while data arrives
        quiet_deadline = time.time() + 0.25
        while time.time() < quiet_deadline:
            n = self.ser.in_waiting
            if n:
                chunks.append(self.ser.read(n).decode("utf-8", "replace"))
                quiet_deadline = time.time() + 0.25
            else:
                time.sleep(0.03)
        return "".join(chunks)

    def cmd(self, line: str, wait: float = 2.0) -> str:
        print(f"\n>>> [serial] {line}", flush=True)
        self.ser.reset_input_buffer()
        self.ser.write((line + "\n").encode("utf-8"))
        t0 = time.time()
        chunks: list[str] = []
        while time.time() - t0 < wait:
            n = self.ser.in_waiting
            if n:
                chunks.append(self.ser.read(n).decode("utf-8", "replace"))
            else:
                time.sleep(0.04)
        chunks.append(self._drain(0.1))
        text = "".join(chunks)
        print(text, end="" if text.endswith("\n") else "\n", flush=True)
        return text

    def cmd_until(self, line: str, pattern: str, timeout: float = 8.0) -> str:
        print(f"\n>>> [serial] {line}  (wait /{pattern}/ ≤{timeout}s)", flush=True)
        self.ser.reset_input_buffer()
        self.ser.write((line + "\n").encode("utf-8"))
        cre = re.compile(pattern, re.I)
        t0 = time.time()
        chunks: list[str] = []
        matched = False
        while time.time() - t0 < timeout:
            n = self.ser.in_waiting
            if n:
                chunks.append(self.ser.read(n).decode("utf-8", "replace"))
                if cre.search("".join(chunks)):
                    matched = True
                    # keep draining a bit for multi-line replies
                    time.sleep(0.35)
                    if self.ser.in_waiting:
                        chunks.append(self.ser.read(self.ser.in_waiting).decode("utf-8", "replace"))
                    break
            else:
                time.sleep(0.05)
        if not matched:
            chunks.append(self._drain(0.15))
        else:
            chunks.append(self._drain(0.2))
        text = "".join(chunks)
        print(text, end="" if text.endswith("\n") else "\n", flush=True)
        return text


class MqttProbe:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.rsp: list[str] = []
        self.tel: list[str] = []
        self.status: list[str] = []
        self._lock = threading.Lock()
        self.connected = False
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"guition-test-{int(time.time()) % 100000}",
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        ok = (reason_code == 0) or (str(reason_code) == "Success")
        self.connected = ok
        print(f"[paho] connected rc={reason_code} ok={ok}", flush=True)
        if ok:
            client.subscribe([(TOPIC_RSP, 0), (TOPIC_TEL, 0), (TOPIC_STAT, 0)])

    def _on_message(self, client, userdata, msg):
        payload = msg.payload.decode("utf-8", "replace")
        with self._lock:
            if msg.topic == TOPIC_RSP:
                self.rsp.append(payload)
            elif msg.topic == TOPIC_TEL:
                self.tel.append(payload)
            elif msg.topic == TOPIC_STAT:
                self.status.append(payload)
        print(f"[paho] {msg.topic}: {payload[:180]}", flush=True)

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
        try:
            info.wait_for_publish(timeout=2.0)
        except Exception:
            pass

    def wait_rsp(self, pattern: str, timeout: float = 12.0) -> str:
        cre = re.compile(pattern, re.I)
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self._lock:
                joined = "\n".join(self.rsp)
            if cre.search(joined):
                return joined
            time.sleep(0.05)
        with self._lock:
            return "\n".join(self.rsp)

    def wait_tel(self, timeout: float = 12.0) -> list[str]:
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self._lock:
                if self.tel:
                    return list(self.tel)
            time.sleep(0.05)
        with self._lock:
            return list(self.tel)


def ensure_softap(ssid: str = "SAJ_Diag_Tool", password: str = "sajpdm30") -> tuple[bool, str]:
    """Associate PC wlan0 to SoftAP; return (ok, detail)."""
    # already associated?
    try:
        out = subprocess.check_output(
            ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"],
            text=True,
            timeout=10,
        )
        for line in out.splitlines():
            if line.startswith("yes:") and ssid in line:
                # check IP
                ip = subprocess.check_output(["ip", "-4", "-o", "addr", "show", "wlan0"], text=True)
                if "192.168.4." in ip:
                    return True, f"already on {ssid}: {ip.strip()}"
    except Exception as e:
        pass

    try:
        subprocess.run(["nmcli", "con", "down", ssid], capture_output=True, timeout=15)
    except Exception:
        pass
    time.sleep(1)
    try:
        subprocess.run(["nmcli", "device", "wifi", "rescan"], capture_output=True, timeout=15)
    except Exception:
        pass
    time.sleep(2)

    r = subprocess.run(
        ["nmcli", "con", "up", ssid],
        capture_output=True,
        text=True,
        timeout=40,
    )
    if r.returncode != 0:
        r = subprocess.run(
            ["nmcli", "dev", "wifi", "connect", ssid, "password", password],
            capture_output=True,
            text=True,
            timeout=40,
        )
    time.sleep(3)
    try:
        ip = subprocess.check_output(["ip", "-4", "-o", "addr", "show", "wlan0"], text=True)
    except Exception as e:
        return False, f"no wlan0 ip: {e}"
    ok = "192.168.4." in ip and r.returncode == 0
    # ping AP
    pr = subprocess.run(
        ["ping", "-c", "2", "-W", "2", "192.168.4.1"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    ping_ok = pr.returncode == 0 or "bytes from" in pr.stdout
    detail = f"nmcli rc={r.returncode}; {ip.strip()}; ping_ok={ping_ok}"
    return ok or ping_ok, detail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="auto")
    ap.add_argument("--broker", default="192.168.4.2")
    ap.add_argument("--broker-port", type=int, default=1883)
    ap.add_argument(
        "--out",
        default=str(
            Path(__file__).resolve().parents[1] / "results" / "guition_full_test.txt"
        ),
    )
    ap.add_argument("--skip-mqtt", action="store_true")
    ap.add_argument("--skip-softap", action="store_true")
    ap.add_argument("--dump-timeout", type=float, default=45.0)
    args = ap.parse_args()

    suite = Suite()
    log: list[str] = []

    def L(s: str = "") -> None:
        print(s, flush=True)
        log.append(s)

    # resolve serial port
    port = args.port
    if port == "auto":
        for cand in ("/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyUSB0"):
            if Path(cand).exists():
                port = cand
                break
        else:
            print("ERROR: no serial port found", flush=True)
            return 2

    L(f"Guition full test — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    L(f"Serial: {port}")
    L(f"MQTT broker target: {args.broker}:{args.broker_port}")
    L("VDF: CONNECTED (expected Link OK / real regs)")
    L("")

    ser = SerialCli(port)
    probe: MqttProbe | None = None

    try:
        # Reduce MQTT reconnect spam while testing Modbus (re-enable later)
        ser.cmd("stream off", 1.0)
        ser.cmd("mqtt disable", 1.0)

        # ========== A) Serial baseline ==========
        t = ser.cmd("help", 2.0)
        suite.add(
            "A-CLI",
            "help lists core + mqtt commands",
            bool(re.search(r"ping|dump|mqtt status|wifi status", t, re.I)),
            clip(t, 100),
        )

        t = ser.cmd_until(
            "wifi status",
            r"board=|SAJ_Diag_Tool|wifi AP",
            timeout=5.0,
        )
        suite.add(
            "A-CLI",
            "wifi status shows Guition board",
            "Guition" in t or "SAJ_Diag_Tool" in t or "board=" in t,
            clip(t, 140),
        )
        suite.add(
            "A-CLI",
            "SoftAP advertised",
            "SAJ_Diag_Tool" in t and "192.168.4.1" in t,
            clip(t, 120),
        )

        t = ser.cmd_until("mqtt status", r"mqtt enabled|host=", timeout=4.0)
        suite.add(
            "A-CLI",
            "mqtt status available",
            "mqtt" in t.lower() and ("host=" in t or "enabled" in t),
            clip(t, 120),
        )

        # ========== B) Modbus / VDF ==========
        t = ser.cmd_until("ping", r"Link OK|PING FAIL|Timeout|ERR:", timeout=10.0)
        link_ok = "Link OK" in t or bool(re.search(r"status=\d+", t))
        # also accept multi-line success without literal "Link OK" if status+freq present
        if re.search(r"status=\d+", t) and re.search(r"freq=", t):
            link_ok = True
        suite.add(
            "B-Modbus",
            "ping / Link OK (VDF connected)",
            link_ok,
            clip(t, 160),
        )

        t = ser.cmd_until("raw 0x3000", r"0x3000\s*=|ERR:|Timeout", timeout=6.0)
        suite.add(
            "B-Modbus",
            "raw status 0x3000",
            bool(re.search(r"0x3000\s*=\s*\d+", t)),
            clip(t),
        )

        t = ser.cmd_until("raw 0x1001", r"0x1001\s*=|ERR:|Timeout", timeout=6.0)
        suite.add(
            "B-Modbus",
            "raw run freq 0x1001",
            bool(re.search(r"0x1001\s*=\s*\d+", t)),
            clip(t),
        )

        t = ser.cmd_until("r0 0", r"P0-00|ERR:|Timeout", timeout=6.0)
        suite.add(
            "B-Modbus",
            "r0 0 (P0-00 pressure setting)",
            bool(re.search(r"P0-00\s*@0x0000", t)),
            clip(t),
        )

        t = ser.cmd_until("r1 35", r"P1-35|ERR:|Timeout", timeout=6.0)
        suite.add(
            "B-Modbus",
            "r1 35 (local address)",
            bool(re.search(r"P1-35\s*@0x0123", t)),
            clip(t),
        )

        t = ser.cmd_until("r1 36", r"P1-36|ERR:|Timeout", timeout=6.0)
        suite.add(
            "B-Modbus",
            "r1 36 (baud)",
            bool(re.search(r"P1-36\s*@0x0124", t)),
            clip(t),
        )

        # Safe write restore only if read works
        if any(r.ok and r.name.startswith("r0 0") for r in suite.results):
            # parse current eng value if present
            t0 = ser.cmd_until("r0 0", r"P0-00|ERR:", timeout=5.0)
            m = re.search(r"=\s*([0-9.]+)", t0)
            base = m.group(1) if m else None
            if base is not None:
                try:
                    base_f = float(base)
                    alt = base_f + 0.1 if base_f < 1000 else base_f
                    # write small delta then restore — only if first write OK
                    tw = ser.cmd_until(f"w0 0 {alt}", r"OK write|ERR:", timeout=6.0)
                    w_ok = "OK write" in tw
                    suite.add("B-Modbus", "w0 0 write delta", w_ok, clip(tw))
                    tr = ser.cmd_until(f"w0 0 {base}", r"OK write|ERR:", timeout=6.0)
                    suite.add("B-Modbus", "w0 0 restore", "OK write" in tr, clip(tr))
                except ValueError:
                    suite.add("B-Modbus", "w0 write/restore", False, "could not parse base")
            else:
                suite.add("B-Modbus", "w0 write/restore", False, "skip — no base value")
        else:
            suite.add(
                "B-Modbus",
                "w0 write/restore",
                False,
                "skipped — r0 failed (no RS485 link)",
            )

        # Dump: with VDF should produce CSV rows; without → ERROR rows but begin
        t = ser.cmd_until(
            "dump",
            r"DUMP begin|CSV:P0|ERR: busy",
            timeout=8.0,
        )
        dump_begin = "DUMP begin" in t or "CSV:param" in t
        suite.add("B-Modbus", "dump begins", dump_begin, clip(t, 120))

        # Collect dump for a while
        t0 = time.time()
        dump_extra: list[str] = [t]
        while time.time() - t0 < min(args.dump_timeout, 25.0):
            time.sleep(0.4)
            if ser.ser.in_waiting:
                chunk = ser.ser.read(ser.ser.in_waiting).decode("utf-8", "replace")
                dump_extra.append(chunk)
                print(chunk, end="", flush=True)
            joined = "".join(dump_extra)
            if re.search(r"DUMP end|dump done|DUMP complete", joined, re.I):
                break
            # enough evidence: real eng values or many ERROR lines
            if len(re.findall(r"CSV:P\d", joined)) >= 8:
                # if we have non-ERROR eng values, great; else keep a bit more
                if re.search(r"CSV:P0-\d+,[^,]+,[0-9.]+,\d+", joined):
                    break
                if time.time() - t0 > 12:
                    break

        dump_blob = "".join(dump_extra)
        real_csv = bool(
            re.search(r"CSV:P[01]-\d{2},0x[0-9A-Fa-f]+,[0-9.eE+-]+,\d+", dump_blob)
        )
        error_csv = "ERROR" in dump_blob
        suite.add(
            "B-Modbus",
            "dump yields real param CSV (VDF)",
            real_csv,
            clip(
                f"real={real_csv} error_rows={error_csv} sample="
                + re.sub(r"\s+", " ", dump_blob)[:140]
            ),
        )

        # Let dump continue or wait — soft stop by stream off (may busy)
        ser.cmd("stream off", 1.0)
        time.sleep(1.0)

        # ========== C) SoftAP ==========
        if not args.skip_softap:
            ok_ap, det = ensure_softap()
            suite.add("C-SoftAP", "PC associated to SAJ_Diag_Tool", ok_ap, det)
            pr = subprocess.run(
                ["ping", "-c", "3", "-W", "2", "192.168.4.1"],
                capture_output=True,
                text=True,
                timeout=12,
            )
            suite.add(
                "C-SoftAP",
                "ICMP to 192.168.4.1",
                "bytes from" in pr.stdout,
                clip(pr.stdout + pr.stderr, 120),
            )
        else:
            suite.add("C-SoftAP", "SoftAP tests", True, "skipped")

        # ========== D) MQTT ==========
        if args.skip_mqtt:
            suite.add("D-MQTT", "MQTT suite", True, "skipped")
        else:
            # Point ESP broker to PC SoftAP IP and re-enable
            t = ser.cmd(f"mqtt set {args.broker} {args.broker_port}", 2.5)
            suite.add(
                "D-MQTT",
                "mqtt set broker",
                "OK mqtt host=" in t and args.broker in t,
                clip(t),
            )
            ser.cmd("mqtt enable", 1.0)
            connected = False
            last = ""
            for _ in range(15):
                last = ser.cmd_until("mqtt status", r"state=|mqtt enabled", timeout=3.0)
                if "state=connected" in last:
                    connected = True
                    break
                time.sleep(1.0)
            suite.add(
                "D-MQTT",
                "ESP MQTT connected",
                connected,
                clip(last),
            )

            probe = MqttProbe(args.broker, args.broker_port)
            pc_ok = probe.start()
            suite.add("D-MQTT", "PC MQTT client to broker", pc_ok)
            time.sleep(1.5)
            with probe._lock:
                st = list(probe.status)
            suite.add(
                "D-MQTT",
                "status online",
                any("online" in s for s in st) or connected,
                ",".join(st) if st else "n/a",
            )
            time.sleep(2.0)

            if connected and pc_ok:
                probe.clear()
                probe.publish_cmd("help")
                rsp = probe.wait_rsp(r"ping|mqtt status|dump", 18.0)
                suite.add("D-MQTT", "cmd help → rsp", bool(re.search(r"ping|mqtt", rsp, re.I)), clip(rsp))
                time.sleep(0.8)

                probe.clear()
                probe.publish_cmd("wifi status")
                rsp = probe.wait_rsp(r"SAJ_Diag_Tool|board=|192\.168\.4\.1", 15.0)
                suite.add(
                    "D-MQTT",
                    "cmd wifi status → rsp",
                    bool(re.search(r"SAJ_Diag_Tool|board=", rsp)),
                    clip(rsp),
                )
                time.sleep(0.8)

                probe.clear()
                probe.publish_cmd("ping")
                rsp = probe.wait_rsp(r"Link OK|PING FAIL|Timeout|status=", 18.0)
                mqtt_link = "Link OK" in rsp or bool(
                    re.search(r"status=\d+.*freq=|freq=.*status=", rsp, re.S)
                )
                # Path proof: any classified ping outcome over MQTT
                mqtt_ping_path = bool(rsp.strip()) and bool(
                    re.search(r"Link OK|PING FAIL|Timeout|status=", rsp, re.I)
                )
                suite.add(
                    "D-MQTT",
                    "cmd ping delivers classified rsp",
                    mqtt_ping_path,
                    clip(rsp),
                )
                suite.add(
                    "D-MQTT",
                    "cmd ping → Link OK (VDF)",
                    mqtt_link,
                    clip(rsp),
                )
                time.sleep(1.0)

                probe.clear()
                probe.publish_cmd("stream on")
                _ = probe.wait_rsp(r"stream ON", 12.0)
                tels = probe.wait_tel(15.0)
                tel_ok = False
                tel_det = "no tel"
                if tels:
                    try:
                        obj = json.loads(tels[-1])
                        tel_ok = isinstance(obj, dict) and "freq" in obj
                        tel_det = json.dumps(obj)
                    except json.JSONDecodeError:
                        tel_det = clip(tels[-1])
                suite.add("D-MQTT", "telemetry JSON stream", tel_ok, clip(tel_det, 180))
                probe.publish_cmd("stream off")
                _ = probe.wait_rsp(r"stream OFF", 10.0)
            else:
                for name in (
                    "cmd help → rsp",
                    "cmd wifi status → rsp",
                    "cmd ping delivers classified rsp",
                    "cmd ping → Link OK (VDF)",
                    "telemetry JSON stream",
                ):
                    suite.add("D-MQTT", name, False, "skipped — MQTT not connected")

    finally:
        if probe:
            probe.stop()
        try:
            ser.cmd("stream off", 0.8)
        except Exception:
            pass
        ser.close()

    body = suite.summary()
    L(body)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # merge live log header + summary
    out.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"\nReport: {out}", flush=True)
    return 0 if all(r.ok for r in suite.results) else 1


if __name__ == "__main__":
    sys.exit(main())
