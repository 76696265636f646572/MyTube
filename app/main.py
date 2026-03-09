from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.repository import Repository
from app.services.ffmpeg_pipeline import FfmpegPipeline
from app.services.ffmpeg_setup import ensure_ffmpeg_path
from app.services.playlist_service import PlaylistService
from app.services.sonos_service import SonosService
from app.services.stream_engine import StreamEngine
from app.services.yt_dlp_service import YtDlpService


def create_app(settings: Settings | None = None, start_engine: bool = True) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    repository = Repository(settings.db_url)
    yt_dlp_service = YtDlpService(settings.yt_dlp_path)
    ffmpeg_path = ensure_ffmpeg_path(settings.ffmpeg_path)
    ffmpeg_pipeline = FfmpegPipeline(ffmpeg_path, bitrate=settings.mp3_bitrate)
    stream_engine = StreamEngine(
        repository=repository,
        yt_dlp_service=yt_dlp_service,
        ffmpeg_pipeline=ffmpeg_pipeline,
        chunk_size=settings.chunk_size,
        queue_poll_seconds=settings.queue_poll_seconds,
        stats_log_seconds=settings.stream_stats_log_seconds,
    )
    playlist_service = PlaylistService(repository, yt_dlp_service)
    sonos_service = SonosService()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository.init_db()
        if start_engine:
            stream_engine.start()
        app.state.settings = settings
        app.state.repository = repository
        app.state.yt_dlp_service = yt_dlp_service
        app.state.ffmpeg_pipeline = ffmpeg_pipeline
        app.state.stream_engine = stream_engine
        app.state.playlist_service = playlist_service
        app.state.sonos_service = sonos_service
        try:
            yield
        except asyncio.CancelledError:
            # Uvicorn may cancel lifespan tasks during reload/shutdown.
            # Treat this as a normal shutdown path.
            pass
        finally:
            if start_engine:
                stream_engine.stop()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    return app
