from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from app.services.extractors.dispatcher import ExtractorDispatcher
from app.services.extractors.youtube import (
    is_start_radio_url,
    normalize_single_url,
    youtube_video_id_from_url,
)
from app.services.yt_dlp_client import YtDlpClient, YtDlpError


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
    def __init__(self, binary_path: str, ffmpeg_path: str, deno_path: str) -> None:
        self.client = YtDlpClient(binary_path=binary_path, ffmpeg_path=ffmpeg_path, deno_path=deno_path)
        self.dispatcher = ExtractorDispatcher()

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

    def spawn_audio_stream(self, url: str):
        return self.client.spawn_audio_stream(url)

    def resolve_video(self, url: str) -> ResolvedTrack:
        dispatch = self.dispatcher.dispatch(url)
        if dispatch.is_playlist:
            raise YtDlpError("Expected a single item URL, got playlist URL")
        raw = self.client.get_single_json(url)
        resolved = dispatch.extractor.extract_single(url, raw)
        stream_url = self.client.get_stream_url(resolved.source_url)
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
        raw = self.client.get_playlist_json(url)
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
                futures_by_provider[provider] = executor.submit(
                    self.client.search_json,
                    query=query,
                    provider=provider,
                    limit=limit,
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
