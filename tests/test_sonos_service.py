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


def test_sonos_discovery_treats_group_less_speaker_as_single_member_group(monkeypatch):
    class FakeSpeaker:
        ip_address = "192.168.1.5"
        player_name = "Office"
        uid = "RINCON_789"
        volume = 10
        group = None

        def get_current_transport_info(self):
            return {"current_transport_state": "STOPPED"}

    def fake_discover(timeout: int = 2):
        _ = timeout
        return [FakeSpeaker()]

    monkeypatch.setattr(sonos_module, "discover", fake_discover)
    service = SonosService()
    speakers = service.discover_speakers()

    assert len(speakers) == 1
    assert speakers[0].group_member_uids == ["RINCON_789"]
    assert speakers[0].coordinator_uid == "RINCON_789"
    assert speakers[0].is_coordinator is True


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


class OfficeSpeaker:
    player_name = "Office"

    def __getattr__(self, name: str):
        raise AttributeError(name)

    @property
    def bass(self):
        return 0

    @property
    def treble(self):
        return 0

    @property
    def loudness(self):
        return True

    @property
    def cross_fade(self):
        return False


def test_get_speaker_settings_hides_sub_without_hardware(monkeypatch):
    monkeypatch.setattr(sonos_module, "SoCo", lambda ip: OfficeSpeaker())
    service = SonosService()
    payload = service.get_speaker_settings("192.168.1.50")
    assert payload["settings"]["sub_gain"] is None
    assert payload["settings"]["sub_enabled"] is None
    assert payload["settings"]["surround_level"] is None
    assert payload["settings"]["bass"] == 0


class LivingRoomSpeaker:
    player_name = "Living Room"

    def __init__(self):
        self._balance = (100, 100)
        self._dialog = False
        self._speech = None

    @property
    def balance(self):
        return self._balance

    @balance.setter
    def balance(self, value):
        self._balance = tuple(value)

    @property
    def bass(self):
        return 1

    @property
    def treble(self):
        return 2

    @property
    def loudness(self):
        return True

    @property
    def cross_fade(self):
        return False

    @property
    def audio_delay(self):
        return 1

    @property
    def soundbar_audio_input_format(self):
        return "Stereo PCM"

    @property
    def mic_enabled(self):
        return False

    @property
    def music_surround_level(self):
        return -2

    @property
    def night_mode(self):
        return False

    @property
    def speech_enhance_enabled(self):
        return self._speech

    @speech_enhance_enabled.setter
    def speech_enhance_enabled(self, value):
        self._speech = bool(value)

    @property
    def dialog_mode(self):
        return self._dialog

    @dialog_mode.setter
    def dialog_mode(self, value):
        self._dialog = bool(value)

    @property
    def sub_gain(self):
        return 4

    @property
    def sub_enabled(self):
        return True

    @property
    def surround_enabled(self):
        return True

    @property
    def surround_level(self):
        return -1

    @property
    def surround_full_volume_enabled(self):
        return 1


def test_get_speaker_settings_soundbar_with_sub(monkeypatch):
    speaker = LivingRoomSpeaker()
    monkeypatch.setattr(sonos_module, "SoCo", lambda ip: speaker)
    service = SonosService()
    payload = service.get_speaker_settings("10.0.0.2")
    s = payload["settings"]
    assert s["sub_enabled"] is True
    assert s["sub_gain"] == 4
    assert s["surround_enabled"] is True
    assert s["music_surround_level"] == -2
    assert s["surround_full_volume_enabled"] is True
    assert s["balance"] == 0


def test_speech_enhancement_read_prefers_speech_enhance_enabled(monkeypatch):
    class ArcUltra(LivingRoomSpeaker):
        @property
        def speech_enhance_enabled(self):
            return False

        @property
        def dialog_mode(self):
            return True

    speaker = ArcUltra()
    monkeypatch.setattr(sonos_module, "SoCo", lambda ip: speaker)
    service = SonosService()
    speech = service.get_speaker_settings("10.0.0.3")["settings"]["speech_enhancement"]
    assert speech is False


def test_speech_enhancement_read_falls_back_to_dialog_mode(monkeypatch):
    class BeamStyle(LivingRoomSpeaker):
        @property
        def speech_enhance_enabled(self):
            return None

        @property
        def dialog_mode(self):
            return True

    speaker = BeamStyle()
    monkeypatch.setattr(sonos_module, "SoCo", lambda ip: speaker)
    service = SonosService()
    speech = service.get_speaker_settings("10.0.0.4")["settings"]["speech_enhancement"]
    assert speech is True


def test_balance_write_maps_to_left_right_tuple(monkeypatch):
    speaker = LivingRoomSpeaker()
    monkeypatch.setattr(sonos_module, "SoCo", lambda ip: speaker)
    service = SonosService()
    service.update_speaker_setting("10.0.0.5", "balance", 40)
    assert speaker._balance == (60, 100)
    service.update_speaker_setting("10.0.0.5", "balance", -30)
    assert speaker._balance == (100, 70)


def test_speech_enhancement_write_falls_back_to_dialog_mode(monkeypatch):
    class BeamWrite(LivingRoomSpeaker):
        @property
        def speech_enhance_enabled(self):
            return None

        @speech_enhance_enabled.setter
        def speech_enhance_enabled(self, value):
            _ = value
            raise sonos_module.NotSupportedException("not arc ultra")

    speaker = BeamWrite()
    monkeypatch.setattr(sonos_module, "SoCo", lambda ip: speaker)
    service = SonosService()
    service.update_speaker_setting("10.0.0.6", "speech_enhancement", True)
    assert speaker._dialog is True
