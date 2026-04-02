from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.common.dependencies import _services
from app.api.common.serializers import _serialize_sonos_speaker

router = APIRouter()


@router.get("/sonos/speakers")
def sonos_speakers(request: Request) -> list[dict[str, Any]]:
    speakers = _services(request)["sonos"].discover_speakers()
    speakers_by_uid = {speaker.uid: speaker for speaker in speakers}
    return [_serialize_sonos_speaker(speaker, speakers_by_uid) for speaker in speakers]
