from __future__ import annotations

from typing import Any

from app.services.resolver.extractors._common import duration_seconds_parse, normalize_upload_date


def _title_from_info(info: dict[str, Any]) -> str | None:
    """Fallback: title or fulltitle (for Vimeo, Bandcamp, etc.)."""
    title = info.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    full = info.get("fulltitle")
    if isinstance(full, str) and full.strip():
        return full.strip()
    return None


def _thumbnail_from_info(info: dict[str, Any]) -> str | None:
    """Fallback: thumbnail, artwork_url, or thumbnails list."""
    thumb = info.get("thumbnail")
    if isinstance(thumb, str) and thumb.strip().startswith("http"):
        return thumb.strip()
    artwork = info.get("artwork_url")
    if isinstance(artwork, str) and artwork.strip().startswith("http"):
        return artwork.strip()
    thumb_list = info.get("thumbnails")
    if isinstance(thumb_list, list) and thumb_list:
        by_id = {t.get("id"): t for t in thumb_list if isinstance(t, dict) and t.get("url")}
        for preferred in ("t300x300", "large", "t500x500", "small", "badge"):
            if preferred in by_id:
                url = by_id[preferred].get("url")
                if isinstance(url, str) and url.strip().startswith("http"):
                    return url.strip()
        for t in thumb_list:
            if isinstance(t, dict):
                url = t.get("url")
                if isinstance(url, str) and url.strip().startswith("http"):
                    return url.strip()
    return None


def _channel_from_info(info: dict[str, Any]) -> str | None:
    """Fallback: uploader or channel."""
    channel = info.get("uploader") or info.get("channel")
    if isinstance(channel, str) and channel.strip():
        return channel.strip()
    return None


def _duration_seconds(value: Any) -> int | None:
    return duration_seconds_parse(value)


def _uploaded_at_from_info(info: dict[str, Any]) -> str | None:
    """Fallback: upload_date (YYYYMMDD) or timestamp."""
    return normalize_upload_date(info)


class _GenericExtractor:
    title_from_info = staticmethod(_title_from_info)
    thumbnail_from_info = staticmethod(_thumbnail_from_info)
    duration_seconds = staticmethod(_duration_seconds)
    channel_from_info = staticmethod(_channel_from_info)
    uploaded_at_from_info = staticmethod(_uploaded_at_from_info)


generic_extractor = _GenericExtractor()
