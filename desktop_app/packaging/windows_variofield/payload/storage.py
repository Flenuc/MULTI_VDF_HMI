"""JSON persistence for parameter lists."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from models import ParameterList

PathLike = Union[str, Path]


def save_json(plist: ParameterList, path: PathLike) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(plist.to_dict(), f, indent=2, ensure_ascii=False)


def load_json(path: PathLike) -> ParameterList:
    with Path(path).open("r", encoding="utf-8") as f:
        return ParameterList.from_dict(json.load(f))
