from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.db.repository import Repository
from app.services.spotify_import_service import SpotifyImportService, is_pending_spotify_import_url
from app.services.yt_dlp_service import PlaylistPreview, ResolvedTrack


@dataclass
class FakeYtDlp:
    hits_by_provider: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def is_playlist_url(self, url: str) -> bool:
        return False

    def resolve_video(self, url: str, force_refresh: bool = False) -> ResolvedTrack:
        _ = force_refresh
        return ResolvedTrack(
            source_url=url,
            normalized_url=url,
            title="x",
            channel="y",
            duration_seconds=1,
            thumbnail_url=None,
            stream_url="http://ex",
            provider="youtube",
            provider_item_id="v",
        )

    def preview_playlist(self, url: str) -> PlaylistPreview:
        return PlaylistPreview(source_url=url, title="p", channel="c", entries=[])

    def list_youtube_user_playlists(self) -> list:
        return []

    def search_single_provider(self, query: str, *, provider: str, limit: int = 10) -> list[dict[str, Any]]:
        _ = query, limit
        base = self.hits_by_provider.get(provider, [])
        return list(base)


def test_start_import_creates_pending_rows(tmp_path, monkeypatch):
    meta = {
        "source_url": "https://open.spotify.com/playlist/testpl",
        "title": "My PL",
        "channel": "Owner",
        "thumbnail_url": "https://example.com/thumb.jpg",
    }
    tracks = [
        {
            "spotify_track_id": "tr1",
            "title": "Song One",
            "channel": "Artist A",
            "duration_seconds": 120,
            "thumbnail_url": None,
        },
        {
            "spotify_track_id": "tr2",
            "title": "Song Two",
            "channel": "Artist B",
            "duration_seconds": 121,
            "thumbnail_url": None,
        },
    ]

    def fake_fetch(pid: str):
        assert pid == "testpl"
        return meta, tracks

    monkeypatch.setattr("app.services.spotify_import_service.fetch_spotify_playlist_tracks", fake_fetch)

    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/simport.db")
    repo.init_db()
    svc = SpotifyImportService(repo, FakeYtDlp())
    out = svc.start_import("https://open.spotify.com/playlist/testpl")
    assert out["track_count"] == 2
    pid = out["playlist_id"]
    entries = repo.list_playlist_entries(UUID(pid))
    assert len(entries) == 2
    assert all(is_pending_spotify_import_url(e.source_url) for e in entries)
    assert entries[0].position == 1
    assert entries[0].provider_item_id == "tr1"


def test_advance_applies_first_youtube_hit(tmp_path, monkeypatch):
    meta = {
        "source_url": "https://open.spotify.com/playlist/p2",
        "title": "PL",
        "channel": "O",
        "thumbnail_url": None,
    }
    tracks = [
        {
            "spotify_track_id": "t1",
            "title": "Alpha",
            "channel": "Beta",
            "duration_seconds": 60,
            "thumbnail_url": None,
        },
    ]

    monkeypatch.setattr(
        "app.services.spotify_import_service.fetch_spotify_playlist_tracks",
        lambda _pid: (meta, tracks),
    )

    hit = {
        "provider": "youtube",
        "provider_item_id": "vid1",
        "source_url": "https://www.youtube.com/watch?v=vid1",
        "normalized_url": "https://www.youtube.com/watch?v=vid1",
        "title": "Alpha",
        "channel": "Beta",
        "duration_seconds": 60,
        "thumbnail_url": None,
    }
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/simport2.db")
    repo.init_db()
    ytdlp = FakeYtDlp(hits_by_provider={"youtube": [hit], "soundcloud": [], "mixcloud": []})
    svc = SpotifyImportService(repo, ytdlp)
    out = svc.start_import("https://open.spotify.com/playlist/p2")
    pl_uuid = UUID(out["playlist_id"])

    snap = svc.advance(pl_uuid)
    assert snap["search_done"] is True
    assert snap["items"][0]["status"] == "matched"
    entry_row = repo.list_playlist_entries(pl_uuid)[0]
    assert not is_pending_spotify_import_url(entry_row.source_url)
    assert entry_row.provider == "youtube"
