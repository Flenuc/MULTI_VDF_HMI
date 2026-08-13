"""
VarioField Windows launcher (portable / NSIS install).

Starts the FastAPI backend with the bundled Expo web UI and opens the browser
when /health is ready. Close this console window to stop the service.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI_DIR = ROOT / "ui"
HOST = os.environ.get("MULTI_VDF_HOST", "127.0.0.1")
PORT = int(os.environ.get("MULTI_VDF_PORT", "8765"))


def _prepare_env() -> None:
    os.environ.setdefault("MULTI_VDF_HOST", HOST)
    os.environ.setdefault("MULTI_VDF_PORT", str(PORT))
    if UI_DIR.is_dir() and (UI_DIR / "index.html").is_file():
        os.environ["MULTI_VDF_UI_DIR"] = str(UI_DIR)
    # Ensure desktop_app root is importable as package parent
    root_s = str(ROOT)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    os.chdir(ROOT)


def _open_browser_when_ready(timeout_s: float = 45.0) -> None:
    import urllib.error
    import urllib.request

    url_health = f"http://{HOST}:{PORT}/health"
    url_ui = f"http://{HOST}:{PORT}/"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url_health, timeout=1.5) as resp:
                if getattr(resp, "status", 200) == 200:
                    webbrowser.open(url_ui)
                    print(f"[variofield] UI abierta: {url_ui}", flush=True)
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.4)
    print(
        f"[variofield] Aviso: no hubo /health a tiempo. Abra manualmente {url_ui}",
        flush=True,
    )


def main() -> None:
    _prepare_env()
    ui = os.environ.get("MULTI_VDF_UI_DIR", "")
    print("=== VarioField 0.3.2 ===", flush=True)
    print(f"Backend: http://{HOST}:{PORT}", flush=True)
    print(f"UI dir:  {ui or '(no encontrada — solo API)'}", flush=True)
    print("Cierre esta ventana para detener el servicio.", flush=True)
    print("", flush=True)

    threading.Thread(target=_open_browser_when_ready, daemon=True).start()

    # Import after path/env are ready
    from backend.main import main as backend_main

    backend_main()


if __name__ == "__main__":
    main()
