from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.db.repository import Repository
from app.services.extractors.dispatcher import ExtractorDispatcher
from app.services.extractors.youtube import (
    normalize_playlist_url,
    is_start_radio_url,
    normalize_single_url,
)
from app.services.yt_dlp_client import YtDlpClient, YtDlpError


COOKIE_PROVIDER_LABELS: dict[str, str] = {
    "youtube": "YouTube",
    "soundcloud": "SoundCloud",
    "mixcloud": "MixCloud",
}


def list_cookie_providers() -> list[dict[str, str]]:
    return [{"provider": provider, "label": label} for provider, label in COOKIE_PROVIDER_LABELS.items()]


def is_supported_cookie_provider(provider: str) -> bool:
    return provider in COOKIE_PROVIDER_LABELS


def cookie_setting_key(provider: str) -> str:
    return f"cookies:{provider}"


@dataclass
class ResolvedTrack:
    source_url: str
    normalized_url: str
    title: str | None
    channel: str | None
    duration_seconds: int | None
    thumbnail_url: str | None
    stream_url: str
    provider: str = "youtube"
    provider_item_id: str | None = None
    is_live: bool = False
    # When set, stored on queue rows as source_type (e.g. remote_audio, local_file).
    item_source_type: str | None = None


@dataclass
class PlaylistPreview:
    source_url: str
    title: str | None
    channel: str | None
    entries: list[dict[str, Any]]
    provider: str = "youtube"
    thumbnail_url: str | None = None


@dataclass
class UserPlaylistSummary:
    source_url: str
    title: str | None
    channel: str | None
    thumbnail_url: str | None
    entry_count: int
    provider: str = "youtube"
    provider_item_id: str | None = None


class YtDlpService:
    def __init__(
        self,
        binary_path: str,
        ffmpeg_path: str,
        deno_path: str,
        repository: Repository | None = None,
    ) -> None:
        self.client = YtDlpClient(binary_path=binary_path, ffmpeg_path=ffmpeg_path, deno_path=deno_path)
        self.dispatcher = ExtractorDispatcher()
        self.repository = repository
        self._resolved_cache_lock = threading.Lock()
        self._resolved_cache_by_url: dict[str, ResolvedTrack] = {}
        self._resolved_cache_order: deque[str] = deque()
        self._resolved_cache_limit = 64
        self._playlist_cache_lock = threading.Lock()
        self._playlist_preview_cache_by_url: dict[str, PlaylistPreview] = {}
        self._playlist_preview_cache_order: deque[str] = deque()
        self._playlist_preview_cache_limit = 32

    @staticmethod
    def _cache_key_for_lookup_url(url: str, cookie_file: str | None) -> str:
        cookie_fingerprint = cookie_file or "-"
        return f"{cookie_fingerprint}::{url}"

    def _get_cached_resolved_track(self, url: str, cookie_file: str | None) -> ResolvedTrack | None:
        normalized_url = self.normalize_url(url)
        lookup_keys = {
            self._cache_key_for_lookup_url(url, cookie_file),
            self._cache_key_for_lookup_url(normalized_url, cookie_file),
        }
        with self._resolved_cache_lock:
            for lookup_key in lookup_keys:
                cached = self._resolved_cache_by_url.get(lookup_key)
                if cached is not None:
                    return cached
        return None

    def _cache_resolved_track(
        self,
        lookup_urls: list[str],
        resolved: ResolvedTrack,
        cookie_file: str | None,
    ) -> None:
        with self._resolved_cache_lock:
            for lookup_url in lookup_urls:
                if not lookup_url:
                    continue
                cache_key = self._cache_key_for_lookup_url(lookup_url, cookie_file)
                if cache_key in self._resolved_cache_order:
                    self._resolved_cache_order.remove(cache_key)
                self._resolved_cache_order.append(cache_key)
                self._resolved_cache_by_url[cache_key] = resolved
            while len(self._resolved_cache_order) > self._resolved_cache_limit:
                stale_url = self._resolved_cache_order.popleft()
                self._resolved_cache_by_url.pop(stale_url, None)

    def _normalize_playlist_cache_key(self, url: str, provider: str, cookie_file: str | None) -> str:
        if provider == "youtube":
            return self._cache_key_for_lookup_url(normalize_playlist_url(url), cookie_file)
        return self._cache_key_for_lookup_url(url, cookie_file)

    def _get_cached_playlist_preview(self, lookup_urls: list[str]) -> PlaylistPreview | None:
        with self._playlist_cache_lock:
            for lookup_url in lookup_urls:
                cached = self._playlist_preview_cache_by_url.get(lookup_url)
                if cached is not None:
                    return cached
        return None

    def _cache_playlist_preview(self, lookup_urls: list[str], preview: PlaylistPreview) -> None:
        with self._playlist_cache_lock:
            for lookup_url in lookup_urls:
                if not lookup_url:
                    continue
                if lookup_url in self._playlist_preview_cache_order:
                    self._playlist_preview_cache_order.remove(lookup_url)
                self._playlist_preview_cache_order.append(lookup_url)
                self._playlist_preview_cache_by_url[lookup_url] = preview
            while len(self._playlist_preview_cache_order) > self._playlist_preview_cache_limit:
                stale_url = self._playlist_preview_cache_order.popleft()
                self._playlist_preview_cache_by_url.pop(stale_url, None)

    def ensure_available(self) -> None:
        self.client.ensure_available()

    def normalize_url(self, url: str) -> str:
        try:
            extractor = self.dispatcher.get_extractor(url)
        except ValueError:
            return url
        if extractor.provider == "youtube":
            return normalize_single_url(url)
        return url

    def is_playlist_url(self, url: str) -> bool:
        try:
            return self.dispatcher.is_playlist_url(url)
        except ValueError:
            return False

    def is_start_radio_url(self, url: str) -> bool:
        return is_start_radio_url(url)

    def _cookie_file_for_provider(self, provider: str) -> str | None:
        if self.repository is None:
            return None
        if not is_supported_cookie_provider(provider):
            return None
        cookie_value = self.repository.get_setting(cookie_setting_key(provider))
        return self.client.resolve_cookie_file(provider, cookie_value)

    def _cookie_file_for_url(self, url: str) -> str | None:
        try:
            provider = self.dispatcher.detect_provider(url)
        except ValueError:
            return None
        return self._cookie_file_for_provider(provider)

    def spawn_audio_stream(self, url: str):
        cookie_file = self._cookie_file_for_url(url)
        return self.client.spawn_audio_stream(url, cookie_file=cookie_file)

    def resolve_video(self, url: str, force_refresh: bool = False) -> ResolvedTrack:
        cookie_file = self._cookie_file_for_url(url)
        if not force_refresh:
            cached = self._get_cached_resolved_track(url, cookie_file)
            if cached is not None:
                return cached
        dispatch = self.dispatcher.dispatch(url)
        if dispatch.is_playlist:
            raise YtDlpError("Expected a single item URL, got playlist URL")
        raw = self.client.get_single_json(url, cookie_file=cookie_file)
        extracted = dispatch.extractor.extract_single(url, raw)
        stream_url = str(raw.get("url") or "").strip()
        if not stream_url:
            requested_downloads = raw.get("requested_downloads")
            if isinstance(requested_downloads, list):
                stream_url = next(
                    (
                        str(entry.get("url") or "").strip()
                        for entry in requested_downloads
                        if isinstance(entry, dict) and entry.get("url")
                    ),
                    "",
                )
        if not stream_url:
            requested_formats = raw.get("requested_formats")
            if isinstance(requested_formats, list):
                stream_url = next(
                    (
                        str(entry.get("url") or "").strip()
                        for entry in requested_formats
                        if isinstance(entry, dict) and entry.get("url")
                    ),
                    "",
                )
        if not stream_url:
            raise YtDlpError("Could not resolve direct stream URL from yt-dlp metadata")
        resolved = ResolvedTrack(
            provider=extracted.provider,
            provider_item_id=extracted.provider_item_id,
            source_url=extracted.source_url,
            normalized_url=extracted.normalized_url,
            title=extracted.title,
            channel=extracted.channel,
            duration_seconds=extracted.duration_seconds,
            thumbnail_url=extracted.thumbnail_url,
            stream_url=stream_url,
            is_live=bool(raw.get("is_live", False)),
        )
        self._cache_resolved_track(
            [url, resolved.source_url, resolved.normalized_url],
            resolved,
            cookie_file,
        )
        return resolved

    def preview_playlist(self, url: str) -> PlaylistPreview:
        dispatch = self.dispatcher.dispatch(url)
        if not dispatch.is_playlist:
            raise YtDlpError("Expected a playlist URL, got single item URL")
        cookie_file = self._cookie_file_for_url(url)
        normalized_cache_key = self._normalize_playlist_cache_key(url, dispatch.extractor.provider, cookie_file)
        cached = self._get_cached_playlist_preview(
            [
                self._cache_key_for_lookup_url(url, cookie_file),
                normalized_cache_key,
            ]
        )
        if cached is not None:
            return cached
        raw = self.client.get_playlist_json(url, cookie_file=cookie_file)
        collection = dispatch.extractor.extract_playlist(url, raw)
        entries = [
            {
                "provider": item.provider,
                "provider_item_id": item.provider_item_id,
                "source_url": item.source_url,
                "normalized_url": item.normalized_url,
                "source_type": item.provider,
                "title": item.title,
                "channel": item.channel,
                "duration_seconds": item.duration_seconds,
                "thumbnail_url": item.thumbnail_url,
            }
            for item in collection.items
        ]
        preview = PlaylistPreview(
            provider=collection.provider,
            source_url=collection.source_url,
            title=collection.title,
            channel=collection.channel,
            entries=entries,
            thumbnail_url=collection.thumbnail_url,
        )
        self._cache_playlist_preview(
            [
                self._cache_key_for_lookup_url(url, cookie_file),
                normalized_cache_key,
                self._normalize_playlist_cache_key(preview.source_url, preview.provider, cookie_file),
            ],
            preview,
        )
        return preview

    def search(self, query: str, limit: int = 10, providers: list[str] | None = None) -> list[dict[str, Any]]:
        active_providers = providers or ["youtube", "soundcloud", "mixcloud"]
        results: list[dict[str, Any]] = []
        provider_extractors: list[tuple[str, Any]] = []
        for provider in active_providers:
            extractor = self.dispatcher.get_extractor_for_provider(provider)
            if extractor is None:
                continue
            provider_extractors.append((provider, extractor))

        if not provider_extractors:
            return results

        futures_by_provider: dict[str, Any] = {}
        max_workers = min(len(provider_extractors), 8)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for provider, _extractor in provider_extractors:
                cookie_file = self._cookie_file_for_provider(provider)
                futures_by_provider[provider] = executor.submit(
                    self.client.search_json,
                    query=query,
                    provider=provider,
                    limit=limit,
                    cookie_file=cookie_file,
                )

            # Preserve provider ordering even though requests run concurrently.
            for provider, extractor in provider_extractors:
                payload = futures_by_provider[provider].result()
                for item in extractor.extract_search_results(payload):
                    results.append(
                        {
                            "provider": item.provider,
                            "provider_item_id": item.provider_item_id,
                            "source_url": item.source_url,
                            "normalized_url": item.normalized_url,
                            "title": item.title,
                            "channel": item.channel,
                            "duration_seconds": item.duration_seconds,
                            "thumbnail_url": item.thumbnail_url,
                        }
                    )
        return results

    def search_single_provider(self, query: str, *, provider: str, limit: int = 10) -> list[dict[str, Any]]:
        """Run yt-dlp search for exactly one provider (sequential, no thread pool)."""
        extractor = self.dispatcher.get_extractor_for_provider(provider)
        if extractor is None:
            return []
        cookie_file = self._cookie_file_for_provider(provider)
        payload = self.client.search_json(query=query, provider=provider, limit=limit, cookie_file=cookie_file)
        return [
            {
                "provider": item.provider,
                "provider_item_id": item.provider_item_id,
                "source_url": item.source_url,
                "normalized_url": item.normalized_url,
                "title": item.title,
                "channel": item.channel,
                "duration_seconds": item.duration_seconds,
                "thumbnail_url": item.thumbnail_url,
            }
            for item in extractor.extract_search_results(payload)
        ]

    def search_videos(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        # Backward-compatible shim retained for older call sites/tests.
        return self.search(query=query, limit=limit, providers=["youtube"])

    @staticmethod
    def _playlist_id_from_url(url: str | None) -> str | None:
        if not url:
            return None
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        playlist_id = (query.get("list") or [None])[0]
        if playlist_id:
            return playlist_id
        path = (parsed.path or "").strip("/")
        if path.startswith("playlist/"):
            remainder = path.split("/", 1)[1]
            return remainder or None
        return None

    def list_youtube_user_playlists(self) -> list[UserPlaylistSummary]:
        cookie_file = self._cookie_file_for_provider("youtube")
        if not cookie_file:
            return []

        raw = self.client.get_playlist_json("https://www.youtube.com/feed/playlists", cookie_file=cookie_file)
        entries = raw.get("entries") if isinstance(raw, dict) else []
        if not isinstance(entries, list):
            return []

        discovered: list[UserPlaylistSummary] = []
        seen_ids: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            source_url = entry.get("url") or entry.get("webpage_url") or entry.get("original_url")
            playlist_id = self._playlist_id_from_url(source_url) or str(entry.get("id") or "").strip() or None
            if not playlist_id or playlist_id in seen_ids:
                continue
            seen_ids.add(playlist_id)
            canonical_url = normalize_playlist_url(f"https://www.youtube.com/playlist?list={playlist_id}")
            first_video_thumbnail = self._first_video_thumbnail_for_playlist(
                canonical_url,
                cookie_file=cookie_file,
            )
            count_value = entry.get("playlist_count")
            count = int(count_value) if isinstance(count_value, int) else 0
            discovered.append(
                UserPlaylistSummary(
                    source_url=canonical_url,
                    title=entry.get("title"),
                    channel=entry.get("uploader") or entry.get("channel"),
                    thumbnail_url=first_video_thumbnail or entry.get("thumbnail"),
                    entry_count=count if count >= 0 else 0,
                    provider_item_id=playlist_id,
                )
            )
        return discovered

    def _first_video_thumbnail_for_playlist(self, playlist_url: str, *, cookie_file: str | None) -> str | None:
        try:
            raw = self.client.get_playlist_json(playlist_url, cookie_file=cookie_file)
        except Exception:
            return None
        entries = raw.get("entries") if isinstance(raw, dict) else None
        if not isinstance(entries, list) or not entries:
            return "https://i.ytimg.com/img/no_thumbnail.jpg"
        first = entries[0]
        if not isinstance(first, dict):
            return "https://i.ytimg.com/img/no_thumbnail.jpg"
        first_id = first.get("id")
        if not first_id or not isinstance(first_id, str):
            return "https://i.ytimg.com/img/no_thumbnail.jpg"
        return f"https://i.ytimg.com/vi/{first_id}/hqdefault.jpg"
