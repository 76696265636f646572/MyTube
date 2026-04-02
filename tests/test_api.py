from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.common.serializers import _serialize_state
from app.core.config import Settings
from app.main import create_app


def test_health_and_state_endpoints(tmp_path):
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/api.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
    )
    app = create_app(settings=settings, start_engine=False)
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        state = client.get("/api/state")
        assert state.status_code == 200
        payload = state.json()
        assert payload["mode"] in ("idle", "playing")
        assert payload["paused"] in (True, False)
        assert payload["repeat_mode"] in ("off", "all", "one")
        assert payload["shuffle_enabled"] in (True, False)
        assert payload["stream_url"].endswith("/stream/live.mp3")


def test_serialize_state_prefers_hq_youtube_thumbnail_over_maxres():
    engine = SimpleNamespace(
        state=SimpleNamespace(
            mode=SimpleNamespace(value="playing"),
            paused=False,
            repeat_mode=SimpleNamespace(value="off"),
            shuffle_enabled=False,
            now_playing_id=1,
            now_playing_title="t",
            now_playing_channel=None,
            now_playing_thumbnail_url="https://i.ytimg.com/vi/abc123/maxresdefault.jpg",
            now_playing_is_live=False,
            now_playing_duration_seconds=60,
        ),
        playback_progress=lambda: {
            "duration_seconds": 60,
            "started_at": None,
            "elapsed_seconds": None,
            "progress_percent": None,
        },
    )
    out = _serialize_state(engine, "http://example.com/stream/live.mp3")
    assert out["now_playing_thumbnail_url"] == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"
