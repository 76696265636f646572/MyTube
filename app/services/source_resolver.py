from __future__ import annotations

import subprocess
from typing import Any

from app.services.resolver.base import PlaylistPreview, ResolvedTrack, SourceResolver
from app.services.resolver.direct_resolver import DirectUrlResolver
from app.services.resolver.yt_dlp_resolver import YtDlpResolver


class CompositeSourceResolver(SourceResolver):
    def __init__(
        self,
        *,
        yt_dlp_resolver: YtDlpResolver,
        direct_resolver: DirectUrlResolver,
        searchable_sites: list[str] | None = None,
        default_enabled_search_sites: list[str] | None = None,
    ) -> None:
        self.yt_dlp_resolver = yt_dlp_resolver
        self.direct_resolver = direct_resolver
        self.searchable_sites = [site.strip().lower() for site in (searchable_sites or []) if site.strip()]
        self.default_enabled_search_sites = [
            site.strip().lower() for site in (default_enabled_search_sites or []) if site.strip()
        ]

    def _resolver_for_url(self, url: str) -> SourceResolver:
        if self.direct_resolver.can_handle_url(url):
            return self.direct_resolver
        return self.yt_dlp_resolver

    def normalize_url(self, url: str) -> str:
        return self._resolver_for_url(url).normalize_url(url)

    def is_playlist_url(self, url: str) -> bool:
        return self._resolver_for_url(url).is_playlist_url(url)

    def resolve_video(self, url: str) -> ResolvedTrack:
        return self._resolver_for_url(url).resolve_video(url)

    def spawn_audio_stream(self, url: str) -> subprocess.Popen[bytes]:
        return self._resolver_for_url(url).spawn_audio_stream(url)

    def preview_playlist(self, url: str) -> PlaylistPreview:
        return self._resolver_for_url(url).preview_playlist(url)

    def _normalized_search_sites(self, sites: list[str] | None = None) -> list[str]:
        if sites:
            requested = [site.strip().lower() for site in sites if site and site.strip()]
        else:
            requested = list(self.default_enabled_search_sites)
        if self.searchable_sites:
            allowed = set(self.searchable_sites)
            requested = [site for site in requested if site in allowed]
        if not requested:
            return list(self.default_enabled_search_sites)
        seen: set[str] = set()
        ordered: list[str] = []
        for site in requested:
            if site in seen:
                continue
            seen.add(site)
            ordered.append(site)
        return ordered

    def search(self, query: str, site: str = "youtube", limit: int = 10) -> list[dict[str, Any]]:
        return self.yt_dlp_resolver.search(query=query, site=site, limit=limit)

    def searchable_sites_payload(self) -> dict[str, list[str]]:
        return {
            "sites": list(self.searchable_sites),
            "default_enabled_sites": self._normalized_search_sites(),
        }

    def effective_search_sites(self, requested_sites: list[str] | None = None) -> list[str]:
        return self._normalized_search_sites(requested_sites)

