from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.api.common.dependencies import _services
from app.api.common.models import CookieSettingUpdateRequest
from app.services.yt_dlp_service import (
    cookie_setting_key,
    is_supported_cookie_provider,
    list_cookie_providers,
)

router = APIRouter()


@router.get("/settings/cookies")
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


@router.put("/settings/cookies")
def update_cookie_setting(payload: CookieSettingUpdateRequest, request: Request) -> dict[str, Any]:
    provider = payload.provider.strip().lower()
    if not is_supported_cookie_provider(provider):
        raise HTTPException(status_code=400, detail="Unsupported cookie provider")
    _services(request)["repo"].set_setting(cookie_setting_key(provider), payload.value)
    return {"ok": True, "provider": provider, "configured": True}


@router.delete("/settings/cookies/{provider}")
def delete_cookie_setting(provider: str, request: Request) -> dict[str, Any]:
    provider_key = provider.strip().lower()
    if not is_supported_cookie_provider(provider_key):
        raise HTTPException(status_code=400, detail="Unsupported cookie provider")
    _services(request)["repo"].clear_setting(cookie_setting_key(provider_key))
    return {"ok": True, "provider": provider_key, "configured": False}
