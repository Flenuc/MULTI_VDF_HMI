"""Domain models — parameter lists for Edge Configurator (engineering floats)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Parameter:
    group: int  # 0=P0, 1=P1
    index: int  # 0..47
    value: float  # engineering unit (what firmware r0/w0 expect)
    notes: str = ""
    manual_only: bool = False
    live_value: Optional[float] = None
    mismatch: bool = False

    def param_id(self) -> str:
        return f"P{self.group}-{self.index:02d}"

    def validate(self) -> None:
        if self.group not in (0, 1):
            raise ValueError("group must be 0 or 1")
        if not 0 <= self.index <= 47:
            raise ValueError("index must be 0..47")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group": self.group,
            "index": self.index,
            "value": float(self.value),
            "notes": self.notes,
            "manual_only": bool(self.manual_only),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Parameter":
        if "param_id" in data and "group" not in data:
            pid = str(data["param_id"]).upper().replace(".", "-").replace(" ", "")
            if pid.startswith("P") and "-" in pid:
                g_s, i_s = pid[1:].split("-", 1)
                data = {**data, "group": int(g_s), "index": int(i_s)}
        p = cls(
            group=int(data["group"]),
            index=int(data["index"]),
            value=float(data["value"]),
            notes=str(data.get("notes", "")),
            manual_only=bool(data.get("manual_only", False)),
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
        for i, ex in enumerate(self.parameters):
            if ex.group == param.group and ex.index == param.index:
                # keep live compare flags if same slot
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
        self.parameters.sort(key=lambda p: (p.group, p.index))

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
    Returns (group, index, eng_float) or None.
    """
    if not line.startswith("CSV:P"):
        return None
    if line.startswith("CSV:param") or line.startswith("CSV:END"):
        return None
    body = line[4:]  # strip CSV:
    parts = body.split(",")
    if len(parts) < 3:
        return None
    pid = parts[0].strip().upper()  # P0-03
    if not pid.startswith("P") or "-" not in pid:
        return None
    g_s, i_s = pid[1:].split("-", 1)
    try:
        g, i = int(g_s), int(i_s)
        eng_s = parts[2].strip()
        if eng_s == "ERROR":
            return (g, i, None)
        eng = float(eng_s)
        return (g, i, eng)
    except ValueError:
        return None
