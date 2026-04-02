from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.api.common.dependencies import _services
from app.api.common.models import InstallBinaryRequest
from app.api.common.serializers import _publish_ui_snapshot
from app.services.stream_engine import StreamEngine

router = APIRouter()


@router.post("/binaries/install")
def install_binary(payload: InstallBinaryRequest, request: Request) -> dict[str, Any]:
    services = _services(request)
    svc = services["binaries"]
    engine: StreamEngine = services["engine"]

    # Stop playback first if requested (ffmpeg/yt-dlp may be in use)
    if payload.stop_stream_first and payload.name in ("ffmpeg", "yt-dlp"):
        engine.skip_current()
        time.sleep(2)

    try:
        svc.install(payload.name)
        _publish_ui_snapshot(request)
        return {"ok": True, "name": payload.name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OSError as e:
        if e.errno == 26:  # errno.ETXTBSY - Text file busy
            raise HTTPException(
                status_code=409,
                detail="binary_in_use",
            )
        raise HTTPException(status_code=500, detail=str(e))
