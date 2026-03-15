from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


UrlKind = str


@dataclass(frozen=True)
class ResolvedItem:
    provider: str
    source_url: str
    normalized_url: str
    title: str | None
    channel: str | None
    duration_seconds: int | None
    thumbnail_url: str | None
    provider_item_id: str | None
    item_type: str


@dataclass(frozen=True)
class ResolvedCollection:
    provider: str
    source_url: str
    title: str | None
    channel: str | None
    thumbnail_url: str | None
    items: list[ResolvedItem]


@dataclass(frozen=True)
class SearchItem:
    provider: str
    source_url: str
    normalized_url: str
    title: str | None
    channel: str | None
    duration_seconds: int | None
    thumbnail_url: str | None
    provider_item_id: str | None


class Extractor(Protocol):
    provider: str
    json_keys: dict[str, tuple[str, ...]]

    def can_handle(self, url: str) -> bool:
        ...

    def classify_url(self, url: str) -> UrlKind:
        ...

    def extract_single(self, url: str, raw_json: dict[str, Any]) -> ResolvedItem:
        ...

    def extract_playlist(self, url: str, raw_json: dict[str, Any]) -> ResolvedCollection:
        ...

    def extract_search_results(self, raw_json: dict[str, Any]) -> list[SearchItem]:
        ...
