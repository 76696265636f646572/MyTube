from __future__ import annotations

from fastapi import APIRouter

from app.api.binaries.install import router as binaries_install_router
from app.api.binaries.list import router as binaries_list_router
from app.api.binaries.updates import router as binaries_updates_router
from app.api.history.routes import router as history_router
from app.api.media.routes import router as media_router
from app.api.playback.routes import router as playback_router
from app.api.playlist.imports import router as playlist_imports_router
from app.api.playlist.preview import router as playlist_preview_router
from app.api.playlists.routes import router as playlists_router
from app.api.queue.routes import router as queue_router
from app.api.search.routes import router as search_router
from app.api.settings.cookies import router as cookie_settings_router
from app.api.sonos.playback import router as sonos_playback_router
from app.api.sonos.settings import router as sonos_settings_router
from app.api.sonos.speakers import router as sonos_speakers_router
from app.api.spotify.imports import router as spotify_imports_router
from app.api.system.routes import router as system_router
from app.api.ws.events import router as ws_events_router

api_router = APIRouter()

api_router.include_router(system_router)
api_router.include_router(binaries_list_router)
api_router.include_router(binaries_updates_router)
api_router.include_router(binaries_install_router)
api_router.include_router(cookie_settings_router)
api_router.include_router(queue_router)
api_router.include_router(media_router)
api_router.include_router(playback_router)
api_router.include_router(history_router)
api_router.include_router(playlist_preview_router)
api_router.include_router(playlist_imports_router)
api_router.include_router(spotify_imports_router)
api_router.include_router(playlists_router)
api_router.include_router(ws_events_router)
api_router.include_router(search_router)
api_router.include_router(sonos_speakers_router)
api_router.include_router(sonos_playback_router)
api_router.include_router(sonos_settings_router)
