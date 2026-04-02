from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from app.api.common.dependencies import _services
from app.api.common.models import SpotifyImportSelectHitRequest, SpotifyImportUrlRequest
from app.api.common.serializers import _publish_ui_snapshot

router = APIRouter()


@router.post("/spotify/import")
def spotify_import_start(payload: SpotifyImportUrlRequest, request: Request) -> dict[str, Any]:
    try:
        result = _services(request)["spotify_import"].start_import(str(payload.url))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _publish_ui_snapshot(request)
    return {"ok": True, **result}


@router.get("/spotify/import/{playlist_id}/state")
def spotify_import_state(playlist_id: UUID, request: Request) -> dict[str, Any]:
    try:
        return _services(request)["spotify_import"].get_state(playlist_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/spotify/import/{playlist_id}/advance")
def spotify_import_advance(playlist_id: UUID, request: Request) -> dict[str, Any]:
    try:
        out = _services(request)["spotify_import"].advance(playlist_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if out.get("just_completed"):
        _publish_ui_snapshot(request)
    return out


@router.post("/spotify/import/{playlist_id}/restart-search")
def spotify_import_restart_search(playlist_id: UUID, request: Request) -> dict[str, Any]:
    try:
        result = _services(request)["spotify_import"].restart_search(playlist_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _publish_ui_snapshot(request)
    return result


@router.patch("/spotify/import/{playlist_id}/entries/{entry_id}")
def spotify_import_select_hit(
    playlist_id: UUID, entry_id: int, payload: SpotifyImportSelectHitRequest, request: Request
) -> dict[str, Any]:
    hit = {
        "source_url": payload.source_url,
        "normalized_url": payload.normalized_url,
        "provider": payload.provider,
        "provider_item_id": payload.provider_item_id,
        "title": payload.title,
        "channel": payload.channel,
        "duration_seconds": payload.duration_seconds,
        "thumbnail_url": payload.thumbnail_url,
    }
    try:
        out = _services(request)["spotify_import"].apply_selected_hit(playlist_id, entry_id, hit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _publish_ui_snapshot(request)
    return out
