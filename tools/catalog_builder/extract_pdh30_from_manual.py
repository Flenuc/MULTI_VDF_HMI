#!/usr/bin/env python3
"""
Extract SAJ PDH-30 function-code tables from docs/PDH30_User_Manual.txt
and write drive_profiles/saj/pdh30/profile.json covering groups:

  F0..F9, FD, FE, D0, E0

Modbus addressing (manual Ch.6):
  Fn.mm → 0xF(n)mm  e.g. F3.15 → 0xF30F
  FD.mm → 0xFDmm
  FE.mm → 0xFEmm
  D0.mm → mapped to special monitoring regs 0x1000.. when known
  E0.mm → 0xE0mm (fault history; verify on bench)

Usage (repo root):
  python3 tools/catalog_builder/extract_pdh30_from_manual.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
MANUAL = ROOT / "docs" / "PDH30_User_Manual.txt"
OUT = ROOT / "drive_profiles" / "saj" / "pdh30" / "profile.json"

# Groups requested for mapping
WANTED_GROUPS = {
    "F0", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9",
    "FD", "FE", "D0", "E0",
}

# Line like " F0.00" or "F0.00" at start / after spaces
CODE_RE = re.compile(
    r"(?P<code>(F[0-9]|FD|FE|D0|E0)\.(?P<idx>\d{1,2}))\b",
    re.I,
)

ACCESS_MAP = {
    "○": "rw",
    "●": "rw_stop",  # only when stopped
    "◎": "ro",
}

# D0 monitoring → Ch.6 special registers (validated family table)
D0_TO_REG = {
    0: 0x1001,   # Operating frequency
    1: 0x1000,   # Setting frequency / setpoint (manual unit 0.01 Hz; 0x1000 is % on some units — verify)
    2: 0x1002,   # Bus voltage
    3: 0x1003,   # Output voltage
    4: 0x1004,   # Output current
    5: 0x1005,   # Output power
    6: 0x1006,   # Output torque
    7: 0x1008,   # DI status
    8: 0x1009,   # DO status
    9: 0x100A,   # AI1
    10: 0x100B,  # AI2
    11: 0x100C,  # Cumulative power-on
    12: 0x100D,  # Cumulative running
    13: 0x100E,  # Energy
    14: 0x1007,  # Load speed RPM
    15: 0x100F,  # PID setting pressure
    16: 0x1010,  # PID feedback pressure
}


def group_nibble(g: str) -> int:
    g = g.upper()
    if g.startswith("F") and len(g) == 2 and g[1].isdigit():
        return int(g[1])
    if g == "FD":
        return 0x0D
    if g == "FE":
        return 0x0E
    if g == "D0":
        return 0xD0  # marker
    if g == "E0":
        return 0xE0
    raise ValueError(g)


def modbus_address(group: str, index: int) -> int:
    g = group.upper()
    if g == "D0":
        if index in D0_TO_REG:
            return D0_TO_REG[index]
        return 0x1000 + index
    if g == "E0":
        return 0xE000 | (index & 0xFF)
    # F0-F9, FD, FE: high = 0xF0 | nibble
    n = group_nibble(g)
    if g.startswith("F") and g[1].isdigit():
        return ((0xF0 | n) << 8) | (index & 0xFF)
    if g == "FD":
        return 0xFD00 | (index & 0xFF)
    if g == "FE":
        return 0xFE00 | (index & 0xFF)
    return ((0xF0 | n) << 8) | (index & 0xFF)


def unit_to_scale(unit: str) -> int:
    """Infer integer scale (eng = raw/scale) from unit column text."""
    u = (unit or "").strip().lower().replace(" ", "")
    if not u or u in ("\\", "/", "-", "—", "–"):
        return 1
    # explicit decimals in unit column like 0.01Hz
    if "0.001" in u or u.startswith("0.001"):
        return 1000
    if "0.01" in u:
        return 100
    if "0.1" in u:
        return 10
    # unit names that usually have one decimal on SAJ
    if u in ("bar", "s", "min", "h", "℃", "c", "khz", "ms"):
        # bar/s often 0.1 on SAJ pump drives for setpoints
        if u == "bar":
            return 10
        if u in ("s", "min", "h", "ms"):
            return 10
        if u in ("khz",):
            return 10
        if u in ("c", "℃"):
            return 1
    if u in ("hz",):
        return 100  # 0.01 Hz typical for freq
    if u in ("a",):
        return 100
    if u in ("v",):
        return 1
    if u in ("kw",):
        return 10
    if u in ("%",):
        return 10
    if u in ("rpm", "1rpm"):
        return 1
    if "1h" in u or u == "1h":
        return 1
    if "1kwh" in u:
        return 1
    return 1


def guess_access(blob: str) -> str:
    for sym, acc in ACCESS_MAP.items():
        if sym in blob:
            return acc
    if "◎" in blob or "actual detected" in blob.lower():
        return "ro"
    return "rw"


def clean_ws(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_blocks(text: str) -> List[Dict[str, Any]]:
    """
    Split Chapter 4-ish region into blocks starting at each function code.
    """
    lines = text.splitlines()
    # Focus datasheet chapter
    start = 0
    for i, ln in enumerate(lines):
        if "Chapter 4 Datasheet" in ln or "4.3 Common Parameter" in ln:
            start = i
            break
    end = len(lines)
    for i in range(start, len(lines)):
        if "Chapter 5 Fault" in lines[i]:
            end = i
            break
    region = lines[start:end]

    # Find all code occurrences with line index
    hits: List[Tuple[int, str, int]] = []  # line_idx, group, index
    for i, ln in enumerate(region):
        for m in CODE_RE.finditer(ln):
            code = m.group("code").upper()
            grp = code.split(".")[0]
            if grp not in WANTED_GROUPS:
                continue
            idx = int(m.group("idx"))
            # Prefer codes that appear near left (function code column)
            if m.start() > 40 and not ln.strip().startswith(code[:2]):
                # still accept if line is mostly the code
                if not re.match(r"^\s*" + re.escape(code), ln, re.I):
                    continue
            hits.append((i, grp, idx))

    # Deduplicate keeping first occurrence per code
    seen = set()
    ordered: List[Tuple[int, str, int]] = []
    for h in hits:
        key = (h[1], h[2])
        if key in seen:
            continue
        seen.add(key)
        ordered.append(h)

    params: List[Dict[str, Any]] = []
    for n, (li, grp, idx) in enumerate(ordered):
        next_li = ordered[n + 1][0] if n + 1 < len(ordered) else min(li + 18, len(region))
        # window of lines for this param
        window = region[li:max(next_li, li + 1)]
        blob = "\n".join(window)
        code = f"{grp}.{idx:02d}" if idx < 100 else f"{grp}.{idx}"

        # Name: words after code on first lines
        name_parts: List[str] = []
        for j, wln in enumerate(window[:6]):
            # strip code itself
            tmp = CODE_RE.sub(" ", wln)
            tmp = re.sub(r"[○●◎]", " ", tmp)
            tmp = re.sub(r"\b\d+\.\d+\b", " ", tmp)  # drop ranges like 0.0
            tmp = re.sub(r"0x[0-9A-Fa-f]+", " ", tmp)
            tmp = clean_ws(tmp)
            # skip pure noise
            if not tmp or tmp in ("\\", "/", "-", "–"):
                continue
            # skip header words
            if tmp.lower() in ("function", "description", "set range", "unit", "default", "remarks", "code", "level", "revision"):
                continue
            if len(tmp) < 2:
                continue
            name_parts.append(tmp)
            if j >= 2 and sum(len(x) for x in name_parts) > 12:
                break
        name = clean_ws(" ".join(name_parts[:4]))[:120] or code

        # Unit: look for unit tokens
        unit = ""
        for tok in ("bar", "Bar", "Hz", "kHz", "s", "min", "h", "A", "V", "%", "℃", "RPM", "kW", "ms"):
            if re.search(rf"\b{re.escape(tok)}\b", blob):
                unit = tok if tok != "Bar" else "bar"
                break
        # also unit from D0 table style "0.01 Hz"
        m_u = re.search(r"(0\.\d+\s*(?:Hz|V|A|bar|Bar|kW|%|s))", blob)
        if m_u and not unit:
            unit = m_u.group(1)

        # Default number
        default = None
        m_def = re.search(
            r"\b(\d+\.\d+|\d+)\s*(?:bar|Bar|Hz|s|%|min|h)?\s*[○●◎]",
            blob,
        )
        if m_def:
            try:
                default = float(m_def.group(1))
            except ValueError:
                default = None

        access = guess_access(blob)
        scale = unit_to_scale(unit)
        # Refine scale from explicit "0.01 Hz" etc.
        if re.search(r"0\.01\s*Hz", blob, re.I):
            scale = 100
            unit = unit or "Hz"
        if re.search(r"0\.1\s*V", blob, re.I):
            scale = 10
            unit = unit or "V"
        if re.search(r"0\.01\s*A", blob, re.I):
            scale = 100
            unit = unit or "A"
        if re.search(r"0\.1\s*bar", blob, re.I):
            scale = 10
            unit = unit or "bar"
        if re.search(r"0\.1\s*%", blob, re.I):
            scale = 10
            unit = unit or "%"
        if re.search(r"0\.1\s*kW", blob, re.I):
            scale = 10
            unit = unit or "kW"

        reg = modbus_address(grp, idx)
        params.append(
            {
                "id": code if not code[1].isdigit() else f"{grp}.{idx:02d}",
                "group_code": grp,
                "group": group_nibble(grp) if grp not in ("D0", "E0") else (0xD0 if grp == "D0" else 0xE0),
                "index": idx,
                "register": f"0x{reg:04X}",
                "name": name,
                "unit": unit,
                "scale": scale,
                "default": default,
                "access": access,
                "notes": clean_ws(blob)[:240],
            }
        )

    return params


def normalize_id(p: Dict[str, Any]) -> str:
    g = p["group_code"]
    i = int(p["index"])
    if g.startswith("F") and len(g) == 2 and g[1].isdigit():
        return f"{g}.{i:02d}"
    return f"{g}.{i:02d}"


# Hand-curated names for plant-critical codes (OCR/layout noise cleanup)
NAME_OVERRIDES = {
    "F0.00": "Pre-set pressure",
    "F0.01": "Startup pressure deviation",
    "F0.02": "Motor rotation direction",
    "F0.03": "Antifreeze function",
    "F0.04": "Water leakage coefficient",
    "F0.05": "Start/stop signal option",
    "F0.06": "Auto-starting option",
    "F0.07": "Auto-starting delay time",
    "F0.08": "Sensor range",
    "F0.09": "Sensor feedback channel",
    "F0.10": "High pressure alarm value",
    "F0.11": "Low pressure alarm value",
    "F0.15": "Working mode of VFD",
    "F0.18": "Acceleration time",
    "F0.19": "Deceleration time",
    "F0.20": "Macro function",
    "F2.06": "Lower limit of running frequency",
    "F2.07": "Maximum output frequency",
    "F2.08": "Upper limit of running frequency",
    "F2.10": "Carrier frequency",
    "F3.00": "Proportional gain",
    "F3.01": "Integral time",
    "F3.15": "Sleep detection (see manual)",
    "F8.00": "Communication address",
    "F8.01": "Communication baud rate",
    "FD.00": "Password of the agent (group FD)",
    "FD.01": "Restore factory defaults",
    "FD.02": "Parameter locked",
    "FE.00": "Password (group FE)",
    "FE.01": "Fault record display times",
    "FE.02": "Power-on arrival time setting",
    "FE.03": "Run time arrival setting",
    "D0.00": "Operating frequency",
    "D0.01": "Setting frequency",
    "D0.15": "PID setting",
    "D0.16": "PID feedback",
    "E0.00": "Last fault type",
}

# Force scales for well-known PDH pressure/time defaults (0.1 unit columns)
SCALE_OVERRIDES = {
    "F0.00": 10, "F0.01": 10, "F0.08": 10, "F0.10": 10, "F0.11": 10,
    "F0.12": 10, "F0.13": 10, "F0.18": 10, "F0.19": 10, "F0.07": 10,
    "F2.06": 100, "F2.07": 100, "F2.08": 100, "F2.10": 10,
    "F3.00": 10, "F3.01": 100,
}


def build_profile(params: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Normalize ids + sort
    for p in params:
        p["id"] = normalize_id(p)
        if p["id"] in NAME_OVERRIDES:
            p["name"] = NAME_OVERRIDES[p["id"]]
        if p["id"] in SCALE_OVERRIDES:
            p["scale"] = SCALE_OVERRIDES[p["id"]]
            if p["id"].startswith("F0.") and p.get("unit") in ("", None):
                p["unit"] = "bar" if p["id"] in (
                    "F0.00", "F0.01", "F0.08", "F0.10", "F0.11", "F0.12", "F0.13"
                ) else p.get("unit") or ""
            if p["id"] in ("F0.18", "F0.19", "F0.07"):
                p["unit"] = "s"
        # drop bulky notes in published profile? keep short
        if len(p.get("notes") or "") > 160:
            p["notes"] = p["notes"][:157] + "…"

    # sort by group order wanted
    order = {g: n for n, g in enumerate(sorted(WANTED_GROUPS, key=lambda x: (
        0 if x.startswith("F") and x[1].isdigit() else 1,
        x,
    )))}
    # better explicit order
    gorder = ["F0", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "FD", "FE", "D0", "E0"]
    rank = {g: i for i, g in enumerate(gorder)}
    params.sort(key=lambda p: (rank.get(p["group_code"], 99), p["index"]))

    by_group: Dict[str, int] = {}
    for p in params:
        by_group[p["group_code"]] = by_group.get(p["group_code"], 0) + 1

    return {
        "id": "saj.pdh30",
        "vendor": "SAJ",
        "family": "PDH",
        "model": "PDH-30",
        "version": "0.2.0",
        "status": "catalog_from_manual",
        "source": [
            "docs/PDH30_User_Manual.txt Chapter 4 + Ch.6",
            "tools/catalog_builder/extract_pdh30_from_manual.py",
            "spike: results/spike_map_pdh30_*.json (f_style vs group_direct both responded — prefer f_style per manual)",
        ],
        "protocol": {
            "link": "modbus_rtu",
            "baud": 9600,
            "parity": "N",
            "data_bits": 8,
            "stop_bits": 1,
            "slave_default": 1,
            "fc_read": 3,
            "fc_write": 6,
            "max_contiguous": 12,
            "notes": "Manual: F3.15 read/write address 0xF30F; max contiguous 12.",
        },
        "addressing": {
            "scheme": "f_style",
            "description": "Fn.mm → ((0xF0|n)<<8)|m ; FD/FE → 0xFD/FE << 8 | m ; D0 → 0x100x map ; E0 → 0xE0mm",
            "param_id_format": "{group_code}.{index:02d}",
            "groups_mapped": gorder,
            "counts": by_group,
        },
        "parameters": params,
        "telemetry": [
            {"id": "D0.00", "register": "0x1001", "scale": 100, "unit": "Hz", "name": "Operating frequency"},
            {"id": "D0.02", "register": "0x1002", "scale": 10, "unit": "V", "name": "Bus voltage"},
            {"id": "D0.03", "register": "0x1003", "scale": 1, "unit": "V", "name": "Output voltage"},
            {"id": "D0.04", "register": "0x1004", "scale": 100, "unit": "A", "name": "Output current"},
            {"id": "D0.15", "register": "0x100F", "scale": 10, "unit": "bar", "name": "PID setting"},
            {"id": "D0.16", "register": "0x1010", "scale": 10, "unit": "bar", "name": "PID feedback"},
            {"id": "vfd_status", "register": "0x3000", "scale": 1, "unit": "", "name": "VFD status"},
        ],
        "commands": {
            "start_fwd": {"register": "0x2000", "value": "0x0001"},
            "start_rev": {"register": "0x2000", "value": "0x0002"},
            "stop": {"register": "0x2000", "value": "0x0006"},
            "estop": {"register": "0x2000", "value": "0x0005"},
            "fault_reset": {"register": "0x2000", "value": "0x0007"},
        },
        "cli": {
            "raw": "raw {register}",
            "notes": "Edge firmware still uses PDM r0/w0 map; use raw for PDH until profile runtime lands.",
        },
    }


def main() -> int:
    if not MANUAL.is_file():
        print(f"Missing {MANUAL}", file=sys.stderr)
        return 1
    text = MANUAL.read_text(encoding="utf-8", errors="replace")
    params = extract_blocks(text)
    if not params:
        print("No parameters extracted", file=sys.stderr)
        return 2
    profile = build_profile(params)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = profile["addressing"]["counts"]
    print(f"Wrote {OUT}")
    print("Counts by group:", json.dumps(counts, sort_keys=True))
    print(f"Total parameters: {len(profile['parameters'])}")
    # show samples
    for sample_id in ("F0.00", "F2.07", "F3.15", "F8.00", "F9.00", "FD.01", "FE.00", "D0.00", "E0.00"):
        for p in profile["parameters"]:
            if p["id"] == sample_id:
                print(f"  {p['id']:6} reg={p['register']} scale={p['scale']} unit={p['unit']!r} name={p['name'][:50]!r}")
                break
        else:
            print(f"  {sample_id}: MISSING")
    return 0


if __name__ == "__main__":
    sys.exit(main())
