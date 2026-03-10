from __future__ import annotations

import uuid
from dataclasses import dataclass
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.models import QueueStatus
from app.db.repository import NewQueueItem
from app.main import create_app


TEST_PLAYLIST_UUID = uuid.UUID("aaaaaaaa-bbbb-4ccc-8000-000000000010")
TEST_ENTRY_ID = 501


@dataclass
class FakePlaylistService:
    next_playlist_id: int = 100
    queue_replace_requested: bool = False

    def add_url(self, url: str) -> dict:
        return {"type": "video", "count": 1, "title": f"added:{url}", "item_ids": [1]}

    def preview_playlist(self, url: str):
        return SimpleNamespace(
            source_url=url,
            title="preview",
            channel="chan",
            thumbnail_url="https://img.youtube.com/pl-preview.jpg",
            entries=[{"id": "1"}, {"id": "2"}],
        )

    def import_playlist(self, url: str) -> dict:
        return {"type": "playlist", "count": 2, "title": f"imported:{url}", "playlist_id": TEST_PLAYLIST_UUID, "item_ids": [2, 3]}

    def list_playlists(self):
        return [
            {
                "id": TEST_PLAYLIST_UUID,
                "title": "Imported Playlist",
                "channel": "chan",
                "source_url": "https://www.youtube.com/playlist?list=pl",
                "thumbnail_url": "https://img.youtube.com/pl.jpg",
                "entry_count": 2,
                "kind": "imported",
            }
        ]

    def create_custom_playlist(self, title: str) -> dict:
        self.next_playlist_id += 1
        custom_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"custom-{self.next_playlist_id}")
        return {
            "id": custom_id,
            "title": title,
            "channel": "Custom",
            "source_url": f"custom://{custom_id}",
            "thumbnail_url": None,
            "entry_count": 0,
            "kind": "custom",
        }

    def list_playlist_entries(self, playlist_id: uuid.UUID):
        _ = playlist_id
        return [
            {
                "id": TEST_ENTRY_ID,
                "playlist_id": TEST_PLAYLIST_UUID,
                "source_url": "https://youtube.com/watch?v=1",
                "normalized_url": "https://youtube.com/watch?v=1",
                "title": "Track 1",
                "channel": "chan",
                "duration_seconds": 60,
                "thumbnail_url": None,
                "position": 1,
            }
        ]

    def add_item_to_playlist(self, playlist_id: uuid.UUID, url: str) -> dict:
        if playlist_id != TEST_PLAYLIST_UUID:
            raise ValueError("Playlist not found")
        return {
            "id": 502,
            "playlist_id": playlist_id,
            "title": f"added:{url}",
            "source_url": url,
            "position": 2,
        }

    def queue_playlist(self, playlist_id: uuid.UUID, *, replace: bool = False) -> dict:
        self.queue_replace_requested = replace
        if playlist_id != TEST_PLAYLIST_UUID:
            return {"ok": True, "count": 0, "item_ids": []}
        return {"ok": True, "count": 2, "item_ids": [11, 12]}

    def queue_playlist_entry(self, entry_id: int) -> dict:
        if entry_id != TEST_ENTRY_ID:
            raise ValueError("Playlist entry not found")
        return {"ok": True, "count": 1, "item_ids": [13]}

    def delete_playlist(self, playlist_id: uuid.UUID) -> None:
        if playlist_id != TEST_PLAYLIST_UUID:
            raise ValueError("Playlist not found")


@dataclass
class FakeEngine:
    def __post_init__(self):
        self.state = SimpleNamespace(
            mode=SimpleNamespace(value="idle"),
            paused=False,
            repeat_mode=SimpleNamespace(value="off"),
            shuffle_enabled=False,
            now_playing_id=None,
            now_playing_title=None,
            now_playing_duration_seconds=None,
        )
        self.skipped = False

    def skip_current(self) -> None:
        self.skipped = True

    def play_previous_or_restart(self) -> str:
        return "noop"

    def toggle_pause(self) -> bool:
        self.state.paused = not self.state.paused
        return self.state.paused

    def set_repeat_mode(self, mode: str) -> str:
        self.state.repeat_mode = SimpleNamespace(value=mode)
        return mode

    def set_shuffle_enabled(self, enabled: bool) -> bool:
        self.state.shuffle_enabled = enabled
        return enabled

    def seek_to_percent(self, percent: float) -> bool:
        _ = percent
        return True

    def subscribe(self):
        def _gen():
            yield b"chunk-1"
            yield b"chunk-2"

        return _gen()

    def playback_progress(self) -> dict:
        return {
            "duration_seconds": None,
            "started_at": None,
            "elapsed_seconds": None,
            "progress_percent": None,
        }


@dataclass
class FakeSonosService:
    def discover_speakers(self, timeout: int = 2):
        _ = timeout
        return [
            SimpleNamespace(
                ip="192.168.1.10",
                name="Living Room",
                uid="RINCON_123",
                coordinator_uid="RINCON_123",
                group_member_uids=["RINCON_123", "RINCON_456"],
                volume=25,
                is_coordinator=True,
            )
        ]

    def play_stream(self, speaker_ip: str, stream_url: str) -> None:
        self.last_play = (speaker_ip, stream_url)

    def group_speaker(self, coordinator_ip: str, member_ip: str) -> None:
        self.last_group = (coordinator_ip, member_ip)

    def ungroup_speaker(self, speaker_ip: str) -> None:
        self.last_ungroup = speaker_ip

    def set_volume(self, speaker_ip: str, volume: int) -> None:
        self.last_volume = (speaker_ip, volume)


@dataclass
class FakeYtDlpService:
    def search_videos(self, query: str, limit: int = 10):
        _ = limit
        return [
            {
                "id": "v1",
                "source_url": "https://www.youtube.com/watch?v=v1",
                "normalized_url": "https://www.youtube.com/watch?v=v1",
                "title": f"{query} result",
                "channel": "chan",
                "duration_seconds": 120,
                "thumbnail_url": None,
            }
        ]


def _build_test_client(tmp_path):
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/extended.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
    )
    app = create_app(settings=settings, start_engine=False)
    client = TestClient(app)
    return client, app


def test_browser_root_and_static_assets(tmp_path):
    client, _app = _build_test_client(tmp_path)
    with client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert '<div id="app"' in resp.text
        assert "/static/dist/app.css" in resp.text
        assert "/static/dist/app.js" in resp.text

        css = client.get("/static/dist/app.css")
        assert css.status_code == 200
        assert len(css.text) > 0

        js = client.get("/static/dist/app.js")
        assert js.status_code == 200
        assert len(js.text) > 0


def test_browser_root_uses_fallback_assets_when_frontend_is_not_built(tmp_path, monkeypatch):
    empty_dist_dir = tmp_path / "missing-dist"
    empty_dist_dir.mkdir()
    monkeypatch.setattr("app.main.FRONTEND_DIST_DIR", empty_dist_dir)

    client, _app = _build_test_client(tmp_path)
    with client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "/static/dist/app.css" in resp.text
        assert "/static/dist/app.js" in resp.text

        css = client.get("/static/dist/app.css")
        assert css.status_code == 200
        assert "Frontend bundle not built" in css.text

        js = client.get("/static/dist/app.js")
        assert js.status_code == 200
        assert "Frontend assets are not built." in js.text


def test_browser_client_routes_use_html_shell(tmp_path):
    client, _app = _build_test_client(tmp_path)
    with client:
        search = client.get("/search?q=daft+punk")
        assert search.status_code == 200
        assert '<div id="app"' in search.text
        assert "/static/dist/app.js" in search.text

        nested = client.get("/search/results")
        assert nested.status_code == 200
        assert '<div id="app"' in nested.text

        asset_like = client.get("/missing.json")
        assert asset_like.status_code == 404

        api_unknown = client.get("/api/unknown")
        assert api_unknown.status_code == 404

        queue_as_spa = client.get("/queue")
        assert queue_as_spa.status_code == 200
        assert '<div id="app"' in queue_as_spa.text


def test_queue_playlist_and_history_endpoints(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        app.state.playlist_service = FakePlaylistService()
        app.state.stream_engine = FakeEngine()

        add = client.post("/api/queue/add", json={"url": "https://www.youtube.com/watch?v=abc"})
        assert add.status_code == 200
        assert add.json()["ok"] is True

        preview = client.post("/api/playlist/preview", json={"url": "https://www.youtube.com/playlist?list=pl"})
        assert preview.status_code == 200
        assert preview.json()["count"] == 2
        assert preview.json()["thumbnail_url"] == "https://img.youtube.com/pl-preview.jpg"

        imported = client.post("/api/playlist/import", json={"url": "https://www.youtube.com/playlist?list=pl"})
        assert imported.status_code == 200
        assert imported.json()["ok"] is True

        queue_resp = client.get("/api/queue")
        assert queue_resp.status_code == 200
        assert isinstance(queue_resp.json(), list)

        history_resp = client.get("/api/history")
        assert history_resp.status_code == 200
        assert isinstance(history_resp.json(), list)


def test_clear_queue_endpoint_removes_all_visible_queue_items(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        fake_engine = FakeEngine()
        app.state.stream_engine = fake_engine
        app.state.repository.enqueue_items(
            [
                NewQueueItem(
                    source_url="https://www.youtube.com/watch?v=abc",
                    normalized_url="https://www.youtube.com/watch?v=abc",
                    source_type="video",
                    title="Track A",
                ),
                NewQueueItem(
                    source_url="https://www.youtube.com/watch?v=def",
                    normalized_url="https://www.youtube.com/watch?v=def",
                    source_type="video",
                    title="Track B",
                ),
            ]
        )
        current = app.state.repository.dequeue_next()

        assert current is not None

        cleared = client.delete("/api/queue")
        assert cleared.status_code == 200
        assert cleared.json()["ok"] is True
        assert fake_engine.skipped is True

        queue_resp = client.get("/api/queue")
        assert queue_resp.status_code == 200
        assert queue_resp.json() == []


def test_history_endpoint_includes_thumbnail_metadata(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        created = app.state.repository.enqueue_items(
            [
                NewQueueItem(
                    source_url="https://www.youtube.com/watch?v=abc123",
                    normalized_url="https://www.youtube.com/watch?v=abc123",
                    source_type="video",
                    title="Song",
                    thumbnail_url="https://i.ytimg.com/vi/abc123/hqdefault.jpg",
                )
            ]
        )
        item = app.state.repository.dequeue_next()
        assert item is not None

        app.state.repository.mark_playback_finished(created[0].id, QueueStatus.completed)

        history_resp = client.get("/api/history")

        assert history_resp.status_code == 200
        payload = history_resp.json()
        assert payload[0]["video_id"] == "abc123"
        assert payload[0]["thumbnail_url"] == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"


def test_play_now_endpoint_triggers_skip(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        fake_engine = FakeEngine()
        app.state.playlist_service = FakePlaylistService()
        app.state.stream_engine = fake_engine

        play_now = client.post("/api/queue/play-now", json={"url": "https://www.youtube.com/watch?v=abc"})
        assert play_now.status_code == 200
        payload = play_now.json()
        assert payload["ok"] is True
        assert payload["item_ids"] == [1]
        assert fake_engine.skipped is True


def test_play_now_playlist_url_replaces_queue(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        fake_engine = FakeEngine()
        fake_playlist = FakePlaylistService()
        app.state.playlist_service = fake_playlist
        app.state.stream_engine = fake_engine
        app.state.yt_dlp_service = SimpleNamespace(is_playlist_url=lambda url: "playlist" in url)

        play_now = client.post("/api/queue/play-now", json={"url": "https://www.youtube.com/playlist?list=abc"})
        assert play_now.status_code == 200
        payload = play_now.json()
        assert payload["ok"] is True
        assert payload["type"] == "playlist"
        assert payload["item_ids"] == [11, 12]
        assert fake_playlist.queue_replace_requested is True
        assert fake_engine.skipped is True


def test_playback_control_endpoints(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        fake_engine = FakeEngine()
        app.state.stream_engine = fake_engine

        previous = client.post("/api/playback/previous")
        assert previous.status_code == 200
        assert previous.json()["ok"] is True

        pause = client.post("/api/playback/toggle-pause")
        assert pause.status_code == 200
        assert pause.json()["ok"] is True
        assert pause.json()["paused"] is True

        repeat = client.post("/api/playback/repeat", json={"mode": "all"})
        assert repeat.status_code == 200
        assert repeat.json()["mode"] == "all"

        shuffle = client.post("/api/playback/shuffle", json={"enabled": True})
        assert shuffle.status_code == 200
        assert shuffle.json()["enabled"] is True

        seek = client.post("/api/playback/seek", json={"percent": 50})
        assert seek.status_code == 200
        assert seek.json()["ok"] is True


def test_playlist_library_endpoints(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        app.state.playlist_service = FakePlaylistService()

        playlists = client.get("/api/playlists")
        assert playlists.status_code == 200
        listed = playlists.json()
        assert len(listed) == 1
        assert listed[0]["id"] == str(TEST_PLAYLIST_UUID)
        assert listed[0]["thumbnail_url"] == "https://img.youtube.com/pl.jpg"

        fetched = client.get(f"/api/playlists/{TEST_PLAYLIST_UUID}")
        assert fetched.status_code == 200
        assert fetched.json()["title"] == "Imported Playlist"

        missing_playlist = client.get("/api/playlists/00000000-0000-0000-0000-000000000001")
        assert missing_playlist.status_code == 404

        created = client.post("/api/playlists/custom", json={"title": "My Mix"})
        assert created.status_code == 200
        assert created.json()["title"] == "My Mix"
        assert created.json()["kind"] == "custom"

        entries = client.get(f"/api/playlists/{TEST_PLAYLIST_UUID}/entries")
        assert entries.status_code == 200
        assert entries.json()[0]["id"] == TEST_ENTRY_ID

        added = client.post(f"/api/playlists/{TEST_PLAYLIST_UUID}/entries", json={"url": "https://www.youtube.com/watch?v=z"})
        assert added.status_code == 200
        assert added.json()["playlist_id"] == str(TEST_PLAYLIST_UUID)

        missing_add = client.post("/api/playlists/00000000-0000-0000-0000-000000000001/entries", json={"url": "https://www.youtube.com/watch?v=z"})
        assert missing_add.status_code == 404

        queued_playlist = client.post(f"/api/playlists/{TEST_PLAYLIST_UUID}/queue")
        assert queued_playlist.status_code == 200
        assert queued_playlist.json()["count"] == 2

        queued_entry = client.post("/api/playlists/entries/501/queue")
        assert queued_entry.status_code == 200
        assert queued_entry.json()["count"] == 1

        missing_entry_queue = client.post("/api/playlists/entries/999/queue")
        assert missing_entry_queue.status_code == 404

        deleted = client.delete(f"/api/playlists/{TEST_PLAYLIST_UUID}")
        assert deleted.status_code == 200
        assert deleted.json() == {"ok": True}

        missing_delete = client.delete("/api/playlists/00000000-0000-0000-0000-000000000001")
        assert missing_delete.status_code == 404


def test_search_endpoint(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        app.state.yt_dlp_service = FakeYtDlpService()

        search = client.get("/api/search/youtube?q=lofi&limit=5")
        assert search.status_code == 200
        payload = search.json()
        assert payload["query"] == "lofi"
        assert payload["count"] == 1
        assert payload["results"][0]["id"] == "v1"


def test_stream_endpoint_returns_bytes_without_hanging(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        app.state.stream_engine = FakeEngine()
        with client.stream("GET", "/stream/live.mp3") as resp:
            assert resp.status_code == 200
            iterator = resp.iter_bytes()
            first = next(iterator)
            assert first.startswith(b"chunk-")


def test_sonos_endpoints(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        fake_sonos = FakeSonosService()
        app.state.sonos_service = fake_sonos

        speakers = client.get("/api/sonos/speakers")
        assert speakers.status_code == 200
        payload = speakers.json()
        assert len(payload) == 1
        assert payload[0]["name"] == "Living Room"
        assert payload[0]["uid"] == "RINCON_123"
        assert payload[0]["group_member_uids"] == ["RINCON_123", "RINCON_456"]
        assert payload[0]["is_coordinator"] is True

        play = client.post("/api/sonos/play", json={"speaker_ip": "192.168.1.10"})
        assert play.status_code == 200
        assert play.json()["ok"] is True
        assert fake_sonos.last_play[0] == "192.168.1.10"
        assert fake_sonos.last_play[1].endswith("/stream/live.mp3")

        group = client.post("/api/sonos/group", json={"coordinator_ip": "192.168.1.10", "member_ip": "192.168.1.11"})
        assert group.status_code == 200
        assert group.json()["ok"] is True
        assert fake_sonos.last_group == ("192.168.1.10", "192.168.1.11")

        ungroup = client.post("/api/sonos/ungroup", json={"speaker_ip": "192.168.1.11"})
        assert ungroup.status_code == 200
        assert ungroup.json()["ok"] is True
        assert fake_sonos.last_ungroup == "192.168.1.11"

        volume = client.post("/api/sonos/volume", json={"speaker_ip": "192.168.1.10", "volume": 33})
        assert volume.status_code == 200
        assert volume.json()["ok"] is True
        assert fake_sonos.last_volume == ("192.168.1.10", 33)


def test_websocket_events_send_initial_snapshot_and_updates(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        created = app.state.repository.enqueue_items(
            [
                NewQueueItem(
                    source_url="https://youtube.com/watch?v=track1",
                    normalized_url="https://youtube.com/watch?v=track1",
                    source_type="video",
                    title="Track 1",
                    channel="chan",
                )
            ]
        )[0]

        with client.websocket_connect("/api/ws/events") as ws:
            initial = ws.receive_json()
            assert initial["type"] == "snapshot"
            assert any(item["id"] == created.id for item in initial["queue"])

            removed = client.delete(f"/api/queue/{created.id}")
            assert removed.status_code == 200
            assert removed.json()["ok"] is True

            updated = ws.receive_json()
            assert updated["type"] == "snapshot"
            assert all(item["id"] != created.id for item in updated["queue"])


def test_websocket_snapshot_serializes_history_datetimes(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        created = app.state.repository.enqueue_items(
            [
                NewQueueItem(
                    source_url="https://youtube.com/watch?v=history1",
                    normalized_url="https://youtube.com/watch?v=history1",
                    source_type="video",
                    title="History Track",
                    channel="chan",
                )
            ]
        )[0]
        app.state.repository.mark_playback_finished(created.id, status=QueueStatus.completed)

        with client.websocket_connect("/api/ws/events") as ws:
            payload = ws.receive_json()
            assert payload["type"] == "snapshot"
            assert isinstance(payload["history"], list)
            assert payload["history"], "Expected at least one history entry in websocket snapshot"

            entry = payload["history"][0]
            assert isinstance(entry["started_at"], str)
            assert isinstance(entry["finished_at"], str)


def test_websocket_updates_are_broadcast_to_all_connected_clients(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        created = app.state.repository.enqueue_items(
            [
                NewQueueItem(
                    source_url="https://youtube.com/watch?v=broadcast1",
                    normalized_url="https://youtube.com/watch?v=broadcast1",
                    source_type="video",
                    title="Broadcast Track",
                    channel="chan",
                )
            ]
        )[0]

        with client.websocket_connect("/api/ws/events") as ws_a, client.websocket_connect("/api/ws/events") as ws_b:
            initial_a = ws_a.receive_json()
            initial_b = ws_b.receive_json()
            assert initial_a["type"] == "snapshot"
            assert initial_b["type"] == "snapshot"

            removed = client.delete(f"/api/queue/{created.id}")
            assert removed.status_code == 200
            assert removed.json()["ok"] is True

            update_a = ws_a.receive_json()
            update_b = ws_b.receive_json()
            assert update_a["type"] == "snapshot"
            assert update_b["type"] == "snapshot"
            assert all(item["id"] != created.id for item in update_a["queue"])
            assert all(item["id"] != created.id for item in update_b["queue"])
