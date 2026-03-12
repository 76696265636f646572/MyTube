from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse


def youtube_video_id_from_url(url: str) -> str | None:
    """Extract YouTube video id from a watch URL or youtu.be URL. Returns None if not a video URL."""
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.netloc.endswith("youtu.be"):
        return (parsed.path or "").strip("/") or None
    if "youtube.com" in parsed.netloc and "watch" in parsed.path:
        query = parse_qs(parsed.query)
        return (query.get("v") or [None])[0]
    return None


class YtDlpError(RuntimeError):
    pass


@dataclass
class ResolvedTrack:
    source_url: str
    normalized_url: str
    title: str | None
    channel: str | None
    duration_seconds: int | None
    thumbnail_url: str | None
    stream_url: str


@dataclass
class PlaylistPreview:
    source_url: str
    title: str | None
    channel: str | None
    entries: list[dict[str, Any]]
    thumbnail_url: str | None = None


class YtDlpService:
    def __init__(self, binary_path: str) -> None:
        self.binary_path = binary_path

    def normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.netloc.endswith("youtu.be"):
            video_id = parsed.path.lstrip("/")
            return f"https://www.youtube.com/watch?v={video_id}"
        if "youtube.com" in parsed.netloc:
            query = parse_qs(parsed.query)
            video_id = query.get("v", [None])[0]
            if video_id:
                return f"https://www.youtube.com/watch?v={video_id}"
            playlist_id = query.get("list", [None])[0]
            if playlist_id:
                return f"https://www.youtube.com/playlist?list={playlist_id}"
        return url

    def is_start_radio_url(self, url: str) -> bool:
        """True for YouTube watch URLs with start_radio=1 (mix/radio)."""
        parsed = urlparse(url)
        if "youtube.com" not in parsed.netloc or "watch" not in parsed.path:
            return False
        query = parse_qs(parsed.query)
        return query.get("start_radio", [None])[0] == "1"

    def is_playlist_url(self, url: str) -> bool:
        """True for playlist page URLs (playlist?list=...) or watch URLs with start_radio=1."""
        if self.is_start_radio_url(url):
            return True
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        return "/playlist" in parsed.path and "list" in query

    def _run_json(self, *args: str) -> dict[str, Any]:
        cmd = [self.binary_path, *args]
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise YtDlpError(completed.stderr.strip() or "yt-dlp failed")
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise YtDlpError("Invalid JSON from yt-dlp") from exc

    def spawn_audio_stream(self, url: str) -> subprocess.Popen[bytes]:
        normalized = self.normalize_url(url)
        cmd = [
            self.binary_path,
            "--no-playlist",
            "-f",
            "bestaudio/best",
            "--no-progress",
            "--quiet",
            "-o",
            "-",
            normalized,
        ]
        try:
            return subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise YtDlpError(
                f"yt-dlp binary not found at '{self.binary_path}'. "
                "Install yt-dlp or set AIRWAVE_YT_DLP_PATH."
            ) from exc

    def resolve_video(self, url: str) -> ResolvedTrack:
        normalized = self.normalize_url(url)
        data = self._run_json(
            "--no-playlist",
            "-f",
            "bestaudio/best",
            "--skip-download",
            "-J",
            normalized,
        )
        direct_url = data.get("url")
        if not direct_url:
            raise YtDlpError("Could not resolve direct stream URL")
        return ResolvedTrack(
            source_url=url,
            normalized_url=normalized,
            title=data.get("title"),
            channel=data.get("uploader") or data.get("channel"),
            duration_seconds=data.get("duration"),
            thumbnail_url=data.get("thumbnail"),
            stream_url=direct_url,
        )

    def preview_playlist(self, url: str) -> PlaylistPreview:
        url_for_ytdlp = url if self.is_start_radio_url(url) else self.normalize_url(url)
        data = self._run_json(
            "--flat-playlist",
            "--skip-download",
            "-J",
            url_for_ytdlp,
        )
        entries: list[dict[str, Any]] = []
        for entry in data.get("entries", []):
            if not isinstance(entry, dict):
                continue
            video_id = entry.get("id")
            if not video_id:
                continue
            entries.append(
                {
                    "source_url": f"https://www.youtube.com/watch?v={video_id}",
                    "normalized_url": f"https://www.youtube.com/watch?v={video_id}",
                    "title": entry.get("title"),
                    "channel": entry.get("uploader") or entry.get("channel"),
                    "duration_seconds": entry.get("duration"),
                    "thumbnail_url": None,
                }
            )
        return PlaylistPreview(
            source_url=url_for_ytdlp,
            title=data.get("title"),
            channel=data.get("uploader") or data.get("channel"),
            entries=entries,
            thumbnail_url=data.get("thumbnail"),
        )

    def search_videos(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 25))
        payload = self._run_json("--flat-playlist", "--skip-download", "-J", f"ytsearch{bounded_limit}:{query}")
        results: list[dict[str, Any]] = []
        for entry in payload.get("entries", []):
            if not isinstance(entry, dict):
                continue
            video_id = entry.get("id")
            if not video_id:
                continue
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            results.append(
                {
                    "id": video_id,
                    "source_url": watch_url,
                    "normalized_url": watch_url,
                    "title": entry.get("title"),
                    "channel": entry.get("uploader") or entry.get("channel"),
                    "duration_seconds": entry.get("duration"),
                    "thumbnail_url": None,
                }
            )
        return results
