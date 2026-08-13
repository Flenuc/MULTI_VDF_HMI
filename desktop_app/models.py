"""Domain models — parameter lists / plant recipes (engineering floats).

Multi-VDF:
  - Recipe carries drive_profile_id (default saj.pdm30).
  - Parameters prefer canonical id (P0-00 / F0.00); group/index kept for PDM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


_PARAM_ID_RE = re.compile(
    r"^(?P<head>P[01]|F[0-9A-E]|D0|E0)[.\-](?P<idx>\d{1,3})$",
    re.IGNORECASE,
)


def normalize_param_id(raw: str) -> Optional[str]:
    """Canonical IDs: P0-00 / F0.00 / FD.01 / D0.00 / E0.00."""
    if not raw:
        return None
    s = str(raw).strip().upper().replace(" ", "")
    m = _PARAM_ID_RE.match(s)
    if not m:
        return None
    head = m.group("head").upper()
    idx = int(m.group("idx"))
    if head.startswith("P"):
        if idx > 47:
            return None
        return f"{head}-{idx:02d}"
    if idx > 255:
        return None
    return f"{head}.{idx:02d}"


def parse_param_id(raw: str) -> Optional[Tuple[str, int, int]]:
    """
    Returns (canonical_id, group_num_or_-1, index).
    For PDM P0/P1: group 0/1. For F/D/E style: group=-1 (use id only).
    """
    pid = normalize_param_id(raw)
    if not pid:
        return None
    if pid[0] == "P" and pid[1] in "01" and pid[2] == "-":
        g = int(pid[1])
        i = int(pid[3:])
        return pid, g, i
    # F0.00 / FD.01 / D0.00 …
    try:
        head, idx_s = pid.split(".", 1)
        return pid, -1, int(idx_s)
    except ValueError:
        return None


@dataclass
class Parameter:
    group: int = 0  # 0=P0, 1=P1; unused (-1 stored as 0) for pure ID recipes
    index: int = 0  # 0..47 for PDM; free for PDH when id is set
    value: float = 0.0  # engineering unit (what firmware pset/w0 expect)
    notes: str = ""
    manual_only: bool = False
    id: Optional[str] = None  # preferred multi-VDF key e.g. F0.00 / P0-00
    live_value: Optional[float] = None
    mismatch: bool = False

    def param_id(self) -> str:
        if self.id:
            return self.id
        return f"P{self.group}-{self.index:02d}"

    def address(self) -> int:
        """Best-effort Modbus address (PDM group_direct or PDH f_style)."""
        pid = self.param_id()
        if pid.startswith("P") and len(pid) >= 4 and pid[2] == "-":
            return ((self.group & 0xFF) << 8) | (self.index & 0xFF)
        # F n . mm → 0xFnmm ; FD/FE ; D0 → 0x100x ; E0 → 0xE0mm
        try:
            head, idx_s = pid.split(".", 1)
            idx = int(idx_s)
        except ValueError:
            return 0
        if head == "D0":
            return 0x1000 + idx
        if head == "E0":
            return 0xE000 | idx
        if head.startswith("F") and len(head) == 2:
            nibble = head[1]
            if nibble.isdigit():
                hi = 0xF0 | int(nibble)
            else:
                hi = 0xF0 | (10 + ord(nibble) - ord("A"))  # FD/FE
            return (hi << 8) | idx
        return 0

    def validate(self) -> None:
        pid = self.param_id()
        if not normalize_param_id(pid):
            raise ValueError(f"invalid param id {pid!r}")
        # PDM classic constraints when no explicit multi-VDF id beyond P0/P1
        if pid.startswith("P") and pid[1] in "01":
            if self.group not in (0, 1):
                raise ValueError("group must be 0 or 1")
            if not 0 <= self.index <= 47:
                raise ValueError("index must be 0..47")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.param_id(),
            "value": float(self.value),
            "notes": self.notes,
            "manual_only": bool(self.manual_only),
        }
        # Keep group/index for PDM tooling / backward compatibility
        if self.param_id().startswith("P") and self.param_id()[1] in "01":
            d["group"] = int(self.group)
            d["index"] = int(self.index)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Parameter":
        raw_id = data.get("id") or data.get("param_id")
        group = data.get("group")
        index = data.get("index")
        pid: Optional[str] = None
        g, i = 0, 0

        if raw_id is not None:
            parsed = parse_param_id(str(raw_id))
            if not parsed:
                raise ValueError(f"invalid param id {raw_id!r}")
            pid, g_p, i_p = parsed
            if g_p >= 0:
                g, i = g_p, i_p
            else:
                g, i = 0, i_p
        elif group is not None and index is not None:
            g, i = int(group), int(index)
            pid = f"P{g}-{i:02d}"
        else:
            raise ValueError("parameter needs id or group+index")

        p = cls(
            group=g,
            index=i,
            value=float(data["value"]),
            notes=str(data.get("notes", "")),
            manual_only=bool(data.get("manual_only", False)),
            id=pid,
        )
        p.validate()
        return p


@dataclass
class ParameterList:
    name: str = "Nueva lista"
    description: str = ""
    # Multi-VDF: which drive catalog this recipe targets (default PDM-30)
    drive_profile_id: str = "saj.pdm30"
    parameters: List[Parameter] = field(default_factory=list)

    def add(self, param: Parameter) -> None:
        param.validate()
        key = param.param_id()
        for i, ex in enumerate(self.parameters):
            if ex.param_id() == key:
                param.live_value = ex.live_value
                param.mismatch = ex.mismatch
                self.parameters[i] = param
                return
        self.parameters.append(param)

    def writable(self) -> List[Parameter]:
        return [p for p in self.parameters if not p.manual_only]

    def clear_compare(self) -> None:
        for p in self.parameters:
            p.live_value = None
            p.mismatch = False

    def sort_by_id(self) -> None:
        def sort_key(p: Parameter):
            pid = p.param_id()
            # P0/P1 first numerically; then F/D/E alpha
            if pid.startswith("P") and len(pid) >= 4 and pid[2] == "-":
                return (0, p.group, p.index, pid)
            return (1, pid)

        self.parameters.sort(key=sort_key)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "drive_profile_id": self.drive_profile_id or "saj.pdm30",
            "parameters": [p.to_dict() for p in self.parameters],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParameterList":
        pl = cls(
            name=str(data.get("name", "Lista")),
            description=str(data.get("description", "")),
            drive_profile_id=str(data.get("drive_profile_id") or "saj.pdm30"),
        )
        for item in data.get("parameters", []):
            pl.add(Parameter.from_dict(item))
        return pl


def parse_dump_csv_line(line: str) -> Optional[tuple]:
    """
    Parse firmware dump line:
      CSV:P0-03,0x0003,10,100,bar
      CSV:F0.00,0xF000,2.6,26,
    Returns (param_id, eng_float_or_None) — eng None means ERROR.
    Also returns legacy (group, index, eng) when P-style for callers that still unpack 3-tuple.

    Prefer parse_dump_csv_line_id() for multi-VDF.
    """
    parsed = parse_dump_csv_line_id(line)
    if parsed is None:
        return None
    pid, eng = parsed
    if pid.startswith("P") and "-" in pid:
        try:
            g = int(pid[1])
            i = int(pid.split("-", 1)[1])
            return (g, i, eng)
        except ValueError:
            return (pid, eng)
    return (pid, eng)


def parse_dump_csv_line_id(line: str) -> Optional[Tuple[str, Optional[float]]]:
    """
    Parse dump CSV to (canonical_id, eng|None).
    """
    s = (line or "").strip()
    if s.startswith(">"):
        s = s[1:].lstrip()
    if not s.startswith("CSV:"):
        return None
    if s.startswith("CSV:param") or s.startswith("CSV:END"):
        return None
    body = s[4:]  # strip CSV:
    parts = body.split(",")
    if len(parts) < 3:
        return None
    raw_pid = parts[0].strip()
    pid = normalize_param_id(raw_pid)
    if not pid:
        # accept already-canonical-ish tokens from firmware
        pid = raw_pid.upper()
        if not _PARAM_ID_RE.match(pid.replace(".", "-") if pid.startswith("P") else pid):
            # try as-is if looks like F0.00
            if not re.match(r"^[PFDE][0-9A-E]?[.\-]\d+", pid, re.I):
                return None
    eng_s = parts[2].strip()
    if eng_s == "ERROR":
        return (pid, None)
    try:
        return (pid, float(eng_s))
    except ValueError:
        return (pid, None)
