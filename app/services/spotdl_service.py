from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.services.yt_dlp_service import PlaylistPreview

from .spotdl_client import SpotdlClient


@dataclass
class SpotdlPlaylistTrack:
    source_url: str
    normalized_url: str
    provider_item_id: str | None
    title: str | None
    channel: str | None
    duration_seconds: int | None
    thumbnail_url: str | None
    search_query: str


@dataclass
class SpotdlPlaylistPreview:
    source_url: str
    title: str | None
    channel: str | None
    thumbnail_url: str | None
    tracks: list[SpotdlPlaylistTrack]

    def as_playlist_preview(self) -> PlaylistPreview:
        return PlaylistPreview(
            provider="spotify",
            source_url=self.source_url,
            title=self.title,
            channel=self.channel,
            thumbnail_url=self.thumbnail_url,
            entries=[
                {
                    "provider": "spotify",
                    "provider_item_id": track.provider_item_id,
                    "source_url": track.source_url,
                    "normalized_url": track.normalized_url,
                    "source_type": "spotify",
                    "title": track.title,
                    "channel": track.channel,
                    "duration_seconds": track.duration_seconds,
                    "thumbnail_url": track.thumbnail_url,
                    "search_query": track.search_query,
                }
                for track in self.tracks
            ],
        )


def _first_string(record: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _duration_to_seconds(value: Any) -> int | None:
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            value = int(value)
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        seconds = int(value)
        if seconds <= 0:
            return None
        if seconds > 10000:
            # Some payloads encode duration in milliseconds.
            return max(1, seconds // 1000)
        return seconds
    return None


def _extract_artist(raw: Any) -> str | None:
    if isinstance(raw, str):
        stripped = raw.strip()
        return stripped or None
    if isinstance(raw, list):
        names: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, dict):
                name = _first_string(item, "name", "artist")
                if name:
                    names.append(name)
        if names:
            return ", ".join(names)
    return None


def _extract_track_id(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    parts = [segment for segment in (parsed.path or "").split("/") if segment]
    if len(parts) >= 2 and parts[0] == "track":
        return parts[1]
    return None


class SpotdlService:
    def __init__(self, binary_path: str) -> None:
        self.client = SpotdlClient(binary_path=binary_path)

    @staticmethod
    def is_spotify_playlist_url(url: str) -> bool:
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        host = (parsed.netloc or "").lower()
        if host not in {"open.spotify.com", "www.open.spotify.com"}:
            return False
        parts = [segment for segment in (parsed.path or "").split("/") if segment]
        return len(parts) >= 2 and parts[0] == "playlist"

    @staticmethod
    def canonical_playlist_url(url: str) -> str:
        parsed = urlparse(url)
        parts = [segment for segment in (parsed.path or "").split("/") if segment]
        if len(parts) >= 2 and parts[0] == "playlist":
            return f"https://open.spotify.com/playlist/{parts[1]}"
        return url

    def preview_playlist(self, url: str) -> SpotdlPlaylistPreview:
        canonical_url = self.canonical_playlist_url(url)
        payload = self.client.fetch_playlist_metadata(canonical_url)
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            raw_entries = []
        tracks: list[SpotdlPlaylistTrack] = []
        for raw in raw_entries:
            if not isinstance(raw, dict):
                continue
            title = _first_string(raw, "name", "title", "song")
            artist = _extract_artist(raw.get("artists")) or _first_string(raw, "artist", "artists")
            source_url = _first_string(
                raw,
                "url",
                "song_url",
                "external_url",
                "spotify_url",
            )
            if not source_url:
                track_id = _first_string(raw, "song_id", "id", "track_id")
                if track_id:
                    source_url = f"https://open.spotify.com/track/{track_id}"
            if not source_url:
                continue
            provider_item_id = _first_string(raw, "song_id", "id", "track_id") or _extract_track_id(source_url)
            normalized_url = (
                f"https://open.spotify.com/track/{provider_item_id}" if provider_item_id else source_url
            )
            duration_seconds = _duration_to_seconds(raw.get("duration")) or _duration_to_seconds(
                raw.get("duration_ms")
            )
            thumbnail_url = _first_string(raw, "cover_url", "thumbnail", "thumbnail_url", "image")
            search_query = " ".join(part for part in [title, artist] if part).strip()
            tracks.append(
                SpotdlPlaylistTrack(
                    source_url=source_url,
                    normalized_url=normalized_url,
                    provider_item_id=provider_item_id,
                    title=title,
                    channel=artist,
                    duration_seconds=duration_seconds,
                    thumbnail_url=thumbnail_url,
                    search_query=search_query or (title or source_url),
                )
            )

        playlist_id = self._playlist_id(canonical_url)
        return SpotdlPlaylistPreview(
            source_url=canonical_url,
            title=f"Spotify playlist {playlist_id}" if playlist_id else "Spotify playlist",
            channel="Spotify",
            thumbnail_url=tracks[0].thumbnail_url if tracks else None,
            tracks=tracks,
        )

    @staticmethod
    def _playlist_id(url: str) -> str | None:
        parsed = urlparse(url)
        parts = [segment for segment in (parsed.path or "").split("/") if segment]
        if len(parts) >= 2 and parts[0] == "playlist":
            return parts[1]
        return None
