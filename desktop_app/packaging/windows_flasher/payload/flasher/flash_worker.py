"""esptool-based flash helpers."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from .github_releases import BoardPackage

LogFn = Callable[[str], None]


def list_serial_ports() -> List[str]:
    try:
        from serial.tools import list_ports

        return [p.device for p in list_ports.comports()]
    except Exception:
        return []


def _find_esptool() -> List[str]:
    """Return command prefix to run esptool."""
    # 1) PATH
    for name in ("esptool.py", "esptool"):
        p = shutil.which(name)
        if p:
            return [p]
    # 2) python -m esptool
    return [sys.executable, "-m", "esptool"]


def resolve_file(board: BoardPackage, rel_path: str) -> Path:
    """Map manifest path like 'esp32dev/firmware.bin' to on-disk file."""
    if not board.local_dir:
        raise FileNotFoundError("Paquete de placa sin carpeta local (¿descarga incompleta?)")
    base = board.local_dir
    # path may be board_id/file.bin
    cand = base / rel_path
    if cand.is_file():
        return cand
    # or just filename inside board folder
    name = Path(rel_path).name
    cand2 = base / board.id / name
    if cand2.is_file():
        return cand2
    cand3 = base / name
    if cand3.is_file():
        return cand3
    # search
    found = list(base.rglob(name))
    if found:
        return found[0]
    raise FileNotFoundError(f"No se encuentra {rel_path} en {base}")


def flash_board(
    board: BoardPackage,
    port: str,
    *,
    baud: int = 921600,
    erase_all: bool = False,
    log: Optional[LogFn] = None,
) -> None:
    def L(msg: str) -> None:
        if log:
            log(msg)
        else:
            print(msg, flush=True)

    if not port:
        raise RuntimeError("Seleccioná un puerto serial")
    if not board.files:
        raise RuntimeError("El paquete de firmware no tiene archivos")

    # Build address file list: addr file addr file ...
    pairs: List[str] = []
    for f in board.files:
        path = resolve_file(board, f.path)
        pairs.extend([f.offset, str(path)])
        L(f"  {f.offset}  {path.name}  ({path.stat().st_size} bytes)")

    cmd = _find_esptool()
    # esptool v4/v5: global opts then subcommand (hyphenated reset modes in v5)
    base = [
        *cmd,
        "--chip",
        board.chip,
        "--port",
        port,
        "--baud",
        str(baud),
        "--before",
        "default-reset",
        "--after",
        "hard-reset",
    ]

    if erase_all:
        erase_cmd = [*base, "erase-flash"]
        L("+ " + " ".join(erase_cmd))
        subprocess.check_call(erase_cmd)

    write_cmd = [
        *base,
        "write-flash",
        "--compress",
        "--flash-mode",
        board.flash_mode,
        "--flash-freq",
        board.flash_freq,
        "--flash-size",
        board.flash_size,
        *pairs,
    ]
    L("+ " + " ".join(write_cmd))
    # Stream output
    proc = subprocess.Popen(
        write_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        L(line.rstrip())
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"esptool terminó con código {rc}")
    L("Flash OK.")
