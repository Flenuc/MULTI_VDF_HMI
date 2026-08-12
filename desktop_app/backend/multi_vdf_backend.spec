# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — run from desktop_app/:
#   pyinstaller backend/multi_vdf_backend.spec

import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH).resolve().parent  # desktop_app when spec is in backend/

a = Analysis(
    [str(root / "backend" / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "backend",
        "backend.main",
        "backend.session",
        "backend.schemas",
        "comms",
        "comms.base",
        "comms.serial_client",
        "comms.mqtt_client",
        "comms.bluetooth_client",
        "comms.ble_nus_client",
        "comms.dummy_client",
        "serial.tools.list_ports",
        "paho.mqtt.client",
        "bleak",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "PIL"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="multi_vdf_backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # keep console for field diagnostics
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
