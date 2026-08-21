"""Formal merge: manual/base profile + live draft → profile.merged.json."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _param_index(params: List[dict]) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for p in params:
        if isinstance(p, dict) and p.get("id"):
            out[str(p["id"])] = p
    return out


def _norm_reg(v: Any) -> Optional[str]:
    if v is None or v == "":
        return None
    try:
        n = int(str(v), 0)
        return f"0x{n:04X}"
    except Exception:
        s = str(v).strip()
        return s.upper() if s else None


def merge_profiles(
    base: dict,
    live: dict,
    *,
    prefer_live_register: bool = False,
) -> Tuple[dict, dict]:
    """
    Merge live onto base.

    - Manual/base wins: name, unit, scale, default, access, notes, group*, addressing
    - Live wins: live_raw, live_eng, map_status
    - register: base wins unless prefer_live_register or base missing
    Returns (merged_profile, report).
    """
    base_params = [p for p in (base.get("parameters") or []) if isinstance(p, dict)]
    live_params = [p for p in (live.get("parameters") or []) if isinstance(p, dict)]
    # Also accept results JSON shape: {rows:[{id,reg,eng,raw,ok}]}
    if not live_params and isinstance(live.get("rows"), list):
        live_params = []
        for r in live["rows"]:
            if not isinstance(r, dict) or not r.get("id"):
                continue
            live_params.append(
                {
                    "id": r["id"],
                    "register": r.get("addr")
                    or (f"0x{r['reg']:04X}" if isinstance(r.get("reg"), int) else None),
                    "live_raw": r.get("raw"),
                    "live_eng": r.get("eng"),
                    "map_status": "ok"
                    if r.get("ok")
                    else ("error" if r.get("ok") is False else "missing"),
                }
            )

    idx_base = _param_index(base_params)
    idx_live = _param_index(live_params)

    only_base = sorted(set(idx_base) - set(idx_live))
    only_live = sorted(set(idx_live) - set(idx_base))
    shared = sorted(set(idx_base) & set(idx_live))

    register_conflicts: List[dict] = []
    scale_notes: List[dict] = []
    updated_live = 0

    merged = copy.deepcopy(base)
    new_params: List[dict] = []

    # Preserve base order; append only_live at end
    ordered_ids = [str(p["id"]) for p in base_params if p.get("id")]
    for pid in only_live:
        ordered_ids.append(pid)

    for pid in ordered_ids:
        b = copy.deepcopy(idx_base.get(pid) or {})
        L = idx_live.get(pid)

        if not L:
            # in manual base but not seen in this live dump
            b["map_status"] = "missing"
            new_params.append(b)
            continue

        if not b:
            # only in live — provisional entry
            entry = copy.deepcopy(L)
            entry.setdefault("name", pid)
            entry.setdefault(
                "notes", "added from live extract (not in manual base)"
            )
            entry["map_status"] = L.get("map_status") or "ok"
            new_params.append(entry)
            continue

        # shared: manual metadata + live confirmation
        reg_b = _norm_reg(b.get("register"))
        reg_l = _norm_reg(L.get("register"))
        if reg_b and reg_l and reg_b != reg_l:
            register_conflicts.append({"id": pid, "base": reg_b, "live": reg_l})
            if prefer_live_register:
                b["register"] = reg_l
                b["notes"] = (
                    (b.get("notes") or "")
                    + f" | merge: register from live {reg_l} (was {reg_b})"
                ).strip(" |")

        updated_live += 1
        if "live_raw" in L:
            b["live_raw"] = L.get("live_raw")
        if "live_eng" in L:
            b["live_eng"] = L.get("live_eng")
        b["map_status"] = L.get("map_status") or (
            "ok" if L.get("live_eng") is not None else "missing"
        )

        if L.get("scale") is not None and b.get("scale") is not None:
            try:
                if float(L["scale"]) != float(b["scale"]):
                    scale_notes.append(
                        {"id": pid, "base": b["scale"], "live": L["scale"]}
                    )
            except Exception:
                pass

        new_params.append(b)

    status_counts = {"ok": 0, "error": 0, "missing": 0, "other": 0}
    for p in new_params:
        st = p.get("map_status") or "other"
        if st in status_counts:
            status_counts[st] += 1
        else:
            status_counts["other"] += 1

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    merged["parameters"] = new_params
    merged["status"] = "merged"
    sources = list(merged.get("source") or [])
    live_src = live.get("live_extract") or live.get("timestamp") or "live"
    sources.append(f"merge {ts} live={live_src}")
    merged["source"] = sources
    merged["merge"] = {
        "timestamp": ts,
        "base_id": base.get("id"),
        "live_status": live.get("status") or live.get("via"),
        "prefer_live_register": prefer_live_register,
        "counts": {
            "base": len(idx_base),
            "live": len(idx_live),
            "merged": len(new_params),
            "only_base": len(only_base),
            "only_live": len(only_live),
            "shared": len(shared),
            "register_conflicts": len(register_conflicts),
            "updated_live_fields": updated_live,
            **{f"map_{k}": v for k, v in status_counts.items()},
        },
    }

    report = {
        "timestamp": ts,
        "only_base": only_base,
        "only_live": only_live,
        "register_conflicts": register_conflicts,
        "scale_notes": scale_notes,
        "counts": merged["merge"]["counts"],
        "ok_pct": round(
            100.0
            * status_counts.get("ok", 0)
            / max(1, len(new_params)),
            2,
        ),
    }
    return merged, report


def write_merged(
    merged: dict,
    report: dict,
    profile_json_path: Path,
    results_dir: Optional[Path] = None,
) -> Dict[str, Path]:
    dest = profile_json_path.with_name("profile.merged.json")
    dest.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    out: Dict[str, Path] = {"merged": dest}
    if results_dir is not None:
        results_dir.mkdir(parents=True, exist_ok=True)
        pid = str(merged.get("id") or "profile").replace(".", "_")
        rep = results_dir / f"merge_report_{pid}_{report['timestamp']}.json"
        latest = results_dir / f"merge_report_{pid}_latest.json"
        text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        rep.write_text(text, encoding="utf-8")
        latest.write_text(text, encoding="utf-8")
        out["report"] = rep
        out["report_latest"] = latest
    return out
