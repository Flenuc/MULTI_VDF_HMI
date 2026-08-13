"""
VarioField backend entry (packaged under Electron resources/pyapp).

Respects MULTI_VDF_UI_DIR / MULTI_VDF_HOST / MULTI_VDF_PORT from the Electron shell.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _prepare() -> None:
    root_s = str(ROOT)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    os.chdir(ROOT)

    # Prefer UI path injected by Electron; fallback to sibling ui/ or local ui/
    if not os.environ.get("MULTI_VDF_UI_DIR", "").strip():
        for candidate in (
            ROOT.parent / "ui",
            ROOT / "ui",
        ):
            if candidate.is_dir() and (candidate / "index.html").is_file():
                os.environ["MULTI_VDF_UI_DIR"] = str(candidate)
                break

    os.environ.setdefault("MULTI_VDF_HOST", "127.0.0.1")
    os.environ.setdefault("MULTI_VDF_PORT", "8765")


def main() -> None:
    _prepare()
    host = os.environ.get("MULTI_VDF_HOST", "127.0.0.1")
    port = os.environ.get("MULTI_VDF_PORT", "8765")
    ui = os.environ.get("MULTI_VDF_UI_DIR", "")
    print(f"[variofield] http://{host}:{port}  ui={ui or '(API only)'}", flush=True)
    from backend.main import main as backend_main

    backend_main()


if __name__ == "__main__":
    main()
