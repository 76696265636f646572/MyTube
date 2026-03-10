from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid


class Base(DeclarativeBase):
    pass


class QueueStatus(str, Enum):
    queued = "queued"
    playing = "playing"
    completed = "completed"
    failed = "failed"
    removed = "removed"
    skipped = "skipped"


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    channel: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    queue_items: Mapped[list["QueueItem"]] = relationship(back_populates="playlist")
    entries: Mapped[list["PlaylistEntry"]] = relationship(back_populates="playlist")


class QueueItem(Base):
    __tablename__ = "queue_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="video")
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    channel: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[QueueStatus] = mapped_column(SqlEnum(QueueStatus), nullable=False, default=QueueStatus.queued)
    queue_position: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    resolved_stream_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    playlist_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("playlists.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    playlist: Mapped[Optional[Playlist]] = relationship(back_populates="queue_items")
    history_entries: Mapped[list["PlayHistory"]] = relationship(back_populates="queue_item")


class PlaylistEntry(Base):
    __tablename__ = "playlist_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    playlist_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("playlists.id"), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    channel: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    playlist: Mapped[Playlist] = relationship(back_populates="entries")


class PlayHistory(Base):
    __tablename__ = "play_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    queue_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("queue_items.id"), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    queue_item: Mapped[Optional[QueueItem]] = relationship(back_populates="history_entries")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
