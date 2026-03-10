from __future__ import annotations

import logging
import queue
import random
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Generator

from app.db.models import QueueStatus
from app.db.repository import NewQueueItem, Repository
from app.services.ffmpeg_pipeline import FfmpegError, FfmpegPipeline
from app.services.resolver.base import SourceResolver
from app.services.resolver.yt_dlp_resolver import YtDlpError

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
    now_playing_source_site: str | None = None
    now_playing_duration_seconds: int | None = None
    now_playing_is_live: bool = False
    now_playing_can_seek: bool = False
    started_at_epoch_seconds: float | None = None
    started_at_monotonic_seconds: float | None = None
    paused: bool = False
    paused_elapsed_seconds: float | None = None
    repeat_mode: RepeatMode = RepeatMode.off
    shuffle_enabled: bool = False


class SharedMp3Hub:
    def __init__(self) -> None:
        self._clients: dict[str, queue.Queue[bytes]] = {}
        self._lock = threading.Lock()

    def subscribe(self) -> Generator[bytes, None, None]:
        client_id = str(time.time_ns())
        q: queue.Queue[bytes] = queue.Queue(maxsize=256)
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
        for q in clients:
            try:
                q.put_nowait(data)
            except queue.Full:
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(data)
                except queue.Full:
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
        source_resolver: SourceResolver,
        ffmpeg_pipeline: FfmpegPipeline,
        chunk_size: int = 4096,
        queue_poll_seconds: float = 1.0,
        playback_retry_count: int = 2,
        stats_log_seconds: float = 15.0,
        on_state_change: Callable[[], None] | None = None,
    ) -> None:
        self.repository = repository
        self.source_resolver = source_resolver
        self.ffmpeg_pipeline = ffmpeg_pipeline
        self.chunk_size = chunk_size
        self.queue_poll_seconds = queue_poll_seconds
        self.playback_retry_count = max(0, playback_retry_count)
        self.stats_log_seconds = max(1.0, stats_log_seconds)
        self.state = PlaybackState()
        self.hub = SharedMp3Hub()
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
        self._repeat_cycle_items: list[tuple[str, str, str, str | None, int | None, str | None, str | None]] = []
        self._shuffle_restore_order: list[int] | None = None

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

    def skip_current(self) -> None:
        self._request_interrupt("skip")

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
        if not self.state.now_playing_can_seek:
            return False
        duration_seconds = self.state.now_playing_duration_seconds
        if duration_seconds is None or duration_seconds <= 0:
            return False
        bounded_percent = max(0.0, min(100.0, float(percent)))
        target_seconds = (bounded_percent / 100.0) * duration_seconds
        return self.seek_to_seconds(target_seconds)

    def seek_to_seconds(self, seconds: float) -> bool:
        if self.state.mode != PlaybackMode.playing:
            return False
        if not self.state.now_playing_can_seek:
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
                    normalized_url=previous.source_url,
                    source_type="history",
                    title=previous.title,
                    uploaded_at=getattr(previous, "uploaded_at", None),
                )
            ]
        )
        if queued:
            self.repository.move_item_to_front(queued[0].id)
        if self.state.mode == PlaybackMode.playing:
            self._request_interrupt("previous")
        self._notify_state_changed()
        return "previous"

    def subscribe(self) -> Generator[bytes, None, None]:
        return self.hub.subscribe()

    def playback_progress(self) -> dict[str, float | int | None]:
        elapsed_seconds: float | None = None
        if self.state.mode == PlaybackMode.playing and self.state.started_at_monotonic_seconds is not None:
            if self.state.paused and self.state.paused_elapsed_seconds is not None:
                elapsed_seconds = max(0.0, self.state.paused_elapsed_seconds)
            else:
                elapsed_seconds = max(0.0, time.monotonic() - self.state.started_at_monotonic_seconds)
        progress_percent: float | None = None
        if elapsed_seconds is not None and self.state.now_playing_duration_seconds:
            if self.state.now_playing_duration_seconds > 0 and self.state.now_playing_can_seek:
                progress_percent = min(100.0, (elapsed_seconds / self.state.now_playing_duration_seconds) * 100.0)
        return {
            "duration_seconds": self.state.now_playing_duration_seconds,
            "started_at": self.state.started_at_epoch_seconds,
            "elapsed_seconds": elapsed_seconds,
            "progress_percent": progress_percent,
        }

    def runtime_stats(self) -> dict[str, float | int | str | None]:
        progress = self.playback_progress()
        with self._stats_lock:
            total_bytes_streamed = self._total_bytes_streamed
            total_chunks_streamed = self._total_chunks_streamed
            tracks_completed = self._tracks_completed
            tracks_failed = self._tracks_failed
            tracks_skipped = self._tracks_skipped
        return {
            "mode": self.state.mode.value,
            "queued_count": self.repository.queued_count(),
            "subscriber_count": self.hub.subscriber_count(),
            "now_playing_id": self.state.now_playing_id,
            "now_playing_title": self.state.now_playing_title,
            "elapsed_seconds": progress["elapsed_seconds"],
            "duration_seconds": progress["duration_seconds"],
            "total_bytes_streamed": total_bytes_streamed,
            "total_chunks_streamed": total_chunks_streamed,
            "tracks_completed": tracks_completed,
            "tracks_failed": tracks_failed,
            "tracks_skipped": tracks_skipped,
        }

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
            if elapsed_seconds is None:
                progress_label = "n/a"
            elif duration_seconds:
                progress_label = f"{elapsed_seconds:.1f}s/{duration_seconds}s"
            else:
                progress_label = f"{elapsed_seconds:.1f}s"
            logger.info(
                "Engine stats mode=%s track=%s progress=%s listeners=%s queued=%s total_bytes=%s total_chunks=%s completed=%s skipped=%s failed=%s",
                stats["mode"],
                track_label,
                progress_label,
                stats["subscriber_count"],
                stats["queued_count"],
                stats["total_bytes_streamed"],
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
                queue_item = self.repository.dequeue_next()
                if queue_item is None:
                    if self.state.repeat_mode == RepeatMode.all and self._repeat_cycle_items:
                        replay_items = [
                            NewQueueItem(
                                source_url=item[0],
                                normalized_url=item[1],
                                source_type=item[2],
                                title=item[3],
                                duration_seconds=item[4],
                                thumbnail_url=item[5],
                                uploaded_at=item[6] if len(item) > 6 else None,
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
        self.state.now_playing_source_site = None
        self.state.now_playing_duration_seconds = None
        self.state.now_playing_is_live = False
        self.state.now_playing_can_seek = False
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
                chunk = self.ffmpeg_pipeline.read_chunk(process.stdout, self.chunk_size)
                if not chunk:
                    break
                self.hub.publish(chunk)
                if time.monotonic() - idle_start >= self.queue_poll_seconds:
                    idle_start = time.monotonic()
                    if self.repository.has_queued_items():
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
        self.state.now_playing_source_site = None
        self.state.now_playing_duration_seconds = queue_item.duration_seconds
        self.state.now_playing_is_live = queue_item.source_type == "live_stream"
        self.state.now_playing_can_seek = bool((queue_item.duration_seconds or 0) > 0) and not self.state.now_playing_is_live
        start_offset_seconds = self._consume_pending_seek_seconds()
        self._set_playback_offset_seconds(start_offset_seconds)
        self.state.paused = False
        self.state.paused_elapsed_seconds = None
        self._notify_state_changed()
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
                    try:
                        resolved = self.source_resolver.resolve_video(queue_item.source_url)
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
                        if resolved.thumbnail_url:
                            self.state.now_playing_thumbnail_url = resolved.thumbnail_url
                        if resolved.channel:
                            self.state.now_playing_channel = resolved.channel
                        self.state.now_playing_source_site = resolved.source_site
                        self.state.now_playing_is_live = bool(resolved.is_live)
                        self.state.now_playing_can_seek = bool(resolved.can_seek)
                        if not resolved.can_seek:
                            self.state.now_playing_duration_seconds = None
                        elif resolved.duration_seconds is not None:
                            self.state.now_playing_duration_seconds = resolved.duration_seconds
                        self._notify_state_changed()
                        seek_offset = self._consume_pending_seek_seconds(default=start_offset_seconds)
                        self._set_playback_offset_seconds(seek_offset)
                        start_offset_seconds = seek_offset

                        spawn_for_source = getattr(self.ffmpeg_pipeline, "spawn_for_source", None)
                        if not callable(spawn_for_source):
                            raise FfmpegError("spawn_for_source unavailable")
                        source_process = None
                        process = spawn_for_source(resolved.stream_url, start_at_seconds=seek_offset)
                        self._set_active_processes(process, None)

                        attempt_chunks_sent = 0
                        attempt_bytes_sent = 0
                        attempt_started_at = time.monotonic()
                        ffmpeg_stderr_snapshot = ""
                        source_stderr_snapshot = ""
                        while not self._stop_event.is_set():
                            if self._skip_event.is_set():
                                raise InterruptedError(self._consume_interrupt_reason())
                            chunk = self.ffmpeg_pipeline.read_chunk(process.stdout, self.chunk_size)
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
                            self.hub.publish(chunk)
                            self._record_streamed_chunk(len(chunk))
                            attempt_chunks_sent += 1
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
                        if (
                            queue_item.duration_seconds
                            and queue_item.duration_seconds > 30
                            and not self.state.now_playing_is_live
                        ):
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
                                        normalized_url=queue_item.normalized_url,
                                        source_type=queue_item.source_type,
                                        title=queue_item.title,
                                        channel=queue_item.channel,
                                        duration_seconds=queue_item.duration_seconds,
                                        thumbnail_url=queue_item.thumbnail_url,
                                        uploaded_at=queue_item.uploaded_at,
                                        playlist_id=queue_item.playlist_id,
                                    )
                                ]
                            )
                            if repeated:
                                self.repository.move_item_to_front(repeated[0].id)
                        self._repeat_cycle_items.append(
                            (
                                queue_item.source_url,
                                queue_item.normalized_url,
                                queue_item.source_type,
                                queue_item.title,
                                queue_item.duration_seconds,
                                queue_item.thumbnail_url,
                                queue_item.uploaded_at,
                            )
                        )
                        self._record_track_outcome(completed=True)
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
                logger.info(
                    "Track %s interrupted (%s). streamed_bytes=%s streamed_chunks=%s",
                    queue_item.id,
                    reason or "skip",
                    total_bytes_sent,
                    total_chunks_sent,
                )
                self.repository.mark_playback_finished(queue_item.id, status=QueueStatus.skipped)
                self._record_track_outcome(skipped=True)
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
            self._notify_state_changed()
        except Exception:
            logger.exception("Failed updating playback state after stop")

    def _stream_paused_cycle(self) -> None:
        while not self._stop_event.is_set() and self.state.paused:
            if self._skip_event.is_set():
                reason = self._consume_interrupt_reason()
                if reason == "pause":
                    continue
                if reason == "resume":
                    break
                raise InterruptedError(reason)
            time.sleep(min(0.1, self.queue_poll_seconds))
