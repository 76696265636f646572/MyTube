from __future__ import annotations

import json
import logging
import os
import uuid

from app.db.repository import NewPlaylistEntry, NewQueueItem, Repository
from app.services.extractors.youtube import youtube_video_id_from_url
from app.services.source_resolver import MediaSourceResolver
from app.services.spotify_free_service import fetch_spotify_playlist_tracks, is_spotify_playlist_url, spotify_playlist_id_from_url
from app.services.yt_dlp_service import PlaylistPreview, ResolvedTrack, YtDlpService

logger = logging.getLogger(__name__)
SIDEBAR_PLAYLIST_ORDER_SETTING_KEY = "sidebar_playlist_order_v1"

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
        source_resolver: MediaSourceResolver | None = None,
    ) -> None:
        self.repository = repository
        self.yt_dlp_service = yt_dlp_service
        self.source_resolver = source_resolver

    @staticmethod
    def _source_type_for_resolved(resolved: ResolvedTrack) -> str:
        return resolved.item_source_type or resolved.provider or "unknown"

    @staticmethod
    def _new_queue_item(resolved: ResolvedTrack) -> NewQueueItem:
        return NewQueueItem(
            source_url=resolved.source_url,
            provider=resolved.provider,
            provider_item_id=resolved.provider_item_id,
            normalized_url=resolved.normalized_url,
            source_type=PlaylistService._source_type_for_resolved(resolved),
            title=resolved.title,
            channel=resolved.channel,
            duration_seconds=resolved.duration_seconds,
            thumbnail_url=resolved.thumbnail_url,
        )

    @staticmethod
    def _new_playlist_entry(resolved: ResolvedTrack) -> NewPlaylistEntry:
        return NewPlaylistEntry(
            source_url=resolved.source_url,
            provider=resolved.provider,
            provider_item_id=resolved.provider_item_id,
            normalized_url=resolved.normalized_url,
            title=resolved.title,
            channel=resolved.channel,
            duration_seconds=resolved.duration_seconds,
            thumbnail_url=resolved.thumbnail_url,
        )

    def _is_provider_managed_url(self, url: str) -> bool:
        dispatcher = getattr(self.yt_dlp_service, "dispatcher", None)
        if dispatcher is None:
            return True
        try:
            dispatcher.get_extractor(url)
            return True
        except ValueError:
            return False

    def _resolve_single_remote_url(self, url: str) -> ResolvedTrack:
        if self._is_provider_managed_url(url):
            return self.yt_dlp_service.resolve_video(url)
        if not url.strip().lower().startswith(("http://", "https://")):
            raise ValueError("Unsupported URL")
        if self.source_resolver is None:
            raise ValueError("Unsupported URL")
        return self.source_resolver.resolve_http_media(url)

    def add_url(self, url: str) -> dict:
        if self.yt_dlp_service.is_playlist_url(url):
            return self.queue_playlist_url(url)
        resolved = self._resolve_single_remote_url(url)
        created = self.repository.enqueue_items([self._new_queue_item(resolved)])
        return {
            "type": "video",
            "count": 1,
            "title": resolved.title,
            "item_ids": [item.id for item in created],
        }

    def add_local_path(self, path: str) -> dict:
        if self.source_resolver is None:
            raise ValueError("Local media is not configured")
        resolved = self.source_resolver.resolve_local_file(path)
        created = self.repository.enqueue_items([self._new_queue_item(resolved)])
        return {
            "type": "video",
            "count": 1,
            "title": resolved.title,
            "item_ids": [item.id for item in created],
        }

    def add_local_folder(self, path: str, *, recursive: bool = True) -> dict:
        if self.source_resolver is None:
            raise ValueError("Local media is not configured")
        trimmed = path.strip()
        candidates = self.source_resolver.list_candidate_audio_files(trimmed, recursive=recursive)
        if not candidates:
            raise ValueError("No audio files found in that folder")
        prepared: list[NewQueueItem] = []
        skipped = 0
        for candidate in candidates:
            try:
                resolved = self.source_resolver.resolve_local_file(candidate)
            except ValueError:
                skipped += 1
                continue
            prepared.append(self._new_queue_item(resolved))
        if not prepared:
            raise ValueError("No playable audio files could be loaded from that folder")
        created = self.repository.enqueue_items(prepared)
        folder_label = os.path.basename(os.path.normpath(trimmed)) or trimmed
        return {
            "type": "folder",
            "count": len(created),
            "skipped": skipped,
            "title": folder_label,
            "item_ids": [item.id for item in created],
        }

    def preview_playlist(self, url: str) -> PlaylistPreview:
        if is_spotify_playlist_url(url):
            return self._preview_spotify_playlist(url)
        return self.yt_dlp_service.preview_playlist(url)

    def _preview_spotify_playlist(self, url: str) -> PlaylistPreview:
        pl_id = spotify_playlist_id_from_url(url)
        if not pl_id:
            raise ValueError("Invalid Spotify playlist URL")
        meta, tracks = fetch_spotify_playlist_tracks(pl_id)
        entries: list[dict] = []
        for t in tracks:
            tid = t["spotify_track_id"]
            track_url = f"https://open.spotify.com/track/{tid}"
            entries.append(
                {
                    "provider": "spotify",
                    "provider_item_id": tid,
                    "source_url": track_url,
                    "normalized_url": track_url,
                    "source_type": "spotify",
                    "title": t.get("title"),
                    "channel": t.get("channel"),
                    "duration_seconds": t.get("duration_seconds"),
                    "thumbnail_url": t.get("thumbnail_url"),
                }
            )
        return PlaylistPreview(
            source_url=meta["source_url"],
            title=meta.get("title"),
            channel=meta.get("channel"),
            entries=entries,
            provider="spotify",
            thumbnail_url=meta.get("thumbnail_url"),
        )

    def queue_playlist_url(self, url: str, *, replace: bool = False) -> dict:
        """Queue playlist entries from URL without importing to library."""
        if is_spotify_playlist_url(url):
            raise ValueError("Spotify playlists cannot be queued; import them from the Spotify import flow")
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
        if is_spotify_playlist_url(url):
            raise ValueError("Spotify playlists must be imported via POST /api/spotify/import")
        preview = self.yt_dlp_service.preview_playlist(url)
        if not target_playlist_id:
            playlist = self.repository.create_or_update_playlist(
                source_url=preview.source_url,
                title=preview.title,
                channel=preview.channel,
                entry_count=len(preview.entries),
                thumbnail_url=preview.thumbnail_url,
            )
            self.repository.replace_playlist_entries(playlist.id, [
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
            ])
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
        new_entries = [
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
        kind = "imported"
        if playlist.source_url.startswith("custom://"):
            kind = "custom"
        elif is_spotify_playlist_url(playlist.source_url):
            kind = "spotify"
        return {
            "id": playlist.id,
            "title": playlist.title or "Untitled playlist",
            "description": playlist.description or None,
            "channel": playlist.channel,
            "source_url": playlist.source_url,
            "thumbnail_url": thumbnail_url,
            "entry_count": playlist.entry_count,
            "pinned": playlist.pinned,
            "kind": kind,
        }

    @staticmethod
    def _playlist_sort_key(playlist: dict) -> str:
        return str(playlist.get("id") or "")

    @staticmethod
    def _order_group(playlists: list[dict], saved_order: list[str]) -> list[dict]:
        remaining: dict[str, dict] = {}
        for playlist in playlists:
            key = PlaylistService._playlist_sort_key(playlist)
            if key and key not in remaining:
                remaining[key] = playlist
        ordered: list[dict] = []
        for key in saved_order:
            playlist = remaining.pop(key, None)
            if playlist is not None:
                ordered.append(playlist)
        for playlist in playlists:
            key = PlaylistService._playlist_sort_key(playlist)
            if key and key in remaining:
                ordered.append(remaining.pop(key))
        return ordered

    def _load_sidebar_order(self) -> dict[str, list[str]]:
        raw = self.repository.get_setting(SIDEBAR_PLAYLIST_ORDER_SETTING_KEY)
        if not raw:
            return {"pinned": [], "unpinned": []}
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {"pinned": [], "unpinned": []}
        pinned = parsed.get("pinned")
        unpinned = parsed.get("unpinned")
        if not isinstance(pinned, list) or not isinstance(unpinned, list):
            return {"pinned": [], "unpinned": []}
        return {
            "pinned": [str(item) for item in pinned if item is not None],
            "unpinned": [str(item) for item in unpinned if item is not None],
        }

    def _save_sidebar_order(self, order: dict[str, list[str]]) -> None:
        payload = {
            "pinned": [str(item) for item in order.get("pinned", []) if item is not None],
            "unpinned": [str(item) for item in order.get("unpinned", []) if item is not None],
        }
        self.repository.set_setting(SIDEBAR_PLAYLIST_ORDER_SETTING_KEY, json.dumps(payload))

    def _apply_sidebar_order(self, playlists: list[dict]) -> list[dict]:
        order = self._load_sidebar_order()
        pinned = [playlist for playlist in playlists if bool(playlist.get("pinned"))]
        unpinned = [playlist for playlist in playlists if not bool(playlist.get("pinned"))]
        ordered_pinned = self._order_group(pinned, order.get("pinned", []))
        ordered_unpinned = self._order_group(unpinned, order.get("unpinned", []))
        return [*ordered_pinned, *ordered_unpinned]

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
        return self._apply_sidebar_order(serialized)

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
        playlist = self.repository.get_playlist(playlist_id)
        if playlist is None:
            raise ValueError("Playlist not found")
        resolved = self._resolve_single_remote_url(url)
        new_entry = self._new_playlist_entry(resolved)
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

    def add_local_path_to_playlist(
        self, playlist_id: uuid.UUID, path: str, *, import_mode: ImportMode | None = None
    ) -> dict:
        if self.source_resolver is None:
            raise ValueError("Local media is not configured")
        playlist = self.repository.get_playlist(playlist_id)
        if playlist is None:
            raise ValueError("Playlist not found")
        resolved = self.source_resolver.resolve_local_file(path)
        new_entry = self._new_playlist_entry(resolved)
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

    def add_local_folder_to_playlist(
        self,
        playlist_id: uuid.UUID,
        path: str,
        *,
        recursive: bool = True,
        import_mode: ImportMode | None = None,
    ) -> dict:
        if self.source_resolver is None:
            raise ValueError("Local media is not configured")
        playlist = self.repository.get_playlist(playlist_id)
        if playlist is None:
            raise ValueError("Playlist not found")
        trimmed = path.strip()
        candidates = self.source_resolver.list_candidate_audio_files(trimmed, recursive=recursive)
        if not candidates:
            raise ValueError("No audio files found in that folder")
        new_entries: list[NewPlaylistEntry] = []
        for candidate in candidates:
            try:
                resolved = self.source_resolver.resolve_local_file(candidate)
            except ValueError:
                continue
            new_entries.append(self._new_playlist_entry(resolved))
        if not new_entries:
            raise ValueError("No playable audio files could be loaded from that folder")
        return self.add_entries_to_playlist(playlist_id, new_entries, import_mode=import_mode)

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

    def reorder_sidebar_playlist(self, playlist_id: str, new_position: int, pinned: bool) -> None:
        group_value = bool(pinned)
        playlists = self.list_playlists()
        target_group = [playlist for playlist in playlists if bool(playlist.get("pinned")) == group_value]
        target_index = next(
            (
                index
                for index, playlist in enumerate(target_group)
                if self._playlist_sort_key(playlist) == str(playlist_id)
            ),
            None,
        )
        if target_index is None:
            raise ValueError("Playlist not found")
        moved = target_group.pop(target_index)
        if new_position < 0:
            insertion_index = 0
        elif new_position > len(target_group):
            insertion_index = len(target_group)
        else:
            insertion_index = new_position
        target_group.insert(insertion_index, moved)
        order = self._load_sidebar_order()
        key = "pinned" if group_value else "unpinned"
        order[key] = [self._playlist_sort_key(playlist) for playlist in target_group]
        self._save_sidebar_order(order)
