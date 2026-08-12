#!/usr/bin/env python3
"""
Parse Serial Monitor output from saj_pdm30_discover and build a parameter map.

Usage:
  python3 parse_discovery_log.py capture.txt
  python3 parse_discovery_log.py capture.txt -o param_map.csv

Recognizes lines:
  MAP: P0-00,0xF000,30,Pressure setting
  CSV:P0-00,0xF000,61440,30,"Pressure setting"
  CHANGE: addr=0xF000  old=30  new=40
  REG: 0xF000,30
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

RE_MAP = re.compile(
    r"MAP:\s*P(\d+)-(\d+),(0x[0-9A-Fa-f]+),([^,]+),(.*)$"
)
RE_CSV = re.compile(
    r'CSV:P(\d+)-(\d+),(0x[0-9A-Fa-f]+),(\d+),(-?\d+|ERROR),"(.*)"'
)
RE_CHANGE = re.compile(
    r"CHANGE:\s*addr=(0x[0-9A-Fa-f]+)\s+old=(\d+)\s+new=(\d+)"
)
RE_REG = re.compile(r"REG:\s*(0x[0-9A-Fa-f]+),(\d+)")
RE_SCHEME = re.compile(r"BEST scheme\s*=\s*(\d+)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse PDM-30 discovery serial log")
    ap.add_argument("logfile", type=Path, help="Serial capture text file")
    ap.add_argument("-o", "--output", type=Path, default=Path("param_map.csv"))
    args = ap.parse_args()

    text = args.logfile.read_text(encoding="utf-8", errors="replace")

    rows: dict[tuple[int, int], dict] = {}
    changes = []
    regs = {}
    best_scheme = None

    for line in text.splitlines():
        line = line.strip()
        m = RE_SCHEME.search(line)
        if m:
            best_scheme = int(m.group(1))

        m = RE_MAP.match(line)
        if m:
            g, i = int(m.group(1)), int(m.group(2))
            addr = int(m.group(3), 16)
            raw = m.group(4)
            name = m.group(5).strip()
            rows[(g, i)] = {
                "param": f"P{g}-{i:02d}",
                "group": g,
                "index": i,
                "address_hex": f"0x{addr:04X}",
                "address_dec": addr,
                "raw_value": raw if raw.startswith("ERR") else int(raw),
                "name": name,
            }
            continue

        m = RE_CSV.match(line)
        if m:
            g, i = int(m.group(1)), int(m.group(2))
            addr = int(m.group(3), 16)
            raw_s = m.group(5)
            name = m.group(6)
            rows[(g, i)] = {
                "param": f"P{g}-{i:02d}",
                "group": g,
                "index": i,
                "address_hex": f"0x{addr:04X}",
                "address_dec": addr,
                "raw_value": raw_s if raw_s == "ERROR" else int(raw_s),
                "name": name,
            }
            continue

        m = RE_CHANGE.match(line)
        if m:
            changes.append(
                {
                    "address_hex": m.group(1),
                    "old": int(m.group(2)),
                    "new": int(m.group(3)),
                }
            )
            continue

        m = RE_REG.match(line)
        if m:
            regs[int(m.group(1), 16)] = int(m.group(2))

    if best_scheme is not None:
        print(f"Best scheme from log: {best_scheme}")
        print("  0=GROUP_DIRECT  1=F_STYLE  2=GROUP_100")

    if changes:
        print(f"\nWatch-mode changes ({len(changes)}):")
        for c in changes:
            print(f"  {c['address_hex']}: {c['old']} → {c['new']}")

    if not rows and regs:
        print(f"\nBrute REG hits: {len(regs)}")
        for a in sorted(regs):
            print(f"  0x{a:04X} = {regs[a]}")

    if rows:
        fieldnames = [
            "param",
            "group",
            "index",
            "address_hex",
            "address_dec",
            "raw_value",
            "name",
        ]
        with args.output.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for key in sorted(rows):
                w.writerow(rows[key])
        print(f"\nWrote {len(rows)} parameters → {args.output}")

        # summary of OK vs ERROR
        ok = sum(1 for r in rows.values() if r["raw_value"] != "ERROR" and not str(r["raw_value"]).startswith("ERR"))
        print(f"Readable: {ok}/{len(rows)}")
    else:
        print("No MAP/CSV lines found. Capture Serial output after 'dump' or 'csv'.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
