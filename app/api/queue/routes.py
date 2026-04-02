from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.api.common.dependencies import _services
from app.api.common.models import AddLocalFolderRequest, AddLocalPathRequest, AddUrlRequest, ReorderRequest
from app.api.common.serializers import _publish_ui_snapshot, _serialize_queue_items

router = APIRouter()


@router.get("/queue")
def list_queue(request: Request) -> list[dict[str, Any]]:
    queue = _services(request)["repo"].list_queue()
    return _serialize_queue_items(queue)


@router.post("/queue/add")
def add_to_queue(payload: AddUrlRequest, request: Request) -> dict[str, Any]:
    try:
        result = _services(request)["playlist"].add_url(str(payload.url))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _publish_ui_snapshot(request)
    return {"ok": True, **result}


@router.post("/queue/add-local")
def add_local_to_queue(payload: AddLocalPathRequest, request: Request) -> dict[str, Any]:
    try:
        result = _services(request)["playlist"].add_local_path(payload.path.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _publish_ui_snapshot(request)
    return {"ok": True, **result}


@router.post("/queue/play-now")
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        if "This video is not available" in str(e):
            raise HTTPException(status_code=400, detail="Sorry, we couldn't play this URL.") from e
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/queue/play-now-local")
def play_now_local(payload: AddLocalPathRequest, request: Request) -> dict[str, Any]:
    services = _services(request)
    try:
        result = services["playlist"].add_local_path(payload.path.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    item_ids = result.get("item_ids") or []
    if item_ids:
        services["repo"].reorder_queued_items(item_ids)
        services["engine"].skip_current()
    _publish_ui_snapshot(request)
    return {"ok": True, **result}


@router.post("/queue/add-local-folder")
def add_local_folder_to_queue(payload: AddLocalFolderRequest, request: Request) -> dict[str, Any]:
    try:
        result = _services(request)["playlist"].add_local_folder(
            payload.path.strip(), recursive=payload.recursive
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _publish_ui_snapshot(request)
    return {"ok": True, **result}


@router.post("/queue/play-now-local-folder")
def play_now_local_folder(payload: AddLocalFolderRequest, request: Request) -> dict[str, Any]:
    services = _services(request)
    try:
        result = services["playlist"].add_local_folder(payload.path.strip(), recursive=payload.recursive)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    item_ids = result.get("item_ids") or []
    if item_ids:
        services["repo"].reorder_queued_items(item_ids)
        services["engine"].skip_current()
    _publish_ui_snapshot(request)
    return {"ok": True, **result}


@router.post("/queue/{item_id}/reorder")
def reorder_queue(item_id: int, payload: ReorderRequest, request: Request) -> dict[str, bool]:
    ok = _services(request)["repo"].reorder_item(item_id=item_id, new_position=payload.new_position)
    if not ok:
        raise HTTPException(status_code=404, detail="Queue item not found")
    _publish_ui_snapshot(request)
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
    _publish_ui_snapshot(request)
    return {"ok": ok}


@router.delete("/queue")
def clear_queue(request: Request) -> dict[str, bool]:
    services = _services(request)
    has_playing_item = any(item.status.value == "playing" for item in services["repo"].list_queue())
    services["repo"].clear_queue()
    if has_playing_item:
        services["engine"].skip_current()
    _publish_ui_snapshot(request)
    return {"ok": True}


@router.post("/queue/skip")
def skip_current(request: Request) -> dict[str, bool]:
    _services(request)["engine"].skip_current()
    # Do NOT publish snapshot here: it runs async and the worker may have already
    # updated state to the next track before the snapshot is built, causing the
    # UI to show new track info before audio starts. The engine notifies when
    # the first chunk of the new track is streamed.
    return {"ok": True}
