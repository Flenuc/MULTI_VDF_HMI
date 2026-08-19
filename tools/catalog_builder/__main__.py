#!/usr/bin/env python3
"""
MULTI_VDF Catalog Builder — MVP CLI (M2)

Usage (from repo root):
  python3 -m tools.catalog_builder list
  python3 -m tools.catalog_builder validate saj.pdh30
  python3 -m tools.catalog_builder extract-manual saj.pdh30
  python3 -m tools.catalog_builder extract-manual saj.pdm30
  python3 -m tools.catalog_builder diff saj.pdm30 saj.pdh30
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / "drive_profiles"
HERE = Path(__file__).resolve().parent

REQUIRED_TOP = ("id", "vendor", "model", "protocol", "addressing", "parameters")
REQUIRED_PROTO = ("link", "baud", "slave_default", "fc_read", "fc_write")
REQUIRED_PARAM = ("id", "register")


def profile_path(profile_id: str) -> Path:
  # saj.pdh30 → drive_profiles/saj/pdh30/profile.json
  parts = profile_id.strip().split(".")
  if len(parts) < 2:
    raise SystemExit(f"bad profile id: {profile_id} (want vendor.model)")
  vendor, model = parts[0], parts[1]
  return PROFILES / vendor / model / "profile.json"


def load_profile(profile_id: str) -> dict[str, Any]:
  path = profile_path(profile_id)
  if not path.is_file():
    raise SystemExit(f"missing profile: {path}")
  return json.loads(path.read_text(encoding="utf-8"))


def cmd_list(_: argparse.Namespace) -> int:
  rows = []
  if not PROFILES.is_dir():
    print("no drive_profiles/", file=sys.stderr)
    return 1
  for path in sorted(PROFILES.glob("*/*/profile.json")):
    try:
      data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
      rows.append((str(path), f"ERR {e}"))
      continue
    pid = data.get("id") or path.parent.name
    n = len(data.get("parameters") or [])
    status = data.get("status") or "?"
    rows.append((pid, f"n={n} status={status} path={path.relative_to(ROOT)}"))
  for pid, info in rows:
    print(f"{pid:24} {info}")
  print(f"\n{len(rows)} profile(s)")
  return 0


def cmd_validate(args: argparse.Namespace) -> int:
  data = load_profile(args.profile_id)
  errs: list[str] = []
  for k in REQUIRED_TOP:
    if k not in data:
      errs.append(f"missing top-level key: {k}")
  proto = data.get("protocol") or {}
  for k in REQUIRED_PROTO:
    if k not in proto:
      errs.append(f"protocol missing: {k}")
  params = data.get("parameters")
  if not isinstance(params, list) or not params:
    errs.append("parameters must be a non-empty list")
  else:
    ids = set()
    for i, p in enumerate(params):
      if not isinstance(p, dict):
        errs.append(f"parameters[{i}] not an object")
        continue
      for k in REQUIRED_PARAM:
        if k not in p:
          errs.append(f"parameters[{i}] missing {k}")
      pid = p.get("id")
      if pid in ids:
        errs.append(f"duplicate param id: {pid}")
      ids.add(pid)
      reg = str(p.get("register") or "")
      if reg and not (reg.startswith("0x") or reg.startswith("0X")):
        # allow int-like
        try:
          int(str(reg), 0)
        except Exception:
          errs.append(f"param {pid}: bad register {reg!r}")

  if data.get("id") and data["id"] != args.profile_id:
    errs.append(f"id mismatch: file={data['id']!r} arg={args.profile_id!r}")

  if errs:
    print(f"FAIL {args.profile_id}: {len(errs)} issue(s)")
    for e in errs[:40]:
      print(f"  - {e}")
    if len(errs) > 40:
      print(f"  … +{len(errs) - 40} more")
    return 1
  n = len(params or [])
  print(f"OK {args.profile_id}: {n} parameters, protocol={proto.get('link')}")
  return 0


def cmd_extract_manual(args: argparse.Namespace) -> int:
  pid = args.profile_id
  if pid in ("saj.pdh30", "pdh30"):
    script = HERE / "extract_pdh30_from_manual.py"
  elif pid in ("saj.pdm30", "pdm30"):
    script = HERE / "generate_saj_pdm30_profile.py"
  else:
    print(
      f"extract-manual: no extractor wired for {pid!r} yet.\n"
      "  Available: saj.pdh30, saj.pdm30\n"
      "  Next: PD-20 / 8200B extractors (M3).",
      file=sys.stderr,
    )
    return 2
  print(f"+ {script.relative_to(ROOT)}")
  return subprocess.call([sys.executable, str(script)], cwd=str(ROOT))


def cmd_diff(args: argparse.Namespace) -> int:
  a = load_profile(args.profile_a)
  b = load_profile(args.profile_b)
  ids_a = {p.get("id") for p in (a.get("parameters") or []) if isinstance(p, dict)}
  ids_b = {p.get("id") for p in (b.get("parameters") or []) if isinstance(p, dict)}
  only_a = sorted(ids_a - ids_b)
  only_b = sorted(ids_b - ids_a)
  both = sorted(ids_a & ids_b)
  print(f"{args.profile_a}: {len(ids_a)} ids")
  print(f"{args.profile_b}: {len(ids_b)} ids")
  print(f"shared: {len(both)}")
  print(f"only {args.profile_a}: {len(only_a)}")
  for x in only_a[:20]:
    print(f"  - {x}")
  if len(only_a) > 20:
    print(f"  … +{len(only_a) - 20}")
  print(f"only {args.profile_b}: {len(only_b)}")
  for x in only_b[:20]:
    print(f"  + {x}")
  if len(only_b) > 20:
    print(f"  … +{len(only_b) - 20}")
  return 0


def main() -> int:
  ap = argparse.ArgumentParser(prog="catalog_builder", description="M2 Catalog Builder MVP")
  sub = ap.add_subparsers(dest="cmd", required=True)

  p = sub.add_parser("list", help="List drive_profiles/*/profile.json")
  p.set_defaults(func=cmd_list)

  p = sub.add_parser("validate", help="Validate profile schema (lightweight)")
  p.add_argument("profile_id", help="e.g. saj.pdh30")
  p.set_defaults(func=cmd_validate)

  p = sub.add_parser("extract-manual", help="Run vendor extractor into drive_profiles/")
  p.add_argument("profile_id", help="saj.pdh30 | saj.pdm30")
  p.set_defaults(func=cmd_extract_manual)

  p = sub.add_parser("diff", help="Compare parameter id sets of two profiles")
  p.add_argument("profile_a")
  p.add_argument("profile_b")
  p.set_defaults(func=cmd_diff)

  args = ap.parse_args()
  return int(args.func(args))


if __name__ == "__main__":
  raise SystemExit(main())
