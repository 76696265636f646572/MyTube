"""Service for checking and installing yt-dlp, ffmpeg, and deno binaries."""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# GitHub release API URLs
YT_DLP_RELEASES_URL = "https://api.github.com/repos/yt-dlp/yt-dlp/releases"
FFMPEG_RELEASES_URL = "https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases"
DENO_RELEASES_URL = "https://api.github.com/repos/denoland/deno/releases"

# Default User-Agent to avoid GitHub rate limiting
GITHUB_UA = "Airwave/1.0 (https://github.com/airwave)"


def _request_json(url: str) -> list[dict[str, Any]]:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": GITHUB_UA})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - trusted GitHub URL
        return json.loads(resp.read().decode())


def _resolve_path(configured: str) -> str:
    """Resolve configured path: if bare name, use which(); else expand user and resolve."""
    if not any(sep in configured for sep in ("/", "\\")):
        resolved = shutil.which(configured)
        return resolved or configured
    expanded = Path(configured).expanduser()
    if not expanded.is_absolute():
        expanded = (Path.cwd() / expanded).resolve()
    return str(expanded)


def _is_managed_path(resolved_path: str) -> bool:
    """True if the binary lives under the project bin/ directory."""
    try:
        resolved = Path(resolved_path).resolve()
        cwd_bin = (Path.cwd() / "bin").resolve()
        return str(resolved).startswith(str(cwd_bin) + os.sep) or resolved == cwd_bin
    except (OSError, ValueError):
        return False


def _run_version(cmd: list[str]) -> str | None:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return None
        return (result.stdout or "").strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _parse_yt_dlp_version(out: str) -> str:
    return out.splitlines()[0].strip() if out else ""


def _parse_ffmpeg_version(out: str) -> str:
    # "ffmpeg version 6.1.1 Copyright..." -> "6.1.1"
    match = re.search(r"ffmpeg version (\S+)", out or "")
    if match:
        try:
            date = re.search(r"(\d{8})", match.group(1))
            if date:
                return datetime.datetime.strptime(date.group(1), "%Y%m%d").strftime("%Y-%m-%d")
            return match.group(1)
        except ValueError:
            return match.group(1)

def _parse_deno_version(out: str) -> str:
    # "deno 2.0.0" or "deno 2.0.0 (release, x86_64-unknown-linux-gnu)"
    match = re.search(r"deno (\d+\.\d+\.\d+)", out or "")
    return match.group(1) if match else (out.splitlines()[0].strip() if out else "")


def _yt_dlp_asset_name() -> str | None:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        if machine in {"x86_64", "amd64"}:
            return "yt-dlp_linux"
        if machine in {"aarch64", "arm64"}:
            return "yt-dlp_linux_aarch64"
        return None
    if system == "darwin":
        return "yt-dlp_macos"
    return None


def _deno_asset_name() -> str | None:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        if machine in {"x86_64", "amd64"}:
            return "deno-x86_64-unknown-linux-gnu.zip"
        if machine in {"aarch64", "arm64"}:
            return "deno-aarch64-unknown-linux-gnu.zip"
        return None
    if system == "darwin":
        if machine in {"x86_64", "amd64"}:
            return "deno-x86_64-apple-darwin.zip"
        if machine in {"aarch64", "arm64"}:
            return "deno-aarch64-apple-darwin.zip"
        return None
    return None


def _ffmpeg_asset_name() -> str | None:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        if machine in {"x86_64", "amd64"}:
            return "ffmpeg-master-latest-linux64-gpl.tar.xz"
        if machine in {"aarch64", "arm64"}:
            return "ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
        return None
    if system == "darwin":
        if machine in {"x86_64", "amd64"}:
            return "ffmpeg-master-latest-macos64-gpl.zip"
        if machine in {"aarch64", "arm64"}:
            return "ffmpeg-master-latest-macosarm64-gpl.zip"
        return None
    return None


@dataclass
class BinaryStatus:
    name: str
    path: str
    version: str
    is_system: bool


@dataclass
class UpdateInfo:
    name: str
    current: str
    latest: str
    has_update: bool


class BinariesService:
    """Service for inspecting and updating yt-dlp, ffmpeg, and deno binaries."""

    def __init__(
        self,
        yt_dlp_path: str,
        ffmpeg_path: str,
        deno_path: str,
    ) -> None:
        self._yt_dlp_configured = yt_dlp_path
        self._ffmpeg_configured = ffmpeg_path
        self._deno_configured = deno_path

    def get_binaries(self) -> list[BinaryStatus]:
        result: list[BinaryStatus] = []
        for name, configured, resolve_fn, parse_fn, version_flag in [
            ("yt-dlp", self._yt_dlp_configured, self._resolve_yt_dlp, _parse_yt_dlp_version, "--version"),
            ("ffmpeg", self._ffmpeg_configured, self._resolve_ffmpeg, _parse_ffmpeg_version, "-version"),
            ("deno", self._deno_configured, self._resolve_deno, _parse_deno_version, "--version"),
        ]:
            path = resolve_fn()
            is_system = not _is_managed_path(path)
            version = ""
            if path:
                out = _run_version([path, version_flag])
                version = parse_fn(out) if out else ""
            result.append(BinaryStatus(name=name, path=path or configured, version=version, is_system=is_system))
        return result

    def _resolve_yt_dlp(self) -> str:
        return _resolve_path(self._yt_dlp_configured)

    def _resolve_ffmpeg(self) -> str:
        expanded = Path(self._ffmpeg_configured).expanduser()
        if expanded.is_absolute() and expanded.exists() and os.access(expanded, os.X_OK):
            return str(expanded)
        if not any(sep in self._ffmpeg_configured for sep in ("/", "\\")):
            resolved = shutil.which(self._ffmpeg_configured)
            return resolved or self._ffmpeg_configured
        if not expanded.is_absolute():
            expanded = (Path.cwd() / expanded).resolve()
        return str(expanded)

    def _resolve_deno(self) -> str:
        return _resolve_path(self._deno_configured)

    def _get_installed_path(self, name: str) -> str:
        if name == "yt-dlp":
            return self._resolve_yt_dlp()
        if name == "ffmpeg":
            return self._resolve_ffmpeg()
        if name == "deno":
            return self._resolve_deno()
        return ""

    def get_updates(self) -> list[UpdateInfo]:
        binaries = {b.name: b for b in self.get_binaries()}
        result: list[UpdateInfo] = []

        # yt-dlp
        cur = binaries.get("yt-dlp")
        latest_yt = self._latest_yt_dlp()
        if latest_yt:
            cur_v = (cur.version if cur else "") or ""
            has = (not cur_v and not (cur and cur.is_system)) or (
                cur_v and not cur.is_system and self._yt_dlp_newer(latest_yt, cur_v)
            )
            result.append(UpdateInfo(name="yt-dlp", current=cur_v or "—", latest=latest_yt, has_update=has))

        # ffmpeg (always allow reinstall for FFmpeg-Builds)
        cur = binaries.get("ffmpeg")
        latest_ff = self._latest_ffmpeg()
        if latest_ff and cur and not cur.is_system:
            # For managed ffmpeg, compare release date vs binary mtime; simplify: always has_update=True if we have latest
            has_update = cur.version != latest_ff
            result.append(
                UpdateInfo(
                    name="ffmpeg",
                    current=cur.version or "—",
                    latest=latest_ff,
                    has_update=has_update,
                )
            )
        elif cur:
            result.append(
                UpdateInfo(name="ffmpeg", current=cur.version or "—", latest=latest_ff or "—", has_update=False)
            )

        # deno
        cur = binaries.get("deno")
        latest_deno = self._latest_deno()
        if latest_deno:
            cur_v = (cur.version if cur else "") or ""
            has = (not cur_v and not (cur and cur.is_system)) or (
                cur_v and not cur.is_system and self._deno_newer(latest_deno, cur_v)
            )
            result.append(UpdateInfo(name="deno", current=cur_v or "—", latest=latest_deno, has_update=has))

        return result

    def _latest_yt_dlp(self) -> str | None:
        try:
            releases = _request_json(f"{YT_DLP_RELEASES_URL}?per_page=5")
            for r in releases:
                if r.get("prerelease"):
                    continue
                tag = r.get("tag_name") or ""
                if tag and re.match(r"^\d{4}\.\d{2}\.\d{2}$", tag):
                    return tag
        except Exception as e:
            logger.warning("Failed to fetch yt-dlp releases: %s", e)
        return None

    def _latest_ffmpeg(self) -> str | None:
        try:
            releases = _request_json(f"{FFMPEG_RELEASES_URL}?per_page=5")
            for r in releases:
                if r.get("tag_name") == "latest":
                    # Use published_at as human-readable "version"
                    pub = r.get("published_at") or ""
                    if pub:
                        return pub[:10]  # YYYY-MM-DD
                    return "latest"
        except Exception as e:
            logger.warning("Failed to fetch FFmpeg-Builds releases: %s", e)
        return None

    def _latest_deno(self) -> str | None:
        try:
            releases = _request_json(f"{DENO_RELEASES_URL}?per_page=5")
            for r in releases:
                if r.get("prerelease"):
                    continue
                tag = r.get("tag_name") or ""
                if tag.startswith("v") and re.match(r"^v\d+\.\d+\.\d+", tag):
                    return tag.lstrip("v")
        except Exception as e:
            logger.warning("Failed to fetch deno releases: %s", e)
        return None

    def _yt_dlp_newer(self, latest: str, current: str) -> bool:
        try:
            l = [int(x) for x in latest.split(".")]
            c = [int(x) for x in current.split(".")]
            for i in range(max(len(l), len(c))):
                a = l[i] if i < len(l) else 0
                b = c[i] if i < len(c) else 0
                if a > b:
                    return True
                if a < b:
                    return False
        except ValueError:
            pass
        return False

    def _deno_newer(self, latest: str, current: str) -> bool:
        def parse(s: str) -> list[int]:
            return [int(x) for x in re.findall(r"\d+", s)[:3]]

        try:
            l = parse(latest)
            c = parse(current)
            for i in range(3):
                a = l[i] if i < len(l) else 0
                b = c[i] if i < len(c) else 0
                if a > b:
                    return True
                if a < b:
                    return False
        except (ValueError, IndexError):
            pass
        return False

    def install(self, name: str) -> None:
        if name == "yt-dlp":
            self._install_yt_dlp()
        elif name == "ffmpeg":
            self._install_ffmpeg()
        elif name == "deno":
            self._install_deno()
        else:
            raise ValueError(f"Unknown binary: {name}")

    def _install_yt_dlp(self) -> None:
        asset = _yt_dlp_asset_name()
        if not asset:
            raise RuntimeError(f"Unsupported platform: {platform.system()} / {platform.machine()}")
        target = _resolve_path(self._yt_dlp_configured)
        if _is_managed_path(target):
            pass
        else:
            raise RuntimeError("Cannot update system-installed yt-dlp")
        releases = _request_json(f"{YT_DLP_RELEASES_URL}?per_page=1")
        tag = None
        for r in releases:
            if not r.get("prerelease"):
                tag = r.get("tag_name")
                break
        if not tag:
            raise RuntimeError("No yt-dlp release found")
        url = f"https://github.com/yt-dlp/yt-dlp/releases/download/{tag}/{asset}"
        _download_file(url, target)

    def _install_deno(self) -> None:
        asset = _deno_asset_name()
        if not asset:
            raise RuntimeError(f"Unsupported platform: {platform.system()} / {platform.machine()}")
        target = _resolve_path(self._deno_configured)
        if not _is_managed_path(target):
            raise RuntimeError("Cannot update system-installed deno")
        releases = _request_json(f"{DENO_RELEASES_URL}?per_page=1")
        tag = None
        for r in releases:
            if not r.get("prerelease") and (r.get("tag_name") or "").startswith("v"):
                tag = r.get("tag_name")
                break
        if not tag:
            raise RuntimeError("No deno release found")
        url = f"https://github.com/denoland/deno/releases/download/{tag}/{asset}"
        with tempfile.TemporaryDirectory(prefix="airwave-deno-") as tmp:
            archive = Path(tmp) / "deno.zip"
            _download_file(url, str(archive))
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(tmp)
            extracted = Path(tmp) / "deno"
            if not extracted.is_file():
                raise RuntimeError("Downloaded archive did not contain deno binary")
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            tmp_target = Path(target).with_suffix(".new")
            shutil.copy2(extracted, tmp_target)
            tmp_target.chmod(tmp_target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            os.replace(tmp_target, target)

    def _install_ffmpeg(self) -> None:
        asset = _ffmpeg_asset_name()
        if not asset:
            raise RuntimeError(f"Unsupported platform: {platform.system()} / {platform.machine()}")
        target = _resolve_path(self._ffmpeg_configured)
        if not _is_managed_path(target):
            raise RuntimeError("Cannot update system-installed ffmpeg")
        url = f"https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/{asset}"
        _download_and_extract_ffmpeg(url, target)

def _download_file(url: str, dest: str) -> None:
    dest_path = Path(dest).expanduser().resolve()
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    req = urllib.request.Request(url, headers={"User-Agent": GITHUB_UA})

    with tempfile.NamedTemporaryFile(dir=dest_path.parent, delete=False) as tmp:
        tmp_path = Path(tmp.name)

        with urllib.request.urlopen(req) as resp:  # noqa: S310
            shutil.copyfileobj(resp, tmp)

    # ensure executable
    tmp_path.chmod(tmp_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # atomic replace
    os.replace(tmp_path, dest_path)

def _download_and_extract_ffmpeg(url: str, target_path: str) -> None:
    target = Path(target_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    suffix = ".zip" if url.lower().endswith(".zip") else ".tar.xz"
    with tempfile.TemporaryDirectory(prefix="airwave-ffmpeg-") as tmp_dir:
        archive_path = Path(tmp_dir) / f"ffmpeg{suffix}"
        req = urllib.request.Request(url, headers={"User-Agent": GITHUB_UA})
        urllib.request.urlretrieve(url, archive_path)  # noqa: S310 - trusted GitHub release URL
        if suffix == ".zip":
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(path=tmp_dir)
        else:
            with tarfile.open(archive_path, mode="r:xz") as tar:
                tar.extractall(path=tmp_dir, filter="data")
        extracted_bin: Path | None = None
        for root, _dirs, files in os.walk(tmp_dir):
            if "ffmpeg" in files:
                candidate = Path(root) / "ffmpeg"
                if "/bin/" in str(candidate).replace("\\", "/"):
                    extracted_bin = candidate
                    break
                extracted_bin = candidate
        if extracted_bin is None:
            raise RuntimeError("Downloaded archive did not contain ffmpeg binary")
        tmp_target = target.with_suffix(".new")
        shutil.copy2(extracted_bin, tmp_target)
        tmp_target.chmod(tmp_target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.replace(tmp_target, target)
