"""Tests for app.services.binaries_service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.binaries_service import (
    BinariesService,
    _is_managed_path,
    _parse_deno_version,
    _parse_ffmpeg_version,
    _parse_yt_dlp_version,
)


def test_parse_yt_dlp_version():
    assert _parse_yt_dlp_version("2026.03.03") == "2026.03.03"
    assert _parse_yt_dlp_version("2026.03.03\n") == "2026.03.03"
    assert _parse_yt_dlp_version("") == ""
    assert _parse_yt_dlp_version("2025.01.15\nExtra line") == "2025.01.15"


def test_parse_ffmpeg_version():
    assert _parse_ffmpeg_version("ffmpeg version 6.1.1 Copyright (c)") == "6.1.1"
    assert _parse_ffmpeg_version("ffmpeg version n7.0.2-3") == "n7.0.2-3"
    # Git-style version: N-123313-g68046d0b33-20260309 -> date
    assert _parse_ffmpeg_version("ffmpeg version N-123313-g68046d0b33-20260309 Copyright") == "2026-03-09"
    assert _parse_ffmpeg_version("") is None
    assert _parse_ffmpeg_version("no version here") is None


def test_parse_deno_version():
    assert _parse_deno_version("deno 2.0.0") == "2.0.0"
    assert _parse_deno_version("deno 2.0.0 (release, x86_64-unknown-linux-gnu)") == "2.0.0"
    assert _parse_deno_version("") == ""
    assert _parse_deno_version("deno 1.42.0 (canary, x86_64-unknown-linux-gnu)") == "1.42.0"


def test_is_managed_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    managed = bin_dir / "yt-dlp"
    managed.touch()
    assert _is_managed_path(str(managed)) is True
    assert _is_managed_path(str(bin_dir / "ffmpeg")) is True
    # System path (not under cwd/bin)
    assert _is_managed_path("/usr/bin/ffmpeg") is False
    assert _is_managed_path("/usr/local/bin/deno") is False


def test_get_binaries_uses_echo_for_version(tmp_path, monkeypatch):
    """When binary path runs 'echo VERSION', we get that as version output."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Create scripts that echo version-like output
    for name, version_flag, output in [
        ("yt-dlp", "--version", "2026.03.03"),
        ("ffmpeg", "-version", "ffmpeg version 6.1.1 Copyright"),
        ("deno", "--version", "deno 2.0.0"),
    ]:
        script = bin_dir / name
        script.write_text(
            f"#!/bin/sh\necho '{output}'\n",
            encoding="utf-8",
        )
        script.chmod(0o755)

    monkeypatch.chdir(tmp_path)
    svc = BinariesService(
        yt_dlp_path=str(bin_dir / "yt-dlp"),
        ffmpeg_path=str(bin_dir / "ffmpeg"),
        deno_path=str(bin_dir / "deno"),
    )
    binaries = svc.get_binaries()
    assert len(binaries) == 3
    by_name = {b.name: b for b in binaries}
    assert by_name["yt-dlp"].version == "2026.03.03"
    assert by_name["yt-dlp"].is_system is False
    assert by_name["ffmpeg"].version == "6.1.1"
    assert by_name["ffmpeg"].is_system is False
    assert by_name["deno"].version == "2.0.0"
    assert by_name["deno"].is_system is False


def test_get_binaries_detects_system_ffmpeg(monkeypatch):
    """When ffmpeg is resolved via which (e.g. /usr/bin/ffmpeg), is_system is True."""
    monkeypatch.setattr("app.services.binaries_service.shutil.which", lambda x: "/usr/bin/ffmpeg" if x == "ffmpeg" else None)
    # We need a real executable for version - use /bin/echo for the version output
    # Actually which("ffmpeg") returns /usr/bin/ffmpeg - we'd run that. So we need to mock _run_version
    # to avoid actually running system ffmpeg. Or use a tmp script and mock which.
    from app.services import binaries_service as mod

    def fake_run_version(cmd):
        if "ffmpeg" in str(cmd):
            return "ffmpeg version 6.0.1 Copyright"
        return None

    monkeypatch.setattr(mod, "_run_version", fake_run_version)
    svc = BinariesService(yt_dlp_path="/nonexistent/yt-dlp", ffmpeg_path="ffmpeg", deno_path="/nonexistent/deno")
    binaries = svc.get_binaries()
    ffmpeg = next(b for b in binaries if b.name == "ffmpeg")
    assert ffmpeg.path == "/usr/bin/ffmpeg"
    assert ffmpeg.is_system is True


def test_install_raises_for_unknown_binary():
    svc = BinariesService(
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        deno_path="/bin/echo",
    )
    with pytest.raises(ValueError, match="Unknown binary"):
        svc.install("unknown")


def test_install_raises_for_system_ffmpeg(monkeypatch):
    """Install refuses when ffmpeg is resolved to a system path (e.g. /usr/bin/ffmpeg)."""
    monkeypatch.setattr(
        "app.services.binaries_service.shutil.which",
        lambda x: "/usr/bin/ffmpeg" if x == "ffmpeg" else None,
    )
    svc = BinariesService(yt_dlp_path="/bin/echo", ffmpeg_path="ffmpeg", deno_path="/bin/echo")
    with pytest.raises(RuntimeError, match="Cannot update system-installed ffmpeg"):
        svc.install("ffmpeg")


def test_get_updates_mocked_github(tmp_path, monkeypatch):
    """get_updates returns update info when GitHub API is mocked."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, out in [
        ("yt-dlp", "2026.01.01"),
        ("ffmpeg", "ffmpeg version 6.0 Copyright"),
        ("deno", "deno 1.40.0"),
    ]:
        s = bin_dir / name
        s.write_text(f"#!/bin/sh\necho '{out}'\n", encoding="utf-8")
        s.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    svc = BinariesService(
        yt_dlp_path=str(bin_dir / "yt-dlp"),
        ffmpeg_path=str(bin_dir / "ffmpeg"),
        deno_path=str(bin_dir / "deno"),
    )
    with patch.object(svc, "_latest_yt_dlp", return_value="2026.03.03"):
        with patch.object(svc, "_latest_ffmpeg", return_value="2026-03-09"):
            with patch.object(svc, "_latest_deno", return_value="2.0.0"):
                updates = svc.get_updates()
    assert len(updates) >= 2
    yt = next((u for u in updates if u.name == "yt-dlp"), None)
    assert yt is not None
    assert yt.current == "2026.01.01"
    assert yt.latest == "2026.03.03"
    assert yt.has_update is True
