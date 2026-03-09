from __future__ import annotations

import uuid

from app.db.repository import NewPlaylistEntry, NewQueueItem, Repository
from app.services.yt_dlp_service import PlaylistPreview, YtDlpService


class PlaylistService:
    def __init__(self, repository: Repository, yt_dlp_service: YtDlpService) -> None:
        self.repository = repository
        self.yt_dlp_service = yt_dlp_service

    def add_url(self, url: str) -> dict:
        if self.yt_dlp_service.is_playlist_url(url):
            return self.import_playlist(url)
        resolved = self.yt_dlp_service.resolve_video(url)
        created = self.repository.enqueue_items(
            [
                NewQueueItem(
                    source_url=resolved.source_url,
                    normalized_url=resolved.normalized_url,
                    source_type="video",
                    title=resolved.title,
                    channel=resolved.channel,
                    duration_seconds=resolved.duration_seconds,
                    thumbnail_url=resolved.thumbnail_url,
                )
            ]
        )
        return {
            "type": "video",
            "count": 1,
            "title": resolved.title,
            "item_ids": [item.id for item in created],
        }

    def preview_playlist(self, url: str) -> PlaylistPreview:
        return self.yt_dlp_service.preview_playlist(url)

    def import_playlist(self, url: str) -> dict:
        preview = self.yt_dlp_service.preview_playlist(url)
        playlist = self.repository.create_or_update_playlist(
            source_url=preview.source_url,
            title=preview.title,
            channel=preview.channel,
            entry_count=len(preview.entries),
        )
        entries = [
            NewPlaylistEntry(
                source_url=entry["source_url"],
                normalized_url=entry["normalized_url"],
                title=entry.get("title"),
                channel=entry.get("channel"),
                duration_seconds=entry.get("duration_seconds"),
                thumbnail_url=entry.get("thumbnail_url"),
            )
            for entry in preview.entries
        ]
        self.repository.replace_playlist_entries(playlist.id, entries)
        items = [
            NewQueueItem(
                source_url=entry.source_url,
                normalized_url=entry.normalized_url,
                source_type="playlist_item",
                title=entry.title,
                channel=entry.channel,
                duration_seconds=entry.duration_seconds,
                thumbnail_url=entry.thumbnail_url,
                playlist_id=playlist.id,
            )
            for entry in entries
        ]
        created = self.repository.enqueue_items(items)
        return {
            "type": "playlist",
            "count": len(created),
            "title": preview.title,
            "playlist_id": playlist.id,
            "item_ids": [item.id for item in created],
        }

    def _serialize_playlist(self, playlist) -> dict:
        return {
            "id": playlist.id,
            "title": playlist.title or "Untitled playlist",
            "channel": playlist.channel,
            "source_url": playlist.source_url,
            "entry_count": playlist.entry_count,
            "pinned": playlist.pinned,
            "kind": "custom" if playlist.source_url.startswith("custom://") else "imported",
        }

    def list_playlists(self) -> list[dict]:
        playlists = self.repository.list_playlists()
        return [self._serialize_playlist(p) for p in playlists]

    def create_custom_playlist(self, title: str) -> dict:
        playlist = self.repository.create_custom_playlist(title=title)
        return self._serialize_playlist(playlist)

    def update_playlist(
        self, playlist_id: uuid.UUID, *, title: str | None = None, pinned: bool | None = None
    ) -> dict:
        playlist = self.repository.update_playlist(playlist_id, title=title, pinned=pinned)
        if playlist is None:
            raise ValueError("Playlist not found")
        return self._serialize_playlist(playlist)

    def list_playlist_entries(self, playlist_id: uuid.UUID) -> list[dict]:
        entries = self.repository.list_playlist_entries(playlist_id)
        return [
            {
                "id": entry.id,
                "playlist_id": entry.playlist_id,
                "source_url": entry.source_url,
                "normalized_url": entry.normalized_url,
                "title": entry.title,
                "channel": entry.channel,
                "duration_seconds": entry.duration_seconds,
                "thumbnail_url": entry.thumbnail_url,
                "position": entry.position,
            }
            for entry in entries
        ]

    def add_item_to_playlist(self, playlist_id: uuid.UUID, url: str) -> dict:
        resolved = self.yt_dlp_service.resolve_video(url)
        entry = self.repository.add_playlist_entry(
            playlist_id,
            NewPlaylistEntry(
                source_url=resolved.source_url,
                normalized_url=resolved.normalized_url,
                title=resolved.title,
                channel=resolved.channel,
                duration_seconds=resolved.duration_seconds,
                thumbnail_url=resolved.thumbnail_url,
            ),
        )
        if entry is None:
            raise ValueError("Playlist not found")
        return {
            "id": entry.id,
            "playlist_id": entry.playlist_id,
            "title": entry.title,
            "source_url": entry.source_url,
            "position": entry.position,
        }

    def queue_playlist(self, playlist_id: uuid.UUID) -> dict:
        created = self.repository.queue_playlist(playlist_id)
        return {"ok": True, "count": len(created), "item_ids": [item.id for item in created]}

    def queue_playlist_entry(self, entry_id: int) -> dict:
        created = self.repository.queue_playlist_entry(entry_id)
        if created is None:
            raise ValueError("Playlist entry not found")
        return {"ok": True, "count": 1, "item_ids": [created.id]}
