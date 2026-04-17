from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from aiosendspin.models.types import PlaybackStateType

from app.services.sendspin_service import REPEAT_MAP_TO_AIRWAVE, REPEAT_MAP_TO_SENDSPIN, SendspinServerService
from app.services.stream_engine import PlaybackMode, RepeatMode


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class FakePlayerRole:
    volume: int | None = 80
    muted: bool = False
    static_delay_ms: int = 0
    preferred_format: Any = None

    _volume_commands: list[int] = field(default_factory=list)
    _mute_commands: list[bool] = field(default_factory=list)

    def set_player_volume(self, vol: int) -> None:
        self._volume_commands.append(vol)

    def set_player_mute(self, muted: bool) -> None:
        self._mute_commands.append(muted)


@dataclass
class FakeClient:
    client_id: str = "client-1"
    name: str = "Test Player"
    is_connected: bool = True
    negotiated_roles: list[str] = field(default_factory=lambda: ["player.v1"])
    info: Any = None
    _player_roles: list[FakePlayerRole] = field(default_factory=list)

    def roles_by_family(self, family: str) -> list:
        if family == "player":
            return list(self._player_roles)
        return []


@dataclass
class FakeGroup:
    clients: list[FakeClient] = field(default_factory=list)
    has_active_stream: bool = False
    _roles: dict[str, Any] = field(default_factory=dict)
    state: PlaybackStateType = PlaybackStateType.STOPPED

    def group_role(self, name: str) -> Any:
        return self._roles.get(name)

    def _set_playback_state(self, new_state: PlaybackStateType) -> None:
        self.state = new_state


@dataclass
class FakeServer:
    _clients: dict[str, FakeClient] = field(default_factory=dict)

    @property
    def connected_clients(self) -> list[FakeClient]:
        return list(self._clients.values())

    def get_client(self, client_id: str) -> FakeClient | None:
        return self._clients.get(client_id)


def _make_service(**overrides: Any) -> SendspinServerService:
    engine = MagicMock()
    engine.state = SimpleNamespace(
        mode=PlaybackMode.idle,
        paused=False,
        repeat_mode=RepeatMode.off,
        shuffle_enabled=False,
        now_playing_id=None,
        now_playing_title=None,
        now_playing_channel=None,
        now_playing_thumbnail_url=None,
        now_playing_duration_seconds=None,
        now_playing_is_live=False,
    )
    engine.playback_progress.return_value = {"elapsed_seconds": 0, "progress_percent": 0}
    pipeline = MagicMock()
    defaults = dict(
        stream_engine=engine,
        ffmpeg_pipeline=pipeline,
        server_name="Test",
        port=9999,
        mdns_enabled=False,
    )
    defaults.update(overrides)
    return SendspinServerService(**defaults)


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

def test_is_running_false_by_default():
    svc = _make_service()
    assert svc.is_running is False


def test_is_running_true_when_server_set():
    svc = _make_service()
    svc._server = FakeServer()  # noqa: SLF001
    assert svc.is_running is True


# ---------------------------------------------------------------------------
# Client serialization
# ---------------------------------------------------------------------------

def test_serialize_client_basic():
    player = FakePlayerRole(volume=65, muted=True, static_delay_ms=200)
    client = FakeClient(
        client_id="abc-123",
        name="Kitchen Speaker",
        _player_roles=[player],
    )
    svc = _make_service()
    result = svc._serialize_client(client)  # noqa: SLF001
    assert result["client_id"] == "abc-123"
    assert result["name"] == "Kitchen Speaker"
    assert result["volume"] == 65
    assert result["muted"] is True
    assert result["static_delay_ms"] == 200
    assert result["is_connected"] is True
    assert result["roles"] == ["player.v1"]


def test_serialize_client_no_player_role():
    client = FakeClient(client_id="no-player", name="Display Only", _player_roles=[])
    svc = _make_service()
    result = svc._serialize_client(client)  # noqa: SLF001
    assert result["volume"] is None
    assert result["muted"] is None
    assert result["codec"] is None


def test_serialize_client_with_preferred_format():
    fmt = SimpleNamespace(sample_rate=48000, bit_depth=16, channels=2)
    player = FakePlayerRole(preferred_format=fmt)
    client = FakeClient(_player_roles=[player])
    svc = _make_service()
    result = svc._serialize_client(client)  # noqa: SLF001
    assert result["codec"] == "48000Hz/16bit/2ch"


def test_serialize_client_with_device_info():
    info = SimpleNamespace(
        device_info=SimpleNamespace(
            product_name="Amp v2",
            manufacturer="Acme",
            software_version="1.2.3",
        )
    )
    client = FakeClient(info=info, _player_roles=[FakePlayerRole()])
    svc = _make_service()
    result = svc._serialize_client(client)  # noqa: SLF001
    assert result["device_info"]["product_name"] == "Amp v2"
    assert result["device_info"]["manufacturer"] == "Acme"
    assert result["device_info"]["software_version"] == "1.2.3"


# ---------------------------------------------------------------------------
# list_clients
# ---------------------------------------------------------------------------

def test_list_clients_returns_empty_when_no_server():
    svc = _make_service()
    assert svc.list_clients() == []


def test_list_clients_returns_connected_clients():
    svc = _make_service()
    c1 = FakeClient(client_id="a", name="A", _player_roles=[FakePlayerRole(volume=50)])
    c2 = FakeClient(client_id="b", name="B", _player_roles=[FakePlayerRole(volume=75)])
    server = FakeServer(_clients={"a": c1, "b": c2})
    svc._server = server  # noqa: SLF001
    result = svc.list_clients()
    assert len(result) == 2
    ids = {r["client_id"] for r in result}
    assert ids == {"a", "b"}


# ---------------------------------------------------------------------------
# get_group_state
# ---------------------------------------------------------------------------

def test_get_group_state_defaults_without_group():
    svc = _make_service()
    assert svc.get_group_state() == {"volume": 0, "muted": False}


def test_get_group_state_with_player_group_role():
    svc = _make_service()
    player_grp = MagicMock()
    player_grp.get_group_volume.return_value = 42
    player_grp.get_group_muted.return_value = True
    group = FakeGroup(_roles={"player": player_grp})
    svc._group = group  # noqa: SLF001
    result = svc.get_group_state()
    assert result == {"volume": 42, "muted": True}


# ---------------------------------------------------------------------------
# set_client_volume / set_client_muted
# ---------------------------------------------------------------------------

def test_set_client_volume_returns_false_without_server():
    svc = _make_service()
    assert svc.set_client_volume("x", 50) is False


def test_set_client_volume_returns_false_for_unknown_client():
    svc = _make_service()
    svc._server = FakeServer()  # noqa: SLF001
    assert svc.set_client_volume("ghost", 50) is False


def test_set_client_volume_updates_player():
    player = FakePlayerRole(volume=30)
    client = FakeClient(client_id="c1", _player_roles=[player])
    server = FakeServer(_clients={"c1": client})
    changed = []
    svc = _make_service(on_clients_changed=lambda: changed.append(True))
    svc._server = server  # noqa: SLF001
    assert svc.set_client_volume("c1", 85) is True
    assert player.volume == 85
    assert player._volume_commands == [85]
    assert len(changed) == 1


def test_set_client_volume_clamps_to_range():
    player = FakePlayerRole(volume=50)
    client = FakeClient(client_id="c1", _player_roles=[player])
    server = FakeServer(_clients={"c1": client})
    svc = _make_service()
    svc._server = server  # noqa: SLF001
    svc.set_client_volume("c1", 150)
    assert player.volume == 100
    svc.set_client_volume("c1", -20)
    assert player.volume == 0


def test_set_client_muted_updates_player():
    player = FakePlayerRole(muted=False)
    client = FakeClient(client_id="c1", _player_roles=[player])
    server = FakeServer(_clients={"c1": client})
    changed = []
    svc = _make_service(on_clients_changed=lambda: changed.append(True))
    svc._server = server  # noqa: SLF001
    assert svc.set_client_muted("c1", True) is True
    assert player.muted is True
    assert player._mute_commands == [True]
    assert len(changed) == 1


# ---------------------------------------------------------------------------
# set_group_volume / set_group_muted
# ---------------------------------------------------------------------------

def test_set_group_volume_returns_false_without_group():
    svc = _make_service()
    assert svc.set_group_volume(50) is False


def test_set_group_volume_redistributes_across_players():
    p1 = FakePlayerRole(volume=40)
    p2 = FakePlayerRole(volume=60)
    group = FakeGroup()
    changed = []
    svc = _make_service(on_clients_changed=lambda: changed.append(True))
    svc._group = group  # noqa: SLF001
    svc._get_group_players = lambda: [p1, p2]  # noqa: SLF001

    assert svc.set_group_volume(80) is True
    assert p1.volume == 70
    assert p2.volume == 90
    assert len(changed) == 1


def test_set_group_muted_mutes_all_players():
    p1 = FakePlayerRole(muted=False)
    p2 = FakePlayerRole(muted=False)
    group = FakeGroup()
    svc = _make_service()
    svc._group = group  # noqa: SLF001
    svc._get_group_players = lambda: [p1, p2]  # noqa: SLF001

    assert svc.set_group_muted(True) is True
    assert p1.muted is True
    assert p2.muted is True


# ---------------------------------------------------------------------------
# _redistribute_volume (static, algorithm correctness)
# ---------------------------------------------------------------------------

def test_redistribute_equal_volumes():
    players = [FakePlayerRole(volume=50), FakePlayerRole(volume=50)]
    result = SendspinServerService._redistribute_volume(players, 80)
    assert list(result.values()) == [80, 80]


def test_redistribute_unequal_volumes_preserves_ratio():
    players = [FakePlayerRole(volume=20), FakePlayerRole(volume=80)]
    result = SendspinServerService._redistribute_volume(players, 70)
    volumes = list(result.values())
    assert sum(volumes) / len(volumes) == 70


def test_redistribute_clamps_at_100():
    players = [FakePlayerRole(volume=90), FakePlayerRole(volume=90)]
    result = SendspinServerService._redistribute_volume(players, 100)
    assert all(v == 100 for v in result.values())


def test_redistribute_clamps_at_0():
    players = [FakePlayerRole(volume=10), FakePlayerRole(volume=10)]
    result = SendspinServerService._redistribute_volume(players, 0)
    assert all(v == 0 for v in result.values())


def test_redistribute_empty_players():
    assert SendspinServerService._redistribute_volume([], 50) == {}


def test_redistribute_none_volume_skipped():
    players = [FakePlayerRole(volume=None), FakePlayerRole(volume=60)]
    result = SendspinServerService._redistribute_volume(players, 80)
    assert len(result) == 1
    assert list(result.values()) == [80]


# ---------------------------------------------------------------------------
# push_state_update (early-return paths)
# ---------------------------------------------------------------------------

def test_push_state_update_noop_without_server():
    svc = _make_service()
    svc._group = FakeGroup()  # noqa: SLF001
    svc.push_state_update()


def test_push_state_update_noop_without_group():
    svc = _make_service()
    svc._server = FakeServer()  # noqa: SLF001
    svc.push_state_update()


def test_push_state_update_sets_group_paused_when_engine_paused():
    svc = _make_service()
    svc._server = FakeServer()  # noqa: SLF001
    svc._group = FakeGroup()  # noqa: SLF001
    svc._stream_engine.state.mode = PlaybackMode.playing  # noqa: SLF001
    svc._stream_engine.state.paused = True  # noqa: SLF001
    svc._push_metadata = MagicMock()  # noqa: SLF001
    svc._push_artwork_if_changed = MagicMock()  # noqa: SLF001
    svc._sync_controller_state_from_group = MagicMock()  # noqa: SLF001

    svc.push_state_update()

    assert svc._group.state == PlaybackStateType.PAUSED  # noqa: SLF001


def test_push_state_update_sets_group_playing_when_engine_playing():
    svc = _make_service()
    svc._server = FakeServer()  # noqa: SLF001
    svc._group = FakeGroup(state=PlaybackStateType.PAUSED)  # noqa: SLF001
    svc._stream_engine.state.mode = PlaybackMode.playing  # noqa: SLF001
    svc._stream_engine.state.paused = False  # noqa: SLF001
    svc._push_metadata = MagicMock()  # noqa: SLF001
    svc._push_artwork_if_changed = MagicMock()  # noqa: SLF001
    svc._sync_controller_state_from_group = MagicMock()  # noqa: SLF001

    svc.push_state_update()

    assert svc._group.state == PlaybackStateType.PLAYING  # noqa: SLF001


def test_push_state_update_sets_group_stopped_when_engine_idle():
    svc = _make_service()
    svc._server = FakeServer()  # noqa: SLF001
    svc._group = FakeGroup(state=PlaybackStateType.PLAYING)  # noqa: SLF001
    svc._stream_engine.state.mode = PlaybackMode.idle  # noqa: SLF001
    svc._stream_engine.state.paused = False  # noqa: SLF001
    svc._push_metadata = MagicMock()  # noqa: SLF001
    svc._push_artwork_if_changed = MagicMock()  # noqa: SLF001
    svc._sync_controller_state_from_group = MagicMock()  # noqa: SLF001

    svc.push_state_update()

    assert svc._group.state == PlaybackStateType.STOPPED  # noqa: SLF001


# ---------------------------------------------------------------------------
# Controller event handling
# ---------------------------------------------------------------------------

def test_handle_play_event_calls_resume():
    svc = _make_service()
    svc._stream_engine.state.paused = True  # noqa: SLF001
    from aiosendspin.server.roles import ControllerPlayEvent
    svc._handle_controller_event(ControllerPlayEvent())  # noqa: SLF001
    svc._stream_engine.resume_playback.assert_called_once()  # noqa: SLF001


def test_handle_play_event_resume_when_not_paused():
    svc = _make_service()
    svc._stream_engine.state.paused = False  # noqa: SLF001
    from aiosendspin.server.roles import ControllerPlayEvent
    svc._handle_controller_event(ControllerPlayEvent())  # noqa: SLF001
    svc._stream_engine.resume_playback.assert_called_once()  # noqa: SLF001


def test_handle_pause_event_pauses_when_playing():
    svc = _make_service()
    svc._stream_engine.state.paused = False  # noqa: SLF001
    svc._stream_engine.state.mode = PlaybackMode.playing  # noqa: SLF001
    from aiosendspin.server.roles import ControllerPauseEvent
    svc._handle_controller_event(ControllerPauseEvent())  # noqa: SLF001
    svc._stream_engine.toggle_pause.assert_called_once()  # noqa: SLF001


def test_handle_next_event_skips():
    svc = _make_service()
    from aiosendspin.server.roles import ControllerNextEvent
    svc._handle_controller_event(ControllerNextEvent())  # noqa: SLF001
    svc._stream_engine.skip_current.assert_called_once()  # noqa: SLF001


def test_handle_previous_event():
    svc = _make_service()
    from aiosendspin.server.roles import ControllerPreviousEvent
    svc._handle_controller_event(ControllerPreviousEvent())  # noqa: SLF001
    svc._stream_engine.play_previous_or_restart.assert_called_once()  # noqa: SLF001


def test_handle_shuffle_event():
    svc = _make_service()
    from aiosendspin.server.roles import ControllerShuffleEvent
    svc._handle_controller_event(ControllerShuffleEvent(shuffle=True))  # noqa: SLF001
    svc._stream_engine.set_shuffle_enabled.assert_called_once_with(True)  # noqa: SLF001


def test_handle_repeat_event():
    svc = _make_service()
    from aiosendspin.server.roles import ControllerRepeatEvent
    from aiosendspin.models.types import RepeatMode as SendspinRepeatMode
    svc._handle_controller_event(ControllerRepeatEvent(mode=SendspinRepeatMode.ALL))  # noqa: SLF001
    svc._stream_engine.set_repeat_mode.assert_called_once_with("all")  # noqa: SLF001


def test_handle_volume_event_sets_group_volume():
    p1 = FakePlayerRole(volume=50)
    group = FakeGroup()
    svc = _make_service()
    svc._group = group  # noqa: SLF001
    svc._server = FakeServer()  # noqa: SLF001
    svc._get_group_players = lambda: [p1]  # noqa: SLF001
    from aiosendspin.server.roles import ControllerVolumeEvent
    svc._handle_controller_event(ControllerVolumeEvent(volume=70))  # noqa: SLF001
    assert p1.volume == 70


def test_handle_mute_event_mutes_group():
    p1 = FakePlayerRole(muted=False)
    group = FakeGroup()
    svc = _make_service()
    svc._group = group  # noqa: SLF001
    svc._get_group_players = lambda: [p1]  # noqa: SLF001
    from aiosendspin.server.roles import ControllerMuteEvent
    svc._handle_controller_event(ControllerMuteEvent(muted=True))  # noqa: SLF001
    assert p1.muted is True


# ---------------------------------------------------------------------------
# Repeat-mode mapping tables
# ---------------------------------------------------------------------------

def test_repeat_map_roundtrip():
    from aiosendspin.models.types import RepeatMode as SendspinRepeatMode
    for airwave_mode in (RepeatMode.off, RepeatMode.one, RepeatMode.all):
        sendspin_mode = REPEAT_MAP_TO_SENDSPIN[airwave_mode]
        back = REPEAT_MAP_TO_AIRWAVE[sendspin_mode]
        assert back == airwave_mode.value


# ---------------------------------------------------------------------------
# _notify_clients_changed resilience
# ---------------------------------------------------------------------------

def test_notify_clients_changed_swallows_callback_errors():
    def exploding_callback():
        raise RuntimeError("boom")

    svc = _make_service(on_clients_changed=exploding_callback)
    svc._notify_clients_changed()  # noqa: SLF001
