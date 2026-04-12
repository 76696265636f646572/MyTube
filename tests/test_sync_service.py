from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.repository import NewPlaylistEntry, Repository
from app.services.sync_service import SyncService
from app.services.yt_dlp_service import PlaylistPreview


@dataclass
class FakeYtDlp:
    preview: PlaylistPreview

    def preview_playlist(self, url: str, force_refresh: bool = False) -> PlaylistPreview:
        _ = url, force_refresh
        return self.preview


def test_update_playlist_entry_preserves_upstream_item_id_when_none(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/sync_upstream_preserve.db")
    repo.init_db()
    playlist = repo.create_or_update_playlist(source_url="https://example.com/pl", title="x", channel="y", entry_count=0)
    created = repo.add_playlist_entries(
        playlist.id,
        [
            NewPlaylistEntry(
                source_url="https://x/1",
                normalized_url="https://x/1",
                provider="pending",
                provider_item_id="t1",
                upstream_item_id="spotify:track:t1",
                title="A",
            )
        ],
    )
    assert created[0].upstream_item_id == "spotify:track:t1"
    updated = repo.update_playlist_entry(
        created[0].id,
        NewPlaylistEntry(
            source_url="https://youtube.com/watch?v=vid",
            normalized_url="https://youtube.com/watch?v=vid",
            provider="youtube",
            provider_item_id="vid",
            upstream_item_id=None,
            title="A (matched)",
        ),
    )
    assert updated is not None
    assert updated.upstream_item_id == "spotify:track:t1"


def test_sync_service_adds_only_new_items_and_is_idempotent(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/sync_idempotent.db")
    repo.init_db()
    playlist = repo.create_or_update_playlist(
        source_url="https://example.com/pl",
        title="x",
        channel="y",
        entry_count=0,
    )

    # Existing entry
    repo.add_playlist_entries(
        playlist.id,
        [
            NewPlaylistEntry(
                source_url="https://www.youtube.com/watch?v=aaa",
                normalized_url="https://www.youtube.com/watch?v=aaa",
                provider="youtube",
                provider_item_id="aaa",
                upstream_item_id="youtube:aaa",
                title="A",
            )
        ],
    )

    preview = PlaylistPreview(
        provider="youtube",
        source_url=playlist.source_url,
        title="p",
        channel="c",
        thumbnail_url=None,
        entries=[
            {
                "provider": "youtube",
                "provider_item_id": "aaa",
                "source_url": "https://www.youtube.com/watch?v=aaa",
                "normalized_url": "https://www.youtube.com/watch?v=aaa",
                "title": "A",
                "channel": "c",
                "duration_seconds": 1,
                "thumbnail_url": None,
            },
            {
                "provider": "youtube",
                "provider_item_id": "bbb",
                "source_url": "https://www.youtube.com/watch?v=bbb",
                "normalized_url": "https://www.youtube.com/watch?v=bbb",
                "title": "B",
                "channel": "c",
                "duration_seconds": 1,
                "thumbnail_url": None,
            },
        ],
    )

    svc = SyncService(repository=repo, yt_dlp_service=FakeYtDlp(preview=preview), interval_seconds=600, max_concurrent=1)

    # Run twice: second run should be a no-op for additions.
    r1 = svc._sync_playlist_blocking(playlist, remove_missing=False)
    assert r1.fetched_items == 2
    assert r1.new_items_added == 1

    r2 = svc._sync_playlist_blocking(playlist, remove_missing=False)
    assert r2.fetched_items == 2
    assert r2.new_items_added == 0

    entries = repo.list_playlist_entries(playlist.id)
    assert len(entries) == 2
    assert [e.upstream_item_id for e in entries] == ["youtube:aaa", "youtube:bbb"]

