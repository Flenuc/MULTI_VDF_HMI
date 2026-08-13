"""Pydantic request/response models for the MULTI_VDF_HMI local API."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Transport = Literal["serial", "mqtt", "bluetooth", "ble", "dummy"]


class ConnectRequest(BaseModel):
    transport: Transport
    # serial
    port: str = ""
    baud: int = 115200
    # mqtt
    host: str = "127.0.0.1"
    mqtt_port: int = 1883
    username: str = ""
    password: str = ""
    topic_prefix: str = "saj/pdm30/saj-pdm30"
    # bluetooth classic / ble
    address: str = ""
    channel: int = 1
    pair: bool = True


class CommandRequest(BaseModel):
    line: str = Field(..., min_length=1, description="CLI line without newline")


class StatusResponse(BaseModel):
    state: str
    message: str = ""
    transport: Optional[str] = None
    connected: bool = False


class PortInfo(BaseModel):
    device: str
    description: str = ""
    hwid: str = ""


class BtDevice(BaseModel):
    address: str
    name: str
    paired: bool = False
    trusted: bool = False
    has_nus: bool = False
    rssi: Optional[int] = None
    source: str = ""


class EventMessage(BaseModel):
    """Pushed over WebSocket to all UI clients."""

    type: str  # line | json | status | error | raw | hello
    payload: Any = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class OkResponse(BaseModel):
    ok: bool = True
    detail: str = ""


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "variofield-backend"
    version: str = "0.3.2"
