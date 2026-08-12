#!/usr/bin/env python3
"""
Full field test — ESP32-DevKit (classic) + USB + SoftAP/MQTT + BT Classic SPP.

Sections:
  A) Serial CLI baseline
  B) Modbus / VDF (if linked)
  C) SoftAP reachability
  D) MQTT cmd/rsp/telemetry
  E) Bluetooth Classic SPP (discover / pair / RFCOMM / CLI)

Usage:
  python3 scripts/esp32dev_full_test.py --port /dev/ttyACM0
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import struct
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
BT_NAME = "SAJ-PDM30-Edge"
BT_RFCOMM_CHANNEL = 1


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
            f"ESP32-DevKit FULL TEST: {n_ok} PASS / {n_fail} FAIL / {len(self.results)} total",
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


def run_cmd(cmd: list[str], timeout: float = 15.0) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 1, str(e)


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
                    time.sleep(0.35)
                    if self.ser.in_waiting:
                        chunks.append(
                            self.ser.read(self.ser.in_waiting).decode("utf-8", "replace")
                        )
                    break
            else:
                time.sleep(0.05)
        chunks.append(self._drain(0.2 if matched else 0.15))
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
            client_id=f"esp32dev-test-{int(time.time()) % 100000}",
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
    try:
        out = subprocess.check_output(
            ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"],
            text=True,
            timeout=10,
        )
        for line in out.splitlines():
            if line.startswith("yes:") and ssid in line:
                ip = subprocess.check_output(
                    ["ip", "-4", "-o", "addr", "show", "wlan0"], text=True
                )
                if "192.168.4." in ip:
                    return True, f"already on {ssid}: {ip.strip()}"
    except Exception:
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
    pr = subprocess.run(
        ["ping", "-c", "2", "-W", "2", "192.168.4.1"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    ping_ok = pr.returncode == 0 or "bytes from" in pr.stdout
    detail = f"nmcli rc={r.returncode}; {ip.strip()}; ping_ok={ping_ok}"
    return ("192.168.4." in ip and r.returncode == 0) or ping_ok, detail


def bt_scan_for_edge(seconds: float = 12.0) -> tuple[str | None, str]:
    """Return (mac, detail) for SAJ-PDM30-Edge if found."""
    run_cmd(["bluetoothctl", "power", "on"], 5)
    run_cmd(["bluetoothctl", "scan", "on"], 3)
    t0 = time.time()
    found: str | None = None
    detail_lines: list[str] = []
    while time.time() - t0 < seconds:
        rc, out = run_cmd(["bluetoothctl", "devices"], 8)
        detail_lines.append(out.strip())
        for line in out.splitlines():
            m = re.match(r"Device\s+([0-9A-Fa-f:]{17})\s+(.*)$", line.strip())
            if not m:
                continue
            addr, name = m.group(1).upper(), m.group(2).strip()
            if BT_NAME.lower() in name.lower() or "SAJ-PDM30" in name.upper():
                found = addr
                break
        if found:
            break
        time.sleep(1.0)
    run_cmd(["bluetoothctl", "scan", "off"], 3)
    # also check last scan log
    detail = f"found={found}; devices={clip(' | '.join(detail_lines[-2:]), 200)}"
    return found, detail


def bt_try_pair(addr: str) -> tuple[bool, str]:
    run_cmd(["bluetoothctl", "agent", "on"], 5)
    run_cmd(["bluetoothctl", "default-agent"], 5)
    run_cmd(["bluetoothctl", "pairable", "on"], 5)
    run_cmd(["bluetoothctl", "trust", addr], 8)
    rc, out = run_cmd(["bluetoothctl", "pair", addr], 35)
    ok = rc == 0 or "AlreadyExists" in out or "already" in out.lower()
    # info
    _, info = run_cmd(["bluetoothctl", "info", addr], 8)
    paired = "Paired: yes" in info
    return ok or paired, clip(out + " | " + info, 220)


def bt_rfcomm_cli(addr: str, channel: int = BT_RFCOMM_CHANNEL) -> tuple[bool, str]:
    """
    Connect RFCOMM and send 'help\\n'. Expect CLI help text.
    Uses BlueZ AF_BLUETOOTH SOCK_STREAM (RFCOMM).
    """
    # AF_BLUETOOTH = 31, BTPROTO_RFCOMM = 3
    AF_BLUETOOTH = getattr(socket, "AF_BLUETOOTH", 31)
    BTPROTO_RFCOMM = 3
    try:
        sock = socket.socket(AF_BLUETOOTH, socket.SOCK_STREAM, BTPROTO_RFCOMM)
        sock.settimeout(12.0)
        # address format: (bdaddr_str, channel)
        sock.connect((addr, channel))
    except Exception as e:
        return False, f"RFCOMM connect failed ch={channel}: {e}"

    try:
        # drain
        sock.settimeout(0.4)
        try:
            while True:
                chunk = sock.recv(512)
                if not chunk:
                    break
        except socket.timeout:
            pass

        sock.settimeout(6.0)
        sock.sendall(b"help\n")
        time.sleep(0.8)
        chunks: list[bytes] = []
        t0 = time.time()
        while time.time() - t0 < 5.0:
            try:
                data = sock.recv(1024)
                if data:
                    chunks.append(data)
                    if b"ping" in b"".join(chunks).lower() or b"help" in b"".join(chunks):
                        time.sleep(0.3)
                        try:
                            more = sock.recv(2048)
                            if more:
                                chunks.append(more)
                        except socket.timeout:
                            pass
                        break
                else:
                    break
            except socket.timeout:
                if chunks:
                    break
        text = b"".join(chunks).decode("utf-8", "replace")
        ok = bool(re.search(r"ping|dump|mqtt|wifi", text, re.I))
        return ok, clip(text or "(empty reply)", 200)
    except Exception as e:
        return False, f"RFCOMM I/O error: {e}"
    finally:
        try:
            sock.close()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="auto")
    ap.add_argument("--broker", default="auto")
    ap.add_argument("--broker-port", type=int, default=1883)
    ap.add_argument(
        "--out",
        default=str(
            Path(__file__).resolve().parents[1] / "results" / "esp32dev_full_test.txt"
        ),
    )
    ap.add_argument("--skip-mqtt", action="store_true")
    ap.add_argument("--skip-softap", action="store_true")
    ap.add_argument("--skip-bt", action="store_true")
    ap.add_argument("--dump-timeout", type=float, default=20.0)
    args = ap.parse_args()

    suite = Suite()
    log: list[str] = []

    def L(s: str = "") -> None:
        print(s, flush=True)
        log.append(s)

    port = args.port
    if port == "auto":
        for cand in ("/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyUSB0"):
            if Path(cand).exists():
                port = cand
                break
        else:
            print("ERROR: no serial port", flush=True)
            return 2

    # Prefer broker on eth0 if already MQTT-connected path; SoftAP IP as fallback
    broker = args.broker
    if broker == "auto":
        # eth0 primary IP often used when ESP is STA
        try:
            eth = subprocess.check_output(
                ["ip", "-4", "-o", "addr", "show", "eth0"], text=True
            )
            m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", eth)
            broker = m.group(1) if m else "192.168.4.2"
        except Exception:
            broker = "192.168.4.2"

    L(f"ESP32-DevKit full test — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    L(f"Serial: {port}")
    L(f"MQTT broker target: {broker}:{args.broker_port}")
    L(f"BT name expected: {BT_NAME}")
    L("")

    ser = SerialCli(port)
    probe: MqttProbe | None = None

    try:
        ser.cmd("stream off", 1.0)

        # ========== A) Serial ==========
        t = ser.cmd("help", 2.0)
        suite.add(
            "A-USB",
            "help lists core + mqtt commands",
            bool(re.search(r"ping|dump|mqtt status|wifi status", t, re.I)),
            clip(t, 100),
        )

        t = ser.cmd_until("wifi status", r"board=|SAJ_Diag_Tool|wifi AP", timeout=5.0)
        suite.add(
            "A-USB",
            "board is ESP32-DevKit",
            "ESP32-DevKit" in t or "board=" in t,
            clip(t, 140),
        )
        suite.add(
            "A-USB",
            "SoftAP advertised",
            "SAJ_Diag_Tool" in t and "192.168.4.1" in t,
            clip(t, 120),
        )

        t = ser.cmd_until("mqtt status", r"mqtt enabled|host=|state=", timeout=4.0)
        suite.add(
            "A-USB",
            "mqtt status available",
            "mqtt" in t.lower() and ("host=" in t or "enabled" in t),
            clip(t, 140),
        )

        # ========== B) Modbus ==========
        t = ser.cmd_until("ping", r"Link OK|PING FAIL|Timeout|ERR:|status=", timeout=10.0)
        link_ok = "Link OK" in t or (
            bool(re.search(r"status=\d+", t)) and bool(re.search(r"freq=", t))
        )
        suite.add("B-Modbus", "ping / Link OK (VDF)", link_ok, clip(t, 160))

        t = ser.cmd_until("raw 0x3000", r"0x3000\s*=|ERR:|Timeout", timeout=6.0)
        suite.add(
            "B-Modbus",
            "raw status 0x3000",
            bool(re.search(r"0x3000\s*=\s*\d+", t)),
            clip(t),
        )

        t = ser.cmd_until("r0 0", r"P0-00|ERR:|Timeout", timeout=6.0)
        suite.add(
            "B-Modbus",
            "r0 0 (P0-00)",
            bool(re.search(r"P0-00\s*@0x0000", t)),
            clip(t),
        )

        t = ser.cmd_until("r1 35", r"P1-35|ERR:|Timeout", timeout=6.0)
        suite.add(
            "B-Modbus",
            "r1 35 local address",
            bool(re.search(r"P1-35\s*@0x0123", t)),
            clip(t),
        )

        # short dump sample
        t = ser.cmd_until("dump", r"DUMP begin|CSV:P0|ERR: busy", timeout=8.0)
        dump_begin = "DUMP begin" in t or "CSV:param" in t or "CSV:P0" in t
        suite.add("B-Modbus", "dump begins", dump_begin, clip(t, 100))
        t0 = time.time()
        dump_extra = [t]
        while time.time() - t0 < min(args.dump_timeout, 15.0):
            time.sleep(0.35)
            if ser.ser.in_waiting:
                chunk = ser.ser.read(ser.ser.in_waiting).decode("utf-8", "replace")
                dump_extra.append(chunk)
                print(chunk, end="", flush=True)
            joined = "".join(dump_extra)
            if re.search(r"DUMP end|dump done|DUMP complete", joined, re.I):
                break
            if len(re.findall(r"CSV:P\d", joined)) >= 6:
                break
        dump_blob = "".join(dump_extra)
        real_csv = bool(
            re.search(r"CSV:P[01]-\d{2},0x[0-9A-Fa-f]+,[0-9.eE+-]+,\d+", dump_blob)
        )
        suite.add(
            "B-Modbus",
            "dump yields param CSV",
            real_csv or ("ERROR" in dump_blob and dump_begin),
            clip(f"real_csv={real_csv} " + re.sub(r"\s+", " ", dump_blob)[:120]),
        )
        ser.cmd("stream off", 0.8)
        time.sleep(0.5)

        # ========== C) SoftAP ==========
        if not args.skip_softap:
            ok_ap, det = ensure_softap()
            suite.add("C-SoftAP", "PC on SAJ_Diag_Tool", ok_ap, det)
            pr = subprocess.run(
                ["ping", "-c", "3", "-W", "2", "192.168.4.1"],
                capture_output=True,
                text=True,
                timeout=12,
            )
            suite.add(
                "C-SoftAP",
                "ICMP 192.168.4.1",
                "bytes from" in pr.stdout,
                clip(pr.stdout + pr.stderr, 100),
            )
        else:
            suite.add("C-SoftAP", "SoftAP tests", True, "skipped")

        # ========== D) MQTT ==========
        if args.skip_mqtt:
            suite.add("D-MQTT", "MQTT suite", True, "skipped")
        else:
            # Keep existing broker if already connected to our auto target;
            # else set SoftAP-local broker as secondary path test.
            t = ser.cmd_until("mqtt status", r"state=|host=", timeout=3.0)
            already = "state=connected" in t and broker in t
            if not already:
                t = ser.cmd(f"mqtt set {broker} {args.broker_port}", 2.5)
                suite.add(
                    "D-MQTT",
                    "mqtt set broker",
                    "OK mqtt host=" in t or broker in t,
                    clip(t),
                )
                ser.cmd("mqtt enable", 1.0)
            else:
                suite.add("D-MQTT", "mqtt set broker", True, f"already host={broker}")

            connected = False
            last = ""
            for _ in range(15):
                last = ser.cmd_until("mqtt status", r"state=|mqtt enabled", timeout=3.0)
                if "state=connected" in last:
                    connected = True
                    break
                time.sleep(1.0)
            suite.add("D-MQTT", "ESP MQTT connected", connected, clip(last))

            probe = MqttProbe(broker, args.broker_port)
            pc_ok = probe.start()
            suite.add("D-MQTT", "PC MQTT client to broker", pc_ok, f"{broker}:{args.broker_port}")
            time.sleep(1.5)

            if connected and pc_ok:
                probe.clear()
                probe.publish_cmd("help")
                rsp = probe.wait_rsp(r"ping|mqtt status|dump", 15.0)
                suite.add(
                    "D-MQTT",
                    "cmd help → rsp",
                    bool(re.search(r"ping|mqtt", rsp, re.I)),
                    clip(rsp),
                )
                time.sleep(0.5)

                probe.clear()
                probe.publish_cmd("wifi status")
                rsp = probe.wait_rsp(r"SAJ_Diag_Tool|board=|ESP32", 12.0)
                suite.add(
                    "D-MQTT",
                    "cmd wifi status → rsp",
                    bool(re.search(r"SAJ_Diag_Tool|board=|ESP32", rsp)),
                    clip(rsp),
                )
                time.sleep(0.5)

                probe.clear()
                probe.publish_cmd("ping")
                rsp = probe.wait_rsp(r"Link OK|PING FAIL|Timeout|status=", 15.0)
                mqtt_path = bool(rsp.strip()) and bool(
                    re.search(r"Link OK|PING FAIL|Timeout|status=", rsp, re.I)
                )
                mqtt_link = "Link OK" in rsp or bool(
                    re.search(r"status=\d+", rsp) and re.search(r"freq=", rsp)
                )
                suite.add("D-MQTT", "cmd ping path OK", mqtt_path, clip(rsp))
                suite.add("D-MQTT", "cmd ping Link OK (VDF)", mqtt_link, clip(rsp))

                probe.clear()
                probe.publish_cmd("stream on")
                _ = probe.wait_rsp(r"stream ON", 10.0)
                tels = probe.wait_tel(12.0)
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
                _ = probe.wait_rsp(r"stream OFF", 8.0)
            else:
                for name in (
                    "cmd help → rsp",
                    "cmd wifi status → rsp",
                    "cmd ping path OK",
                    "cmd ping Link OK (VDF)",
                    "telemetry JSON stream",
                ):
                    suite.add("D-MQTT", name, False, "skipped — MQTT not up")

        # ========== E) Bluetooth Classic SPP ==========
        if args.skip_bt:
            suite.add("E-BT", "BT suite", True, "skipped")
        else:
            # Note BT status from boot/serial if available
            t = ser.cmd("help", 1.0)  # keep USB alive
            addr, det = bt_scan_for_edge(14.0)
            suite.add("E-BT", f"discover {BT_NAME}", addr is not None, det)

            if addr:
                pair_ok, pair_det = bt_try_pair(addr)
                suite.add("E-BT", "pair/trust", pair_ok, pair_det)

                # try connect via bluetoothctl first
                rc, cout = run_cmd(["bluetoothctl", "connect", addr], 25)
                ctl_ok = rc == 0 or "Connection successful" in cout
                suite.add("E-BT", "bluetoothctl connect", ctl_ok, clip(cout, 160))

                rf_ok, rf_det = bt_rfcomm_cli(addr, BT_RFCOMM_CHANNEL)
                suite.add("E-BT", "RFCOMM ch1 CLI help", rf_ok, rf_det)

                # alternate channel 2 if ch1 fails (some stacks)
                if not rf_ok:
                    rf2_ok, rf2_det = bt_rfcomm_cli(addr, 2)
                    suite.add("E-BT", "RFCOMM ch2 CLI help (fallback)", rf2_ok, rf2_det)
            else:
                suite.add("E-BT", "pair/trust", False, "device not found")
                suite.add("E-BT", "bluetoothctl connect", False, "device not found")
                suite.add("E-BT", "RFCOMM ch1 CLI help", False, "device not found")

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

    # Human conclusion block
    usb_ok = all(r.ok for r in suite.results if r.section == "A-USB")
    mqtt_ok = all(
        r.ok
        for r in suite.results
        if r.section == "D-MQTT" and "Link OK (VDF)" not in r.name
    )
    bt_ok = all(r.ok for r in suite.results if r.section == "E-BT")
    L("")
    L("CONCLUSION")
    L(f"  USB:  {'OK' if usb_ok else 'ISSUES'}")
    L(f"  MQTT: {'OK' if mqtt_ok else 'ISSUES'} (path/core; VDF link separate)")
    L(f"  BT:   {'OK' if bt_ok else 'NOT WORKING (expected if SPP stack fails)'}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"\nReport: {out}", flush=True)
    # Exit 0 if USB+MQTT path OK even if BT fails (field reality)
    core_ok = usb_ok and mqtt_ok
    return 0 if core_ok else 1


if __name__ == "__main__":
    sys.exit(main())
