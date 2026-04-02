from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.common.dependencies import _services
from app.api.common.serializers import _serialize_state, _stream_url
from app.services.stream_engine import StreamEngine

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    services = _services(request)
    return {"status": "ok", "mode": services["engine"].state.mode.value}


@router.get("/state")
def state(request: Request) -> dict[str, Any]:
    services = _services(request)
    engine: StreamEngine = services["engine"]
    return _serialize_state(engine, _stream_url(request))
