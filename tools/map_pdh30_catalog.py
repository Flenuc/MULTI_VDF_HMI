#!/usr/bin/env python3
"""
Map / compare PDH-30 catalog via Guition (or any Edge) USB CLI.

Reads every register in drive_profiles/saj/pdh30/profile.json using:
  slave <id>
  raw 0x....

Writes:
  results/pdh30_catalog_map_<ts>.json
  results/pdh30_catalog_map_<ts>.csv

Usage:
  python3 tools/map_pdh30_catalog.py --port /dev/ttyACM0
  python3 tools/map_pdh30_catalog.py --port /dev/ttyACM0 --groups F0,F2,D0
  python3 tools/map_pdh30_catalog.py --port /dev/ttyACM0 --plant-only
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
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "drive_profiles" / "saj" / "pdh30" / "profile.json"
PLANT = ROOT / "drive_profiles" / "saj" / "pdh30" / "plant_priority_ids.json"
RESULTS = ROOT / "results"

try:
    import serial
except ImportError:
    print("pip install pyserial", file=sys.stderr)
    sys.exit(1)


def open_ser(port: str, baud: int) -> serial.Serial:
    ser = serial.Serial(port, baud, timeout=0.15)
    time.sleep(0.35)
    # drain boot noise
    ser.reset_input_buffer()
    return ser


def read_until_prompt(ser: serial.Serial, timeout: float = 6.0) -> str:
    buf = ""
    t0 = time.time()
    while time.time() - t0 < timeout:
        chunk = ser.read(512)
        if chunk:
            buf += chunk.decode("utf-8", errors="replace")
            if buf.rstrip().endswith(">") or "\n> " in buf or buf.endswith("> "):
                time.sleep(0.04)
                extra = ser.read(2048)
                if extra:
                    buf += extra.decode("utf-8", errors="replace")
                return buf
    return buf


def send_cmd(ser: serial.Serial, cmd: str, timeout: float = 6.0) -> str:
    ser.reset_input_buffer()
    ser.write((cmd.strip() + "\n").encode("utf-8"))
    ser.flush()
    return read_until_prompt(ser, timeout=timeout)


def parse_raw(text: str) -> Optional[int]:
    """Parse '0xF000 = 26 (0x001A)' or ERR."""
    if re.search(r"\bERR:", text, re.I):
        # still try extract if mixed
        pass
    m = re.search(r"0x[0-9A-Fa-f]{1,4}\s*=\s*(-?\d+)", text)
    if m:
        return int(m.group(1))
    if re.search(r"\bERR:", text, re.I):
        return None
    m = re.search(r"raw\s*=\s*(-?\d+)", text, re.I)
    if m:
        return int(m.group(1))
    return None


def eng_from_raw(raw: Optional[int], scale: int) -> Optional[float]:
    if raw is None:
        return None
    s = scale if scale and scale > 0 else 1
    # signed-ish for scale 1
    if s <= 1:
        v = raw if raw < 32768 else raw - 65536
        return float(v)
    # treat as signed int16 then divide
    if raw >= 32768:
        raw_s = raw - 65536
    else:
        raw_s = raw
    return float(raw_s) / float(s)


def main() -> int:
    ap = argparse.ArgumentParser(description="Map PDH-30 catalog via Edge raw CLI (Guition)")
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--slave", type=int, default=1)
    ap.add_argument("--groups", default="", help="Comma list e.g. F0,F2,D0 (empty=all)")
    ap.add_argument("--plant-only", action="store_true", help="Only plant_priority_ids.json")
    ap.add_argument("--pause", type=float, default=0.08)
    ap.add_argument("--retries", type=int, default=2)
    args = ap.parse_args()

    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    params: List[Dict[str, Any]] = list(profile.get("parameters") or [])

    if args.plant_only and PLANT.is_file():
        ids = set(json.loads(PLANT.read_text(encoding="utf-8")).get("ids") or [])
        params = [p for p in params if p.get("id") in ids]
    elif args.groups.strip():
        want = {g.strip().upper() for g in args.groups.split(",") if g.strip()}
        params = [p for p in params if p.get("group_code", "").upper() in want]

    if not params:
        print("No parameters selected", file=sys.stderr)
        return 2

    RESULTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_json = RESULTS / f"pdh30_catalog_map_{ts}.json"
    out_csv = RESULTS / f"pdh30_catalog_map_{ts}.csv"

    print(f"Guition/Edge {args.port} — mapping {len(params)} params, slave={args.slave}")
    try:
        ser = open_ser(args.port, args.baud)
    except Exception as e:
        print(f"Cannot open {args.port}: {e}", file=sys.stderr)
        return 1

    # wake
    for _ in range(2):
        send_cmd(ser, "", timeout=1.5)
    ping = send_cmd(ser, "ping", timeout=5)
    print("ping:", ping.replace("\r", "").strip()[:200])
    print(send_cmd(ser, f"slave {args.slave}", timeout=4).replace("\r", "").strip()[:120])

    rows: List[Dict[str, Any]] = []
    ok = fail = 0
    by_group: Dict[str, Dict[str, int]] = {}

    for i, p in enumerate(params):
        reg = str(p.get("register") or "")
        pid = p.get("id")
        gcode = p.get("group_code", "")
        scale = int(p.get("scale") or 1)
        raw = None
        reply = ""
        for attempt in range(args.retries + 1):
            reply = send_cmd(ser, f"raw {reg}", timeout=5)
            raw = parse_raw(reply)
            if raw is not None:
                break
            time.sleep(0.15)
        eng = eng_from_raw(raw, scale)
        status = "ok" if raw is not None else "fail"
        if status == "ok":
            ok += 1
        else:
            fail += 1
        gstat = by_group.setdefault(gcode, {"ok": 0, "fail": 0})
        gstat["ok" if status == "ok" else "fail"] += 1

        row = {
            "id": pid,
            "group_code": gcode,
            "index": p.get("index"),
            "register": reg,
            "name": p.get("name"),
            "unit": p.get("unit"),
            "scale": scale,
            "access": p.get("access"),
            "raw": raw,
            "eng": eng,
            "status": status,
            "reply": reply.replace("\r", "").strip()[:160],
        }
        rows.append(row)
        mark = "OK" if status == "ok" else "!!"
        eng_s = f"{eng:.4g}" if eng is not None else "-"
        print(f"[{mark}] {pid:7} {reg} raw={raw!s:>6} eng={eng_s:>8} {p.get('unit') or ''}  {str(p.get('name') or '')[:40]}")
        time.sleep(args.pause)
        if (i + 1) % 25 == 0:
            print(f"  … {i+1}/{len(params)}  ok={ok} fail={fail}")

    # summary special telemetry from profile
    tel_rows = []
    for t in profile.get("telemetry") or []:
        reg = t.get("register")
        reply = send_cmd(ser, f"raw {reg}", timeout=5)
        raw = parse_raw(reply)
        tel_rows.append(
            {
                "id": t.get("id"),
                "register": reg,
                "raw": raw,
                "eng": eng_from_raw(raw, int(t.get("scale") or 1)),
                "name": t.get("name"),
            }
        )
        print(f"[TEL] {t.get('id')} {reg} raw={raw}")

    report = {
        "timestamp": ts,
        "port": args.port,
        "slave": args.slave,
        "profile_id": profile.get("id"),
        "profile_version": profile.get("version"),
        "total": len(params),
        "ok": ok,
        "fail": fail,
        "ok_pct": round(100.0 * ok / max(len(params), 1), 1),
        "by_group": by_group,
        "parameters": rows,
        "telemetry": tel_rows,
        "note": (
            "eng = raw/scale per profile. "
            "Fails may be illegal address, drive busy, or RS485 noise — re-run plant-only."
        ),
    }

    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "id", "group_code", "index", "register", "name", "unit",
                "scale", "access", "raw", "eng", "status",
            ],
        )
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in w.fieldnames})

    print("\n=== SUMMARY ===")
    print(f"ok={ok} fail={fail} ({report['ok_pct']}%)")
    for g, st in sorted(by_group.items()):
        print(f"  {g}: ok={st['ok']} fail={st['fail']}")
    print(f"Wrote {out_json}")
    print(f"Wrote {out_csv}")
    ser.close()
    return 0 if fail < len(params) else 3


if __name__ == "__main__":
    sys.exit(main())
