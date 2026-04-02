from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.common.dependencies import _services
from app.api.common.models import AddUrlRequest
from app.api.common.serializers import _publish_ui_snapshot

router = APIRouter()


@router.post("/playlist/import")
def playlist_import(payload: AddUrlRequest, request: Request) -> dict[str, Any]:
    result = _services(request)["playlist"].import_playlist(
        str(payload.url),
        target_playlist_id=payload.target_playlist_id,
        import_mode=payload.import_mode,
    )
    if not result.get("has_duplicates"):
        _publish_ui_snapshot(request)
    if result.get("has_duplicates"):
        return result
    return {"ok": True, **result}
