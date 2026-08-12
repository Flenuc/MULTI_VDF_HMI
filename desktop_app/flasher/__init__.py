"""Firmware flasher GUI — download latest builds from GitHub and flash with esptool."""

from .github_releases import fetch_latest_firmware_index, GithubFirmwareIndex
from .flash_worker import flash_board, list_serial_ports

__all__ = [
    "fetch_latest_firmware_index",
    "GithubFirmwareIndex",
    "flash_board",
    "list_serial_ports",
]
