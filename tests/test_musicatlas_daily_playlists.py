from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.models import QueueStatus
from app.db.repository import NewPlaylistEntry, NewQueueItem
from app.main import create_app
from app.services.musicatlas_playlist_service import (
    DAILY_MUSICATLAS_PLAYLISTS,
    DailyMusicAtlasPlaylistRunner,
    DailyMusicAtlasPlaylistService,
)
from app.services.yt_dlp_client import YtDlpError
from app.services.yt_dlp_service import ResolvedTrack


class _FakeMusicAtlasDailyClient:
    enabled = True

    def __init__(
        self,
        responses: list[dict[str, Any]],
        *,
        missing_catalog_tracks: set[tuple[str, str]] | None = None,
        add_track_results: dict[tuple[str, str], tuple[int, dict[str, Any]]] | None = None,
    ) -> None:
        self._responses = list(responses)
        self._last_response = self._responses[-1] if self._responses else {"success": True, "matches": []}
        self.missing_catalog_tracks = set(missing_catalog_tracks or set())
        self.add_track_results = dict(add_track_results or {})
        self.calls: list[list[dict[str, str]]] = []
        self.similar_tracks_calls: list[dict[str, str]] = []
        self.add_track_calls: list[dict[str, str]] = []
        self.add_track_progress_calls: list[str] = []

    def similar_tracks(self, *, artist: str, track: str, embed: int | None = None) -> dict[str, Any]:
        self.similar_tracks_calls.append({"artist": artist, "track": track})
        if (artist, track) in self.missing_catalog_tracks:
            return {"success": True, "matches": [], "message": "not in catalog"}
        return {
            "success": True,
            "matches": [{"artist": "Indexed Artist", "title": "Indexed Track", "platform_ids": {"youtube": "indexed001"}}],
        }

    def similar_tracks_multi(self, *, liked_tracks: list[dict[str, str]], disliked_tracks: list | None = None) -> dict[str, Any]:
        self.calls.append(list(liked_tracks))
        if not self._responses:
            return self._last_response
        response = self._responses.pop(0)
        self._last_response = response
        return response

    def add_track(self, *, artist: str, title: str) -> tuple[int, dict[str, Any]]:
        self.add_track_calls.append({"artist": artist, "title": title})
        self.missing_catalog_tracks.discard((artist, title))
        custom = self.add_track_results.get((artist, title))
        if custom is not None:
            return custom
        return (200, {"success": True, "job_id": f"job-{len(self.add_track_calls)}"})

    def add_track_progress(self, *, job_id: str) -> dict[str, Any]:
        self.add_track_progress_calls.append(job_id)
        return {"status": "done", "percent_complete": 100, "message": "ready"}


class _FakeRunnerService:
    def __init__(self) -> None:
        self.calls = 0

    def refresh_daily_playlists(self) -> None:
        self.calls += 1


class _FakeYtDlpService:
    def __init__(self, *, duration_seconds: int = 245) -> None:
        self.duration_seconds = duration_seconds
        self.calls: list[str] = []

    def resolve_video(self, url: str) -> ResolvedTrack:
        self.calls.append(url)
        return ResolvedTrack(
            source_url=url,
            normalized_url=url,
            title="Resolved Title",
            channel="Resolved Channel",
            duration_seconds=self.duration_seconds,
            thumbnail_url="https://img.example.com/resolved.jpg",
            stream_url="https://stream.example.com/audio",
            provider="youtube",
            provider_item_id=url.rsplit("=", 1)[-1],
        )


class _FailingFakeYtDlpService(_FakeYtDlpService):
    def __init__(self, failing_provider_item_ids: set[str], *, duration_seconds: int = 245) -> None:
        super().__init__(duration_seconds=duration_seconds)
        self.failing_provider_item_ids = set(failing_provider_item_ids)

    def resolve_video(self, url: str) -> ResolvedTrack:
        provider_item_id = url.rsplit("=", 1)[-1]
        if provider_item_id in self.failing_provider_item_ids:
            raise YtDlpError(f"metadata failed for {provider_item_id}")
        return super().resolve_video(url)


def _settings_for(tmp_path, name: str, *, musicatlas_api_key: str) -> Settings:
    return Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/{name}.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        musicatlas_api_key=musicatlas_api_key,
    )


def _daily_playlists(repo) -> list[Any]:
    return [playlist for playlist in repo.list_playlists() if str(getattr(playlist, "source_url", "")).startswith("custom://daily_")]


def _seed_history(repo, *, count: int = 8) -> None:
    for index in range(count):
        artist = f"Artist {index}"
        title = f"Song {index}"
        queued = repo.enqueue_items(
            [
                NewQueueItem(
                    source_url=f"https://example.com/watch/{index}",
                    normalized_url=f"https://example.com/watch/{index}",
                    source_type="video",
                    provider="youtube",
                    provider_item_id=f"seed_{index}",
                    title=f"{artist} - {title}",
                    channel=artist,
                    thumbnail_url=f"https://img.example.com/{index}.jpg",
                )
            ]
        )
        repo.mark_playback_finished(queued[0].id, QueueStatus.completed)


def _seed_duplicate_history(repo, *, artist: str, title: str, count: int = 2) -> None:
    for index in range(count):
        queued = repo.enqueue_items(
            [
                NewQueueItem(
                    source_url=f"https://example.com/dup/{index}",
                    normalized_url=f"https://example.com/dup/{index}",
                    source_type="video",
                    provider="youtube",
                    provider_item_id=f"dup_{index}",
                    title=f"{artist} - {title}",
                    channel=artist,
                    thumbnail_url=f"https://img.example.com/dup/{index}.jpg",
                )
            ]
        )
        repo.mark_playback_finished(queued[0].id, QueueStatus.completed)


def _matches(count: int, *, offset: int = 0) -> dict[str, Any]:
    return {
        "success": True,
        "matches": [
            {
                "artist": f"Match Artist {offset + idx}",
                "title": f"Match Song {offset + idx}",
                "platform_ids": {"youtube": f"yt{offset + idx:03d}"},
            }
            for idx in range(count)
        ],
    }


def test_daily_playlists_seeded_once_when_enabled(tmp_path) -> None:
    app = create_app(settings=_settings_for(tmp_path, "musicatlas_daily_enabled", musicatlas_api_key="k"), start_engine=False)

    with TestClient(app):
        repo = app.state.repository
        daily_playlists = _daily_playlists(repo)
        assert len(daily_playlists) == len(DAILY_MUSICATLAS_PLAYLISTS)
        assert {playlist.source_url for playlist in daily_playlists} == {
            definition.source_url for definition in DAILY_MUSICATLAS_PLAYLISTS
        }
        assert all(playlist.can_edit is False for playlist in daily_playlists)
        assert all(playlist.can_delete is False for playlist in daily_playlists)
        assert all(playlist.sync_enabled is False for playlist in daily_playlists)

        app.state.daily_musicatlas_playlist_service.ensure_daily_playlists()
        assert len(_daily_playlists(repo)) == len(DAILY_MUSICATLAS_PLAYLISTS)


def test_daily_playlists_not_seeded_when_musicatlas_disabled(tmp_path) -> None:
    app = create_app(settings=_settings_for(tmp_path, "musicatlas_daily_disabled", musicatlas_api_key=""), start_engine=False)

    with TestClient(app):
        assert _daily_playlists(app.state.repository) == []


def test_history_rows_default_musicatlas_submitted_false(tmp_path) -> None:
    app = create_app(settings=_settings_for(tmp_path, "musicatlas_history_default", musicatlas_api_key="k"), start_engine=False)

    with TestClient(app):
        repo = app.state.repository
        _seed_history(repo, count=3)
        history = repo.list_history(limit=10)
        assert len(history) == 3
        assert all(row.musicatlas_submitted is False for row in history)


def test_daily_playlist_refresh_replaces_entries_on_success(tmp_path) -> None:
    app = create_app(settings=_settings_for(tmp_path, "musicatlas_daily_refresh", musicatlas_api_key="k"), start_engine=False)

    with TestClient(app):
        repo = app.state.repository
        _seed_history(repo, count=8)
        app.state.stream_engine.state.now_playing_channel = "Now Artist"
        app.state.stream_engine.state.now_playing_title = "Now Artist - Now Song"
        fake_client = _FakeMusicAtlasDailyClient(
            [_matches(2, offset=idx * 10) for idx in range(len(DAILY_MUSICATLAS_PLAYLISTS))]
        )
        fake_yt_dlp = _FakeYtDlpService(duration_seconds=222)
        service = DailyMusicAtlasPlaylistService(
            repository=repo,
            stream_engine=app.state.stream_engine,
            musicatlas_client=fake_client,
            yt_dlp_service=fake_yt_dlp,
            track_count=2,
        )

        results = service.refresh_daily_playlists()

        assert len(fake_client.calls) == len(DAILY_MUSICATLAS_PLAYLISTS)
        assert all(result.entries_replaced == 2 for result in results)
        assert all(result.skipped_reason is None for result in results)
        for definition in DAILY_MUSICATLAS_PLAYLISTS:
            playlist = repo.get_playlist_by_source_url(definition.source_url)
            assert playlist is not None
            entries = repo.list_playlist_entries(playlist.id)
            assert len(entries) == 2
            assert all(entry.provider == "youtube" for entry in entries)
            assert all(entry.duration_seconds == 222 for entry in entries)
        assert fake_yt_dlp.calls


def test_daily_playlist_refresh_marks_all_matching_history_rows_submitted(tmp_path) -> None:
    app = create_app(settings=_settings_for(tmp_path, "musicatlas_history_mark_all", musicatlas_api_key="k"), start_engine=False)

    with TestClient(app):
        repo = app.state.repository
        _seed_duplicate_history(repo, artist="Shared Artist", title="Shared Song", count=2)
        fake_client = _FakeMusicAtlasDailyClient(
            [_matches(2, offset=idx * 10) for idx in range(len(DAILY_MUSICATLAS_PLAYLISTS))],
            missing_catalog_tracks={("Shared Artist", "Shared Song")},
        )
        service = DailyMusicAtlasPlaylistService(
            repository=repo,
            stream_engine=app.state.stream_engine,
            musicatlas_client=fake_client,
            yt_dlp_service=_FakeYtDlpService(duration_seconds=180),
            track_count=2,
        )

        service.refresh_daily_playlists()

        history = repo.list_history(limit=10)
        matching = [row for row in history if row.title == "Shared Artist - Shared Song"]
        assert len(matching) == 2
        assert all(row.musicatlas_submitted is True for row in matching)
        assert fake_client.add_track_calls == [{"artist": "Shared Artist", "title": "Shared Song"}]


def test_daily_playlist_refresh_skips_already_submitted_history_rows(tmp_path) -> None:
    app = create_app(settings=_settings_for(tmp_path, "musicatlas_history_idempotent", musicatlas_api_key="k"), start_engine=False)

    with TestClient(app):
        repo = app.state.repository
        _seed_duplicate_history(repo, artist="Shared Artist", title="Shared Song", count=2)
        history = repo.list_history(limit=10)
        matching_ids = [row.id for row in history if row.title == "Shared Artist - Shared Song"]
        repo.mark_history_rows_musicatlas_submitted(matching_ids)

        fake_client = _FakeMusicAtlasDailyClient(
            [_matches(2, offset=idx * 10) for idx in range(len(DAILY_MUSICATLAS_PLAYLISTS))],
            missing_catalog_tracks={("Shared Artist", "Shared Song")},
        )
        service = DailyMusicAtlasPlaylistService(
            repository=repo,
            stream_engine=app.state.stream_engine,
            musicatlas_client=fake_client,
            yt_dlp_service=_FakeYtDlpService(duration_seconds=180),
            track_count=2,
        )

        service.refresh_daily_playlists()

        assert fake_client.add_track_calls == []


def test_daily_playlist_refresh_marks_history_on_conflict(tmp_path) -> None:
    app = create_app(settings=_settings_for(tmp_path, "musicatlas_history_conflict", musicatlas_api_key="k"), start_engine=False)

    with TestClient(app):
        repo = app.state.repository
        _seed_duplicate_history(repo, artist="Shared Artist", title="Shared Song", count=2)
        fake_client = _FakeMusicAtlasDailyClient(
            [_matches(2, offset=idx * 10) for idx in range(len(DAILY_MUSICATLAS_PLAYLISTS))],
            missing_catalog_tracks={("Shared Artist", "Shared Song")},
            add_track_results={("Shared Artist", "Shared Song"): (409, {"message": "already exists"})},
        )
        service = DailyMusicAtlasPlaylistService(
            repository=repo,
            stream_engine=app.state.stream_engine,
            musicatlas_client=fake_client,
            yt_dlp_service=_FakeYtDlpService(duration_seconds=180),
            track_count=2,
        )

        service.refresh_daily_playlists()

        history = repo.list_history(limit=10)
        matching = [row for row in history if row.title == "Shared Artist - Shared Song"]
        assert len(matching) == 2
        assert all(row.musicatlas_submitted is True for row in matching)
        assert fake_client.add_track_progress_calls == []


def test_daily_playlist_refresh_continues_when_add_track_has_no_job_id(tmp_path) -> None:
    app = create_app(settings=_settings_for(tmp_path, "musicatlas_daily_missing_job_id", musicatlas_api_key="k"), start_engine=False)

    with TestClient(app):
        repo = app.state.repository
        _seed_duplicate_history(repo, artist="Shared Artist", title="Shared Song", count=2)
        fake_client = _FakeMusicAtlasDailyClient(
            [_matches(2, offset=idx * 10) for idx in range(len(DAILY_MUSICATLAS_PLAYLISTS))],
            missing_catalog_tracks={("Shared Artist", "Shared Song")},
            add_track_results={
                ("Shared Artist", "Shared Song"): (200, {"success": True, "message": "accepted without job id"})
            },
        )
        service = DailyMusicAtlasPlaylistService(
            repository=repo,
            stream_engine=app.state.stream_engine,
            musicatlas_client=fake_client,
            yt_dlp_service=_FakeYtDlpService(duration_seconds=180),
            track_count=2,
        )

        results = service.refresh_daily_playlists()

        history = repo.list_history(limit=10)
        matching = [row for row in history if row.title == "Shared Artist - Shared Song"]
        assert all(row.musicatlas_submitted is True for row in matching)
        assert fake_client.add_track_calls == [{"artist": "Shared Artist", "title": "Shared Song"}]
        assert fake_client.add_track_progress_calls == []
        assert all(result.skipped_reason is None for result in results)


def test_daily_playlist_refresh_skips_unresolved_metadata_and_continues(tmp_path) -> None:
    app = create_app(settings=_settings_for(tmp_path, "musicatlas_daily_skip_bad_meta", musicatlas_api_key="k"), start_engine=False)

    with TestClient(app):
        repo = app.state.repository
        _seed_history(repo, count=10)
        app.state.stream_engine.state.now_playing_channel = "Now Artist"
        app.state.stream_engine.state.now_playing_title = "Now Artist - Now Song"
        fake_client = _FakeMusicAtlasDailyClient(
            [
                _matches(2, offset=0),
                _matches(2, offset=10),
                _matches(2, offset=20),
                _matches(2, offset=30),
                _matches(2, offset=40),
                _matches(2, offset=50),
            ]
        )
        service = DailyMusicAtlasPlaylistService(
            repository=repo,
            stream_engine=app.state.stream_engine,
            musicatlas_client=fake_client,
            yt_dlp_service=_FailingFakeYtDlpService({"yt000"}, duration_seconds=333),
            track_count=2,
        )

        results = service.refresh_daily_playlists()

        first_result = next(result for result in results if result.source_url == "custom://daily_1")
        assert first_result.entries_replaced == 2
        assert first_result.skipped_reason is None
        first_playlist = repo.get_playlist_by_source_url("custom://daily_1")
        assert first_playlist is not None
        entries = repo.list_playlist_entries(first_playlist.id)
        assert [entry.provider_item_id for entry in entries] == ["yt001", "yt010"]
        assert all(entry.duration_seconds == 333 for entry in entries)


def test_daily_playlist_refresh_keeps_existing_entries_on_insufficient_matches(tmp_path) -> None:
    app = create_app(settings=_settings_for(tmp_path, "musicatlas_daily_failure", musicatlas_api_key="k"), start_engine=False)

    with TestClient(app):
        repo = app.state.repository
        _seed_history(repo, count=6)
        service = DailyMusicAtlasPlaylistService(
            repository=repo,
            stream_engine=app.state.stream_engine,
            musicatlas_client=_FakeMusicAtlasDailyClient([_matches(1, offset=0) for _ in range(5)]),
            track_count=2,
        )
        playlists = service.ensure_daily_playlists()
        first_playlist = playlists[0]
        repo.replace_playlist_entries(
            first_playlist.id,
            [
                NewPlaylistEntry(
                    source_url="https://www.youtube.com/watch?v=existing001",
                    normalized_url="https://www.youtube.com/watch?v=existing001",
                    provider="youtube",
                    provider_item_id="existing001",
                    upstream_item_id="youtube:existing001",
                    title="Existing Song",
                    channel="Existing Artist",
                ),
                NewPlaylistEntry(
                    source_url="https://www.youtube.com/watch?v=existing002",
                    normalized_url="https://www.youtube.com/watch?v=existing002",
                    provider="youtube",
                    provider_item_id="existing002",
                    upstream_item_id="youtube:existing002",
                    title="Existing Song 2",
                    channel="Existing Artist",
                ),
            ],
        )

        results = service.refresh_daily_playlists()

        first_result = next(result for result in results if result.source_url == "custom://daily_1")
        assert first_result.skipped_reason == "insufficient_matches"


def test_daily_playlist_runner_helpers() -> None:
    fake_service = _FakeRunnerService()
    runner = DailyMusicAtlasPlaylistRunner(service=fake_service, enabled=False)
    asyncio.run(runner.run_forever())
    assert fake_service.calls == 0

    enabled_runner = DailyMusicAtlasPlaylistRunner(service=fake_service, enabled=True)
    local_tz = datetime.now().astimezone().tzinfo or timezone.utc
    seconds = enabled_runner.seconds_until_next_run(datetime(2026, 4, 14, 23, 59, 30, tzinfo=local_tz))
    assert seconds == 30.0
