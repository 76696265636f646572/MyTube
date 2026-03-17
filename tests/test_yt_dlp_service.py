"""Tests for YtDlpService URL detection (no subprocess)."""

from dataclasses import dataclass, field
from unittest.mock import patch

import pytest
from urllib.parse import urlparse

from app.db.repository import Repository
from app.services.yt_dlp_service import cookie_setting_key
from app.services.yt_dlp_service import YtDlpService


@pytest.fixture
def service():
    return YtDlpService(binary_path="/bin/echo", deno_path="/bin/echo", ffmpeg_path="/bin/echo")


def test_is_playlist_url_playlist_page(service):
    assert service.is_playlist_url("https://www.youtube.com/playlist?list=PLxxx") is True
    assert service.is_playlist_url("https://youtube.com/playlist?list=ABC") is True


def test_is_playlist_url_watch_single_video(service):
    assert service.is_playlist_url("https://www.youtube.com/watch?v=Hjw86NcG8Bo") is False


def test_is_playlist_url_watch_with_list_param_treated_as_single_video(service):
    """watch?v=...&list=... without start_radio should queue/play only the video."""
    url = "https://www.youtube.com/watch?v=Hjw86NcG8Bo&list=PLMmqTuUsDkRIZ1C1T2AsVz5XIxtVDfSOe"
    assert service.is_playlist_url(url) is False


def test_is_start_radio_url(service):
    assert service.is_start_radio_url("https://www.youtube.com/watch?v=u6wOyMUs74I&list=RDu6wOyMUs74I&start_radio=1") is True
    assert service.is_start_radio_url("https://www.youtube.com/watch?v=HMUDVMiITOU&list=RDMMHMUDVMiITOU&start_radio=1") is True
    assert service.is_start_radio_url("https://www.youtube.com/watch?v=Hjw86NcG8Bo&list=PLxxx") is False
    assert service.is_start_radio_url("https://www.youtube.com/watch?v=Hjw86NcG8Bo") is False
    assert service.is_start_radio_url("https://www.youtube.com/playlist?list=PLxxx") is False


def test_is_playlist_url_start_radio(service):
    """watch?v=...&list=...&start_radio=1 should be treated as playlist for import/queue."""
    url = "https://www.youtube.com/watch?v=u6wOyMUs74I&list=RDu6wOyMUs74I&start_radio=1"
    assert service.is_playlist_url(url) is True


@dataclass
class _CaptureClient:
    resolved_values: list[tuple[str, str | None]] = field(default_factory=list)
    single_calls: list[tuple[str, str | None]] = field(default_factory=list)
    stream_calls: list[tuple[str, str | None]] = field(default_factory=list)
    spawn_calls: list[tuple[str, str | None]] = field(default_factory=list)
    search_calls: list[tuple[str, str, int, str | None]] = field(default_factory=list)
    playlist_calls: list[tuple[str, str | None]] = field(default_factory=list)

    def resolve_cookie_file(self, provider: str, value: str | None) -> str | None:
        self.resolved_values.append((provider, value))
        if value is None:
            return None
        return f"/tmp/{provider}.cookies"

    def get_single_json(self, url: str, cookie_file: str | None = None) -> dict[str, object]:
        self.single_calls.append((url, cookie_file))
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com"):
            return {
                "id": "abc",
                "title": "YouTube Track",
                "uploader": "YouTube Channel",
                "duration": 120,
                "thumbnail": "https://img.youtube.com/abc.jpg",
                "webpage_url": "https://www.youtube.com/watch?v=abc",
            }
        if host == "soundcloud.com" or host.endswith(".soundcloud.com"):
            return {
                "id": 11,
                "title": "SoundCloud Track",
                "uploader": "SoundCloud Artist",
                "duration": 240,
                "webpage_url": "https://soundcloud.com/artist/track",
            }
        return {
            "id": "55",
            "title": "Mixcloud Show",
            "uploader": "Mix DJ",
            "duration": 3600,
            "webpage_url": "https://www.mixcloud.com/user/show/",
        }

    def get_stream_url(self, url: str, cookie_file: str | None = None) -> str:
        self.stream_calls.append((url, cookie_file))
        return "https://stream.example/audio.mp3"

    def spawn_audio_stream(self, url: str, cookie_file: str | None = None):
        self.spawn_calls.append((url, cookie_file))
        return object()

    def search_json(
        self,
        query: str,
        provider: str,
        limit: int = 10,
        cookie_file: str | None = None,
    ) -> dict[str, object]:
        self.search_calls.append((query, provider, limit, cookie_file))
        return {"entries": []}

    def get_playlist_json(self, url: str, cookie_file: str | None = None) -> dict[str, object]:
        self.playlist_calls.append((url, cookie_file))
        if "feed/playlists" not in url:
            playlist_id = (url.split("list=")[-1].split("&")[0] or "PLXXX").strip()
            return {"entries": [{"id": f"{playlist_id}_VIDEO1"}]}
        return {
            "entries": [
                {
                    "id": "PL111",
                    "title": "Playlist One",
                    "channel": "Owner 1",
                    "thumbnail": "https://img.youtube.com/pl111.jpg",
                    "playlist_count": 12,
                    "url": "https://www.youtube.com/playlist?list=PL111",
                },
                {
                    "id": "PL222",
                    "title": "Playlist Two",
                    "uploader": "Owner 2",
                    "url": "https://www.youtube.com/playlist?list=PL222&feature=shared",
                },
            ]
        }


def test_service_applies_provider_specific_cookies(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/cookies.db")
    repo.init_db()
    repo.set_setting(cookie_setting_key("youtube"), "/tmp/youtube-source.txt")
    repo.set_setting(cookie_setting_key("soundcloud"), "/tmp/soundcloud-source.txt")
    repo.set_setting(cookie_setting_key("mixcloud"), "/tmp/mixcloud-source.txt")

    service = YtDlpService(
        binary_path="/bin/echo",
        deno_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        repository=repo,
    )
    capture_client = _CaptureClient()
    service.client = capture_client

    service.resolve_video("https://www.youtube.com/watch?v=abc")
    service.resolve_video("https://soundcloud.com/artist/track")
    service.spawn_audio_stream("https://www.mixcloud.com/user/show/")
    service.search(query="lofi", providers=["youtube", "soundcloud"], limit=3)

    assert ("youtube", "/tmp/youtube-source.txt") in capture_client.resolved_values
    assert ("soundcloud", "/tmp/soundcloud-source.txt") in capture_client.resolved_values
    assert ("mixcloud", "/tmp/mixcloud-source.txt") in capture_client.resolved_values
    assert ("https://www.youtube.com/watch?v=abc", "/tmp/youtube.cookies") in capture_client.single_calls
    assert ("https://soundcloud.com/artist/track", "/tmp/soundcloud.cookies") in capture_client.single_calls
    assert ("https://www.mixcloud.com/user/show/", "/tmp/mixcloud.cookies") in capture_client.spawn_calls
    assert ("lofi", "youtube", 3, "/tmp/youtube.cookies") in capture_client.search_calls
    assert ("lofi", "soundcloud", 3, "/tmp/soundcloud.cookies") in capture_client.search_calls


def test_list_youtube_user_playlists_uses_youtube_cookies(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/youtube_feed.db")
    repo.init_db()
    repo.set_setting(cookie_setting_key("youtube"), "/tmp/youtube-source.txt")

    service = YtDlpService(
        binary_path="/bin/echo",
        deno_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        repository=repo,
    )
    capture_client = _CaptureClient()
    service.client = capture_client

    playlists = service.list_youtube_user_playlists()

    assert ("https://www.youtube.com/feed/playlists", "/tmp/youtube.cookies") in capture_client.playlist_calls
    assert [p.provider_item_id for p in playlists] == ["PL111", "PL222"]
    assert playlists[0].source_url == "https://www.youtube.com/playlist?list=PL111"
    assert playlists[1].source_url == "https://www.youtube.com/playlist?list=PL222"
    assert playlists[0].thumbnail_url == "https://i.ytimg.com/vi/PL111_VIDEO1/hqdefault.jpg"
    assert playlists[1].thumbnail_url == "https://i.ytimg.com/vi/PL222_VIDEO1/hqdefault.jpg"


def test_list_youtube_user_playlists_without_cookie_returns_empty(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/youtube_feed_empty.db")
    repo.init_db()

    service = YtDlpService(
        binary_path="/bin/echo",
        deno_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        repository=repo,
    )
    capture_client = _CaptureClient()
    service.client = capture_client

    playlists = service.list_youtube_user_playlists()

    assert playlists == []
    assert capture_client.playlist_calls == []
