#!/usr/bin/env python3
"""
Full PDH-30 dump on bank via Edge CLI (profile saj.pdh30).

Usage:
  python3 tools/bank_dump_pdh30.py --port /dev/ttyACM0
  python3 tools/bank_dump_pdh30.py --port COM5 --timeout 240

Requires Edge firmware with:
  profile set | dump (PDH catalog path)

Strips USB prompt prefix '> ' and MQTT/wifi noise.
Writes results/pdh30_full_dump_<ts>.{csv,json,raw.txt} and *_latest.*.
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

ROOT = Path(__file__).resolve().parents[1]
HDR = ROOT / "firmware/saj_pdm30_edge/include/generated/Pdh30ParamTable.h"
OUT_DIR = ROOT / "results"


def load_catalog() -> tuple[list[str], dict[str, dict]]:
    text = HDR.read_text(encoding="utf-8")
    entries = re.findall(
        r'\{"([A-Z0-9.]+)",\s*0x([0-9A-Fa-f]+),\s*(\d+),\s*(\d+)\}', text
    )
    ids = [e[0] for e in entries]
    m = {
        e[0]: {"reg": int(e[1], 16), "scale": int(e[2]), "ro": int(e[3])}
        for e in entries
    }
    return ids, m


def strip_line(line: str) -> str:
    s = line.rstrip("\r\n")
    if s.startswith(">"):
        s = s[1:].lstrip()
    return s


def parse_csv_line(s: str) -> dict | None:
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Bank full dump PDH-30 via Edge CLI")
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--timeout", type=float, default=240.0, help="seconds")
    ap.add_argument("--profile", default="saj.pdh30")
    args = ap.parse_args()

    try:
        import serial
    except ImportError:
        print("pyserial required: pip install pyserial", file=sys.stderr)
        return 1

    catalog_ids, catalog_map = load_catalog()
    print(f"catalog={len(catalog_ids)} port={args.port} profile={args.profile}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"pdh30_full_dump_{ts}"

    ser = serial.Serial(args.port, args.baud, timeout=0.2)
    time.sleep(1.0)
    try:
        ser.reset_input_buffer()
    except Exception:
        pass

    def send(cmd: str) -> None:
        ser.write((cmd + "\n").encode("utf-8"))
        ser.flush()
        print(f"→ {cmd}")

    def drain(sec: float) -> list[str]:
        out: list[str] = []
        t0 = time.time()
        while time.time() - t0 < sec:
            raw = ser.readline()
            if raw:
                s = strip_line(raw.decode("utf-8", errors="replace"))
                if s:
                    out.append(s)
            else:
                time.sleep(0.01)
        return out

    send("stream off")
    drain(0.4)
    send(f"profile set {args.profile}")
    for L in drain(0.8):
        if not L.startswith("["):
            print(f"← {L}")
    send("profile get")
    for L in drain(0.5):
        if not L.startswith("["):
            print(f"← {L}")

    rows: list[dict] = []
    raw_lines: list[str] = []
    started = False
    done = False
    t0 = time.time()
    send("dump")

    while time.time() - t0 < args.timeout:
        raw = ser.readline()
        if not raw:
            time.sleep(0.02)
            continue
        line_raw = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        raw_lines.append(line_raw)
        s = strip_line(line_raw)
        if not s:
            continue
        if s.startswith("[mqtt]") or s.startswith("[wifi]") or s.startswith("[mdns]"):
            continue
        if s.startswith("DUMP begin"):
            started = True
            print(f"← {s}")
            continue
        if s.startswith("CSV:param"):
            print(f"← {s}")
            continue
        if s.startswith("CSV:END") or s == "DUMP done":
            print(f"← {s}")
            done = True
            if s == "DUMP done":
                break
            continue
        if s.startswith("ERR:"):
            print(f"← {s}")
            continue
        parsed = parse_csv_line(s)
        if not parsed:
            continue
        pe = catalog_map.get(parsed["id"], {})
        parsed["scale"] = pe.get("scale")
        parsed["ro"] = pe.get("ro")
        if parsed["reg"] is None:
            parsed["reg"] = pe.get("reg")
        rows.append(parsed)
        if len(rows) % 25 == 0:
            print(f"  … {len(rows)}/{len(catalog_ids)} ({time.time()-t0:.1f}s)")

    # tail
    for L in drain(1.0):
        raw_lines.append(L)
        s = strip_line(L)
        if s == "DUMP done" or s.startswith("CSV:END"):
            done = True
            print(f"← {s}")

    ser.close()
    elapsed = round(time.time() - t0, 2)

    got = {r["id"] for r in rows}
    ok_n = sum(1 for r in rows if r["ok"])
    fails = [r for r in rows if not r["ok"]]
    missing = [i for i in catalog_ids if i not in got]
    summary = {
        "timestamp": ts,
        "port": args.port,
        "profile": args.profile,
        "method": "edge_cli_dump",
        "elapsed_s": elapsed,
        "dump_started": started,
        "dump_done": done,
        "catalog_count": len(catalog_ids),
        "lines_received": len(rows),
        "unique_ids": len(got),
        "ok": ok_n,
        "fail": len(fails),
        "ok_pct": round(100.0 * ok_n / max(1, len(rows)), 2),
        "missing_ids": missing,
        "fail_ids": [r["id"] for r in fails],
        "fails": fails,
    }

    csv_path = OUT_DIR / f"{stem}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["id", "addr", "reg", "eng", "raw", "ok", "scale", "ro"]
        )
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "id": r["id"],
                    "addr": r["addr"],
                    "reg": r["reg"],
                    "eng": "" if r["eng"] is None else r["eng"],
                    "raw": "" if r["raw"] is None else r["raw"],
                    "ok": r["ok"],
                    "scale": r.get("scale") if r.get("scale") is not None else "",
                    "ro": r.get("ro") if r.get("ro") is not None else "",
                }
            )

    payload = {"summary": summary, "rows": rows}
    json_path = OUT_DIR / f"{stem}.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    raw_path = OUT_DIR / f"{stem}_raw.txt"
    raw_path.write_text("\n".join(raw_lines) + "\n", encoding="utf-8")

    # stable aliases
    (OUT_DIR / "pdh30_full_dump_latest.csv").write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    (OUT_DIR / "pdh30_full_dump_latest.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")

    print("\n======== SUMMARY ========")
    print(json.dumps({k: summary[k] for k in summary if k != "fails"}, indent=2))
    if fails:
        print("fails:")
        for r in fails:
            print(f"  {r['id']} {r['addr']}")
    print(f"wrote {csv_path}")
    print(f"wrote {json_path}")
    print(f"wrote {raw_path}")

    if not done or missing:
        print("BANK DUMP INCOMPLETE", file=sys.stderr)
        return 2
    if len(fails) > 15:
        print("BANK DUMP too many fails", file=sys.stderr)
        return 3
    print(f"BANK DUMP OK  {ok_n}/{len(rows)} ({summary['ok_pct']}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
