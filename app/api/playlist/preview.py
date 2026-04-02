from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.common.dependencies import _services
from app.api.common.models import AddUrlRequest

router = APIRouter()


@router.post("/playlist/preview")
def playlist_preview(payload: AddUrlRequest, request: Request) -> dict[str, Any]:
    preview = _services(request)["playlist"].preview_playlist(str(payload.url))
    return {
        "provider": preview.provider,
        "source_url": preview.source_url,
        "title": preview.title,
        "channel": preview.channel,
        "thumbnail_url": preview.thumbnail_url,
        "entries": preview.entries,
        "count": len(preview.entries),
    }
