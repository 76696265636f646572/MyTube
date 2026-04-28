from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.services.stream_engine import StreamEngine

from .dependencies import _services

templates = Jinja2Templates(directory="app/templates")


def _stream_url(request: Request) -> str:
    return _services(request)["settings"].stream_url_for(str(request.base_url))


def _stream_url_from_base(settings: Any, base_url: str) -> str:
    return settings.stream_url_for(base_url)


def _prefer_youtube_hq_thumbnail(url: str | None) -> str | None:
    """Map maxres YouTube CDN thumbs to hqdefault (yt-dlp often returns maxresdefault)."""
    if not url or "maxresdefault" not in url:
        return url
    host = (urlparse(url).netloc or "").lower()
    if "ytimg.com" not in host and host not in {"img.youtube.com", "www.img.youtube.com"}:
        return url
    return url.replace("maxresdefault.jpg", "hqdefault.jpg").replace("maxresdefault.webp", "hqdefault.webp")


def _serialize_state(engine: StreamEngine, stream_url: str, *, repo: Any | None = None) -> dict[str, Any]:
    progress = engine.playback_progress()
    now_playing_is_liked = False
    if repo is not None and getattr(engine.state, "now_playing_id", None) is not None:
        try:
            liked = repo.get_playlist_by_source_url("custom://liked_songs")
            if liked is not None:
                item = repo.get_item(engine.state.now_playing_id)
                if item is not None:
                    now_playing_is_liked = repo.playlist_contains_track(
                        liked.id,
                        normalized_url=getattr(item, "normalized_url", None),
                        provider_item_id=getattr(item, "provider_item_id", None),
                    )
        except Exception:
            now_playing_is_liked = False
    return {
        "mode": engine.state.mode.value,
        "paused": engine.state.paused,
        "repeat_mode": engine.state.repeat_mode.value,
        "shuffle_enabled": engine.state.shuffle_enabled,
        "can_seek": bool(engine.state.now_playing_duration_seconds and engine.state.now_playing_duration_seconds > 0),
        "now_playing_id": engine.state.now_playing_id,
        "now_playing_title": engine.state.now_playing_title,
        "now_playing_channel": getattr(engine.state, "now_playing_channel", None),
        "now_playing_thumbnail_url": _prefer_youtube_hq_thumbnail(
            getattr(engine.state, "now_playing_thumbnail_url", None)
        ),
        "now_playing_is_live": getattr(engine.state, "now_playing_is_live", False),
        "now_playing_is_liked": now_playing_is_liked,
        "stream_url": stream_url,
        **progress,
    }


def _serialize_queue_items(items: list[Any]) -> list[dict[str, Any]]:
    def resolved_thumbnail(item: Any) -> str | None:
        if item.thumbnail_url:
            return item.thumbnail_url
        provider_item_id = getattr(item, "provider_item_id", None)
        if provider_item_id:
            return f"https://i.ytimg.com/vi/{provider_item_id}/hqdefault.jpg"
        source_url = getattr(item, "source_url", None) or ""
        parsed = urlparse(source_url)
        host = (parsed.netloc or "").lower()
        if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
            video_id = (parse_qs(parsed.query).get("v") or [None])[0]
            if video_id:
                return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        if host in {"youtu.be", "www.youtu.be"}:
            video_id = (parsed.path or "").strip("/")
            if video_id:
                return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        return None

    return [
        {
            "id": item.id,
            "title": item.title,
            "source_url": item.source_url,
            "provider": item.provider,
            "provider_item_id": item.provider_item_id,
            "status": item.status.value,
            "queue_position": item.queue_position,
            "source_type": item.source_type,
            "channel": item.channel,
            "duration_seconds": item.duration_seconds,
            "thumbnail_url": resolved_thumbnail(item),
            "playlist_id": item.playlist_id,
        }
        for item in items
    ]


def serialize_musicatlas_matches_for_queue_ui(matches: list[Any]) -> list[dict[str, Any]]:
    """
    Map MusicAtlas ``matches`` entries to the same keys as :func:`_serialize_queue_items`
    so the Vue layer can reuse list row / Song-style rendering.
    """
    out: list[dict[str, Any]] = []
    for match in matches:
        if not isinstance(match, dict):
            continue
        artist = (match.get("artist") or "").strip()
        title = (match.get("title") or "").strip()
        platform_ids = match.get("platform_ids")
        youtube_id: str | None = None
        if isinstance(platform_ids, dict):
            raw_yt = platform_ids.get("youtube")
            if raw_yt is not None:
                youtube_id = str(raw_yt).strip() or None
        source_url = f"https://www.youtube.com/watch?v={youtube_id}" if youtube_id else None
        thumb = f"https://i.ytimg.com/vi/{youtube_id}/hqdefault.jpg" if youtube_id else None
        item: dict[str, Any] = {
            "id": None,
            "title": title or None,
            "source_url": source_url,
            "provider": "youtube" if youtube_id else None,
            "provider_item_id": youtube_id,
            "status": "suggested",
            "queue_position": None,
            "source_type": "video" if youtube_id else None,
            "channel": artist or None,
            "duration_seconds": None,
            "thumbnail_url": thumb,
            "playlist_id": None,
        }
        sim = match.get("atlas_similarity")
        if isinstance(sim, (int, float)):
            item["atlas_similarity"] = float(sim)
        out.append(item)
    return out


def _serialize_history_rows(rows: list[Any]) -> list[dict[str, Any]]:
    def resolved_thumbnail(row: Any) -> str | None:
        if row.thumbnail_url:
            return row.thumbnail_url
        provider_item_id = getattr(row, "provider_item_id", None)
        if provider_item_id:
            return f"https://i.ytimg.com/vi/{provider_item_id}/hqdefault.jpg"
        source_url = getattr(row, "source_url", None) or ""
        parsed = urlparse(source_url)
        host = (parsed.netloc or "").lower()
        if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
            video_id = (parse_qs(parsed.query).get("v") or [None])[0]
            if video_id:
                return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        if host in {"youtu.be", "www.youtu.be"}:
            video_id = (parsed.path or "").strip("/")
            if video_id:
                return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        return None

    return [
        {
            "id": row.id,
            "queue_item_id": row.queue_item_id,
            "title": row.title,
            "source_url": row.source_url,
            "provider": row.provider,
            "provider_item_id": row.provider_item_id,
            "thumbnail_url": resolved_thumbnail(row),
            "status": row.status,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "error_message": row.error_message,
        }
        for row in rows
    ]


def _serialize_sonos_speaker_base(speaker: Any) -> dict[str, Any]:
    return {
        "ip": speaker.ip,
        "name": speaker.name,
        "uid": speaker.uid,
        "coordinator_uid": speaker.coordinator_uid,
        "group_member_uids": speaker.group_member_uids,
        "volume": speaker.volume,
        "transport_state": getattr(speaker, "transport_state", None),
        "is_playing": bool(getattr(speaker, "is_playing", False)),
        "is_coordinator": speaker.is_coordinator,
    }


def _serialize_sonos_speaker(speaker: Any, speakers_by_uid: dict[str, Any]) -> dict[str, Any]:
    payload = _serialize_sonos_speaker_base(speaker)
    payload["group_members"] = [
        _serialize_sonos_speaker_base(member)
        for member_uid in speaker.group_member_uids
        if (member := speakers_by_uid.get(member_uid)) is not None
    ]
    return payload


def build_ui_snapshot(app, base_url: str) -> dict[str, Any]:
    settings = app.state.settings
    stream_url = _stream_url_from_base(settings, base_url)
    engine: StreamEngine = app.state.stream_engine
    repo = app.state.repository
    playlist = app.state.playlist_service
    return {
        "type": "snapshot",
        "state": _serialize_state(engine, stream_url, repo=repo),
        "queue": _serialize_queue_items(repo.list_queue()),
        "history": _serialize_history_rows(repo.list_history(limit=settings.history_limit)),
        "playlists": playlist.list_playlists(),
    }


def _publish_ui_snapshot(request: Request) -> None:
    services = _services(request)
    services["ui_events"].publish_snapshot(str(request.base_url))


def render_frontend_shell(request: Request) -> HTMLResponse:
    services = _services(request)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": services["settings"].app_name,
            "stream_url": _stream_url(request),
        },
    )
