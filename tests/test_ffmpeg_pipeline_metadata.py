from __future__ import annotations

from app.services.ffmpeg_pipeline import FfmpegPipeline


class CapturedProc:
    def __init__(self) -> None:
        self.stdout = None
        self.stderr = None


def test_spawn_for_source_includes_metadata(monkeypatch):
    captured: dict[str, list[str]] = {}

    def fake_popen(cmd, stdin=None, stdout=None, stderr=None):
        _ = (stdin, stdout, stderr)
        captured["cmd"] = cmd
        return CapturedProc()

    monkeypatch.setattr("app.services.ffmpeg_pipeline.subprocess.Popen", fake_popen)
    pipeline = FfmpegPipeline(ffmpeg_path="/usr/bin/ffmpeg")
    pipeline.spawn_for_source(
        "https://example.com/audio",
        metadata={"title": "Song", "artist": "Artist"},
    )

    joined = " ".join(captured["cmd"])
    assert "-metadata title=Song" in joined
    assert "-metadata artist=Artist" in joined


def test_spawn_for_stdin_ignores_empty_metadata(monkeypatch):
    captured: dict[str, list[str]] = {}

    def fake_popen(cmd, stdin=None, stdout=None, stderr=None):
        _ = (stdin, stdout, stderr)
        captured["cmd"] = cmd
        return CapturedProc()

    monkeypatch.setattr("app.services.ffmpeg_pipeline.subprocess.Popen", fake_popen)
    pipeline = FfmpegPipeline(ffmpeg_path="/usr/bin/ffmpeg")
    pipeline.spawn_for_stdin(
        stdin=None,
        metadata={"title": "", "artist": None},
    )

    assert "-metadata" not in " ".join(captured["cmd"])
