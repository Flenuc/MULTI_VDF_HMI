"""Drive profile loader (multi-VDF)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent


def profiles_root() -> Path:
    return ROOT


def list_profile_ids() -> List[str]:
    ids: List[str] = []
    for p in ROOT.glob("*/*/profile.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            pid = data.get("id") or f"{p.parent.parent.name}.{p.parent.name}"
            ids.append(str(pid))
        except Exception:
            continue
    return sorted(ids)


def load_profile(profile_id: str) -> Dict[str, Any]:
    """
    Load by id like 'saj.pdm30' or path fragment 'saj/pdm30'.
    """
    pid = profile_id.strip()
    candidates = []
    if "/" in pid:
        candidates.append(ROOT / pid / "profile.json")
    if "." in pid:
        vendor, model = pid.split(".", 1)
        candidates.append(ROOT / vendor / model.replace(".", "_") / "profile.json")
        # saj.pdm30 → saj/pdm30
        candidates.append(ROOT / vendor / model / "profile.json")
    candidates.append(ROOT / pid / "profile.json")

    for c in candidates:
        if c.is_file():
            return json.loads(c.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"drive profile not found: {profile_id}")


def default_profile_id() -> str:
    return "saj.pdm30"


def address_for(profile: Dict[str, Any], group: int, index: int) -> int:
    scheme = (profile.get("addressing") or {}).get("scheme", "group_direct")
    if scheme == "f_style":
        return ((0xF0 | group) << 8) | index
    if scheme == "group_100":
        return group * 100 + index
    return (group << 8) | index


def param_by_id(profile: Dict[str, Any], param_id: str) -> Optional[Dict[str, Any]]:
    for p in profile.get("parameters") or []:
        if p.get("id") == param_id:
            return p
    return None
