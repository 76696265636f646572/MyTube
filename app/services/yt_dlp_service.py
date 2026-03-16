from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from app.db.repository import Repository
from app.services.extractors.dispatcher import ExtractorDispatcher
from app.services.extractors.youtube import (
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


@dataclass
class PlaylistPreview:
    source_url: str
    title: str | None
    channel: str | None
    entries: list[dict[str, Any]]
    provider: str = "youtube"
    thumbnail_url: str | None = None


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

    def resolve_video(self, url: str) -> ResolvedTrack:
        dispatch = self.dispatcher.dispatch(url)
        if dispatch.is_playlist:
            raise YtDlpError("Expected a single item URL, got playlist URL")
        cookie_file = self._cookie_file_for_url(url)
        raw = self.client.get_single_json(url, cookie_file=cookie_file)
        resolved = dispatch.extractor.extract_single(url, raw)
        stream_url = self.client.get_stream_url(resolved.source_url, cookie_file=cookie_file)
        return ResolvedTrack(
            provider=resolved.provider,
            provider_item_id=resolved.provider_item_id,
            source_url=resolved.source_url,
            normalized_url=resolved.normalized_url,
            title=resolved.title,
            channel=resolved.channel,
            duration_seconds=resolved.duration_seconds,
            thumbnail_url=resolved.thumbnail_url,
            stream_url=stream_url,
            is_live=bool(raw.get("is_live", False)),
        )

    def preview_playlist(self, url: str) -> PlaylistPreview:
        dispatch = self.dispatcher.dispatch(url)
        if not dispatch.is_playlist:
            raise YtDlpError("Expected a playlist URL, got single item URL")
        cookie_file = self._cookie_file_for_url(url)
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
        return PlaylistPreview(
            provider=collection.provider,
            source_url=collection.source_url,
            title=collection.title,
            channel=collection.channel,
            entries=entries,
            thumbnail_url=collection.thumbnail_url,
        )

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

    def search_videos(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        # Backward-compatible shim retained for older call sites/tests.
        return self.search(query=query, limit=limit, providers=["youtube"])
