from __future__ import annotations

from typing import Any

from fastapi import Request


def _services(request: Request) -> dict[str, Any]:
    return {
        "repo": request.app.state.repository,
        "playlist": request.app.state.playlist_service,
        "engine": request.app.state.stream_engine,
        "settings": request.app.state.settings,
        "sonos": request.app.state.sonos_service,
        "yt_dlp": request.app.state.yt_dlp_service,
        "ui_events": request.app.state.ui_events,
        "binaries": request.app.state.binaries_service,
        "spotify_import": request.app.state.spotify_import_service,
        "source_resolver": request.app.state.source_resolver,
        "sendspin": request.app.state.sendspin_service,
    }
