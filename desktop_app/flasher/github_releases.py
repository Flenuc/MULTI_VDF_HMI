"""Fetch firmware packages from GitHub Releases (Flenuc/MULTI_VDF_HMI)."""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_REPO = "Flenuc/MULTI_VDF_HMI"
API = "https://api.github.com"
USER_AGENT = "MULTI_VDF_HMI-Flasher/1.0"


@dataclass
class FirmwareFile:
    role: str
    offset: str
    path: str
    size: int = 0
    sha256: str = ""


@dataclass
class BoardPackage:
    id: str
    name: str
    chip: str
    flash_size: str = "4MB"
    flash_mode: str = "dio"
    flash_freq: str = "40m"
    files: List[FirmwareFile] = field(default_factory=list)
    local_dir: Optional[Path] = None  # extracted on disk


@dataclass
class GithubFirmwareIndex:
    version: str
    repo: str
    release_tag: str
    release_url: str
    built_at: str
    firmwares: List[BoardPackage]
    source: str  # "release" | "local"
    zip_name: str = ""
    cache_dir: Optional[Path] = None


def _http_json(url: str, token: str = "") -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_download(url: str, dest: Path, token: str = "", progress=None) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done, total)


def _parse_manifest(data: dict, base_dir: Optional[Path] = None) -> List[BoardPackage]:
    out: List[BoardPackage] = []
    for fw in data.get("firmwares", []):
        files = [
            FirmwareFile(
                role=str(x.get("role", "")),
                offset=str(x.get("offset", "0x0")),
                path=str(x.get("path", "")),
                size=int(x.get("size") or 0),
                sha256=str(x.get("sha256") or ""),
            )
            for x in fw.get("files", [])
        ]
        out.append(
            BoardPackage(
                id=str(fw.get("id", "")),
                name=str(fw.get("name", fw.get("id", ""))),
                chip=str(fw.get("chip", "esp32")),
                flash_size=str(fw.get("flash_size", "4MB")),
                flash_mode=str(fw.get("flash_mode", "dio")),
                flash_freq=str(fw.get("flash_freq", "40m")),
                files=files,
                local_dir=base_dir,
            )
        )
    return out


def load_local_manifest(path: Path) -> GithubFirmwareIndex:
    data = json.loads(path.read_text(encoding="utf-8"))
    base = path.parent
    return GithubFirmwareIndex(
        version=str(data.get("version", "local")),
        repo=str(data.get("repo", DEFAULT_REPO)),
        release_tag="local",
        release_url=str(path),
        built_at=str(data.get("built_at", "")),
        firmwares=_parse_manifest(data, base_dir=base),
        source="local",
        cache_dir=base,
    )


def fetch_latest_firmware_index(
    repo: str = DEFAULT_REPO,
    cache_root: Optional[Path] = None,
    token: str = "",
    prefer_prerelease: bool = False,
    progress=None,
) -> GithubFirmwareIndex:
    """
    Download the newest GitHub Release that contains a firmware zip or manifest.
    Falls back to repo contents path dist/ if no releases exist.
    """
    cache_root = cache_root or (Path.home() / ".cache" / "multi_vdf_hmi" / "firmware")
    cache_root.mkdir(parents=True, exist_ok=True)

    releases = _http_json(f"{API}/repos/{repo}/releases?per_page=15", token=token)
    if not isinstance(releases, list):
        releases = []

    chosen = None
    for rel in releases:
        if rel.get("draft"):
            continue
        if rel.get("prerelease") and not prefer_prerelease:
            # still allow if it's the only one later
            continue
        assets = rel.get("assets") or []
        if any(
            a.get("name", "").endswith(".zip") and "firmware" in a.get("name", "").lower()
            for a in assets
        ) or any(a.get("name") == "manifest.json" for a in assets):
            chosen = rel
            break
    if chosen is None:
        for rel in releases:
            if rel.get("draft"):
                continue
            assets = rel.get("assets") or []
            if assets:
                chosen = rel
                break

    if chosen is None:
        raise RuntimeError(
            f"No hay releases con firmware en github.com/{repo}.\n"
            "Publicá un release (tag vX.Y.Z) con el zip generado por scripts/package_firmware.py\n"
            "o usá «Cargar carpeta local…»."
        )

    tag = str(chosen.get("tag_name") or "unknown")
    version = tag[1:] if tag.startswith("v") else tag
    assets = chosen.get("assets") or []
    zip_asset = None
    man_asset = None
    for a in assets:
        name = a.get("name") or ""
        if name.endswith(".zip") and "firmware" in name.lower():
            zip_asset = a
        if name == "manifest.json":
            man_asset = a

    work = cache_root / version
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    if zip_asset:
        zip_path = cache_root / zip_asset["name"]
        _http_download(
            zip_asset["browser_download_url"],
            zip_path,
            token=token,
            progress=progress,
        )
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(work)
        # manifest may be at root of extracted tree
        man_path = work / "manifest.json"
        if not man_path.is_file():
            # zip may contain version folder
            found = list(work.rglob("manifest.json"))
            if not found:
                raise RuntimeError("El zip de release no incluye manifest.json")
            # if nested, lift contents
            man_path = found[0]
            work = man_path.parent
        data = json.loads(man_path.read_text(encoding="utf-8"))
        firmwares = _parse_manifest(data, base_dir=work)
        return GithubFirmwareIndex(
            version=str(data.get("version") or version),
            repo=str(data.get("repo") or repo),
            release_tag=tag,
            release_url=str(chosen.get("html_url") or ""),
            built_at=str(data.get("built_at") or chosen.get("published_at") or ""),
            firmwares=firmwares,
            source="release",
            zip_name=str(zip_asset.get("name") or ""),
            cache_dir=work,
        )

    if man_asset:
        man_path = work / "manifest.json"
        _http_download(man_asset["browser_download_url"], man_path, token=token, progress=progress)
        data = json.loads(man_path.read_text(encoding="utf-8"))
        # Without zip, user must have board folders hosted somehow — not supported fully
        firmwares = _parse_manifest(data, base_dir=work)
        return GithubFirmwareIndex(
            version=str(data.get("version") or version),
            repo=repo,
            release_tag=tag,
            release_url=str(chosen.get("html_url") or ""),
            built_at=str(data.get("built_at") or ""),
            firmwares=firmwares,
            source="release",
            cache_dir=work,
        )

    raise RuntimeError(f"Release {tag} no tiene assets de firmware (.zip).")
