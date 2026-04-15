from __future__ import annotations

import json
import re
import subprocess
from typing import IO


class FfmpegError(RuntimeError):
    pass


# ffprobe can hang on bad URLs or stuck I/O; cap wall time so workers do not block indefinitely.
_FFPROBE_RUN_TIMEOUT_SEC = 60


def _ffprobe_timeout_message(
    exc: subprocess.TimeoutExpired,
    *,
    ffprobe_path: str,
    source: str,
) -> str:
    parts = [
        f"ffprobe timed out after {exc.timeout}s",
        f"ffprobe_path={ffprobe_path!r}",
        f"source={source!r}",
    ]
    for label, chunk in (("partial_stdout", exc.stdout), ("partial_stderr", exc.stderr)):
        if not chunk:
            continue
        text = chunk if isinstance(chunk, str) else chunk.decode(errors="replace")
        if len(text) > 2000:
            text = text[:2000] + "..."
        parts.append(f"{label}={text!r}")
    return "; ".join(parts)


def _normalize_ffprobe_tag_dict(tags: object) -> dict[str, str]:
    if not isinstance(tags, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in tags.items():
        if isinstance(key, str) and isinstance(value, str) and value.strip():
            out[key.upper()] = value.strip()
    return out


def _looks_like_audio_stream_codec_label(title: str) -> bool:
    """True when ffprobe stream 'title' is almost certainly a codec layout label, not a song name."""
    t = title.strip()
    if not t:
        return True
    tl = t.lower()
    if re.search(r"\b\d+\.\d+\s*(ch|channels?)\b", tl):
        return True
    codec_markers = (
        "truehd",
        " atmos",
        "atmos",
        "dts-hd",
        "dts hd",
        "dthd",
        "e-ac-3",
        "eac3",
        "ac-3",
        " pcm",
        " pcm_",
        "aac lc",
        "aac-lc",
        "embedded audio",
        "mono track",
        "default (",
    )
    return any(m in tl for m in codec_markers)


class FfmpegPipeline:
    def __init__(self, ffmpeg_path: str, ffprobe_path: str = "ffprobe", bitrate: str = "128k") -> None:
        self.ffmpeg_path = ffmpeg_path
        self._ffprobe_path = ffprobe_path
        self.bitrate = bitrate

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
        ffprobe_exe = self._ffprobe_path
        try:
            completed = subprocess.run(
                [
                    ffprobe_exe,
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
                timeout=_FFPROBE_RUN_TIMEOUT_SEC,
            )
        except OSError as exc:
            raise FfmpegError(
                f"ffprobe binary not found at '{ffprobe_exe}'. "
                "Install ffprobe or set AIRWAVE_FFPROBE_PATH."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise FfmpegError(
                _ffprobe_timeout_message(exc, ffprobe_path=ffprobe_exe, source=source_url)
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

    def probe_audio_streams(self, source: str) -> dict[str, str | float | int | bool | None]:
        """Inspect streams via ffprobe; require at least one audio stream for playable media."""
        ffprobe_exe = self._ffprobe_path
        try:
            completed = subprocess.run(
                [
                    ffprobe_exe,
                    "-v",
                    "error",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    source,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=_FFPROBE_RUN_TIMEOUT_SEC,
            )
        except OSError as exc:
            raise FfmpegError(
                f"ffprobe binary not found at '{ffprobe_exe}'. "
                "Install ffprobe or set AIRWAVE_FFPROBE_PATH."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise FfmpegError(
                _ffprobe_timeout_message(exc, ffprobe_path=ffprobe_exe, source=source)
            ) from exc
        if completed.returncode != 0:
            raise FfmpegError(completed.stderr.strip() or "ffprobe failed")
        try:
            payload = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise FfmpegError("Invalid JSON from ffprobe") from exc
        streams = payload.get("streams")
        if not isinstance(streams, list):
            streams = []
        audio_streams: list[dict[str, object]] = []
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            if stream.get("codec_type") == "audio":
                audio_streams.append(stream)
        format_data = payload.get("format") or {}
        if not isinstance(format_data, dict):
            format_data = {}
        duration_value = format_data.get("duration")
        try:
            duration = float(duration_value) if duration_value is not None else None
        except (TypeError, ValueError):
            duration = None
        format_tags = _normalize_ffprobe_tag_dict(format_data.get("tags"))
        stream_tags: dict[str, str] = {}
        if audio_streams:
            stream_tags = _normalize_ffprobe_tag_dict(audio_streams[0].get("tags"))

        title: str | None = format_tags.get("TITLE") or format_tags.get("TIT2")
        if not title:
            for stream in audio_streams:
                st = _normalize_ffprobe_tag_dict(stream.get("tags"))
                stream_title = st.get("TITLE") or st.get("TIT2")
                if stream_title and not _looks_like_audio_stream_codec_label(stream_title):
                    title = stream_title
                    break

        artist = (
            format_tags.get("ARTIST")
            or format_tags.get("TPE1")
            or format_tags.get("ALBUM_ARTIST")
            or format_tags.get("ALBUMARTIST")
            or stream_tags.get("ARTIST")
            or stream_tags.get("TPE1")
            or stream_tags.get("ALBUM_ARTIST")
            or stream_tags.get("ALBUMARTIST")
        )
        if not artist and len(audio_streams) > 1:
            for stream in audio_streams[1:]:
                st = _normalize_ffprobe_tag_dict(stream.get("tags"))
                artist = st.get("ARTIST") or st.get("TPE1") or st.get("ALBUM_ARTIST") or st.get("ALBUMARTIST")
                if artist:
                    break
        return {
            "has_audio": len(audio_streams) > 0,
            "duration_seconds": duration,
            "audio_stream_count": len(audio_streams),
            "title": title,
            "artist": artist,
            "format_name": format_data.get("format_name") if isinstance(format_data.get("format_name"), str) else None,
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

    def spawn_pcm_for_source(
        self,
        source_url: str,
        start_at_seconds: float = 0.0,
        sample_rate: int = 48000,
        channels: int = 2,
        bit_depth: int = 16,
    ) -> subprocess.Popen[bytes]:
        fmt = f"s{bit_depth}le"
        args: list[str] = []
        if start_at_seconds > 0:
            args.extend(["-ss", f"{float(start_at_seconds):.3f}"])
        args.extend(
            [
                "-i",
                source_url,
                "-vn",
                "-acodec",
                f"pcm_{fmt}",
                "-ar",
                str(sample_rate),
                "-ac",
                str(channels),
                "-f",
                fmt,
                "pipe:1",
            ]
        )
        return self._spawn(args)

    def spawn_pcm_for_stdin(
        self,
        stdin: IO[bytes] | None,
        sample_rate: int = 48000,
        channels: int = 2,
        bit_depth: int = 16,
    ) -> subprocess.Popen[bytes]:
        fmt = f"s{bit_depth}le"
        args = [
            "-i",
            "pipe:0",
            "-vn",
            "-acodec",
            f"pcm_{fmt}",
            "-ar",
            str(sample_rate),
            "-ac",
            str(channels),
            "-f",
            fmt,
            "pipe:1",
        ]
        return self._spawn(args, stdin=stdin)

    def spawn_pcm_silence(
        self,
        sample_rate: int = 48000,
        channels: int = 2,
        bit_depth: int = 16,
    ) -> subprocess.Popen[bytes]:
        fmt = f"s{bit_depth}le"
        layout = "stereo" if channels == 2 else "mono"
        args = [
            "-re",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout={layout}:sample_rate={sample_rate}",
            "-acodec",
            f"pcm_{fmt}",
            "-ar",
            str(sample_rate),
            "-ac",
            str(channels),
            "-f",
            fmt,
            "pipe:1",
        ]
        return self._spawn(args)

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
