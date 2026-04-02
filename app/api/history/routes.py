from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.common.dependencies import _services
from app.api.common.serializers import _publish_ui_snapshot, _serialize_history_rows

router = APIRouter()


@router.get("/history")
def history(request: Request) -> list[dict[str, Any]]:
    services = _services(request)
    rows = services["repo"].list_history(limit=services["settings"].history_limit)
    return _serialize_history_rows(rows)


@router.delete("/history")
def clear_history(request: Request) -> dict[str, bool]:
    _services(request)["repo"].clear_history()
    _publish_ui_snapshot(request)
    return {"ok": True}
