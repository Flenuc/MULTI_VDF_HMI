#!/usr/bin/env python3
"""Headless tests: models, storage, dummy serial (no GUI)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models import Parameter, ParameterList
from serial_client import DummySerialBackend, Esp32Client
from storage import load_json, save_json, save_csv, load_csv


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
    print("test_models OK")


def test_storage():
    pl = ParameterList(name="stor")
    pl.add(Parameter(0, 0, 10, notes="a"))
    pl.add(Parameter(1, 5, 6000, manual_only=True))
    with tempfile.TemporaryDirectory() as td:
        jp = Path(td) / "t.json"
        cp = Path(td) / "t.csv"
        save_json(pl, jp)
        save_csv(pl, cp)
        j2 = load_json(jp)
        c2 = load_csv(cp)
        assert len(j2.parameters) == 2
        assert len(c2.parameters) == 2
        assert j2.parameters[0].value == 10
    print("test_storage OK")


def test_dummy_serial():
    c = Esp32Client()
    c.connect_dummy()
    assert c.connected
    ping = c.ping()
    assert ping.ok, ping.message
    w = c.write_param(0, 0, 15)
    assert w.ok, w.message
    r = c.read_param(0, 0)
    assert r.ok and r.value == 15
    # list write skips manual
    params = [
        Parameter(0, 0, 20),
        Parameter(1, 35, 1, manual_only=True),
    ]
    results = c.write_list(params)
    assert len(results) == 1
    r2 = c.read_param(0, 0)
    assert r2.value == 20
    c.disconnect()
    print("test_dummy_serial OK")


def test_example_json():
    path = ROOT / "param_lists" / "ejemplo_pdm30.json"
    pl = load_json(path)
    assert len(pl.parameters) >= 5
    assert any(p.manual_only for p in pl.parameters)
    print("test_example_json OK")


if __name__ == "__main__":
    test_models()
    test_storage()
    test_dummy_serial()
    test_example_json()
    print("ALL LOGIC TESTS PASSED")
