#!/usr/bin/env python3
"""
Build PlatformIO envs and package flashable firmware bundles + manifest.json.

Output layout (default: dist/firmware/<version>/):
  manifest.json
  guition_jc_esp32p4_m3/
    bootloader.bin  partitions.bin  boot_app0.bin  firmware.bin  meta.json
  esp32dev/
    ...
  MULTI_VDF_HMI-firmware-<version>.zip

Usage:
  python3 scripts/package_firmware.py
  python3 scripts/package_firmware.py --version 0.2.0 --skip-build
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FW_DIR = ROOT / "firmware" / "saj_pdm30_edge"
DEFAULT_OUT = ROOT / "dist" / "firmware"

# Flash maps (offsets used by Arduino-ESP32 / esptool uploads)
# Guition P4 (USB-Serial/JTAG): bootloader @ 0x2000
# Classic ESP32: bootloader @ 0x1000
BOARDS = {
    "esp32dev": {
        "name": "ESP32 DevKit + SN75176 (Classic + BT SPP)",
        "chip": "esp32",
        "flash_size": "4MB",
        "flash_mode": "dio",
        "flash_freq": "40m",
        "env": "esp32dev",
        "files": [
            {"role": "bootloader", "offset": "0x1000", "src": "bootloader.bin"},
            {"role": "partitions", "offset": "0x8000", "src": "partitions.bin"},
            {"role": "boot_app0", "offset": "0xe000", "src": "boot_app0.bin"},
            {"role": "app", "offset": "0x10000", "src": "firmware.bin"},
        ],
    },
    "guition_jc_esp32p4_m3": {
        "name": "Guition JC-ESP32P4-M3-DEV (RS485 + MQTT + BLE NUS)",
        "chip": "esp32p4",
        "flash_size": "16MB",
        "flash_mode": "qio",
        "flash_freq": "80m",
        "env": "guition_jc_esp32p4_m3",
        "files": [
            {"role": "bootloader", "offset": "0x2000", "src": "bootloader.bin"},
            {"role": "partitions", "offset": "0x8000", "src": "partitions.bin"},
            {"role": "boot_app0", "offset": "0xe000", "src": "boot_app0.bin"},
            {"role": "app", "offset": "0x10000", "src": "firmware.bin"},
        ],
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_boot_app0() -> Path | None:
    # Prefer PIO package copy
    candidates = [
        Path.home()
        / ".platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin",
        Path.home()
        / ".platformio/packages/framework-arduinoespressif32-libs/tools/partitions/boot_app0.bin",
    ]
    for c in candidates:
        if c.is_file():
            return c
    # search
    base = Path.home() / ".platformio/packages"
    if base.is_dir():
        for p in base.rglob("boot_app0.bin"):
            return p
    return None


def run_pio_build(envs: list[str]) -> None:
    env = os.environ.copy()
    # Prefer project / user PIO
    for p in (
        ROOT / "firmware" / ".pio-venv" / "bin",
        Path.home() / ".platformio" / "penv" / "bin",
    ):
        if (p / "pio").is_file():
            env["PATH"] = f"{p}:{env.get('PATH', '')}"
            break
    cmd = ["pio", "run"]
    for e in envs:
        cmd.extend(["-e", e])
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=str(FW_DIR), env=env)


def package_board(board_id: str, out_root: Path) -> dict:
    cfg = BOARDS[board_id]
    env = cfg["env"]
    build = FW_DIR / ".pio" / "build" / env
    dest = out_root / board_id
    dest.mkdir(parents=True, exist_ok=True)

    boot_app0 = find_boot_app0()
    files_out = []
    for item in cfg["files"]:
        role = item["role"]
        src_name = item["src"]
        if role == "boot_app0":
            if not boot_app0:
                raise FileNotFoundError("boot_app0.bin not found in PlatformIO packages")
            src = boot_app0
        else:
            src = build / src_name
        if not src.is_file():
            raise FileNotFoundError(f"Missing build artifact for {board_id}: {src}")
        dst = dest / src_name
        shutil.copy2(src, dst)
        meta = {
            "role": role,
            "offset": item["offset"],
            "path": f"{board_id}/{src_name}",
            "size": dst.stat().st_size,
            "sha256": sha256_file(dst),
        }
        files_out.append(meta)
        print(f"  + {board_id}/{src_name} @ {item['offset']} ({meta['size']} bytes)")

    board_meta = {
        "id": board_id,
        "name": cfg["name"],
        "chip": cfg["chip"],
        "flash_size": cfg["flash_size"],
        "flash_mode": cfg["flash_mode"],
        "flash_freq": cfg["flash_freq"],
        "env": env,
        "files": files_out,
    }
    (dest / "meta.json").write_text(
        json.dumps(board_meta, indent=2) + "\n", encoding="utf-8"
    )
    return board_meta


def make_zip(folder: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(folder).as_posix())
    print(f"ZIP {zip_path} ({zip_path.stat().st_size} bytes)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Package SAJ Edge firmwares")
    ap.add_argument("--version", default="", help="Version string (default: date)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument(
        "--boards",
        default="guition_jc_esp32p4_m3,esp32dev",
        help="Comma list of board ids",
    )
    args = ap.parse_args()

    version = args.version.strip() or datetime.now(timezone.utc).strftime("%Y.%m.%d")
    boards = [b.strip() for b in args.boards.split(",") if b.strip()]
    for b in boards:
        if b not in BOARDS:
            print(f"Unknown board id: {b}", file=sys.stderr)
            return 2

    if not args.skip_build:
        run_pio_build([BOARDS[b]["env"] for b in boards])

    out_ver = args.out / version
    if out_ver.exists():
        shutil.rmtree(out_ver)
    out_ver.mkdir(parents=True)

    firmwares = []
    for b in boards:
        print(f"Packaging {b}…")
        firmwares.append(package_board(b, out_ver))

    manifest = {
        "schema": 1,
        "product": "MULTI_VDF_HMI",
        "repo": "Flenuc/MULTI_VDF_HMI",
        "version": version,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "git": _git_describe(),
        "firmwares": firmwares,
    }
    man_path = out_ver / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {man_path}")

    zip_name = f"MULTI_VDF_HMI-firmware-{version}.zip"
    zip_path = args.out / zip_name
    make_zip(out_ver, zip_path)

    # convenience pointer
    latest = args.out / "latest"
    if latest.is_symlink() or latest.exists():
        if latest.is_dir() and not latest.is_symlink():
            shutil.rmtree(latest)
        else:
            latest.unlink()
    try:
        latest.symlink_to(out_ver.name)
    except OSError:
        # Windows or no symlink permission: copy manifest pointer
        (args.out / "latest_version.txt").write_text(version + "\n", encoding="utf-8")

    print("Done.")
    return 0


def _git_describe() -> dict:
    def g(*a):
        try:
            return subprocess.check_output(
                ["git", *a], cwd=str(ROOT), text=True, stderr=subprocess.DEVNULL
            ).strip()
        except Exception:
            return ""

    return {
        "commit": g("rev-parse", "--short", "HEAD"),
        "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
        "describe": g("describe", "--tags", "--always", "--dirty"),
    }


if __name__ == "__main__":
    sys.exit(main())
