from __future__ import annotations

from typing import Any, Protocol

from app.services.resolver.extractors import generic, soundcloud, youtube
from app.services.resolver.extractors._common import duration_seconds_parse

_youtube_extractor = youtube.youtube_extractor
_soundcloud_extractor = soundcloud.soundcloud_extractor
_generic_extractor = generic.generic_extractor


class InfoExtractor(Protocol):
    """Protocol for site-specific yt-dlp info dict extraction."""

    def title_from_info(self, info: dict[str, Any]) -> str | None: ...
    def thumbnail_from_info(self, info: dict[str, Any]) -> str | None: ...
    def duration_seconds(self, value: Any) -> int | None: ...
    def channel_from_info(self, info: dict[str, Any]) -> str | None: ...
    def uploaded_at_from_info(self, info: dict[str, Any]) -> str | None: ...


def get_extractor(info: dict[str, Any]) -> InfoExtractor:
    """Return the extractor for the given yt-dlp info dict (by extractor key)."""
    ext = (info.get("extractor") or info.get("extractor_key") or "").lower()
    if "youtube" in ext:
        return _youtube_extractor
    if "soundcloud" in ext:
        return _soundcloud_extractor
    return _generic_extractor


__all__ = [
    "InfoExtractor",
    "get_extractor",
    "duration_seconds_parse",
    "youtube",
    "soundcloud",
    "generic",
]
