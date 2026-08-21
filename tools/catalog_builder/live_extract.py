"""Merge Edge dump rows into a live-draft drive profile + results JSON."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _slug(profile_id: str) -> str:
    return profile_id.strip().replace(".", "_")


def build_summary(
    profile_id: str,
    via: str,
    dump: dict,
    catalog_ids: List[str],
    transport_meta: Optional[dict] = None,
) -> dict:
    rows: List[dict] = dump.get("rows") or []
    got = {r["id"] for r in rows}
    ok_n = sum(1 for r in rows if r.get("ok"))
    fails = [r for r in rows if not r.get("ok")]
    missing = [i for i in catalog_ids if i not in got]
    raw = dump.get("raw_lines") or []
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "profile_id": profile_id,
        "via": via,
        "transport": transport_meta or {},
        "method": "edge_cli_dump",
        "elapsed_s": dump.get("elapsed_s"),
        "dump_started": dump.get("started"),
        "dump_done": dump.get("done"),
        "catalog_count": len(catalog_ids),
        "lines_received": len(rows),
        "unique_ids": len(got),
        "ok": ok_n,
        "fail": len(fails),
        "ok_pct": round(100.0 * ok_n / max(1, len(rows)), 2),
        "missing_ids": missing,
        "fail_ids": [r["id"] for r in fails],
        "raw_preview": raw[:40],
        "rows": rows,
    }


def merge_draft(base_profile: dict, summary: dict) -> dict:
    """Copy profile and stamp live_raw / live_eng / map_status from dump."""
    draft = copy.deepcopy(base_profile)
    by_id = {r["id"]: r for r in summary.get("rows") or []}
    for p in draft.get("parameters") or []:
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        row = by_id.get(pid)
        if not row:
            p["map_status"] = "missing"
            p.pop("live_raw", None)
            p.pop("live_eng", None)
            continue
        if row.get("ok"):
            p["map_status"] = "ok"
            p["live_raw"] = row.get("raw")
            p["live_eng"] = row.get("eng")
        else:
            p["map_status"] = "error"
            p["live_raw"] = None
            p["live_eng"] = None
    draft["status"] = "live_draft"
    sources = list(draft.get("source") or [])
    sources.append(
        f"live extract {summary.get('timestamp')} via={summary.get('via')} "
        f"ok_pct={summary.get('ok_pct')}"
    )
    draft["source"] = sources
    draft["live_extract"] = {
        "timestamp": summary.get("timestamp"),
        "via": summary.get("via"),
        "ok": summary.get("ok"),
        "fail": summary.get("fail"),
        "ok_pct": summary.get("ok_pct"),
        "missing": len(summary.get("missing_ids") or []),
    }
    return draft


def write_results(
    summary: dict,
    out_dir: Path,
    stem: Optional[str] = None,
) -> Dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pid = _slug(str(summary.get("profile_id") or "profile"))
    ts = summary.get("timestamp") or "now"
    base = stem or f"live_extract_{pid}_{ts}"
    json_path = out_dir / f"{base}.json"
    latest = out_dir / f"live_extract_{pid}_latest.json"
    payload = {k: v for k, v in summary.items()}
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    json_path.write_text(text + "\n", encoding="utf-8")
    latest.write_text(text + "\n", encoding="utf-8")
    return {"json": json_path, "latest": latest}


def write_draft(draft: dict, profile_json_path: Path) -> Path:
    dest = profile_json_path.with_name("profile.live_draft.json")
    dest.write_text(
        json.dumps(draft, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return dest


def load_mqtt_profile_file(
    path: Path, name: Optional[str] = None
) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    profiles = data.get("mqtt_profiles") or []
    if not profiles:
        raise RuntimeError(f"no mqtt_profiles in {path}")
    if name:
        for p in profiles:
            if p.get("name") == name:
                return p
        raise RuntimeError(f"mqtt profile {name!r} not found in {path}")
    last = data.get("last_mqtt") or ""
    if last:
        for p in profiles:
            if p.get("name") == last:
                return p
    return profiles[0]
