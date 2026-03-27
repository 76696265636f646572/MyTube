from __future__ import annotations

import logging
import uuid
from urllib.parse import urlparse

from app.db.repository import NewPlaylistEntry, NewQueueItem, Repository
from app.services.extractors.youtube import youtube_video_id_from_url
from app.services.spotdl_service import SpotdlService
from app.services.yt_dlp_service import PlaylistPreview, YtDlpService

logger = logging.getLogger(__name__)

ImportMode = str  # "check" | "add_all" | "skip_duplicates"


def _is_duplicate(keys: set[tuple[str, str | None]], normalized_url: str | None, provider_item_id: str | None) -> bool:
    norm = (normalized_url or "").strip()
    pid = (provider_item_id or "").strip() or None
    if norm:
        return any(k[0] == norm for k in keys)
    if pid:
        return any(k[1] == pid for k in keys)
    return False


class PlaylistService:
    def __init__(
        self,
        repository: Repository,
        yt_dlp_service: YtDlpService,
        spotdl_service: SpotdlService | None = None,
    ) -> None:
        self.repository = repository
        self.yt_dlp_service = yt_dlp_service
        self.spotdl_service = spotdl_service

    def is_spotify_playlist_url(self, url: str) -> bool:
        if self.spotdl_service is None:
            return False
        return self.spotdl_service.is_spotify_playlist_url(url)

    def _preview_for_import(self, url: str) -> PlaylistPreview:
        if self.is_spotify_playlist_url(url):
            if self.spotdl_service is None:
                raise ValueError("Spotify import is not configured")
            return self.spotdl_service.preview_playlist(url).as_playlist_preview()
        return self.yt_dlp_service.preview_playlist(url)

    @staticmethod
    def _entries_for_preview(preview: PlaylistPreview) -> list[NewPlaylistEntry]:
        return [
            NewPlaylistEntry(
                source_url=e["source_url"],
                provider=e.get("provider"),
                provider_item_id=e.get("provider_item_id"),
                normalized_url=e["normalized_url"],
                title=e.get("title"),
                channel=e.get("channel"),
                duration_seconds=e.get("duration_seconds"),
                thumbnail_url=e.get("thumbnail_url"),
            )
            for e in preview.entries
        ]

    def add_url(self, url: str) -> dict:
        if self.yt_dlp_service.is_playlist_url(url):
            return self.queue_playlist_url(url)
        resolved = self.yt_dlp_service.resolve_video(url)
        created = self.repository.enqueue_items(
            [
                NewQueueItem(
                    source_url=resolved.source_url,
                    provider=resolved.provider,
                    provider_item_id=resolved.provider_item_id,
                    normalized_url=resolved.normalized_url,
                    source_type=resolved.provider,
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
        return self._preview_for_import(url)

    def queue_playlist_url(self, url: str, *, replace: bool = False) -> dict:
        """Queue playlist entries from URL without importing to library."""
        preview = self.yt_dlp_service.preview_playlist(url)
        items = [
            NewQueueItem(
                source_url=e["source_url"],
                provider=e.get("provider"),
                provider_item_id=e.get("provider_item_id"),
                normalized_url=e["normalized_url"],
                source_type=e.get("provider") or "unknown",
                title=e.get("title"),
                channel=e.get("channel"),
                duration_seconds=e.get("duration_seconds"),
                thumbnail_url=e.get("thumbnail_url"),
            )
            for e in preview.entries
        ]
        if replace:
            created = self.repository.replace_queued_items(items)
        else:
            created = self.repository.enqueue_items(items)
        return {
            "type": "playlist",
            "count": len(created),
            "title": preview.title,
            "item_ids": [item.id for item in created],
        }

    def import_playlist(
        self, url: str, target_playlist_id: uuid.UUID | None = None, *, import_mode: ImportMode | None = None
    ) -> dict:
        if target_playlist_id and self.is_spotify_playlist_url(url):
            raise ValueError("Spotify playlist import into an existing playlist is not supported")
        preview = self._preview_for_import(url)
        if not target_playlist_id:
            playlist = self.repository.create_or_update_playlist(
                source_url=preview.source_url,
                title=preview.title,
                channel=preview.channel,
                entry_count=len(preview.entries),
                thumbnail_url=preview.thumbnail_url,
            )
            self.repository.replace_playlist_entries(playlist.id, self._entries_for_preview(preview))
            entries = self.repository.list_playlist_entries(playlist.id)
            return {
                "type": "playlist",
                "count": len(entries),
                "title": preview.title,
                "playlist_id": playlist.id,
            }
        playlist = self.repository.get_playlist(target_playlist_id)
        if playlist is None:
            raise ValueError("Playlist not found")
        target_title = playlist.title or "Untitled playlist"
        new_entries = self._entries_for_preview(preview)
        keys = self.repository.get_playlist_dedup_keys(playlist.id)
        dup_count = sum(1 for e in new_entries if _is_duplicate(keys, e.normalized_url, e.provider_item_id))
        mode = import_mode or "add_all"
        if mode == "check" and dup_count > 0:
            return {
                "has_duplicates": True,
                "duplicate_count": dup_count,
                "total": len(new_entries),
                "new_count": len(new_entries) - dup_count,
                "target_playlist_title": target_title,
                "target_playlist_id": str(playlist.id),
            }
        if mode == "skip_duplicates":
            to_add = [e for e in new_entries if not _is_duplicate(keys, e.normalized_url, e.provider_item_id)]
            if not to_add:
                return {
                    "ok": True,
                    "skipped_duplicates": True,
                    "count": 0,
                    "target_playlist_title": target_title,
                    "playlist_id": playlist.id,
                }
            self.repository.add_playlist_entries(playlist.id, to_add)
        else:
            self.repository.add_playlist_entries(playlist.id, new_entries)
        entries = self.repository.list_playlist_entries(playlist.id)
        return {
            "type": "playlist",
            "count": len(entries),
            "title": preview.title,
            "playlist_id": playlist.id,
        }

    def import_spotify_playlist(self, url: str) -> dict:
        if not self.is_spotify_playlist_url(url):
            raise ValueError("Expected a Spotify playlist URL")
        result = self.import_playlist(url)
        playlist_id = result["playlist_id"]
        playlist = self.repository.get_playlist(playlist_id)
        if playlist is None:
            raise ValueError("Playlist not found")
        entries = self.list_playlist_entries(playlist_id)
        return {
            **result,
            "playlist": self._serialize_playlist(playlist),
            "entries": entries,
        }

    def _is_spotify_library_playlist(self, source_url: str | None) -> bool:
        if not source_url:
            return False
        parsed = urlparse(source_url)
        host = (parsed.netloc or "").lower()
        if host not in {"open.spotify.com", "www.open.spotify.com"}:
            return False
        parts = [segment for segment in (parsed.path or "").split("/") if segment]
        return len(parts) >= 2 and parts[0] == "playlist"

    def spotify_review(self, playlist_id: uuid.UUID) -> dict:
        playlist = self.repository.get_playlist(playlist_id)
        if playlist is None:
            raise ValueError("Playlist not found")
        if not self._is_spotify_library_playlist(playlist.source_url):
            raise ValueError("Playlist is not a Spotify import")
        entries = self.list_playlist_entries(playlist_id)
        return {
            "playlist": self._serialize_playlist(playlist),
            "entries": entries,
        }

    def _ensure_spotify_review_playlist(self, playlist_id: uuid.UUID) -> None:
        playlist = self.repository.get_playlist(playlist_id)
        if playlist is None:
            raise ValueError("Playlist not found")
        if not self._is_spotify_library_playlist(playlist.source_url):
            raise ValueError("Playlist is not a Spotify import")

    def search_spotify_entry(self, playlist_id: uuid.UUID, entry_id: int, limit: int = 10) -> dict:
        self._ensure_spotify_review_playlist(playlist_id)
        entry = self.repository.get_playlist_entry(entry_id)
        if entry is None or entry.playlist_id != playlist_id:
            raise ValueError("Playlist entry not found")
        if limit < 1:
            limit = 1
        query = " ".join(part for part in [entry.title, entry.channel] if part).strip() or entry.source_url
        results = self.yt_dlp_service.search(query=query, limit=limit)
        return {
            "entry_id": entry_id,
            "query": query,
            "count": len(results),
            "results": results,
            "selected": results[0] if results else None,
        }

    def select_spotify_entry_result(self, playlist_id: uuid.UUID, entry_id: int, selected: dict) -> dict:
        self._ensure_spotify_review_playlist(playlist_id)
        updated = self.repository.update_playlist_entry_source(
            playlist_id=playlist_id,
            entry_id=entry_id,
            source_url=selected["source_url"],
            normalized_url=selected["normalized_url"],
            provider=selected.get("provider"),
            provider_item_id=selected.get("provider_item_id"),
            title=selected.get("title"),
            channel=selected.get("channel"),
            duration_seconds=selected.get("duration_seconds"),
            thumbnail_url=selected.get("thumbnail_url"),
        )
        if updated is None:
            raise ValueError("Playlist entry not found")
        return {
            "id": updated.id,
            "playlist_id": updated.playlist_id,
            "source_url": updated.source_url,
            "normalized_url": updated.normalized_url,
            "provider": updated.provider,
            "provider_item_id": updated.provider_item_id,
            "title": updated.title,
            "channel": updated.channel,
            "duration_seconds": updated.duration_seconds,
            "thumbnail_url": updated.thumbnail_url,
            "position": updated.position,
        }

    def _serialize_playlist(self, playlist) -> dict:
        thumbnail_url = playlist.thumbnail_url
        if not thumbnail_url:
            first_entry = self.repository.get_first_playlist_entry(playlist.id)
            if first_entry is not None:
                thumbnail_url = first_entry.thumbnail_url
                if not thumbnail_url and (first_entry.provider == "youtube" or first_entry.provider is None):
                    video_id = youtube_video_id_from_url(first_entry.source_url)
                    if video_id:
                        thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        return {
            "id": playlist.id,
            "title": playlist.title or "Untitled playlist",
            "description": playlist.description or None,
            "channel": playlist.channel,
            "source_url": playlist.source_url,
            "thumbnail_url": thumbnail_url,
            "entry_count": playlist.entry_count,
            "pinned": playlist.pinned,
            "kind": "custom" if playlist.source_url.startswith("custom://") else "imported",
        }

    def list_playlists(self) -> list[dict]:
        playlists = self.repository.list_playlists()
        serialized = [self._serialize_playlist(p) for p in playlists]
        known_sources = {
            (playlist.get("source_url") or "").strip()
            for playlist in serialized
            if playlist.get("source_url")
        }
        try:
            remote_playlists = self.yt_dlp_service.list_youtube_user_playlists()
        except Exception:
            logger.warning("Failed to load YouTube user playlists", exc_info=True)
            remote_playlists = []

        for remote in remote_playlists:
            if remote.source_url in known_sources:
                continue
            serialized.append(
                {
                    "id": f"remote:youtube:{remote.provider_item_id or remote.source_url}",
                    "title": remote.title or "Untitled playlist",
                    "description": None,
                    "channel": remote.channel,
                    "source_url": remote.source_url,
                    "thumbnail_url": remote.thumbnail_url,
                    "entry_count": remote.entry_count,
                    "pinned": False,
                    "kind": "remote_youtube",
                    "provider": remote.provider,
                    "provider_item_id": remote.provider_item_id,
                }
            )
        return serialized

    def create_custom_playlist(self, title: str) -> dict:
        playlist = self.repository.create_custom_playlist(title=title)
        return self._serialize_playlist(playlist)

    def update_playlist(
        self,
        playlist_id: uuid.UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        pinned: bool | None = None,
    ) -> dict:
        playlist = self.repository.update_playlist(
            playlist_id, title=title, description=description, pinned=pinned
        )
        if playlist is None:
            raise ValueError("Playlist not found")
        return self._serialize_playlist(playlist)

    def delete_playlist(self, playlist_id: uuid.UUID) -> None:
        if not self.repository.delete_playlist(playlist_id):
            raise ValueError("Playlist not found")

    def list_playlist_entries(self, playlist_id: uuid.UUID) -> list[dict]:
        entries = self.repository.list_playlist_entries(playlist_id)
        return [
            {
                "id": entry.id,
                "playlist_id": entry.playlist_id,
                "source_url": entry.source_url,
                "normalized_url": entry.normalized_url,
                "provider": entry.provider,
                "provider_item_id": entry.provider_item_id,
                "title": entry.title,
                "channel": entry.channel,
                "duration_seconds": entry.duration_seconds,
                "thumbnail_url": entry.thumbnail_url,
                "position": entry.position,
            }
            for entry in entries
        ]

    def add_item_to_playlist(
        self, playlist_id: uuid.UUID, url: str, *, import_mode: ImportMode | None = None
    ) -> dict:
        resolved = self.yt_dlp_service.resolve_video(url)
        new_entry = NewPlaylistEntry(
            source_url=resolved.source_url,
            provider=resolved.provider,
            provider_item_id=resolved.provider_item_id,
            normalized_url=resolved.normalized_url,
            title=resolved.title,
            channel=resolved.channel,
            duration_seconds=resolved.duration_seconds,
            thumbnail_url=resolved.thumbnail_url,
        )
        playlist = self.repository.get_playlist(playlist_id)
        if playlist is None:
            raise ValueError("Playlist not found")
        target_title = playlist.title or "Untitled playlist"
        keys = self.repository.get_playlist_dedup_keys(playlist_id)
        is_dup = _is_duplicate(keys, new_entry.normalized_url, new_entry.provider_item_id)
        mode = import_mode or "add_all"
        if mode == "check" and is_dup:
            return {
                "has_duplicates": True,
                "duplicate_count": 1,
                "total": 1,
                "new_count": 0,
                "target_playlist_title": target_title,
                "target_playlist_id": str(playlist_id),
            }
        if mode == "skip_duplicates" and is_dup:
            return {
                "ok": True,
                "skipped_duplicates": True,
                "count": 0,
                "target_playlist_title": target_title,
            }
        entry = self.repository.add_playlist_entry(playlist_id, new_entry)
        if entry is None:
            raise ValueError("Playlist not found")
        return {
            "id": entry.id,
            "playlist_id": entry.playlist_id,
            "title": entry.title,
            "source_url": entry.source_url,
            "position": entry.position,
        }

    def queue_playlist(self, playlist_id: uuid.UUID, *, replace: bool = False) -> dict:
        created = self.repository.queue_playlist(playlist_id, replace=replace)
        return {"ok": True, "count": len(created), "item_ids": [item.id for item in created]}

    def queue_playlist_entry(self, entry_id: int) -> dict:
        created = self.repository.queue_playlist_entry(entry_id)
        if created is None:
            raise ValueError("Playlist entry not found")
        return {"ok": True, "count": 1, "item_ids": [created.id]}

    def add_entries_to_playlist(
        self, playlist_id: uuid.UUID, entries: list[NewPlaylistEntry], *, import_mode: ImportMode | None = None
    ) -> dict:
        playlist = self.repository.get_playlist(playlist_id)
        if playlist is None:
            raise ValueError("Playlist not found")
        target_title = playlist.title or "Untitled playlist"
        keys = self.repository.get_playlist_dedup_keys(playlist.id)
        dup_count = sum(1 for e in entries if _is_duplicate(keys, e.normalized_url, e.provider_item_id))
        mode = import_mode or "add_all"
        if mode == "check" and dup_count > 0:
            return {
                "has_duplicates": True,
                "duplicate_count": dup_count,
                "total": len(entries),
                "new_count": len(entries) - dup_count,
                "target_playlist_title": target_title,
                "target_playlist_id": str(playlist_id),
            }
        if mode == "skip_duplicates":
            to_add = [e for e in entries if not _is_duplicate(keys, e.normalized_url, e.provider_item_id)]
            if not to_add:
                return {
                    "ok": True,
                    "skipped_duplicates": True,
                    "count": 0,
                    "target_playlist_title": target_title,
                }
            created = self.repository.add_playlist_entries(playlist.id, to_add)
        else:
            created = self.repository.add_playlist_entries(playlist.id, entries)
        all_entries = self.repository.list_playlist_entries(playlist.id)
        return {
            "ok": True,
            "count": len(created),
            "playlist_id": playlist.id,
            "total_entries": len(all_entries),
        }

    def remove_playlist_entry(self, entry_id: int) -> None:
        if not self.repository.delete_playlist_entry(entry_id):
            raise ValueError("Playlist entry not found")

    def reorder_playlist_entry(self, entry_id: int, new_position: int) -> None:
        if not self.repository.reorder_playlist_entry(entry_id, new_position):
            raise ValueError("Playlist entry not found")
