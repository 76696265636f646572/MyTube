from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.db.repository import Repository
from app.main import create_app
from app.services.ffmpeg_pipeline import FfmpegPipeline
from app.services.playlist_service import PlaylistService
from app.services.source_resolver import MediaSourceResolver, normalize_http_url
from app.services.yt_dlp_service import YtDlpService


class FakeFfmpegProbe(FfmpegPipeline):
    def __init__(self) -> None:
        super().__init__("/bin/ffmpeg")

    def probe_audio_streams(self, source: str) -> dict:  # noqa: ARG002
        return {
            "has_audio": True,
            "duration_seconds": 12.4,
            "audio_stream_count": 1,
            "title": "Tagged",
            "artist": "Artist",
            "format_name": "mp3",
        }


def test_normalize_http_url_strips_fragment():
    assert "frag" not in normalize_http_url("https://ExAmple.com/foo.mp3#frag")


def test_settings_local_media_roots_list_accepts_comma_and_json():
    assert Settings(local_media_roots="/mnt").local_media_roots_list == ["/mnt"]
    assert Settings(local_media_roots="/a,/b").local_media_roots_list == ["/a", "/b"]
    assert Settings(local_media_roots='["/x","/y"]').local_media_roots_list == ["/x", "/y"]


def test_media_resolver_rejects_without_audio(monkeypatch, tmp_path):
    ffmpeg = FakeFfmpegProbe()
    root = tmp_path / "media"
    root.mkdir()
    resolver = MediaSourceResolver(ffmpeg, [str(root)])

    monkeypatch.setattr(
        ffmpeg,
        "probe_audio_streams",
        lambda s: {"has_audio": False, "duration_seconds": None, "title": None, "artist": None},
    )
    with pytest.raises(ValueError, match="audio"):
        resolver.resolve_http_media("https://example.com/x.mp3")


def test_media_resolver_local_outside_root(tmp_path):
    ffmpeg = FakeFfmpegProbe()
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    f = other / "a.mp3"
    f.write_bytes(b"x")
    resolver = MediaSourceResolver(ffmpeg, [str(allowed)])
    with pytest.raises(ValueError, match="outside"):
        resolver.resolve_local_file(str(f))


def test_media_resolver_local_missing_roots():
    ffmpeg = FakeFfmpegProbe()
    resolver = MediaSourceResolver(ffmpeg, [])
    with pytest.raises(ValueError, match="disabled"):
        resolver.resolve_local_file("/tmp/foo.mp3")


def test_playlist_dedupe_local_normalized_path(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/p.db")
    repo.init_db()
    root = tmp_path / "m"
    root.mkdir()
    audio = root / "track.mp3"
    audio.write_bytes(b"x")
    ffmpeg = FakeFfmpegProbe()
    resolver = MediaSourceResolver(ffmpeg, [str(root)])
    yt = MagicMock(spec=YtDlpService)
    yt.dispatcher = MagicMock()
    yt.is_playlist_url = MagicMock(return_value=False)
    pl = PlaylistService(repo, yt, resolver)
    playlist = repo.create_custom_playlist(title="T")
    pid = playlist.id
    pl.add_local_path_to_playlist(pid, str(audio), import_mode="add_all")
    r2 = pl.add_local_path_to_playlist(pid, str(audio), import_mode="skip_duplicates")
    assert r2.get("skipped_duplicates") is True
    entries = repo.list_playlist_entries(pid)
    assert len(entries) == 1


def test_playlist_dedupe_direct_normalized_url(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/p2.db")
    repo.init_db()
    ffmpeg = FakeFfmpegProbe()
    resolver = MediaSourceResolver(ffmpeg, [])
    yt = MagicMock(spec=YtDlpService)
    yt.dispatcher = MagicMock()
    yt.dispatcher.get_extractor = MagicMock(side_effect=ValueError("no"))
    yt.is_playlist_url = MagicMock(return_value=False)
    pl = PlaylistService(repo, yt, resolver)
    playlist = repo.create_custom_playlist(title="T")
    pid = playlist.id
    pl.add_item_to_playlist(pid, "https://example.com/same.mp3", import_mode="add_all")
    r2 = pl.add_item_to_playlist(pid, "https://example.com/same.mp3", import_mode="skip_duplicates")
    assert r2.get("skipped_duplicates") is True
    assert len(repo.list_playlist_entries(pid)) == 1


def test_queue_add_local_api(tmp_path):
    root = tmp_path / "m"
    root.mkdir()
    audio = root / "t.mp3"
    audio.write_bytes(b"x")
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/api.db",
        local_media_roots=str(root),
    )
    app = create_app(settings=settings, start_engine=False)
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        app.state.source_resolver = MediaSourceResolver(FakeFfmpegProbe(), [str(root)])
        app.state.playlist_service = PlaylistService(
            app.state.repository,
            app.state.yt_dlp_service,
            app.state.source_resolver,
        )
        r = client.post("/api/queue/add-local", json={"path": str(audio)})
        assert r.status_code == 200, r.text
        assert r.json().get("count") == 1


def test_local_roots_api(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/r.db",
        local_media_roots=str(root),
    )
    app = create_app(settings=settings, start_engine=False)
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        res = client.get("/api/media/local/roots")
        assert res.status_code == 200
        roots = res.json().get("roots")
        assert isinstance(roots, list) and len(roots) == 1
        assert roots[0]["path"] == str(root.resolve())


def test_browse_local_api(tmp_path):
    root = tmp_path / "br"
    root.mkdir()
    (root / "sub").mkdir()
    (root / "a.mp3").write_bytes(b"x")
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/b.db",
        local_media_roots=str(root),
    )
    app = create_app(settings=settings, start_engine=False)
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        res = client.get("/api/media/local/browse", params={"path": str(root)})
        assert res.status_code == 200
        data = res.json()
        names = {e["name"] for e in data["entries"]}
        assert "sub" in names and "a.mp3" in names
