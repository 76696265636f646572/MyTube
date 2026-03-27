from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from app.db.repository import NewPlaylistEntry, Repository
from app.services.spotify_free_service import (
    fetch_spotify_playlist_tracks,
    is_spotify_playlist_url,
    spotify_playlist_id_from_url,
)
from app.services.yt_dlp_service import YtDlpService

logger = logging.getLogger(__name__)

DEFAULT_PROVIDERS = ["youtube", "soundcloud", "mixcloud"]


def pending_source_url(playlist_id: uuid.UUID, position_1based: int) -> str:
    return f"airwave-pending://spotify-import/{playlist_id}/{position_1based}"


def is_pending_spotify_import_url(url: str | None) -> bool:
    return isinstance(url, str) and url.startswith("airwave-pending://spotify-import/")


def _hit_to_new_entry(hit: dict[str, Any]) -> NewPlaylistEntry:
    return NewPlaylistEntry(
        source_url=str(hit["source_url"]),
        normalized_url=str(hit.get("normalized_url") or hit["source_url"]),
        provider=hit.get("provider"),
        provider_item_id=hit.get("provider_item_id"),
        title=hit.get("title"),
        channel=hit.get("channel"),
        duration_seconds=hit.get("duration_seconds"),
        thumbnail_url=hit.get("thumbnail_url"),
    )


def _same_hit_identity(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True if two search-hit dicts refer to the same item (URL or provider id)."""
    ua, ub = a.get("source_url"), b.get("source_url")
    if ua is not None and ub is not None and str(ua) == str(ub):
        return True
    ia, ib = a.get("provider_item_id"), b.get("provider_item_id")
    if ia is not None and ib is not None and str(ia) == str(ib):
        return True
    return False


@dataclass
class _Session:
    playlist_id: uuid.UUID
    providers: list[str]
    track_j: int = 0
    num_tracks: int = 0
    cell_results: dict[tuple[int, str], list[dict[str, Any]]] = field(default_factory=dict)
    done: bool = False
    last_error: str | None = None


def _hit_dict_from_playlist_entry(entry: Any) -> dict[str, Any]:
    """Rebuild a provider hit dict from a matched playlist row (for session cell_results)."""
    return {
        "source_url": entry.source_url,
        "normalized_url": entry.normalized_url,
        "provider": entry.provider,
        "provider_item_id": entry.provider_item_id,
        "title": entry.title,
        "channel": entry.channel,
        "duration_seconds": entry.duration_seconds,
        "thumbnail_url": entry.thumbnail_url,
    }


def _session_from_persisted_entries(
    playlist_id: uuid.UUID,
    entries: list[Any],
    providers: list[str],
) -> _Session:
    """Rebuild import progress from DB rows: matched rows → synthetic per-provider results;
    pending + spotify_import_searched → empty hit lists (no_match); first pending without
    searched is the next track (track_j), still searching."""
    num_tracks = len(entries)
    cell_results: dict[tuple[int, str], list[dict[str, Any]]] = {}
    track_j = 0
    for i, entry in enumerate(entries):
        pos = entry.position
        if not is_pending_spotify_import_url(entry.source_url):
            hit = _hit_dict_from_playlist_entry(entry)
            win = entry.provider
            for p in providers:
                cell_results[(pos, p)] = [hit] if p == win else []
            track_j = i + 1
            continue
        searched = bool(getattr(entry, "spotify_import_searched", False))
        if searched:
            for p in providers:
                cell_results[(pos, p)] = []
            track_j = i + 1
            continue
        break
    done = track_j >= num_tracks
    return _Session(
        playlist_id=playlist_id,
        providers=list(providers),
        track_j=track_j,
        num_tracks=num_tracks,
        cell_results=cell_results,
        done=done,
        last_error=None,
    )


class SpotifyImportService:
    """Spotify playlist import: pending rows; per track, all providers are searched in parallel."""

    def __init__(self, repository: Repository, yt_dlp: YtDlpService) -> None:
        self.repository = repository
        self.yt_dlp = yt_dlp
        self._lock = threading.Lock()
        self._sessions: dict[uuid.UUID, _Session] = {}

    def start_import(self, url: str) -> dict[str, Any]:
        if not is_spotify_playlist_url(str(url)):
            raise ValueError("Not a Spotify playlist URL")
        pl_id = spotify_playlist_id_from_url(str(url))
        if not pl_id:
            raise ValueError("Could not read Spotify playlist id")
        meta, tracks = fetch_spotify_playlist_tracks(pl_id)
        if not tracks:
            logger.warning("Spotify import aborted: no tracks spotify_playlist_id=%s", pl_id)
            raise ValueError("Spotify playlist has no tracks")
        playlist = self.repository.create_or_update_playlist(
            source_url=meta["source_url"],
            title=meta.get("title"),
            channel=meta.get("channel"),
            entry_count=0,
            thumbnail_url=meta.get("thumbnail_url"),
        )
        pid = playlist.id
        pending_entries: list[NewPlaylistEntry] = []
        for i, t in enumerate(tracks, start=1):
            pending_entries.append(
                NewPlaylistEntry(
                    source_url=pending_source_url(pid, i),
                    normalized_url=pending_source_url(pid, i),
                    provider="pending",
                    provider_item_id=t["spotify_track_id"],
                    title=t.get("title"),
                    channel=t.get("channel"),
                    duration_seconds=t.get("duration_seconds"),
                    thumbnail_url=t.get("thumbnail_url"),
                )
            )
        self.repository.replace_playlist_entries(pid, pending_entries)
        with self._lock:
            self._sessions[pid] = _Session(
                playlist_id=pid,
                providers=list(DEFAULT_PROVIDERS),
                num_tracks=len(tracks),
            )
        logger.info(
            "Spotify import started library_playlist_id=%s spotify_playlist_id=%s tracks=%s title=%r",
            pid,
            pl_id,
            len(tracks),
            meta.get("title"),
        )
        return {
            "playlist_id": str(pid),
            "title": meta.get("title"),
            "source_url": meta["source_url"],
            "track_count": len(tracks),
        }

    def restart_search(self, playlist_id: uuid.UUID) -> dict[str, Any]:
        playlist = self.repository.get_playlist(playlist_id)
        if playlist is None:
            raise ValueError("Playlist not found")
        sid = spotify_playlist_id_from_url(playlist.source_url)
        if not sid:
            raise ValueError("Not a Spotify import playlist")
        meta, tracks = fetch_spotify_playlist_tracks(sid)
        if not tracks:
            logger.warning(
                "Spotify import restart aborted: no tracks library_playlist_id=%s spotify_playlist_id=%s",
                playlist_id,
                sid,
            )
            raise ValueError("Spotify playlist has no tracks")
        self.repository.create_or_update_playlist(
            source_url=playlist.source_url,
            title=meta.get("title"),
            channel=meta.get("channel"),
            entry_count=0,
            thumbnail_url=meta.get("thumbnail_url"),
        )
        pending_entries: list[NewPlaylistEntry] = []
        for i, t in enumerate(tracks, start=1):
            pending_entries.append(
                NewPlaylistEntry(
                    source_url=pending_source_url(playlist_id, i),
                    normalized_url=pending_source_url(playlist_id, i),
                    provider="pending",
                    provider_item_id=t["spotify_track_id"],
                    title=t.get("title"),
                    channel=t.get("channel"),
                    duration_seconds=t.get("duration_seconds"),
                    thumbnail_url=t.get("thumbnail_url"),
                )
            )
        self.repository.replace_playlist_entries(playlist_id, pending_entries)
        with self._lock:
            self._sessions[playlist_id] = _Session(
                playlist_id=playlist_id,
                providers=list(DEFAULT_PROVIDERS),
                num_tracks=len(tracks),
            )
        logger.info(
            "Spotify import restart_search library_playlist_id=%s spotify_playlist_id=%s tracks=%s",
            playlist_id,
            sid,
            len(tracks),
        )
        return {"ok": True, "track_count": len(tracks)}

    def _get_or_create_session_unlocked(self, playlist_id: uuid.UUID) -> _Session:
        s = self._sessions.get(playlist_id)
        if s is not None:
            return s
        entries = self.repository.list_playlist_entries(playlist_id)
        if not entries:
            raise ValueError("No playlist entries")
        s = _session_from_persisted_entries(playlist_id, entries, list(DEFAULT_PROVIDERS))
        self._sessions[playlist_id] = s
        logger.debug(
            "Spotify import session recreated from DB library_playlist_id=%s num_tracks=%s track_j=%s done=%s",
            playlist_id,
            len(entries),
            s.track_j,
            s.done,
        )
        return s

    def _entry_at_position(self, playlist_id: uuid.UUID, position_1based: int):
        entries = self.repository.list_playlist_entries(playlist_id)
        for e in entries:
            if e.position == position_1based:
                return e
        return None

    def _search_parallel_for_query(
        self, playlist_id: uuid.UUID, pos: int, query: str, providers: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Run yt-dlp search for each provider concurrently; return provider -> hits."""

        def one(provider: str) -> tuple[str, list[dict[str, Any]]]:
            try:
                hits = self.yt_dlp.search_single_provider(query, provider=provider, limit=15)
                return provider, hits
            except Exception as exc:
                logger.warning(
                    "Spotify import search failed library_playlist_id=%s provider=%s position=%s: %s",
                    playlist_id,
                    provider,
                    pos,
                    exc,
                )
                return provider, []

        out: dict[str, list[dict[str, Any]]] = {}
        max_workers = min(len(providers), 8)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(one, p): p for p in providers}
            for fut in as_completed(futures):
                provider, hits = fut.result()
                out[provider] = hits
        return out

    def advance(self, playlist_id: uuid.UUID) -> dict[str, Any]:
        with self._lock:
            session = self._get_or_create_session_unlocked(playlist_id)
            if session.done:
                snap = self._snapshot_unlocked(playlist_id, session)
                snap["just_completed"] = False
                return snap

            start_j = session.track_j
            pos = start_j + 1
            entry = self._entry_at_position(playlist_id, pos)
            if entry is None:
                session.done = True
                session.last_error = "Missing playlist entry"
                logger.error(
                    "Spotify import missing entry library_playlist_id=%s position=%s",
                    playlist_id,
                    pos,
                )
                return self._snapshot_unlocked(playlist_id, session)

            title = (entry.title or "").strip()
            artist = (entry.channel or "").strip()
            query = f"{title} {artist}".strip() or title or artist or "unknown"
            providers = list(session.providers)
            entry_id = entry.id

        # yt-dlp calls can be slow; run providers in parallel without holding session lock.
        by_provider = self._search_parallel_for_query(playlist_id, pos, query, providers)

        with self._lock:
            session = self._get_or_create_session_unlocked(playlist_id)
            if session.done or session.track_j != start_j:
                if session.track_j != start_j and not session.done:
                    logger.debug(
                        "Spotify import advance skipped stale library_playlist_id=%s expected_j=%s actual_j=%s",
                        playlist_id,
                        start_j,
                        session.track_j,
                    )
                snap = self._snapshot_unlocked(playlist_id, session)
                snap["just_completed"] = False
                return snap

            entry = self.repository.get_playlist_entry(entry_id)
            if entry is None or entry.playlist_id != playlist_id:
                session.done = True
                session.last_error = "Missing playlist entry"
                logger.error(
                    "Spotify import entry vanished library_playlist_id=%s entry_id=%s",
                    playlist_id,
                    entry_id,
                )
                return self._snapshot_unlocked(playlist_id, session)

            for prov in providers:
                session.cell_results[(pos, prov)] = list(by_provider.get(prov, []))
            q_short = query[:200] if len(query) > 200 else query
            logger.debug(
                "Spotify import parallel search library_playlist_id=%s position=%s query=%r hits=%s",
                playlist_id,
                pos,
                q_short,
                {p: len(by_provider.get(p) or []) for p in providers},
            )

            if is_pending_spotify_import_url(entry.source_url):
                chosen: list[dict[str, Any]] | None = None
                chosen_prov: str | None = None
                for prov in providers:
                    cell = session.cell_results.get((pos, prov)) or []
                    if cell:
                        chosen = cell
                        chosen_prov = prov
                        break
                if chosen:
                    self.repository.update_playlist_entry(entry.id, _hit_to_new_entry(chosen[0]))
                    logger.debug(
                        "Spotify import auto-matched library_playlist_id=%s entry_id=%s position=%s provider=%s",
                        playlist_id,
                        entry.id,
                        pos,
                        chosen_prov,
                    )
                else:
                    self.repository.set_playlist_entry_spotify_import_searched(entry.id, True)

            session.track_j += 1
            just_completed = False
            if session.track_j >= session.num_tracks:
                session.done = True
                just_completed = True
                logger.info(
                    "Spotify import search finished library_playlist_id=%s tracks=%s",
                    playlist_id,
                    session.num_tracks,
                )

            snap = self._snapshot_unlocked(playlist_id, session)
            snap["just_completed"] = just_completed
            return snap

    def apply_selected_hit(self, playlist_id: uuid.UUID, entry_id: int, hit: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            entry = self.repository.get_playlist_entry(entry_id)
            if entry is None or entry.playlist_id != playlist_id:
                raise ValueError("Playlist entry not found")
            if not is_pending_spotify_import_url(entry.source_url):
                raise ValueError("Playlist entry is not pending")

            prov = hit.get("provider")
            if not isinstance(prov, str) or not prov.strip():
                raise ValueError("Invalid hit provider")

            session = self._get_or_create_session_unlocked(playlist_id)
            cell = list(session.cell_results.get((entry.position, prov)) or [])
            if not any(_same_hit_identity(hit, row) for row in cell):
                raise ValueError("Hit is not in cached search results for this track")

            updated = self.repository.update_playlist_entry(entry_id, _hit_to_new_entry(hit))
            if updated is None:
                raise ValueError("Update failed")
            logger.info(
                "Spotify import manual match library_playlist_id=%s entry_id=%s provider=%s url=%s",
                playlist_id,
                entry_id,
                hit.get("provider"),
                hit.get("source_url"),
            )
            session = self._get_or_create_session_unlocked(playlist_id)
            return self._snapshot_unlocked(playlist_id, session)

    def get_state(self, playlist_id: uuid.UUID) -> dict[str, Any]:
        with self._lock:
            session = self._get_or_create_session_unlocked(playlist_id)
            return self._snapshot_unlocked(playlist_id, session)

    def _item_status(self, entry, session: _Session) -> str:
        pos = entry.position
        if not is_pending_spotify_import_url(entry.source_url):
            return "matched"
        for p in session.providers:
            key = (pos, p)
            if key not in session.cell_results:
                return "searching"
        return "no_match"

    def _snapshot_unlocked(self, playlist_id: uuid.UUID, session: _Session) -> dict[str, Any]:
        entries = self.repository.list_playlist_entries(playlist_id)
        items: list[dict[str, Any]] = []
        for entry in entries:
            pos = entry.position
            results_by_provider: dict[str, list[dict[str, Any]]] = {}
            for p in session.providers:
                key = (pos, p)
                if key in session.cell_results:
                    results_by_provider[p] = list(session.cell_results[key])

            selected: dict[str, Any] | None = None
            if not is_pending_spotify_import_url(entry.source_url):
                selected = {
                    "source_url": entry.source_url,
                    "normalized_url": entry.normalized_url,
                    "provider": entry.provider,
                    "provider_item_id": entry.provider_item_id,
                    "title": entry.title,
                    "channel": entry.channel,
                    "duration_seconds": entry.duration_seconds,
                    "thumbnail_url": entry.thumbnail_url,
                }
            else:
                for p in session.providers:
                    hits = results_by_provider.get(p) or []
                    if hits:
                        selected = dict(hits[0])
                        break

            items.append(
                {
                    "id": entry.id,
                    "position": entry.position,
                    "spotify_track_id": entry.provider_item_id if is_pending_spotify_import_url(entry.source_url) else None,
                    "title": entry.title,
                    "channel": entry.channel,
                    "duration_seconds": entry.duration_seconds,
                    "thumbnail_url": entry.thumbnail_url,
                    "status": self._item_status(entry, session),
                    "results_by_provider": results_by_provider,
                    "selected": selected,
                }
            )

        return {
            "playlist_id": str(playlist_id),
            "search_done": session.done,
            "last_error": session.last_error,
            "progress": {
                "provider": None,
                "parallel_providers": True,
                "track_index": session.track_j,
                "tracks_completed": min(session.track_j, session.num_tracks),
                "tracks_total": session.num_tracks,
                "providers": list(session.providers),
            },
            "items": items,
        }
