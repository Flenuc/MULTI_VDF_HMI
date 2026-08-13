#!/usr/bin/env python3
"""Headless tests: models, storage, dummy serial (no GUI)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models import Parameter, ParameterList, parse_dump_csv_line_id
from storage import load_json, save_json


def test_models():
    p = Parameter(0, 0, 10, notes="pressure", manual_only=False)
    assert p.param_id() == "P0-00"
    assert p.address() == 0x0000
    pl = ParameterList(name="t")
    pl.add(p)
    pl.add(Parameter(0, 0, 11))  # replace
    assert len(pl.parameters) == 1
    assert pl.parameters[0].value == 11
    assert pl.writable()[0].value == 11
    pl.add(Parameter(1, 35, 1, manual_only=True))
    assert len(pl.writable()) == 1
    # multi-VDF id
    f = Parameter.from_dict({"id": "F0.00", "value": 2.6, "notes": "press"})
    assert f.param_id() == "F0.00"
    assert f.address() == 0xF000
    pl2 = ParameterList(name="pdh", drive_profile_id="saj.pdh30")
    pl2.add(f)
    d = pl2.to_dict()
    assert d["drive_profile_id"] == "saj.pdh30"
    assert d["parameters"][0]["id"] == "F0.00"
    print("test_models OK")


def test_storage():
    pl = ParameterList(name="stor")
    pl.add(Parameter(0, 0, 10, notes="a"))
    pl.add(Parameter(1, 5, 6000, manual_only=True))
    with tempfile.TemporaryDirectory() as td:
        jp = Path(td) / "t.json"
        save_json(pl, jp)
        j2 = load_json(jp)
        assert len(j2.parameters) == 2
        assert j2.parameters[0].value == 10
        assert j2.drive_profile_id == "saj.pdm30"
    print("test_storage OK")


def test_example_json():
    path = ROOT / "param_lists" / "ejemplo_pdm30.json"
    pl = load_json(path)
    assert len(pl.parameters) >= 5
    assert any(p.manual_only for p in pl.parameters)
    print("test_example_json OK")


def test_pdh_recipe_ids():
    path = ROOT / "param_lists" / "ejemplo_pdh30.json"
    pl = load_json(path)
    assert pl.drive_profile_id == "saj.pdh30"
    assert len(pl.parameters) >= 10
    assert any(p.param_id().startswith("F0.") for p in pl.parameters)
    # round-trip
    d = pl.to_dict()
    pl2 = ParameterList.from_dict(d)
    assert pl2.parameters[0].param_id() == pl.parameters[0].param_id()
    print("test_pdh_recipe_ids OK")


def test_parse_dump_pdh():
    from models import parse_dump_csv_line_id

    r = parse_dump_csv_line_id("CSV:F0.00,0xF000,2.6,26,")
    assert r is not None
    assert r[0] == "F0.00" and abs(r[1] - 2.6) < 1e-6
    r2 = parse_dump_csv_line_id("CSV:P0-03,0x0003,10,100,bar")
    assert r2 is not None and r2[0] == "P0-03"
    print("test_parse_dump_pdh OK")


if __name__ == "__main__":
    test_models()
    test_storage()
    test_example_json()
    test_pdh_recipe_ids()
    test_parse_dump_pdh()
    print("ALL LOGIC TESTS PASSED")
