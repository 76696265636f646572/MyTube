from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.common.serializers import build_ui_snapshot, render_frontend_shell
from app.api.root import root_router
from app.api.routes import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.repository import Repository
from app.services.binaries_service import BinariesService
from app.services.ffmpeg_pipeline import FfmpegPipeline
from app.services.playlist_service import PlaylistService
from app.services.sendspin_service import SendspinServerService
from app.services.source_resolver import MediaSourceResolver
from app.services.spotify_import_service import SpotifyImportService
from app.services.sonos_service import SonosService
from app.services.stream_engine import StreamEngine
from app.services.sync_service import SyncService
from app.services.ui_events import UiEventBroker
from app.services.yt_dlp_service import YtDlpService

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
FRONTEND_DIST_DIR = STATIC_DIR / "dist"


def _frontend_bundle_exists(dist_dir: Path | None = None) -> bool:
    dist_dir = dist_dir or FRONTEND_DIST_DIR
    return (dist_dir / "app.css").is_file() and (dist_dir / "app.js").is_file()


def _register_frontend_asset_fallbacks(app: FastAPI, dist_dir: Path | None = None) -> None:
    dist_dir = dist_dir or FRONTEND_DIST_DIR
    if _frontend_bundle_exists(dist_dir):
        return

    @app.get("/static/dist/app.css", include_in_schema=False)
    async def frontend_css_fallback() -> Response:
        return Response("/* Frontend bundle not built. */\n", media_type="text/css")

    @app.get("/static/dist/app.js", include_in_schema=False)
    async def frontend_js_fallback() -> Response:
        body = (
            "const root = document.getElementById('app');\n"
            "if (root && !root.hasChildNodes()) {\n"
            "  root.textContent = 'Frontend assets are not built.';\n"
            "}\n"
        )
        return Response(body, media_type="application/javascript")


def create_app(settings: Settings | None = None, start_engine: bool = True) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    repository = Repository(settings.db_url)
    ffmpeg_path = settings.ffmpeg_path
    yt_dlp_service = YtDlpService(
        settings.yt_dlp_path,
        ffmpeg_path,
        settings.deno_path,
        repository=repository,
    )
    ffmpeg_pipeline = FfmpegPipeline(ffmpeg_path, settings.ffprobe_path, bitrate=settings.mp3_bitrate)
    ui_events = UiEventBroker()

    def notify_ui_state_changed() -> None:
        ui_events.publish_snapshot(settings.public_base_url)
        if sendspin_service and sendspin_service.is_running:
            try:
                sendspin_service.push_state_update()
            except Exception:
                pass

    stream_engine = StreamEngine(
        repository=repository,
        yt_dlp_service=yt_dlp_service,
        ffmpeg_pipeline=ffmpeg_pipeline,
        chunk_size=settings.chunk_size,
        stream_queue_size=settings.stream_queue_size,
        queue_poll_seconds=settings.queue_poll_seconds,
        stats_log_seconds=settings.stream_stats_log_seconds,
        on_state_change=notify_ui_state_changed,
    )
    source_resolver = MediaSourceResolver(ffmpeg_pipeline, settings.local_media_roots_list)
    playlist_service = PlaylistService(repository, yt_dlp_service, source_resolver)
    spotify_import_service = SpotifyImportService(repository, yt_dlp_service)
    sync_service = SyncService(
        repository=repository,
        yt_dlp_service=yt_dlp_service,
        spotify_import_service=spotify_import_service,
        interval_seconds=settings.playlist_sync_interval_seconds,
        max_concurrent=settings.playlist_sync_max_concurrent,
    )
    sendspin_service: SendspinServerService | None = None
    if settings.sendspin_enabled:
        sendspin_service = SendspinServerService(
            stream_engine=stream_engine,
            ffmpeg_pipeline=ffmpeg_pipeline,
            server_name=settings.sendspin_name,
            port=settings.sendspin_port,
            mdns_enabled=settings.sendspin_mdns_enabled,
            on_clients_changed=notify_ui_state_changed,
        )

    sonos_service = SonosService()
    binaries_service = BinariesService(
        yt_dlp_path=settings.yt_dlp_path,
        ffmpeg_path=settings.ffmpeg_path,
        ffprobe_path=settings.ffprobe_path,
        deno_path=settings.deno_path,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository.init_db()
        ui_events.bind_loop(asyncio.get_running_loop())
        sync_task: asyncio.Task[None] | None = None

        async def snapshot_builder(base_url: str) -> dict[str, object]:
            return build_ui_snapshot(app, base_url)

        ui_events.set_snapshot_builder(snapshot_builder)
        if start_engine:
            stream_engine.start()
        app.state.settings = settings
        app.state.repository = repository
        app.state.yt_dlp_service = yt_dlp_service
        app.state.ffmpeg_pipeline = ffmpeg_pipeline
        app.state.stream_engine = stream_engine
        app.state.playlist_service = playlist_service
        app.state.source_resolver = source_resolver
        app.state.spotify_import_service = spotify_import_service
        app.state.sync_service = sync_service
        app.state.sonos_service = sonos_service
        app.state.binaries_service = binaries_service
        app.state.ui_events = ui_events
        app.state.sendspin_service = sendspin_service
        sync_task = asyncio.create_task(sync_service.run_forever(), name="playlist-sync")
        app.state.sync_task = sync_task
        if sendspin_service and start_engine:
            await sendspin_service.start(asyncio.get_running_loop())
        try:
            yield
        except asyncio.CancelledError:
            # Uvicorn may cancel lifespan tasks during reload/shutdown.
            # Treat this as a normal shutdown path.
            pass
        finally:
            if sendspin_service:
                try:
                    await sendspin_service.stop()
                except Exception:
                    pass
            try:
                sync_service.stop()
                if sync_task is not None:
                    await asyncio.wait_for(sync_task, timeout=5)
            except asyncio.TimeoutError:
                if sync_task is not None:
                    sync_task.cancel()
            except Exception:
                pass
            if start_engine:
                stream_engine.stop()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(root_router)
    app.include_router(api_router, prefix="/api")
    _register_frontend_asset_fallbacks(app)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/site.webmanifest", include_in_schema=False)
    def serve_manifest():
        return FileResponse(STATIC_DIR / "site.webmanifest", media_type="application/manifest+json")

    @app.get("/{frontend_path:path}", include_in_schema=False)
    def frontend_route_fallback(frontend_path: str, request: Request):
        first_segment = frontend_path.split("/", 1)[0]
        if not frontend_path or first_segment == "api" or "." in first_segment:
            raise HTTPException(status_code=404, detail="Not Found")
        return render_frontend_shell(request)

    return app
