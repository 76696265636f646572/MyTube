from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.services.extractors.base import ResolvedCollection, ResolvedItem, SearchItem


SOUNDCLOUD_HOSTS = {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"}


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _entry_url(entry: dict[str, Any]) -> str | None:
    return (
        entry.get("webpage_url")
        or entry.get("original_url")
        or entry.get("url")
        or entry.get("permalink_url")
    )


def _thumbnail_from_payload(payload: dict[str, Any]) -> str | None:
    thumbnail = payload.get("thumbnail")
    if isinstance(thumbnail, str) and thumbnail:
        return thumbnail
    candidates = payload.get("thumbnails")
    if not isinstance(candidates, list):
        return None
    best_url: str | None = None
    best_score = -1
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        url = candidate.get("url")
        if not isinstance(url, str) or not url:
            continue
        preference = candidate.get("preference")
        width = candidate.get("width")
        height = candidate.get("height")
        score = 0
        if isinstance(preference, (int, float)):
            score += int(preference) * 1_000_000
        if isinstance(width, (int, float)):
            score += int(width)
        if isinstance(height, (int, float)):
            score += int(height)
        if score >= best_score:
            best_score = score
            best_url = url
    return best_url


class SoundCloudExtractor:
    provider = "soundcloud"
    json_keys = {
        "single": (
            "id",
            "title",
            "full_title",
            "uploader",
            "channel",
            "duration",
            "thumbnail",
            "thumbnails[].url",
            "webpage_url",
            "permalink_url",
        ),
        "playlist": (
            "title",
            "uploader",
            "channel",
            "thumbnail",
            "thumbnails[].url",
            "entries[].id",
            "entries[].title",
            "entries[].duration",
            "entries[].webpage_url",
        ),
        "search": (
            "entries[].id",
            "entries[].title",
            "entries[].uploader",
            "entries[].duration",
            "entries[].webpage_url",
            "entries[].thumbnail",
            "entries[].thumbnails[].url",
        ),
    }

    def can_handle(self, url: str) -> bool:
        return urlparse(url).netloc.lower() in SOUNDCLOUD_HOSTS

    def classify_url(self, url: str) -> str:
        path = urlparse(url).path.lower()
        return "playlist" if "/sets/" in path else "single"

    def extract_single(self, url: str, raw_json: dict[str, Any]) -> ResolvedItem:
        source_url = (
            raw_json.get("webpage_url")
            or raw_json.get("original_url")
            or raw_json.get("url")
            or raw_json.get("permalink_url")
            or url
        )
        return ResolvedItem(
            provider=self.provider,
            source_url=source_url,
            normalized_url=source_url,
            title=raw_json.get("title") or raw_json.get("full_title"),
            channel=raw_json.get("uploader") or raw_json.get("channel") or raw_json.get("artist"),
            duration_seconds=_to_int(raw_json.get("duration")),
            thumbnail_url=_thumbnail_from_payload(raw_json),
            provider_item_id=str(raw_json.get("id")) if raw_json.get("id") is not None else None,
            item_type="single",
        )

    def extract_playlist(self, url: str, raw_json: dict[str, Any]) -> ResolvedCollection:
        items: list[ResolvedItem] = []
        for entry in raw_json.get("entries", []):
            if not isinstance(entry, dict):
                continue
            source_url = _entry_url(entry)
            if not source_url:
                continue
            items.append(
                ResolvedItem(
                    provider=self.provider,
                    source_url=source_url,
                    normalized_url=source_url,
                    title=entry.get("title") or entry.get("full_title"),
                    channel=entry.get("uploader") or entry.get("channel") or entry.get("artist"),
                    duration_seconds=_to_int(entry.get("duration")),
                    thumbnail_url=_thumbnail_from_payload(entry),
                    provider_item_id=str(entry.get("id")) if entry.get("id") is not None else None,
                    item_type="playlist_item",
                )
            )
        return ResolvedCollection(
            provider=self.provider,
            source_url=url,
            title=raw_json.get("title"),
            channel=raw_json.get("uploader") or raw_json.get("channel"),
            thumbnail_url=_thumbnail_from_payload(raw_json),
            items=items,
        )

    def extract_search_results(self, raw_json: dict[str, Any]) -> list[SearchItem]:
        results: list[SearchItem] = []
        for entry in raw_json.get("entries", []):
            if not isinstance(entry, dict):
                continue
            source_url = _entry_url(entry)
            if not source_url:
                continue
            results.append(
                SearchItem(
                    provider=self.provider,
                    source_url=source_url,
                    normalized_url=source_url,
                    title=entry.get("title") or entry.get("full_title"),
                    channel=entry.get("uploader") or entry.get("channel"),
                    duration_seconds=_to_int(entry.get("duration")),
                    thumbnail_url=_thumbnail_from_payload(entry),
                    provider_item_id=str(entry.get("id")) if entry.get("id") is not None else None,
                )
            )
        return results
