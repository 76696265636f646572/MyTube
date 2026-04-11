from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.api.common.dependencies import _services
from app.api.common.models import (
    AddLocalFolderRequest,
    AddLocalPathRequest,
    AddUrlRequest,
    BatchAddPlaylistEntriesRequest,
    CreateCustomPlaylistRequest,
    ReorderRequest,
    SidebarPlaylistReorderRequest,
    UpdatePlaylistRequest,
)
from app.api.common.serializers import _publish_ui_snapshot
from app.db.repository import NewPlaylistEntry

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/playlists")
def playlists(request: Request) -> list[dict[str, Any]]:
    return _services(request)["playlist"].list_playlists()


@router.post("/playlists/custom")
def create_custom_playlist(payload: CreateCustomPlaylistRequest, request: Request) -> dict[str, Any]:
    result = _services(request)["playlist"].create_custom_playlist(payload.title.strip())
    _publish_ui_snapshot(request)
    return result


@router.get("/playlists/{playlist_id}")
def get_playlist(playlist_id: UUID, request: Request) -> dict[str, Any]:
    playlists = _services(request)["playlist"].list_playlists()
    match = next((playlist for playlist in playlists if playlist["id"] == playlist_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return match


@router.get("/playlists/{playlist_id}/entries")
def playlist_entries(playlist_id: UUID, request: Request) -> list[dict[str, Any]]:
    return _services(request)["playlist"].list_playlist_entries(playlist_id)


@router.post("/playlists/{playlist_id}/entries")
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


@router.post("/playlists/{playlist_id}/entries/local")
def add_local_playlist_entry(playlist_id: UUID, payload: AddLocalPathRequest, request: Request) -> dict[str, Any]:
    try:
        result = _services(request)["playlist"].add_local_path_to_playlist(
            playlist_id=playlist_id,
            path=payload.path.strip(),
            import_mode=payload.import_mode,
        )
        if not result.get("has_duplicates"):
            _publish_ui_snapshot(request)
        return result
    except ValueError as exc:
        detail = str(exc)
        status = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail) from exc


@router.post("/playlists/{playlist_id}/entries/local-folder")
def add_local_folder_playlist_entries(
    playlist_id: UUID, payload: AddLocalFolderRequest, request: Request
) -> dict[str, Any]:
    try:
        result = _services(request)["playlist"].add_local_folder_to_playlist(
            playlist_id=playlist_id,
            path=payload.path.strip(),
            recursive=payload.recursive,
            import_mode=payload.import_mode,
        )
        if not result.get("has_duplicates"):
            _publish_ui_snapshot(request)
        return result
    except ValueError as exc:
        detail = str(exc)
        status = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail) from exc


@router.post("/playlists/{playlist_id}/entries/batch")
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


@router.post("/playlists/{playlist_id}/queue")
def queue_playlist(playlist_id: UUID, request: Request) -> dict[str, Any]:
    result = _services(request)["playlist"].queue_playlist(playlist_id)
    _publish_ui_snapshot(request)
    return result


@router.patch("/playlists/{playlist_id}")
def update_playlist(playlist_id: UUID, payload: UpdatePlaylistRequest, request: Request) -> dict[str, Any]:
    if (
        payload.title is None
        and payload.description is None
        and payload.pinned is None
        and payload.sync_enabled is None
        and payload.sync_remove_missing is None
    ):
        raise HTTPException(
            status_code=400,
            detail="At least one field must be provided",
        )
    playlist = _services(request)["repo"].get_playlist(playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist not found")
    # Allow pinning/unpinning of playlists only.
    restricted_fields_requested = any(
        value is not None
        for value in (
            payload.title,
            payload.description,
            payload.sync_enabled,
            payload.sync_remove_missing,
        )
    )
    if not getattr(playlist, "can_edit", True) and restricted_fields_requested:
        raise HTTPException(status_code=403, detail="Playlist cannot be edited")
    old_sync_enabled = bool(getattr(playlist, "sync_enabled", False))
    old_sync_remove_missing = bool(getattr(playlist, "sync_remove_missing", False))
    try:
        kwargs: dict[str, Any] = {
            "title": payload.title,
            "description": payload.description,
            "pinned": payload.pinned,
        }
        if getattr(playlist, "can_edit", True):
            if payload.sync_enabled is not None:
                kwargs["sync_enabled"] = payload.sync_enabled
            if payload.sync_remove_missing is not None:
                kwargs["sync_remove_missing"] = payload.sync_remove_missing
        result = _services(request)["playlist"].update_playlist(playlist_id, **kwargs)
        if payload.sync_enabled is not None and bool(payload.sync_enabled) != old_sync_enabled:
            logger.info(
                "Playlist sync toggle changed playlist_id=%s sync_enabled=%s",
                playlist_id,
                bool(payload.sync_enabled),
            )
        if payload.sync_remove_missing is not None and bool(payload.sync_remove_missing) != old_sync_remove_missing:
            logger.info(
                "Playlist sync prune toggle changed playlist_id=%s sync_remove_missing=%s",
                playlist_id,
                bool(payload.sync_remove_missing),
            )
        _publish_ui_snapshot(request)
        return result
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/playlists/{playlist_id}")
def delete_playlist(playlist_id: UUID, request: Request) -> dict[str, Any]:
    playlist = _services(request)["repo"].get_playlist(playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist not found")
    if not getattr(playlist, "can_delete", True):
        raise HTTPException(status_code=403, detail="Playlist cannot be deleted")
    try:
        _services(request)["playlist"].delete_playlist(playlist_id)
        _publish_ui_snapshot(request)
        return {"ok": True}
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/playlists/reorder")
def reorder_sidebar_playlist(payload: SidebarPlaylistReorderRequest, request: Request) -> dict[str, bool]:
    try:
        _services(request)["playlist"].reorder_sidebar_playlist(
            payload.playlist_id, payload.new_position, payload.pinned
        )
        _publish_ui_snapshot(request)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/playlists/{playlist_id}/play-now")
def play_playlist_now(playlist_id: UUID, request: Request) -> dict[str, Any]:
    services = _services(request)
    result = services["playlist"].queue_playlist(playlist_id, replace=True)
    item_ids = result.get("item_ids") or []
    if item_ids:
        services["engine"].skip_current()
    _publish_ui_snapshot(request)
    return result


@router.post("/playlists/entries/{entry_id}/queue")
def queue_playlist_entry(entry_id: int, request: Request) -> dict[str, Any]:
    try:
        result = _services(request)["playlist"].queue_playlist_entry(entry_id)
        _publish_ui_snapshot(request)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/playlists/entries/{entry_id}")
def delete_playlist_entry(entry_id: int, request: Request) -> Response:
    try:
        _services(request)["playlist"].remove_playlist_entry(entry_id)
        _publish_ui_snapshot(request)
        return Response(status_code=204)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/playlists/entries/{entry_id}/reorder")
def reorder_playlist_entry(entry_id: int, payload: ReorderRequest, request: Request) -> dict[str, bool]:
    try:
        _services(request)["playlist"].reorder_playlist_entry(entry_id, payload.new_position)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
