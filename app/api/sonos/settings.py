from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.api.common.dependencies import _services
from app.api.common.models import SonosSettingPatchRequest
from app.services.sonos_service import SonosSettingsError

router = APIRouter()


@router.get("/sonos/settings/{speaker_ip}")
def sonos_get_settings(speaker_ip: str, request: Request) -> dict[str, Any]:
    return _services(request)["sonos"].get_speaker_settings(speaker_ip)


@router.patch("/sonos/settings/{speaker_ip}")
def sonos_patch_settings(
    speaker_ip: str,
    payload: SonosSettingPatchRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        updated = _services(request)["sonos"].update_speaker_setting(
            speaker_ip,
            payload.setting,
            payload.value,
        )
    except SonosSettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "setting": payload.setting, "value": updated}
