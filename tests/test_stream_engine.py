from io import BytesIO
import queue
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

    def spawn_for_source(self, source_url: str, start_at_seconds: float = 0.0) -> FakeProc:
        _ = source_url, start_at_seconds
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
    def __init__(self) -> None:
        self.spawn_calls = 0

    def spawn_audio_stream(self, url: str) -> FakeProc:
        _ = url
        self.spawn_calls += 1
        return FakeProc(b"src")

    def resolve_video(self, url: str, force_refresh: bool = False) -> ResolvedTrack:
        _ = force_refresh
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
    hub = SharedMp3Hub(stream_queue_size=16)
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


def test_shared_hub_clear_drops_buffered_audio():
    hub = SharedMp3Hub(stream_queue_size=16)
    hub._clients["client-a"] = queue.Queue()  # noqa: SLF001 - focused hub coverage
    hub._clients["client-b"] = queue.Queue()  # noqa: SLF001 - focused hub coverage

    hub.publish(b"old-a")
    hub.publish(b"old-b")

    hub.clear()

    assert hub._clients["client-a"].empty() is True  # noqa: SLF001
    assert hub._clients["client-b"].empty() is True  # noqa: SLF001

    hub.publish(b"fresh")

    assert hub._clients["client-a"].get_nowait() == b"fresh"  # noqa: SLF001
    assert hub._clients["client-b"].get_nowait() == b"fresh"  # noqa: SLF001


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


def test_stream_engine_prefetches_upcoming_tracks_before_current_track_finishes(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/prefetch.db")
    repo.init_db()
    first = repo.enqueue_items(
        [NewQueueItem(source_url="u1", normalized_url="u1", source_type="video", title="First")]
    )[0]
    repo.enqueue_items(
        [NewQueueItem(source_url="u2", normalized_url="u2", source_type="video", title="Second")]
    )
    dequeued = repo.dequeue_next()
    assert dequeued is not None

    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=FakeYtDlp(),
        ffmpeg_pipeline=FakeFfmpeg(),
        chunk_size=2,
        queue_poll_seconds=0.1,
    )

    prefetch_called = False

    def _trigger_prefetch() -> None:
        nonlocal prefetch_called
        prefetch_called = True

    engine._trigger_prefetch_upcoming_tracks = _trigger_prefetch  # type: ignore[method-assign]  # noqa: SLF001

    original_mark_playback_finished = repo.mark_playback_finished

    def _mark_playback_finished(item_id: int, status: QueueStatus, error_message: str | None = None):
        if item_id == first.id:
            assert prefetch_called is True
        return original_mark_playback_finished(item_id, status=status, error_message=error_message)

    repo.mark_playback_finished = _mark_playback_finished  # type: ignore[method-assign]

    engine._play_item(first.id)  # noqa: SLF001 - regression coverage for transition prefetch timing

    assert prefetch_called is True


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


def test_interrupt_clears_buffered_audio_for_connected_clients(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/interrupt-clear.db")
    repo.init_db()
    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=FakeYtDlp(),
        ffmpeg_pipeline=FakeFfmpeg(),
        queue_poll_seconds=0.01,
    )
    client_queue: queue.Queue[bytes] = queue.Queue()
    engine.hub._clients["listener"] = client_queue  # noqa: SLF001 - focused regression coverage

    engine.hub.publish(b"stale-audio")

    assert client_queue.empty() is False

    engine._request_interrupt("skip")  # noqa: SLF001 - direct interrupt coverage

    assert client_queue.empty() is True


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


def test_paused_cycle_publishes_silence_until_resume(tmp_path):
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

    assert published != []
    assert all(chunk == b"\x00" * 8 for chunk in published)


def test_playback_bridges_silence_before_first_track_chunk(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/transition-silence.db")
    repo.init_db()
    created = repo.enqueue_items(
        [NewQueueItem(source_url="u", normalized_url="u", source_type="video", title="Song")]
    )
    dequeued = repo.dequeue_next()
    assert dequeued is not None

    class SlowStartYtDlp(FakeYtDlp):
        def spawn_audio_stream(self, url: str) -> FakeProc:
            import time

            time.sleep(0.03)
            return super().spawn_audio_stream(url)

    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=SlowStartYtDlp(),
        ffmpeg_pipeline=FakeFfmpeg(),
        chunk_size=2,
        queue_poll_seconds=0.01,
    )
    published: list[bytes] = []
    engine.hub.publish = published.append  # type: ignore[method-assign]
    engine.hub.subscriber_count = lambda: 1  # type: ignore[method-assign]

    engine._play_item(created[0].id)  # noqa: SLF001 - regression coverage

    assert published != []
    first_audio_index = next(index for index, chunk in enumerate(published) if chunk != b"\x00" * len(chunk))
    assert first_audio_index > 0
    assert all(chunk == b"\x00" * len(chunk) for chunk in published[:first_audio_index])
    assert published[first_audio_index:] == [b"ab", b"c1", b"23"]


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


def test_resolve_uses_prefetched_cache(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/prefetched-cache.db")
    repo.init_db()
    created = repo.enqueue_items(
        [NewQueueItem(source_url="u", normalized_url="u", source_type="video", title="Song")]
    )

    class CountingYtDlp(FakeYtDlp):
        def __init__(self) -> None:
            self.calls = 0

        def resolve_video(self, url: str, force_refresh: bool = False) -> ResolvedTrack:
            _ = force_refresh
            self.calls += 1
            return super().resolve_video(url)

    yt = CountingYtDlp()
    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=yt,
        ffmpeg_pipeline=FakeFfmpeg(),
        queue_poll_seconds=0.01,
    )
    queue_item = repo.get_item(created[0].id)
    assert queue_item is not None

    prefetched = yt.resolve_video(queue_item.source_url)
    engine._cache_resolved_track(queue_item.id, prefetched)  # noqa: SLF001 - direct cache coverage

    resolved = engine._resolve_track_for_item(queue_item, force_refresh=False)  # noqa: SLF001 - direct cache coverage

    assert resolved.stream_url == prefetched.stream_url
    assert yt.calls == 1


def test_previous_reuses_recently_resolved_track(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/previous-cache.db")
    repo.init_db()

    class NormalizingYtDlp(FakeYtDlp):
        @staticmethod
        def normalize_url(url: str) -> str:
            return url

    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=NormalizingYtDlp(),
        ffmpeg_pipeline=FakeFfmpeg(),
        queue_poll_seconds=0.01,
    )

    resolved = ResolvedTrack(
        source_url="u",
        normalized_url="u",
        title="resolved",
        channel="chan",
        duration_seconds=120,
        thumbnail_url=None,
        stream_url="http://media.local/audio",
    )
    engine._remember_recent_resolved_track(resolved)  # noqa: SLF001 - direct cache coverage

    repo.enqueue_items([NewQueueItem(source_url="u", normalized_url="u", source_type="video", title="Song")])
    played = repo.dequeue_next()
    assert played is not None
    repo.mark_playback_finished(played.id, status=QueueStatus.completed)

    outcome = engine.play_previous_or_restart()

    assert outcome == "previous"
    queued_ids = repo.list_queued_ids()
    assert len(queued_ids) == 1
    cached = engine._get_cached_resolved_track(queued_ids[0])  # noqa: SLF001 - direct cache coverage
    assert cached is not None
    assert cached.stream_url == resolved.stream_url


def test_retry_resolves_fresh_metadata_after_failed_attempt(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/retry-refresh.db")
    repo.init_db()
    created = repo.enqueue_items(
        [NewQueueItem(source_url="u", normalized_url="u", source_type="video", title="Song")]
    )
    dequeued = repo.dequeue_next()
    assert dequeued is not None

    class RetryAwareYtDlp(FakeYtDlp):
        def __init__(self) -> None:
            super().__init__()
            self.resolve_calls = 0
            self.force_refresh_values: list[bool] = []

        def resolve_video(self, url: str, force_refresh: bool = False) -> ResolvedTrack:
            self.resolve_calls += 1
            self.force_refresh_values.append(force_refresh)
            stream_url = f"http://media.local/audio/{self.resolve_calls}"
            return ResolvedTrack(
                source_url=url,
                normalized_url=url,
                title="resolved",
                channel="chan",
                duration_seconds=120,
                thumbnail_url=None,
                stream_url=stream_url,
            )

    class RetryAwareFfmpeg(FakeFfmpeg):
        def __init__(self) -> None:
            self.urls: list[str] = []

        def spawn_for_source(self, source_url: str, start_at_seconds: float = 0.0) -> FakeProc:
            _ = start_at_seconds
            self.urls.append(source_url)
            if len(self.urls) == 1:
                return FakeProc(b"", returncode=1)
            return FakeProc(b"abc123", returncode=0)

    yt = RetryAwareYtDlp()
    ffmpeg = RetryAwareFfmpeg()
    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=yt,
        ffmpeg_pipeline=ffmpeg,
        chunk_size=2,
        queue_poll_seconds=0.01,
        playback_retry_count=1,
    )

    engine._set_pending_seek_seconds(10.0)  # noqa: SLF001 - force spawn_for_source path
    engine._play_item(created[0].id)  # noqa: SLF001 - retry behavior coverage

    assert yt.resolve_calls == 2
    assert yt.force_refresh_values == [False, True]
    assert ffmpeg.urls == ["http://media.local/audio/1", "http://media.local/audio/2"]
    finished = repo.get_item(created[0].id)
    assert finished is not None
    assert finished.status == QueueStatus.completed


def test_runtime_stats_reports_cache_sizes(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/cache-stats.db")
    repo.init_db()
    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=FakeYtDlp(),
        ffmpeg_pipeline=FakeFfmpeg(),
        queue_poll_seconds=0.01,
    )
    engine.hub.subscriber_count = lambda: 3  # type: ignore[method-assign]

    first = ResolvedTrack(
        source_url="u1",
        normalized_url="u1",
        title="resolved",
        channel="chan",
        duration_seconds=120,
        thumbnail_url=None,
        stream_url="http://media.local/audio/1",
    )
    second = ResolvedTrack(
        source_url="u2",
        normalized_url="u2",
        title="resolved",
        channel="chan",
        duration_seconds=120,
        thumbnail_url=None,
        stream_url="http://media.local/audio/2",
    )

    engine._cache_resolved_track(101, first)  # noqa: SLF001 - direct cache stats coverage
    engine._cache_resolved_track(102, second)  # noqa: SLF001 - direct cache stats coverage
    engine._remember_recent_resolved_track(first)  # noqa: SLF001 - direct cache stats coverage

    stats = engine.runtime_stats()

    assert stats["cached_track_count"] == 2
    assert stats["recent_cache_count"] == 1
    assert stats["prefetched_audio_count"] == 0
    assert stats["mp3_stream_listeners"] == 3
    assert stats["pcm_stream_listeners"] == 0
    assert stats["total_listeners"] == 3


def test_runtime_stats_include_pcm_listener_provider(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/pcm-listeners.db")
    repo.init_db()
    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=FakeYtDlp(),
        ffmpeg_pipeline=FakeFfmpeg(),
        queue_poll_seconds=0.01,
        pcm_listener_count_provider=lambda: 2,
    )
    engine.hub.subscriber_count = lambda: 1  # type: ignore[method-assign]

    stats = engine.runtime_stats()

    assert stats["mp3_stream_listeners"] == 1
    assert stats["pcm_stream_listeners"] == 2
    assert stats["total_listeners"] == 3


def test_recent_resolved_cache_prunes_old_entries(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/recent-prune.db")
    repo.init_db()

    class NormalizingYtDlp(FakeYtDlp):
        @staticmethod
        def normalize_url(url: str) -> str:
            return url

    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=NormalizingYtDlp(),
        ffmpeg_pipeline=FakeFfmpeg(),
        queue_poll_seconds=0.01,
    )

    for index in range(1, 5):
        resolved = ResolvedTrack(
            source_url=f"u{index}",
            normalized_url=f"u{index}",
            title="resolved",
            channel="chan",
            duration_seconds=120,
            thumbnail_url=None,
            stream_url=f"http://media.local/audio/{index}",
        )
        engine._remember_recent_resolved_track(resolved)  # noqa: SLF001 - direct cache pruning coverage

    stats = engine.runtime_stats()

    assert stats["recent_cache_count"] == 2
    assert list(engine._recent_resolved_order) == ["u3", "u4"]  # noqa: SLF001 - direct cache pruning coverage
    assert set(engine._recent_resolved_by_url.keys()) == {"u3", "u4"}  # noqa: SLF001 - direct cache pruning coverage

    engine._seed_resolved_cache_from_recent(777, "u1")  # noqa: SLF001 - ensure stale item not seedable
    assert engine._get_cached_resolved_track(777) is None  # noqa: SLF001 - ensure stale item not seedable


def test_stream_engine_direct_media_uses_spawn_for_source_not_ytdlp_stdin(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/direct.db")
    repo.init_db()
    created = repo.enqueue_items(
        [
            NewQueueItem(
                source_url="https://CDN.example.com/track.mp3#frag",
                normalized_url="https://cdn.example.com/track.mp3",
                provider="direct",
                source_type="remote_audio",
                title="Direct",
            )
        ]
    )[0]
    repo.dequeue_next()

    class CountingFfmpeg(FakeFfmpeg):
        def __init__(self) -> None:
            self.sources: list[str] = []

        def spawn_for_source(self, source_url: str, start_at_seconds: float = 0.0) -> FakeProc:
            _ = start_at_seconds
            self.sources.append(source_url)
            return FakeProc(b"abc123")

    ffmpeg = CountingFfmpeg()
    yt = FakeYtDlp()
    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=yt,
        ffmpeg_pipeline=ffmpeg,
        chunk_size=2,
        queue_poll_seconds=0.01,
    )
    engine._play_item(created.id)  # noqa: SLF001
    assert ffmpeg.sources == ["https://cdn.example.com/track.mp3"]
    assert yt.spawn_calls == 0


def test_playback_uses_prefetched_audio_file_when_available(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/prefetched-audio-playback.db")
    repo.init_db()
    created = repo.enqueue_items(
        [NewQueueItem(source_url="u", normalized_url="u", source_type="video", title="Song")]
    )
    dequeued = repo.dequeue_next()
    assert dequeued is not None

    class SourceAwareFfmpeg(FakeFfmpeg):
        def __init__(self) -> None:
            self.sources: list[str] = []

        def spawn_for_source(self, source_url: str, start_at_seconds: float = 0.0) -> FakeProc:
            _ = start_at_seconds
            self.sources.append(source_url)
            return FakeProc(b"abc123")

    yt = FakeYtDlp()
    ffmpeg = SourceAwareFfmpeg()
    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=yt,
        ffmpeg_pipeline=ffmpeg,
        chunk_size=2,
        queue_poll_seconds=0.01,
    )

    prefetched_path = tmp_path / "prefetched.bin"
    prefetched_path.write_bytes(b"prefetched-audio")
    engine._cache_prefetched_audio_path(created[0].id, str(prefetched_path))  # noqa: SLF001

    engine._play_item(created[0].id)  # noqa: SLF001 - playback path coverage

    assert ffmpeg.sources == [str(prefetched_path)]
    assert yt.spawn_calls == 0


def test_get_current_ffmpeg_input_prefers_prefetch_then_stream_url(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/ffmpeg_input.db")
    repo.init_db()
    created = repo.enqueue_items(
        [
            NewQueueItem(
                source_url="https://example.com/v",
                normalized_url="https://example.com/v",
                source_type="video",
                title="Song",
            )
        ]
    )[0]
    engine = StreamEngine(
        repository=repo,
        yt_dlp_service=FakeYtDlp(),
        ffmpeg_pipeline=FakeFfmpeg(),
        chunk_size=2,
        queue_poll_seconds=0.1,
    )
    pf = tmp_path / "pre.bin"
    pf.write_bytes(b"x")
    engine.state.now_playing_id = created.id
    engine._cache_resolved_track(  # noqa: SLF001
        created.id,
        ResolvedTrack(
            source_url=created.source_url,
            normalized_url=created.normalized_url or created.source_url,
            title="t",
            channel="c",
            duration_seconds=60,
            thumbnail_url=None,
            stream_url="http://media.remote/track",
        ),
    )
    engine._cache_prefetched_audio_path(created.id, str(pf))  # noqa: SLF001
    assert engine.get_current_stream_url() == "http://media.remote/track"
    assert engine.get_current_ffmpeg_input() == str(pf)

    engine._drop_prefetched_audio_path(created.id)  # noqa: SLF001
    assert engine.get_current_ffmpeg_input() == "http://media.remote/track"
