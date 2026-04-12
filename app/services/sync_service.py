from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.db.repository import NewPlaylistEntry, Repository
from app.services.spotify_free_service import is_spotify_playlist_url, spotify_playlist_id_from_url
from app.services.spotify_free_service import fetch_spotify_playlist_tracks
from app.services.spotify_import_service import SpotifyImportService, pending_source_url
from app.services.yt_dlp_service import YtDlpService

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_error_text(exc: Exception, limit: int = 2000) -> str:
    text = str(exc) or exc.__class__.__name__
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _upstream_id(provider: str | None, provider_item_id: str | None, normalized_url: str | None) -> str:
    prov = (provider or "unknown").strip() or "unknown"
    pid = (provider_item_id or "").strip()
    if pid:
        return f"{prov}:{pid}"
    norm = (normalized_url or "").strip()
    if norm:
        return f"{prov}:url:{norm}"
    return f"{prov}:unknown:{uuid.uuid4()}"


@dataclass
class SyncResult:
    fetched_items: int = 0
    new_items_added: int = 0
    already_present: int = 0
    removed_missing: int = 0


class SyncService:
    def __init__(
        self,
        *,
        repository: Repository,
        yt_dlp_service: YtDlpService,
        spotify_import_service: SpotifyImportService | None = None,
        interval_seconds: int = 600,
        max_concurrent: int = 2,
    ) -> None:
        self.repository = repository
        self.yt_dlp_service = yt_dlp_service
        self.spotify_import_service = spotify_import_service
        self.interval_seconds = max(30, int(interval_seconds))
        self.max_concurrent = max(1, int(max_concurrent))
        self._stop = asyncio.Event()
        self._playlist_locks: dict[str, asyncio.Lock] = {}
        self._failures: dict[str, int] = {}
        self._next_allowed_at: dict[str, float] = {}

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Playlist sync run crashed unexpectedly")
            elapsed = time.monotonic() - started
            delay = max(1.0, float(self.interval_seconds) - elapsed)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

    async def run_once(self) -> None:
        sync_run_id = str(uuid.uuid4())
        run_started_at = time.monotonic()
        logger.info("Playlist sync run start sync_run_id=%s interval_seconds=%s", sync_run_id, self.interval_seconds)

        playlists = await asyncio.to_thread(self.repository.list_playlists)
        eligible = [p for p in playlists if bool(getattr(p, "sync_enabled", False))]
        logger.info(
            "Playlist sync run eligible sync_run_id=%s playlists_total=%s playlists_eligible=%s",
            sync_run_id,
            len(playlists),
            len(eligible),
        )

        sem = asyncio.Semaphore(self.max_concurrent)
        skipped_backoff = 0
        tasks: list[asyncio.Task[None]] = []
        for p in eligible:
            pid = str(getattr(p, "id", ""))
            next_allowed = self._next_allowed_at.get(pid)
            if next_allowed is not None and time.monotonic() < next_allowed:
                skipped_backoff += 1
                continue
            tasks.append(asyncio.create_task(self._sync_one_playlist(p, sync_run_id=sync_run_id, sem=sem)))

        if tasks:
            await asyncio.gather(*tasks)

        dur_ms = int((time.monotonic() - run_started_at) * 1000)
        logger.info(
            "Playlist sync run end sync_run_id=%s duration_ms=%s skipped_backoff=%s",
            sync_run_id,
            dur_ms,
            skipped_backoff,
        )

    def _lock_for(self, playlist_id: str) -> asyncio.Lock:
        lock = self._playlist_locks.get(playlist_id)
        if lock is None:
            lock = asyncio.Lock()
            self._playlist_locks[playlist_id] = lock
        return lock

    async def _sync_one_playlist(self, playlist, *, sync_run_id: str, sem: asyncio.Semaphore) -> None:
        playlist_id = str(getattr(playlist, "id", ""))
        if not playlist_id:
            return
        async with sem:
            async with self._lock_for(playlist_id):
                await self._sync_one_playlist_locked(playlist, sync_run_id=sync_run_id)

    async def _sync_one_playlist_locked(self, playlist, *, sync_run_id: str) -> None:
        playlist_id = getattr(playlist, "id", None)
        source_url = str(getattr(playlist, "source_url", "") or "")
        remove_missing = bool(getattr(playlist, "sync_remove_missing", False))
        source = "spotify" if is_spotify_playlist_url(source_url) else "yt_dlp"

        attempt_started_at = _utcnow()
        await asyncio.to_thread(
            self.repository.set_playlist_sync_state,
            playlist_id,
            last_sync_started_at=attempt_started_at,
            last_sync_status="running",
            last_sync_error="",
        )

        t0 = time.monotonic()
        try:
            result = await asyncio.to_thread(self._sync_playlist_blocking, playlist, remove_missing=remove_missing)
            dur_ms = int((time.monotonic() - t0) * 1000)
            await asyncio.to_thread(
                self.repository.set_playlist_sync_state,
                playlist_id,
                last_sync_succeeded_at=_utcnow(),
                last_sync_status="ok",
                last_sync_error="",
            )
            logger.info(
                "Playlist sync ok sync_run_id=%s playlist_id=%s source=%s fetched_items=%s new_items_added=%s already_present=%s removed_missing=%s duration_ms=%s",
                sync_run_id,
                playlist_id,
                source,
                result.fetched_items,
                result.new_items_added,
                result.already_present,
                result.removed_missing,
                dur_ms,
            )
            self._failures.pop(str(playlist_id), None)
            self._next_allowed_at.pop(str(playlist_id), None)
        except Exception as exc:
            dur_ms = int((time.monotonic() - t0) * 1000)
            err = _safe_error_text(exc)
            await asyncio.to_thread(
                self.repository.set_playlist_sync_state,
                playlist_id,
                last_sync_status="error",
                last_sync_error=err,
            )
            failures = int(self._failures.get(str(playlist_id), 0)) + 1
            self._failures[str(playlist_id)] = failures
            backoff_seconds = min(3600, int(30 * (2 ** min(10, failures - 1))))
            self._next_allowed_at[str(playlist_id)] = time.monotonic() + backoff_seconds
            logger.warning(
                "Playlist sync failed sync_run_id=%s playlist_id=%s source=%s duration_ms=%s failures=%s backoff_seconds=%s error=%r",
                sync_run_id,
                playlist_id,
                source,
                dur_ms,
                failures,
                backoff_seconds,
                err,
            )

    def _sync_playlist_blocking(self, playlist, *, remove_missing: bool) -> SyncResult:
        pid = getattr(playlist, "id", None)
        source_url = str(getattr(playlist, "source_url", "") or "")
        existing_entries = self.repository.list_playlist_entries(pid)
        next_pos = (max((int(getattr(e, "position", 0) or 0) for e in existing_entries), default=0) + 1) if existing_entries else 1
        existing_ids: set[str] = set()
        for e in existing_entries:
            if getattr(e, "upstream_item_id", None):
                existing_ids.add(str(e.upstream_item_id))
            else:
                existing_ids.add(_upstream_id(e.provider, e.provider_item_id, e.normalized_url))

        fetched: list[dict[str, object]] = []
        if is_spotify_playlist_url(source_url):
            pl_id = spotify_playlist_id_from_url(source_url) or ""
            if not pl_id:
                raise ValueError("Could not read Spotify playlist id")
            _meta, tracks = fetch_spotify_playlist_tracks(pl_id)
            for t in tracks:
                tid = str(t.get("spotify_track_id") or "").strip()
                if not tid:
                    continue
                upstream_item_id = f"spotify:track:{tid}"
                fetched.append(
                    {
                        "upstream_item_id": upstream_item_id,
                        "provider": "pending",
                        "provider_item_id": tid,
                        "source_url": pending_source_url(pid, next_pos),
                        "normalized_url": pending_source_url(pid, next_pos),
                        "title": t.get("title"),
                        "channel": t.get("channel"),
                        "duration_seconds": t.get("duration_seconds"),
                        "thumbnail_url": t.get("thumbnail_url"),
                    }
                )
                next_pos += 1
        else:
            preview = self.yt_dlp_service.preview_playlist(source_url, force_refresh=True)
            for item in preview.entries:
                if not isinstance(item, dict):
                    continue
                provider = str(item.get("provider") or "").strip() or None
                provider_item_id = str(item.get("provider_item_id") or "").strip() or None
                normalized_url = str(item.get("normalized_url") or item.get("source_url") or "").strip() or None
                source_url_item = str(item.get("source_url") or "").strip()
                upstream_item_id = _upstream_id(provider, provider_item_id, normalized_url)
                fetched.append(
                    {
                        "upstream_item_id": upstream_item_id,
                        "provider": provider,
                        "provider_item_id": provider_item_id,
                        "source_url": source_url_item,
                        "normalized_url": normalized_url or source_url_item,
                        "title": item.get("title"),
                        "channel": item.get("channel"),
                        "duration_seconds": item.get("duration_seconds"),
                        "thumbnail_url": item.get("thumbnail_url"),
                    }
                )

        result = SyncResult(fetched_items=len(fetched))
        keep_ids: set[str] = set()
        to_add: list[NewPlaylistEntry] = []
        for row in fetched:
            upstream_item_id = str(row["upstream_item_id"])
            keep_ids.add(upstream_item_id)
            if upstream_item_id in existing_ids:
                result.already_present += 1
                continue
            to_add.append(
                NewPlaylistEntry(
                    source_url=str(row["source_url"]),
                    normalized_url=str(row["normalized_url"]),
                    provider=row.get("provider") if isinstance(row.get("provider"), str) else None,
                    provider_item_id=row.get("provider_item_id") if isinstance(row.get("provider_item_id"), str) else None,
                    upstream_item_id=upstream_item_id,
                    title=row.get("title") if isinstance(row.get("title"), str) else None,
                    channel=row.get("channel") if isinstance(row.get("channel"), str) else None,
                    duration_seconds=row.get("duration_seconds") if isinstance(row.get("duration_seconds"), int) else None,
                    thumbnail_url=row.get("thumbnail_url") if isinstance(row.get("thumbnail_url"), str) else None,
                )
            )

        if to_add:
            created = self.repository.add_playlist_entries(pid, to_add)
            result.new_items_added = len(created)
            if is_spotify_playlist_url(source_url) and self.spotify_import_service is not None and created:
                try:
                    self.spotify_import_service.auto_match_first_hits(pid, [int(e.id) for e in created])
                except Exception:
                    logger.warning(
                        "Spotify auto-match failed sync playlist_id=%s created=%s",
                        pid,
                        len(created),
                        exc_info=True,
                    )

        if remove_missing:
            removed = self.repository.prune_playlist_entries_missing_upstream_ids(
                pid, keep_upstream_item_ids=keep_ids
            )
            result.removed_missing = removed

        return result

