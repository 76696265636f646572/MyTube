from io import BytesIO
from threading import Thread

from app.db.models import QueueStatus
from app.db.repository import NewQueueItem, Repository
from app.services.stream_engine import PlaybackMode, SharedMp3Hub, StreamEngine
from app.services.yt_dlp_service import ResolvedTrack


class FakeProc:
    def __init__(self, payload: bytes, *, returncode: int = 0, stderr: bytes = b"") -> None:
        self.stdout = BytesIO(payload)
        self.stderr = BytesIO(stderr)
        self.returncode = returncode

    def terminate(self) -> None:
        return

    def wait(self, timeout: float | None = None) -> None:
        return

    def poll(self):
        return self.returncode


class FakeFfmpeg:
    def spawn_for_stdin(self, stdin) -> FakeProc:
        _ = stdin
        return FakeProc(b"abc123")

    def spawn_silence(self) -> FakeProc:
        return FakeProc(b"\x00" * 8)

    @staticmethod
    def read_chunk(stdout, chunk_size: int) -> bytes:
        return stdout.read(chunk_size)

    @staticmethod
    def probe_source(source_url: str) -> dict[str, str | float | None]:
        _ = source_url
        return {"duration_seconds": 120.0, "bit_rate": 128000.0, "format_name": "mp3"}


class TruncatedFfmpeg(FakeFfmpeg):
    def spawn_for_stdin(self, stdin) -> FakeProc:
        _ = stdin
        return FakeProc(
            b"abc123",
            returncode=0,
            stderr=b"[tls] Error in the pull function.\nInput/output error\n",
        )


class FakeYtDlp:
    def spawn_audio_stream(self, url: str) -> FakeProc:
        _ = url
        return FakeProc(b"src")

    def resolve_video(self, url: str) -> ResolvedTrack:
        return ResolvedTrack(
            source_url=url,
            normalized_url=url,
            title="resolved",
            channel="chan",
            duration_seconds=120,
            thumbnail_url=None,
            stream_url="http://media.local/audio",
        )


def test_shared_hub_fan_out():
    hub = SharedMp3Hub()
    gen1 = hub.subscribe()
    gen2 = hub.subscribe()
    received: list[bytes] = []

    def _consume(gen):
        received.append(next(gen))

    t1 = Thread(target=_consume, args=(gen1,))
    t2 = Thread(target=_consume, args=(gen2,))
    t1.start()
    t2.start()
    hub.publish(b"chunk")
    t1.join(timeout=1)
    t2.join(timeout=1)
    assert received == [b"chunk", b"chunk"]
    gen1.close()
    gen2.close()


def test_stream_engine_playback_lifecycle(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/engine.db")
    repo.init_db()
    created = repo.enqueue_items(
        [NewQueueItem(source_url="u", normalized_url="u", source_type="video", title="Song")]
    )
    item = repo.dequeue_next()
    assert item is not None

    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=FakeYtDlp(),
        ffmpeg_pipeline=FakeFfmpeg(),
        chunk_size=2,
        queue_poll_seconds=0.1,
    )
    engine._play_item(created[0].id)  # noqa: SLF001 - lifecycle unit coverage
    assert engine.state.mode == PlaybackMode.playing

    finished = repo.get_item(created[0].id)
    assert finished is not None
    assert finished.status in (QueueStatus.completed, QueueStatus.skipped)


def test_stream_engine_does_not_mark_upstream_truncation_complete(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/engine.db")
    repo.init_db()
    created = repo.enqueue_items(
        [
            NewQueueItem(
                source_url="u",
                normalized_url="u",
                source_type="video",
                title="Song",
                duration_seconds=120,
            )
        ]
    )
    item = repo.dequeue_next()
    assert item is not None

    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=FakeYtDlp(),
        ffmpeg_pipeline=TruncatedFfmpeg(),
        chunk_size=2,
        queue_poll_seconds=0.1,
        playback_retry_count=0,
    )

    engine._play_item(created[0].id)  # noqa: SLF001 - lifecycle unit coverage

    finished = repo.get_item(created[0].id)
    assert finished is not None
    assert finished.status == QueueStatus.failed


def test_pause_interrupt_is_consumed_without_lingering_skip_event(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/pause.db")
    repo.init_db()
    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=FakeYtDlp(),
        ffmpeg_pipeline=FakeFfmpeg(),
        queue_poll_seconds=0.01,
    )

    engine._request_interrupt("pause", terminate=False)  # noqa: SLF001 - regression coverage

    assert engine._skip_event.is_set() is True  # noqa: SLF001
    assert engine._consume_interrupt_reason() == "pause"  # noqa: SLF001
    assert engine._skip_event.is_set() is False  # noqa: SLF001


def test_paused_cycle_exits_cleanly_on_resume_interrupt(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/resume.db")
    repo.init_db()
    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=FakeYtDlp(),
        ffmpeg_pipeline=FakeFfmpeg(),
        queue_poll_seconds=0.01,
    )
    engine.state.paused = True
    engine._request_interrupt("resume", terminate=False)  # noqa: SLF001 - regression coverage

    engine._stream_paused_cycle()  # noqa: SLF001 - regression coverage

    assert engine._skip_event.is_set() is False  # noqa: SLF001


def test_paused_cycle_does_not_publish_silence(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/no-silence.db")
    repo.init_db()
    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=FakeYtDlp(),
        ffmpeg_pipeline=FakeFfmpeg(),
        queue_poll_seconds=0.01,
    )
    published: list[bytes] = []
    engine.hub.publish = published.append  # type: ignore[method-assign]
    engine.state.paused = True

    def _resume_soon():
        import time

        time.sleep(0.03)
        engine._request_interrupt("resume", terminate=False)  # noqa: SLF001 - regression coverage

    Thread(target=_resume_soon, daemon=True).start()
    engine._stream_paused_cycle()  # noqa: SLF001 - regression coverage

    assert published == []


def test_shuffle_reorders_queue_and_restores_previous_order(tmp_path, monkeypatch):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/shuffle.db")
    repo.init_db()
    created = repo.enqueue_items(
        [
            NewQueueItem(source_url="u1", normalized_url="u1", source_type="video", title="One"),
            NewQueueItem(source_url="u2", normalized_url="u2", source_type="video", title="Two"),
            NewQueueItem(source_url="u3", normalized_url="u3", source_type="video", title="Three"),
        ]
    )

    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=FakeYtDlp(),
        ffmpeg_pipeline=FakeFfmpeg(),
        queue_poll_seconds=0.01,
    )

    original_ids = [item.id for item in created]

    def reverse_shuffle(values):
        values.reverse()

    monkeypatch.setattr("app.services.stream_engine.random.shuffle", reverse_shuffle)

    assert engine.set_shuffle_enabled(True) is True
    assert repo.list_queued_ids() == list(reversed(original_ids))

    assert engine.set_shuffle_enabled(False) is False
    assert repo.list_queued_ids() == original_ids
