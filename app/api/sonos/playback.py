from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.common.dependencies import _services
from app.api.common.models import (
    SonosGroupRequest,
    SonosPlayRequest,
    SonosStopRequest,
    SonosUngroupRequest,
    SonosVolumeRequest,
)
from app.api.common.serializers import _stream_url

router = APIRouter()


@router.post("/sonos/play")
def sonos_play(payload: SonosPlayRequest, request: Request) -> dict[str, bool]:
    services = _services(request)
    services["sonos"].play_stream(payload.speaker_ip, _stream_url(request))
    return {"ok": True}


@router.post("/sonos/stop")
def sonos_stop(payload: SonosStopRequest, request: Request) -> dict[str, bool]:
    _services(request)["sonos"].stop_stream(payload.speaker_ip)
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
