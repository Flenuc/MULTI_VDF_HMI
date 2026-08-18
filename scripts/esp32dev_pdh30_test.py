#!/usr/bin/env python3
"""
ESP32-DevKit + SAJ PDH-30 field regression via Edge USB CLI.

Focus: prove Edge is DevKit, then exercise Modbus/PDH map. Optionally probes
RS485 diagnosis commands (firmware ≥ 0.3.5):
  rs485 status | rs485 de invert|normal | rs485 swaptrx

Usage:
  python3 scripts/esp32dev_pdh30_test.py --port /dev/ttyACM0
  python3 scripts/esp32dev_pdh30_test.py --port /dev/ttyACM0 --try-rs485-diag
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
PLANT = ROOT / "drive_profiles" / "saj" / "pdh30" / "plant_priority_ids.json"

try:
    import serial
except ImportError:
    print("pip install pyserial", file=sys.stderr)
    sys.exit(1)


def strip_prompt(s: str) -> str:
    return "\n".join(
        ln[2:] if ln.startswith("> ") else ln for ln in s.splitlines()
    )


class Cli:
    def __init__(self, port: str, baud: int = 115200):
        self.ser = serial.Serial(port, baud, timeout=0.2)
        time.sleep(0.8)
        self.ser.write(b"\n")
        time.sleep(0.2)
        self.ser.reset_input_buffer()

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass

    def cmd(self, line: str, wait: float = 3.0) -> str:
        print(f"\n>>> {line}", flush=True)
        self.ser.reset_input_buffer()
        self.ser.write((line + "\n").encode("utf-8"))
        self.ser.flush()
        t0 = time.time()
        buf = ""
        while time.time() - t0 < wait:
            n = self.ser.in_waiting
            if n:
                buf += self.ser.read(n).decode("utf-8", "replace")
            else:
                time.sleep(0.04)
        print(buf, end="" if buf.endswith("\n") else "\n", flush=True)
        return buf


def ok(name: str, passed: bool, detail: str = "") -> dict:
    tag = "PASS" if passed else "FAIL"
    extra = f" — {detail}" if detail else ""
    print(f"[{tag}] {name}{extra}", flush=True)
    return {"name": name, "ok": passed, "detail": detail}


def parse_raw_ok(text: str) -> bool:
    return bool(re.search(r"0x[0-9A-Fa-f]+\s*=\s*-?\d+", text)) and "ERR:" not in text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--try-rs485-diag", action="store_true",
                    help="Try DE invert / TX-RX swap if Modbus fails (needs fw≥0.3.5)")
    ap.add_argument("--plant-limit", type=int, default=12,
                    help="Max plant-priority IDs to probe with pget")
    args = ap.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS / f"esp32dev_pdh30_test_{ts}.json"
    RESULTS.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "timestamp": ts,
        "port": args.port,
        "target": "esp32dev + saj.pdh30",
        "results": [],
    }

    def add(r: dict) -> None:
        report["results"].append(r)

    cli = Cli(args.port)
    try:
        cli.cmd("stream off", 1.0)

        # ---- A) Edge identity ----
        t = cli.cmd("help", 1.5)
        add(ok("A help lists profile/pget/raw",
               bool(re.search(r"pget|profile|raw", t, re.I)), t[:120].replace("\n", " | ")))

        t = cli.cmd("wifi status", 2.5)
        is_devkit = "ESP32-DevKit" in t
        add(ok("A board=ESP32-DevKit", is_devkit, t[:160].replace("\n", " | ")))
        if not is_devkit:
            add(ok("A abort: not DevKit firmware on this port", False,
                   "Reflash esp32dev or pick correct USB port"))
            report["summary"] = "WRONG_BOARD"
            out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"\nWrote {out_path}")
            return 2

        t = cli.cmd("profile get", 1.0)
        add(ok("A profile get works", "profile=" in t, t.strip()[:80]))

        # ---- B) Baseline Modbus (status + PDH) ----
        cli.cmd("profile set saj.pdh30", 1.0)
        t = cli.cmd("ping", 6.0)
        link = "Link OK" in t
        add(ok("B ping Link OK", link, t[:180].replace("\n", " | ")))

        t = cli.cmd("raw 0x3000", 3.5)
        add(ok("B raw VFD status 0x3000", parse_raw_ok(t), t[:100].replace("\n", " ")))

        t = cli.cmd("raw 0xF000", 3.5)
        add(ok("B raw F0.00 @0xF000", parse_raw_ok(t), t[:100].replace("\n", " ")))

        t = cli.cmd("pget F0.00", 3.5)
        add(ok("B pget F0.00", "F0.00" in t and "ERR:" not in t, t[:120].replace("\n", " ")))

        # ---- C) RS485 diagnosis if Modbus bad ----
        modbus_ok = any(r["ok"] for r in report["results"] if r["name"].startswith("B "))
        t = cli.cmd("rs485 status", 1.5)
        has_rs485_cli = "rs485 tx=" in t and "ERR:" not in t
        add(ok("C rs485 status (fw≥0.3.5)", has_rs485_cli, t[:140].replace("\n", " ")))

        if args.try_rs485_diag and has_rs485_cli and not modbus_ok:
            # Try DE invert
            cli.cmd("rs485 de invert", 1.0)
            t = cli.cmd("ping", 6.0)
            inv_ok = "Link OK" in t
            add(ok("C ping after DE invert", inv_ok, t[:160].replace("\n", " | ")))
            if inv_ok:
                t = cli.cmd("raw 0xF000", 3.5)
                add(ok("C raw F0.00 after DE invert", parse_raw_ok(t), t[:100]))
            else:
                # restore + try TX/RX swap
                cli.cmd("rs485 de normal", 1.0)
                cli.cmd("rs485 swaptrx", 1.0)
                t = cli.cmd("ping", 6.0)
                swap_ok = "Link OK" in t
                add(ok("C ping after TX/RX swap", swap_ok, t[:160].replace("\n", " | ")))
                if swap_ok:
                    t = cli.cmd("raw 0xF000", 3.5)
                    add(ok("C raw F0.00 after swap", parse_raw_ok(t), t[:100]))
                else:
                    # try invert + swap
                    cli.cmd("rs485 de invert", 1.0)
                    t = cli.cmd("ping", 6.0)
                    add(ok("C ping after swap+DE invert", "Link OK" in t,
                           t[:160].replace("\n", " | ")))

        # ---- D) Plant priority subset (only if link works) ----
        link_now = any(
            r["ok"] and "ping" in r["name"].lower() and "Link" in r["name"]
            for r in report["results"]
        ) or any(r["ok"] and r["name"].startswith("C ping") for r in report["results"])
        # broader: any successful Modbus read
        link_now = link_now or any(
            r["ok"] and ("raw" in r["name"] or "pget" in r["name"] or "ping" in r["name"])
            for r in report["results"]
            if r["name"].startswith(("B ", "C "))
        )

        plant_ids = []
        if PLANT.is_file():
            plant_ids = list(json.loads(PLANT.read_text()).get("ids") or [])
        plant_ids = plant_ids[: max(1, args.plant_limit)]

        if link_now and plant_ids:
            ok_n = fail_n = 0
            fails = []
            for pid in plant_ids:
                t = cli.cmd(f"pget {pid}", 3.0)
                if "ERR:" in t or "Timeout" in t or "CRC" in t:
                    fail_n += 1
                    fails.append(pid)
                else:
                    ok_n += 1
            add(ok(
                f"D plant pget {ok_n}/{ok_n+fail_n}",
                fail_n == 0,
                f"fails={fails[:8]}",
            ))
        else:
            add(ok("D plant pget skipped", False, "no Modbus link"))

    finally:
        cli.close()

    n_ok = sum(1 for r in report["results"] if r["ok"])
    n_fail = len(report["results"]) - n_ok
    report["summary"] = {"pass": n_ok, "fail": n_fail}
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    latest = RESULTS / "esp32dev_pdh30_test_latest.json"
    latest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("\n" + "=" * 64)
    print(f"ESP32-DevKit + PDH-30: {n_ok} PASS / {n_fail} FAIL")
    print(f"Wrote {out_path}")
    print("=" * 64)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
