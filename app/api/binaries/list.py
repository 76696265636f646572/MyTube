from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.common.dependencies import _services
from app.services.stream_engine import PlaybackMode, StreamEngine

router = APIRouter()


def _is_binary_in_use(name: str, engine: StreamEngine) -> bool:
    """True if the binary is currently running (e.g. ffmpeg/yt-dlp during playback)."""
    if engine.state.mode != PlaybackMode.playing:
        return False
    return name in ("ffmpeg", "yt-dlp")


@router.get("/binaries")
def list_binaries(request: Request) -> dict[str, list[dict[str, Any]]]:
    services = _services(request)
    binaries = services["binaries"].get_binaries()
    engine: StreamEngine = services["engine"]
    return {
        "binaries": [
            {
                "name": b.name,
                "path": b.path,
                "version": b.version,
                "is_system": b.is_system,
                "in_use": _is_binary_in_use(b.name, engine),
            }
            for b in binaries
        ]
    }
