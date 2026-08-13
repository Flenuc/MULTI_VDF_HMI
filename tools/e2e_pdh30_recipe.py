#!/usr/bin/env python3
"""
End-to-end plant recipe flow on bank (same as app: load → compare → send).

  python3 tools/e2e_pdh30_recipe.py --port /dev/ttyACM0
  python3 tools/e2e_pdh30_recipe.py --port /dev/ttyACM0 --sync-only-matching

Steps:
  1. Load desktop_app/param_lists/ejemplo_pdh30.json
  2. profile set saj.pdh30 + dump
  3. Compare recipe IDs vs dump map
  4. pset writable params (wait for OK write / retry busy)
  5. Optional readback of a few keys
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
RECIPE_DEFAULT = ROOT / "desktop_app/param_lists/ejemplo_pdh30.json"
OUT_DIR = ROOT / "results"


def strip_line(line: str) -> str:
    s = line.rstrip("\r\n")
    if s.startswith(">"):
        s = s[1:].lstrip()
    return s


def load_recipe(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("drive_profile_id"):
        data["drive_profile_id"] = "saj.pdm30"
    params = []
    for item in data.get("parameters") or []:
        pid = item.get("id") or item.get("param_id")
        if not pid and "group" in item and "index" in item:
            pid = f"P{int(item['group'])}-{int(item['index']):02d}"
        if not pid:
            continue
        params.append(
            {
                "id": str(pid).strip().upper(),
                "value": float(item["value"]),
                "manual_only": bool(item.get("manual_only", False)),
                "notes": str(item.get("notes") or ""),
            }
        )
    data["parameters"] = params
    return data


class EdgeCli:
    def __init__(self, port: str, baud: int = 115200):
        import serial

        self.ser = serial.Serial(port, baud, timeout=0.15)
        time.sleep(1.0)
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass
        self.log: list[str] = []

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass

    def _read_until(self, pred, timeout: float, also_collect_csv: bool = False) -> tuple[str | None, list[str]]:
        t0 = time.time()
        csv_lines: list[str] = []
        while time.time() - t0 < timeout:
            raw = self.ser.readline()
            if not raw:
                time.sleep(0.01)
                continue
            s = strip_line(raw.decode("utf-8", errors="replace"))
            if not s:
                continue
            self.log.append(s)
            if s.startswith("[mqtt]") or s.startswith("[wifi]") or s.startswith("[mdns]"):
                continue
            if also_collect_csv and s.startswith("CSV:"):
                csv_lines.append(s)
            if pred(s):
                return s, csv_lines
        return None, csv_lines

    def send(self, cmd: str) -> None:
        self.ser.write((cmd + "\n").encode("utf-8"))
        self.ser.flush()
        print(f"→ {cmd}")

    def send_await(self, cmd: str, timeout: float = 12.0) -> str:
        """Send and wait for final Modbus/control reply (skip OK queued)."""

        def is_final(s: str) -> bool:
            if s.startswith("OK queued"):
                return False
            if s.startswith("OK write") or s.startswith("OK op") or s.startswith("OK profile="):
                return True
            if s.startswith("OK wraw"):
                return True
            if s.startswith("ERR: busy"):
                return True
            if s.startswith("ERR:"):
                return True
            if s.startswith("stream ON") or s.startswith("stream OFF"):
                return True
            if re.match(r"^[A-Z0-9.]+\s+@0x", s, re.I):
                return True
            if s.startswith("0x") and "=" in s:
                return True
            return False

        for attempt in range(4):
            self.send(cmd)
            line, _ = self._read_until(is_final, timeout)
            if line is None:
                if attempt >= 3:
                    raise TimeoutError(f"timeout: {cmd}")
                time.sleep(0.2)
                continue
            if line.startswith("ERR: busy") or (
                line.startswith("ERR:") and re.search(r"crc|timeout|frame|busy", line, re.I)
            ):
                time.sleep(0.3 + attempt * 0.2)
                continue
            if line.startswith("ERR:"):
                raise RuntimeError(line)
            print(f"← {line}")
            return line
        raise RuntimeError(f"failed: {cmd}")

    def dump(self, timeout: float = 180.0) -> dict[str, float]:
        self.send("dump")
        dump_map: dict[str, float] = {}
        t0 = time.time()
        while time.time() - t0 < timeout:
            raw = self.ser.readline()
            if not raw:
                time.sleep(0.01)
                continue
            s = strip_line(raw.decode("utf-8", errors="replace"))
            if not s:
                continue
            self.log.append(s)
            if s.startswith("[mqtt]") or s.startswith("[wifi]") or s.startswith("[mdns]"):
                continue
            if s.startswith("DUMP begin"):
                print(f"← {s}")
                continue
            if s.startswith("CSV:param"):
                continue
            if s.startswith("CSV:END") or s == "DUMP done":
                print(f"← {s}")
                if s == "DUMP done":
                    break
                continue
            if s.startswith("CSV:"):
                parts = s[4:].split(",")
                if len(parts) < 3:
                    continue
                pid = parts[0].strip()
                eng_s = parts[2].strip()
                if eng_s == "ERROR":
                    continue
                try:
                    dump_map[pid] = float(eng_s)
                except ValueError:
                    pass
                if len(dump_map) % 25 == 0:
                    print(f"  … dump {len(dump_map)} ({time.time()-t0:.1f}s)")
        return dump_map


def compare(recipe_params: list[dict], dump_map: dict[str, float], tol: float = 1e-3):
    """Compare writable recipe targets only (manual_only monitors are observed, not scored)."""
    mismatches = []
    matches = []
    missing = []
    for p in recipe_params:
        if p.get("manual_only"):
            continue
        pid = p["id"]
        if pid not in dump_map:
            missing.append(pid)
            mismatches.append({"id": pid, "recipe": p["value"], "live": None, "reason": "missing"})
            continue
        live = dump_map[pid]
        thr = max(tol, abs(p["value"]) * 1e-4)
        if abs(live - p["value"]) > thr:
            mismatches.append(
                {
                    "id": pid,
                    "recipe": p["value"],
                    "live": live,
                    "reason": "diff",
                }
            )
        else:
            matches.append(pid)
    return matches, mismatches, missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--recipe", type=Path, default=RECIPE_DEFAULT)
    ap.add_argument(
        "--sync-only-matching",
        action="store_true",
        help="Only pset params that already match (noop write smoke)",
    )
    ap.add_argument(
        "--skip-sync",
        action="store_true",
        help="Compare only",
    )
    ap.add_argument("--max-sync", type=int, default=0, help="Limit writes (0=all writable)")
    args = ap.parse_args()

    recipe = load_recipe(args.recipe)
    prof = recipe.get("drive_profile_id") or "saj.pdh30"
    params = recipe["parameters"]
    writable = [p for p in params if not p["manual_only"]]
    print(f"recipe={args.recipe.name} profile={prof} params={len(params)} writable={len(writable)}")

    edge = EdgeCli(args.port)
    summary: dict = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "port": args.port,
        "recipe": str(args.recipe),
        "profile": prof,
        "param_count": len(params),
        "writable_count": len(writable),
    }
    try:
        # --- load profile ---
        edge.send_await(f"profile set {prof}", 3.0)
        edge.send("stream off")
        edge._read_until(lambda s: s.startswith("stream"), 2.0)

        # --- compare (dump) ---
        t0 = time.time()
        dump_map = edge.dump(180.0)
        summary["dump_elapsed_s"] = round(time.time() - t0, 2)
        summary["dump_ids"] = len(dump_map)
        matches, mismatches, missing = compare(params, dump_map)
        summary["compare_matches"] = len(matches)
        summary["compare_mismatches"] = len(mismatches)
        summary["compare_missing"] = len(missing)
        summary["mismatch_sample"] = mismatches[:20]
        print(
            f"COMPARE: match={len(matches)} mismatch={len(mismatches)} "
            f"missing={len(missing)} dump_ids={len(dump_map)}"
        )
        for m in mismatches[:12]:
            print(f"  DIFF {m['id']}: recipe={m['recipe']} live={m['live']} ({m['reason']})")

        # --- sync ---
        if args.skip_sync:
            summary["sync"] = "skipped"
        else:
            to_write = list(writable)
            if args.sync_only_matching:
                match_set = set(matches)
                to_write = [p for p in writable if p["id"] in match_set]
            if args.max_sync and args.max_sync > 0:
                to_write = to_write[: args.max_sync]

            ok_n = fail_n = 0
            fails = []
            t1 = time.time()
            for i, p in enumerate(to_write):
                cmd = f"pset {p['id']} {p['value']}"
                try:
                    edge.send_await(cmd, 12.0)
                    ok_n += 1
                except Exception as e:
                    fail_n += 1
                    fails.append({"id": p["id"], "error": str(e)})
                    print(f"  FAIL {p['id']}: {e}")
                if (i + 1) % 10 == 0:
                    print(f"  … sync {i+1}/{len(to_write)}")
            summary["sync_elapsed_s"] = round(time.time() - t1, 2)
            summary["sync_ok"] = ok_n
            summary["sync_fail"] = fail_n
            summary["sync_fails"] = fails
            print(f"SYNC: ok={ok_n} fail={fail_n} in {summary['sync_elapsed_s']}s")

            # readback sample
            samples = [p for p in to_write if p["id"] in ("F0.00", "F0.01", "F0.07")]
            if not samples:
                samples = to_write[:3]
            rb = []
            for p in samples:
                try:
                    line = edge.send_await(f"pget {p['id']}", 8.0)
                    rb.append({"id": p["id"], "line": line, "recipe": p["value"]})
                except Exception as e:
                    rb.append({"id": p["id"], "error": str(e)})
            summary["readback"] = rb
            print("READBACK:")
            for r in rb:
                print(f"  {r}")

        summary["ok"] = (
            summary.get("compare_missing", 0) == 0
            and summary.get("sync_fail", 0) == 0
            and not args.skip_sync
        ) or (args.skip_sync and summary.get("compare_missing", 0) == 0)

    finally:
        edge.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"e2e_pdh30_recipe_{summary['timestamp']}.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUT_DIR / "e2e_pdh30_recipe_latest.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"wrote {out}")

    # exit: allow a few mismatches (recipe may drift from live) but require dump coverage
    if summary.get("dump_ids", 0) < 50:
        print("E2E FAIL: dump too small", file=sys.stderr)
        return 2
    if not args.skip_sync and summary.get("sync_fail", 0) > 5:
        print("E2E FAIL: too many sync errors", file=sys.stderr)
        return 3
    print("E2E OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
