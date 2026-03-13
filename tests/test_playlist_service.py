from dataclasses import dataclass

from app.db.models import QueueStatus
from app.db.repository import NewQueueItem, Repository
from app.services.playlist_service import PlaylistService
from app.services.yt_dlp_service import PlaylistPreview, ResolvedTrack


@dataclass
class FakeYtDlp:
    playlist: bool = False
    playlist_thumbnail_url: str | None = "https://img.youtube.com/pl.jpg"

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
            thumbnail_url=self.playlist_thumbnail_url,
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


def test_add_url_playlist_queues_without_importing(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/playlist2.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=True))

    result = service.add_url("https://youtube.com/playlist?list=x")
    assert result["type"] == "playlist"
    assert result["count"] == 2
    queue = repo.list_queue()
    assert len(queue) == 2
    playlists = service.list_playlists()
    assert len(playlists) == 0


def test_playlist_thumbnail_falls_back_to_first_entry(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/playlist_fallback.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=True, playlist_thumbnail_url=None))

    service.import_playlist("https://youtube.com/playlist?list=x")
    playlists = service.list_playlists()
    assert playlists[0]["thumbnail_url"] == "https://i.ytimg.com/vi/1/hqdefault.jpg"


def test_import_playlist_endpoint_behavior_is_library_only(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/playlist_import_only.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=True))

    result = service.import_playlist("https://youtube.com/playlist?list=x")
    assert result["type"] == "playlist"
    assert result["count"] == 2
    assert "item_ids" not in result
    assert len(repo.list_playlists()) == 1
    assert repo.list_queue() == []


def test_queue_playlist_replace_swaps_existing_queue(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/playlist_replace.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=True))
    original = repo.enqueue_items([NewQueueItem(source_url="u1", normalized_url="u1", source_type="video", title="seed")])[0]

    imported = service.import_playlist("https://youtube.com/playlist?list=x")
    queued = service.queue_playlist(imported["playlist_id"], replace=True)

    assert queued["count"] == 2
    queue = repo.list_queue()
    queued_items = [item for item in queue if item.status == QueueStatus.queued]
    assert len(queued_items) == 2
    assert all(item.source_type == "playlist_item" for item in queued_items)
    original_after = repo.get_item(original.id)
    assert original_after is not None
    assert original_after.status == QueueStatus.removed


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


def test_update_playlist_rename_for_imported(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/imported.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=True))
    service.import_playlist("https://youtube.com/playlist?list=x")
    playlists = service.list_playlists()
    imported_id = next(p["id"] for p in playlists if p["kind"] == "imported")
    original_title = next(p["title"] for p in playlists if p["id"] == imported_id)

    service.update_playlist(imported_id, title="test")
    playlists_after = service.list_playlists()
    current = next(p for p in playlists_after if p["id"] == imported_id)
    assert current["title"] == "test"
