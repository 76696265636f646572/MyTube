from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.api.common.dependencies import _services
from app.api.common.models import RepeatModeRequest, SeekRequest, ShuffleModeRequest
from app.api.common.serializers import _publish_ui_snapshot

router = APIRouter()


@router.post("/playback/play")
def playback_play(request: Request) -> dict[str, Any]:
    action = _services(request)["engine"].resume_playback()
    _publish_ui_snapshot(request)
    return {"ok": True, "action": action}


@router.post("/playback/stop")
def playback_stop(request: Request) -> dict[str, Any]:
    _services(request)["engine"].stop_playback()
    _publish_ui_snapshot(request)
    return {"ok": True}


@router.post("/playback/previous")
def playback_previous(request: Request) -> dict[str, Any]:
    action = _services(request)["engine"].play_previous_or_restart()
    _publish_ui_snapshot(request)
    return {"ok": True, "action": action}


@router.post("/playback/toggle-pause")
def playback_toggle_pause(request: Request) -> dict[str, Any]:
    paused = _services(request)["engine"].toggle_pause()
    _publish_ui_snapshot(request)
    return {"ok": True, "paused": paused}


@router.post("/playback/repeat")
def playback_repeat(payload: RepeatModeRequest, request: Request) -> dict[str, Any]:
    try:
        mode = _services(request)["engine"].set_repeat_mode(payload.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _publish_ui_snapshot(request)
    return {"ok": True, "mode": mode}


@router.post("/playback/shuffle")
def playback_shuffle(payload: ShuffleModeRequest, request: Request) -> dict[str, Any]:
    enabled = _services(request)["engine"].set_shuffle_enabled(payload.enabled)
    _publish_ui_snapshot(request)
    return {"ok": True, "enabled": enabled}


@router.post("/playback/seek")
def playback_seek(payload: SeekRequest, request: Request) -> dict[str, Any]:
    ok = _services(request)["engine"].seek_to_percent(payload.percent)
    if not ok:
        raise HTTPException(status_code=400, detail="Current track is not seekable")
    _publish_ui_snapshot(request)
    return {"ok": True}
