from __future__ import annotations

import asyncio
import time
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, HttpUrl

from app.db.repository import NewPlaylistEntry
from app.services.stream_engine import PlaybackMode, StreamEngine
from app.services.yt_dlp_service import (
    cookie_setting_key,
    is_supported_cookie_provider,
    list_cookie_providers,
)

root_router = APIRouter()
api_router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class GracefulStreamingResponse(StreamingResponse):
    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        except asyncio.CancelledError:
            # A cancelled stream task is expected during client disconnect
            # or server shutdown.
            return


ImportMode = Literal["check", "add_all", "skip_duplicates"]


class AddUrlRequest(BaseModel):
    url: HttpUrl
    target_playlist_id: UUID | None = None
    import_mode: ImportMode | None = None


class ReorderRequest(BaseModel):
    new_position: int


class SonosPlayRequest(BaseModel):
    speaker_ip: str


class SonosGroupRequest(BaseModel):
    coordinator_ip: str
    member_ip: str


class SonosUngroupRequest(BaseModel):
    speaker_ip: str


class SonosVolumeRequest(BaseModel):
    speaker_ip: str
    volume: int = Field(ge=0, le=100)


class BatchPlaylistEntryInput(BaseModel):
    source_url: str
    normalized_url: str
    provider: str | None = None
    provider_item_id: str | None = None
    title: str | None = None
    channel: str | None = None
    duration_seconds: int | None = None
    thumbnail_url: str | None = None


class BatchAddPlaylistEntriesRequest(BaseModel):
    entries: list[BatchPlaylistEntryInput] = Field(min_length=1)
    import_mode: ImportMode | None = None


class CreateCustomPlaylistRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class UpdatePlaylistRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    pinned: bool | None = None


class RepeatModeRequest(BaseModel):
    mode: str = Field(pattern="^(off|all|one)$")


class ShuffleModeRequest(BaseModel):
    enabled: bool


class SeekRequest(BaseModel):
    percent: float = Field(ge=0.0, le=100.0)


class InstallBinaryRequest(BaseModel):
    name: str = Field(pattern="^(yt-dlp|ffmpeg|deno)$")
    stop_stream_first: bool = False


class CookieSettingUpdateRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    value: str = Field(min_length=1)


def _services(request: Request) -> dict[str, Any]:
    return {
        "repo": request.app.state.repository,
        "playlist": request.app.state.playlist_service,
        "engine": request.app.state.stream_engine,
        "settings": request.app.state.settings,
        "sonos": request.app.state.sonos_service,
        "yt_dlp": request.app.state.yt_dlp_service,
        "ui_events": request.app.state.ui_events,
        "binaries": request.app.state.binaries_service,
    }


def _stream_url(request: Request) -> str:
    return _services(request)["settings"].stream_url_for(str(request.base_url))


def _stream_url_from_base(settings: Any, base_url: str) -> str:
    return settings.stream_url_for(base_url)


def _serialize_state(engine: StreamEngine, stream_url: str) -> dict[str, Any]:
    progress = engine.playback_progress()
    return {
        "mode": engine.state.mode.value,
        "paused": engine.state.paused,
        "repeat_mode": engine.state.repeat_mode.value,
        "shuffle_enabled": engine.state.shuffle_enabled,
        "can_seek": bool(engine.state.now_playing_duration_seconds and engine.state.now_playing_duration_seconds > 0),
        "now_playing_id": engine.state.now_playing_id,
        "now_playing_title": engine.state.now_playing_title,
        "now_playing_channel": getattr(engine.state, "now_playing_channel", None),
        "now_playing_thumbnail_url": getattr(engine.state, "now_playing_thumbnail_url", None),
        "now_playing_is_live": getattr(engine.state, "now_playing_is_live", False),
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


def build_ui_snapshot(app, base_url: str) -> dict[str, Any]:
    settings = app.state.settings
    stream_url = _stream_url_from_base(settings, base_url)
    engine: StreamEngine = app.state.stream_engine
    repo = app.state.repository
    playlist = app.state.playlist_service
    return {
        "type": "snapshot",
        "state": _serialize_state(engine, stream_url),
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


@root_router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return render_frontend_shell(request)


@api_router.get("/health")
def health(request: Request) -> dict[str, str]:
    services = _services(request)
    return {"status": "ok", "mode": services["engine"].state.mode.value}


def _is_binary_in_use(name: str, engine: StreamEngine) -> bool:
    """True if the binary is currently running (e.g. ffmpeg/yt-dlp during playback)."""
    if engine.state.mode != PlaybackMode.playing:
        return False
    return name in ("ffmpeg", "yt-dlp")


@api_router.get("/binaries")
def list_binaries(request: Request) -> dict[str, list[dict[str, Any]]]:
    services = _services(request)
    binaries = services["binaries"].get_binaries()
    engine: StreamEngine = services["engine"]
    return {
        "binaries": [
            {
                "name": b.name,
                "path": b.path,
                "version": b.version,
                "is_system": b.is_system,
                "in_use": _is_binary_in_use(b.name, engine),
            }
            for b in binaries
        ]
    }


@api_router.get("/binaries/updates")
def list_binary_updates(request: Request) -> dict[str, list[dict[str, Any]]]:
    updates = _services(request)["binaries"].get_updates()
    return {
        "updates": [
            {"name": u.name, "current": u.current, "latest": u.latest, "has_update": u.has_update}
            for u in updates
        ]
    }


@api_router.post("/binaries/install")
def install_binary(payload: InstallBinaryRequest, request: Request) -> dict[str, Any]:
    services = _services(request)
    svc = services["binaries"]
    engine: StreamEngine = services["engine"]

    # Stop playback first if requested (ffmpeg/yt-dlp may be in use)
    if payload.stop_stream_first and payload.name in ("ffmpeg", "yt-dlp"):
        engine.skip_current()
        time.sleep(2)

    try:
        svc.install(payload.name)
        _publish_ui_snapshot(request)
        return {"ok": True, "name": payload.name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OSError as e:
        if e.errno == 26:  # errno.ETXTBSY - Text file busy
            raise HTTPException(
                status_code=409,
                detail="binary_in_use",
            )
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/state")
def state(request: Request) -> dict[str, Any]:
    services = _services(request)
    engine: StreamEngine = services["engine"]
    return _serialize_state(engine, _stream_url(request))


@api_router.get("/settings/cookies")
def list_cookie_settings(request: Request) -> dict[str, list[dict[str, Any]]]:
    repo = _services(request)["repo"]
    providers = []
    for provider_info in list_cookie_providers():
        provider = provider_info["provider"]
        providers.append(
            {
                "provider": provider,
                "label": provider_info["label"],
                "configured": bool(repo.get_setting(cookie_setting_key(provider))),
            }
        )
    return {"providers": providers}


@api_router.put("/settings/cookies")
def update_cookie_setting(payload: CookieSettingUpdateRequest, request: Request) -> dict[str, Any]:
    provider = payload.provider.strip().lower()
    if not is_supported_cookie_provider(provider):
        raise HTTPException(status_code=400, detail="Unsupported cookie provider")
    _services(request)["repo"].set_setting(cookie_setting_key(provider), payload.value)
    return {"ok": True, "provider": provider, "configured": True}


@api_router.delete("/settings/cookies/{provider}")
def delete_cookie_setting(provider: str, request: Request) -> dict[str, Any]:
    provider_key = provider.strip().lower()
    if not is_supported_cookie_provider(provider_key):
        raise HTTPException(status_code=400, detail="Unsupported cookie provider")
    _services(request)["repo"].clear_setting(cookie_setting_key(provider_key))
    return {"ok": True, "provider": provider_key, "configured": False}


@api_router.get("/queue")
def list_queue(request: Request) -> list[dict[str, Any]]:
    queue = _services(request)["repo"].list_queue()
    return _serialize_queue_items(queue)


@api_router.post("/queue/add")
def add_to_queue(payload: AddUrlRequest, request: Request) -> dict[str, Any]:
    result = _services(request)["playlist"].add_url(str(payload.url))
    _publish_ui_snapshot(request)
    return {"ok": True, **result}


@api_router.post("/queue/play-now")
def play_now(payload: AddUrlRequest, request: Request) -> dict[str, Any]:
    services = _services(request)
    url = str(payload.url)
    try:
        is_playlist = services["yt_dlp"].is_playlist_url(url)
        if is_playlist:
            services["repo"].clear_queue()
            result = services["playlist"].queue_playlist_url(url, replace=True)
        else:
            result = services["playlist"].add_url(url)
        item_ids = result.get("item_ids") or []
        if item_ids:
            services["repo"].move_item_to_front(item_ids[0])
            services["engine"].skip_current()
        _publish_ui_snapshot(request)
        return {"ok": True, **result}
    except Exception as e:
        if "This video is not available" in str(e):
            raise HTTPException(status_code=400, detail="Sorry, we couldn't play this URL.") from e
        raise HTTPException(status_code=500, detail=str(e)) from e

@api_router.post("/queue/{item_id}/reorder")
def reorder_queue(item_id: int, payload: ReorderRequest, request: Request) -> dict[str, bool]:
    ok = _services(request)["repo"].reorder_item(item_id=item_id, new_position=payload.new_position)
    if not ok:
        raise HTTPException(status_code=404, detail="Queue item not found")
    _publish_ui_snapshot(request)
    return {"ok": True}


@api_router.delete("/queue/{item_id}")
def remove_queue_item(item_id: int, request: Request) -> dict[str, bool]:
    services = _services(request)
    item = services["repo"].get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Queue item not found")
    ok = services["repo"].remove_item(item_id=item_id)
    if item.status.value == "playing":
        services["engine"].skip_current()
    _publish_ui_snapshot(request)
    return {"ok": ok}


@api_router.delete("/queue")
def clear_queue(request: Request) -> dict[str, bool]:
    services = _services(request)
    has_playing_item = any(item.status.value == "playing" for item in services["repo"].list_queue())
    services["repo"].clear_queue()
    if has_playing_item:
        services["engine"].skip_current()
    _publish_ui_snapshot(request)
    return {"ok": True}


@api_router.post("/queue/skip")
def skip_current(request: Request) -> dict[str, bool]:
    _services(request)["engine"].skip_current()
    # Do NOT publish snapshot here: it runs async and the worker may have already
    # updated state to the next track before the snapshot is built, causing the
    # UI to show new track info before audio starts. The engine notifies when
    # the first chunk of the new track is streamed.
    return {"ok": True}


@api_router.post("/playback/previous")
def playback_previous(request: Request) -> dict[str, Any]:
    action = _services(request)["engine"].play_previous_or_restart()
    _publish_ui_snapshot(request)
    return {"ok": True, "action": action}


@api_router.post("/playback/toggle-pause")
def playback_toggle_pause(request: Request) -> dict[str, Any]:
    paused = _services(request)["engine"].toggle_pause()
    _publish_ui_snapshot(request)
    return {"ok": True, "paused": paused}


@api_router.post("/playback/repeat")
def playback_repeat(payload: RepeatModeRequest, request: Request) -> dict[str, Any]:
    try:
        mode = _services(request)["engine"].set_repeat_mode(payload.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _publish_ui_snapshot(request)
    return {"ok": True, "mode": mode}


@api_router.post("/playback/shuffle")
def playback_shuffle(payload: ShuffleModeRequest, request: Request) -> dict[str, Any]:
    enabled = _services(request)["engine"].set_shuffle_enabled(payload.enabled)
    _publish_ui_snapshot(request)
    return {"ok": True, "enabled": enabled}


@api_router.post("/playback/seek")
def playback_seek(payload: SeekRequest, request: Request) -> dict[str, Any]:
    ok = _services(request)["engine"].seek_to_percent(payload.percent)
    if not ok:
        raise HTTPException(status_code=400, detail="Current track is not seekable")
    _publish_ui_snapshot(request)
    return {"ok": True}


@api_router.get("/history")
def history(request: Request) -> list[dict[str, Any]]:
    services = _services(request)
    rows = services["repo"].list_history(limit=services["settings"].history_limit)
    return _serialize_history_rows(rows)


@api_router.delete("/history")
def clear_history(request: Request) -> dict[str, bool]:
    _services(request)["repo"].clear_history()
    _publish_ui_snapshot(request)
    return {"ok": True}


@api_router.post("/playlist/preview")
def playlist_preview(payload: AddUrlRequest, request: Request) -> dict[str, Any]:
    preview = _services(request)["playlist"].preview_playlist(str(payload.url))
    return {
        "provider": preview.provider,
        "source_url": preview.source_url,
        "title": preview.title,
        "channel": preview.channel,
        "thumbnail_url": preview.thumbnail_url,
        "entries": preview.entries,
        "count": len(preview.entries),
    }


@api_router.post("/playlist/import")
def playlist_import(payload: AddUrlRequest, request: Request) -> dict[str, Any]:
    result = _services(request)["playlist"].import_playlist(
        str(payload.url),
        target_playlist_id=payload.target_playlist_id,
        import_mode=payload.import_mode,
    )
    if not result.get("has_duplicates"):
        _publish_ui_snapshot(request)
    if result.get("has_duplicates"):
        return result
    return {"ok": True, **result}


@api_router.get("/playlists")
def playlists(request: Request) -> list[dict[str, Any]]:
    return _services(request)["playlist"].list_playlists()


@api_router.post("/playlists/custom")
def create_custom_playlist(payload: CreateCustomPlaylistRequest, request: Request) -> dict[str, Any]:
    result = _services(request)["playlist"].create_custom_playlist(payload.title.strip())
    _publish_ui_snapshot(request)
    return result


@api_router.get("/playlists/{playlist_id}")
def get_playlist(playlist_id: UUID, request: Request) -> dict[str, Any]:
    playlists = _services(request)["playlist"].list_playlists()
    match = next((playlist for playlist in playlists if playlist["id"] == playlist_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return match


@api_router.get("/playlists/{playlist_id}/entries")
def playlist_entries(playlist_id: UUID, request: Request) -> list[dict[str, Any]]:
    return _services(request)["playlist"].list_playlist_entries(playlist_id)


@api_router.post("/playlists/{playlist_id}/entries")
def add_playlist_entry(playlist_id: UUID, payload: AddUrlRequest, request: Request) -> dict[str, Any]:
    try:
        result = _services(request)["playlist"].add_item_to_playlist(
            playlist_id=playlist_id,
            url=str(payload.url),
            import_mode=payload.import_mode,
        )
        if not result.get("has_duplicates"):
            _publish_ui_snapshot(request)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.post("/playlists/{playlist_id}/entries/batch")
def batch_add_playlist_entries(
    playlist_id: UUID, payload: BatchAddPlaylistEntriesRequest, request: Request
) -> dict[str, Any]:
    try:
        entries = [
            NewPlaylistEntry(
                source_url=e.source_url,
                provider=e.provider,
                provider_item_id=e.provider_item_id,
                normalized_url=e.normalized_url,
                title=e.title,
                channel=e.channel,
                duration_seconds=e.duration_seconds,
                thumbnail_url=e.thumbnail_url,
            )
            for e in payload.entries
        ]
        result = _services(request)["playlist"].add_entries_to_playlist(
            playlist_id=playlist_id,
            entries=entries,
            import_mode=payload.import_mode,
        )
        if not result.get("has_duplicates"):
            _publish_ui_snapshot(request)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.post("/playlists/{playlist_id}/queue")
def queue_playlist(playlist_id: UUID, request: Request) -> dict[str, Any]:
    result = _services(request)["playlist"].queue_playlist(playlist_id)
    _publish_ui_snapshot(request)
    return result


@api_router.patch("/playlists/{playlist_id}")
def update_playlist(playlist_id: UUID, payload: UpdatePlaylistRequest, request: Request) -> dict[str, Any]:
    if payload.title is None and payload.description is None and payload.pinned is None:
        raise HTTPException(status_code=400, detail="At least one of title, description, or pinned must be provided")
    try:
        result = _services(request)["playlist"].update_playlist(
            playlist_id,
            title=payload.title,
            description=payload.description,
            pinned=payload.pinned,
        )
        _publish_ui_snapshot(request)
        return result
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_router.delete("/playlists/{playlist_id}")
def delete_playlist(playlist_id: UUID, request: Request) -> dict[str, Any]:
    try:
        _services(request)["playlist"].delete_playlist(playlist_id)
        _publish_ui_snapshot(request)
        return {"ok": True}
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_router.post("/playlists/{playlist_id}/play-now")
def play_playlist_now(playlist_id: UUID, request: Request) -> dict[str, Any]:
    services = _services(request)
    result = services["playlist"].queue_playlist(playlist_id)
    item_ids = result.get("item_ids") or []
    if item_ids:
        services["repo"].move_item_to_front(item_ids[0])
        services["engine"].skip_current()
    _publish_ui_snapshot(request)
    return result


@api_router.post("/playlists/entries/{entry_id}/queue")
def queue_playlist_entry(entry_id: int, request: Request) -> dict[str, Any]:
    try:
        result = _services(request)["playlist"].queue_playlist_entry(entry_id)
        _publish_ui_snapshot(request)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.delete("/playlists/entries/{entry_id}")
def delete_playlist_entry(entry_id: int, request: Request) -> Response:
    try:
        _services(request)["playlist"].remove_playlist_entry(entry_id)
        _publish_ui_snapshot(request)
        return Response(status_code=204)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.post("/playlists/entries/{entry_id}/reorder")
def reorder_playlist_entry(entry_id: int, payload: ReorderRequest, request: Request) -> dict[str, bool]:
    try:
        _services(request)["playlist"].reorder_playlist_entry(entry_id, payload.new_position)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    broker = websocket.app.state.ui_events
    base_url = str(websocket.base_url)
    queue = await broker.add_client(websocket, base_url)
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(jsonable_encoder(payload))
    except WebSocketDisconnect:
        return
    finally:
        await broker.remove_client(queue)


@api_router.get("/search")
def search(
    request: Request,
    q: str = Query(min_length=1),
    limit: int = Query(default=10, ge=1, le=100),
    providers: str | None = Query(default=None),
) -> dict[str, Any]:
    selected_providers = [part.strip() for part in providers.split(",") if part.strip()] if providers else None
    yt_dlp_service = _services(request)["yt_dlp"]
    if hasattr(yt_dlp_service, "search"):
        results = yt_dlp_service.search(query=q, limit=limit, providers=selected_providers)
    else:
        results = yt_dlp_service.search_videos(query=q, limit=limit)
    return {"query": q, "count": len(results), "results": results}


@api_router.get("/search/youtube")
def search_youtube(
    request: Request,
    q: str = Query(min_length=1),
    limit: int = Query(default=10, ge=1, le=100),
) -> dict[str, Any]:
    # Backward-compatible endpoint shim.
    return search(request=request, q=q, limit=limit, providers="youtube")


@root_router.get("/stream/live.mp3")
def stream_live(request: Request) -> StreamingResponse:
    engine = _services(request)["engine"]
    return GracefulStreamingResponse(engine.subscribe(), media_type="audio/mpeg")


@api_router.get("/sonos/speakers")
def sonos_speakers(request: Request) -> list[dict[str, Any]]:
    speakers = _services(request)["sonos"].discover_speakers()
    return [
        {
            "ip": speaker.ip,
            "name": speaker.name,
            "uid": speaker.uid,
            "coordinator_uid": speaker.coordinator_uid,
            "group_member_uids": speaker.group_member_uids,
            "volume": speaker.volume,
            "is_coordinator": speaker.is_coordinator,
        }
        for speaker in speakers
    ]


@api_router.post("/sonos/play")
def sonos_play(payload: SonosPlayRequest, request: Request) -> dict[str, bool]:
    services = _services(request)
    services["sonos"].play_stream(payload.speaker_ip, _stream_url(request))
    return {"ok": True}


@api_router.post("/sonos/group")
def sonos_group(payload: SonosGroupRequest, request: Request) -> dict[str, bool]:
    _services(request)["sonos"].group_speaker(payload.coordinator_ip, payload.member_ip)
    return {"ok": True}


@api_router.post("/sonos/ungroup")
def sonos_ungroup(payload: SonosUngroupRequest, request: Request) -> dict[str, bool]:
    _services(request)["sonos"].ungroup_speaker(payload.speaker_ip)
    return {"ok": True}


@api_router.post("/sonos/volume")
def sonos_volume(payload: SonosVolumeRequest, request: Request) -> dict[str, bool]:
    _services(request)["sonos"].set_volume(payload.speaker_ip, payload.volume)
    return {"ok": True}
