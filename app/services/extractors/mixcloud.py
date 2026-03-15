from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.services.extractors.base import ResolvedCollection, ResolvedItem, SearchItem


MIXCLOUD_HOSTS = {"mixcloud.com", "www.mixcloud.com", "m.mixcloud.com"}


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class MixcloudExtractor:
    provider = "mixcloud"
    json_keys = {
        "single": (
            "id",
            "title",
            "uploader",
            "channel",
            "duration",
            "thumbnail",
            "webpage_url",
            "original_url",
        ),
    }

    def can_handle(self, url: str) -> bool:
        return urlparse(url).netloc.lower() in MIXCLOUD_HOSTS

    def classify_url(self, url: str) -> str:
        # Mixcloud support is intentionally scoped to single shows.
        return "single"

    def extract_single(self, url: str, raw_json: dict[str, Any]) -> ResolvedItem:
        source_url = raw_json.get("webpage_url") or raw_json.get("original_url") or raw_json.get("url") or url
        return ResolvedItem(
            provider=self.provider,
            source_url=source_url,
            normalized_url=source_url,
            title=raw_json.get("title") or raw_json.get("full_title"),
            channel=raw_json.get("uploader") or raw_json.get("channel") or raw_json.get("artist"),
            duration_seconds=_to_int(raw_json.get("duration")),
            thumbnail_url=raw_json.get("thumbnail"),
            provider_item_id=str(raw_json.get("id")) if raw_json.get("id") is not None else None,
            item_type="single",
        )

    def extract_playlist(self, url: str, raw_json: dict[str, Any]) -> ResolvedCollection:
        raise NotImplementedError("Mixcloud playlist/collection extraction is not supported")

    def extract_search_results(self, raw_json: dict[str, Any]) -> list[SearchItem]:
        # yt-dlp support for Mixcloud search is inconsistent; we currently return no normalized results.
        return []
