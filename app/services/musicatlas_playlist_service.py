from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from app.core.config import Settings
from app.db.models import PlayHistory, Playlist
from app.db.repository import NewPlaylistEntry, Repository
from app.services.musicatlas_client import MusicAtlasClient, extract_artist_song_title, parse_musicatlas_api_keys
from app.services.yt_dlp_client import YtDlpError

logger = logging.getLogger(__name__)

DAILY_PLAYLIST_TRACK_COUNT = 50
DAILY_PLAYLIST_CHANNEL = "MusicAtlas"
MAX_MUSICATLAS_SEED_BATCHES = 12
MUSICATLAS_CATALOG_PROGRESS_POLL_SECONDS = 10.0
MUSICATLAS_CATALOG_PROGRESS_MAX_POLLS = 30


@dataclass(frozen=True)
class MusicAtlasSeedOptions:
    history_limit: int = 15
    max_seeds: int = 8
    include_now_playing: bool = True
    randomize_history: bool = False


@dataclass(frozen=True)
class DailyMusicAtlasPlaylistDefinition:
    source_url: str
    title: str
    description: str
    seed_options: MusicAtlasSeedOptions


@dataclass
class DailyMusicAtlasPlaylistResult:
    source_url: str
    playlist_id: uuid.UUID | None
    seeds_used: int
    entries_replaced: int = 0
    skipped_reason: str | None = None


@dataclass(frozen=True)
class HistoryCatalogCandidate:
    artist: str
    title: str
    history_ids: tuple[int, ...]


DAILY_MUSICATLAS_PLAYLISTS: tuple[DailyMusicAtlasPlaylistDefinition, ...] = (
    DailyMusicAtlasPlaylistDefinition(
        source_url="custom://daily_1",
        title="Daily Mix 1",
        description="MusicAtlas daily mix generated from now playing plus recent history.",
        seed_options=MusicAtlasSeedOptions(history_limit=15, max_seeds=8, include_now_playing=True),
    ),
    DailyMusicAtlasPlaylistDefinition(
        source_url="custom://daily_2",
        title="Daily Mix 2",
        description="MusicAtlas daily mix generated from random listening history picks.",
        seed_options=MusicAtlasSeedOptions(history_limit=18, max_seeds=8, include_now_playing=False, randomize_history=True),
    ),
    DailyMusicAtlasPlaylistDefinition(
        source_url="custom://daily_3",
        title="Daily Mix 3",
        description="MusicAtlas daily mix generated from now playing plus random recent history picks.",
        seed_options=MusicAtlasSeedOptions(history_limit=12, max_seeds=4, include_now_playing=True, randomize_history=True),
    ),
    DailyMusicAtlasPlaylistDefinition(
        source_url="custom://daily_4",
        title="Daily Mix 4",
        description="MusicAtlas daily mix generated from a broader random history blend.",
        seed_options=MusicAtlasSeedOptions(history_limit=30, max_seeds=12, include_now_playing=True, randomize_history=True),
    ),
    DailyMusicAtlasPlaylistDefinition(
        source_url="custom://daily_5",
        title="Daily Mix 5",
        description="MusicAtlas daily mix using a fallback history-heavy seed set.",
        seed_options=MusicAtlasSeedOptions(history_limit=25, max_seeds=10, include_now_playing=False),
    ),
)


def musicatlas_daily_playlists_enabled(settings: Settings) -> bool:
    return bool(parse_musicatlas_api_keys(settings.musicatlas_api_key))


def _normalize_seed(artist: str | None, title: str | None) -> dict[str, str] | None:
    clean_artist = (artist or "").strip()
    clean_title = (title or "").strip()
    if not clean_artist or not clean_title:
        return None
    return {"artist": clean_artist, "title": clean_title}


def _history_row_seed(repo: Repository, row: PlayHistory) -> dict[str, str] | None:
    title = (row.title or "").strip()
    if not title:
        return None

    artist: str | None = None
    queue_item_id = row.queue_item_id
    if queue_item_id is not None:
        item = repo.get_item(int(queue_item_id))
        if item is not None:
            item_artist, item_title = extract_artist_song_title(item.channel or "", item.title or "")
            artist = item_artist or (item.channel or "").strip() or None
            if item_title:
                title = item_title

    if not artist:
        parsed_artist, parsed_title = extract_artist_song_title("", title)
        artist = parsed_artist or None
        if parsed_title:
            title = parsed_title

    if not artist:
        parts = title.split(" - ", 1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            artist = parts[0].strip()
            title = parts[1].strip()

    return _normalize_seed(artist or "Unknown Artist", title)


def dedupe_musicatlas_liked_tracks(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for item in items:
        normalized = _normalize_seed(item.get("artist"), item.get("title"))
        if normalized is None:
            continue
        key = (normalized["artist"].lower(), normalized["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return out


def _extract_musicatlas_job_id(body: dict[str, Any]) -> str:
    direct = str(body.get("job_id") or "").strip()
    if direct:
        return direct

    job = body.get("job")
    if isinstance(job, dict):
        nested = str(job.get("job_id") or job.get("id") or "").strip()
        if nested:
            return nested

    data = body.get("data")
    if isinstance(data, dict):
        nested = str(data.get("job_id") or data.get("id") or "").strip()
        if nested:
            return nested

    return ""


def build_musicatlas_liked_tracks(
    *,
    repository: Repository,
    stream_engine: Any,
    seed_options: MusicAtlasSeedOptions,
) -> list[dict[str, str]]:
    seed_pool = build_musicatlas_seed_pool(
        repository=repository,
        stream_engine=stream_engine,
        seed_options=seed_options,
    )
    return seed_pool[: seed_options.max_seeds]


def build_musicatlas_seed_pool(
    *,
    repository: Repository,
    stream_engine: Any,
    seed_options: MusicAtlasSeedOptions,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []

    if seed_options.include_now_playing:
        artist, title = extract_artist_song_title(
            getattr(stream_engine.state, "now_playing_channel", None) or "",
            getattr(stream_engine.state, "now_playing_title", None) or "",
        )
        normalized = _normalize_seed(artist, title)
        if normalized is not None:
            candidates.append(normalized)

    history_rows = repository.list_history(limit=seed_options.history_limit)
    if seed_options.randomize_history and len(history_rows) > 1:
        history_rows = random.sample(history_rows, k=len(history_rows))

    for row in history_rows:
        seed = _history_row_seed(repository, row)
        if seed is not None:
            candidates.append(seed)

    return dedupe_musicatlas_liked_tracks(candidates)


def build_musicatlas_seed_batches(
    *,
    seed_pool: list[dict[str, str]],
    max_seeds: int,
    max_batches: int = MAX_MUSICATLAS_SEED_BATCHES,
) -> list[list[dict[str, str]]]:
    if not seed_pool:
        return []

    batch_size = max(1, min(int(max_seeds), len(seed_pool)))
    batches: list[list[dict[str, str]]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()

    def add_batch(items: list[dict[str, str]]) -> None:
        if len(batches) >= max_batches:
            return
        normalized = dedupe_musicatlas_liked_tracks(items)[:batch_size]
        if not normalized:
            return
        key = tuple((item["artist"].lower(), item["title"].lower()) for item in normalized)
        if key in seen:
            return
        seen.add(key)
        batches.append(normalized)

    orderings = [
        list(seed_pool),
        list(reversed(seed_pool)),
        list(seed_pool[::2] + seed_pool[1::2]),
        list(seed_pool[1::2] + seed_pool[::2]),
    ]

    for ordering in orderings:
        if len(batches) >= max_batches:
            break
        add_batch(ordering[:batch_size])
        if len(ordering) > batch_size:
            add_batch(ordering[-batch_size:])
            for start in range(1, len(ordering) - batch_size + 1):
                add_batch(ordering[start : start + batch_size])
                if len(batches) >= max_batches:
                    break
        if len(ordering) > 2:
            smaller_batch_size = max(1, batch_size - 1)
            add_batch(ordering[:smaller_batch_size])
            add_batch(ordering[-smaller_batch_size:])

    return batches or [seed_pool[:batch_size]]


def musicatlas_matches_to_playlist_entries(
    matches: list[Any],
    *,
    limit: int = DAILY_PLAYLIST_TRACK_COUNT,
    existing_provider_item_ids: set[str] | None = None,
    entry_factory: Callable[[dict[str, Any], str, str], NewPlaylistEntry | None] | None = None,
) -> list[NewPlaylistEntry]:
    entries: list[NewPlaylistEntry] = []
    seen_youtube_ids: set[str] = set(existing_provider_item_ids or set())

    for match in matches:
        if not isinstance(match, dict):
            continue
        platform_ids = match.get("platform_ids")
        if not isinstance(platform_ids, dict):
            continue
        youtube_id = str(platform_ids.get("youtube") or "").strip()
        if not youtube_id or youtube_id in seen_youtube_ids:
            continue
        seen_youtube_ids.add(youtube_id)
        source_url = f"https://www.youtube.com/watch?v={youtube_id}"
        if entry_factory is None:
            logger.info(f"Creating new playlist entry for {match.get('title')} by {match.get('artist')} (No entry factory)")
            entry = NewPlaylistEntry(
                source_url=source_url,
                normalized_url=source_url,
                provider="youtube",
                provider_item_id=youtube_id,
                upstream_item_id=f"youtube:{youtube_id}",
                title=(match.get("title") or None),
                channel=(match.get("artist") or None),
                thumbnail_url=f"https://i.ytimg.com/vi/{youtube_id}/hqdefault.jpg",
            )
        else:
            logger.info(f"Creating new playlist entry for {match.get('title')} by {match.get('artist')} (With entry factory)")
            entry = entry_factory(match, source_url, youtube_id)
            if entry is None:
                continue
        entries.append(entry)
        if len(entries) >= limit:
            break

    return entries


class DailyMusicAtlasPlaylistService:
    def __init__(
        self,
        *,
        repository: Repository,
        stream_engine: Any,
        musicatlas_client: MusicAtlasClient,
        yt_dlp_service: Any | None = None,
        track_count: int = DAILY_PLAYLIST_TRACK_COUNT,
    ) -> None:
        self.repository = repository
        self.stream_engine = stream_engine
        self.musicatlas_client = musicatlas_client
        self.yt_dlp_service = yt_dlp_service
        self.track_count = max(1, int(track_count))

    def ensure_daily_playlists(self) -> list[Playlist]:
        playlists: list[Playlist] = []
        for definition in DAILY_MUSICATLAS_PLAYLISTS:
            playlists.append(
                self.repository.ensure_custom_playlist(
                    source_url=definition.source_url,
                    title=definition.title,
                    channel=DAILY_PLAYLIST_CHANNEL,
                    description=definition.description,
                    can_edit=False,
                    can_delete=False,
                    sync_enabled=False,
                    sync_remove_missing=False,
                )
            )
        return playlists

    def _history_catalog_candidates(self) -> list[HistoryCatalogCandidate]:
        history_limit = max((definition.seed_options.history_limit for definition in DAILY_MUSICATLAS_PLAYLISTS), default=0)
        candidates_by_key: dict[tuple[str, str], HistoryCatalogCandidate] = {}
        for row in self.repository.list_history(limit=history_limit):
            if bool(getattr(row, "musicatlas_submitted", False)):
                continue
            title = (row.title or "").strip()
            if not title:
                continue
            channel = ""
            if row.queue_item_id is not None:
                item = self.repository.get_item(int(row.queue_item_id))
                if item is not None:
                    channel = (item.channel or "").strip()
                    if item.title:
                        title = item.title
            artist, song = extract_artist_song_title(channel, title)
            normalized = _normalize_seed(artist, song)
            if normalized is not None:
                key = (normalized["artist"].lower(), normalized["title"].lower())
                existing = candidates_by_key.get(key)
                history_ids = tuple(sorted(set((existing.history_ids if existing is not None else tuple()) + (int(row.id),))))
                candidates_by_key[key] = HistoryCatalogCandidate(
                    artist=normalized["artist"],
                    title=normalized["title"],
                    history_ids=history_ids,
                )
        return list(candidates_by_key.values())

    def _wait_for_catalog_ingestion(self, *, artist: str, title: str, job_id: str) -> None:
        for poll_index in range(1, MUSICATLAS_CATALOG_PROGRESS_MAX_POLLS + 1):
            progress = self.musicatlas_client.add_track_progress(job_id=job_id)
            status = str(progress.get("status") or "").strip().lower() or "unknown"
            logger.info(
                "Daily MusicAtlas catalog preflight progress artist=%s title=%s job_id=%s poll=%s progress=%s",
                artist,
                title,
                job_id,
                poll_index,
                status,
            )
            if status == "done":
                return
            if status == "error":
                raise RuntimeError(
                    f"MusicAtlas catalog ingestion failed for {artist} - {title}: {progress.get('message') or 'unknown error'}"
                )
            time.sleep(MUSICATLAS_CATALOG_PROGRESS_POLL_SECONDS)
        raise RuntimeError(f"MusicAtlas catalog ingestion timed out for {artist} - {title}")

    def _ensure_history_exists_in_musicatlas(self) -> None:
        for candidate in self._history_catalog_candidates():
            artist = candidate.artist
            title = candidate.title
            try:
                logger.info(
                    "Daily MusicAtlas catalog preflight checking artist=%s title=%s",
                    artist,
                    title,
                )
                response = self.musicatlas_client.similar_tracks(artist=artist, track=title)
                matches = response.get("matches")
                if isinstance(matches, list) and len(matches) > 0:
                    logger.info(
                        "Daily MusicAtlas catalog preflight already indexed artist=%s title=%s",
                        artist,
                        title,
                    )
                    self.repository.mark_history_rows_musicatlas_submitted(list(candidate.history_ids))
                    continue

                logger.info(
                    "Daily MusicAtlas catalog preflight missing track artist=%s title=%s; submitting add_track",
                    artist,
                    title,
                )
                status_code, body = self.musicatlas_client.add_track(artist=artist, title=title)
                if status_code == 409:
                    logger.info(
                        "Daily MusicAtlas catalog preflight add_track conflict artist=%s title=%s message=%s",
                        artist,
                        title,
                        body.get("message"),
                    )
                    self.repository.mark_history_rows_musicatlas_submitted(list(candidate.history_ids))
                    continue

                job_id = _extract_musicatlas_job_id(body)
                if not job_id:
                    logger.warning(
                        "Daily MusicAtlas catalog preflight add_track missing job_id artist=%s title=%s status_code=%s message=%s; continuing",
                        artist,
                        title,
                        status_code,
                        body.get("message"),
                    )
                    self.repository.mark_history_rows_musicatlas_submitted(list(candidate.history_ids))
                    continue
                logger.info(
                    "Daily MusicAtlas catalog preflight waiting for ingestion artist=%s title=%s job_id=%s",
                    artist,
                    title,
                    job_id,
                )
                self._wait_for_catalog_ingestion(artist=artist, title=title, job_id=job_id)
                self.repository.mark_history_rows_musicatlas_submitted(list(candidate.history_ids))
            except Exception:
                logger.exception(
                    "Daily MusicAtlas catalog preflight failed artist=%s title=%s; continuing",
                    artist,
                    title,
                )
                continue

    def _request_playlist_entries(
        self,
        *,
        definition: DailyMusicAtlasPlaylistDefinition,
        seed_pool: list[dict[str, str]],
        playlist_id: uuid.UUID,
    ) -> tuple[list[NewPlaylistEntry], int]:
        seed_batches = build_musicatlas_seed_batches(
            seed_pool=seed_pool,
            max_seeds=definition.seed_options.max_seeds,
        )
        collected_entries: list[NewPlaylistEntry] = []
        seen_provider_item_ids: set[str] = set()
        request_count = 0

        for batch in seed_batches:
            if len(collected_entries) >= self.track_count:
                break

            request_count += 1
            raw = self.musicatlas_client.similar_tracks_multi(liked_tracks=batch)
            matches = raw.get("matches") if isinstance(raw, dict) else None
            match_list = matches if isinstance(matches, list) else []
            remaining = self.track_count - len(collected_entries)
            new_entries = musicatlas_matches_to_playlist_entries(
                match_list,
                limit=remaining,
                existing_provider_item_ids=seen_provider_item_ids,
                entry_factory=self._resolve_musicatlas_match_entry,
            )
            if not new_entries:
                continue
            collected_entries.extend(new_entries)
            seen_provider_item_ids.update(
                entry.provider_item_id for entry in new_entries if entry.provider_item_id is not None
            )

        if len(collected_entries) >= self.track_count:
            return collected_entries[: self.track_count], request_count
        logger.warning(
            "Daily MusicAtlas playlist exhausted seed variants source_url=%s playlist_id=%s requests=%s expected=%s actual=%s",
            definition.source_url,
            playlist_id,
            request_count,
            self.track_count,
            len(collected_entries),
        )
        return collected_entries, request_count

    def _resolve_musicatlas_match_entry(
        self,
        match: dict[str, Any],
        source_url: str,
        youtube_id: str,
    ) -> NewPlaylistEntry | None:
        title = (match.get("title") or None)
        channel = (match.get("artist") or None)
        thumbnail_url = f"https://i.ytimg.com/vi/{youtube_id}/hqdefault.jpg"
        duration_seconds: int | None = None

        if self.yt_dlp_service is not None:
            try:
                resolved = self.yt_dlp_service.resolve_video(source_url)
            except YtDlpError:
                logger.warning(
                    "Daily MusicAtlas playlist could not resolve video metadata source_url=%s; skipping track",
                    source_url,
                )
                return None
            except Exception:
                logger.exception(
                    "Daily MusicAtlas playlist metadata resolution failed source_url=%s; skipping track",
                    source_url,
                )
                return None
            else:
                title = resolved.title or title
                channel = resolved.channel or channel
                thumbnail_url = resolved.thumbnail_url or thumbnail_url
                duration_seconds = resolved.duration_seconds

        return NewPlaylistEntry(
            source_url=source_url,
            normalized_url=source_url,
            provider="youtube",
            provider_item_id=youtube_id,
            upstream_item_id=f"youtube:{youtube_id}",
            title=title,
            channel=channel,
            duration_seconds=duration_seconds,
            thumbnail_url=thumbnail_url,
        )

    def refresh_daily_playlists(self) -> list[DailyMusicAtlasPlaylistResult]:
        playlist_by_source = {playlist.source_url: playlist for playlist in self.ensure_daily_playlists()}
        results: list[DailyMusicAtlasPlaylistResult] = []
        self._ensure_history_exists_in_musicatlas()

        for definition in DAILY_MUSICATLAS_PLAYLISTS:
            playlist = playlist_by_source.get(definition.source_url)
            logger.info(f"Refreshing daily playlist {definition.title}")
            playlist_id = getattr(playlist, "id", None)
            seed_pool = build_musicatlas_seed_pool(
                repository=self.repository,
                stream_engine=self.stream_engine,
                seed_options=definition.seed_options,
            )
            result = DailyMusicAtlasPlaylistResult(
                source_url=definition.source_url,
                playlist_id=playlist_id,
                seeds_used=len(seed_pool),
            )
            if playlist is None:
                result.skipped_reason = "playlist_missing"
                results.append(result)
                continue
            if not seed_pool:
                result.skipped_reason = "no_seeds"
                results.append(result)
                continue

            try:
                entries, request_count = self._request_playlist_entries(
                    definition=definition,
                    seed_pool=seed_pool,
                    playlist_id=playlist.id,
                )
            except Exception:
                logger.exception(
                    "Daily MusicAtlas playlist generation failed source_url=%s playlist_id=%s",
                    definition.source_url,
                    playlist.id,
                )
                result.skipped_reason = "musicatlas_error"
                results.append(result)
                continue

            if len(entries) < self.track_count:
                logger.warning(
                    "Daily MusicAtlas playlist skipped due to insufficient matches source_url=%s playlist_id=%s requests=%s expected=%s actual=%s",
                    definition.source_url,
                    playlist.id,
                    request_count,
                    self.track_count,
                    len(entries),
                )
                result.skipped_reason = "insufficient_matches"
                results.append(result)
                continue

            replaced = self.repository.replace_playlist_entries(playlist.id, entries)
            result.entries_replaced = len(replaced)
            logger.info(f"Replaced {len(replaced)} entries for {definition.title}")
            if len(replaced) < self.track_count:
                result.skipped_reason = "replace_incomplete"
            results.append(result)

        return results


class DailyMusicAtlasPlaylistRunner:
    def __init__(
        self,
        *,
        service: DailyMusicAtlasPlaylistService,
        enabled: bool,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.service = service
        self.enabled = enabled
        self._now_factory = now_factory or (lambda: datetime.now().astimezone())
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    def seconds_until_next_run(self, now: datetime | None = None) -> float:
        current = (now or self._now_factory()).astimezone()
        next_midnight = current.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        # next_midnight = current + timedelta(minutes=1)

        return max(1.0, (next_midnight - current).total_seconds())

    async def run_forever(self) -> None:
        if not self.enabled:
            return

        while not self._stop.is_set():
            delay = self.seconds_until_next_run()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
                break
            except asyncio.TimeoutError:
                pass

            if self._stop.is_set():
                break

            try:
                await asyncio.to_thread(self.service.refresh_daily_playlists)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Daily MusicAtlas playlist runner crashed during refresh")
