"""
MULTI_VDF_HMI — local HTTP + WebSocket API for React Native / Electron UIs.

Dev:
  cd desktop_app && ./run_backend.sh

Packaged (PyInstaller):
  multi_vdf_backend   # serves API + optional static UI from MULTI_VDF_UI_DIR
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.schemas import (
    BtDevice,
    CommandRequest,
    ConnectRequest,
    HealthResponse,
    OkResponse,
    PortInfo,
    StatusResponse,
)
from backend.session import session


def _ui_dir() -> Optional[Path]:
    """Locate exported Expo web build (optional)."""
    env = os.environ.get("MULTI_VDF_UI_DIR", "").strip()
    candidates: List[Path] = []
    if env:
        candidates.append(Path(env))
    if getattr(sys, "frozen", False):
        # PyInstaller: next to the executable
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                exe_dir / "ui",
                meipass / "ui",
                exe_dir.parent / "ui",
            ]
        )
    else:
        root = Path(__file__).resolve().parents[1]
        candidates.extend(
            [
                root / "frontend" / "dist",
                root / "electron" / "resources" / "ui",
            ]
        )
    for c in candidates:
        if c.is_dir() and (c / "index.html").is_file():
            return c
    return None


def _bind_host() -> str:
    return os.environ.get("MULTI_VDF_HOST", "127.0.0.1")


def _bind_port() -> int:
    return int(os.environ.get("MULTI_VDF_PORT", "8765"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    session.bind_loop(asyncio.get_running_loop())
    yield
    try:
        session.disconnect()
    except Exception:
        pass


app = FastAPI(
    title="MULTI_VDF_HMI Backend",
    version="0.2.0-rn",
    description="Python transport layer for USB / MQTT / BT / BLE — UI-agnostic.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="api")


async def _run_sync(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, lambda: fn(*args, **kwargs))


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.get("/status", response_model=StatusResponse)
def get_status() -> StatusResponse:
    s = session.status()
    return StatusResponse(**s)


@app.get("/telemetry")
def get_telemetry():
    return {"telemetry": session.last_telemetry}


@app.get("/ports", response_model=List[PortInfo])
def list_ports() -> List[PortInfo]:
    return [PortInfo(**p) for p in session.list_serial_ports()]


@app.get("/bt/classic", response_model=List[BtDevice])
async def list_bt_classic(
    scan_seconds: float = Query(10.0, ge=0.0, le=30.0),
) -> List[BtDevice]:
    devs = await _run_sync(session.list_bt_classic, scan_seconds)
    out: List[BtDevice] = []
    for d in devs:
        out.append(
            BtDevice(
                address=str(d.get("address", "")),
                name=str(d.get("name", "")),
                paired=bool(d.get("paired", False)),
                trusted=bool(d.get("trusted", False)),
                has_nus=bool(d.get("has_nus", False)),
                rssi=d.get("rssi"),
                source=str(d.get("source", "")),
            )
        )
    return out


@app.get("/bt/ble", response_model=List[BtDevice])
async def list_bt_ble(
    scan_seconds: float = Query(6.0, ge=0.0, le=30.0),
) -> List[BtDevice]:
    devs = await _run_sync(session.list_bt_ble, scan_seconds)
    out = []
    for d in devs:
        out.append(
            BtDevice(
                address=d.get("address", ""),
                name=d.get("name", ""),
                paired=bool(d.get("paired", False)),
                trusted=bool(d.get("trusted", False)),
                has_nus=bool(d.get("has_nus", False)),
                rssi=d.get("rssi"),
                source=str(d.get("source", "bleak")),
            )
        )
    return out


@app.post("/connect", response_model=OkResponse)
async def connect(body: ConnectRequest) -> OkResponse:
    try:
        await _run_sync(
            session.connect,
            body.transport,
            port=body.port,
            baud=body.baud,
            host=body.host,
            mqtt_port=body.mqtt_port,
            username=body.username,
            password=body.password,
            topic_prefix=body.topic_prefix,
            address=body.address,
            channel=body.channel,
            pair=body.pair,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return OkResponse(ok=True, detail=f"connected via {body.transport}")


@app.post("/disconnect", response_model=OkResponse)
def disconnect() -> OkResponse:
    session.disconnect()
    return OkResponse(ok=True, detail="disconnected")


@app.post("/command", response_model=OkResponse)
def command(body: CommandRequest) -> OkResponse:
    try:
        session.send_line(body.line)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return OkResponse(ok=True, detail="sent")


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    await session.register_ws(ws)
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                try:
                    await ws.send_json(
                        {"type": "ping", "payload": "keepalive", "meta": {}}
                    )
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        session.unregister_ws(ws)


# --- Optional static UI (Expo web export) — registered last so API wins ---
_UI = _ui_dir()
if _UI is not None:
    # Expo puts hashed assets under _expo/ and assets/
    for sub in ("_expo", "assets"):
        p = _UI / sub
        if p.is_dir():
            app.mount(f"/{sub}", StaticFiles(directory=str(p)), name=f"ui-{sub}")

    @app.get("/")
    async def ui_index():
        return FileResponse(_UI / "index.html")

    @app.get("/{full_path:path}")
    async def ui_spa(full_path: str):
        # Never shadow known API prefixes (safety)
        if full_path.split("/", 1)[0] in {
            "health",
            "status",
            "telemetry",
            "ports",
            "bt",
            "connect",
            "disconnect",
            "command",
            "ws",
            "docs",
            "openapi.json",
            "redoc",
        }:
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (_UI / full_path).resolve()
        try:
            candidate.relative_to(_UI.resolve())
        except ValueError:
            raise HTTPException(status_code=404, detail="Not found") from None
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_UI / "index.html")


def main() -> None:
    import uvicorn

    host = _bind_host()
    port = _bind_port()
    ui = _ui_dir()
    print(f"[backend] http://{host}:{port}  ui={ui or '(API only)'}", flush=True)

    # When frozen, pass app object (string import path may fail)
    if getattr(sys, "frozen", False):
        uvicorn.run(app, host=host, port=port, log_level="info")
    else:
        uvicorn.run(
            "backend.main:app",
            host=host,
            port=port,
            reload=False,
            log_level="info",
        )


if __name__ == "__main__":
    main()
