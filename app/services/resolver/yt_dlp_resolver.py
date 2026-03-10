from __future__ import annotations

import json
import logging
import subprocess
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.services.resolver.base import PlaylistPreview, ResolvedTrack, ResolverError, SourceResolver
from app.services.resolver.utils import is_youtube_url, source_site_from_url

logger = logging.getLogger(__name__)


class YtDlpError(ResolverError):
    pass


SEARCH_PREFIXES = {
    "youtube": "ytsearch",
    "soundcloud": "scsearch",
    # "vimeo": "vimsearch",
    # "dailymotion": "dailymotion",
    # "bilibili": "bilibili",
    # "peertube": "peertube",
    # "audiomack": "audiomack",
    # "mixcloud": "mixcloud"
}

GENERIC_COLLECTION_KEYWORDS = (
    "playlist",
    "playlists",
    "album",
    "albums",
    "channel",
    "channels",
    "artist",
    "artists",
    "collection",
    "collections",
    "show",
    "shows",
    "podcast",
    "podcasts",
    "likes",
    "tracks",
    "videos",
    "uploads",
    "sets",
    "set",
    "tag",
    "tags",
    "music",
)


class YtDlpResolver(SourceResolver):
    def __init__(
        self,
        binary_path: str,
        *,
        blocked_domains: list[str] | None = None,
        blocked_extractors: list[str] | None = None,
    ) -> None:
        self.binary_path = binary_path
        self.blocked_domains = [d.lower().strip() for d in (blocked_domains or []) if d.strip()]
        self.blocked_extractors = [e.lower().strip() for e in (blocked_extractors or []) if e.strip()]

    def _host(self, url: str) -> str:
        host = (urlparse(url).hostname or "").lower()
        if host.startswith("www."):
            return host[4:]
        return host

    def _looks_like_collection_url(self, url: str) -> bool:
        parsed = urlparse(url)
        host = self._host(url)
        path = (parsed.path or "").lower()
        query = parse_qs(parsed.query or "")

        # Preserve existing behavior: YouTube watch pages always represent a single video.
        if is_youtube_url(url):
            if "watch" in path:
                return False
            if "/playlist" in path and "list" in query:
                return True
            if path.startswith("/@") and path.count("/") >= 1:
                return True
            if path.startswith(("/channel/", "/c/", "/user/")):
                return True
            segments = [segment for segment in path.split("/") if segment]
            if len(segments) == 1 and segments[0] not in {"watch", "playlist", "results", "feed", "shorts", "live"}:
                return True

        if host.endswith("vimeo.com") and (path.startswith("/showcase/") or path.startswith("/channels/")):
            return True
        if host.endswith("dailymotion.com") and path.startswith("/playlist/"):
            return True
        if host.endswith("bilibili.com") and (
            path.startswith("/bangumi/play/ss")
            or "/channel/collectiondetail" in path
            or "sid" in query
        ):
            return True
        # Single-track URLs are /username/track-slug (two segments); only these are collections:
        if host.endswith("soundcloud.com") and (
            "/sets/" in path
            or path.endswith("/tracks")
            or path.endswith("/likes")
        ):
            return True
        if host.endswith("bandcamp.com") and (path.startswith("/album/") or path.startswith("/music")):
            return True
        if host.endswith("audiomack.com") and ("/album/" in path or "/playlist/" in path):
            return True
        if host.endswith("mixcloud.com") and ("/playlists/" in path or path.startswith("/tag/")):
            return True
        if host.endswith("hearthis.at") and ("/set/" in path or path.count("/") == 2):
            return True
        if host.endswith("boomplay.com") and (path.startswith("/albums/") or path.startswith("/playlists/")):
            return True
        if host.endswith("anghami.com") and (path.startswith("/playlist/") or path.startswith("/album/")):
            return True
        if host.endswith("jamendo.com") and (path.startswith("/album/") or path.startswith("/artist/")):
            return True
        if host.endswith("archive.org") and path.startswith("/details/"):
            return True
        if host.endswith("freemusicarchive.org") and (path.startswith("/music/") or path.startswith("/curator/")):
            return True
        if host.endswith("house-mixes.com") and ("/profile/" in path):
            return True
        if host.endswith("1001tracklists.com") and (path.startswith("/tracklist/") or path.startswith("/dj/")):
            return True
        if host.endswith("nts.live") and path.startswith("/shows/"):
            return True
        if host.endswith("podcasts.apple.com") and "/podcast/" in path:
            return True
        if host.endswith("tunein.com") and path.startswith("/podcasts/"):
            return True
        if host.endswith("podbean.com"):
            return True
        if host.endswith("spreaker.com") and path.startswith("/show/"):
            return True
        if host.endswith("tiktok.com") and ("/@".lower() in path and ("/playlist/" in path or path.count("/") == 2)):
            return True
        if host.endswith("twitch.tv") and path.endswith("/videos"):
            return True
        if host.endswith("facebook.com") and path.endswith("/videos"):
            return True

        segments = [segment for segment in path.split("/") if segment]
        return any(segment in GENERIC_COLLECTION_KEYWORDS for segment in segments)

    def normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.netloc.endswith("youtu.be"):
            video_id = parsed.path.lstrip("/")
            return f"https://www.youtube.com/watch?v={video_id}"
        if "youtube.com" in parsed.netloc:
            query = parse_qs(parsed.query)
            video_id = query.get("v", [None])[0]
            if video_id:
                return f"https://www.youtube.com/watch?v={video_id}"
            playlist_id = query.get("list", [None])[0]
            if playlist_id:
                return f"https://www.youtube.com/playlist?list={playlist_id}"
        return url

    def _run_json(self, *args: str) -> dict[str, Any]:
        cmd = [self.binary_path, *args]
        logger.info(
            "yt_dlp_resolver: _run_json cmd=%s",
            cmd,
            extra={"mytube_resolver": "yt_dlp", "action": "run_json", "argv": args},
        )
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            logger.warning(
                "yt_dlp_resolver: _run_json failed returncode=%s stderr=%r stdout_len=%s",
                completed.returncode,
                (completed.stderr or "").strip()[:500],
                len(completed.stdout or ""),
                extra={"mytube_resolver": "yt_dlp", "action": "run_json_failed", "returncode": completed.returncode},
            )
            raise YtDlpError(completed.stderr.strip() or "yt-dlp failed")
        try:
            out = json.loads(completed.stdout)
            logger.debug(
                "yt_dlp_resolver: _run_json ok keys=%s",
                list(out.keys()) if isinstance(out, dict) else type(out).__name__,
                extra={"mytube_resolver": "yt_dlp", "action": "run_json_ok"},
            )
            return out
        except json.JSONDecodeError as exc:
            logger.warning(
                "yt_dlp_resolver: _run_json invalid JSON err=%s stdout_preview=%r",
                exc,
                (completed.stdout or "")[:200],
                extra={"mytube_resolver": "yt_dlp", "action": "run_json_decode_error"},
            )
            raise YtDlpError("Invalid JSON from yt-dlp") from exc

    def _ensure_domain_allowed(self, url: str) -> None:
        host = (urlparse(url).hostname or "").lower()
        logger.debug(
            "yt_dlp_resolver: _ensure_domain_allowed url=%s host=%s blocked_domains=%s",
            url[:200],
            host,
            self.blocked_domains,
            extra={"mytube_resolver": "yt_dlp", "action": "ensure_domain", "host": host},
        )
        if not host:
            return
        for blocked in self.blocked_domains:
            if host == blocked or host.endswith(f".{blocked}"):
                logger.warning(
                    "yt_dlp_resolver: domain blocked url=%s host=%s blocked=%s",
                    url[:200],
                    host,
                    blocked,
                    extra={"mytube_resolver": "yt_dlp", "action": "domain_blocked"},
                )
                raise YtDlpError("This site is not allowed")

    def _extract_entry_url(self, entry: dict[str, Any]) -> str | None:
        webpage_url = entry.get("webpage_url")
        if isinstance(webpage_url, str) and webpage_url.startswith("http"):
            return webpage_url
        original_url = entry.get("original_url")
        if isinstance(original_url, str) and original_url.startswith("http"):
            return original_url
        raw_url = entry.get("url")
        if isinstance(raw_url, str) and raw_url.startswith("http"):
            return raw_url
        if isinstance(raw_url, str) and raw_url.startswith("//"):
            return f"https:{raw_url}"
        video_id = entry.get("id")
        extractor = (entry.get("extractor") or entry.get("extractor_key") or "").lower()
        if video_id and ("youtube" in extractor):
            return f"https://www.youtube.com/watch?v={video_id}"
        logger.debug(
            "yt_dlp_resolver: _extract_entry_url no url entry_id=%s extractor=%s keys=%s",
            entry.get("id"),
            extractor,
            list(entry.keys()),
            extra={"mytube_resolver": "yt_dlp", "action": "extract_entry_no_url"},
        )
        return None

    @staticmethod
    def _title_from_info(info: dict[str, Any]) -> str | None:
        """Title from yt-dlp info dict; some extractors (e.g. SoundCloud) use fulltitle."""
        title = info.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
        full = info.get("fulltitle")
        if isinstance(full, str) and full.strip():
            return full.strip()
        return None

    @staticmethod
    def _thumbnail_from_info(info: dict[str, Any]) -> str | None:
        """Thumbnail URL from yt-dlp info; SoundCloud uses artwork_url or thumbnails list."""
        thumb = info.get("thumbnail")
        if isinstance(thumb, str) and thumb.strip().startswith("http"):
            return thumb.strip()
        artwork = info.get("artwork_url")
        if isinstance(artwork, str) and artwork.strip().startswith("http"):
            return artwork.strip()
        # SoundCloud search/flat-playlist often provides thumbnails list only
        thumb_list = info.get("thumbnails")
        if isinstance(thumb_list, list) and thumb_list:
            # Prefer a medium/large size if present
            by_id = {t.get("id"): t for t in thumb_list if isinstance(t, dict) and t.get("url")}
            for preferred in ("t300x300", "large", "t500x500", "small", "badge"):
                if preferred in by_id:
                    url = by_id[preferred].get("url")
                    if isinstance(url, str) and url.strip().startswith("http"):
                        return url.strip()
            # Fallback: first entry with a valid url
            for t in thumb_list:
                if isinstance(t, dict):
                    url = t.get("url")
                    if isinstance(url, str) and url.strip().startswith("http"):
                        return url.strip()
        return None

    @staticmethod
    def _duration_seconds(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return max(0, int(value))
        if isinstance(value, str):
            try:
                return max(0, int(float(value.strip())))
            except ValueError:
                return None
        return None

    def is_playlist_url(self, url: str) -> bool:
        normalized = self.normalize_url(url)
        logger.info(
            "yt_dlp_resolver: is_playlist_url url=%s normalized=%s",
            url[:200],
            normalized[:200],
            extra={"mytube_resolver": "yt_dlp", "action": "is_playlist_url", "url": url[:200]},
        )
        self._ensure_domain_allowed(normalized)
        parsed = urlparse(normalized)
        if is_youtube_url(normalized) and "watch" in (parsed.path or "").lower():
            logger.debug("yt_dlp_resolver: is_playlist_url -> False (youtube watch)")
            return False
        if self._looks_like_collection_url(normalized):
            logger.info("yt_dlp_resolver: is_playlist_url -> True (looks_like_collection)")
            return True
        data = self._run_json("--flat-playlist", "--skip-download", "-J", normalized)
        entries = data.get("entries")
        is_list = isinstance(entries, list)
        entry_count = len(entries) if is_list else 0
        _type = data.get("_type")
        result = is_list and entry_count > 1 and (_type == "playlist" or entry_count > 1)
        logger.info(
            "yt_dlp_resolver: is_playlist_url data _type=%s entries_count=%s -> %s",
            _type,
            entry_count,
            result,
            extra={"mytube_resolver": "yt_dlp", "action": "is_playlist_result", "entries_count": entry_count},
        )
        if not is_list or not entries:
            return False
        # Single entry => single track (e.g. SoundCloud track that yt-dlp returns as playlist)
        if entry_count == 1:
            return False
        if _type == "playlist":
            return True
        return len(entries) > 1

    def spawn_audio_stream(self, url: str) -> subprocess.Popen[bytes]:
        normalized = self.normalize_url(url)
        logger.info(
            "yt_dlp_resolver: spawn_audio_stream url=%s normalized=%s binary=%s",
            url[:200],
            normalized[:200],
            self.binary_path,
            extra={"mytube_resolver": "yt_dlp", "action": "spawn_audio_stream", "url": url[:200]},
        )
        self._ensure_domain_allowed(normalized)
        cmd = [
            self.binary_path,
            "--no-playlist",
            "-f",
            "bestaudio/best",
            "--no-progress",
            "--quiet",
            "-o",
            "-",
            normalized,
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logger.info(
                "yt_dlp_resolver: spawn_audio_stream started pid=%s",
                proc.pid,
                extra={"mytube_resolver": "yt_dlp", "action": "spawn_audio_started", "pid": proc.pid},
            )
            return proc
        except FileNotFoundError as exc:
            logger.error(
                "yt_dlp_resolver: spawn_audio_stream binary not found path=%s",
                self.binary_path,
                extra={"mytube_resolver": "yt_dlp", "action": "spawn_audio_binary_not_found"},
            )
            raise YtDlpError(
                f"yt-dlp binary not found at '{self.binary_path}'. "
                "Install yt-dlp or set MYTUBE_YT_DLP_PATH."
            ) from exc

    def resolve_video(self, url: str) -> ResolvedTrack:
        normalized = self.normalize_url(url)
        logger.info(
            "yt_dlp_resolver: resolve_video url=%s normalized=%s",
            url[:200],
            normalized[:200],
            extra={"mytube_resolver": "yt_dlp", "action": "resolve_video", "url": url[:200]},
        )
        self._ensure_domain_allowed(normalized)
        data = self._run_json("--no-playlist", "-f", "bestaudio/best", "--skip-download", "-J", normalized)
        # Some extractors (e.g. SoundCloud) return a single-entry playlist; use that entry when top-level lacks url/title
        raw_entries = [e for e in (data.get("entries") or []) if isinstance(e, dict)]
        if len(raw_entries) == 1:
            data = raw_entries[0]
        direct_url = data.get("url")
        title = self._title_from_info(data)
        logger.info(
            "yt_dlp_resolver: resolve_video got data has_url=%s title=%s extractor=%s",
            bool(direct_url),
            (title or "")[:80],
            data.get("extractor") or data.get("extractor_key"),
            extra={"mytube_resolver": "yt_dlp", "action": "resolve_video_data"},
        )
        if not direct_url:
            logger.warning(
                "yt_dlp_resolver: resolve_video no direct URL keys=%s",
                list(data.keys()),
                extra={"mytube_resolver": "yt_dlp", "action": "resolve_video_no_url"},
            )
            raise YtDlpError("Could not resolve direct stream URL")
        is_live = bool(data.get("is_live")) or str(data.get("live_status") or "").lower() in {"is_live", "post_live"}
        duration = self._duration_seconds(data.get("duration"))
        track = ResolvedTrack(
            source_url=url,
            normalized_url=normalized,
            title=title,
            channel=data.get("uploader") or data.get("channel"),
            duration_seconds=duration,
            thumbnail_url=self._thumbnail_from_info(data),
            stream_url=direct_url,
            source_site=source_site_from_url(normalized),
            is_live=is_live,
            can_seek=bool((duration or 0) > 0 and not is_live),
        )
        logger.info(
            "yt_dlp_resolver: resolve_video success title=%s stream_url_len=%s is_live=%s",
            (track.title or "")[:60],
            len(track.stream_url or ""),
            track.is_live,
            extra={"mytube_resolver": "yt_dlp", "action": "resolve_video_ok"},
        )
        return track

    def preview_playlist(self, url: str) -> PlaylistPreview:
        normalized = self.normalize_url(url)
        logger.info(
            "yt_dlp_resolver: preview_playlist url=%s normalized=%s",
            url[:200],
            normalized[:200],
            extra={"mytube_resolver": "yt_dlp", "action": "preview_playlist", "url": url[:200]},
        )
        self._ensure_domain_allowed(normalized)
        data = self._run_json("--flat-playlist", "--skip-download", "-J", normalized)
        raw_entries = data.get("entries", [])
        entries: list[dict[str, Any]] = []
        skipped = 0
        for entry in raw_entries:
            if not isinstance(entry, dict):
                skipped += 1
                continue
            source_url = self._extract_entry_url(entry)
            if not source_url:
                logger.debug(
                    "yt_dlp_resolver: preview_playlist skip entry (no url) id=%s extractor=%s",
                    entry.get("id"),
                    entry.get("extractor") or entry.get("extractor_key"),
                )
                skipped += 1
                continue
            duration = self._duration_seconds(entry.get("duration"))
            entries.append(
                {
                    "source_url": source_url,
                    "normalized_url": source_url,
                    "title": self._title_from_info(entry),
                    "channel": entry.get("uploader") or entry.get("channel"),
                    "duration_seconds": duration,
                    "thumbnail_url": self._thumbnail_from_info(entry),
                    "source_site": source_site_from_url(source_url),
                    "is_live": bool(entry.get("is_live")),
                }
            )
        logger.info(
            "yt_dlp_resolver: preview_playlist done entries=%s skipped=%s total_raw=%s",
            len(entries),
            skipped,
            len(raw_entries),
            extra={"mytube_resolver": "yt_dlp", "action": "preview_playlist_done", "entries_count": len(entries)},
        )
        return PlaylistPreview(
            source_url=normalized,
            title=data.get("title"),
            channel=data.get("uploader") or data.get("channel"),
            entries=entries,
            thumbnail_url=self._thumbnail_from_info(data),
        )

    def search(self, query: str, site: str = "youtube", limit: int = 10) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 25))
        site_key = (site or "youtube").strip().lower()
        prefix = SEARCH_PREFIXES.get(site_key, SEARCH_PREFIXES["youtube"])
        search_spec = f"{prefix}{bounded_limit}:{query}"
        logger.info(
            "yt_dlp_resolver: search query=%r site=%s limit=%s prefix=%s search_spec=%s",
            query[:100],
            site_key,
            bounded_limit,
            prefix,
            search_spec[:120],
            extra={
                "mytube_resolver": "yt_dlp",
                "action": "search",
                "site": site_key,
                "prefix": prefix,
                "has_custom_prefix": site_key in SEARCH_PREFIXES,
            },
        )
        payload = self._run_json("--flat-playlist", "--skip-download", "-J", search_spec)
        raw_entries = payload.get("entries", [])
        results: list[dict[str, Any]] = []
        skipped = 0
        for entry in raw_entries:
            if not isinstance(entry, dict):
                skipped += 1
                continue
            source_url = self._extract_entry_url(entry)
            if not source_url:
                logger.debug(
                    "yt_dlp_resolver: search skip entry (no url) id=%s extractor=%s title=%s",
                    entry.get("id"),
                    entry.get("extractor") or entry.get("extractor_key"),
                    (entry.get("title") or "")[:40],
                )
                skipped += 1
                continue
            duration = self._duration_seconds(entry.get("duration"))
            results.append(
                {
                    "id": entry.get("id") or source_url,
                    "source_url": source_url,
                    "normalized_url": source_url,
                    "title": self._title_from_info(entry),
                    "channel": entry.get("uploader") or entry.get("channel"),
                    "duration_seconds": duration,
                    "thumbnail_url": self._thumbnail_from_info(entry),
                    "source_site": source_site_from_url(source_url) or site_key.capitalize(),
                    "site": site_key,
                }
            )
        logger.info(
            "yt_dlp_resolver: search done site=%s results=%s skipped=%s raw_entries=%s",
            site_key,
            len(results),
            skipped,
            len(raw_entries),
            extra={
                "mytube_resolver": "yt_dlp",
                "action": "search_done",
                "site": site_key,
                "results_count": len(results),
            },
        )
        return results

