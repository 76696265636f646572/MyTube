from dataclasses import dataclass

from app.db.repository import Repository
from app.services.playlist_service import PlaylistService
from app.services.yt_dlp_service import PlaylistPreview, ResolvedTrack


@dataclass
class FakeYtDlp:
    playlist: bool = False

    def is_playlist_url(self, url: str) -> bool:
        return self.playlist

    def resolve_video(self, url: str) -> ResolvedTrack:
        return ResolvedTrack(
            source_url=url,
            normalized_url=url,
            title="one",
            channel="chan",
            duration_seconds=100,
            thumbnail_url=None,
            stream_url="http://example/audio",
        )

    def preview_playlist(self, url: str) -> PlaylistPreview:
        return PlaylistPreview(
            source_url=url,
            title="pl",
            channel="chan",
            entries=[
                {
                    "source_url": "https://youtube.com/watch?v=1",
                    "normalized_url": "https://youtube.com/watch?v=1",
                    "title": "t1",
                    "channel": "ch1",
                    "duration_seconds": 60,
                    "thumbnail_url": None,
                },
                {
                    "source_url": "https://youtube.com/watch?v=2",
                    "normalized_url": "https://youtube.com/watch?v=2",
                    "title": "t2",
                    "channel": "ch2",
                    "duration_seconds": 61,
                    "thumbnail_url": None,
                },
            ],
        )


def test_add_single_video(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/playlist.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=False))

    result = service.add_url("https://youtube.com/watch?v=abc")
    assert result["type"] == "video"
    assert result["count"] == 1
    queue = repo.list_queue()
    assert len(queue) == 1
    assert queue[0].title == "one"


def test_import_playlist(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/playlist2.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=True))

    result = service.add_url("https://youtube.com/playlist?list=x")
    assert result["type"] == "playlist"
    assert result["count"] == 2
    queue = repo.list_queue()
    assert len(queue) == 2


def test_update_playlist_rename_and_pin(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/update_pl.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=False))

    created = service.create_custom_playlist("Original")
    pid = created["id"]
    assert created["title"] == "Original"
    assert created["pinned"] is False

    updated = service.update_playlist(pid, title="Renamed")
    assert updated["title"] == "Renamed"

    service.update_playlist(pid, pinned=True)
    playlists = service.list_playlists()
    found = next(p for p in playlists if p["id"] == pid)
    assert found["pinned"] is True
    assert found["title"] == "Renamed"

    service.update_playlist(pid, pinned=False)
    playlists = service.list_playlists()
    found = next(p for p in playlists if p["id"] == pid)
    assert found["pinned"] is False


def test_update_playlist_rename_rejected_for_imported(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/imported.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=True))
    service.add_url("https://youtube.com/playlist?list=x")
    playlists = service.list_playlists()
    imported_id = next(p["id"] for p in playlists if p["kind"] == "imported")
    original_title = next(p["title"] for p in playlists if p["id"] == imported_id)

    service.update_playlist(imported_id, title="Hacked")
    playlists_after = service.list_playlists()
    current = next(p for p in playlists_after if p["id"] == imported_id)
    assert current["title"] == original_title
