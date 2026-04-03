from __future__ import annotations

from pathlib import Path

import app.services.ffmpeg_pipeline as ffmpeg_pipeline
import app.services.ffmpeg_setup as ffmpeg_setup
import pytest


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


def test_probe_source_uses_configured_ffprobe_path(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return ffmpeg_pipeline.subprocess.CompletedProcess(args=args, returncode=0, stdout='{"format":{}}', stderr="")

    monkeypatch.setattr(ffmpeg_pipeline.subprocess, "run", fake_run)

    pipeline = ffmpeg_pipeline.FfmpegPipeline(
        "/usr/bin/ffmpeg",
        ffprobe_path="/opt/tools/ffprobe",
    )
    result = pipeline.probe_source("https://example.test/audio.mp3")

    assert captured["args"][0] == "/opt/tools/ffprobe"
    assert captured["kwargs"]["timeout"] == ffmpeg_pipeline._FFPROBE_RUN_TIMEOUT_SEC  # noqa: SLF001
    assert result["duration_seconds"] is None
    assert result["bit_rate"] is None
    assert result["format_name"] is None


def test_probe_source_ffprobe_timeout_includes_path_and_partial_output(monkeypatch):
    def fake_run(_args, **_kwargs):
        raise ffmpeg_pipeline.subprocess.TimeoutExpired(
            cmd=["/opt/tools/ffprobe"],
            timeout=ffmpeg_pipeline._FFPROBE_RUN_TIMEOUT_SEC,  # noqa: SLF001
            output="partial stdout",
            stderr="partial stderr",
        )

    monkeypatch.setattr(ffmpeg_pipeline.subprocess, "run", fake_run)
    pipeline = ffmpeg_pipeline.FfmpegPipeline("/usr/bin/ffmpeg", ffprobe_path="/opt/tools/ffprobe")

    with pytest.raises(ffmpeg_pipeline.FfmpegError) as excinfo:
        pipeline.probe_source("https://example.test/audio.mp3")

    msg = str(excinfo.value)
    assert "ffprobe timed out" in msg
    assert "ffprobe_path='/opt/tools/ffprobe'" in msg
    assert "source='https://example.test/audio.mp3'" in msg
    assert "partial_stdout='partial stdout'" in msg
    assert "partial_stderr='partial stderr'" in msg


def test_probe_source_ffprobe_missing_mentions_airwave_ffprobe_path(monkeypatch):
    def fake_run(_args, **_kwargs):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(ffmpeg_pipeline.subprocess, "run", fake_run)
    pipeline = ffmpeg_pipeline.FfmpegPipeline("/usr/bin/ffmpeg", ffprobe_path="/opt/tools/ffprobe")

    with pytest.raises(ffmpeg_pipeline.FfmpegError) as excinfo:
        pipeline.probe_source("https://example.test/audio.mp3")

    msg = str(excinfo.value)
    assert "ffprobe binary not found at '/opt/tools/ffprobe'" in msg
    assert "AIRWAVE_FFPROBE_PATH" in msg
