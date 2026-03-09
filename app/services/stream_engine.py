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


class StreamEngine:
    def __init__(
        self,
        repository: Repository,
        yt_dlp_service: YtDlpService,
        ffmpeg_pipeline: FfmpegPipeline,
        chunk_size: int = 4096,
        queue_poll_seconds: float = 1.0,
    ) -> None:
        self.repository = repository
        self.yt_dlp_service = yt_dlp_service
        self.ffmpeg_pipeline = ffmpeg_pipeline
        self.chunk_size = chunk_size
        self.queue_poll_seconds = queue_poll_seconds
        self.state = PlaybackState()
        self.hub = SharedMp3Hub()
        self._stop_event = threading.Event()
        self._skip_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._process_lock = threading.Lock()
        self._active_process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._run, daemon=True, name="stream-engine")
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._terminate_active_process()
        if self._worker:
            self._worker.join(timeout=3)

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

    def _set_active_process(self, process: subprocess.Popen[bytes] | None) -> None:
        with self._process_lock:
            self._active_process = process

    def _terminate_active_process(self) -> None:
        with self._process_lock:
            process = self._active_process
        if process is None:
            return
        try:
            process.terminate()
            process.wait(timeout=1)
        except Exception:
            pass

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
        self._set_active_process(process)
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
            self._set_active_process(None)
            try:
                process.terminate()
                process.wait(timeout=1)
            except Exception:
                pass

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
        try:
            resolved = self.yt_dlp_service.resolve_video(queue_item.source_url)
            self.repository.mark_item_resolved(queue_item.id, resolved.stream_url)
            if resolved.thumbnail_url:
                self.state.now_playing_thumbnail_url = resolved.thumbnail_url
            if resolved.channel:
                self.state.now_playing_channel = resolved.channel
            process = self.ffmpeg_pipeline.spawn_for_source(resolved.stream_url)
            self._set_active_process(process)
            while not self._stop_event.is_set():
                if self._skip_event.is_set():
                    raise InterruptedError("Track skipped")
                chunk = self.ffmpeg_pipeline.read_chunk(process.stdout, self.chunk_size)
                if not chunk:
                    break
                self.hub.publish(chunk)
            status = QueueStatus.skipped if self._skip_event.is_set() else QueueStatus.completed
            self.repository.mark_playback_finished(queue_item.id, status=status)
        except InterruptedError:
            self.repository.mark_playback_finished(queue_item.id, status=QueueStatus.skipped)
        except YtDlpError as exc:
            logger.warning("Failed resolving track %s: %s", queue_item.id, exc)
            self.repository.mark_playback_finished(queue_item.id, status=QueueStatus.failed, error_message=str(exc))
        except FfmpegError as exc:
            logger.error("ffmpeg error on track %s: %s", queue_item.id, exc)
            self.repository.mark_playback_finished(queue_item.id, status=QueueStatus.failed, error_message=str(exc))
        except Exception as exc:
            logger.exception("Playback failure: %s", exc)
            self.repository.mark_playback_finished(queue_item.id, status=QueueStatus.failed, error_message=str(exc))
        finally:
            self._terminate_active_process()
            self._set_active_process(None)
