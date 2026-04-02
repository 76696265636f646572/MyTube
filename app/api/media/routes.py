from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.common.dependencies import _services

router = APIRouter()


@router.get("/media/local/roots")
def list_local_media_roots(request: Request) -> dict[str, Any]:
    resolver = _services(request)["source_resolver"]
    return {"roots": resolver.list_roots_payload()}


@router.get("/media/local/browse")
def browse_local_media(request: Request, path: str = Query(..., min_length=1)) -> dict[str, Any]:
    resolver = _services(request)["source_resolver"]
    try:
        return resolver.browse_directory(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
