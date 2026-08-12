#!/usr/bin/env python3
"""
PC-side helper: open the ESP32 USB serial port, run discovery commands,
and save a parameter map CSV.

Requires: pyserial  (pip install pyserial)

Usage:
  python3 discover_via_serial.py --port /dev/ttyACM0
  python3 discover_via_serial.py --port /dev/ttyACM0 --cmd schemes
  python3 discover_via_serial.py --port /dev/ttyACM0 --cmd csv -o map.csv

Flash saj_pdm30_discover.ino to the ESP32 first.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    import serial
except ImportError:
    print("Install pyserial:  pip install pyserial", file=sys.stderr)
    sys.exit(1)


def read_until_prompt(ser: serial.Serial, timeout: float = 30.0) -> str:
    """Read until we see a bare '> ' prompt or timeout."""
    ser.timeout = 0.2
    buf = ""
    t0 = time.time()
    while time.time() - t0 < timeout:
        chunk = ser.read(256)
        if chunk:
            buf += chunk.decode("utf-8", errors="replace")
            if buf.rstrip().endswith(">") or "\n> " in buf or buf.endswith("> "):
                # wait a bit more for trailing data
                time.sleep(0.15)
                extra = ser.read(4096)
                if extra:
                    buf += extra.decode("utf-8", errors="replace")
                return buf
        else:
            # if we already have substantial output and idle, return
            if len(buf) > 20 and (time.time() - t0) > 2:
                # still waiting for prompt
                pass
    return buf


def send_cmd(ser: serial.Serial, cmd: str, timeout: float = 120.0) -> str:
    ser.reset_input_buffer()
    ser.write((cmd + "\n").encode("utf-8"))
    ser.flush()
    return read_until_prompt(ser, timeout=timeout)


def main() -> int:
    ap = argparse.ArgumentParser(description="Drive PDM-30 discovery over USB serial")
    ap.add_argument("--port", default="/dev/ttyACM0", help="ESP32 serial port")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument(
        "--cmd",
        default="schemes",
        choices=["ping", "schemes", "dump", "csv", "fullscan", "watch"],
        help="Discovery command to run",
    )
    ap.add_argument("-o", "--output", type=Path, default=Path("discovery_capture.txt"))
    ap.add_argument("--map-csv", type=Path, default=Path("param_map.csv"))
    args = ap.parse_args()

    print(f"Opening {args.port} @ {args.baud}...")
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.2)
    except serial.SerialException as e:
        print(f"Cannot open port: {e}", file=sys.stderr)
        return 1

    time.sleep(2.0)  # ESP32 reset on open (if DTR connected)
    ser.reset_input_buffer()
    # wake prompt
    ser.write(b"\n")
    banner = read_until_prompt(ser, timeout=5.0)
    print(banner)

    timeouts = {
        "ping": 10,
        "schemes": 90,
        "dump": 180,
        "csv": 180,
        "fullscan": 600,
        "watch": 60,
    }
    print(f"\n>>> {args.cmd}")
    out = send_cmd(ser, args.cmd, timeout=timeouts.get(args.cmd, 120))
    print(out)

    args.output.write_text(banner + "\n" + out, encoding="utf-8")
    print(f"Saved capture → {args.output}")

    # auto-parse if csv/dump
    if args.cmd in ("csv", "dump", "schemes"):
        parse = Path(__file__).with_name("parse_discovery_log.py")
        if parse.exists():
            import subprocess

            subprocess.run(
                [sys.executable, str(parse), str(args.output), "-o", str(args.map_csv)],
                check=False,
            )

    ser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
