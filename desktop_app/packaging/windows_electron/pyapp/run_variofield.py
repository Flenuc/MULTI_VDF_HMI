"""
VarioField backend entry (Electron resources/pyapp).

Designed for the Windows embeddable CPython layout where python*._pth
ignores PYTHONPATH — we always inject paths ourselves.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# resources/ is parent of pyapp/
RESOURCES = ROOT.parent
PYTHON_DIR = RESOURCES / "python"
LOG_FALLBACK = ROOT / "backend-boot.log"


def _log(msg: str) -> None:
    line = msg.rstrip() + "\n"
    try:
        sys.stderr.write(line)
        sys.stderr.flush()
    except Exception:
        pass
    try:
        with open(LOG_FALLBACK, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _prepare() -> None:
    # Ensure our app root is first on sys.path (._pth often ignores PYTHONPATH)
    root_s = str(ROOT)
    if root_s in sys.path:
        sys.path.remove(root_s)
    sys.path.insert(0, root_s)

    site_pkg = PYTHON_DIR / "Lib" / "site-packages"
    if site_pkg.is_dir():
        sp = str(site_pkg)
        if sp not in sys.path:
            sys.path.insert(1, sp)

    try:
        os.chdir(ROOT)
    except Exception as e:
        _log(f"chdir failed: {e}")

    # Prefer UI path from Electron; else sibling resources/ui
    if not os.environ.get("MULTI_VDF_UI_DIR", "").strip():
        for candidate in (RESOURCES / "ui", ROOT / "ui"):
            if candidate.is_dir() and (candidate / "index.html").is_file():
                os.environ["MULTI_VDF_UI_DIR"] = str(candidate)
                break

    # Multi-VDF catalogs
    if not os.environ.get("MULTI_VDF_RESOURCES", "").strip():
        os.environ["MULTI_VDF_RESOURCES"] = str(RESOURCES)
    if not os.environ.get("MULTI_VDF_DRIVE_PROFILES", "").strip():
        for candidate in (RESOURCES / "drive_profiles", ROOT / "drive_profiles"):
            if candidate.is_dir():
                os.environ["MULTI_VDF_DRIVE_PROFILES"] = str(candidate)
                break

    os.environ.setdefault("MULTI_VDF_HOST", "127.0.0.1")
    os.environ.setdefault("MULTI_VDF_PORT", "8765")
    os.environ.setdefault("VARIOFIELD_EMBED", "1")


def main() -> None:
    try:
        with open(LOG_FALLBACK, "w", encoding="utf-8") as f:
            f.write("=== run_variofield boot ===\n")
    except Exception:
        pass

    _prepare()
    host = os.environ.get("MULTI_VDF_HOST", "127.0.0.1")
    port = os.environ.get("MULTI_VDF_PORT", "8765")
    ui = os.environ.get("MULTI_VDF_UI_DIR", "")
    _log(f"python={sys.version}")
    _log(f"executable={sys.executable}")
    _log(f"ROOT={ROOT}")
    _log(f"sys.path[:5]={sys.path[:5]}")
    _log(f"http://{host}:{port}  ui={ui or '(API only)'}")

    # Import check with clear errors
    try:
        import fastapi  # noqa: F401
        import uvicorn
        import pydantic  # noqa: F401
    except Exception:
        _log("FATAL: dependency import failed")
        _log(traceback.format_exc())
        raise

    try:
        from backend.main import app as fastapi_app
    except Exception:
        _log("FATAL: cannot import backend.main")
        _log(traceback.format_exc())
        raise

    _log("imports OK — starting uvicorn")
    # Pass app object (avoids re-import via string under embed isolation)
    uvicorn.run(
        fastapi_app,
        host=host,
        port=int(port),
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _log(traceback.format_exc())
        raise
