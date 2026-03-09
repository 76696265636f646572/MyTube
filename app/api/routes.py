from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, HttpUrl

from app.services.stream_engine import StreamEngine

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class GracefulStreamingResponse(StreamingResponse):
    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        except asyncio.CancelledError:
            # A cancelled stream task is expected during client disconnect
            # or server shutdown.
            return


class AddUrlRequest(BaseModel):
    url: HttpUrl


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


class CreateCustomPlaylistRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


def _services(request: Request) -> dict[str, Any]:
    return {
        "repo": request.app.state.repository,
        "playlist": request.app.state.playlist_service,
        "engine": request.app.state.stream_engine,
        "settings": request.app.state.settings,
        "sonos": request.app.state.sonos_service,
        "yt_dlp": request.app.state.yt_dlp_service,
    }


def _stream_url(request: Request) -> str:
    return _services(request)["settings"].stream_url_for(str(request.base_url))


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    services = _services(request)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": services["settings"].app_name,
            "stream_url": _stream_url(request),
        },
    )


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    services = _services(request)
    return {"status": "ok", "mode": services["engine"].state.mode.value}


@router.get("/state")
def state(request: Request) -> dict[str, Any]:
    services = _services(request)
    engine: StreamEngine = services["engine"]
    progress = engine.playback_progress()
    return {
        "mode": engine.state.mode.value,
        "now_playing_id": engine.state.now_playing_id,
        "now_playing_title": engine.state.now_playing_title,
        "now_playing_channel": getattr(engine.state, "now_playing_channel", None),
        "now_playing_thumbnail_url": getattr(engine.state, "now_playing_thumbnail_url", None),
        "stream_url": _stream_url(request),
        **progress,
    }


@router.get("/queue")
def list_queue(request: Request) -> list[dict[str, Any]]:
    queue = _services(request)["repo"].list_queue()
    return [
        {
            "id": item.id,
            "title": item.title,
            "source_url": item.source_url,
            "status": item.status.value,
            "queue_position": item.queue_position,
            "source_type": item.source_type,
            "channel": item.channel,
            "duration_seconds": item.duration_seconds,
            "thumbnail_url": item.thumbnail_url,
            "playlist_id": item.playlist_id,
        }
        for item in queue
    ]


@router.post("/queue/add")
def add_to_queue(payload: AddUrlRequest, request: Request) -> dict[str, Any]:
    result = _services(request)["playlist"].add_url(str(payload.url))
    return {"ok": True, **result}


@router.post("/queue/play-now")
def play_now(payload: AddUrlRequest, request: Request) -> dict[str, Any]:
    services = _services(request)
    result = services["playlist"].add_url(str(payload.url))
    item_ids = result.get("item_ids") or []
    if item_ids:
        services["repo"].move_item_to_front(item_ids[0])
    services["engine"].skip_current()
    return {"ok": True, **result}


@router.post("/queue/{item_id}/reorder")
def reorder_queue(item_id: int, payload: ReorderRequest, request: Request) -> dict[str, bool]:
    ok = _services(request)["repo"].reorder_item(item_id=item_id, new_position=payload.new_position)
    if not ok:
        raise HTTPException(status_code=404, detail="Queue item not found")
    return {"ok": True}


@router.delete("/queue/{item_id}")
def remove_queue_item(item_id: int, request: Request) -> dict[str, bool]:
    services = _services(request)
    item = services["repo"].get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Queue item not found")
    ok = services["repo"].remove_item(item_id=item_id)
    if item.status.value == "playing":
        services["engine"].skip_current()
    return {"ok": ok}


@router.post("/queue/skip")
def skip_current(request: Request) -> dict[str, bool]:
    _services(request)["engine"].skip_current()
    return {"ok": True}


@router.get("/history")
def history(request: Request) -> list[dict[str, Any]]:
    services = _services(request)
    rows = services["repo"].list_history(limit=services["settings"].history_limit)
    return [
        {
            "id": row.id,
            "queue_item_id": row.queue_item_id,
            "title": row.title,
            "source_url": row.source_url,
            "status": row.status,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "error_message": row.error_message,
        }
        for row in rows
    ]


@router.delete("/history")
def clear_history(request: Request) -> dict[str, bool]:
    _services(request)["repo"].clear_history()
    return {"ok": True}


@router.post("/playlist/preview")
def playlist_preview(payload: AddUrlRequest, request: Request) -> dict[str, Any]:
    preview = _services(request)["playlist"].preview_playlist(str(payload.url))
    return {
        "source_url": preview.source_url,
        "title": preview.title,
        "channel": preview.channel,
        "entries": preview.entries,
        "count": len(preview.entries),
    }


@router.post("/playlist/import")
def playlist_import(payload: AddUrlRequest, request: Request) -> dict[str, Any]:
    result = _services(request)["playlist"].import_playlist(str(payload.url))
    return {"ok": True, **result}


@router.get("/playlists")
def playlists(request: Request) -> list[dict[str, Any]]:
    return _services(request)["playlist"].list_playlists()


@router.post("/playlists/custom")
def create_custom_playlist(payload: CreateCustomPlaylistRequest, request: Request) -> dict[str, Any]:
    return _services(request)["playlist"].create_custom_playlist(payload.title.strip())


@router.get("/playlists/{playlist_id}")
def get_playlist(playlist_id: int, request: Request) -> dict[str, Any]:
    playlists = _services(request)["playlist"].list_playlists()
    match = next((playlist for playlist in playlists if playlist["id"] == playlist_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return match


@router.get("/playlists/{playlist_id}/entries")
def playlist_entries(playlist_id: int, request: Request) -> list[dict[str, Any]]:
    return _services(request)["playlist"].list_playlist_entries(playlist_id)


@router.post("/playlists/{playlist_id}/entries")
def add_playlist_entry(playlist_id: int, payload: AddUrlRequest, request: Request) -> dict[str, Any]:
    try:
        return _services(request)["playlist"].add_item_to_playlist(playlist_id=playlist_id, url=str(payload.url))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/playlists/{playlist_id}/queue")
def queue_playlist(playlist_id: int, request: Request) -> dict[str, Any]:
    return _services(request)["playlist"].queue_playlist(playlist_id)


@router.post("/playlists/entries/{entry_id}/queue")
def queue_playlist_entry(entry_id: int, request: Request) -> dict[str, Any]:
    try:
        return _services(request)["playlist"].queue_playlist_entry(entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/search/youtube")
def search_youtube(
    request: Request,
    q: str = Query(min_length=1),
    limit: int = Query(default=10, ge=1, le=25),
) -> dict[str, Any]:
    results = _services(request)["yt_dlp"].search_videos(query=q, limit=limit)
    return {"query": q, "count": len(results), "results": results}


@router.get("/stream/live.mp3")
def stream_live(request: Request) -> StreamingResponse:
    engine = _services(request)["engine"]
    return GracefulStreamingResponse(engine.subscribe(), media_type="audio/mpeg")


@router.get("/sonos/speakers")
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


@router.post("/sonos/play")
def sonos_play(payload: SonosPlayRequest, request: Request) -> dict[str, bool]:
    services = _services(request)
    services["sonos"].play_stream(payload.speaker_ip, _stream_url(request))
    return {"ok": True}


@router.post("/sonos/group")
def sonos_group(payload: SonosGroupRequest, request: Request) -> dict[str, bool]:
    _services(request)["sonos"].group_speaker(payload.coordinator_ip, payload.member_ip)
    return {"ok": True}


@router.post("/sonos/ungroup")
def sonos_ungroup(payload: SonosUngroupRequest, request: Request) -> dict[str, bool]:
    _services(request)["sonos"].ungroup_speaker(payload.speaker_ip)
    return {"ok": True}


@router.post("/sonos/volume")
def sonos_volume(payload: SonosVolumeRequest, request: Request) -> dict[str, bool]:
    _services(request)["sonos"].set_volume(payload.speaker_ip, payload.volume)
    return {"ok": True}
