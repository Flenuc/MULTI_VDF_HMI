#!/usr/bin/env python3
"""
Generate drive_profiles/saj/pdm30/profile.json from field-proven tables
(ScaleTable.cpp, saj_pdm30_protocol.h names, results/param_map.csv addressing).

Usage (from repo root):
  python3 tools/catalog_builder/generate_saj_pdm30_profile.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "drive_profiles" / "saj" / "pdm30" / "profile.json"

# From ScaleTable.cpp
P0_SCALE = [
    10, 10, 1, 10, 1, 1000, 10, 100, 1, 10,
    10, 100, 10, 10, 1, 10, 1, 100, 1, 1,
    10, 10, 10, 10, 10, 1, 10, 100, 10, 10,
    1, 1, 10, 10, 100, 100, 10, 10, 1, 1,
    1, 1, 1000, 1, 1, 1, 1, 1,
]
P1_SCALE = [
    1, 1, 1, 1, 1, 100, 100, 100, 1, 10,
    100, 10, 1, 10, 100, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 100,
    1, 100, 10, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1,
]
P0_UNIT = [
    "bar", "bar", "", "bar", "", "", "s", "s", "", "s",
    "s", "Hz", "s", "bar", "", "s", "", "Hz", "s", "s",
    "", "bar", "s", "bar", "s", "", "bar", "Hz", "%", "s",
    "min", "", "bar", "s", "V", "V", "s", "s", "", "",
    "", "C", "", "", "", "", "", "",
]
P1_UNIT = [
    "", "", "", "", "min", "Hz", "Hz", "Hz", "", "kHz",
    "V", "s", "", "kW", "Hz", "", "", "", "", "",
    "", "", "", "", "", "", "", "", "", "Hz",
    "", "Hz", "s", "", "", "", "", "", "ms", "",
    "", "", "", "", "", "", "", "",
]

# From saj_pdm30_protocol.h
P0_NAMES = [
    "Pressure setting", "Pressure deviation (wake)", "Operation direction",
    "Sensor range", "Sensor feedback type", "Pressure calibration factor",
    "Proportional gain P1", "Integration time I1", "PID function selection",
    "PID sleep delay", "PID wake-up delay", "PID sleep frequency",
    "PID low-freq hold run time", "PID sleep deviation pressure",
    "Power-on automatic start", "Power-on auto start delay",
    "Antifreeze function", "Antifreeze operating frequency",
    "Antifreeze running time", "Antifreeze operation cycle",
    "Leakage size factor", "High pressure alarm value", "High pressure alarm delay",
    "Low pressure alarm value", "Low pressure alarm delay",
    "Water shortage protection fn", "Water shortage fault threshold",
    "Water shortage test frequency", "Water shortage current %",
    "Water shortage detect time", "Water shortage auto restart delay",
    "PID sleep rate", "Incoming water detection pressure",
    "Incoming water detection time", "AI minimum input", "AI maximum input",
    "Acceleration time 1", "Deceleration time 1", "Parameter initialization",
    "Parameter function lock", "Broken record", "Radiator temperature",
    "Software version", "Main frequency source X", "System working mode",
    "Pressure display mode", "(reserved / unknown)", "Application macro selection",
]
P1_NAMES = [
    "Multi online slave backup host action", "Multi online network mode",
    "Number of multi-line aux machines", "Multi online operating modes",
    "Multi-line rotation interval", "Maximum output frequency", "Upper frequency",
    "Lower limit frequency", "Below lower limit frequency action", "Carrier frequency",
    "PID feedback loss detection value", "PID feedback loss detection time",
    "Motor power selection", "Motor rated power / related", "Motor rated frequency",
    "(see manual)", "(see manual)", "(see manual)", "(see manual)", "(see manual)",
    "(see manual)", "(see manual)", "(see manual)", "(see manual)", "(see manual)",
    "(see manual)", "(see manual)", "(see manual)", "Stop mode",
    "Keyboard setting frequency", "PID action direction",
    "PID low frequency hold frequency", "Sleep detection cycle", "PWM mode",
    "Command source selection", "Local address (Modbus slave)", "Baud rate",
    "Data format", "Response delay", "(reserved / unknown)", "(reserved / unknown)",
    "(reserved / unknown)", "Motor type selection", "Single-phase turns ratio",
    "Single-phase current correction", "Water shortage protection reset times",
    "(reserved / unknown)", "(reserved / unknown)",
]


def addr_group_direct(g: int, i: int) -> int:
    return (g << 8) | i


def build() -> dict:
    params = []
    for g, names, scales, units in (
        (0, P0_NAMES, P0_SCALE, P0_UNIT),
        (1, P1_NAMES, P1_SCALE, P1_UNIT),
    ):
        for i in range(48):
            reg = addr_group_direct(g, i)
            scale = scales[i] or 1
            params.append(
                {
                    "id": f"P{g}-{i:02d}",
                    "group": g,
                    "index": i,
                    "register": f"0x{reg:04X}",
                    "name": names[i],
                    "unit": units[i],
                    "scale": scale,  # eng = raw / scale
                    "access": "rw",
                    "notes": "Field-proven PDM-30 MAP_GROUP_DIRECT",
                }
            )

    return {
        "id": "saj.pdm30",
        "vendor": "SAJ",
        "family": "PDM",
        "model": "PDM-30",
        "version": "1.0.0",
        "status": "production",
        "source": [
            "firmware/saj_pdm30_edge/src/ScaleTable.cpp",
            "include/saj_pdm30_protocol.h",
            "results/param_map.csv",
            "field validation 2026",
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
        },
        "addressing": {
            "scheme": "group_direct",
            "description": "register = (group << 8) | index  → P0-ii=0x00ii, P1-ii=0x01ii",
            "param_id_format": "P{group}-{index:02d}",
        },
        "parameters": params,
        "telemetry": [
            {"id": "run_freq", "register": "0x1001", "scale": 100, "unit": "Hz", "notes": "0.01 Hz"},
            {"id": "bus_voltage", "register": "0x1002", "scale": 10, "unit": "V", "notes": "field may swap with 0x1003"},
            {"id": "out_voltage", "register": "0x1003", "scale": 1, "unit": "V"},
            {"id": "out_current", "register": "0x1004", "scale": 100, "unit": "A"},
            {"id": "set_pressure", "register": "0x0000", "scale": 10, "unit": "bar", "notes": "prefer P0-00 not 0x100F"},
            {"id": "fb_pressure", "register": "0x1010", "scale": 10, "unit": "bar"},
            {"id": "vfd_status", "register": "0x3000", "scale": 1, "unit": ""},
        ],
        "commands": {
            "start_fwd": {"register": "0x2000", "value": "0x0001"},
            "start_rev": {"register": "0x2000", "value": "0x0002"},
            "stop": {"register": "0x2000", "value": "0x0006"},
            "estop": {"register": "0x2000", "value": "0x0005"},
            "fault_reset": {"register": "0x2000", "value": "0x0007"},
        },
        "fingerprint": [
            {"id": "P1-35", "register": "0x0123", "expect_raw_hint": 1, "name": "slave id"},
            {"id": "P1-36", "register": "0x0124", "expect_raw_hint": 1, "name": "baud code 9600"},
            {"id": "P1-05", "register": "0x0105", "notes": "max freq raw often 5000 or 6000"},
        ],
        "cli": {
            "read": "r{group} {index}",
            "write": "w{group} {index} {eng}",
            "raw": "raw {register}",
            "dump": "dump",
        },
    }


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    profile = build()
    OUT.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(profile['parameters'])} params)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
