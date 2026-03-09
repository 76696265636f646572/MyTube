from __future__ import annotations

from types import SimpleNamespace

import app.services.sonos_service as sonos_module
from app.services.sonos_service import SonosService


def test_sonos_discovery_uses_soco_discover(monkeypatch):
    def fake_discover(timeout: int = 2):
        _ = timeout
        return [
            SimpleNamespace(ip_address="192.168.1.5", player_name="Office"),
            SimpleNamespace(ip_address="192.168.1.6", player_name="Kitchen"),
        ]

    monkeypatch.setattr(sonos_module, "discover", fake_discover)
    service = SonosService()
    speakers = service.discover_speakers()
    names = {s.name for s in speakers}
    assert names == {"Office", "Kitchen"}


def test_sonos_play_stream_calls_play_uri(monkeypatch):
    calls = {}

    class FakeSpeaker:
        def play_uri(self, stream_url: str, title: str):
            calls["stream_url"] = stream_url
            calls["title"] = title

    def fake_soco(ip: str):
        calls["ip"] = ip
        return FakeSpeaker()

    monkeypatch.setattr(sonos_module, "SoCo", fake_soco)
    service = SonosService()
    service.play_stream("192.168.1.20", "http://radio.local/stream/live.mp3")

    assert calls["ip"] == "192.168.1.20"
    assert calls["stream_url"].endswith("/stream/live.mp3")
    assert calls["title"] == "MyTube Radio"


def test_sonos_play_stream_uses_group_coordinator(monkeypatch):
    calls = {}

    class FakeCoordinator:
        def play_uri(self, stream_url: str, title: str):
            calls["stream_url"] = stream_url
            calls["title"] = title
            calls["target"] = "coordinator"

    class FakeSpeaker:
        def __init__(self):
            self.group = SimpleNamespace(coordinator=FakeCoordinator())

        def play_uri(self, stream_url: str, title: str):
            calls["stream_url"] = stream_url
            calls["title"] = title
            calls["target"] = "member"

    def fake_soco(ip: str):
        calls["ip"] = ip
        return FakeSpeaker()

    monkeypatch.setattr(sonos_module, "SoCo", fake_soco)
    service = SonosService()
    service.play_stream("192.168.1.21", "http://radio.local/stream/live.mp3")

    assert calls["ip"] == "192.168.1.21"
    assert calls["target"] == "coordinator"
    assert calls["stream_url"].endswith("/stream/live.mp3")
    assert calls["title"] == "MyTube Radio"
