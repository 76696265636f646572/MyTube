from __future__ import annotations

import json
import os
import subprocess
from typing import IO


class FfmpegError(RuntimeError):
    pass


class FfmpegPipeline:
    def __init__(self, ffmpeg_path: str, bitrate: str = "128k") -> None:
        self.ffmpeg_path = ffmpeg_path
        self.bitrate = bitrate

    def _ffprobe_path(self) -> str:
        ffmpeg_dir = os.path.dirname(self.ffmpeg_path)
        return os.path.join(ffmpeg_dir, "ffprobe") if ffmpeg_dir else "ffprobe"

    def _spawn(self, args: list[str], *, stdin: int | IO[bytes] | None = None) -> subprocess.Popen[bytes]:
        try:
            return subprocess.Popen(
                [self.ffmpeg_path, "-hide_banner", "-nostats", "-loglevel", "warning", *args],
                stdin=stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise FfmpegError(
                f"ffmpeg binary not found at '{self.ffmpeg_path}'. "
                "Install ffmpeg or set AIRWAVE_FFMPEG_PATH."
            ) from exc

    def probe_source(self, source_url: str) -> dict[str, str | float | None]:
        try:
            completed = subprocess.run(
                [
                    self._ffprobe_path(),
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration,bit_rate,format_name",
                    "-of",
                    "json",
                    source_url,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise FfmpegError(
                f"ffprobe binary not found next to '{self.ffmpeg_path}'. "
                "Install ffprobe or set AIRWAVE_FFMPEG_PATH to a full ffmpeg suite."
            ) from exc
        if completed.returncode != 0:
            raise FfmpegError(completed.stderr.strip() or "ffprobe failed")
        try:
            payload = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise FfmpegError("Invalid JSON from ffprobe") from exc
        format_data = payload.get("format") or {}
        duration_value = format_data.get("duration")
        bit_rate_value = format_data.get("bit_rate")
        try:
            duration = float(duration_value) if duration_value is not None else None
        except (TypeError, ValueError):
            duration = None
        try:
            bit_rate = float(bit_rate_value) if bit_rate_value is not None else None
        except (TypeError, ValueError):
            bit_rate = None
        return {
            "duration_seconds": duration,
            "bit_rate": bit_rate,
            "format_name": format_data.get("format_name"),
        }

    def spawn_for_source(self, source_url: str, start_at_seconds: float = 0.0) -> subprocess.Popen[bytes]:
        args: list[str] = ["-re"]
        if start_at_seconds > 0:
            args.extend(["-ss", f"{float(start_at_seconds):.3f}"])
        args.extend(
            [
                "-i",
                source_url,
                "-vn",
                "-acodec",
                "libmp3lame",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-b:a",
                self.bitrate,
                "-f",
                "mp3",
                "pipe:1",
            ]
        )
        return self._spawn(args)

    def spawn_for_stdin(self, stdin: IO[bytes] | None) -> subprocess.Popen[bytes]:
        args = [
            "-re",
            "-i",
            "pipe:0",
            "-vn",
            "-acodec",
            "libmp3lame",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            self.bitrate,
            "-f",
            "mp3",
            "pipe:1",
        ]
        return self._spawn(args, stdin=stdin)

    def spawn_silence(self) -> subprocess.Popen[bytes]:
        args = [
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
            self.bitrate,
            "-f",
            "mp3",
            "pipe:1",
        ]
        return self._spawn(args)

    @staticmethod
    def read_chunk(stdout: IO[bytes] | None, chunk_size: int) -> bytes:
        if stdout is None:
            return b""
        return stdout.read(chunk_size)
