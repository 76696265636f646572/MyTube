from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class _FakeMusicAtlasClient:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.similar_tracks_calls: list[dict[str, Any]] = []
        self.similar_tracks_multi_calls: list[list[dict[str, str]]] = []

    def similar_tracks(self, *, artist: str, track: str, embed: int | None = None) -> dict[str, Any]:
        self.similar_tracks_calls.append({"artist": artist, "track": track, "embed": embed})
        return {
            "success": True,
            "matches": [
                {
                    "artist": "Seed Artist",
                    "title": "Match One",
                    "platform_ids": {"youtube": "abc123def"},
                }
            ],
        }

    def similar_tracks_multi(self, *, liked_tracks: list[dict[str, str]], disliked_tracks: list | None = None):
        self.similar_tracks_multi_calls.append(list(liked_tracks))
        return {
            "success": True,
            "matches": [
                {
                    "artist": "Other",
                    "title": "Multi Match",
                    "platform_ids": {"youtube": "zztop11"},
                    "atlas_similarity": 0.91,
                }
            ],
        }


def test_musicatlas_status_feature_disabled(tmp_path) -> None:
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/musicatlas_status_disabled.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        musicatlas_api_key="",
    )
    app = create_app(settings=settings, start_engine=False)
    with TestClient(app) as client:
        r = client.get("/api/musicatlas/status")
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is False
    assert "not configured" in (data.get("message") or "").lower()


def test_musicatlas_status_with_mock_client(tmp_path) -> None:
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/musicatlas_status_enabled.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        musicatlas_api_key="dummy-key",
    )
    app = create_app(settings=settings, start_engine=False)
    fake = _FakeMusicAtlasClient()
    with TestClient(app) as client:
        app.state.musicatlas_client = fake
        r = client.get("/api/musicatlas/status")
    assert r.status_code == 200
    data = r.json()
    assert data == {"enabled": True, "message": None}
    assert fake.similar_tracks_calls == []
    assert fake.similar_tracks_multi_calls == []


def test_musicatlas_suggestions_feature_disabled(tmp_path) -> None:
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/musicatlas_routes.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        musicatlas_api_key="",
    )
    app = create_app(settings=settings, start_engine=False)
    with TestClient(app) as client:
        r = client.get("/api/musicatlas/suggestions", params={"artist": "A", "track": "B"})
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is False
    assert data["items"] == []
    assert "not configured" in (data.get("message") or "").lower()


def test_musicatlas_suggestions_with_mock_client(tmp_path) -> None:
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/musicatlas_routes2.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        musicatlas_api_key="dummy-key",
    )
    app = create_app(settings=settings, start_engine=False)
    fake = _FakeMusicAtlasClient()
    with TestClient(app) as client:
        app.state.musicatlas_client = fake
        r = client.get("/api/musicatlas/suggestions", params={"artist": "Radiohead", "track": "Creep"})
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is True
    assert data["seed"] == {"artist": "Radiohead", "track": "Creep"}
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["title"] == "Match One"
    assert item["provider_item_id"] == "abc123def"
    assert item["source_url"] == "https://www.youtube.com/watch?v=abc123def"
    assert fake.similar_tracks_calls == [{"artist": "Radiohead", "track": "Creep", "embed": None}]
    assert data.get("catalog_ingestion") is None


def test_musicatlas_suggestions_use_now_playing_seed(tmp_path) -> None:
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/musicatlas_routes3.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        musicatlas_api_key="k",
    )
    app = create_app(settings=settings, start_engine=False)
    fake = _FakeMusicAtlasClient()
    with TestClient(app) as client:
        app.state.musicatlas_client = fake
        app.state.stream_engine.state.now_playing_channel = "Live Artist"
        app.state.stream_engine.state.now_playing_title = "Live Title"
        r = client.get("/api/musicatlas/suggestions")
    assert r.status_code == 200
    data = r.json()
    assert data["seed"] == {"artist": "Live Artist", "track": "Live Title"}
    assert fake.similar_tracks_calls[0]["artist"] == "Live Artist"


def test_musicatlas_suggestions_bad_embed(tmp_path) -> None:
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/musicatlas_routes4.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        musicatlas_api_key="k",
    )
    app = create_app(settings=settings, start_engine=False)
    with TestClient(app) as client:
        app.state.musicatlas_client = _FakeMusicAtlasClient()
        r = client.get("/api/musicatlas/suggestions", params={"artist": "A", "track": "B", "embed": 2})
    assert r.status_code == 400


def test_musicatlas_generate_playlist_disabled(tmp_path) -> None:
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/musicatlas_routes5.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        musicatlas_api_key="",
    )
    app = create_app(settings=settings, start_engine=False)
    with TestClient(app) as client:
        r = client.post("/api/musicatlas/generate-playlist", json={})
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_musicatlas_generate_playlist_no_seeds_returns_400(tmp_path) -> None:
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/musicatlas_routes7.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        musicatlas_api_key="k",
    )
    app = create_app(settings=settings, start_engine=False)
    with TestClient(app) as client:
        app.state.musicatlas_client = _FakeMusicAtlasClient()
        r = client.post(
            "/api/musicatlas/generate-playlist",
            json={"include_now_playing": False, "history_limit": 5},
        )
    assert r.status_code == 400


def test_musicatlas_generate_playlist_with_mock_client(tmp_path) -> None:
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/musicatlas_routes6.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        musicatlas_api_key="k",
    )
    app = create_app(settings=settings, start_engine=False)
    fake = _FakeMusicAtlasClient()
    with TestClient(app) as client:
        app.state.musicatlas_client = fake
        app.state.stream_engine.state.now_playing_channel = "Chan"
        app.state.stream_engine.state.now_playing_title = "Song"
        r = client.post("/api/musicatlas/generate-playlist", json={})
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is True
    assert data["seeds"] == [{"artist": "Chan", "title": "Song"}]
    assert len(data["items"]) == 1
    assert data["items"][0]["atlas_similarity"] == 0.91
    assert len(fake.similar_tracks_multi_calls) == 1
    assert fake.similar_tracks_multi_calls[0][0]["artist"] == "Chan"


class _FakeMusicAtlasCatalogClient:
    """similar_tracks reports not in catalog; supports add_track / add_track_progress."""

    enabled = True

    def __init__(self, *, add_conflict: bool = False) -> None:
        self.similar_tracks_calls: list[dict[str, Any]] = []
        self.add_track_calls: list[dict[str, str]] = []
        self.add_track_progress_calls: list[str] = []
        self._add_conflict = add_conflict
        self._progress_hits = 0

    def similar_tracks(self, *, artist: str, track: str, embed: int | None = None) -> dict[str, Any]:
        self.similar_tracks_calls.append({"artist": artist, "track": track, "embed": embed})
        return {"success": True, "in_catalog": False, "matches": [], "message": "not in catalog"}

    def similar_tracks_multi(self, *, liked_tracks: list[dict[str, str]], disliked_tracks: list | None = None):
        raise AssertionError("not used")

    def add_track(self, *, artist: str, title: str) -> tuple[int, dict[str, Any]]:
        self.add_track_calls.append({"artist": artist, "title": title})
        if self._add_conflict:
            return (409, {"message": "already indexed"})
        return (200, {"success": True, "job_id": "job_catalog_1", "message": "accepted"})

    def add_track_progress(self, *, job_id: str) -> dict[str, Any]:
        self.add_track_progress_calls.append(job_id)
        self._progress_hits += 1
        if self._progress_hits == 1:
            return {"status": "queued", "percent_complete": 0, "message": "waiting"}
        return {"status": "done", "percent_complete": 100, "message": "ready"}


def test_musicatlas_suggestions_not_in_catalog_starts_job(tmp_path) -> None:
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/musicatlas_cat1.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        musicatlas_api_key="k",
    )
    app = create_app(settings=settings, start_engine=False)
    fake = _FakeMusicAtlasCatalogClient()
    with TestClient(app) as client:
        app.state.musicatlas_client = fake
        r = client.get("/api/musicatlas/suggestions", params={"artist": "A", "track": "Song"})
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is True
    assert data["items"] == []
    assert "not in catalog" in (data.get("notice") or "")
    ci = data.get("catalog_ingestion")
    assert ci is not None
    assert ci["job_id"] == "job_catalog_1"
    assert ci["status"] == "queued"
    assert ci["terminal"] is False
    assert len(fake.add_track_calls) == 1
    assert fake.add_track_calls[0] == {"artist": "A", "title": "Song"}
    assert fake.add_track_progress_calls == ["job_catalog_1"]


def test_musicatlas_suggestions_dedupes_add_track_while_active(tmp_path) -> None:
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/musicatlas_cat2.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        musicatlas_api_key="k",
    )
    app = create_app(settings=settings, start_engine=False)
    fake = _FakeMusicAtlasCatalogClient()
    with TestClient(app) as client:
        app.state.musicatlas_client = fake
        r1 = client.get("/api/musicatlas/suggestions", params={"artist": "A", "track": "Song"})
        assert r1.json()["catalog_ingestion"]["status"] == "queued"
        r2 = client.get("/api/musicatlas/suggestions", params={"artist": "A", "track": "Song"})
    assert r2.status_code == 200
    assert r2.json()["catalog_ingestion"]["status"] == "done"
    assert len(fake.add_track_calls) == 1
    assert fake.add_track_progress_calls == ["job_catalog_1", "job_catalog_1"]


def test_musicatlas_suggestions_poll_by_catalog_job_id(tmp_path) -> None:
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/musicatlas_cat3.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        musicatlas_api_key="k",
    )
    app = create_app(settings=settings, start_engine=False)
    fake = _FakeMusicAtlasCatalogClient()
    with TestClient(app) as client:
        app.state.musicatlas_client = fake
        client.get("/api/musicatlas/suggestions", params={"artist": "X", "track": "Y"})
        r_poll = client.get(
            "/api/musicatlas/suggestions",
            params={"catalog_job_id": "job_catalog_1", "artist": "X", "track": "Y"},
        )
    assert r_poll.status_code == 200
    body = r_poll.json()
    assert body["catalog_ingestion"]["job_id"] == "job_catalog_1"
    assert body["seed"] == {"artist": "X", "track": "Y"}
    assert body["items"] == []
    assert fake.similar_tracks_calls == [{"artist": "X", "track": "Y", "embed": None}]


def test_musicatlas_suggestions_unknown_catalog_job_id(tmp_path) -> None:
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/musicatlas_cat4.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        musicatlas_api_key="k",
    )
    app = create_app(settings=settings, start_engine=False)
    with TestClient(app) as client:
        app.state.musicatlas_client = _FakeMusicAtlasCatalogClient()
        r = client.get("/api/musicatlas/suggestions", params={"catalog_job_id": "nope"})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "musicatlas_unknown_catalog_job"


def test_musicatlas_suggestions_add_track_conflict(tmp_path) -> None:
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/musicatlas_cat5.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        musicatlas_api_key="k",
    )
    app = create_app(settings=settings, start_engine=False)
    fake = _FakeMusicAtlasCatalogClient(add_conflict=True)
    with TestClient(app) as client:
        app.state.musicatlas_client = fake
        r = client.get("/api/musicatlas/suggestions", params={"artist": "A", "track": "Song"})
    assert r.status_code == 200
    data = r.json()
    ci = data["catalog_ingestion"]
    assert ci["terminal"] is True
    assert ci["status"] == "conflict"
    assert ci["job_id"] is None
    assert "already" in (ci.get("message") or "").lower()
    assert fake.add_track_progress_calls == []
