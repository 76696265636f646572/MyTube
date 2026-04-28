from __future__ import annotations

import json
import logging
import threading
from collections.abc import Mapping, Sequence
from typing import Any
import re
import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)

DEFAULT_MUSICATLAS_BASE_URL = "https://musicatlas.ai/api"
_ROTATE_HTTP_STATUSES = frozenset({401, 403, 429})
_BODY_PREVIEW_LIMIT = 512


class MusicAtlasError(RuntimeError):
    """Base error for MusicAtlas client failures."""


class MusicAtlasDisabledError(MusicAtlasError):
    """Raised when the integration is disabled (no API keys configured)."""


class MusicAtlasTimeoutError(MusicAtlasError):
    def __init__(self, message: str, *, path: str, timeout_seconds: float) -> None:
        super().__init__(message)
        self.path = path
        self.timeout_seconds = timeout_seconds


class MusicAtlasTransportError(MusicAtlasError):
    def __init__(self, message: str, *, path: str) -> None:
        super().__init__(message)
        self.path = path


class MusicAtlasHttpError(MusicAtlasError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        path: str,
        response_body_preview: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.path = path
        self.response_body_preview = response_body_preview


class MusicAtlasKeysExhaustedError(MusicAtlasError):
    def __init__(
        self,
        message: str,
        *,
        path: str,
        last_status_code: int,
        keys_tried: int,
    ) -> None:
        super().__init__(message)
        self.path = path
        self.last_status_code = last_status_code
        self.keys_tried = keys_tried


def parse_musicatlas_api_keys(raw: str | None) -> list[str]:
    """Split comma-separated API keys, trim whitespace, drop empties."""
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _preview_body(text: str) -> str:
    text = text.strip()
    if len(text) <= _BODY_PREVIEW_LIMIT:
        return text
    return f"{text[:_BODY_PREVIEW_LIMIT]}…"

def extract_artist_song_title(channel: str, track: str) -> tuple[str, str]:
    if not channel or not track:
        return (channel or "").strip(), (track or "").strip()
    artist = track.split(" - ", 1)
    if artist and len(artist) > 1:
        artist = artist[0].strip()
    else:
        artist = channel
    artist = extract_artist(artist)
    track = extract_song_title(artist, track)
    return artist, track

def extract_artist(artist: str) -> str:
    if not artist:
        return artist
    artist = re.sub(r"Official", "", artist)
    artist = artist.strip()
    return artist

def extract_song_title(artist: str, track: str) -> str:
    """Extract the song title from the track string."""
    if not track:
        return track
    track = track.split(" - ", 1)
    if track and len(track) > 1:
        track = track[1].strip()
    else:
        track = track[0].strip()
    #subparts array
    after_song_title = ["|", "(", ")", "[", "]"]
    for part in after_song_title:
        if part in track:
            track = track.split(part, 1)[0].strip()
            break
    if not track:
        return track
    return track

class MusicAtlasClient:
    """
    HTTP client for the MusicAtlas public API with API-key rotation.

    Bearer auth is used for every request. Raw keys must never be logged.
    """

    def __init__(
        self,
        *,
        api_keys: Sequence[str],
        base_url: str = DEFAULT_MUSICATLAS_BASE_URL,
        timeout_seconds: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._keys = [k for k in api_keys if k]
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._own_client = http_client is None
        self._http = http_client or httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"Accept": "application/json"},
        )
        self._active_index = 0
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> MusicAtlasClient:
        keys = parse_musicatlas_api_keys(settings.musicatlas_api_key)
        base = (settings.musicatlas_base_url or "").strip() or DEFAULT_MUSICATLAS_BASE_URL
        return cls(
            api_keys=keys,
            base_url=base,
            timeout_seconds=settings.musicatlas_timeout_seconds,
        )

    @property
    def enabled(self) -> bool:
        return bool(self._keys)

    @property
    def active_key_index(self) -> int | None:
        if not self._keys:
            return None
        return self._active_index % len(self._keys)

    @property
    def active_key(self) -> str | None:
        """Current API key used for requests. Do not log this value."""
        if not self._keys:
            return None
        return self._keys[self._active_index % len(self._keys)]

    def close(self) -> None:
        if self._own_client:
            self._http.close()

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise MusicAtlasDisabledError(
                "MusicAtlas is disabled because AIRWAVE_MUSICATLAS_API_KEY is unset or empty."
            )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        ok_status_codes: frozenset[int] = frozenset({200}),
    ) -> tuple[int, dict[str, Any]]:
        """
        Perform an authorized JSON request with API-key rotation.

        Returns ``(status_code, parsed_json)`` when ``status_code`` is in
        ``ok_status_codes``. Otherwise raises the same errors as the public
        MusicAtlas helpers for unexpected HTTP statuses.
        """
        self._require_enabled()
        rel = path if path.startswith("/") else f"/{path}"
        upper = method.upper()
        request_json = dict(json_body) if json_body is not None else None
        request_params = dict(params) if params is not None else None

        with self._lock:
            keys = tuple(self._keys)
            n = len(keys)
            start_idx = self._active_index % n

        for offset in range(n):
            idx = (start_idx + offset) % n
            key = keys[idx]
            headers = {"Authorization": f"Bearer {key}"}
            try:
                response = self._http.request(
                    upper,
                    rel,
                    json=request_json,
                    params=request_params,
                    headers=headers,
                )
            except httpx.TimeoutException as exc:
                raise MusicAtlasTimeoutError(
                    f"MusicAtlas request timed out after {self._timeout_seconds}s",
                    path=rel,
                    timeout_seconds=self._timeout_seconds,
                ) from exc
            except httpx.RequestError as exc:
                raise MusicAtlasTransportError(
                    f"MusicAtlas request failed: {exc}",
                    path=rel,
                ) from exc

            if response.status_code in _ROTATE_HTTP_STATUSES:
                logger.warning(
                    "MusicAtlas HTTP %s for %s (key_index=%s); rotating to next key if available",
                    response.status_code,
                    rel,
                    idx,
                )
                with self._lock:
                    if offset == n - 1:
                        raise MusicAtlasKeysExhaustedError(
                            "All MusicAtlas API keys were rejected or rate-limited for this request.",
                            path=rel,
                            last_status_code=response.status_code,
                            keys_tried=n,
                        )
                    self._active_index = (idx + 1) % n
                continue

            if response.status_code not in ok_status_codes:
                preview: str | None = None
                try:
                    preview = _preview_body(response.text)
                except Exception:
                    preview = None
                raise MusicAtlasHttpError(
                    f"MusicAtlas request failed with HTTP {response.status_code}",
                    status_code=response.status_code,
                    path=rel,
                    response_body_preview=preview,
                )

            with self._lock:
                self._active_index = idx
            try:
                body = response.json()
            except json.JSONDecodeError as exc:
                raise MusicAtlasHttpError(
                    "MusicAtlas returned a non-JSON response body",
                    status_code=response.status_code,
                    path=rel,
                    response_body_preview=_preview_body(response.text),
                ) from exc
            if not isinstance(body, dict):
                raise MusicAtlasHttpError(
                    "MusicAtlas returned a JSON value that is not an object",
                    status_code=response.status_code,
                    path=rel,
                    response_body_preview=_preview_body(response.text),
                )
            return response.status_code, body

    def _post_json(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        _status, data = self._request_json("POST", path, json_body=payload, ok_status_codes=frozenset({200}))
        return data

    def similar_tracks(
        self,
        *,
        artist: str,
        track: str,
        embed: int | None = None,
    ) -> dict[str, Any]:
        """
        POST /similar_tracks — seed by artist + track name.

        Optional ``embed`` (0 or 1) skips validation/resolution when set (non-zero).
        """
        payload: dict[str, Any] = {"artist": artist, "track": track}
        if embed is not None:
            payload["embed"] = embed
        return self._post_json("/similar_tracks", payload)

    def similar_tracks_multi(
        self,
        *,
        liked_tracks: Sequence[Mapping[str, str]],
        disliked_tracks: Sequence[Mapping[str, str]] | None = None,
    ) -> dict[str, Any]:
        """
        POST /similar_tracks_multi — positive seeds ``liked_tracks`` (artist + title),
        optional ``disliked_tracks`` for negative steering.
        """
        payload: dict[str, Any] = {"liked_tracks": [dict(t) for t in liked_tracks]}
        if disliked_tracks is not None:
            payload["disliked_tracks"] = [dict(t) for t in disliked_tracks]
        return self._post_json("/similar_tracks_multi", payload)

    def add_track(self, *, artist: str, title: str) -> tuple[int, dict[str, Any]]:
        """
        POST /add_track — async catalog ingestion.

        Returns ``(http_status, body)``. ``200`` and ``409`` are returned without
        raising so callers can treat "already in catalog" as a soft outcome.
        """
        return self._request_json(
            "POST",
            "/add_track",
            json_body={"artist": artist, "title": title},
            ok_status_codes=frozenset({200, 409}),
        )

    def add_track_progress(self, *, job_id: str) -> dict[str, Any]:
        """GET /add_track_progress — single snapshot for ``job_id``."""
        _status, data = self._request_json(
            "GET",
            "/add_track_progress",
            params={"job_id": job_id},
            ok_status_codes=frozenset({200}),
        )
        return data
