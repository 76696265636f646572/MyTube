from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from app.api.common.dependencies import _services
from app.api.common.responses import GracefulStreamingResponse
from app.api.common.serializers import render_frontend_shell

root_router = APIRouter()


@root_router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return render_frontend_shell(request)


@root_router.get("/stream/live.mp3")
def stream_live(request: Request) -> StreamingResponse:
    engine = _services(request)["engine"]
    return GracefulStreamingResponse(
        engine.subscribe(),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",
        },
    )
