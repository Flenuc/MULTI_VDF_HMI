"""
Bluetooth Classic SPP (RFCOMM) transport — wireless serial port.

Linux (BlueZ):
  Discovery: hcitool inquiry + bluetoothctl BREDR.
  Connect: AF_BLUETOOTH + BTPROTO_RFCOMM (no root / rfcomm bind).

Windows:
  Discovery: WinRT BluetoothDevice list, BTHPORT registry (paired),
  PnP Bluetooth devices, and Bluetooth SPP COM ports.
  Connect: AF_BLUETOOTH RFCOMM when available; fallback to the paired
  SPP virtual serial port (COMx) that Windows creates after pairing.

Edge advertises Classic SPP name: SAJ-PDM30-Edge (ESP32 classic only).
On Windows, pair once in system settings if needed; then scan + connect.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple

from .base import CommsClient, ConnectionState

# Serial Port Profile RFCOMM channel (BluetoothSerial default is 1)
DEFAULT_RFCOMM_CHANNEL = 1
PREFERRED_NAMES = ("SAJ-PDM30-Edge", "SAJ-PDM30", "SAJ", "PDM", "EDGE", "VARIO")


def _run(cmd: list[str], timeout: float = 12.0) -> Tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 1, str(e)


def _normalize_mac(raw: str) -> str:
    s = re.sub(r"[^0-9A-Fa-f]", "", (raw or "").upper())
    if len(s) != 12:
        return ""
    return ":".join(s[i : i + 2] for i in range(0, 12, 2))


def _mac_from_uint64(addr: int) -> str:
    """Windows BluetoothAddress is a 64-bit value; lower 48 bits are the MAC."""
    addr = int(addr) & 0xFFFFFFFFFFFF
    return ":".join(f"{(addr >> (8 * (5 - i))) & 0xFF:02X}" for i in range(6))


def _merge_device(
    bag: Dict[str, dict],
    address: str,
    name: str = "",
    *,
    paired: Optional[bool] = None,
    trusted: Optional[bool] = None,
    source: str = "",
    com_port: str = "",
) -> None:
    address = _normalize_mac(address) or address.strip().upper()
    if not re.match(r"^[0-9A-F:]{17}$", address):
        return
    cur = bag.get(address)
    if cur is None:
        bag[address] = {
            "address": address,
            "name": (name or address).strip() or address,
            "paired": bool(paired) if paired is not None else False,
            "trusted": bool(trusted) if trusted is not None else False,
            "source": source,
            "com_port": com_port or "",
        }
        return
    # Prefer human name over raw MAC
    if name and name.strip() and name.strip().upper() != address:
        if cur["name"] == cur["address"] or not cur.get("name"):
            cur["name"] = name.strip()
        elif name.strip() not in cur["name"] and len(name.strip()) > len(cur["name"]):
            # keep longer descriptive name
            if not any(p in cur["name"].upper() for p in PREFERRED_NAMES):
                cur["name"] = name.strip()
    if paired is not None:
        cur["paired"] = bool(paired) or bool(cur.get("paired"))
    if trusted is not None:
        cur["trusted"] = bool(trusted) or bool(cur.get("trusted"))
    if com_port and not cur.get("com_port"):
        cur["com_port"] = com_port
    if source and source not in (cur.get("source") or ""):
        cur["source"] = f"{cur.get('source', '')}+{source}".strip("+")


def _rank_devices(devices: List[dict]) -> List[dict]:
    def rank(d: dict) -> tuple:
        name_u = (d.get("name") or "").upper()
        pref = 50
        for i, needle in enumerate(PREFERRED_NAMES):
            if needle.upper() in name_u:
                pref = i
                break
        return (
            pref,
            0 if d.get("paired") else 1,
            0 if d.get("com_port") else 1,
            (d.get("name") or "").lower(),
        )

    devices.sort(key=rank)
    return devices


# ---------------------------------------------------------------------------
# Linux discovery
# ---------------------------------------------------------------------------


def _scan_hcitool(scan_seconds: float) -> Dict[str, dict]:
    """Classic inquiry — finds ESP32 SPP without prior pairing."""
    bag: Dict[str, dict] = {}
    if not shutil.which("hcitool"):
        return bag
    timeout = max(14.0, float(scan_seconds) + 8.0)
    rc, out = _run(["hcitool", "scan"], timeout=timeout)
    if rc != 0 and not out.strip():
        _run(["hciconfig", "hci0", "up"], timeout=5.0)
        rc, out = _run(["hcitool", "scan"], timeout=timeout)
    for line in out.splitlines():
        m = re.search(
            r"([0-9A-Fa-f:]{17})\s+(\S.*\S|\S)\s*$",
            line.strip(),
        )
        if not m:
            continue
        addr, name = m.group(1), m.group(2).strip()
        if name.lower() in ("scanning", "...") or name.startswith("Scanning"):
            continue
        _merge_device(bag, addr, name, source="hcitool")
    return bag


def _scan_bluetoothctl_bredr(scan_seconds: float) -> None:
    if not shutil.which("bluetoothctl"):
        return
    seconds = min(max(float(scan_seconds), 5.0), 20.0)
    try:
        p = subprocess.Popen(
            ["bluetoothctl"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert p.stdin is not None
        for line in (
            "power on",
            "agent NoInputNoOutput",
            "default-agent",
            "pairable on",
            "menu scan",
            "transport bredr",
            "duplicate-data on",
            "back",
            "scan on",
        ):
            p.stdin.write(line + "\n")
        p.stdin.flush()
        time.sleep(seconds)
        p.stdin.write("scan off\nquit\n")
        p.stdin.flush()
        try:
            p.communicate(timeout=6)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate(timeout=3)
    except Exception:
        _run(["bluetoothctl", "power", "on"], timeout=5.0)
        _run(["bluetoothctl", "scan", "on"], timeout=3.0)
        time.sleep(seconds)
        _run(["bluetoothctl", "scan", "off"], timeout=3.0)


def _devices_from_bluetoothctl() -> Dict[str, dict]:
    bag: Dict[str, dict] = {}
    rc, out = _run(["bluetoothctl", "devices"], timeout=8.0)
    if rc != 0:
        return bag
    for line in out.splitlines():
        m = re.match(r"Device\s+([0-9A-Fa-f:]{17})\s+(.*)$", line.strip())
        if not m:
            continue
        addr, name = m.group(1).upper(), m.group(2).strip()
        info_rc, info = _run(["bluetoothctl", "info", addr], timeout=5.0)
        paired = "Paired: yes" in info if info_rc == 0 else False
        trusted = "Trusted: yes" in info if info_rc == 0 else False
        _merge_device(
            bag,
            addr,
            name,
            paired=paired,
            trusted=trusted,
            source="bluetoothctl",
        )
    return bag


def _list_bluetooth_linux(scan_seconds: float) -> List[dict]:
    _run(["bluetoothctl", "power", "on"], timeout=5.0)
    if shutil.which("rfkill"):
        _run(["rfkill", "unblock", "bluetooth"], timeout=3.0)

    bag: Dict[str, dict] = {}
    for addr, d in _scan_hcitool(scan_seconds).items():
        bag[addr] = d
    _scan_bluetoothctl_bredr(scan_seconds)
    for addr, d in _devices_from_bluetoothctl().items():
        if addr in bag:
            _merge_device(
                bag,
                addr,
                d.get("name", ""),
                paired=d.get("paired"),
                trusted=d.get("trusted"),
                source="bluetoothctl",
            )
        else:
            bag[addr] = d
    return _rank_devices(list(bag.values()))


# ---------------------------------------------------------------------------
# Windows discovery
# ---------------------------------------------------------------------------


def _win_devices_from_registry() -> Dict[str, dict]:
    """Paired Classic devices under BTHPORT (includes friendly Name bytes)."""
    bag: Dict[str, dict] = {}
    if sys.platform != "win32":
        return bag
    try:
        import winreg  # type: ignore
    except ImportError:
        return bag

    path = r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices"
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
    except OSError:
        return bag

    i = 0
    while True:
        try:
            sub = winreg.EnumKey(root, i)
            i += 1
        except OSError:
            break
        mac = _normalize_mac(sub)
        if not mac:
            continue
        name = ""
        try:
            sk = winreg.OpenKey(root, sub)
            try:
                raw, typ = winreg.QueryValueEx(sk, "Name")
                if isinstance(raw, bytes):
                    name = raw.split(b"\x00")[0].decode("utf-8", errors="ignore").strip()
                elif isinstance(raw, str):
                    name = raw.strip()
            except OSError:
                pass
            finally:
                winreg.CloseKey(sk)
        except OSError:
            pass
        _merge_device(
            bag,
            mac,
            name or mac,
            paired=True,
            source="registry",
        )
    try:
        winreg.CloseKey(root)
    except Exception:
        pass
    return bag


def _win_devices_from_pnp() -> Dict[str, dict]:
    """WMIC / PowerShell PnP Bluetooth entries (name + MAC in InstanceId)."""
    bag: Dict[str, dict] = {}
    if sys.platform != "win32":
        return bag

    # PowerShell: more reliable than wmic on Win11
    ps = (
        "Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | "
        "Where-Object { $_.FriendlyName } | "
        "Select-Object FriendlyName, InstanceId, Status | ConvertTo-Json -Compress"
    )
    rc, out = _run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps,
        ],
        timeout=20.0,
    )
    if rc != 0 or not out.strip():
        # Fallback wmic
        rc, out = _run(
            [
                "wmic",
                "path",
                "Win32_PnPEntity",
                "where",
                "PNPClass='Bluetooth'",
                "get",
                "Name,DeviceID",
                "/format:csv",
            ],
            timeout=15.0,
        )
        for line in out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3 or parts[0].lower() == "node":
                continue
            # csv: Node,DeviceID,Name
            dev_id = parts[1] if len(parts) >= 3 else ""
            name = parts[2] if len(parts) >= 3 else parts[-1]
            m = re.search(r"([0-9A-Fa-f]{12})", dev_id.replace(":", ""))
            if not m:
                # DEV_AABBCCDDEEFF pattern
                m = re.search(r"DEV_([0-9A-Fa-f]{12})", dev_id, re.I)
            if not m:
                continue
            mac = _normalize_mac(m.group(1))
            if mac and name and "Microsoft" not in name:
                _merge_device(bag, mac, name, paired=True, source="pnp")
        return bag

    # Parse JSON (single object or list)
    import json

    try:
        data = json.loads(out.strip())
    except json.JSONDecodeError:
        return bag
    if isinstance(data, dict):
        data = [data]
    for row in data or []:
        name = str(row.get("FriendlyName") or "").strip()
        inst = str(row.get("InstanceId") or "")
        if not name:
            continue
        # Skip radio / generic stack entries without a remote MAC
        m = re.search(r"DEV_([0-9A-Fa-f]{12})", inst, re.I)
        if not m:
            m = re.search(r"([0-9A-Fa-f]{12})", inst.replace(":", "").replace("-", ""))
        if not m:
            continue
        mac = _normalize_mac(m.group(1))
        if not mac:
            continue
        # Filter pure local radio names
        low = name.lower()
        if low in ("bluetooth", "microsoft bluetooth enumerator", "bluetooth device"):
            continue
        if "enumerator" in low or "radio" in low and "saj" not in low:
            # keep radios out unless they look like our edge
            if not any(p.lower() in low for p in PREFERRED_NAMES):
                continue
        _merge_device(bag, mac, name, paired=True, source="pnp")
    return bag


def _win_devices_from_com_ports() -> Dict[str, dict]:
    """
    Windows pairs SPP as 'Standard Serial over Bluetooth link (COMx)'.
    HWID often embeds the remote MAC.
    """
    bag: Dict[str, dict] = {}
    try:
        from serial.tools import list_ports
    except Exception:
        return bag
    for p in list_ports.comports():
        desc = (p.description or "") + " " + (p.manufacturer or "")
        hwid = (getattr(p, "hwid", None) or "") + " " + desc
        if not re.search(r"bth|bluetooth|bt_", hwid, re.I):
            # still allow explicit Bluetooth wording in description
            if "bluetooth" not in desc.lower():
                continue
        m = re.search(r"DEV_([0-9A-Fa-f]{12})", hwid, re.I)
        if not m:
            m = re.search(
                r"([0-9A-Fa-f]{2}[:\-]?){5}[0-9A-Fa-f]{2}",
                hwid,
            )
            mac = _normalize_mac(m.group(0)) if m else ""
        else:
            mac = _normalize_mac(m.group(1))
        name = (p.description or p.device or "BT SPP").strip()
        # Clean "Standard Serial over Bluetooth link (COM5)" → keep useful text
        if mac:
            _merge_device(
                bag,
                mac,
                name,
                paired=True,
                source="com",
                com_port=p.device,
            )
        else:
            # COM without parseable MAC — still useful as serial transport
            # expose synthetic key only if we can later connect by COM
            pass
    return bag


def _win_devices_from_winrt(scan_seconds: float = 0.0) -> Dict[str, dict]:
    """Enumerate Classic Bluetooth devices via WinRT (paired + known)."""
    bag: Dict[str, dict] = {}
    if sys.platform != "win32":
        return bag
    try:
        import asyncio

        from winrt.windows.devices.bluetooth import (  # type: ignore
            BluetoothConnectionStatus,
            BluetoothDevice,
        )
        from winrt.windows.devices.enumeration import DeviceInformation  # type: ignore
    except Exception:
        return bag

    async def _go() -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        try:
            selector = BluetoothDevice.get_device_selector()
            infos = await DeviceInformation.find_all_async(selector)
        except Exception:
            return out
        for info in infos:
            try:
                name = (info.name or "").strip()
                dev = await BluetoothDevice.from_id_async(info.id)
                if dev is None:
                    continue
                mac = _mac_from_uint64(int(dev.bluetooth_address))
                paired = True  # appears in selector when known/paired
                try:
                    # connection_status available on some builds
                    _ = dev.connection_status
                    if dev.connection_status == BluetoothConnectionStatus.CONNECTED:
                        paired = True
                except Exception:
                    pass
                if not name:
                    try:
                        name = (dev.name or "").strip()
                    except Exception:
                        name = ""
                if not name:
                    name = mac
                _merge_device(out, mac, name, paired=paired, source="winrt")
            except Exception:
                continue
        return out

    try:
        try:
            asyncio.get_running_loop()
            # Already on a loop (unlikely in threadpool) — use new loop in thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                bag = pool.submit(lambda: asyncio.run(_go())).result(
                    timeout=max(12.0, float(scan_seconds) + 5.0)
                )
        except RuntimeError:
            bag = asyncio.run(_go())
    except Exception:
        bag = {}
    return bag


def _list_bluetooth_windows(scan_seconds: float) -> List[dict]:
    bag: Dict[str, dict] = {}
    # Order: rich names first
    for src in (
        _win_devices_from_winrt(scan_seconds),
        _win_devices_from_registry(),
        _win_devices_from_pnp(),
        _win_devices_from_com_ports(),
    ):
        for addr, d in src.items():
            if addr in bag:
                _merge_device(
                    bag,
                    addr,
                    d.get("name", ""),
                    paired=d.get("paired"),
                    trusted=d.get("trusted"),
                    source=str(d.get("source") or ""),
                    com_port=str(d.get("com_port") or ""),
                )
            else:
                bag[addr] = d
    return _rank_devices(list(bag.values()))


def list_bluetooth_devices(scan_seconds: float = 10.0) -> List[dict]:
    """
    Discover Classic Bluetooth devices for SPP.

    Linux: inquiry without prior pairing (hcitool / bluetoothctl).
    Windows: paired/known devices + SPP COM ports (pair in OS if missing).

    Each item: {address, name, paired, trusted, source?, com_port?}
    """
    if sys.platform == "win32":
        return _list_bluetooth_windows(scan_seconds)
    return _list_bluetooth_linux(scan_seconds)


def ensure_paired(address: str, timeout: float = 25.0) -> None:
    """
    Best-effort trust + pair.

    Linux: bluetoothctl Just Works agent.
    Windows: pairing is done by the OS; we no-op (device should already
    appear in Settings → Bluetooth).
    """
    address = address.upper()
    if sys.platform == "win32":
        return
    _run(["bluetoothctl", "power", "on"], timeout=5.0)
    try:
        p = subprocess.Popen(
            ["bluetoothctl"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert p.stdin is not None
        for line in (
            "agent NoInputNoOutput",
            "default-agent",
            "pairable on",
            f"trust {address}",
            f"pair {address}",
        ):
            p.stdin.write(line + "\n")
        p.stdin.flush()
        time.sleep(min(timeout, 18.0))
        p.stdin.write("quit\n")
        p.stdin.flush()
        try:
            p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    except Exception:
        _run(["bluetoothctl", "trust", address], timeout=8.0)
        _run(["bluetoothctl", "pair", address], timeout=timeout)


def find_spp_com_port(address: str) -> Optional[str]:
    """Locate Windows Bluetooth SPP virtual COM port for a MAC."""
    address = _normalize_mac(address)
    if not address:
        return None
    flat = address.replace(":", "")
    try:
        from serial.tools import list_ports
    except Exception:
        return None
    for p in list_ports.comports():
        hwid = (getattr(p, "hwid", None) or "") + " " + (p.description or "")
        h = hwid.upper().replace(":", "").replace("-", "")
        if flat in h and re.search(r"BTH|BLUETOOTH", h, re.I):
            return p.device
        if flat in h and "COM" in (p.device or "").upper():
            return p.device
    # Second pass: any BTH port if only one BT serial exists and list was empty of match
    return None


class BluetoothClient(CommsClient):
    """
    Classic Bluetooth SPP client.

    Byte stream is line-oriented CLI identical to USB Serial.
    On Windows may fall back to the paired SPP COM port.
    """

    def __init__(self) -> None:
        super().__init__()
        self._sock: Optional[socket.socket] = None
        self._serial = None  # optional pyserial.Serial for Windows COM fallback
        self._rx_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._write_lock = threading.Lock()
        self._address = ""
        self._channel = DEFAULT_RFCOMM_CHANNEL
        self._via = ""  # "rfcomm" | "com"

    def connect(
        self,
        address: str = "",
        channel: int = DEFAULT_RFCOMM_CHANNEL,
        pair: bool = True,
        **_,
    ) -> None:
        if not address or len(address) < 12:
            raise RuntimeError("Seleccioná un dispositivo Bluetooth (MAC)")

        self.disconnect()
        address = _normalize_mac(address) or address.strip().upper()
        self._address = address
        self._channel = int(channel) if channel else DEFAULT_RFCOMM_CHANNEL
        self._set_state(
            ConnectionState.CONNECTING,
            f"BT SPP {address} ch{self._channel}…",
        )

        if pair and sys.platform != "win32":
            try:
                ensure_paired(address)
            except Exception as e:
                self._emit_error(f"BT pair aviso: {e}")

        last_err: Optional[Exception] = None

        # 1) Native RFCOMM (Linux always; Windows when stack allows)
        if hasattr(socket, "AF_BLUETOOTH") and hasattr(socket, "BTPROTO_RFCOMM"):
            try:
                sock = socket.socket(
                    socket.AF_BLUETOOTH,
                    socket.SOCK_STREAM,
                    socket.BTPROTO_RFCOMM,  # type: ignore[attr-defined]
                )
                sock.settimeout(20.0)
                sock.connect((address, self._channel))
                sock.settimeout(0.2)
                self._sock = sock
                self._via = "rfcomm"
            except Exception as e:
                last_err = e
                self._sock = None

        # 2) Windows: SPP virtual serial port after system pairing
        if self._sock is None and sys.platform == "win32":
            com = find_spp_com_port(address)
            if not com:
                # Refresh discovery once to pick up COM mapping
                try:
                    _list_bluetooth_windows(2.0)
                except Exception:
                    pass
                com = find_spp_com_port(address)
            if com:
                try:
                    import serial

                    ser = serial.Serial(com, baudrate=115200, timeout=0.2)
                    self._serial = ser
                    self._via = f"com:{com}"
                except Exception as e:
                    last_err = e
                    self._serial = None

        if self._sock is None and self._serial is None:
            self._set_state(ConnectionState.ERROR, str(last_err or "BT open failed"))
            detail = str(last_err) if last_err else "sin detalle"
            if sys.platform == "win32":
                raise RuntimeError(
                    f"No se pudo abrir SPP con {address}.\n"
                    f"Detalle: {detail}\n\n"
                    "En Windows:\n"
                    "1) Emparejá el ESP32 en Configuración → Bluetooth "
                    "(nombre típico SAJ-PDM30-Edge).\n"
                    "2) Volvé a «Buscar equipos» en VarioField.\n"
                    "3) Si aparece un puerto COM Bluetooth, también podés "
                    "usar el modo USB/Serial con ese COM.\n"
                ) from last_err
            raise RuntimeError(
                f"No se pudo abrir SPP con {address}.\n"
                f"Detalle: {detail}\n\n"
                "Comprobá: Edge con firmware BT (ESP32 classic), "
                "visible al escanear «SAJ-PDM30-Edge», y BT del PC encendido.\n"
            ) from last_err

        self._stop.clear()
        self._rx_thread = threading.Thread(
            target=self._rx_loop, name="bt-spp-rx", daemon=True
        )
        self._rx_thread.start()
        self._set_state(
            ConnectionState.CONNECTED,
            f"BT SPP {address} ({self._via})",
        )
        time.sleep(0.2)

    def disconnect(self) -> None:
        self._stop.set()
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.5)
        self._rx_thread = None
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
        self._via = ""
        if self.state != ConnectionState.DISCONNECTED:
            self._set_state(ConnectionState.DISCONNECTED, "BT closed")

    def send_line(self, line: str) -> None:
        data = (line.rstrip("\r\n") + "\n").encode("utf-8")
        with self._write_lock:
            if self._sock is not None:
                self._sock.sendall(data)
                return
            if self._serial is not None:
                self._serial.write(data)
                self._serial.flush()
                return
            raise RuntimeError("Bluetooth no conectado")

    def _recv_chunk(self) -> bytes:
        if self._sock is not None:
            try:
                return self._sock.recv(512)
            except socket.timeout:
                return b""
        if self._serial is not None:
            try:
                n = self._serial.in_waiting
            except Exception:
                n = 0
            if n:
                return self._serial.read(min(n, 512))
            # blocking-ish poll
            return self._serial.read(1) or b""
        return b""

    def _rx_loop(self) -> None:
        buf = ""
        while not self._stop.is_set():
            try:
                if self._sock is None and self._serial is None:
                    break
                try:
                    chunk = self._recv_chunk()
                except socket.timeout:
                    continue
                except Exception as e:
                    if not self._stop.is_set():
                        self._emit_error(f"BT RX: {e}")
                    break
                if not chunk:
                    if self._serial is not None:
                        time.sleep(0.05)
                        continue
                    # empty recv on socket often means closed
                    if self._sock is not None:
                        if not self._stop.is_set():
                            self._emit_error("BT: conexión cerrada por el peer")
                            self._set_state(
                                ConnectionState.DISCONNECTED, "BT peer closed"
                            )
                        break
                    continue
                buf += chunk.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip("\r")
                    if line and line != ">":
                        if line.startswith("> "):
                            line = line[2:]
                        self._emit_line(line)
            except Exception as e:
                if not self._stop.is_set():
                    self._emit_error(f"BT RX: {e}")
                break
