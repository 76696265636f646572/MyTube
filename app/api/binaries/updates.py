from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.common.dependencies import _services

router = APIRouter()


@router.get("/binaries/updates")
def list_binary_updates(request: Request) -> dict[str, list[dict[str, Any]]]:
    updates = _services(request)["binaries"].get_updates()
    return {
        "updates": [
            {"name": u.name, "current": u.current, "latest": u.latest, "has_update": u.has_update}
            for u in updates
        ]
    }
