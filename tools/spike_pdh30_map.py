#!/usr/bin/env python3
"""
Spike PDH-30 / PDM-30 Modbus address map via Edge CLI over USB serial.

The Edge must run field firmware with:
  - RS485 wired to the VFD under test
  - CLI commands: raw <addr>, r0/r1, slave <id>, ping

For each addressing scheme, reads fingerprint registers and reports hits.

Usage:
  # PDH-30 on slave 1 (default), Edge on ACM0
  python3 tools/spike_pdh30_map.py --port /dev/ttyACM0 --label pdh30

  # Compare against known-good PDM-30
  python3 tools/spike_pdh30_map.py --port /dev/ttyACM0 --label pdm30

  # Also try CLI r0/r1 (PDM map only)
  python3 tools/spike_pdh30_map.py --port /dev/ttyACM0 --also-cli

Output:
  results/spike_map_<label>_<timestamp>.json
  results/spike_map_<label>_<timestamp>.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

try:
    import serial
except ImportError:
    print("pip install pyserial", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Address schemes (same as include/saj_pdm30_protocol.h)
# ---------------------------------------------------------------------------

def addr_group_direct(g: int, i: int) -> int:
    return (g << 8) | i


def addr_f_style(g: int, i: int) -> int:
    """PDH30 manual: F3.15 → 0xF30F  (high = 0xF0|group, low = index)."""
    return ((0xF0 | g) << 8) | i


def addr_group_100(g: int, i: int) -> int:
    return g * 100 + i


SCHEMES = {
    "group_direct": addr_group_direct,  # proven PDM-30
    "f_style": addr_f_style,            # documented PDH-30
    "group_100": addr_group_100,
}

# Fingerprint candidates: (group, index, label, notes)
# Prefer params that usually have non-zero / distinctive values.
FINGERPRINTS: List[Tuple[int, int, str, str]] = [
    (0, 0, "set_pressure / F0.00?", "pressure setpoint often non-zero"),
    (0, 3, "sensor_range", "often 10.0 bar raw~100"),
    (0, 8, "pid_fn", "often 1"),
    (0, 36, "accel", "accel time"),
    (0, 43, "freq_source", "often 8 on pump macros"),
    (1, 5, "fmax", "max freq raw 5000/6000"),
    (1, 6, "f_upper", "upper freq"),
    (1, 9, "carrier", "carrier"),
    (1, 35, "slave_id", "local address usually 1"),
    (1, 36, "baud_code", "1 = 9600 on SAJ family"),
    (1, 37, "data_format", "0 = 8N1"),
]

# Special status regs (family PDH Ch.6) — scheme-independent
SPECIAL_REGS = [
    (0x1001, "run_freq"),
    (0x1002, "bus_or_out"),
    (0x1003, "out_or_bus"),
    (0x1004, "out_current"),
    (0x3000, "vfd_status"),
    (0x2000, "ctrl_cmd_ro_probe"),
]


def read_until_prompt(ser: serial.Serial, timeout: float = 8.0) -> str:
    ser.timeout = 0.15
    buf = ""
    t0 = time.time()
    while time.time() - t0 < timeout:
        chunk = ser.read(512)
        if chunk:
            buf += chunk.decode("utf-8", errors="replace")
            if buf.rstrip().endswith(">") or "\n> " in buf or buf.endswith("> "):
                time.sleep(0.05)
                extra = ser.read(2048)
                if extra:
                    buf += extra.decode("utf-8", errors="replace")
                return buf
    return buf


def send_cmd(ser: serial.Serial, cmd: str, timeout: float = 8.0) -> str:
    ser.reset_input_buffer()
    ser.write((cmd.strip() + "\n").encode("utf-8"))
    ser.flush()
    return read_until_prompt(ser, timeout=timeout)


def parse_raw_reply(text: str) -> Optional[int]:
    """
    Parse Edge raw-read replies. Accept common forms:
      RAW 0x0105 = 6000
      raw@0x0105=6000
      OK raw=6000
      value=6000
    """
    patterns = [
        r"(?:raw|RAW|value|eng)?\s*[=:@]?\s*(?:0x[0-9A-Fa-f]+\s*[=:]\s*)?(-?\d+)",
        r"=\s*(-?\d+)\s*(?:raw)?",
        r"raw\s*=\s*(-?\d+)",
        r"@0x[0-9A-Fa-f]+\s*=\s*(-?\d+)",
    ]
    # Prefer line with hex address
    for line in text.splitlines():
        if "ERR" in line.upper():
            continue
        m = re.search(
            r"0x[0-9A-Fa-f]{1,4}\s*[:=]\s*(-?\d+)",
            line,
            re.I,
        )
        if m:
            return int(m.group(1))
        m = re.search(r"raw\s*=\s*(-?\d+)", line, re.I)
        if m:
            return int(m.group(1))
    for line in text.splitlines():
        if "ERR" in line.upper() or line.strip() in (">", ""):
            continue
        m = re.search(r"(-?\d{1,5})\s*$", line.strip())
        if m and "P" not in line[:3]:
            v = int(m.group(1))
            if 0 <= v <= 65535:
                return v
    return None


def parse_cli_param_reply(text: str) -> Optional[Tuple[float, int]]:
    """Parse 'P0-00 @0x0000 = 2.6 bar  (raw=26)' """
    m = re.search(
        r"P(\d)-(\d+)\s*@0x([0-9A-Fa-f]+)\s*=\s*([-\d.]+).*raw\s*=\s*(\d+)",
        text,
        re.I | re.S,
    )
    if m:
        return float(m.group(4)), int(m.group(5))
    m = re.search(r"raw\s*=\s*(\d+)", text, re.I)
    if m:
        return None, int(m.group(1))
    return None


def score_scheme(rows: List[dict]) -> dict:
    """Heuristic: non-null reads + distinctive values raise score."""
    ok = [r for r in rows if r.get("raw") is not None]
    errs = [r for r in rows if r.get("raw") is None]
    distinctive = 0
    for r in ok:
        raw = r["raw"]
        if raw in (0, 65535, 0xFFFF):
            continue
        distinctive += 1
        # SAJ-ish hints
        if r.get("index") == 35 and raw in (1, 2, 3, 4, 5):
            distinctive += 2
        if r.get("index") == 36 and raw in (0, 1, 2, 3, 4):
            distinctive += 1
        if r.get("index") == 5 and 1000 <= raw <= 12000:
            distinctive += 2
    return {
        "reads_ok": len(ok),
        "reads_fail": len(errs),
        "distinctive": distinctive,
        "score": len(ok) * 2 + distinctive,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Spike PDH/PDM Modbus map via Edge raw CLI")
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--slave", type=int, default=1, help="Modbus slave id on VFD")
    ap.add_argument("--label", default="spike", help="pdh30 | pdm30 | other tag")
    ap.add_argument("--also-cli", action="store_true", help="Also try r0/r1 (PDM map)")
    ap.add_argument("--schemes", default="group_direct,f_style,group_100")
    ap.add_argument("--pause", type=float, default=0.12, help="delay between raw reads")
    args = ap.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_json = RESULTS / f"spike_map_{args.label}_{ts}.json"
    out_csv = RESULTS / f"spike_map_{args.label}_{ts}.csv"

    print(f"Opening Edge {args.port} @ {args.baud} …")
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.2)
    except serial.SerialException as e:
        print(f"Cannot open port: {e}", file=sys.stderr)
        print("Tip: close VarioField / serial monitor first.", file=sys.stderr)
        return 1

    time.sleep(0.3)
    # Wake CLI
    banner = send_cmd(ser, "ping", timeout=5)
    print("--- ping ---")
    print(banner.strip()[:400])
    if "ERR" in banner and "Link" not in banner and "OK" not in banner:
        print("WARN: ping weak; continue with raw reads")

    slave_out = send_cmd(ser, f"slave {args.slave}", timeout=4)
    print(slave_out.strip()[:200])

    schemes = [s.strip() for s in args.schemes.split(",") if s.strip() in SCHEMES]
    report: Dict = {
        "label": args.label,
        "timestamp": ts,
        "port": args.port,
        "slave": args.slave,
        "schemes": {},
        "special_regs": [],
        "cli_pdm_map": [],
        "recommendation": "",
    }

    # Special regs (independent of param scheme)
    print("\n=== Special registers (PDH Ch.6 style) ===")
    for reg, name in SPECIAL_REGS:
        text = send_cmd(ser, f"raw 0x{reg:04X}", timeout=5)
        raw = parse_raw_reply(text)
        row = {"register": f"0x{reg:04X}", "name": name, "raw": raw, "reply": text.strip()[:180]}
        report["special_regs"].append(row)
        print(f"  0x{reg:04X} {name:16} raw={raw}  | {text.strip()[:80]!r}")
        time.sleep(args.pause)

    # Scheme probes
    for scheme in schemes:
        fn = SCHEMES[scheme]
        print(f"\n=== Scheme: {scheme} ===")
        rows = []
        for g, i, label, notes in FINGERPRINTS:
            addr = fn(g, i)
            text = send_cmd(ser, f"raw 0x{addr:04X}", timeout=5)
            raw = parse_raw_reply(text)
            row = {
                "scheme": scheme,
                "group": g,
                "index": i,
                "id": f"G{g}-{i:02d}",
                "label": label,
                "notes": notes,
                "register": f"0x{addr:04X}",
                "raw": raw,
                "reply": text.strip()[:200],
            }
            rows.append(row)
            mark = "OK" if raw is not None else "FAIL"
            print(f"  [{mark}] {label:14} G{g}-{i:02d} @0x{addr:04X} → {raw}")
            time.sleep(args.pause)
        sc = score_scheme(rows)
        report["schemes"][scheme] = {"score": sc, "rows": rows}
        print(f"  → score={sc['score']} ok={sc['reads_ok']} fail={sc['reads_fail']} distinctive={sc['distinctive']}")

    # Optional CLI r0/r1 (always group_direct in current firmware)
    if args.also_cli:
        print("\n=== CLI r0/r1 (firmware PDM map) ===")
        for g, i, label, _ in FINGERPRINTS[:6]:
            cmd = f"r{g} {i}"
            text = send_cmd(ser, cmd, timeout=6)
            parsed = parse_cli_param_reply(text)
            eng, raw = (parsed if parsed else (None, None))
            report["cli_pdm_map"].append(
                {
                    "cmd": cmd,
                    "label": label,
                    "eng": eng,
                    "raw": raw,
                    "reply": text.strip()[:200],
                }
            )
            print(f"  {cmd:8} eng={eng} raw={raw} | {text.strip()[:70]!r}")
            time.sleep(args.pause)

    # Recommendation
    ranked = sorted(
        ((name, data["score"]["score"]) for name, data in report["schemes"].items()),
        key=lambda x: -x[1],
    )
    if ranked:
        best, best_score = ranked[0]
        report["recommendation"] = (
            f"Best scheme by heuristic: {best} (score={best_score}). "
            f"For label={args.label}: "
            + (
                "expect group_direct if this is PDM-30; "
                "expect f_style if this is PDH-30 (manual F3.15→0xF30F). "
                if args.label.lower().startswith("pdh")
                else "expect group_direct on PDM-30. "
            )
            + "Confirm by matching slave id (G1-35) and fmax (G1-05) to HMI display."
        )
        print("\n***", report["recommendation"])

    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    # CSV flat
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "scheme",
                "id",
                "label",
                "group",
                "index",
                "register",
                "raw",
            ],
        )
        w.writeheader()
        for scheme, data in report["schemes"].items():
            for row in data["rows"]:
                w.writerow({k: row.get(k) for k in w.fieldnames})

    print(f"\nWrote {out_json}")
    print(f"Wrote {out_csv}")
    ser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
