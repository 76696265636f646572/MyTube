from dataclasses import dataclass, field
from types import SimpleNamespace

from app.db.models import QueueStatus
from app.db.repository import NewQueueItem, Repository
from app.services.playlist_service import PlaylistService
from app.services.spotdl_service import SpotdlPlaylistPreview, SpotdlPlaylistTrack
from app.services.yt_dlp_service import PlaylistPreview, ResolvedTrack


@dataclass
class FakeYtDlp:
    playlist: bool = False
    playlist_thumbnail_url: str | None = "https://img.youtube.com/pl.jpg"
    remote_playlists: list[object] = field(default_factory=list)
    fail_remote_playlists: bool = False

    def is_playlist_url(self, url: str) -> bool:
        return self.playlist

    def resolve_video(self, url: str, force_refresh: bool = False) -> ResolvedTrack:
        _ = force_refresh
        return ResolvedTrack(
            source_url=url,
            normalized_url=url,
            title="one",
            channel="chan",
            duration_seconds=100,
            thumbnail_url=None,
            stream_url="http://example/audio",
            provider="youtube",
            provider_item_id="single",
        )

    def preview_playlist(self, url: str) -> PlaylistPreview:
        return PlaylistPreview(
            source_url=url,
            title="pl",
            channel="chan",
            entries=[
                {
                    "provider": "youtube",
                    "provider_item_id": "1",
                    "source_url": "https://youtube.com/watch?v=1",
                    "normalized_url": "https://youtube.com/watch?v=1",
                    "title": "t1",
                    "channel": "ch1",
                    "duration_seconds": 60,
                    "thumbnail_url": None,
                },
                {
                    "provider": "youtube",
                    "provider_item_id": "2",
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

    def list_youtube_user_playlists(self) -> list[object]:
        if self.fail_remote_playlists:
            raise RuntimeError("yt-dlp failed")
        return self.remote_playlists

    def search(self, query: str, limit: int = 10, providers: list[str] | None = None) -> list[dict]:
        _ = providers
        return [
            {
                "provider": "youtube",
                "provider_item_id": "yt123",
                "source_url": "https://www.youtube.com/watch?v=yt123",
                "normalized_url": "https://www.youtube.com/watch?v=yt123",
                "title": f"{query} result",
                "channel": "Channel",
                "duration_seconds": 111,
                "thumbnail_url": "https://i.ytimg.com/vi/yt123/hqdefault.jpg",
            }
        ][:limit]


@dataclass
class FakeSpotdl:
    def is_spotify_playlist_url(self, url: str) -> bool:
        return "open.spotify.com/playlist/" in url

    def preview_playlist(self, url: str) -> SpotdlPlaylistPreview:
        return SpotdlPlaylistPreview(
            source_url="https://open.spotify.com/playlist/abc123",
            title="Spotify playlist abc123",
            channel="Spotify",
            thumbnail_url="https://i.scdn.co/image/cover",
            tracks=[
                SpotdlPlaylistTrack(
                    source_url="https://open.spotify.com/track/track1",
                    normalized_url="https://open.spotify.com/track/track1",
                    provider_item_id="track1",
                    title="Song 1",
                    channel="Artist 1",
                    duration_seconds=180,
                    thumbnail_url="https://i.scdn.co/image/cover",
                    search_query="Song 1 Artist 1",
                ),
                SpotdlPlaylistTrack(
                    source_url="https://open.spotify.com/track/track2",
                    normalized_url="https://open.spotify.com/track/track2",
                    provider_item_id="track2",
                    title="Song 2",
                    channel="Artist 2",
                    duration_seconds=200,
                    thumbnail_url="https://i.scdn.co/image/cover",
                    search_query="Song 2 Artist 2",
                ),
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
    assert "provider" not in playlists[0]
    assert "provider_item_id" not in playlists[0]


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
    assert all(item.source_type == "youtube" for item in queued_items)
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
    assert "provider" not in created
    assert "provider_item_id" not in created

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


def test_update_playlist_description(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/update_desc.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=False))

    created = service.create_custom_playlist("My Playlist")
    pid = created["id"]
    assert created.get("description") is None

    updated = service.update_playlist(pid, description="A curated collection of favorites")
    assert updated["description"] == "A curated collection of favorites"

    playlists = service.list_playlists()
    found = next(p for p in playlists if p["id"] == pid)
    assert found["description"] == "A curated collection of favorites"

    service.update_playlist(pid, description="")
    playlists = service.list_playlists()
    found = next(p for p in playlists if p["id"] == pid)
    assert found["description"] is None


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


def test_list_playlists_merges_remote_youtube_playlists(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/remote_merge.db")
    repo.init_db()
    service = PlaylistService(
        repo,
        FakeYtDlp(
            remote_playlists=[
                SimpleNamespace(
                    source_url="https://www.youtube.com/playlist?list=PLremote1",
                    title="Remote One",
                    channel="YouTube",
                    thumbnail_url="https://img.youtube.com/remote.jpg",
                    entry_count=8,
                    provider="youtube",
                    provider_item_id="PLremote1",
                )
            ]
        ),
    )

    playlists = service.list_playlists()

    assert len(playlists) == 1
    assert playlists[0]["kind"] == "remote_youtube"
    assert playlists[0]["source_url"] == "https://www.youtube.com/playlist?list=PLremote1"
    assert playlists[0]["provider_item_id"] == "PLremote1"


def test_list_playlists_ignores_remote_lookup_failures(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/remote_fail.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(fail_remote_playlists=True))

    playlists = service.list_playlists()

    assert playlists == []


def test_add_item_to_playlist_duplicate_check(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/dup_check.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=False))

    created = service.create_custom_playlist("Target")
    pid = created["id"]
    service.add_item_to_playlist(pid, "https://youtube.com/watch?v=abc")

    check = service.add_item_to_playlist(pid, "https://youtube.com/watch?v=abc", import_mode="check")
    assert check["has_duplicates"] is True
    assert check["duplicate_count"] == 1
    assert check["total"] == 1
    assert check["new_count"] == 0

    skip = service.add_item_to_playlist(pid, "https://youtube.com/watch?v=abc", import_mode="skip_duplicates")
    assert skip.get("skipped_duplicates") is True
    assert skip.get("count") == 0

    add_all = service.add_item_to_playlist(pid, "https://youtube.com/watch?v=abc", import_mode="add_all")
    assert "id" in add_all
    entries = service.list_playlist_entries(pid)
    assert len(entries) == 2


def test_import_spotify_playlist_uses_existing_model(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/spotify_import.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=False), spotdl_service=FakeSpotdl())

    result = service.import_spotify_playlist("https://open.spotify.com/playlist/abc123?si=foo")

    assert result["type"] == "playlist"
    assert result["count"] == 2
    assert result["playlist"]["source_url"] == "https://open.spotify.com/playlist/abc123"
    entries = service.list_playlist_entries(result["playlist_id"])
    assert len(entries) == 2
    assert entries[0]["provider"] == "spotify"
    assert entries[0]["provider_item_id"] == "track1"


def test_spotify_reimport_updates_same_playlist(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/spotify_reimport.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=False), spotdl_service=FakeSpotdl())

    first = service.import_spotify_playlist("https://open.spotify.com/playlist/abc123")
    second = service.import_spotify_playlist("https://open.spotify.com/playlist/abc123?si=changed")

    assert first["playlist_id"] == second["playlist_id"]
    playlists = service.list_playlists()
    assert len([p for p in playlists if p["source_url"] == "https://open.spotify.com/playlist/abc123"]) == 1


def test_spotify_search_and_select_updates_playlist_entry(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/spotify_select.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=False), spotdl_service=FakeSpotdl())
    imported = service.import_spotify_playlist("https://open.spotify.com/playlist/abc123")
    playlist_id = imported["playlist_id"]
    entry_id = imported["entries"][0]["id"]

    search = service.search_spotify_entry(playlist_id, entry_id, limit=1)
    assert search["count"] == 1
    assert search["selected"]["provider"] == "youtube"

    selected = service.select_spotify_entry_result(playlist_id, entry_id, search["selected"])
    assert selected["provider"] == "youtube"
    assert selected["source_url"] == "https://www.youtube.com/watch?v=yt123"
