from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from app.services.extractors.base import ResolvedCollection, ResolvedItem, SearchItem


YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _host(url: str) -> str:
    return urlparse(url).netloc.lower()


def youtube_video_id_from_url(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.netloc.endswith("youtu.be"):
        return (parsed.path or "").strip("/") or None
    if parsed.netloc.lower() in YOUTUBE_HOSTS and "watch" in parsed.path:
        query = parse_qs(parsed.query)
        return (query.get("v") or [None])[0]
    return None


def normalize_single_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.endswith("youtu.be"):
        video_id = parsed.path.lstrip("/")
        return f"https://www.youtube.com/watch?v={video_id}"
    if host in YOUTUBE_HOSTS:
        query = parse_qs(parsed.query)
        video_id = query.get("v", [None])[0]
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
    return url


def normalize_playlist_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.lower() not in YOUTUBE_HOSTS:
        return url
    query = parse_qs(parsed.query)
    playlist_id = query.get("list", [None])[0]
    if not playlist_id:
        return url
    return f"https://www.youtube.com/playlist?{urlencode({'list': playlist_id})}"


def is_start_radio_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc.lower() not in YOUTUBE_HOSTS or "watch" not in parsed.path:
        return False
    query = parse_qs(parsed.query)
    return query.get("start_radio", [None])[0] == "1"


def is_feed_playlists_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc.lower() not in YOUTUBE_HOSTS:
        return False
    return parsed.path.rstrip("/") == "/feed/playlists"


class YouTubeExtractor:
    provider = "youtube"
    json_keys = {
        "single": ("id", "title", "uploader", "channel", "duration", "thumbnail", "webpage_url"),
        "playlist": ("title", "uploader", "channel", "thumbnail", "entries[].id", "entries[].title", "entries[].duration"),
        "search": ("entries[].id", "entries[].title", "entries[].uploader", "entries[].channel", "entries[].duration"),
    }

    def can_handle(self, url: str) -> bool:
        return _host(url) in YOUTUBE_HOSTS

    def classify_url(self, url: str) -> str:
        if is_start_radio_url(url):
            return "playlist"
        if is_feed_playlists_url(url):
            # This is a container of playlists, not a track list playlist.
            return "single"
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if "/playlist" in parsed.path and "list" in query:
            return "playlist"
        return "single"

    def extract_single(self, url: str, raw_json: dict[str, Any]) -> ResolvedItem:
        video_id = raw_json.get("id") or youtube_video_id_from_url(url)
        normalized_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else normalize_single_url(url)
        source_url = raw_json.get("webpage_url") or normalized_url
        return ResolvedItem(
            provider=self.provider,
            source_url=source_url,
            normalized_url=normalized_url,
            title=raw_json.get("title"),
            channel=raw_json.get("uploader") or raw_json.get("channel"),
            duration_seconds=_to_int(raw_json.get("duration")),
            thumbnail_url=raw_json.get("thumbnail"),
            provider_item_id=str(video_id) if video_id else None,
            item_type="single",
        )

    def extract_playlist(self, url: str, raw_json: dict[str, Any]) -> ResolvedCollection:
        items: list[ResolvedItem] = []
        for entry in raw_json.get("entries", []):
            if not isinstance(entry, dict):
                continue
            video_id = entry.get("id")
            if not video_id:
                continue
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            items.append(
                ResolvedItem(
                    provider=self.provider,
                    source_url=watch_url,
                    normalized_url=watch_url,
                    title=entry.get("title"),
                    channel=entry.get("uploader") or entry.get("channel"),
                    duration_seconds=_to_int(entry.get("duration")),
                    thumbnail_url=entry.get("thumbnail"),
                    provider_item_id=str(video_id),
                    item_type="playlist_item",
                )
            )
        return ResolvedCollection(
            provider=self.provider,
            source_url=url if is_start_radio_url(url) else normalize_playlist_url(url),
            title=raw_json.get("title"),
            channel=raw_json.get("uploader") or raw_json.get("channel"),
            thumbnail_url=raw_json.get("thumbnail"),
            items=items,
        )

    def extract_search_results(self, raw_json: dict[str, Any]) -> list[SearchItem]:
        results: list[SearchItem] = []
        for entry in raw_json.get("entries", []):
            if not isinstance(entry, dict):
                continue
            video_id = entry.get("id")
            if not video_id:
                continue
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            results.append(
                SearchItem(
                    provider=self.provider,
                    source_url=watch_url,
                    normalized_url=watch_url,
                    title=entry.get("title"),
                    channel=entry.get("uploader") or entry.get("channel"),
                    duration_seconds=_to_int(entry.get("duration")),
                    thumbnail_url=entry.get("thumbnail"),
                    provider_item_id=str(video_id),
                )
            )
        return results
