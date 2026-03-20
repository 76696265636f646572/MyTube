from __future__ import annotations

from pathlib import Path

import app.services.ffmpeg_pipeline as ffmpeg_pipeline
import app.services.ffmpeg_setup as ffmpeg_setup


def test_asset_url_supports_darwin(monkeypatch):
    monkeypatch.setattr(ffmpeg_setup.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(ffmpeg_setup.platform, "machine", lambda: "arm64")
    assert ffmpeg_setup._asset_url().endswith("macosarm64-gpl.zip")  # noqa: SLF001


def test_ensure_ffmpeg_path_returns_existing_binary(tmp_path):
    existing = tmp_path / "ffmpeg"
    existing.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    existing.chmod(0o755)
    assert ffmpeg_setup.ensure_ffmpeg_path(str(existing)) == str(existing)


def test_ensure_ffmpeg_path_downloads_when_missing(monkeypatch, tmp_path):
    target = tmp_path / "bin" / "ffmpeg"

    monkeypatch.setattr(ffmpeg_setup, "_is_executable", lambda _path: False)
    monkeypatch.setattr(ffmpeg_setup.shutil, "which", lambda _name: None)
    monkeypatch.setattr(ffmpeg_setup, "_asset_url", lambda: "https://example.com/ffmpeg.tar.xz")

    def fake_download(_url: str, target_path: str) -> None:
        out = Path(target_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        out.chmod(0o755)

    monkeypatch.setattr(ffmpeg_setup, "_download_and_extract_ffmpeg", fake_download)

    resolved = ffmpeg_setup.ensure_ffmpeg_path("ffmpeg", fallback_target=str(target))
    assert resolved == str(target)
    assert target.exists()


def test_ensure_ffmpeg_path_falls_back_on_download_failure(monkeypatch):
    monkeypatch.setattr(ffmpeg_setup, "_is_executable", lambda _path: False)
    monkeypatch.setattr(ffmpeg_setup.shutil, "which", lambda _name: None)
    monkeypatch.setattr(ffmpeg_setup, "_asset_url", lambda: "https://example.com/ffmpeg.tar.xz")

    def fail_download(_url: str, _target_path: str) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(ffmpeg_setup, "_download_and_extract_ffmpeg", fail_download)
    assert ffmpeg_setup.ensure_ffmpeg_path("ffmpeg") == "ffmpeg"


def test_spawn_silence_uses_real_time_lavfi_input(monkeypatch):
    captured: dict[str, object] = {}

    class DummyProc:
        pass

    def fake_popen(args, stdin=None, stdout=None, stderr=None):
        captured["args"] = args
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        return DummyProc()

    monkeypatch.setattr(ffmpeg_pipeline.subprocess, "Popen", fake_popen)

    pipeline = ffmpeg_pipeline.FfmpegPipeline("/usr/bin/ffmpeg", bitrate="192k")
    process = pipeline.spawn_silence()

    assert isinstance(process, DummyProc)
    assert captured["args"] == [
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "warning",
        "-re",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-acodec",
        "libmp3lame",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-b:a",
        "192k",
        "-f",
        "mp3",
        "pipe:1",
    ]
    assert captured["stdin"] is None
    assert captured["stdout"] == ffmpeg_pipeline.subprocess.PIPE
    assert captured["stderr"] == ffmpeg_pipeline.subprocess.PIPE
