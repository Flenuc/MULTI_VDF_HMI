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
    devices = _rank_devices(list(bag.values()))
    # Surface COM port in the display name (Windows SPP virtual serial)
    for d in devices:
        com = (d.get("com_port") or "").strip()
        name = (d.get("name") or "").strip()
        if com and com not in name:
            d["name"] = f"{name} ({com})" if name else com
    return devices


def list_bluetooth_devices(scan_seconds: float = 10.0) -> List[dict]:
    """
    Discover Classic Bluetooth devices for SPP.

    Linux: inquiry without prior pairing (hcitool / bluetoothctl).
    Windows: paired/known devices + SPP COM ports (pair in OS if missing).

    Each item: {address, name, paired, trusted, source?, com_port?}
    """
    if sys.platform == "win32":
        return _list_bluetooth_windows(scan_seconds)
    try:
        return _list_bluetooth_linux(scan_seconds)
    finally:
        # Leave adapter idle so a following Connect does not hit ENOMEM
        _run(["bluetoothctl", "scan", "off"], timeout=4.0)


def _btctl_is_paired(address: str) -> bool:
    rc, info = _run(["bluetoothctl", "info", address], timeout=6.0)
    if rc != 0:
        return False
    return "Paired: yes" in info or "Bonded: yes" in info


def prepare_linux_rfcomm(address: str, timeout: float = 35.0) -> str:
    """
    Make the device ready for RFCOMM on BlueZ.

    ENOMEM / flaky RFCOMM usually means: discovery still running, device not
    in cache, or passkey confirm left hanging. Flow:

      1) power + agent that can answer Confirm passkey with «yes»
      2) scan until the MAC is known
      3) trust + pair (auto-yes on agent prompts)
      4) stop discovery (critical before RFCOMM)
      5) do NOT bluetoothctl connect — BlueZ has no SPP client profile;
         the app opens RFCOMM itself.
    """
    address = _normalize_mac(address) or address.upper()
    if not shutil.which("bluetoothctl"):
        return "no-bluetoothctl"

    log: List[str] = []
    try:
        import select as _select
    except ImportError:
        _select = None  # type: ignore

    p = subprocess.Popen(
        ["bluetoothctl"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert p.stdin is not None and p.stdout is not None

    def send(cmd: str, wait: float = 0.25) -> None:
        log.append(f">>>{cmd}")
        try:
            p.stdin.write(cmd + "\n")
            p.stdin.flush()
        except Exception as e:
            log.append(f"send-err {e}")
        time.sleep(wait)

    def drain(seconds: float) -> str:
        end = time.time() + seconds
        chunks: List[str] = []
        while time.time() < end:
            if _select is not None:
                r, _, _ = _select.select([p.stdout], [], [], 0.2)
                if p.stdout not in r:
                    continue
            line = p.stdout.readline()
            if not line:
                break
            chunks.append(line)
            low = line.lower()
            # Auto-accept SSP / passkey / PIN prompts on the host agent
            if (
                "confirm passkey" in low
                or "confirm value" in low
                or "[agent] confirm" in low
                or ("yes/no" in low and "agent" in low)
                or "authorization request" in low
            ):
                send("yes", 0.2)
            if "enter pin" in low or "passkey request" in low:
                # Firmware default PIN
                send("1234", 0.2)
        return "".join(chunks)

    try:
        send("power on", 0.4)
        # DisplayYesNo can answer Confirm passkey; NoInputNoOutput often cannot
        send("agent DisplayYesNo", 0.4)
        send("default-agent", 0.3)
        send("pairable on", 0.3)
        send("scan on", 0.5)

        deadline = time.time() + min(max(timeout, 15.0), 45.0)
        seen = _btctl_is_paired(address)
        while time.time() < deadline:
            out = drain(1.0)
            if address in out or "SAJ-PDM30" in out:
                seen = True
                break
            # Already in cache from previous inquiry
            rc, info = _run(["bluetoothctl", "info", address], timeout=4.0)
            if rc == 0 and "not available" not in info.lower():
                seen = True
                break

        if not seen:
            log.append("device-not-seen-in-scan")
        else:
            send(f"trust {address}", 0.4)
            if not _btctl_is_paired(address):
                send(f"pair {address}", 0.5)
                pair_deadline = time.time() + 18.0
                while time.time() < pair_deadline:
                    out = drain(1.0)
                    if "paired: yes" in out.lower() or "pairing successful" in out.lower():
                        break
                    if _btctl_is_paired(address):
                        break
                    if "failed" in out.lower() and "pair" in out.lower():
                        log.append("pair-failed-line")
                        break

        # Always stop discovery before RFCOMM (avoids ENOMEM on many adapters)
        send("scan off", 0.4)
        drain(0.5)
        send("quit", 0.2)
        try:
            p.communicate(timeout=4)
        except Exception:
            p.kill()
    except Exception as e:
        log.append(f"exc:{e}")
        try:
            p.kill()
        except Exception:
            pass

    paired = _btctl_is_paired(address)
    return f"paired={paired};" + ";".join(log[-12:])


def ensure_paired(address: str, timeout: float = 25.0) -> None:
    """Back-compat wrapper."""
    if sys.platform == "win32":
        return
    prepare_linux_rfcomm(address, timeout=timeout)


def find_spp_com_port(address: str) -> Optional[str]:
    """Locate Windows Bluetooth SPP virtual COM port for a MAC."""
    address = _normalize_mac(address)
    flat = address.replace(":", "") if address else ""
    try:
        from serial.tools import list_ports
    except Exception:
        return None

    bt_ports = []
    for p in list_ports.comports():
        desc = (p.description or "") + " " + (p.manufacturer or "")
        hwid = (getattr(p, "hwid", None) or "") + " " + desc
        is_bt = bool(re.search(r"bth|bluetooth|bt_", hwid, re.I)) or (
            "bluetooth" in desc.lower()
        )
        if not is_bt:
            continue
        bt_ports.append(p)
        if flat:
            h = hwid.upper().replace(":", "").replace("-", "")
            if flat in h:
                return p.device

    # If exactly one BT serial port exists, use it (common after pairing one Edge)
    if len(bt_ports) == 1:
        return bt_ports[0].device
    # Prefer description mentioning SAJ / SPP / Standard Serial
    for p in bt_ports:
        d = (p.description or "").upper()
        if any(x in d for x in ("SAJ", "PDM", "STANDARD SERIAL", "SPP")):
            return p.device
    return None


def _open_rfcomm(address: str, channel: int, timeout: float = 20.0):
    sock = socket.socket(
        socket.AF_BLUETOOTH,
        socket.SOCK_STREAM,
        socket.BTPROTO_RFCOMM,  # type: ignore[attr-defined]
    )
    sock.settimeout(timeout)
    sock.connect((address, int(channel)))
    sock.settimeout(0.3)
    return sock


class BluetoothClient(CommsClient):
    """
    Classic Bluetooth SPP client.

    Byte stream is line-oriented CLI identical to USB Serial.
    Windows: prefer the OS SPP COM port (avoids double-connect / peer close).
    Linux: prepare BlueZ then RFCOMM ch1.
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
        self._via = ""  # "rfcomm" | "com:COMx"

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

        last_err: Optional[Exception] = None
        prep_note = ""

        # ----- Windows: COM first (stack already holds SPP after pairing) -----
        if sys.platform == "win32":
            com = find_spp_com_port(address)
            if not com:
                try:
                    _list_bluetooth_windows(2.0)
                except Exception:
                    pass
                com = find_spp_com_port(address)
            if com:
                try:
                    import serial

                    # Exclusive open; 115200 is ignored by most BT SPP drivers
                    ser = serial.Serial(
                        port=com,
                        baudrate=115200,
                        timeout=0.25,
                        write_timeout=2.0,
                    )
                    self._serial = ser
                    self._via = f"com:{com}"
                except Exception as e:
                    last_err = e
                    self._serial = None

            # RFCOMM only if no COM — dual open drops the peer on ESP32
            if self._serial is None and hasattr(socket, "AF_BLUETOOTH"):
                try:
                    self._sock = _open_rfcomm(address, self._channel, 20.0)
                    self._via = "rfcomm"
                except Exception as e:
                    last_err = e
                    self._sock = None

        # ----- Linux / other: RFCOMM (pair only if first attempts fail) -----
        else:
            # Discovery left running after «Buscar equipos» often yields ENOMEM
            _run(["bluetoothctl", "scan", "off"], timeout=4.0)
            time.sleep(0.35)

            channels: List[int] = []
            for ch in (self._channel, 1, 2):
                if int(ch) not in channels:
                    channels.append(int(ch))

            def try_rfcomm_once() -> bool:
                nonlocal last_err
                if not (
                    hasattr(socket, "AF_BLUETOOTH")
                    and hasattr(socket, "BTPROTO_RFCOMM")
                ):
                    last_err = RuntimeError(
                        "Este Python/SO no expone AF_BLUETOOTH (¿BlueZ?)"
                    )
                    return False
                for ch in channels:
                    try:
                        self._sock = _open_rfcomm(address, ch, timeout=18.0)
                        self._channel = ch
                        self._via = f"rfcomm:ch{ch}"
                        last_err = None
                        return True
                    except Exception as e:
                        last_err = e
                        self._sock = None
                return False

            # 1) Direct RFCOMM — works for ESP32 SPP without a full bond
            if not try_rfcomm_once():
                # 2) Soft prep (scan→trust→pair+auto-yes) then retry
                if pair:
                    try:
                        prep_note = prepare_linux_rfcomm(address, timeout=30.0)
                        print(f"[bt] prep: {prep_note}", flush=True)
                    except Exception as e:
                        prep_note = str(e)
                        print(f"[bt] pair aviso: {e}", flush=True)
                    _run(["bluetoothctl", "scan", "off"], timeout=4.0)
                    time.sleep(0.4)
                    try_rfcomm_once()

            # 3) Last chance after brief pause (adapter recovering from ENOMEM)
            if self._sock is None:
                time.sleep(0.8)
                _run(["bluetoothctl", "scan", "off"], timeout=3.0)
                try_rfcomm_once()

        if self._sock is None and self._serial is None:
            self._set_state(ConnectionState.ERROR, str(last_err or "BT open failed"))
            detail = str(last_err) if last_err else "sin detalle"
            if sys.platform == "win32":
                raise RuntimeError(
                    f"No se pudo abrir SPP con {address}.\n"
                    f"Detalle: {detail}\n\n"
                    "En Windows:\n"
                    "1) Emparejá el ESP32 en Configuración → Bluetooth "
                    "(SAJ-PDM30-Edge).\n"
                    "2) Abrí «Más opciones Bluetooth» y comprobá que exista "
                    "un puerto serie (COM) «Standard Serial over Bluetooth».\n"
                    "3) Volvé a Buscar equipos y conectar.\n"
                    "4) Alternativa: modo USB/Serial eligiendo ese COM.\n"
                ) from last_err
            hint_enomem = ""
            if "12" in detail or "Cannot allocate memory" in detail or "ENOMEM" in detail:
                hint_enomem = (
                    "\nENOMEM suele indicar emparejamiento incompleto o scan activo.\n"
                    "Probalo: bluetoothctl → scan off → trust MAC → pair MAC "
                    "(confirmá passkey) → luego conectar de nuevo en la app.\n"
                )
            raise RuntimeError(
                f"No se pudo abrir SPP con {address}.\n"
                f"Detalle: {detail}\n"
                f"{hint_enomem}\n"
                "Comprobá: módulo encendido, BT del PC activo, cerca del PC.\n"
                f"(prep: {prep_note})\n"
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
        # Let banner ("SAJ-PDM30-Edge SPP ready") arrive before host commands
        time.sleep(0.35)

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

    def _recv_chunk(self) -> Optional[bytes]:
        """
        Read some bytes. Returns:
          - bytes: data (may be empty only for serial poll with nothing waiting)
          - None: soft wait (timeout / no data yet) — NOT a disconnect
        Raises OSError on hard socket errors; empty bytes from RFCOMM = peer closed.
        """
        if self._sock is not None:
            try:
                data = self._sock.recv(512)
            except socket.timeout:
                return None  # still connected, just idle
            # RFCOMM: b"" means orderly shutdown by peer
            return data
        if self._serial is not None:
            try:
                n = self._serial.in_waiting
            except Exception:
                n = 0
            if n:
                return self._serial.read(min(n, 512))
            # short non-blocking poll
            b = self._serial.read(1)
            return b if b else None
        return None

    def _rx_loop(self) -> None:
        buf = ""
        while not self._stop.is_set():
            try:
                if self._sock is None and self._serial is None:
                    break
                try:
                    chunk = self._recv_chunk()
                except Exception as e:
                    if not self._stop.is_set():
                        self._emit_error(f"BT RX: {e}")
                    break
                if chunk is None:
                    # idle — keep link open
                    time.sleep(0.02)
                    continue
                if chunk == b"":
                    # only RFCOMM uses empty as EOF; serial returns None when idle
                    if self._sock is not None and not self._stop.is_set():
                        self._emit_error("BT: conexión cerrada por el peer")
                        self._set_state(
                            ConnectionState.DISCONNECTED, "BT peer closed"
                        )
                    break
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
