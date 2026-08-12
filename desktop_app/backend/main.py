"""
MULTI_VDF_HMI — local HTTP + WebSocket API for React Native / web UIs.

  uvicorn backend.main:app --host 127.0.0.1 --port 8765 --app-dir desktop_app

Or:  python -m backend.main
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

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

# Local RN (Expo web / metro) + Electron / desktop webviews
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
            # Keepalive / ignore client pings; UI is push-only for events
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                try:
                    await ws.send_json({"type": "ping", "payload": "keepalive", "meta": {}})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        session.unregister_ws(ws)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
