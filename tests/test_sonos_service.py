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
    assert all(s.transport_state is None for s in speakers)
    assert all(s.is_playing is False for s in speakers)


def test_sonos_discovery_uses_coordinator_transport_state(monkeypatch):
    transport_calls = {"count": 0}

    class FakeCoordinator:
        ip_address = "192.168.1.10"
        uid = "RINCON_123"
        volume = 25
        player_name = "Living Room"

        def get_current_transport_info(self):
            transport_calls["count"] += 1
            return {"current_transport_state": "PLAYING"}

    coordinator = FakeCoordinator()
    member = SimpleNamespace(
        ip_address="192.168.1.11",
        player_name="Kitchen",
        uid="RINCON_456",
        volume=18,
    )
    group = SimpleNamespace(coordinator=coordinator, members=[coordinator, member])
    coordinator.group = group
    member.group = group

    def fake_discover(timeout: int = 2):
        _ = timeout
        return [coordinator, member]

    monkeypatch.setattr(sonos_module, "discover", fake_discover)
    service = SonosService()
    speakers = service.discover_speakers()

    by_uid = {speaker.uid: speaker for speaker in speakers}
    assert by_uid["RINCON_123"].transport_state == "PLAYING"
    assert by_uid["RINCON_123"].is_playing is True
    assert by_uid["RINCON_456"].transport_state == "PLAYING"
    assert by_uid["RINCON_456"].is_playing is True
    assert transport_calls["count"] == 1


def test_sonos_discovery_falls_back_when_transport_lookup_fails(monkeypatch):
    class FakeSpeaker:
        ip_address = "192.168.1.5"
        player_name = "Office"
        uid = "RINCON_789"
        volume = 10

        def get_current_transport_info(self):
            raise RuntimeError("transport unavailable")

    def fake_discover(timeout: int = 2):
        _ = timeout
        return [FakeSpeaker()]

    monkeypatch.setattr(sonos_module, "discover", fake_discover)
    service = SonosService()
    speakers = service.discover_speakers()

    assert len(speakers) == 1
    assert speakers[0].transport_state is None
    assert speakers[0].is_playing is False


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
    assert calls["title"] == "Airwave"


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
    assert calls["title"] == "Airwave"
