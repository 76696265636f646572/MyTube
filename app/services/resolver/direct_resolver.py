from __future__ import annotations

import logging
import os
import subprocess
from urllib.parse import urlparse

from app.services.resolver.base import PlaylistPreview, ResolvedTrack, ResolverError, SourceResolver
from app.services.resolver.utils import source_site_from_url

logger = logging.getLogger(__name__)


class DirectUrlError(ResolverError):
    pass


KNOWN_NON_DIRECT_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "soundcloud.com",
    "vimeo.com",
    "twitch.tv",
)

LIVE_MARKERS = ("live", "stream", "radio", ".m3u8", "icy", "icecast", "shoutcast")
DIRECT_EXTENSIONS = (
    ".mp3",
    ".m4a",
    ".aac",
    ".ogg",
    ".opus",
    ".flac",
    ".wav",
    ".m3u8",
    ".m3u",
    ".pls",
)


class DirectUrlResolver(SourceResolver):
    @staticmethod
    def _has_direct_extension(url: str) -> bool:
        lowered = url.lower()
        return any(ext in lowered for ext in DIRECT_EXTENSIONS)

    @staticmethod
    def _has_stream_hints(url: str) -> bool:
        lowered = url.lower()
        markers = ("live", "stream", "radio", "icecast", "shoutcast", "listen", "mount", "channel")
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _looks_like_stream_host(host: str) -> bool:
        if not host:
            return False
        prefixes = ("radio.", "stream.", "live.", "icecast.", "shoutcast.")
        return host.startswith(prefixes)

    def can_handle_url(self, url: str) -> bool:
        parsed = urlparse(url)
        scheme = parsed.scheme or ""
        host = (parsed.hostname or "").lower()
        if scheme not in {"http", "https"}:
            logger.debug(
                "direct_resolver: can_handle_url -> False (scheme) url=%s scheme=%s",
                url[:200],
                scheme,
                extra={"mytube_resolver": "direct", "action": "can_handle_scheme"},
            )
            return False
        for blocked in KNOWN_NON_DIRECT_DOMAINS:
            if host == blocked or host.endswith(f".{blocked}"):
                logger.debug(
                    "direct_resolver: can_handle_url -> False (blocked domain) url=%s host=%s blocked=%s",
                    url[:200],
                    host,
                    blocked,
                    extra={"mytube_resolver": "direct", "action": "can_handle_blocked", "host": host},
                )
                return False
        normalized = self.normalize_url(url)
        has_ext = self._has_direct_extension(normalized)
        has_hints = self._has_stream_hints(normalized)
        looks_stream = self._looks_like_stream_host(host)
        result = has_ext or has_hints or looks_stream
        logger.info(
            "direct_resolver: can_handle_url url=%s host=%s has_ext=%s has_hints=%s looks_stream=%s -> %s",
            url[:200],
            host,
            has_ext,
            has_hints,
            looks_stream,
            result,
            extra={
                "mytube_resolver": "direct",
                "action": "can_handle_url",
                "host": host,
                "result": result,
            },
        )
        return result

    def normalize_url(self, url: str) -> str:
        normalized = url.strip()
        logger.debug(
            "direct_resolver: normalize_url in_len=%s out_len=%s",
            len(url),
            len(normalized),
            extra={"mytube_resolver": "direct", "action": "normalize_url"},
        )
        return normalized

    def is_playlist_url(self, url: str) -> bool:
        _ = url
        return False

    def _is_likely_live(self, url: str) -> bool:
        lowered = url.lower()
        return any(marker in lowered for marker in LIVE_MARKERS)

    def _title_from_url(self, url: str) -> str | None:
        parsed = urlparse(url)
        basename = os.path.basename(parsed.path or "").strip()
        if not basename:
            return None
        return basename[:160]

    def resolve_video(self, url: str) -> ResolvedTrack:
        normalized = self.normalize_url(url)
        logger.info(
            "direct_resolver: resolve_video url=%s normalized=%s",
            url[:200],
            normalized[:200],
            extra={"mytube_resolver": "direct", "action": "resolve_video", "url": url[:200]},
        )
        is_live = self._is_likely_live(normalized)
        title = self._title_from_url(normalized)
        track = ResolvedTrack(
            source_url=url,
            normalized_url=normalized,
            title=title,
            channel=source_site_from_url(normalized),
            duration_seconds=None,
            thumbnail_url=None,
            stream_url=normalized,
            source_site=source_site_from_url(normalized),
            is_live=is_live,
            can_seek=not is_live,
            uploaded_at=None,
        )
        logger.info(
            "direct_resolver: resolve_video success title=%s is_live=%s",
            (title or "")[:60],
            is_live,
            extra={"mytube_resolver": "direct", "action": "resolve_video_ok"},
        )
        return track

    def spawn_audio_stream(self, url: str) -> subprocess.Popen[bytes]:
        logger.warning(
            "direct_resolver: spawn_audio_stream called (unsupported) url=%s",
            url[:200],
            extra={"mytube_resolver": "direct", "action": "spawn_audio_unsupported"},
        )
        _ = url
        raise DirectUrlError("DirectUrlResolver does not spawn yt-dlp streams")

    def preview_playlist(self, url: str) -> PlaylistPreview:
        logger.warning(
            "direct_resolver: preview_playlist called (unsupported) url=%s",
            url[:200],
            extra={"mytube_resolver": "direct", "action": "preview_playlist_unsupported"},
        )
        raise DirectUrlError("Direct URLs do not support playlist preview")

