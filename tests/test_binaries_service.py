"""Tests for app.services.binaries_service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.binaries_service import (
    BinariesService,
    _html_subsection_after_h3,
    _is_managed_path,
    _martin_riedl_release_section_html,
    _mr_release_numeric_newer,
    _mr_release_version_from_subsection,
    _parse_deno_version,
    _parse_ffprobe_version,
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


def test_parse_ffprobe_version():
    assert _parse_ffprobe_version("ffprobe version 6.1.1 Copyright (c)") == "6.1.1"
    assert _parse_ffprobe_version("ffprobe version N-123313-g68046d0b33-20260309 Copyright") == "2026-03-09"
    assert (
        _parse_ffprobe_version("ffprobe version 8.1-https://www.martin-riedl.de Copyright")
        == "8.1"
    )
    assert _parse_ffprobe_version("") is None
    assert _parse_ffprobe_version("no version here") is None


def test_martin_riedl_release_section_and_linux_amd64_version():
    html = """
    <body>
    <h2>Download Snapshot Build</h2>
    <h3>Linux (amd64)</h3>
    <p><b>Release: </b>should-not-use</p>
    <h2>Download Release Build</h2>
    <h3>Linux (amd64)</h3>
    <p><b>Release: </b>8.1</p>
    <a href="/download/linux/amd64/1774550169_8.1/ffprobe.zip">FFprobe (ZIP)</a>
    <h2>Timeline for macOS</h2>
    </body>
    """
    section = _martin_riedl_release_section_html(html)
    assert section is not None
    assert "should-not-use" not in section
    sub = _html_subsection_after_h3(section, "Linux (amd64)")
    assert _mr_release_version_from_subsection(sub) == "8.1"


def test_martin_riedl_release_version_from_ffprobe_zip_href_only():
    sub = '<a href="https://ffmpeg.martin-riedl.de/download/linux/arm64/1774548896_8.1/ffprobe.zip">x</a>'
    assert _mr_release_version_from_subsection(sub) == "8.1"


def test_mr_release_numeric_newer():
    assert _mr_release_numeric_newer("8.1", "8.0") is True
    assert _mr_release_numeric_newer("8.0", "8.1") is False
    assert _mr_release_numeric_newer("8.1", "8.1") is False
    assert _mr_release_numeric_newer("8.10", "8.9") is True
    assert _mr_release_numeric_newer("2026-03-09", "8.1") is False


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
        ("ffprobe", "-version", "ffprobe version 6.1.1 Copyright"),
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
        ffprobe_path=str(bin_dir / "ffprobe"),
        deno_path=str(bin_dir / "deno"),
    )
    binaries = svc.get_binaries()
    assert len(binaries) == 4
    by_name = {b.name: b for b in binaries}
    assert by_name["yt-dlp"].version == "2026.03.03"
    assert by_name["yt-dlp"].is_system is False
    assert by_name["ffmpeg"].version == "6.1.1"
    assert by_name["ffmpeg"].is_system is False
    assert by_name["ffprobe"].version == "6.1.1"
    assert by_name["ffprobe"].is_system is False
    assert by_name["deno"].version == "2.0.0"
    assert by_name["deno"].is_system is False


def test_get_binaries_detects_system_ffmpeg(monkeypatch):
    """When ffmpeg is resolved via which (e.g. /usr/bin/ffmpeg), is_system is True."""
    monkeypatch.setattr(
        "app.services.binaries_service.shutil.which",
        lambda x: "/usr/bin/ffmpeg" if x == "ffmpeg" else ("/usr/bin/ffprobe" if x == "ffprobe" else None),
    )
    # We need a real executable for version - use /bin/echo for the version output
    # Actually which("ffmpeg") returns /usr/bin/ffmpeg - we'd run that. So we need to mock _run_version
    # to avoid actually running system ffmpeg. Or use a tmp script and mock which.
    from app.services import binaries_service as mod

    def fake_run_version(cmd):
        cmd_s = " ".join(str(c) for c in cmd)
        if "ffmpeg" in cmd_s and cmd[-1] == "-version":
            return "ffmpeg version 6.0.1 Copyright"
        if "ffprobe" in cmd_s and cmd[-1] == "-version":
            return "ffprobe version 6.0.1 Copyright"
        return None

    monkeypatch.setattr(mod, "_run_version", fake_run_version)
    svc = BinariesService(
        yt_dlp_path="/nonexistent/yt-dlp",
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        deno_path="/nonexistent/deno",
    )
    binaries = svc.get_binaries()
    ffmpeg = next(b for b in binaries if b.name == "ffmpeg")
    assert ffmpeg.path == "/usr/bin/ffmpeg"
    assert ffmpeg.is_system is True
    ffprobe = next(b for b in binaries if b.name == "ffprobe")
    assert ffprobe.path == "/usr/bin/ffprobe"
    assert ffprobe.version == "6.0.1"
    assert ffprobe.is_system is True


def test_install_raises_for_unknown_binary():
    svc = BinariesService(
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        ffprobe_path="/bin/echo",
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
    svc = BinariesService(
        yt_dlp_path="/bin/echo",
        ffmpeg_path="ffmpeg",
        ffprobe_path="/bin/echo",
        deno_path="/bin/echo",
    )
    with pytest.raises(RuntimeError, match="Cannot update system-installed ffmpeg"):
        svc.install("ffmpeg")


def test_get_updates_mocked_github(tmp_path, monkeypatch):
    """get_updates returns update info when GitHub API is mocked."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, out in [
        ("yt-dlp", "2026.01.01"),
        ("ffmpeg", "ffmpeg version 6.0 Copyright"),
        ("ffprobe", "ffprobe version 6.0 Copyright"),
        ("deno", "deno 1.40.0"),
    ]:
        s = bin_dir / name
        s.write_text(f"#!/bin/sh\necho '{out}'\n", encoding="utf-8")
        s.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    svc = BinariesService(
        yt_dlp_path=str(bin_dir / "yt-dlp"),
        ffmpeg_path=str(bin_dir / "ffmpeg"),
        ffprobe_path=str(bin_dir / "ffprobe"),
        deno_path=str(bin_dir / "deno"),
    )
    with patch.object(svc, "_latest_yt_dlp", return_value="2026.03.03"):
        with patch.object(svc, "_latest_ffmpeg", return_value="2026-03-09"):
            with patch.object(svc, "_latest_martin_riedl_ffprobe_release", return_value="6.0"):
                with patch.object(svc, "_latest_deno", return_value="2.0.0"):
                    updates = svc.get_updates()
    assert len(updates) >= 2
    ffprobe_u = next((u for u in updates if u.name == "ffprobe"), None)
    assert ffprobe_u is not None
    assert ffprobe_u.current == "6.0"
    assert ffprobe_u.latest == "6.0"
    assert ffprobe_u.has_update is False
    yt = next((u for u in updates if u.name == "yt-dlp"), None)
    assert yt is not None
    assert yt.current == "2026.01.01"
    assert yt.latest == "2026.03.03"
    assert yt.has_update is True
