from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Iterator, Optional

from sqlalchemy import Engine, Select, create_engine, delete, func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, PlayHistory, Playlist, PlaylistEntry, QueueItem, QueueStatus, Setting


@dataclass
class NewQueueItem:
    source_url: str
    normalized_url: str
    source_type: str
    provider: str | None = None
    provider_item_id: str | None = None
    title: str | None = None
    channel: str | None = None
    duration_seconds: int | None = None
    thumbnail_url: str | None = None
    playlist_id: uuid.UUID | None = None


@dataclass
class NewPlaylistEntry:
    source_url: str
    normalized_url: str
    provider: str | None = None
    provider_item_id: str | None = None
    upstream_item_id: str | None = None
    title: str | None = None
    channel: str | None = None
    duration_seconds: int | None = None
    thumbnail_url: str | None = None


class Repository:
    def __init__(self, db_url: str) -> None:
        self.engine: Engine = create_engine(db_url, future=True)
        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self._queue_lock = Lock()

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine)
        self._ensure_playlist_thumbnail_column()
        self._ensure_playlist_description_column()
        self._ensure_play_history_thumbnail_column()
        self._ensure_play_history_musicatlas_submitted_column()
        self._ensure_provider_columns()
        self._ensure_playlist_entry_spotify_import_searched_column()
        self._ensure_playlist_can_edit_column()
        self._ensure_playlist_can_delete_column()
        self._ensure_playlist_sync_columns()
        self._ensure_playlist_entry_upstream_item_id_column()
        self._ensure_liked_songs_playlist_entry()


    def _ensure_liked_songs_playlist_entry(self) -> None:
        if self.engine.url.get_backend_name() != "sqlite":
            return
        with Session(self.engine) as session:
            existing = session.execute(select(Playlist.id).where(Playlist.title == "Liked Songs")).scalar_one_or_none()
            if existing is not None:
                return

            playlist = Playlist(
                title="Liked Songs",
                channel="Liked Songs",
                thumbnail_url="/static/images/liked_song.png",
                can_edit=False,
                can_delete=False,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                source_url="custom://liked_songs",
            )
            session.add(playlist)
            session.commit()
            return

    def _ensure_playlist_can_edit_column(self) -> None:
        if self.engine.url.get_backend_name() != "sqlite":
            return
        with self.engine.begin() as conn:
            column_rows = conn.execute(text("PRAGMA table_info(playlists)")).mappings().all()
            column_names = {row["name"] for row in column_rows}
            if "can_edit" not in column_names:
                conn.execute(text("ALTER TABLE playlists ADD COLUMN can_edit INTEGER NOT NULL DEFAULT 1"))

    def _ensure_playlist_can_delete_column(self) -> None:
        if self.engine.url.get_backend_name() != "sqlite":
            return
        with self.engine.begin() as conn:
            column_rows = conn.execute(text("PRAGMA table_info(playlists)")).mappings().all()
            column_names = {row["name"] for row in column_rows}
            if "can_delete" not in column_names:
                conn.execute(text("ALTER TABLE playlists ADD COLUMN can_delete INTEGER NOT NULL DEFAULT 1"))

    def _ensure_playlist_entry_spotify_import_searched_column(self) -> None:
        if self.engine.url.get_backend_name() != "sqlite":
            return
        with self.engine.begin() as conn:
            column_rows = conn.execute(text("PRAGMA table_info(playlist_entries)")).mappings().all()
            column_names = {row["name"] for row in column_rows}
            if "spotify_import_searched" not in column_names:
                conn.execute(
                    text(
                        "ALTER TABLE playlist_entries ADD COLUMN spotify_import_searched INTEGER NOT NULL DEFAULT 0"
                    )
                )

    def _ensure_playlist_entry_upstream_item_id_column(self) -> None:
        if self.engine.url.get_backend_name() != "sqlite":
            return
        with self.engine.begin() as conn:
            column_rows = conn.execute(text("PRAGMA table_info(playlist_entries)")).mappings().all()
            column_names = {row["name"] for row in column_rows}
            if "upstream_item_id" not in column_names:
                conn.execute(text("ALTER TABLE playlist_entries ADD COLUMN upstream_item_id TEXT"))

    def _ensure_playlist_thumbnail_column(self) -> None:
        # Existing SQLite databases need an explicit ALTER TABLE when new
        # nullable columns are introduced after the table was created.
        if self.engine.url.get_backend_name() != "sqlite":
            return
        with self.engine.begin() as conn:
            column_rows = conn.execute(text("PRAGMA table_info(playlists)")).mappings().all()
            column_names = {row["name"] for row in column_rows}
            if "thumbnail_url" not in column_names:
                conn.execute(text("ALTER TABLE playlists ADD COLUMN thumbnail_url TEXT"))

    def _ensure_playlist_description_column(self) -> None:
        if self.engine.url.get_backend_name() != "sqlite":
            return
        with self.engine.begin() as conn:
            column_rows = conn.execute(text("PRAGMA table_info(playlists)")).mappings().all()
            column_names = {row["name"] for row in column_rows}
            if "description" not in column_names:
                conn.execute(text("ALTER TABLE playlists ADD COLUMN description TEXT"))

    def _ensure_playlist_sync_columns(self) -> None:
        if self.engine.url.get_backend_name() != "sqlite":
            return
        with self.engine.begin() as conn:
            column_rows = conn.execute(text("PRAGMA table_info(playlists)")).mappings().all()
            column_names = {row["name"] for row in column_rows}
            if "sync_enabled" not in column_names:
                conn.execute(text("ALTER TABLE playlists ADD COLUMN sync_enabled INTEGER NOT NULL DEFAULT 0"))
            if "sync_remove_missing" not in column_names:
                conn.execute(text("ALTER TABLE playlists ADD COLUMN sync_remove_missing INTEGER NOT NULL DEFAULT 0"))
            if "last_sync_started_at" not in column_names:
                conn.execute(text("ALTER TABLE playlists ADD COLUMN last_sync_started_at DATETIME"))
            if "last_sync_succeeded_at" not in column_names:
                conn.execute(text("ALTER TABLE playlists ADD COLUMN last_sync_succeeded_at DATETIME"))
            if "last_sync_status" not in column_names:
                conn.execute(text("ALTER TABLE playlists ADD COLUMN last_sync_status TEXT"))
            if "last_sync_error" not in column_names:
                conn.execute(text("ALTER TABLE playlists ADD COLUMN last_sync_error TEXT"))

    def _ensure_play_history_thumbnail_column(self) -> None:
        if self.engine.url.get_backend_name() != "sqlite":
            return
        with self.engine.begin() as conn:
            column_rows = conn.execute(text("PRAGMA table_info(play_history)")).mappings().all()
            column_names = {row["name"] for row in column_rows}
            if "thumbnail_url" not in column_names:
                conn.execute(text("ALTER TABLE play_history ADD COLUMN thumbnail_url TEXT"))

    def _ensure_play_history_musicatlas_submitted_column(self) -> None:
        if self.engine.url.get_backend_name() != "sqlite":
            return
        with self.engine.begin() as conn:
            column_rows = conn.execute(text("PRAGMA table_info(play_history)")).mappings().all()
            column_names = {row["name"] for row in column_rows}
            if "musicatlas_submitted" not in column_names:
                conn.execute(text("ALTER TABLE play_history ADD COLUMN musicatlas_submitted INTEGER NOT NULL DEFAULT 0"))

    def _ensure_provider_columns(self) -> None:
        if self.engine.url.get_backend_name() != "sqlite":
            return
        tables = {
            "queue_items": ("provider", "provider_item_id"),
            "playlist_entries": ("provider", "provider_item_id"),
            "play_history": ("provider", "provider_item_id"),
        }
        with self.engine.begin() as conn:
            for table_name, columns in tables.items():
                column_rows = conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
                column_names = {row["name"] for row in column_rows}
                for column_name in columns:
                    if column_name in column_names:
                        continue
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} TEXT"))

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _next_position(self, session: Session) -> int:
        current_max = session.scalar(select(func.max(QueueItem.queue_position)).where(QueueItem.status == QueueStatus.queued))
        return int(current_max or 0) + 1

    def enqueue_items(self, items: list[NewQueueItem]) -> list[QueueItem]:
        if not items:
            return []
        with self._queue_lock, self.session() as session:
            position = self._next_position(session)
            created: list[QueueItem] = []
            for item in items:
                queue_item = QueueItem(
                    source_url=item.source_url,
                    provider=item.provider,
                    provider_item_id=item.provider_item_id,
                    normalized_url=item.normalized_url,
                    source_type=item.source_type,
                    title=item.title,
                    channel=item.channel,
                    duration_seconds=item.duration_seconds,
                    thumbnail_url=item.thumbnail_url,
                    playlist_id=item.playlist_id,
                    status=QueueStatus.queued,
                    queue_position=position,
                )
                session.add(queue_item)
                created.append(queue_item)
                position += 1
            session.flush()
            return created

    def replace_queued_items(self, items: list[NewQueueItem]) -> list[QueueItem]:
        with self._queue_lock, self.session() as session:
            session.execute(update(QueueItem).where(QueueItem.status == QueueStatus.queued).values(status=QueueStatus.removed))
            if not items:
                return []
            created: list[QueueItem] = []
            for position, item in enumerate(items, start=1):
                queue_item = QueueItem(
                    source_url=item.source_url,
                    provider=item.provider,
                    provider_item_id=item.provider_item_id,
                    normalized_url=item.normalized_url,
                    source_type=item.source_type,
                    title=item.title,
                    channel=item.channel,
                    duration_seconds=item.duration_seconds,
                    thumbnail_url=item.thumbnail_url,
                    playlist_id=item.playlist_id,
                    status=QueueStatus.queued,
                    queue_position=position,
                )
                session.add(queue_item)
                created.append(queue_item)
            session.flush()
            return created

    @staticmethod
    def _normalize_playing_items(session: Session, *, keep_latest: bool) -> None:
        playing_items = list(
            session.scalars(
                select(QueueItem)
                .where(QueueItem.status == QueueStatus.playing)
                .order_by(QueueItem.updated_at.desc(), QueueItem.id.desc())
            ).all()
        )
        if not playing_items:
            return
        if keep_latest and len(playing_items) == 1:
            return

        keep_id = playing_items[0].id if keep_latest else None
        for item in playing_items:
            if keep_id is not None and item.id == keep_id:
                continue
            item.status = QueueStatus.skipped

    def list_queue(self) -> list[QueueItem]:
        with self._queue_lock, self.session() as session:
            self._normalize_playing_items(session, keep_latest=True)
            stmt: Select[tuple[QueueItem]] = select(QueueItem).where(
                QueueItem.status.in_([QueueStatus.queued, QueueStatus.playing])
            ).order_by(QueueItem.status.asc(), QueueItem.queue_position.asc())
            return list(session.scalars(stmt).all())

    def list_history(self, limit: int = 50) -> list[PlayHistory]:
        with self.session() as session:
            stmt = select(PlayHistory).order_by(PlayHistory.started_at.desc()).limit(limit)
            return list(session.scalars(stmt).all())

    def mark_history_rows_musicatlas_submitted(self, history_ids: list[int]) -> int:
        ids = sorted({int(history_id) for history_id in history_ids if history_id})
        if not ids:
            return 0
        with self.session() as session:
            result = session.execute(
                update(PlayHistory)
                .where(PlayHistory.id.in_(ids))
                .values(musicatlas_submitted=True)
            )
            return int(result.rowcount or 0)

    def clear_history(self) -> int:
        with self.session() as session:
            result = session.execute(delete(PlayHistory))
            return int(result.rowcount or 0)

    def clear_queue(self) -> int:
        with self._queue_lock, self.session() as session:
            removed = session.execute(
                update(QueueItem).where(QueueItem.status == QueueStatus.queued).values(status=QueueStatus.removed)
            )
            skipped = session.execute(
                update(QueueItem).where(QueueItem.status == QueueStatus.playing).values(status=QueueStatus.skipped)
            )
            return int((removed.rowcount or 0) + (skipped.rowcount or 0))

    def create_or_update_playlist(
        self,
        source_url: str,
        title: str | None,
        channel: str | None,
        entry_count: int,
        thumbnail_url: str | None = None,
    ) -> Playlist:
        with self.session() as session:
            playlist = session.scalar(select(Playlist).where(Playlist.source_url == source_url))
            if playlist is None:
                playlist = Playlist(
                    source_url=source_url,
                    title=title,
                    channel=channel,
                    thumbnail_url=thumbnail_url,
                    entry_count=entry_count,
                )
                session.add(playlist)
            else:
                playlist.title = title
                playlist.channel = channel
                playlist.thumbnail_url = thumbnail_url
                playlist.entry_count = entry_count
            session.flush()
            # Ensure server-default timestamps are populated before detaching.
            session.refresh(playlist)
            return playlist

    def create_custom_playlist(self, title: str) -> Playlist:
        with self.session() as session:
            playlist = Playlist(
                source_url=f"custom://{datetime.now(timezone.utc).timestamp()}",
                title=title,
                channel="Custom",
                entry_count=0,
            )
            session.add(playlist)
            session.flush()
            playlist.source_url = f"custom://{str(playlist.id)}"
            # Ensure server-default timestamps are populated before detaching.
            session.refresh(playlist)
            return playlist

    def ensure_custom_playlist(
        self,
        *,
        source_url: str,
        title: str,
        channel: str = "Custom",
        description: str | None = None,
        thumbnail_url: str | None = None,
        pinned: bool = False,
        can_edit: bool = True,
        can_delete: bool = True,
        sync_enabled: bool = False,
        sync_remove_missing: bool = False,
    ) -> Playlist:
        with self.session() as session:
            playlist = session.scalar(select(Playlist).where(Playlist.source_url == source_url))
            if playlist is None:
                playlist = Playlist(
                    source_url=source_url,
                    title=title,
                    channel=channel,
                    description=description,
                    thumbnail_url=thumbnail_url,
                    entry_count=0,
                    pinned=bool(pinned),
                    can_edit=bool(can_edit),
                    can_delete=bool(can_delete),
                    sync_enabled=bool(sync_enabled),
                    sync_remove_missing=bool(sync_remove_missing),
                )
                session.add(playlist)
            else:
                playlist.title = title
                playlist.channel = channel
                playlist.description = description
                playlist.thumbnail_url = thumbnail_url
                playlist.pinned = bool(pinned)
                playlist.can_edit = bool(can_edit)
                playlist.can_delete = bool(can_delete)
                playlist.sync_enabled = bool(sync_enabled)
                playlist.sync_remove_missing = bool(sync_remove_missing)
            session.flush()
            session.refresh(playlist)
            return playlist

    def list_playlists(self) -> list[Playlist]:
        with self.session() as session:
            stmt = select(Playlist).order_by(Playlist.pinned.desc(), Playlist.updated_at.desc())
            return list(session.scalars(stmt).all())

    def playlist_last_played_at_by_id(self) -> dict[uuid.UUID, datetime]:
        """Return last playback activity per playlist_id.

        Uses the latest QueueItem.updated_at for items that reached a playback-related
        status (playing/completed/skipped/failed). Queued/removed items are ignored.
        """
        playback_statuses = [
            QueueStatus.playing,
            QueueStatus.completed,
            QueueStatus.skipped,
            QueueStatus.failed,
        ]
        with self.session() as session:
            rows = session.execute(
                select(QueueItem.playlist_id, func.max(QueueItem.updated_at))
                .where(
                    QueueItem.playlist_id.is_not(None),
                    QueueItem.status.in_(playback_statuses),
                )
                .group_by(QueueItem.playlist_id)
            ).all()
            result: dict[uuid.UUID, datetime] = {}
            for playlist_id, last_played_at in rows:
                if playlist_id is None or last_played_at is None:
                    continue
                result[playlist_id] = last_played_at
            return result

    def update_playlist(
        self,
        playlist_id: uuid.UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        pinned: bool | None = None,
        sync_enabled: bool | None = None,
        sync_remove_missing: bool | None = None,
    ) -> Optional[Playlist]:
        with self.session() as session:
            playlist = session.get(Playlist, playlist_id)
            if playlist is None:
                return None
            if title is not None:
                playlist.title = title
            if description is not None:
                playlist.description = description
            if pinned is not None:
                playlist.pinned = pinned
            if sync_enabled is not None:
                playlist.sync_enabled = bool(sync_enabled)
            if sync_remove_missing is not None:
                playlist.sync_remove_missing = bool(sync_remove_missing)
            session.flush()
            # Ensure onupdate timestamps are reflected before detaching.
            session.refresh(playlist)
            return playlist

    def get_playlist(self, playlist_id: uuid.UUID) -> Optional[Playlist]:
        with self.session() as session:
            return session.get(Playlist, playlist_id)

    def set_playlist_sync_state(
        self,
        playlist_id: uuid.UUID,
        *,
        last_sync_started_at: datetime | None = None,
        last_sync_succeeded_at: datetime | None = None,
        last_sync_status: str | None = None,
        last_sync_error: str | None = None,
    ) -> Optional[Playlist]:
        with self.session() as session:
            playlist = session.get(Playlist, playlist_id)
            if playlist is None:
                return None
            if last_sync_started_at is not None:
                playlist.last_sync_started_at = last_sync_started_at
            if last_sync_succeeded_at is not None:
                playlist.last_sync_succeeded_at = last_sync_succeeded_at
            if last_sync_status is not None:
                playlist.last_sync_status = last_sync_status
            if last_sync_error is not None:
                playlist.last_sync_error = last_sync_error
            session.flush()
            session.refresh(playlist)
            return playlist

    def prune_playlist_entries_missing_upstream_ids(
        self,
        playlist_id: uuid.UUID,
        *,
        keep_upstream_item_ids: set[str],
    ) -> int:
        """Delete entries with upstream_item_id not present in keep set.

        Only entries with a non-null upstream_item_id are considered. Legacy rows
        without upstream_item_id are preserved.
        """
        with self.session() as session:
            playlist = session.get(Playlist, playlist_id)
            if playlist is None:
                return 0

            stmt = delete(PlaylistEntry).where(
                PlaylistEntry.playlist_id == playlist_id,
                PlaylistEntry.upstream_item_id.is_not(None),
            )
            if keep_upstream_item_ids:
                stmt = stmt.where(PlaylistEntry.upstream_item_id.not_in(list(keep_upstream_item_ids)))
            result = session.execute(stmt)
            removed = int(result.rowcount or 0)
            if removed > 0:
                playlist.entry_count = int(
                    session.scalar(select(func.count(PlaylistEntry.id)).where(PlaylistEntry.playlist_id == playlist_id))
                    or 0
                )
                session.flush()
                session.refresh(playlist)
            return removed

    def delete_playlist(self, playlist_id: uuid.UUID) -> bool:
        with self.session() as session:
            playlist = session.get(Playlist, playlist_id)
            if playlist is None:
                return False
            session.execute(update(QueueItem).where(QueueItem.playlist_id == playlist_id).values(playlist_id=None))
            session.execute(delete(PlaylistEntry).where(PlaylistEntry.playlist_id == playlist_id))
            session.delete(playlist)
            return True

    def replace_playlist_entries(self, playlist_id: uuid.UUID, entries: list[NewPlaylistEntry]) -> list[PlaylistEntry]:
        with self.session() as session:
            playlist = session.get(Playlist, playlist_id)
            if playlist is None:
                return []
            session.execute(delete(PlaylistEntry).where(PlaylistEntry.playlist_id == playlist_id))
            created: list[PlaylistEntry] = []
            for idx, entry in enumerate(entries, start=1):
                row = PlaylistEntry(
                    playlist_id=playlist_id,
                    source_url=entry.source_url,
                    provider=entry.provider,
                    provider_item_id=entry.provider_item_id,
                    upstream_item_id=entry.upstream_item_id,
                    normalized_url=entry.normalized_url,
                    title=entry.title,
                    channel=entry.channel,
                    duration_seconds=entry.duration_seconds,
                    thumbnail_url=entry.thumbnail_url,
                    position=idx,
                )
                session.add(row)
                created.append(row)
            playlist.entry_count = len(created)
            session.flush()
            return created

    def add_playlist_entries(self, playlist_id: uuid.UUID, entries: list[NewPlaylistEntry]) -> list[PlaylistEntry]:
        if not entries:
            return []
        with self.session() as session:
            playlist = session.get(Playlist, playlist_id)
            if playlist is None:
                return []
            next_pos = int(
                session.scalar(select(func.max(PlaylistEntry.position)).where(PlaylistEntry.playlist_id == playlist_id)) or 0
            ) + 1
            created: list[PlaylistEntry] = []
            for entry in entries:
                row = PlaylistEntry(
                    playlist_id=playlist_id,
                    source_url=entry.source_url,
                    provider=entry.provider,
                    provider_item_id=entry.provider_item_id,
                    upstream_item_id=entry.upstream_item_id,
                    normalized_url=entry.normalized_url,
                    title=entry.title,
                    channel=entry.channel,
                    duration_seconds=entry.duration_seconds,
                    thumbnail_url=entry.thumbnail_url,
                    position=next_pos,
                )
                session.add(row)
                created.append(row)
                next_pos += 1
            playlist.entry_count = int(
                session.scalar(select(func.count(PlaylistEntry.id)).where(PlaylistEntry.playlist_id == playlist_id))
            )
            session.flush()
            return created

    def add_playlist_entry(self, playlist_id: uuid.UUID, entry: NewPlaylistEntry) -> Optional[PlaylistEntry]:
        with self.session() as session:
            playlist = session.get(Playlist, playlist_id)
            if playlist is None:
                return None
            next_pos = int(
                session.scalar(select(func.max(PlaylistEntry.position)).where(PlaylistEntry.playlist_id == playlist_id)) or 0
            ) + 1
            row = PlaylistEntry(
                playlist_id=playlist_id,
                source_url=entry.source_url,
                provider=entry.provider,
                provider_item_id=entry.provider_item_id,
                upstream_item_id=entry.upstream_item_id,
                normalized_url=entry.normalized_url,
                title=entry.title,
                channel=entry.channel,
                duration_seconds=entry.duration_seconds,
                thumbnail_url=entry.thumbnail_url,
                position=next_pos,
            )
            session.add(row)
            playlist.entry_count = next_pos
            session.flush()
            return row

    def list_playlist_entries(self, playlist_id: uuid.UUID) -> list[PlaylistEntry]:
        with self.session() as session:
            stmt = select(PlaylistEntry).where(PlaylistEntry.playlist_id == playlist_id).order_by(PlaylistEntry.position.asc())
            return list(session.scalars(stmt).all())

    def get_playlist_entry(self, entry_id: int) -> Optional[PlaylistEntry]:
        with self.session() as session:
            return session.get(PlaylistEntry, entry_id)

    def update_playlist_entry(self, entry_id: int, entry: NewPlaylistEntry) -> Optional[PlaylistEntry]:
        with self.session() as session:
            row = session.get(PlaylistEntry, entry_id)
            if row is None:
                return None
            row.source_url = entry.source_url
            row.provider = entry.provider
            row.provider_item_id = entry.provider_item_id
            if entry.upstream_item_id is not None:
                row.upstream_item_id = entry.upstream_item_id
            row.normalized_url = entry.normalized_url
            row.title = entry.title
            row.channel = entry.channel
            row.duration_seconds = entry.duration_seconds
            row.thumbnail_url = entry.thumbnail_url
            session.flush()
            return row

    def set_playlist_entry_spotify_import_searched(self, entry_id: int, searched: bool = True) -> Optional[PlaylistEntry]:
        with self.session() as session:
            row = session.get(PlaylistEntry, entry_id)
            if row is None:
                return None
            row.spotify_import_searched = searched
            session.flush()
            return row

    def get_playlist_dedup_keys(self, playlist_id: uuid.UUID) -> set[tuple[str, str | None]]:
        """Return (normalized_url, provider_item_id) pairs for duplicate detection."""
        entries = self.list_playlist_entries(playlist_id)
        keys: set[tuple[str, str | None]] = set()
        for e in entries:
            norm = (e.normalized_url or "").strip()
            pid = (e.provider_item_id or "").strip() or None
            if norm:
                keys.add((norm, pid))
            elif pid:
                keys.add(("", pid))
        return keys

    def get_first_playlist_entry(self, playlist_id: uuid.UUID) -> Optional[PlaylistEntry]:
        with self.session() as session:
            stmt = (
                select(PlaylistEntry)
                .where(PlaylistEntry.playlist_id == playlist_id)
                .order_by(PlaylistEntry.position.asc(), PlaylistEntry.id.asc())
                .limit(1)
            )
            return session.scalar(stmt)

    def queue_playlist(self, playlist_id: uuid.UUID, *, replace: bool = False) -> list[QueueItem]:
        entries = self.list_playlist_entries(playlist_id)
        new_items = [
            NewQueueItem(
                source_url=entry.source_url,
                provider=entry.provider,
                provider_item_id=entry.provider_item_id,
                normalized_url=entry.normalized_url,
                source_type=entry.provider or "unknown",
                title=entry.title,
                channel=entry.channel,
                duration_seconds=entry.duration_seconds,
                thumbnail_url=entry.thumbnail_url,
                playlist_id=playlist_id,
            )
            for entry in entries
        ]
        if replace:
            return self.replace_queued_items(new_items)
        return self.enqueue_items(new_items)

    def queue_playlist_entry(self, entry_id: int) -> Optional[QueueItem]:
        with self.session() as session:
            entry = session.get(PlaylistEntry, entry_id)
            if entry is None:
                return None
            playlist_id = entry.playlist_id
            new_item = NewQueueItem(
                source_url=entry.source_url,
                provider=entry.provider,
                provider_item_id=entry.provider_item_id,
                normalized_url=entry.normalized_url,
                source_type=entry.provider or "unknown",
                title=entry.title,
                channel=entry.channel,
                duration_seconds=entry.duration_seconds,
                thumbnail_url=entry.thumbnail_url,
                playlist_id=playlist_id,
            )
        queued = self.enqueue_items([new_item])
        return queued[0] if queued else None

    def delete_playlist_entry(self, entry_id: int) -> bool:
        with self.session() as session:
            entry = session.get(PlaylistEntry, entry_id)
            if entry is None:
                return False
            playlist_id = entry.playlist_id
            session.delete(entry)
            playlist = session.get(Playlist, playlist_id)
            if playlist is not None and playlist.entry_count > 0:
                playlist.entry_count -= 1
            return True

    def reorder_playlist_entry(self, entry_id: int, new_position: int) -> bool:
        with self.session() as session:
            entry = session.get(PlaylistEntry, entry_id)
            if entry is None:
                return False
            playlist_id = entry.playlist_id
            entries = list(
                session.scalars(
                    select(PlaylistEntry)
                    .where(PlaylistEntry.playlist_id == playlist_id)
                    .order_by(PlaylistEntry.position.asc())
                ).all()
            )
            if not entries:
                return False
            idx = next((i for i, e in enumerate(entries) if e.id == entry_id), None)
            if idx is None:
                return False
            item = entries.pop(idx)
            bounded_target = max(0, min(new_position, len(entries)))
            entries.insert(bounded_target, item)
            for pos, e in enumerate(entries, start=1):
                e.position = pos
            return True

    def has_queued_items(self) -> bool:
        with self.session() as session:
            count = session.scalar(select(func.count(QueueItem.id)).where(QueueItem.status == QueueStatus.queued))
            return bool(count and count > 0)

    def queued_count(self) -> int:
        with self.session() as session:
            count = session.scalar(select(func.count(QueueItem.id)).where(QueueItem.status == QueueStatus.queued))
            return int(count or 0)

    def list_queued_ids(self) -> list[int]:
        with self.session() as session:
            stmt = select(QueueItem.id).where(QueueItem.status == QueueStatus.queued).order_by(QueueItem.queue_position.asc())
            return [int(item_id) for item_id in session.scalars(stmt).all()]

    def dequeue_next(self) -> QueueItem | None:
        with self._queue_lock, self.session() as session:
            self._normalize_playing_items(session, keep_latest=False)
            next_item = session.scalar(
                select(QueueItem)
                .where(QueueItem.status == QueueStatus.queued)
                .order_by(QueueItem.queue_position.asc())
                .limit(1)
            )
            if next_item is None:
                return None
            next_item.status = QueueStatus.playing
            return next_item

    def mark_item_resolved(self, item_id: int, stream_url: str) -> None:
        with self.session() as session:
            item = session.get(QueueItem, item_id)
            if item is None:
                return
            item.resolved_stream_url = stream_url
            item.resolved_at = datetime.now(timezone.utc)

    def mark_playback_finished(self, item_id: int, status: QueueStatus, error_message: str | None = None) -> None:
        with self._queue_lock, self.session() as session:
            item = session.get(QueueItem, item_id)
            if item is None:
                return
            item.status = status
            session.add(
                PlayHistory(
                    queue_item_id=item.id,
                    title=item.title,
                    source_url=item.source_url,
                    provider=item.provider,
                    provider_item_id=item.provider_item_id,
                    thumbnail_url=item.thumbnail_url,
                    musicatlas_submitted=False,
                    status=status.value,
                    error_message=error_message,
                    finished_at=datetime.now(timezone.utc),
                )
            )

    def remove_item(self, item_id: int) -> bool:
        with self._queue_lock, self.session() as session:
            item = session.get(QueueItem, item_id)
            if item is None:
                return False
            if item.status == QueueStatus.playing:
                item.status = QueueStatus.skipped
            else:
                item.status = QueueStatus.removed
            return True

    def reorder_item(self, item_id: int, new_position: int) -> bool:
        with self._queue_lock, self.session() as session:
            queue_items = list(
                session.scalars(
                    select(QueueItem)
                    .where(QueueItem.status == QueueStatus.queued)
                    .order_by(QueueItem.queue_position.asc())
                ).all()
            )
            if not queue_items:
                return False
            idx = next((i for i, item in enumerate(queue_items) if item.id == item_id), None)
            if idx is None:
                return False
            item = queue_items.pop(idx)
            bounded_target = max(0, min(new_position, len(queue_items)))
            queue_items.insert(bounded_target, item)
            for pos, queue_item in enumerate(queue_items, start=1):
                queue_item.queue_position = pos
            return True

    def reorder_queued_items(self, item_ids: list[int]) -> bool:
        with self._queue_lock, self.session() as session:
            queue_items = list(
                session.scalars(
                    select(QueueItem)
                    .where(QueueItem.status == QueueStatus.queued)
                    .order_by(QueueItem.queue_position.asc())
                ).all()
            )
            if not queue_items:
                return False

            items_by_id = {item.id: item for item in queue_items}
            reordered: list[QueueItem] = []
            seen_ids: set[int] = set()

            for item_id in item_ids:
                item = items_by_id.get(item_id)
                if item is None or item.id in seen_ids:
                    continue
                reordered.append(item)
                seen_ids.add(item.id)

            for item in queue_items:
                if item.id in seen_ids:
                    continue
                reordered.append(item)

            for pos, queue_item in enumerate(reordered, start=1):
                queue_item.queue_position = pos
            return True

    def move_item_to_front(self, item_id: int) -> bool:
        return self.reorder_item(item_id=item_id, new_position=0)

    def get_item(self, item_id: int) -> Optional[QueueItem]:
        with self.session() as session:
            return session.get(QueueItem, item_id)

    def get_setting(self, key: str) -> str | None:
        with self.session() as session:
            setting = session.get(Setting, key)
            return None if setting is None else setting.value

    def set_setting(self, key: str, value: str) -> None:
        with self.session() as session:
            setting = session.get(Setting, key)
            if setting is None:
                session.add(Setting(key=key, value=value))
            else:
                setting.value = value

    def clear_setting(self, key: str) -> None:
        with self.session() as session:
            setting = session.get(Setting, key)
            if setting is not None:
                session.delete(setting)

    def get_playlist_by_source_url(self, source_url: str) -> Optional[Playlist]:
        with self.session() as session:
            return session.scalar(select(Playlist).where(Playlist.source_url == source_url))

    def playlist_contains_track(
        self,
        playlist_id: uuid.UUID,
        *,
        normalized_url: str | None,
        provider_item_id: str | None,
    ) -> bool:
        norm = (normalized_url or "").strip()
        pid = (provider_item_id or "").strip() or None
        if not norm and not pid:
            return False
        with self.session() as session:
            stmt = select(func.count(PlaylistEntry.id)).where(PlaylistEntry.playlist_id == playlist_id)
            if norm:
                stmt = stmt.where(PlaylistEntry.normalized_url == norm)
            elif pid:
                stmt = stmt.where(PlaylistEntry.provider_item_id == pid)
            count = session.scalar(stmt)
            return bool(count and int(count) > 0)

    def remove_playlist_track(
        self,
        playlist_id: uuid.UUID,
        *,
        normalized_url: str | None,
        provider_item_id: str | None,
    ) -> int:
        norm = (normalized_url or "").strip()
        pid = (provider_item_id or "").strip() or None
        if not norm and not pid:
            return 0
        with self.session() as session:
            playlist = session.get(Playlist, playlist_id)
            if playlist is None:
                return 0
            stmt = delete(PlaylistEntry).where(PlaylistEntry.playlist_id == playlist_id)
            if norm:
                stmt = stmt.where(PlaylistEntry.normalized_url == norm)
            elif pid:
                stmt = stmt.where(PlaylistEntry.provider_item_id == pid)
            result = session.execute(stmt)
            removed = int(result.rowcount or 0)
            if removed > 0:
                playlist.entry_count = max(
                    0,
                    int(
                        session.scalar(
                            select(func.count(PlaylistEntry.id)).where(PlaylistEntry.playlist_id == playlist_id)
                        )
                        or 0
                    ),
                )
            return removed
