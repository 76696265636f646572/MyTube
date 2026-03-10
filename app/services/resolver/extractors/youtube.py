from __future__ import annotations

from typing import Any

from app.services.resolver.extractors._common import duration_seconds_parse, normalize_upload_date


def _title_from_info(info: dict[str, Any]) -> str | None:
    """YouTube provides title."""
    title = info.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return None


def _thumbnail_from_info(info: dict[str, Any]) -> str | None:
    """YouTube provides a direct thumbnail URL."""
    thumb = info.get("thumbnail")
    if isinstance(thumb, str) and thumb.strip().startswith("http"):
        return thumb.strip()
    return None


def _channel_from_info(info: dict[str, Any]) -> str | None:
    """YouTube uses uploader or channel."""
    channel = info.get("uploader") or info.get("channel")
    if isinstance(channel, str) and channel.strip():
        return channel.strip()
    return None


def _duration_seconds(value: Any) -> int | None:
    return duration_seconds_parse(value)


def _uploaded_at_from_info(info: dict[str, Any]) -> str | None:
    """YouTube: upload_date (YYYYMMDD) or timestamp."""
    return normalize_upload_date(info)


class _YoutubeExtractor:
    title_from_info = staticmethod(_title_from_info)
    thumbnail_from_info = staticmethod(_thumbnail_from_info)
    duration_seconds = staticmethod(_duration_seconds)
    channel_from_info = staticmethod(_channel_from_info)
    uploaded_at_from_info = staticmethod(_uploaded_at_from_info)


youtube_extractor = _YoutubeExtractor()
