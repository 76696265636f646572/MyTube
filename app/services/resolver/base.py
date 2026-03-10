from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class ResolverError(RuntimeError):
    pass


@dataclass
class ResolvedTrack:
    source_url: str
    normalized_url: str
    title: str | None
    channel: str | None
    duration_seconds: int | None
    thumbnail_url: str | None
    stream_url: str
    source_site: str | None = None
    is_live: bool = False
    can_seek: bool = True
    uploaded_at: str | None = None


@dataclass
class PlaylistPreview:
    source_url: str
    title: str | None
    channel: str | None
    entries: list[dict[str, Any]]
    thumbnail_url: str | None = None


class SourceResolver(ABC):
    @abstractmethod
    def normalize_url(self, url: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_playlist_url(self, url: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def resolve_video(self, url: str) -> ResolvedTrack:
        raise NotImplementedError

    @abstractmethod
    def spawn_audio_stream(self, url: str) -> subprocess.Popen[bytes]:
        raise NotImplementedError

    @abstractmethod
    def preview_playlist(self, url: str) -> PlaylistPreview:
        raise NotImplementedError

    def search(self, query: str, site: str = "youtube", limit: int = 10) -> list[dict[str, Any]]:
        raise NotImplementedError

