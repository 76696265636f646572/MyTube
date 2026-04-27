from __future__ import annotations

import logging
import os
import queue
import random
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from collections import deque
from enum import Enum
from typing import Callable, Generator

from app.db.models import QueueStatus
from app.db.repository import NewQueueItem, Repository
from app.lib.tools import format_byte_size
from app.services.ffmpeg_pipeline import FfmpegError, FfmpegPipeline
from app.services.yt_dlp_service import ResolvedTrack, YtDlpError, YtDlpService

logger = logging.getLogger(__name__)


def _stderr_indicates_stream_failure(stderr_text: str) -> bool:
    normalized = stderr_text.lower()
    failure_markers = (
        "input/output error",
        "read error",
        "error in the pull function",
        "session has been invalidated",
        "connection reset",
        "end of file",
    )
    return any(marker in normalized for marker in failure_markers)


class PlaybackMode(str, Enum):
    idle = "idle"
    playing = "playing"


class RepeatMode(str, Enum):
    off = "off"
    all = "all"
    one = "one"


@dataclass
class PlaybackState:
    mode: PlaybackMode = PlaybackMode.idle
    now_playing_id: int | None = None
    now_playing_title: str | None = None
    now_playing_channel: str | None = None
    now_playing_thumbnail_url: str | None = None
    now_playing_duration_seconds: int | None = None
    now_playing_is_live: bool = False
    started_at_epoch_seconds: float | None = None
    started_at_monotonic_seconds: float | None = None
    paused: bool = False
    paused_elapsed_seconds: float | None = None
    repeat_mode: RepeatMode = RepeatMode.off
    shuffle_enabled: bool = False


class SharedMp3Hub:
    def __init__(self, stream_queue_size: int) -> None:
        self._clients: dict[str, queue.Queue[bytes]] = {}
        self._lock = threading.Lock()
        self._stream_queue_size = stream_queue_size

    def subscribe(self) -> Generator[bytes, None, None]:
        client_id = str(time.time_ns())
        q: queue.Queue[bytes] = queue.Queue(maxsize=self._stream_queue_size)
        with self._lock:
            self._clients[client_id] = q
        try:
            while True:
                chunk = q.get()
                if chunk is None:  # type: ignore[comparison-overlap]
                    break
                yield chunk
        finally:
            with self._lock:
                self._clients.pop(client_id, None)

    def publish(self, data: bytes) -> None:
        with self._lock:
            clients = list(self._clients.values())
            subscriber_count = len(clients)
        for q in clients:
            try:
                q.put_nowait(data)
            except queue.Full:
                logger.warning(
                    "MP3 hub client queue full: dropped oldest chunk to keep stream live "
                    "(subscriber_count=%s queue_maxsize=%s chunk_bytes=%s)",
                    subscriber_count,
                    self._stream_queue_size,
                    len(data),
                )
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(data)
                except queue.Full:
                    logger.warning(
                        "MP3 hub client queue still full after drop; skipping chunk for one client "
                        "(queue_maxsize=%s chunk_bytes=%s)",
                        self._stream_queue_size,
                        len(data),
                    )
                    continue

    def clear(self) -> None:
        with self._lock:
            clients = list(self._clients.values())
        for q in clients:
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._clients)


class StreamEngine:
    def __init__(
        self,
        repository: Repository,
        yt_dlp_service: YtDlpService,
        ffmpeg_pipeline: FfmpegPipeline,
        stream_queue_size: int = 16,
        chunk_size: int = 4096,
        queue_poll_seconds: float = 1.0,
        playback_retry_count: int = 2,
        stats_log_seconds: float = 15.0,
        on_state_change: Callable[[], None] | None = None,
        pcm_listener_count_provider: Callable[[], int] | None = None,
    ) -> None:
        self.repository = repository
        self.yt_dlp_service = yt_dlp_service
        self.ffmpeg_pipeline = ffmpeg_pipeline
        self.chunk_size = chunk_size
        self.queue_poll_seconds = queue_poll_seconds
        self.playback_retry_count = max(0, playback_retry_count)
        self.stats_log_seconds = max(1.0, stats_log_seconds)
        self.state = PlaybackState()
        self.hub = SharedMp3Hub(stream_queue_size)
        self._stop_event = threading.Event()
        self._skip_event = threading.Event()
        self._control_lock = threading.Lock()
        self._control_reason: str | None = None
        self._pending_seek_seconds: float | None = None
        self._worker: threading.Thread | None = None
        self._stats_worker: threading.Thread | None = None
        self._process_lock = threading.Lock()
        self._active_process: subprocess.Popen[bytes] | None = None
        self._active_source_process: subprocess.Popen[bytes] | None = None
        self._stats_lock = threading.Lock()
        self._total_bytes_streamed = 0
        self._total_chunks_streamed = 0
        self._tracks_completed = 0
        self._tracks_failed = 0
        self._tracks_skipped = 0
        self._on_state_change = on_state_change
        self._pcm_listener_count_provider = pcm_listener_count_provider
        self._repeat_cycle_items: list[
            tuple[str, str | None, str | None, str, str, str | None, int | None, str | None]
        ] = []
        self._shuffle_restore_order: list[int] | None = None
        self._prefetch_next_count = 2
        self._prefetch_previous_count = 2
        self._resolved_cache_lock = threading.Lock()
        self._resolved_track_cache: dict[int, ResolvedTrack] = {}
        self._recent_resolved_by_url: dict[str, ResolvedTrack] = {}
        self._recent_resolved_order: deque[str] = deque()
        self._prefetched_audio_cache: dict[int, str] = {}
        self._prefetched_audio_dir = tempfile.mkdtemp(prefix="airwave-prefetch-")
        self._prefetch_thread: threading.Thread | None = None
        self._user_stopped = False

    def _notify_state_changed(self) -> None:
        if self._on_state_change is None:
            return
        try:
            self._on_state_change()
        except Exception:
            logger.exception("Failed to publish stream state change event")

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._run, daemon=True, name="stream-engine")
        self._worker.start()
        self._stats_worker = threading.Thread(target=self._log_stats_loop, daemon=True, name="stream-engine-stats")
        self._stats_worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._request_interrupt("stop")
        if self._worker:
            self._worker.join(timeout=3)
        if self._stats_worker:
            self._stats_worker.join(timeout=3)
        self._clear_prefetched_audio_cache()

    def skip_current(self) -> None:
        self._request_interrupt("skip")

    def stop_playback(self) -> None:
        """Halt playback without advancing to the next track.

        The currently-playing item is re-enqueued at the front so a
        subsequent ``resume_playback`` picks it up.  The engine
        transitions to an idle cycle that stays silent until explicitly
        resumed.
        """
        self._user_stopped = True
        self._request_interrupt("user_stop")

    def resume_playback(self) -> str:
        """Resume playback per the SendSpin 'play' command spec.

        * If paused: unpause.
        * If user-stopped (idle with queue): clear the stop flag and
          wake the idle cycle so the next queued item starts.
        * If idle with an empty queue: re-enqueue the last history item
          and wake the idle cycle (\"resume last media\").

        Returns a short label describing what happened.
        """
        if self.state.paused:
            self.toggle_pause()
            return "resumed"

        if self._user_stopped:
            self._user_stopped = False
            self._request_interrupt("resume_from_stop")
            return "resumed_from_stop"

        if self.state.mode == PlaybackMode.idle:
            history = self.repository.list_history(limit=1)
            if not history:
                return "noop"
            previous = history[0]
            queued = self.repository.enqueue_items(
                [
                    NewQueueItem(
                        source_url=previous.source_url,
                        provider=getattr(previous, "provider", None),
                        provider_item_id=getattr(previous, "provider_item_id", None),
                        normalized_url=previous.source_url,
                        source_type=getattr(previous, "provider", None) or "unknown",
                        title=previous.title,
                    )
                ]
            )
            if queued:
                self.repository.move_item_to_front(queued[0].id)
                self._seed_resolved_cache_from_recent(queued[0].id, previous.source_url)
            self._request_interrupt("resume_from_stop")
            self._notify_state_changed()
            return "resume_last"

        return "noop"

    def set_repeat_mode(self, mode: str) -> str:
        try:
            repeat_mode = RepeatMode(mode)
        except ValueError as exc:
            raise ValueError("Invalid repeat mode") from exc
        self.state.repeat_mode = repeat_mode
        self._notify_state_changed()
        return self.state.repeat_mode.value

    def set_shuffle_enabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        queued_ids = self.repository.list_queued_ids()

        if enabled and not self.state.shuffle_enabled:
            self._shuffle_restore_order = list(queued_ids)
            shuffled_ids = list(queued_ids)
            if len(shuffled_ids) > 1:
                random.shuffle(shuffled_ids)
                self.repository.reorder_queued_items(shuffled_ids)
        elif not enabled and self.state.shuffle_enabled:
            restore_ids = list(self._shuffle_restore_order or [])
            if restore_ids:
                self.repository.reorder_queued_items(restore_ids)
            self._shuffle_restore_order = None

        self.state.shuffle_enabled = enabled
        self._notify_state_changed()
        return self.state.shuffle_enabled

    def toggle_pause(self) -> bool:
        if self.state.mode != PlaybackMode.playing:
            return False
        if self.state.paused:
            elapsed = self.playback_progress()["elapsed_seconds"]
            target = float(elapsed or 0.0)
            self.state.paused = False
            self.state.paused_elapsed_seconds = None
            self._set_playback_offset_seconds(target)
            self._set_pending_seek_seconds(target)
            self._notify_state_changed()
            self._request_interrupt("resume")
            return False
        elapsed = self.playback_progress()["elapsed_seconds"]
        self.state.paused = True
        self.state.paused_elapsed_seconds = float(elapsed or 0.0)
        self._notify_state_changed()
        self._request_interrupt("pause")
        return True

    def seek_to_percent(self, percent: float) -> bool:
        duration_seconds = self.state.now_playing_duration_seconds
        if duration_seconds is None or duration_seconds <= 0:
            return False
        bounded_percent = max(0.0, min(100.0, float(percent)))
        target_seconds = (bounded_percent / 100.0) * duration_seconds
        return self.seek_to_seconds(target_seconds)

    def seek_to_seconds(self, seconds: float) -> bool:
        if self.state.mode != PlaybackMode.playing:
            return False
        duration_seconds = self.state.now_playing_duration_seconds
        target_seconds = max(0.0, float(seconds))
        if duration_seconds is not None and duration_seconds > 0:
            target_seconds = min(target_seconds, float(duration_seconds))
        self._set_pending_seek_seconds(target_seconds)
        self._set_playback_offset_seconds(target_seconds)
        if self.state.paused:
            self.state.paused_elapsed_seconds = target_seconds
            self._notify_state_changed()
            return True
        self._notify_state_changed()
        self._request_interrupt("seek")
        return True

    def play_previous_or_restart(self, restart_threshold_seconds: float = 5.0) -> str:
        elapsed = float(self.playback_progress()["elapsed_seconds"] or 0.0)
        if self.state.mode == PlaybackMode.playing and elapsed > restart_threshold_seconds:
            self.seek_to_seconds(0.0)
            return "restarted"
        history = self.repository.list_history(limit=1)
        if not history:
            if self.state.mode == PlaybackMode.playing:
                self.seek_to_seconds(0.0)
                return "restarted"
            return "noop"
        previous = history[0]
        queued = self.repository.enqueue_items(
            [
                NewQueueItem(
                    source_url=previous.source_url,
                    provider=getattr(previous, "provider", None),
                    provider_item_id=getattr(previous, "provider_item_id", None),
                    normalized_url=previous.source_url,
                    source_type=getattr(previous, "provider", None) or "unknown",
                    title=previous.title,
                )
            ]
        )
        if queued:
            self.repository.move_item_to_front(queued[0].id)
            self._seed_resolved_cache_from_recent(queued[0].id, previous.source_url)
        if self.state.mode == PlaybackMode.playing:
            self._request_interrupt("previous")
        self._notify_state_changed()
        return "previous"

    def _cache_resolved_track(self, item_id: int, resolved: ResolvedTrack) -> None:
        with self._resolved_cache_lock:
            self._resolved_track_cache[item_id] = resolved

    def _get_cached_resolved_track(self, item_id: int) -> ResolvedTrack | None:
        with self._resolved_cache_lock:
            return self._resolved_track_cache.get(item_id)

    def _drop_cached_resolved_track(self, item_id: int) -> None:
        with self._resolved_cache_lock:
            self._resolved_track_cache.pop(item_id, None)

    def _cache_prefetched_audio_path(self, item_id: int, path: str) -> None:
        with self._resolved_cache_lock:
            previous = self._prefetched_audio_cache.get(item_id)
            self._prefetched_audio_cache[item_id] = path
        if previous and previous != path:
            self._remove_prefetched_audio_file(previous)

    def _get_prefetched_audio_path(self, item_id: int) -> str | None:
        with self._resolved_cache_lock:
            path = self._prefetched_audio_cache.get(item_id)
        if path is None:
            return None
        if os.path.exists(path):
            return path
        with self._resolved_cache_lock:
            self._prefetched_audio_cache.pop(item_id, None)
        return None

    def _drop_prefetched_audio_path(self, item_id: int) -> None:
        with self._resolved_cache_lock:
            path = self._prefetched_audio_cache.pop(item_id, None)
        if path is not None:
            self._remove_prefetched_audio_file(path)

    @staticmethod
    def _remove_prefetched_audio_file(path: str) -> None:
        try:
            os.remove(path)
        except FileNotFoundError:
            return
        except Exception:
            logger.debug("Failed removing prefetched audio file %s", path, exc_info=True)

    def _clear_prefetched_audio_cache(self) -> None:
        with self._resolved_cache_lock:
            cached_paths = list(self._prefetched_audio_cache.values())
            self._prefetched_audio_cache.clear()
        for path in cached_paths:
            self._remove_prefetched_audio_file(path)
        try:
            os.rmdir(self._prefetched_audio_dir)
        except OSError:
            return

    def _prefetch_audio_for_item(self, queue_item_id: int, source_url: str) -> None:
        if self._get_prefetched_audio_path(queue_item_id) is not None:
            logger.debug("Prefetch skip item %s (already cached)", queue_item_id)
            return
        source_process = self.yt_dlp_service.spawn_audio_stream(source_url)
        temp_path = os.path.join(self._prefetched_audio_dir, f"{queue_item_id}.bin")
        logger.debug("Prefetching audio for item %s from %s to %s", queue_item_id, source_url, temp_path)
        try:
            with open(temp_path, "wb") as destination:
                while True:
                    chunk = source_process.stdout.read(64 * 1024) if source_process.stdout is not None else b""
                    if not chunk:
                        break
                    destination.write(chunk)
            stderr_text = (
                source_process.stderr.read().decode("utf-8", errors="replace").strip()
                if source_process.stderr is not None
                else ""
            )
            return_code = self._process_return_code(source_process)
            if return_code != 0:
                raise YtDlpError(stderr_text or f"yt-dlp exited with status {return_code}")
            if not os.path.exists(temp_path) or os.path.getsize(temp_path) <= 0:
                raise YtDlpError("yt-dlp prefetch returned empty audio stream")
            self._cache_prefetched_audio_path(queue_item_id, temp_path)
            logger.debug("Prefetched audio for item %s from %s to %s successfully", queue_item_id, source_url, temp_path)
        except Exception:
            self._remove_prefetched_audio_file(temp_path)
            logger.debug("Failed prefetching audio for item %s from %s to %s", queue_item_id, source_url, temp_path)
            raise
        finally:
            self._terminate_process(source_process)

    def _remember_recent_resolved_track(self, resolved: ResolvedTrack) -> None:
        key = resolved.normalized_url
        with self._resolved_cache_lock:
            if key in self._recent_resolved_order:
                self._recent_resolved_order.remove(key)
            self._recent_resolved_order.append(key)
            self._recent_resolved_by_url[key] = resolved
            while len(self._recent_resolved_order) > self._prefetch_previous_count:
                stale_key = self._recent_resolved_order.popleft()
                self._recent_resolved_by_url.pop(stale_key, None)

    def _seed_resolved_cache_from_recent(self, item_id: int, source_url: str) -> None:
        normalized_url = self.yt_dlp_service.normalize_url(source_url)
        with self._resolved_cache_lock:
            cached = self._recent_resolved_by_url.get(normalized_url)
            if cached is None:
                return
            self._resolved_track_cache[item_id] = cached

    @staticmethod
    def _item_uses_direct_ffmpeg(queue_item) -> bool:
        provider = getattr(queue_item, "provider", None)
        if provider in ("direct", "local"):
            return True
        source_type = getattr(queue_item, "source_type", None)
        return source_type in ("remote_audio", "local_file")

    def _resolve_track_for_item(self, queue_item, *, force_refresh: bool) -> ResolvedTrack:
        if not force_refresh:
            cached = self._get_cached_resolved_track(queue_item.id)
            if cached is not None:
                return cached
        if self._item_uses_direct_ffmpeg(queue_item):
            direct_stream_url = queue_item.normalized_url or queue_item.source_url
            resolved = ResolvedTrack(
                source_url=queue_item.source_url,
                normalized_url=queue_item.normalized_url,
                title=queue_item.title,
                channel=queue_item.channel,
                duration_seconds=queue_item.duration_seconds,
                thumbnail_url=queue_item.thumbnail_url,
                stream_url=direct_stream_url,
                provider=queue_item.provider or "direct",
                provider_item_id=queue_item.provider_item_id,
                is_live=False,
                item_source_type=getattr(queue_item, "source_type", None),
            )
            self._cache_resolved_track(queue_item.id, resolved)
            return resolved
        resolved = self.yt_dlp_service.resolve_video(queue_item.source_url, force_refresh=force_refresh)
        self._cache_resolved_track(queue_item.id, resolved)
        return resolved

    def _prefetch_upcoming_tracks(self) -> None:
        try:
            queue_items = self.repository.list_queue()
            queued_items = [item for item in queue_items if item.status == QueueStatus.queued][: self._prefetch_next_count]
            for queued_item in queued_items:
                if self._get_cached_resolved_track(queued_item.id) is not None:
                    continue
                if self._item_uses_direct_ffmpeg(queued_item):
                    try:
                        resolved = self._resolve_track_for_item(queued_item, force_refresh=False)
                    except Exception:
                        logger.debug("Failed prefetching direct item %s", queued_item.id, exc_info=True)
                        continue
                    self._remember_recent_resolved_track(resolved)
                    continue
                try:
                    resolved = self.yt_dlp_service.resolve_video(queued_item.source_url)
                except Exception:
                    logger.debug("Failed prefetching queued track %s", queued_item.id, exc_info=True)
                    continue
                self._cache_resolved_track(queued_item.id, resolved)
                try:
                    self._prefetch_audio_for_item(queued_item.id, queued_item.source_url)
                except Exception:
                    logger.debug("Failed prefetching queued audio %s", queued_item.id, exc_info=True)
        finally:
            with self._resolved_cache_lock:
                self._prefetch_thread = None

    def _trigger_prefetch_upcoming_tracks(self) -> None:
        with self._resolved_cache_lock:
            if self._prefetch_thread is not None and self._prefetch_thread.is_alive():
                return
            self._prefetch_thread = threading.Thread(
                target=self._prefetch_upcoming_tracks,
                daemon=True,
                name="stream-engine-prefetch",
            )
            self._prefetch_thread.start()

    def subscribe(self) -> Generator[bytes, None, None]:
        return self.hub.subscribe()

    def set_pcm_listener_count_provider(self, provider: Callable[[], int] | None) -> None:
        self._pcm_listener_count_provider = provider

    def playback_progress(self) -> dict[str, float | int | None]:
        elapsed_seconds: float | None = None
        if self.state.mode == PlaybackMode.playing and self.state.started_at_monotonic_seconds is not None:
            if self.state.paused and self.state.paused_elapsed_seconds is not None:
                elapsed_seconds = max(0.0, self.state.paused_elapsed_seconds)
            else:
                elapsed_seconds = max(0.0, time.monotonic() - self.state.started_at_monotonic_seconds)
        progress_percent: float | None = None
        if elapsed_seconds is not None and self.state.now_playing_duration_seconds:
            if self.state.now_playing_duration_seconds > 0:
                progress_percent = min(100.0, (elapsed_seconds / self.state.now_playing_duration_seconds) * 100.0)
        return {
            "duration_seconds": self.state.now_playing_duration_seconds,
            "started_at": self.state.started_at_epoch_seconds,
            "elapsed_seconds": elapsed_seconds,
            "progress_percent": progress_percent,
        }

    def runtime_stats(self) -> dict[str, float | int | str | None]:
        progress = self.playback_progress()
        mp3_stream_listeners = self.hub.subscriber_count()
        pcm_stream_listeners = 0
        if self._pcm_listener_count_provider is not None:
            try:
                pcm_stream_listeners = max(0, int(self._pcm_listener_count_provider()))
            except Exception:
                logger.debug("Failed reading PCM listener count", exc_info=True)
        with self._stats_lock:
            total_bytes_streamed = self._total_bytes_streamed
            total_chunks_streamed = self._total_chunks_streamed
            tracks_completed = self._tracks_completed
            tracks_failed = self._tracks_failed
            tracks_skipped = self._tracks_skipped
        with self._resolved_cache_lock:
            cached_track_count = len(self._resolved_track_cache)
            recent_cache_count = len(self._recent_resolved_by_url)
            prefetched_audio_count = len(self._prefetched_audio_cache)
        return {
            "mode": self.state.mode.value,
            "queued_count": self.repository.queued_count(),
            "mp3_stream_listeners": mp3_stream_listeners,
            "pcm_stream_listeners": pcm_stream_listeners,
            "total_listeners": mp3_stream_listeners + pcm_stream_listeners,
            "now_playing_id": self.state.now_playing_id,
            "now_playing_title": self.state.now_playing_title,
            "elapsed_seconds": progress["elapsed_seconds"],
            "duration_seconds": progress["duration_seconds"],
            "total_bytes_streamed": total_bytes_streamed,
            "total_chunks_streamed": total_chunks_streamed,
            "tracks_completed": tracks_completed,
            "tracks_failed": tracks_failed,
            "tracks_skipped": tracks_skipped,
            "cached_track_count": cached_track_count,
            "recent_cache_count": recent_cache_count,
            "prefetched_audio_count": prefetched_audio_count,
        }

    def get_current_stream_url(self) -> str | None:
        item_id = self.state.now_playing_id
        if item_id is None:
            return None

        cached = self._get_cached_resolved_track(item_id)
        if cached:
            return cached.stream_url

        item = self.repository.get_item(item_id)
        if not item:
            return None
        return item.resolved_stream_url or item.normalized_url or item.source_url

    def get_current_ffmpeg_input(self) -> str | None:
        """Prefer prefetched on-disk audio (same as live MP3) so PCM avoids a second remote demux."""
        item_id = self.state.now_playing_id
        if item_id is None:
            return None
        prefetched = self._get_prefetched_audio_path(item_id)
        if prefetched is not None:
            return prefetched
        return self.get_current_stream_url()

    def _record_streamed_chunk(self, chunk_size: int) -> None:
        with self._stats_lock:
            self._total_chunks_streamed += 1
            self._total_bytes_streamed += chunk_size

    def _record_track_outcome(self, *, completed: bool = False, failed: bool = False, skipped: bool = False) -> None:
        with self._stats_lock:
            if completed:
                self._tracks_completed += 1
            if failed:
                self._tracks_failed += 1
            if skipped:
                self._tracks_skipped += 1

    def _log_stats_loop(self) -> None:
        while not self._stop_event.wait(self.stats_log_seconds):
            stats = self.runtime_stats()
            track_label = (
                f'{stats["now_playing_id"]}:{stats["now_playing_title"]}'
                if stats["now_playing_id"] is not None
                else "none"
            )
            elapsed_seconds = stats["elapsed_seconds"]
            duration_seconds = stats["duration_seconds"]
            total_bytes = stats["total_bytes_streamed"]
            total_human = format_byte_size(total_bytes)
            if elapsed_seconds is None:
                progress_label = "n/a"
            elif duration_seconds:
                progress_label = f"{elapsed_seconds:.1f}s/{duration_seconds}s"
            else:
                progress_label = f"{elapsed_seconds:.1f}s"
            logger.info(
                "Engine stats mode=%s track=%s progress=%s mp3_stream_listeners=%s pcm_stream_listeners=%s total_listeners=%s queued=%s cache=%s recent_cache=%s prefetched_audio=%s total_bytes=%s (%s) total_chunks=%s completed=%s skipped=%s failed=%s",
                stats["mode"],
                track_label,
                progress_label,
                stats["mp3_stream_listeners"],
                stats["pcm_stream_listeners"],
                stats["total_listeners"],
                stats["queued_count"],
                stats["cached_track_count"],
                stats["recent_cache_count"],
                stats["prefetched_audio_count"],
                total_bytes,
                total_human,
                stats["total_chunks_streamed"],
                stats["tracks_completed"],
                stats["tracks_skipped"],
                stats["tracks_failed"],
            )

    def _set_active_processes(
        self,
        transcode_process: subprocess.Popen[bytes] | None,
        source_process: subprocess.Popen[bytes] | None = None,
    ) -> None:
        with self._process_lock:
            self._active_process = transcode_process
            self._active_source_process = source_process

    @staticmethod
    def _terminate_process(process: subprocess.Popen[bytes] | None) -> None:
        if process is None:
            return
        try:
            process.terminate()
            process.wait(timeout=1)
        except Exception:
            pass

    def _terminate_active_process(self) -> None:
        with self._process_lock:
            transcode_process = self._active_process
            source_process = self._active_source_process
        self._terminate_process(transcode_process)
        self._terminate_process(source_process)

    def _start_transition_silence(self) -> tuple[threading.Event | None, threading.Thread | None]:
        if self._stop_event.is_set() or self._skip_event.is_set():
            return None, None
        stop_event = threading.Event()

        def _publish_silence() -> None:
            while not stop_event.is_set() and not self._stop_event.is_set():
                if self._skip_event.is_set():
                    return
                try:
                    process = self.ffmpeg_pipeline.spawn_silence()
                except FfmpegError as exc:
                    logger.error("%s", exc)
                    return
                try:
                    while not stop_event.is_set() and not self._stop_event.is_set():
                        if self._skip_event.is_set():
                            return
                        chunk = self.ffmpeg_pipeline.read_chunk(process.stdout, self.chunk_size)
                        if not chunk:
                            break
                        if stop_event.is_set() or self._stop_event.is_set() or self._skip_event.is_set():
                            return
                        self.hub.publish(chunk)
                        self._record_streamed_chunk(len(chunk))
                finally:
                    self._terminate_process(process)

        worker = threading.Thread(
            target=_publish_silence,
            daemon=True,
            name="stream-engine-transition-silence",
        )
        worker.start()
        return stop_event, worker

    @staticmethod
    def _stop_transition_silence(
        stop_event: threading.Event | None,
        worker: threading.Thread | None,
    ) -> None:
        if stop_event is not None:
            stop_event.set()
        if worker is not None and worker.is_alive():
            worker.join(timeout=1)

    def _set_playback_offset_seconds(self, seconds: float) -> None:
        offset = max(0.0, float(seconds))
        self.state.started_at_epoch_seconds = time.time() - offset
        self.state.started_at_monotonic_seconds = time.monotonic() - offset

    def _set_pending_seek_seconds(self, seconds: float) -> None:
        with self._control_lock:
            self._pending_seek_seconds = max(0.0, float(seconds))

    def _consume_pending_seek_seconds(self, default: float = 0.0) -> float:
        with self._control_lock:
            pending = self._pending_seek_seconds
            self._pending_seek_seconds = None
        return max(0.0, float(default if pending is None else pending))

    def _request_interrupt(self, reason: str, *, terminate: bool = True) -> None:
        with self._control_lock:
            self._control_reason = reason
            self._skip_event.set()
        # This is a shared live stream, so control changes should drop any
        # already-buffered audio from the previous playback position/source.
        if terminate:
            self.hub.clear()
        if terminate:
            self._terminate_active_process()

    def _consume_interrupt_reason(self, default: str = "skip") -> str:
        with self._control_lock:
            reason = self._control_reason
            self._control_reason = None
            self._skip_event.clear()
        return reason or default

    @staticmethod
    def _process_return_code(process: subprocess.Popen[bytes]) -> int | None:
        poll = getattr(process, "poll", None)
        if callable(poll):
            code = poll()
            if code is not None:
                return code
        wait = getattr(process, "wait", None)
        if callable(wait):
            try:
                wait(timeout=0.2)
            except Exception:
                pass
        if callable(poll):
            return poll()
        return getattr(process, "returncode", None)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._user_stopped:
                    self._stream_idle_cycle()
                    continue

                queue_item = self.repository.dequeue_next()
                if queue_item is None:
                    if self.state.repeat_mode == RepeatMode.all and self._repeat_cycle_items:
                        replay_items = [
                            NewQueueItem(
                                source_url=item[0],
                                provider=item[1],
                                provider_item_id=item[2],
                                normalized_url=item[3],
                                source_type=item[4],
                                title=item[5],
                                duration_seconds=item[6],
                                thumbnail_url=item[7],
                            )
                            for item in self._repeat_cycle_items
                        ]
                        self._repeat_cycle_items = []
                        self.repository.enqueue_items(replay_items)
                        continue
                    if self.state.repeat_mode != RepeatMode.all:
                        self._repeat_cycle_items = []
                    self._stream_idle_cycle()
                    continue
                self._play_item(queue_item.id)
            except Exception:
                logger.exception("Stream engine loop failed; retrying")
                time.sleep(self.queue_poll_seconds)

    def _stream_idle_cycle(self) -> None:
        self.state.mode = PlaybackMode.idle
        self.state.now_playing_id = None
        self.state.now_playing_title = None
        self.state.now_playing_channel = None
        self.state.now_playing_thumbnail_url = None
        self.state.now_playing_duration_seconds = None
        self.state.now_playing_is_live = False
        self.state.started_at_epoch_seconds = None
        self.state.started_at_monotonic_seconds = None
        self.state.paused = False
        self.state.paused_elapsed_seconds = None
        self._notify_state_changed()
        try:
            process = self.ffmpeg_pipeline.spawn_silence()
        except FfmpegError as exc:
            logger.error("%s", exc)
            time.sleep(self.queue_poll_seconds)
            return
        self._set_active_processes(process)
        idle_start = time.monotonic()
        try:
            while not self._stop_event.is_set():
                if self._skip_event.is_set():
                    reason = self._consume_interrupt_reason()
                    if reason == "resume_from_stop":
                        return
                    if reason == "user_stop":
                        continue
                chunk = self.ffmpeg_pipeline.read_chunk(process.stdout, self.chunk_size)
                if not chunk:
                    break
                self.hub.publish(chunk)
                if time.monotonic() - idle_start >= self.queue_poll_seconds:
                    idle_start = time.monotonic()
                    if not self._user_stopped and self.repository.has_queued_items():
                        break
        finally:
            self._set_active_processes(None, None)
            self._terminate_process(process)

    def _play_item(self, item_id: int) -> None:
        queue_item = self.repository.get_item(item_id)
        if queue_item is None:
            return
        self.state.mode = PlaybackMode.playing
        self.state.now_playing_id = queue_item.id
        self.state.now_playing_title = queue_item.title
        self.state.now_playing_channel = queue_item.channel
        self.state.now_playing_thumbnail_url = queue_item.thumbnail_url
        self.state.now_playing_duration_seconds = queue_item.duration_seconds
        start_offset_seconds = self._consume_pending_seek_seconds()
        self._set_playback_offset_seconds(start_offset_seconds)
        self.state.paused = False
        self.state.paused_elapsed_seconds = None
        total_bytes_sent = 0
        total_chunks_sent = 0
        resolved_duration_seconds: int | None = None
        probed_duration_seconds: float | None = None
        while not self._stop_event.is_set():
            self._skip_event.clear()
            total_attempts = self.playback_retry_count + 1
            try:
                for attempt in range(1, total_attempts + 1):
                    if self._stop_event.is_set():
                        raise InterruptedError("stop")
                    transition_silence_stop: threading.Event | None = None
                    transition_silence_worker: threading.Thread | None = None
                    try:
                        transition_silence_stop, transition_silence_worker = self._start_transition_silence()
                        resolved = self._resolve_track_for_item(queue_item, force_refresh=attempt > 1)
                        resolved_duration_seconds = resolved.duration_seconds
                        probe_source = getattr(self.ffmpeg_pipeline, "probe_source", None)
                        try:
                            probe = probe_source(resolved.stream_url) if callable(probe_source) else None
                            if probe is None:
                                raise AttributeError("probe_source unavailable")
                            probed_duration_seconds = (
                                float(probe["duration_seconds"]) if probe["duration_seconds"] is not None else None
                            )
                        except FfmpegError:
                            probed_duration_seconds = None
                        except AttributeError:
                            probed_duration_seconds = None
                        self.repository.mark_item_resolved(queue_item.id, resolved.normalized_url)
                        self._remember_recent_resolved_track(resolved)
                        if resolved.thumbnail_url:
                            self.state.now_playing_thumbnail_url = resolved.thumbnail_url
                        if resolved.channel:
                            self.state.now_playing_channel = resolved.channel
                        self.state.now_playing_is_live = resolved.is_live
                        seek_offset = self._consume_pending_seek_seconds(default=start_offset_seconds)
                        self._set_playback_offset_seconds(seek_offset)
                        start_offset_seconds = seek_offset

                        prefetched_audio_path = self._get_prefetched_audio_path(queue_item.id)
                        spawn_for_source = getattr(self.ffmpeg_pipeline, "spawn_for_source", None)
                        if callable(spawn_for_source) and prefetched_audio_path:
                            source_process = None
                            process = spawn_for_source(prefetched_audio_path, start_at_seconds=seek_offset)
                            self._set_active_processes(process, None)
                        elif callable(spawn_for_source) and (
                            seek_offset > 0 or self._item_uses_direct_ffmpeg(queue_item)
                        ):
                            source_process = None
                            process = spawn_for_source(resolved.stream_url, start_at_seconds=seek_offset)
                            self._set_active_processes(process, None)
                        else:
                            source_process = self.yt_dlp_service.spawn_audio_stream(queue_item.source_url)
                            self._set_active_processes(None, source_process)
                            process = self.ffmpeg_pipeline.spawn_for_stdin(source_process.stdout)
                            if source_process.stdout is not None:
                                source_process.stdout.close()
                            self._set_active_processes(process, source_process)

                        # Trigger upcoming prefetch as soon as playback pipeline is ready.
                        # Relying only on the first emitted chunk can miss/delay prefetch
                        # for some direct/local playback paths.
                        self._trigger_prefetch_upcoming_tracks()

                        attempt_chunks_sent = 0
                        attempt_bytes_sent = 0
                        attempt_started_at = time.monotonic()
                        ffmpeg_stderr_snapshot = ""
                        source_stderr_snapshot = ""
                        while not self._stop_event.is_set():
                            if self._skip_event.is_set():
                                raise InterruptedError(self._consume_interrupt_reason())
                            read_started = time.monotonic()
                            chunk = self.ffmpeg_pipeline.read_chunk(process.stdout, self.chunk_size)
                            read_seconds = time.monotonic() - read_started
                            if chunk and read_seconds >= 0.3:
                                logger.warning(
                                    "Slow ffmpeg read while streaming track_id=%s attempt=%s chunk_index=%s "
                                    "read_seconds=%.3f requested_bytes=%s received_bytes=%s",
                                    queue_item.id,
                                    attempt,
                                    attempt_chunks_sent,
                                    read_seconds,
                                    self.chunk_size,
                                    len(chunk),
                                )
                            if not chunk:
                                ffmpeg_stderr_pipe = getattr(process, "stderr", None)
                                ffmpeg_stderr_snapshot = (
                                    ffmpeg_stderr_pipe.read().decode("utf-8", errors="replace").strip()
                                    if ffmpeg_stderr_pipe is not None
                                    else ""
                                )
                                source_stderr_pipe = getattr(source_process, "stderr", None)
                                source_stderr_snapshot = (
                                    source_stderr_pipe.read().decode("utf-8", errors="replace").strip()
                                    if source_stderr_pipe is not None
                                    else ""
                                )
                                break
                            if attempt_chunks_sent == 0:
                                self._stop_transition_silence(transition_silence_stop, transition_silence_worker)
                                transition_silence_stop = None
                                transition_silence_worker = None
                            self.hub.publish(chunk)
                            self._record_streamed_chunk(len(chunk))
                            attempt_chunks_sent += 1
                            if attempt_chunks_sent == 1:
                                self._trigger_prefetch_upcoming_tracks()
                                self._notify_state_changed()
                                logger.info(
                                    "Notifying state changed (attempt_chunks_sent=%s)",
                                    attempt_chunks_sent,
                                )
                            attempt_bytes_sent += len(chunk)
                            total_chunks_sent += 1
                            total_bytes_sent += len(chunk)

                        if self._stop_event.is_set():
                            raise InterruptedError("stop")
                        if self._skip_event.is_set():
                            raise InterruptedError(self._consume_interrupt_reason())

                        return_code = self._process_return_code(process)
                        source_return_code = self._process_return_code(source_process) if source_process is not None else 0
                        elapsed_seconds = max(0.0, time.monotonic() - attempt_started_at)
                        expected_duration_seconds = (
                            probed_duration_seconds
                            or float(resolved_duration_seconds or 0)
                            or float(queue_item.duration_seconds or 0)
                        )
                        ffmpeg_stderr_text = ffmpeg_stderr_snapshot
                        source_stderr_text = source_stderr_snapshot
                        stderr_text = f"{ffmpeg_stderr_text}\n{source_stderr_text}".strip()
                        premature_end = bool(
                            expected_duration_seconds
                            and expected_duration_seconds > 30
                            and elapsed_seconds < expected_duration_seconds * 0.9
                        )
                        stderr_failure = _stderr_indicates_stream_failure(stderr_text)
                        if return_code != 0:
                            raise FfmpegError(f"ffmpeg exited with status {return_code}")
                        if source_return_code != 0:
                            raise YtDlpError(f"yt-dlp exited with status {source_return_code}")
                        if premature_end and stderr_failure:
                            raise YtDlpError("upstream stream ended early after transport failure")
                        if queue_item.duration_seconds and queue_item.duration_seconds > 30:
                            if elapsed_seconds < queue_item.duration_seconds * 0.2:
                                logger.warning(
                                    "Track %s (%s) completed unusually fast (elapsed=%.2fs duration=%ss bytes=%s chunks=%s)",
                                    queue_item.id,
                                    queue_item.title or queue_item.source_url,
                                    elapsed_seconds,
                                    queue_item.duration_seconds,
                                    attempt_bytes_sent,
                                    attempt_chunks_sent,
                                )
                        self.repository.mark_playback_finished(queue_item.id, status=QueueStatus.completed)
                        if self.state.repeat_mode == RepeatMode.one:
                            repeated = self.repository.enqueue_items(
                                [
                                    NewQueueItem(
                                        source_url=queue_item.source_url,
                                        provider=queue_item.provider,
                                        provider_item_id=queue_item.provider_item_id,
                                        normalized_url=queue_item.normalized_url,
                                        source_type=queue_item.source_type,
                                        title=queue_item.title,
                                        channel=queue_item.channel,
                                        duration_seconds=queue_item.duration_seconds,
                                        thumbnail_url=queue_item.thumbnail_url,
                                        playlist_id=queue_item.playlist_id,
                                    )
                                ]
                            )
                            if repeated:
                                self.repository.move_item_to_front(repeated[0].id)
                        self._repeat_cycle_items.append(
                            (
                                queue_item.source_url,
                                queue_item.provider,
                                queue_item.provider_item_id,
                                queue_item.normalized_url,
                                queue_item.source_type,
                                queue_item.title,
                                queue_item.duration_seconds,
                                queue_item.thumbnail_url,
                            )
                        )
                        self._record_track_outcome(completed=True)
                        self._drop_prefetched_audio_path(queue_item.id)
                        self._trigger_prefetch_upcoming_tracks()
                        self._notify_state_changed()
                        logger.info(
                            "Track %s completed on attempt %s/%s (elapsed=%.2fs bytes=%s chunks=%s)",
                            queue_item.id,
                            attempt,
                            total_attempts,
                            elapsed_seconds,
                            attempt_bytes_sent,
                            attempt_chunks_sent,
                        )
                        return
                    except InterruptedError:
                        raise
                    except (YtDlpError, FfmpegError) as exc:
                        if attempt >= total_attempts:
                            logger.error(
                                "Track %s failed after %s/%s attempts (%s): %s",
                                queue_item.id,
                                attempt,
                                total_attempts,
                                type(exc).__name__,
                                exc,
                            )
                            raise
                        self._drop_prefetched_audio_path(queue_item.id)
                        self._drop_cached_resolved_track(queue_item.id)
                        logger.warning(
                            "Playback attempt %s/%s failed on track %s (%s): %s",
                            attempt,
                            total_attempts,
                            queue_item.id,
                            type(exc).__name__,
                            exc,
                        )
                        time.sleep(min(0.5, self.queue_poll_seconds))
                    finally:
                        self._stop_transition_silence(transition_silence_stop, transition_silence_worker)
                        self._terminate_active_process()
                        self._set_active_processes(None, None)
            except InterruptedError as exc:
                reason = str(exc)
                if reason in {"pause", "resume"} or (reason == "seek" and self.state.paused):
                    self._stream_paused_cycle()
                    if self._stop_event.is_set():
                        break
                    start_offset_seconds = self._consume_pending_seek_seconds(
                        default=float(self.playback_progress()["elapsed_seconds"] or 0.0)
                    )
                    self.state.paused = False
                    self.state.paused_elapsed_seconds = None
                    self._set_playback_offset_seconds(start_offset_seconds)
                    self._notify_state_changed()
                    continue
                if reason == "seek":
                    start_offset_seconds = self._consume_pending_seek_seconds(
                        default=float(self.playback_progress()["elapsed_seconds"] or 0.0)
                    )
                    continue
                if reason == "stop":
                    break
                if reason == "user_stop":
                    logger.info(
                        "Track %s user-stopped; re-enqueueing. streamed_bytes=%s streamed_chunks=%s",
                        queue_item.id,
                        total_bytes_sent,
                        total_chunks_sent,
                    )
                    self.repository.mark_playback_finished(queue_item.id, status=QueueStatus.skipped)
                    self._record_track_outcome(skipped=True)
                    self._drop_prefetched_audio_path(queue_item.id)
                    re_queued = self.repository.enqueue_items(
                        [
                            NewQueueItem(
                                source_url=queue_item.source_url,
                                provider=queue_item.provider,
                                provider_item_id=queue_item.provider_item_id,
                                normalized_url=queue_item.normalized_url,
                                source_type=queue_item.source_type,
                                title=queue_item.title,
                                channel=queue_item.channel,
                                duration_seconds=queue_item.duration_seconds,
                                thumbnail_url=queue_item.thumbnail_url,
                                playlist_id=queue_item.playlist_id,
                            )
                        ]
                    )
                    if re_queued:
                        self.repository.move_item_to_front(re_queued[0].id)
                        self._seed_resolved_cache_from_recent(re_queued[0].id, queue_item.source_url)
                    self._notify_state_changed()
                    return
                logger.info(
                    "Track %s interrupted (%s). streamed_bytes=%s streamed_chunks=%s",
                    queue_item.id,
                    reason or "skip",
                    total_bytes_sent,
                    total_chunks_sent,
                )
                self.repository.mark_playback_finished(queue_item.id, status=QueueStatus.skipped)
                self._record_track_outcome(skipped=True)
                self._drop_prefetched_audio_path(queue_item.id)
                self._notify_state_changed()
                return
            except YtDlpError as exc:
                logger.warning(
                    "Failed resolving track %s (%s): %s",
                    queue_item.id,
                    queue_item.source_url,
                    exc,
                )
                self.repository.mark_playback_finished(queue_item.id, status=QueueStatus.failed, error_message=str(exc))
                self._record_track_outcome(failed=True)
                self._drop_prefetched_audio_path(queue_item.id)
                self._notify_state_changed()
                self._notify_state_changed()
                return
            except FfmpegError as exc:
                logger.error(
                    "ffmpeg error on track %s (%s): %s [bytes=%s chunks=%s]",
                    queue_item.id,
                    queue_item.title or queue_item.source_url,
                    exc,
                    total_bytes_sent,
                    total_chunks_sent,
                )
                self.repository.mark_playback_finished(queue_item.id, status=QueueStatus.failed, error_message=str(exc))
                self._record_track_outcome(failed=True)
                self._drop_prefetched_audio_path(queue_item.id)
                self._notify_state_changed()
                self._notify_state_changed()
                return
            except Exception as exc:
                logger.exception(
                    "Playback failure on track %s (%s): %s",
                    queue_item.id,
                    queue_item.title or queue_item.source_url,
                    exc,
                )
                self.repository.mark_playback_finished(queue_item.id, status=QueueStatus.failed, error_message=str(exc))
                self._record_track_outcome(failed=True)
                self._drop_prefetched_audio_path(queue_item.id)
                self._notify_state_changed()
                return
        if self._stop_event.is_set():
            return
        try:
            logger.info(
                "Track %s interrupted (%s). streamed_bytes=%s streamed_chunks=%s",
                queue_item.id,
                "stopped",
                total_bytes_sent,
                total_chunks_sent,
            )
            self.repository.mark_playback_finished(queue_item.id, status=QueueStatus.skipped)
            self._record_track_outcome(skipped=True)
            self._drop_prefetched_audio_path(queue_item.id)
            self._notify_state_changed()
        except Exception:
            logger.exception("Failed updating playback state after stop")

    def _stream_paused_cycle(self) -> None:
        while not self._stop_event.is_set() and self.state.paused:
            try:
                process = self.ffmpeg_pipeline.spawn_silence()
            except FfmpegError as exc:
                logger.error("%s", exc)
                time.sleep(min(0.1, self.queue_poll_seconds))
                continue
            self._set_active_processes(process)
            try:
                while not self._stop_event.is_set() and self.state.paused:
                    if self._skip_event.is_set():
                        reason = self._consume_interrupt_reason()
                        if reason == "pause":
                            continue
                        if reason == "resume":
                            return
                        raise InterruptedError(reason)
                    chunk = self.ffmpeg_pipeline.read_chunk(process.stdout, self.chunk_size)
                    if not chunk:
                        break
                    self.hub.publish(chunk)
                    self._record_streamed_chunk(len(chunk))
            finally:
                self._set_active_processes(None, None)
                self._terminate_process(process)
