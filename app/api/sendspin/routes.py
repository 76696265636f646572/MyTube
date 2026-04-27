from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.common.dependencies import _services
from app.api.common.serializers import _publish_ui_snapshot

router = APIRouter(prefix="/sendspin", tags=["sendspin"])


class VolumeBody(BaseModel):
    volume: int = Field(ge=0, le=100)


class MuteBody(BaseModel):
    muted: bool


@router.get("/clients")
def list_clients(request: Request):
    settings = _services(request)["settings"]
    svc = _services(request)["sendspin"]
    base = {
        "clients": [],
        "group": {"volume": 0, "muted": False},
        "port": settings.sendspin_port,
        "enabled": settings.sendspin_enabled,
    }
    if svc:
        base.update({
            "clients": svc.list_clients(),
            "group": svc.get_group_state(),
        })
    return base


@router.post("/clients/{client_id}/volume")
def set_client_volume(client_id: str, body: VolumeBody, request: Request):
    svc = _services(request)["sendspin"]
    if not svc:
        raise HTTPException(status_code=503, detail="SendSpin not enabled")
    if not svc.set_client_volume(client_id, body.volume):
        raise HTTPException(status_code=404, detail="Client not found or has no player role")
    _publish_ui_snapshot(request)
    return {"ok": True}


@router.post("/clients/{client_id}/mute")
def set_client_mute(client_id: str, body: MuteBody, request: Request):
    svc = _services(request)["sendspin"]
    if not svc:
        raise HTTPException(status_code=503, detail="SendSpin not enabled")
    if not svc.set_client_muted(client_id, body.muted):
        raise HTTPException(status_code=404, detail="Client not found or has no player role")
    _publish_ui_snapshot(request)
    return {"ok": True}


@router.post("/group/volume")
def set_group_volume(body: VolumeBody, request: Request):
    svc = _services(request)["sendspin"]
    if not svc:
        raise HTTPException(status_code=503, detail="SendSpin not enabled")
    svc.set_group_volume(body.volume)
    _publish_ui_snapshot(request)
    return {"ok": True}


@router.post("/group/mute")
def set_group_mute(body: MuteBody, request: Request):
    svc = _services(request)["sendspin"]
    if not svc:
        raise HTTPException(status_code=503, detail="SendSpin not enabled")
    svc.set_group_muted(body.muted)
    _publish_ui_snapshot(request)
    return {"ok": True}
