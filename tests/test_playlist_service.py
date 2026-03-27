from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from app.db.models import QueueStatus
from app.db.repository import NewQueueItem, Repository
from app.services.playlist_service import PlaylistService
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


def test_reorder_sidebar_playlist_persists_mixed_unpinned_order(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/sidebar_order.db")
    repo.init_db()
    fake = FakeYtDlp(
        remote_playlists=[
            SimpleNamespace(
                source_url="https://www.youtube.com/playlist?list=PLremote1",
                title="Remote One",
                channel="YouTube",
                thumbnail_url=None,
                entry_count=4,
                provider="youtube",
                provider_item_id="PLremote1",
            )
        ]
    )
    service = PlaylistService(repo, fake)
    first = service.create_custom_playlist("First")
    second = service.create_custom_playlist("Second")

    initial_ids = [str(playlist["id"]) for playlist in service.list_playlists()]
    assert str(second["id"]) in initial_ids
    assert str(first["id"]) in initial_ids
    remote_id = next(str(playlist["id"]) for playlist in service.list_playlists() if playlist["kind"] == "remote_youtube")

    service.reorder_sidebar_playlist(remote_id, 0, pinned=False)

    reordered_ids = [str(playlist["id"]) for playlist in service.list_playlists()]
    assert reordered_ids[0] == remote_id
    assert str(second["id"]) in reordered_ids
    assert str(first["id"]) in reordered_ids

    service_after_restart = PlaylistService(repo, fake)
    persisted_ids = [str(playlist["id"]) for playlist in service_after_restart.list_playlists()]
    assert persisted_ids[0] == remote_id

    fake.remote_playlists.append(
        SimpleNamespace(
            source_url="https://www.youtube.com/playlist?list=PLremote2",
            title="Remote Two",
            channel="YouTube",
            thumbnail_url=None,
            entry_count=2,
            provider="youtube",
            provider_item_id="PLremote2",
        )
    )
    with_new_remote = [str(playlist["id"]) for playlist in service_after_restart.list_playlists()]
    assert with_new_remote[0] == remote_id
    assert with_new_remote[-1] == "remote:youtube:PLremote2"


def test_reorder_sidebar_playlist_keeps_pinned_group_boundary(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/sidebar_group_order.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp())

    pinned_playlist = service.create_custom_playlist("Pinned")
    unpinned_playlist = service.create_custom_playlist("Unpinned")
    service.update_playlist(pinned_playlist["id"], pinned=True)

    service.reorder_sidebar_playlist(str(unpinned_playlist["id"]), 0, pinned=False)
    ordered = service.list_playlists()
    assert ordered[0]["id"] == pinned_playlist["id"]
    assert ordered[1]["id"] == unpinned_playlist["id"]

    with pytest.raises(ValueError, match="Playlist not found"):
        service.reorder_sidebar_playlist(str(unpinned_playlist["id"]), 0, pinned=True)


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


def test_import_playlist_rejects_spotify_url(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/spotify_reject.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=False))
    with pytest.raises(ValueError, match="spotify/import"):
        service.import_playlist("https://open.spotify.com/playlist/abc123")


def test_queue_playlist_url_rejects_spotify_url(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/spotify_queue_reject.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=False))
    with pytest.raises(ValueError, match="Spotify playlists cannot be queued"):
        service.queue_playlist_url("https://open.spotify.com/playlist/abc123")


def test_preview_spotify_playlist(monkeypatch, tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/spotify_preview.db")
    repo.init_db()
    service = PlaylistService(repo, FakeYtDlp(playlist=False))

    def fake_fetch(pid: str):
        assert pid == "plid"
        return (
            {
                "source_url": "https://open.spotify.com/playlist/plid",
                "title": "T",
                "channel": "O",
                "thumbnail_url": None,
            },
            [
                {
                    "spotify_track_id": "tr1",
                    "title": "Song",
                    "channel": "Artist",
                    "duration_seconds": 90,
                    "thumbnail_url": None,
                },
            ],
        )

    monkeypatch.setattr("app.services.playlist_service.fetch_spotify_playlist_tracks", fake_fetch)
    prev = service.preview_playlist("https://open.spotify.com/playlist/plid")
    assert prev.provider == "spotify"
    assert prev.source_url == "https://open.spotify.com/playlist/plid"
    assert len(prev.entries) == 1
    assert prev.entries[0]["provider"] == "spotify"
