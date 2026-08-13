"""
BLE Nordic UART Service (NUS) client — wireless serial for Guition / C6.

UUIDs (Nordic standard):
  Service  6E400001-B5A3-F393-E0A9-E50E24DCCA9E
  RX       6E400002-...  (write to device)
  TX       6E400003-...  (notify from device)

Requires: pip install bleak
"""

from __future__ import annotations

import asyncio
import re
import threading
import time
from typing import List, Optional

from .base import CommsClient, ConnectionState

NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


def list_ble_nus_devices(scan_seconds: float = 5.0) -> List[dict]:
    """
    Scan for BLE advertisers. Prefer names containing SAJ / PDM / Edge,
    or devices exposing the NUS service UUID when the scanner reports it.
    """
    try:
        from bleak import BleakScanner
    except ImportError as e:
        raise RuntimeError("Instalá bleak: pip install bleak") from e

    async def _scan():
        out = []
        try:
            found = await BleakScanner.discover(
                timeout=scan_seconds, return_adv=True
            )
        except TypeError:
            # older bleak: list of BLEDevice only
            found = {
                d.address: (d, None)
                for d in await BleakScanner.discover(timeout=scan_seconds)
            }
        for addr, pair in found.items():
            if isinstance(pair, tuple):
                dev, adv = pair
            else:
                dev, adv = pair, None
            name = getattr(dev, "name", None) or ""
            if adv is not None:
                name = name or getattr(adv, "local_name", None) or ""
                uuids = [u.lower() for u in (getattr(adv, "service_uuids", None) or [])]
                rssi = getattr(adv, "rssi", None)
            else:
                uuids, rssi = [], getattr(dev, "rssi", None)
            has_nus = NUS_SERVICE in uuids
            interesting = (
                has_nus
                or "SAJ" in name.upper()
                or "PDM" in name.upper()
                or "EDGE" in name.upper()
            )
            out.append(
                {
                    "address": str(addr).upper() if ":" in str(addr) else str(addr),
                    "name": name or str(addr),
                    "rssi": rssi,
                    "has_nus": has_nus,
                    "interesting": interesting,
                }
            )
        out.sort(
            key=lambda d: (
                0 if d["has_nus"] else 1,
                0 if d["interesting"] else 1,
                -(d["rssi"] or -999),
                d["name"].lower(),
            )
        )
        return out

    return asyncio.run(_scan())


class BleNusClient(CommsClient):
    """Async bleak loop on a worker thread; same line CLI as USB/SPP."""

    def __init__(self) -> None:
        super().__init__()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._client = None  # BleakClient
        self._stop = threading.Event()
        self._write_lock = threading.Lock()
        self._address = ""
        self._rx_buf = ""

    def connect(self, address: str = "", **_) -> None:
        if not address:
            raise RuntimeError("Seleccioná un dispositivo BLE (Escanear BLE)")

        self.disconnect()
        self._address = address.strip()
        self._stop.clear()
        self._set_state(ConnectionState.CONNECTING, f"BLE NUS {self._address}…")

        ready = threading.Event()
        err_box: list = []

        def runner():
            try:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._loop.run_until_complete(self._async_connect())
                ready.set()
                self._loop.run_forever()
            except Exception as e:
                err_box.append(e)
                ready.set()
            finally:
                try:
                    if self._loop and self._loop.is_running():
                        self._loop.stop()
                except Exception:
                    pass

        self._thread = threading.Thread(target=runner, name="ble-nus", daemon=True)
        self._thread.start()
        if not ready.wait(timeout=25.0):
            self.disconnect()
            raise RuntimeError(f"Timeout conectando BLE a {self._address}")
        if err_box:
            self._set_state(ConnectionState.ERROR, str(err_box[0]))
            raise RuntimeError(
                f"BLE NUS falló con {self._address}: {err_box[0]}\n"
                "¿Firmware Guition con NUS? ¿Dispositivo en rango?"
            ) from err_box[0]
        self._set_state(ConnectionState.CONNECTED, f"BLE NUS {self._address}")

    async def _async_connect(self):
        from bleak import BleakClient

        self._client = BleakClient(self._address, timeout=20.0)
        await self._client.connect()
        # Prefer notify on TX characteristic
        await self._client.start_notify(NUS_TX, self._on_notify)

    def _on_notify(self, _handle: int, data: bytearray):
        try:
            chunk = bytes(data).decode("utf-8", errors="replace")
        except Exception:
            return
        self._rx_buf += chunk
        while "\n" in self._rx_buf:
            line, self._rx_buf = self._rx_buf.split("\n", 1)
            line = line.strip("\r")
            if line and line != ">":
                if line.startswith("> "):
                    line = line[2:]
                self._emit_line(line)

    def disconnect(self) -> None:
        self._stop.set()
        loop = self._loop
        client = self._client
        if loop and client and loop.is_running():

            async def _close():
                try:
                    if client.is_connected:
                        try:
                            await client.stop_notify(NUS_TX)
                        except Exception:
                            pass
                        await client.disconnect()
                except Exception:
                    pass

            try:
                fut = asyncio.run_coroutine_threadsafe(_close(), loop)
                fut.result(timeout=5.0)
            except Exception:
                pass
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._loop = None
        self._client = None
        if self.state != ConnectionState.DISCONNECTED:
            self._set_state(ConnectionState.DISCONNECTED, "BLE closed")

    def send_line(self, line: str) -> None:
        if not self._client or not self._loop:
            raise RuntimeError("BLE no conectado")
        data = (line.rstrip("\r\n") + "\n").encode("utf-8")

        async def _write():
            # Chunk for default ATT MTU
            mtu_payload = 180
            for i in range(0, len(data), mtu_payload):
                await self._client.write_gatt_char(
                    NUS_RX, data[i : i + mtu_payload], response=False
                )

        with self._write_lock:
            fut = asyncio.run_coroutine_threadsafe(_write(), self._loop)
            fut.result(timeout=8.0)
