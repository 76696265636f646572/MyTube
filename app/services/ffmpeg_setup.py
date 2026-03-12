from __future__ import annotations

import logging
import os
import platform
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _is_executable(path: str) -> bool:
    expanded = Path(path).expanduser()
    return expanded.exists() and os.access(expanded, os.X_OK)


def _asset_url() -> str | None:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        if machine in {"x86_64", "amd64"}:
            return "https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linux64-gpl.tar.xz"
        if machine in {"aarch64", "arm64"}:
            return "https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
        return None
    if system == "darwin":
        if machine in {"x86_64", "amd64"}:
            return "https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-macos64-gpl.zip"
        if machine in {"aarch64", "arm64"}:
            return "https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-macosarm64-gpl.zip"
        return None
    return None


def _download_and_extract_ffmpeg(url: str, target_path: str) -> None:
    target = Path(target_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="airwave-ffmpeg-") as tmp_dir:
        suffix = ".zip" if url.lower().endswith(".zip") else ".tar.xz"
        archive_path = Path(tmp_dir) / f"ffmpeg{suffix}"
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
        shutil.copy2(extracted_bin, target)
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def ensure_ffmpeg_path(configured_path: str, fallback_target: str = "./bin/ffmpeg") -> str:
    if _is_executable(configured_path):
        return configured_path
    resolved = shutil.which(configured_path)
    if resolved:
        return resolved

    url = _asset_url()
    if url is None:
        logger.warning("ffmpeg missing and auto-download unsupported on this platform; set AIRWAVE_FFMPEG_PATH manually")
        return configured_path

    install_target = configured_path if any(sep in configured_path for sep in ("/", "\\")) else fallback_target
    try:
        logger.info("ffmpeg not found, downloading from GitHub release...")
        _download_and_extract_ffmpeg(url, install_target)
        logger.info("ffmpeg installed to %s", install_target)
        return install_target
    except Exception as exc:
        logger.error("Failed to auto-install ffmpeg: %s", exc)
        return configured_path
