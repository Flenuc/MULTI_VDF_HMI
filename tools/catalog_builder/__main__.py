#!/usr/bin/env python3
"""
MULTI_VDF Catalog Builder — M2 CLI

Usage (from repo root):
  python3 -m tools.catalog_builder list
  python3 -m tools.catalog_builder validate saj.pdh30
  python3 -m tools.catalog_builder extract-manual saj.pdh30
  python3 -m tools.catalog_builder extract-manual saj.pdm30
  python3 -m tools.catalog_builder diff saj.pdm30 saj.pdh30
  python3 -m tools.catalog_builder extract-live saj.pdh30 --via mqtt --mqtt-profile "Local Mosquitto"
  python3 -m tools.catalog_builder extract-live saj.pdh30 --via serial --port /dev/ttyACM0
  python3 -m tools.catalog_builder merge saj.pdh30
  python3 -m tools.catalog_builder merge saj.pdh30 --live results/live_extract_saj_pdh30_latest.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / "drive_profiles"
HERE = Path(__file__).resolve().parent
OUT_DIR = ROOT / "results"
DEFAULT_MQTT_STORE = ROOT / "desktop_app" / "config" / "connection_profiles.json"

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


def cmd_extract_live(args: argparse.Namespace) -> int:
  from tools.catalog_builder.edge_cli import MqttTransport, SerialTransport, run_dump
  from tools.catalog_builder.live_extract import (
    build_summary,
    load_mqtt_profile_file,
    merge_draft,
    write_draft,
    write_results,
  )

  profile_id = args.profile_id
  base = load_profile(profile_id)
  params = base.get("parameters") or []
  if not params:
    print(f"FAIL {profile_id}: empty parameters — run extract-manual first", file=sys.stderr)
    return 1
  catalog_ids = [str(p.get("id")) for p in params if isinstance(p, dict) and p.get("id")]

  via = args.via
  tr = None
  transport_meta: dict[str, Any] = {"via": via}

  try:
    if via == "serial":
      port = args.port or "/dev/ttyACM0"
      transport_meta.update({"port": port, "baud": args.baud})
      print(f"extract-live {profile_id} via=serial port={port}")
      tr = SerialTransport(port, args.baud)
    elif via == "mqtt":
      host = args.host
      port = args.mqtt_port
      prefix = args.prefix
      user = args.username
      password = args.password or os.environ.get("VARIOFIELD_MQTT_PASS", "")

      if args.mqtt_profile or (not prefix and DEFAULT_MQTT_STORE.is_file()):
        store = Path(args.mqtt_store) if args.mqtt_store else DEFAULT_MQTT_STORE
        if not store.is_file():
          print(f"FAIL: mqtt profile store missing: {store}", file=sys.stderr)
          return 1
        mp = load_mqtt_profile_file(store, args.mqtt_profile)
        host = host or mp.get("host") or "127.0.0.1"
        port = port or int(mp.get("port") or 1883)
        user = user if user is not None and user != "" else (mp.get("username") or "")
        if not password:
          password = mp.get("password") or ""
        if not prefix:
          prefix = mp.get("topic_prefix") or ""

      host = host or "127.0.0.1"
      port = int(port or 1883)
      prefix = (prefix or "").strip().rstrip("/")
      if not prefix or "XXXXXX" in prefix:
        print(
          "FAIL: MQTT topic_prefix required (e.g. saj/pdm30/vf-e23fc4).\n"
          "  Use --prefix or --mqtt-profile with a real vf-… prefix.",
          file=sys.stderr,
        )
        return 1
      if not (user or "").strip():
        print(
          "FAIL: MQTT username required (broker auth). "
          "Pass --username or --mqtt-profile / VARIOFIELD_MQTT_PASS.",
          file=sys.stderr,
        )
        return 1

      transport_meta.update(
        {
          "host": host,
          "port": port,
          "prefix": prefix,
          "username": user,
        }
      )
      print(f"extract-live {profile_id} via=mqtt {host}:{port} prefix={prefix}")
      tr = MqttTransport(
        host=host,
        port=port,
        prefix=prefix,
        username=user,
        password=password,
      )
    else:
      print(f"FAIL: unknown --via {via!r}", file=sys.stderr)
      return 2

    def on_progress(n: int, elapsed: float) -> None:
      print(f"  … {n}/{len(catalog_ids)} ({elapsed:.1f}s)")

    dump = run_dump(
      tr,
      profile_id=profile_id,
      timeout=float(args.timeout),
      on_progress=on_progress,
    )
  except Exception as e:
    print(f"FAIL extract-live: {e}", file=sys.stderr)
    return 1
  finally:
    if tr is not None:
      try:
        tr.close()
      except Exception:
        pass

  # Enrich rows with catalog register when missing
  cat_reg = {}
  for p in params:
    if isinstance(p, dict) and p.get("id"):
      try:
        cat_reg[p["id"]] = int(str(p.get("register")), 0)
      except Exception:
        pass
  for r in dump.get("rows") or []:
    if r.get("reg") is None and r.get("id") in cat_reg:
      r["reg"] = cat_reg[r["id"]]
      r["addr"] = r.get("addr") or f"0x{cat_reg[r['id']]:04X}"

  summary = build_summary(
    profile_id=profile_id,
    via=via,
    dump=dump,
    catalog_ids=catalog_ids,
    transport_meta=transport_meta,
  )
  paths = write_results(summary, OUT_DIR, stem=args.out_stem)
  print(
    json.dumps(
      {
        k: summary[k]
        for k in summary
        if k not in ("rows",)
      },
      indent=2,
    )
  )
  print(f"wrote {paths['json'].relative_to(ROOT)}")
  print(f"wrote {paths['latest'].relative_to(ROOT)}")

  if args.write_draft:
    draft = merge_draft(base, summary)
    dest = write_draft(draft, profile_path(profile_id))
    print(f"wrote draft {dest.relative_to(ROOT)}")

  if not summary.get("dump_done") and summary.get("lines_received", 0) == 0:
    return 2
  return 0


def cmd_merge(args: argparse.Namespace) -> int:
  from tools.catalog_builder.merge_profiles import merge_profiles, write_merged

  profile_id = args.profile_id
  base_path = profile_path(profile_id)
  base = load_profile(profile_id)

  if args.live:
    live_path = Path(args.live)
    if not live_path.is_file():
      # allow relative to repo root
      alt = ROOT / args.live
      live_path = alt if alt.is_file() else live_path
  else:
    live_path = base_path.with_name("profile.live_draft.json")

  if not live_path.is_file():
    print(
      f"FAIL: live source missing: {live_path}\n"
      "  Run extract-live --write-draft first, or pass --live PATH",
      file=sys.stderr,
    )
    return 1

  live = json.loads(live_path.read_text(encoding="utf-8"))
  merged, report = merge_profiles(
    base,
    live,
    prefer_live_register=bool(args.prefer_live_register),
  )
  paths = write_merged(merged, report, base_path, OUT_DIR)

  print(
    json.dumps(
      {
        "profile_id": profile_id,
        "live": str(live_path),
        "ok_pct": report.get("ok_pct"),
        "counts": report.get("counts"),
        "register_conflicts": len(report.get("register_conflicts") or []),
        "only_base": len(report.get("only_base") or []),
        "only_live": len(report.get("only_live") or []),
      },
      indent=2,
    )
  )
  print(f"wrote {paths['merged'].relative_to(ROOT)}")
  if "report" in paths:
    print(f"wrote {paths['report'].relative_to(ROOT)}")

  conflicts = report.get("register_conflicts") or []
  if conflicts:
    print(f"register conflicts ({len(conflicts)}):")
    for c in conflicts[:15]:
      print(f"  {c['id']}: base={c['base']} live={c['live']}")
    if len(conflicts) > 15:
      print(f"  … +{len(conflicts) - 15}")

  if args.apply:
    bak = base_path.with_suffix(base_path.suffix + ".bak")
    bak.write_text(base_path.read_text(encoding="utf-8"), encoding="utf-8")
    base_path.write_text(
      json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"applied → {base_path.relative_to(ROOT)} (backup {bak.name})")

  return 0


def main() -> int:
  ap = argparse.ArgumentParser(
    prog="catalog_builder", description="M2 Catalog Builder (manual + live)"
  )
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

  p = sub.add_parser(
    "extract-live",
    help="Dump live params via Edge CLI (MQTT or serial) → results/ + optional draft",
  )
  p.add_argument("profile_id", help="e.g. saj.pdh30")
  p.add_argument("--via", choices=("mqtt", "serial"), required=True)
  p.add_argument("--timeout", type=float, default=240.0)
  p.add_argument("--write-draft", action="store_true", help="Write profile.live_draft.json")
  p.add_argument("--out-stem", default=None, help="Optional results filename stem")
  # serial
  p.add_argument("--port", default="/dev/ttyACM0")
  p.add_argument("--baud", type=int, default=115200)
  # mqtt
  p.add_argument("--host", default=None)
  p.add_argument("--mqtt-port", type=int, default=None)
  p.add_argument("--prefix", default=None, help="saj/pdm30/vf-XXXXXX")
  p.add_argument("--username", default=None)
  p.add_argument("--password", default=None)
  p.add_argument(
    "--mqtt-profile",
    default=None,
    help="Name in desktop_app/config/connection_profiles.json",
  )
  p.add_argument(
    "--mqtt-store",
    default=None,
    help="Path to connection_profiles.json (default: desktop_app/config/...)",
  )
  p.set_defaults(func=cmd_extract_live)

  p = sub.add_parser(
    "merge",
    help="Merge manual profile.json + live draft/results → profile.merged.json",
  )
  p.add_argument("profile_id", help="e.g. saj.pdh30")
  p.add_argument(
    "--live",
    default=None,
    help="Live source: profile.live_draft.json or results/live_extract_*.json "
    "(default: drive_profiles/.../profile.live_draft.json)",
  )
  p.add_argument(
    "--prefer-live-register",
    action="store_true",
    help="On register conflict, keep live address (default: keep manual)",
  )
  p.add_argument(
    "--apply",
    action="store_true",
    help="Also overwrite profile.json (writes .bak first). Default: only merged file.",
  )
  p.set_defaults(func=cmd_merge)

  args = ap.parse_args()
  return int(args.func(args))


if __name__ == "__main__":
  raise SystemExit(main())
