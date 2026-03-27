from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

SPOTIFY_PLAYLIST_HOSTS = frozenset({"open.spotify.com", "www.spotify.com"})


def is_spotify_playlist_url(url: str) -> bool:
    return spotify_playlist_id_from_url(url) is not None


def spotify_playlist_id_from_url(url: str) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    try:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    except Exception:
        return None
    host = (parsed.hostname or "").lower()
    if host not in SPOTIFY_PLAYLIST_HOSTS:
        return None
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2 or parts[0].lower() != "playlist":
        return None
    playlist_id = parts[1].split("?")[0].strip()
    return playlist_id or None


def normalize_spotify_playlist_url(playlist_id: str) -> str:
    return f"https://open.spotify.com/playlist/{playlist_id}"


def _first_url_from_image_sources(sources: Any) -> str | None:
    if not isinstance(sources, list):
        return None
    for src in sources:
        if isinstance(src, dict) and src.get("url"):
            return str(src["url"])
    return None


def _playlist_cover_url(meta: dict[str, Any]) -> str | None:
    """Cover art from SpotipyFree playlist() (playlistV2 / GraphQL-shaped) response."""
    images = meta.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            if first.get("url"):
                return str(first["url"])
            return _first_url_from_image_sources(first.get("sources"))

    if isinstance(images, dict):
        items = images.get("items")
        if isinstance(items, list) and items:
            last = items[-1]
            if isinstance(last, dict):
                u = _first_url_from_image_sources(last.get("sources"))
                if u:
                    return u

    vi = meta.get("visualIdentity")
    if isinstance(vi, dict):
        sq = vi.get("squareCoverImage")
        if isinstance(sq, dict):
            img = sq.get("image")
            if isinstance(img, dict):
                data = img.get("data")
                if isinstance(data, dict):
                    u = _first_url_from_image_sources(data.get("sources"))
                    if u:
                        return u
    return None


def _playlist_owner_display(meta: dict[str, Any]) -> str | None:
    owner = meta.get("owner")
    if isinstance(owner, dict):
        return owner.get("display_name") or owner.get("name")
    return None


def _album_thumb_from_track(track: dict[str, Any]) -> str | None:
    album = track.get("album")
    if isinstance(album, dict):
        images = album.get("images")
        if isinstance(images, list) and images:
            im0 = images[0]
            if isinstance(im0, dict) and im0.get("url"):
                return str(im0["url"])
        if album.get("coverArt"):
            return _first_url_from_image_sources((album.get("coverArt") or {}).get("sources"))
    return None


def _duration_seconds_from_track(track: dict[str, Any]) -> int | None:
    ms = track.get("duration_ms")
    if isinstance(ms, (int, float)):
        return max(0, int(ms // 1000))
    td = track.get("trackDuration") or {}
    if isinstance(td, dict):
        ms2 = td.get("totalMilliseconds")
        if isinstance(ms2, (int, float)):
            return max(0, int(ms2 // 1000))
    return None


def _artist_names_from_track(track: dict[str, Any]) -> str | None:
    artists = track.get("artists")
    if not isinstance(artists, list):
        return None
    names: list[str] = []
    for a in artists:
        if not isinstance(a, dict):
            continue
        n = a.get("name")
        if not n and isinstance(a.get("profile"), dict):
            n = a["profile"].get("name")
        if n:
            names.append(str(n))
    return ", ".join(names) if names else None


def _row_from_wrapped_item(wrap: dict[str, Any]) -> dict[str, Any] | None:
    """Parse one playlist item from playlist_items() shape: { \"track\": { ... } }."""
    track = wrap.get("track")
    if not isinstance(track, dict) or not track.get("id"):
        return None
    tid = str(track["id"])
    return {
        "spotify_track_id": tid,
        "title": track.get("name"),
        "channel": _artist_names_from_track(track),
        "duration_seconds": _duration_seconds_from_track(track),
        "thumbnail_url": _album_thumb_from_track(track),
    }


def _rows_from_playlist_content(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse tracks embedded in playlist() under content.items (GraphQL itemV2/itemV3)."""
    content = meta.get("content")
    if not isinstance(content, dict):
        return []
    items = content.get("items")
    if not isinstance(items, list):
        return []
    rows: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        track_data = None
        item_v2 = row.get("itemV2")
        if isinstance(item_v2, dict):
            inner = item_v2.get("data")
            if isinstance(inner, dict) and inner.get("__typename") == "Track":
                track_data = inner
        if track_data is None:
            continue
        uri = track_data.get("uri") or ""
        prefix = "spotify:track:"
        tid = uri[len(prefix) :] if uri.startswith(prefix) else None
        if not tid:
            continue
        names: list[str] = []
        artists_block = track_data.get("artists")
        if isinstance(artists_block, dict):
            for a in artists_block.get("items") or []:
                if isinstance(a, dict):
                    prof = a.get("profile")
                    if isinstance(prof, dict) and prof.get("name"):
                        names.append(str(prof["name"]))
        duration_ms = None
        td = track_data.get("trackDuration")
        if isinstance(td, dict):
            duration_ms = td.get("totalMilliseconds")
        duration_seconds = max(0, int(duration_ms // 1000)) if isinstance(duration_ms, (int, float)) else None
        thumb = None
        album = track_data.get("albumOfTrack")
        if isinstance(album, dict):
            thumb = _first_url_from_image_sources((album.get("coverArt") or {}).get("sources"))
        rows.append(
            {
                "spotify_track_id": tid,
                "title": track_data.get("name"),
                "channel": ", ".join(names) if names else None,
                "duration_seconds": duration_seconds,
                "thumbnail_url": thumb,
            }
        )
    return rows


def fetch_spotify_playlist_tracks(playlist_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return (playlist_meta, track_rows) using SpotipyFree (no Spotify Web API token).

    SpotipyFree ``playlist()`` returns playlistV2-style metadata; ``playlist_items()``
    aggregates all pages internally but returns spotipy-shaped ``{items: [{track: ...}]}``.
    """
    from SpotipyFree import Spotify

    logger.info("Fetching Spotify playlist via SpotipyFree playlist_id=%s", playlist_id)
    sp = Spotify()
    try:
        meta = sp.playlist(playlist_id)
    except Exception:
        logger.exception("SpotipyFree playlist() failed playlist_id=%s", playlist_id)
        raise
    if not isinstance(meta, dict):
        logger.warning("Unexpected Spotify playlist response type=%s playlist_id=%s", type(meta), playlist_id)
        raise ValueError("Unexpected Spotify playlist response")

    title = meta.get("name")
    channel = _playlist_owner_display(meta)
    thumb = _playlist_cover_url(meta)

    rows: list[dict[str, Any]] = []
    playlist_items_error: Exception | None = None
    page: dict[str, Any] | None = None
    try:
        page = sp.playlist_items(playlist_id, limit=-1, offset=0)
    except Exception as exc:
        playlist_items_error = exc
        logger.exception("SpotipyFree playlist_items failed playlist_id=%s", playlist_id)
        page = None

    if isinstance(page, dict):
        items = page.get("items")
        if isinstance(items, list):
            logger.debug(
                "Spotify playlist_items playlist_id=%s item_wrappers=%s total=%s",
                playlist_id,
                len(items),
                page.get("total"),
            )
            for wrap in items:
                if isinstance(wrap, dict):
                    r = _row_from_wrapped_item(wrap)
                    if r:
                        rows.append(r)

    if not rows:
        embedded = _rows_from_playlist_content(meta)
        if embedded:
            logger.info(
                "Using embedded content.items for tracks playlist_id=%s count=%s",
                playlist_id,
                len(embedded),
            )
            rows = embedded
        else:
            logger.warning("No tracks parsed from playlist_items or content.items playlist_id=%s", playlist_id)
            if playlist_items_error is not None:
                raise playlist_items_error
            raise ValueError("No tracks parsed from playlist_items or content.items")

    logger.info(
        "Spotify playlist loaded playlist_id=%s title=%r track_count=%s",
        playlist_id,
        title,
        len(rows),
    )
    return (
        {
            "title": title,
            "channel": channel,
            "thumbnail_url": thumb,
            "source_url": normalize_spotify_playlist_url(playlist_id),
        },
        rows,
    )
