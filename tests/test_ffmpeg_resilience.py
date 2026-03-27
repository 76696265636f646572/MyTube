from __future__ import annotations

import time
from io import BytesIO

from app.db.models import QueueStatus
from app.db.repository import NewQueueItem, Repository
from app.services.ffmpeg_pipeline import FfmpegError
from app.services.stream_engine import StreamEngine
from app.services.yt_dlp_service import ResolvedTrack


class MissingFfmpegPipeline:
    def spawn_silence(self):
        raise FfmpegError("ffmpeg missing")

    def spawn_for_stdin(self, stdin):
        _ = stdin
        raise FfmpegError("ffmpeg missing")

    @staticmethod
    def read_chunk(stdout, chunk_size: int):
        _ = stdout, chunk_size
        return b""


class FakeProc:
    def __init__(self, payload: bytes, returncode: int = 0):
        self.stdout = BytesIO(payload)
        self.returncode = returncode

    def terminate(self):
        return

    def wait(self, timeout=None):
        _ = timeout
        return

    def poll(self):
        return self.returncode


class SequenceFfmpegPipeline:
    def __init__(self, attempts: list[tuple[bytes, int]]):
        self._attempts = list(attempts)
        self.spawn_calls = 0

    def spawn_silence(self):
        return FakeProc(b"\x00" * 8, returncode=0)

    def spawn_for_stdin(self, stdin):
        _ = stdin
        self.spawn_calls += 1
        payload, code = self._attempts.pop(0)
        return FakeProc(payload, returncode=code)

    @staticmethod
    def read_chunk(stdout, chunk_size: int):
        return stdout.read(chunk_size)


class FakeYtDlp:
    def __init__(self) -> None:
        self.spawn_urls: list[str] = []

    def spawn_audio_stream(self, url: str) -> FakeProc:
        self.spawn_urls.append(url)
        return FakeProc(b"source", returncode=0)

    def resolve_video(self, url: str, force_refresh: bool = False) -> ResolvedTrack:
        _ = force_refresh
        return ResolvedTrack(
            source_url=url,
            normalized_url=url,
            title="t",
            channel="c",
            duration_seconds=1,
            thumbnail_url=None,
            stream_url="http://x/audio",
        )


class SourceAwareYtDlp:
    def __init__(self) -> None:
        self.spawn_urls: list[str] = []

    def spawn_audio_stream(self, url: str) -> FakeProc:
        self.spawn_urls.append(url)
        return FakeProc(b"source", returncode=0)

    def resolve_video(self, url: str, force_refresh: bool = False) -> ResolvedTrack:
        _ = force_refresh
        return ResolvedTrack(
            source_url=url,
            normalized_url=url,
            title="t",
            channel="c",
            duration_seconds=1,
            thumbnail_url=None,
            stream_url=f"http://x/{url}",
        )


def test_engine_survives_missing_ffmpeg_in_idle(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/idle.db")
    repo.init_db()
    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=FakeYtDlp(),
        ffmpeg_pipeline=MissingFfmpegPipeline(),
        queue_poll_seconds=0.01,
    )
    engine.start()
    time.sleep(0.05)
    assert engine._worker is not None  # noqa: SLF001
    assert engine._worker.is_alive() is True  # noqa: SLF001
    engine.stop()


def test_engine_marks_track_failed_when_ffmpeg_missing(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/play.db")
    repo.init_db()
    created = repo.enqueue_items(
        [NewQueueItem(source_url="u", normalized_url="u", source_type="video", title="song")]
    )
    item = repo.dequeue_next()
    assert item is not None

    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=FakeYtDlp(),
        ffmpeg_pipeline=MissingFfmpegPipeline(),
        queue_poll_seconds=0.01,
    )
    engine._play_item(created[0].id)  # noqa: SLF001
    saved = repo.get_item(created[0].id)
    assert saved is not None
    assert saved.status == QueueStatus.failed


def test_engine_marks_track_failed_on_unexpected_ffmpeg_exit(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/unexpected-exit.db")
    repo.init_db()
    created = repo.enqueue_items(
        [NewQueueItem(source_url="u", normalized_url="u", source_type="video", title="song")]
    )
    dequeued = repo.dequeue_next()
    assert dequeued is not None

    pipeline = SequenceFfmpegPipeline(attempts=[(b"abc", 1)])
    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=FakeYtDlp(),
        ffmpeg_pipeline=pipeline,
        queue_poll_seconds=0.01,
        playback_retry_count=0,
    )
    engine._play_item(created[0].id)  # noqa: SLF001

    saved = repo.get_item(created[0].id)
    assert saved is not None
    assert saved.status == QueueStatus.failed
    assert pipeline.spawn_calls == 1


def test_engine_retries_track_and_recovers(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/retry-recover.db")
    repo.init_db()
    created = repo.enqueue_items(
        [NewQueueItem(source_url="u", normalized_url="u", source_type="video", title="song")]
    )
    dequeued = repo.dequeue_next()
    assert dequeued is not None

    pipeline = SequenceFfmpegPipeline(attempts=[(b"broken", 1), (b"healthy", 0)])
    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=FakeYtDlp(),
        ffmpeg_pipeline=pipeline,
        queue_poll_seconds=0.01,
        playback_retry_count=1,
    )
    engine._play_item(created[0].id)  # noqa: SLF001

    saved = repo.get_item(created[0].id)
    assert saved is not None
    assert saved.status == QueueStatus.completed
    assert pipeline.spawn_calls == 2


def test_engine_only_advances_after_retries_exhausted(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/retry-advance.db")
    repo.init_db()
    first = repo.enqueue_items(
        [NewQueueItem(source_url="u1", normalized_url="u1", source_type="video", title="first")]
    )[0]
    second = repo.enqueue_items(
        [NewQueueItem(source_url="u2", normalized_url="u2", source_type="video", title="second")]
    )[0]

    pipeline = SequenceFfmpegPipeline(
        attempts=[
            (b"chunk", 1),
            (b"chunk", 1),
            (b"chunk", 1),
            (b"chunk", 0),
        ]
    )
    yt_dlp = SourceAwareYtDlp()
    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=yt_dlp,
        ffmpeg_pipeline=pipeline,
        queue_poll_seconds=0.01,
        playback_retry_count=2,
    )
    engine.start()
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        first_saved = repo.get_item(first.id)
        second_saved = repo.get_item(second.id)
        if (
            first_saved is not None
            and second_saved is not None
            and first_saved.status == QueueStatus.failed
            and second_saved.status == QueueStatus.completed
        ):
            break
        time.sleep(0.02)
    engine.stop()

    first_saved = repo.get_item(first.id)
    second_saved = repo.get_item(second.id)
    assert first_saved is not None
    assert second_saved is not None
    assert first_saved.status == QueueStatus.failed
    assert second_saved.status == QueueStatus.completed
    assert pipeline.spawn_calls >= 4
    assert yt_dlp.spawn_urls[0] == "u1"
    assert yt_dlp.spawn_urls.count("u1") >= 3
    assert "u2" in yt_dlp.spawn_urls
