from __future__ import annotations

from app.services.yt_dlp_client import YtDlpClient


def _client() -> YtDlpClient:
    return YtDlpClient(binary_path="/bin/echo", ffmpeg_path="/bin/echo", deno_path="/bin/echo")


def test_resolve_cookie_file_uses_direct_path():
    client = _client()
    resolved = client.resolve_cookie_file("youtube", "~/cookies.txt")
    assert resolved is not None
    assert resolved.endswith("/cookies.txt")


def test_resolve_cookie_file_caches_netscape_content():
    client = _client()
    content = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tFALSE\t0\tSID\tabc"

    first = client.resolve_cookie_file("youtube", content)
    second = client.resolve_cookie_file("youtube", content)
    assert first is not None
    assert second == first


def test_get_single_json_passes_cookies_flag(monkeypatch):
    captured: dict[str, list[str]] = {}

    class FakePipe:
        def __init__(self, lines: list[str]):
            self._lines = list(lines)

        def readline(self) -> str:
            if self._lines:
                return self._lines.pop(0)
            return ""

        def close(self) -> None:
            return None

    class FakePopen:
        def __init__(self, cmd, **_kwargs):
            captured["cmd"] = cmd
            self.returncode = 0
            self.stdout = FakePipe(['{"id":"abc"}\n'])
            self.stderr = FakePipe([])

        def wait(self):
            return 0

    monkeypatch.setattr("app.services.yt_dlp_client.subprocess.Popen", FakePopen)
    client = _client()
    payload = client.get_single_json("https://www.youtube.com/watch?v=abc", cookie_file="/tmp/youtube.cookies")
    assert payload["id"] == "abc"
    assert "--cookies" in captured["cmd"]
    assert "/tmp/youtube.cookies" in captured["cmd"]


def test_search_json_passes_cookies_flag_for_soundcloud(monkeypatch):
    captured: dict[str, list[str]] = {}

    class FakePipe:
        def __init__(self, lines: list[str]):
            self._lines = list(lines)

        def readline(self) -> str:
            if self._lines:
                return self._lines.pop(0)
            return ""

        def close(self) -> None:
            return None

    class FakePopen:
        def __init__(self, cmd, **_kwargs):
            captured["cmd"] = cmd
            self.returncode = 0
            self.stdout = FakePipe(['{"entries":[]}\n'])
            self.stderr = FakePipe([])

        def wait(self):
            return 0

    monkeypatch.setattr("app.services.yt_dlp_client.subprocess.Popen", FakePopen)

    client = _client()
    payload = client.search_json(
        query="house",
        provider="soundcloud",
        limit=5,
        cookie_file="/tmp/soundcloud.cookies",
    )
    assert payload["entries"] == []
    assert "--cookies" in captured["cmd"]
    assert "/tmp/soundcloud.cookies" in captured["cmd"]
