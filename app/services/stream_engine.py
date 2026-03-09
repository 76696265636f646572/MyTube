from __future__ import annotations

import logging
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Generator

from app.db.models import QueueStatus
from app.db.repository import Repository
from app.services.ffmpeg_pipeline import FfmpegError, FfmpegPipeline
from app.services.yt_dlp_service import YtDlpError, YtDlpService

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


@dataclass
class PlaybackState:
    mode: PlaybackMode = PlaybackMode.idle
    now_playing_id: int | None = None
    now_playing_title: str | None = None
    now_playing_channel: str | None = None
    now_playing_thumbnail_url: str | None = None
    now_playing_duration_seconds: int | None = None
    started_at_epoch_seconds: float | None = None
    started_at_monotonic_seconds: float | None = None


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

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._clients)


class StreamEngine:
    def __init__(
        self,
        repository: Repository,
        yt_dlp_service: YtDlpService,
        ffmpeg_pipeline: FfmpegPipeline,
        chunk_size: int = 4096,
        queue_poll_seconds: float = 1.0,
        playback_retry_count: int = 2,
        stats_log_seconds: float = 15.0,
    ) -> None:
        self.repository = repository
        self.yt_dlp_service = yt_dlp_service
        self.ffmpeg_pipeline = ffmpeg_pipeline
        self.chunk_size = chunk_size
        self.queue_poll_seconds = queue_poll_seconds
        self.playback_retry_count = max(0, playback_retry_count)
        self.stats_log_seconds = max(1.0, stats_log_seconds)
        self.state = PlaybackState()
        self.hub = SharedMp3Hub()
        self._stop_event = threading.Event()
        self._skip_event = threading.Event()
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
        self._terminate_active_process()
        if self._worker:
            self._worker.join(timeout=3)
        if self._stats_worker:
            self._stats_worker.join(timeout=3)

    def skip_current(self) -> None:
        self._skip_event.set()
        self._terminate_active_process()

    def subscribe(self) -> Generator[bytes, None, None]:
        return self.hub.subscribe()

    def playback_progress(self) -> dict[str, float | int | None]:
        elapsed_seconds: float | None = None
        if self.state.mode == PlaybackMode.playing and self.state.started_at_monotonic_seconds is not None:
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
        self.state.started_at_epoch_seconds = None
        self.state.started_at_monotonic_seconds = None
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
        self.state.now_playing_duration_seconds = queue_item.duration_seconds
        self.state.started_at_epoch_seconds = time.time()
        self.state.started_at_monotonic_seconds = time.monotonic()
        self._skip_event.clear()
        total_attempts = self.playback_retry_count + 1
        total_chunks_sent = 0
        total_bytes_sent = 0
        resolved_duration_seconds: int | None = None
        probed_duration_seconds: float | None = None
        try:
            for attempt in range(1, total_attempts + 1):
                if self._stop_event.is_set():
                    raise InterruptedError("Playback stopped")
                try:
                    resolved = self.yt_dlp_service.resolve_video(queue_item.source_url)
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
                    source_process = self.yt_dlp_service.spawn_audio_stream(queue_item.source_url)
                    self._set_active_processes(None, source_process)
                    process = self.ffmpeg_pipeline.spawn_for_stdin(source_process.stdout)
                    if source_process.stdout is not None:
                        source_process.stdout.close()
                    self._set_active_processes(process, source_process)
                    attempt_chunks_sent = 0
                    attempt_bytes_sent = 0
                    attempt_started_at = time.monotonic()
                    ffmpeg_stderr_snapshot = ""
                    source_stderr_snapshot = ""
                    while not self._stop_event.is_set():
                        if self._skip_event.is_set():
                            raise InterruptedError("Track skipped")
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
                        raise InterruptedError("Playback stopped")
                    if self._skip_event.is_set():
                        raise InterruptedError("Track skipped")

                    return_code = self._process_return_code(process)
                    source_return_code = self._process_return_code(source_process)
                    elapsed_seconds = max(0.0, time.monotonic() - attempt_started_at)
                    expected_duration_seconds = (
                        probed_duration_seconds or float(resolved_duration_seconds or 0) or float(queue_item.duration_seconds or 0)
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
                    self._record_track_outcome(completed=True)
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
        except InterruptedError:
            logger.info(
                "Track %s interrupted (%s). streamed_bytes=%s streamed_chunks=%s",
                queue_item.id,
                "skipped" if self._skip_event.is_set() else "stopped",
                total_bytes_sent,
                total_chunks_sent,
            )
            self.repository.mark_playback_finished(queue_item.id, status=QueueStatus.skipped)
            self._record_track_outcome(skipped=True)
        except YtDlpError as exc:
            logger.warning(
                "Failed resolving track %s (%s): %s",
                queue_item.id,
                queue_item.source_url,
                exc,
            )
            self.repository.mark_playback_finished(queue_item.id, status=QueueStatus.failed, error_message=str(exc))
            self._record_track_outcome(failed=True)
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
        except Exception as exc:
            logger.exception(
                "Playback failure on track %s (%s): %s",
                queue_item.id,
                queue_item.title or queue_item.source_url,
                exc,
            )
            self.repository.mark_playback_finished(queue_item.id, status=QueueStatus.failed, error_message=str(exc))
            self._record_track_outcome(failed=True)
