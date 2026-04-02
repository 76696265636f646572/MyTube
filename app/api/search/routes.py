from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.common.dependencies import _services

router = APIRouter()


@router.get("/search")
def search(
    request: Request,
    q: str = Query(min_length=1),
    limit: int = Query(default=10, ge=1, le=100),
    providers: str | None = Query(default=None),
) -> dict[str, Any]:
    selected_providers = [part.strip() for part in providers.split(",") if part.strip()] if providers else None
    yt_dlp_service = _services(request)["yt_dlp"]
    if hasattr(yt_dlp_service, "search"):
        results = yt_dlp_service.search(query=q, limit=limit, providers=selected_providers)
    else:
        results = yt_dlp_service.search_videos(query=q, limit=limit)
    return {"query": q, "count": len(results), "results": results}


@router.get("/search/youtube")
def search_youtube(
    request: Request,
    q: str = Query(min_length=1),
    limit: int = Query(default=10, ge=1, le=100),
) -> dict[str, Any]:
    # Backward-compatible endpoint shim.
    return search(request=request, q=q, limit=limit, providers="youtube")
