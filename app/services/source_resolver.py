from __future__ import annotations

import logging
import os
import re
from urllib.parse import unquote, urldefrag, urlparse

from app.services.ffmpeg_pipeline import FfmpegError, FfmpegPipeline
from app.services.yt_dlp_service import ResolvedTrack

logger = logging.getLogger(__name__)

# Shown in browse UI; add-time validation still uses ffprobe.
_BROWSE_AUDIO_EXTENSIONS = frozenset(
    {
        ".aac",
        ".ac3",
        ".aiff",
        ".alac",
        ".ape",
        ".flac",
        ".m4a",
        ".m4b",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".mpc",
        ".ogg",
        ".opus",
        ".wav",
        ".webm",
        ".wma",
    }
)


def normalize_http_url(url: str) -> str:
    clean, _frag = urldefrag(url.strip())
    parsed = urlparse(clean)
    scheme = (parsed.scheme or "https").lower()
    netloc = (parsed.netloc or "").lower()
    if not netloc:
        return clean
    path = parsed.path or ""
    return f"{scheme}://{netloc}{path}" + (f"?{parsed.query}" if parsed.query else "")


def _title_from_http_url(url: str) -> str:
    parsed = urlparse(urldefrag(url)[0])
    base = unquote(os.path.basename(parsed.path) or "") or url
    return base or url


def _title_from_local_path(path: str) -> str:
    return os.path.basename(path) or path


def _natural_sort_key(value: str) -> tuple[object, ...]:
    parts = re.split(r"(\d+)", value)
    key: list[object] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part.lower())
    return tuple(key)


def _relative_path_sort_key(root: str, path: str) -> tuple[tuple[object, ...], ...]:
    relative = os.path.relpath(path, root)
    parts = relative.split(os.sep)
    return tuple(_natural_sort_key(part) for part in parts)


class MediaSourceResolver:
    """Classify and probe direct HTTP(S) media and allowlisted local files."""

    def __init__(self, ffmpeg_pipeline: FfmpegPipeline, local_media_roots: list[str]) -> None:
        self.ffmpeg_pipeline = ffmpeg_pipeline
        self._canonical_roots = self._canonicalize_roots(local_media_roots)

    @staticmethod
    def _canonicalize_roots(paths: list[str]) -> list[str]:
        resolved: list[str] = []
        for raw in paths:
            expanded = os.path.expanduser((raw or "").strip())
            if not expanded:
                continue
            try:
                real = os.path.realpath(expanded)
            except OSError as exc:
                logger.warning("Skipping invalid local media root %r: %s", expanded, exc)
                continue
            if not os.path.isdir(real):
                logger.warning("Local media root is not a directory: %s", real)
                continue
            resolved.append(real)
        return sorted(set(resolved))

    @property
    def canonical_roots(self) -> list[str]:
        return list(self._canonical_roots)

    def list_roots_payload(self) -> list[dict[str, str]]:
        return [{"path": root, "name": os.path.basename(root.rstrip(os.sep)) or root} for root in self._canonical_roots]

    def resolve_under_root(self, requested_path: str) -> str:
        if not self._canonical_roots:
            raise ValueError("Local media is disabled (no AIRWAVE_LOCAL_MEDIA_ROOTS configured)")
        expanded = os.path.expanduser((requested_path or "").strip())
        try:
            real = os.path.realpath(expanded)
        except OSError as exc:
            raise ValueError(f"Invalid path: {exc}") from exc
        if not os.path.exists(real):
            raise ValueError("Path does not exist")
        allowed = False
        for root in self._canonical_roots:
            if real == root or real.startswith(root + os.sep):
                allowed = True
                break
        if not allowed:
            raise ValueError("Path is outside allowed media directories")
        return real

    def _is_real_path_allowed(self, real_path: str) -> bool:
        for root in self._canonical_roots:
            if real_path == root or real_path.startswith(root + os.sep):
                return True
        return False

    def list_candidate_audio_files(self, directory_path: str, *, recursive: bool) -> list[str]:
        """Return sorted absolute paths under a directory (extension filter, allowlist, readable files)."""
        resolved = self.resolve_under_root(directory_path)
        if not os.path.isdir(resolved):
            raise ValueError("Not a directory")
        found: set[str] = set()

        def consider_file(full: str) -> None:
            try:
                real_full = os.path.realpath(full)
            except OSError:
                return
            if not self._is_real_path_allowed(real_full):
                return
            if not os.path.isfile(real_full) or not os.access(real_full, os.R_OK):
                return
            ext = os.path.splitext(real_full)[1].lower()
            if ext not in _BROWSE_AUDIO_EXTENSIONS:
                return
            found.add(real_full)

        if recursive:
            for dirpath, dirnames, filenames in os.walk(resolved, topdown=True, followlinks=False):
                dirnames[:] = sorted(
                    [d for d in dirnames if not d.startswith(".")],
                    key=_natural_sort_key,
                )
                filenames.sort(key=_natural_sort_key)
                for name in filenames:
                    if name.startswith("."):
                        continue
                    consider_file(os.path.join(dirpath, name))
        else:
            try:
                names = sorted(os.listdir(resolved), key=_natural_sort_key)
            except OSError as exc:
                raise ValueError(f"Cannot read directory: {exc}") from exc
            for name in names:
                if name.startswith("."):
                    continue
                consider_file(os.path.join(resolved, name))

        return sorted(found, key=lambda path: _relative_path_sort_key(resolved, path))

    def browse_directory(self, directory_path: str) -> dict[str, object]:
        resolved = self.resolve_under_root(directory_path)
        if not os.path.isdir(resolved):
            raise ValueError("Not a directory")
        entries: list[dict[str, object]] = []
        try:
            names = sorted(os.listdir(resolved), key=_natural_sort_key)
        except OSError as exc:
            raise ValueError(f"Cannot read directory: {exc}") from exc
        for name in names:
            if name.startswith("."):
                continue
            full = os.path.join(resolved, name)
            try:
                real_full = os.path.realpath(full)
            except OSError:
                continue
            if not self._is_real_path_allowed(real_full):
                continue
            try:
                is_dir = os.path.isdir(real_full)
            except OSError:
                continue
            if is_dir:
                entries.append({"name": name, "path": real_full, "kind": "directory"})
                continue
            if not os.path.isfile(real_full):
                continue
            if not os.access(real_full, os.R_OK):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in _BROWSE_AUDIO_EXTENSIONS:
                continue
            entries.append({"name": name, "path": real_full, "kind": "file"})
        return {"path": resolved, "entries": entries}

    def resolve_http_media(self, url: str) -> ResolvedTrack:
        text = (url or "").strip()
        if not text.lower().startswith(("http://", "https://")):
            raise ValueError("Direct media URL must start with http:// or https://")
        normalized = normalize_http_url(text)
        try:
            probe = self.ffmpeg_pipeline.probe_audio_streams(normalized)
        except FfmpegError as exc:
            raise ValueError(f"Could not read media URL: {exc}") from exc
        if not probe.get("has_audio"):
            raise ValueError("URL does not appear to contain a playable audio stream")
        duration_raw = probe.get("duration_seconds")
        duration_int: int | None = None
        if isinstance(duration_raw, (int, float)) and duration_raw > 0:
            duration_int = int(round(float(duration_raw)))
        title = probe.get("title") if isinstance(probe.get("title"), str) else None
        artist = probe.get("artist") if isinstance(probe.get("artist"), str) else None
        if not title:
            title = _title_from_http_url(normalized)
        return ResolvedTrack(
            source_url=text,
            normalized_url=normalized,
            title=title,
            channel=artist,
            duration_seconds=duration_int,
            thumbnail_url=None,
            stream_url=normalized,
            provider="direct",
            provider_item_id=None,
            is_live=False,
            item_source_type="remote_audio",
        )

    def resolve_local_file(self, path: str) -> ResolvedTrack:
        canonical = self.resolve_under_root(path)
        if not os.path.isfile(canonical):
            raise ValueError("Not a file")
        if not os.access(canonical, os.R_OK):
            raise ValueError("File is not readable")
        try:
            probe = self.ffmpeg_pipeline.probe_audio_streams(canonical)
        except FfmpegError as exc:
            raise ValueError(f"Could not read media file: {exc}") from exc
        if not probe.get("has_audio"):
            raise ValueError("File does not appear to contain a playable audio stream")
        duration_raw = probe.get("duration_seconds")
        duration_int: int | None = None
        if isinstance(duration_raw, (int, float)) and duration_raw > 0:
            duration_int = int(round(float(duration_raw)))
        title = probe.get("title") if isinstance(probe.get("title"), str) else None
        artist = probe.get("artist") if isinstance(probe.get("artist"), str) else None
        if not title:
            title = _title_from_local_path(canonical)
        return ResolvedTrack(
            source_url=canonical,
            normalized_url=canonical,
            title=title,
            channel=artist,
            duration_seconds=duration_int,
            thumbnail_url=None,
            stream_url=canonical,
            provider="local",
            provider_item_id=None,
            is_live=False,
            item_source_type="local_file",
        )
