from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@dataclass
class FakeSendspinService:
    is_running: bool = True
    _clients: list[dict[str, Any]] = field(default_factory=list)
    _group_state: dict[str, Any] = field(default_factory=lambda: {"volume": 50, "muted": False})
    last_client_volume: tuple[str, int] | None = None
    last_client_muted: tuple[str, bool] | None = None
    last_group_volume: int | None = None
    last_group_muted: bool | None = None

    def list_clients(self) -> list[dict[str, Any]]:
        return list(self._clients)

    def get_group_state(self) -> dict[str, Any]:
        return dict(self._group_state)

    def set_client_volume(self, client_id: str, volume: int) -> bool:
        self.last_client_volume = (client_id, volume)
        return any(c["client_id"] == client_id for c in self._clients)

    def set_client_muted(self, client_id: str, muted: bool) -> bool:
        self.last_client_muted = (client_id, muted)
        return any(c["client_id"] == client_id for c in self._clients)

    def set_group_volume(self, volume: int) -> bool:
        self.last_group_volume = volume
        return True

    def set_group_muted(self, muted: bool) -> bool:
        self.last_group_muted = muted
        return True


def _build_test_client(tmp_path):
    settings = Settings(
        db_url=f"sqlite+pysqlite:///{tmp_path}/sendspin.db",
        yt_dlp_path="/bin/echo",
        ffmpeg_path="/bin/echo",
        deno_path="/bin/echo",
        sendspin_enabled=False,
    )
    app = create_app(settings=settings, start_engine=False)
    client = TestClient(app)
    return client, app


SAMPLE_CLIENTS = [
    {
        "client_id": "browser-1",
        "name": "Airwave Web Player",
        "is_connected": True,
        "volume": 80,
        "muted": False,
        "static_delay_ms": 0,
        "codec": "48000Hz/16bit/2ch",
        "device_info": {},
        "roles": ["player.v1"],
    },
    {
        "client_id": "phone-2",
        "name": "Phone App",
        "is_connected": True,
        "volume": 60,
        "muted": True,
        "static_delay_ms": 100,
        "codec": None,
        "device_info": {"product_name": "Phone", "manufacturer": "Acme"},
        "roles": ["player.v1"],
    },
]


# ---------------------------------------------------------------------------
# GET /api/sendspin/clients
# ---------------------------------------------------------------------------

def test_list_clients_returns_defaults_when_service_disabled(tmp_path):
    client, _app = _build_test_client(tmp_path)
    with client:
        resp = client.get("/api/sendspin/clients")
        assert resp.status_code == 200
        body = resp.json()
        assert body["clients"] == []
        assert body["group"] == {"volume": 0, "muted": False}
        assert body["enabled"] is False


def test_list_clients_returns_service_data(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        fake = FakeSendspinService(_clients=SAMPLE_CLIENTS)
        app.state.sendspin_service = fake
        resp = client.get("/api/sendspin/clients")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["clients"]) == 2
        assert body["clients"][0]["client_id"] == "browser-1"
        assert body["group"]["volume"] == 50


# ---------------------------------------------------------------------------
# POST /api/sendspin/clients/{client_id}/volume
# ---------------------------------------------------------------------------

def test_set_client_volume_succeeds(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        fake = FakeSendspinService(_clients=SAMPLE_CLIENTS)
        app.state.sendspin_service = fake
        resp = client.post(
            "/api/sendspin/clients/browser-1/volume",
            json={"volume": 42},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert fake.last_client_volume == ("browser-1", 42)


def test_set_client_volume_returns_503_when_disabled(tmp_path):
    client, _app = _build_test_client(tmp_path)
    with client:
        resp = client.post(
            "/api/sendspin/clients/browser-1/volume",
            json={"volume": 50},
        )
        assert resp.status_code == 503


def test_set_client_volume_returns_404_for_unknown_client(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        fake = FakeSendspinService(_clients=SAMPLE_CLIENTS)
        app.state.sendspin_service = fake
        resp = client.post(
            "/api/sendspin/clients/ghost/volume",
            json={"volume": 50},
        )
        assert resp.status_code == 404


def test_set_client_volume_validates_range(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        fake = FakeSendspinService(_clients=SAMPLE_CLIENTS)
        app.state.sendspin_service = fake
        resp_over = client.post(
            "/api/sendspin/clients/browser-1/volume",
            json={"volume": 150},
        )
        assert resp_over.status_code == 422

        resp_under = client.post(
            "/api/sendspin/clients/browser-1/volume",
            json={"volume": -5},
        )
        assert resp_under.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/sendspin/clients/{client_id}/mute
# ---------------------------------------------------------------------------

def test_set_client_mute_succeeds(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        fake = FakeSendspinService(_clients=SAMPLE_CLIENTS)
        app.state.sendspin_service = fake
        resp = client.post(
            "/api/sendspin/clients/browser-1/mute",
            json={"muted": True},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert fake.last_client_muted == ("browser-1", True)


def test_set_client_mute_returns_503_when_disabled(tmp_path):
    client, _app = _build_test_client(tmp_path)
    with client:
        resp = client.post(
            "/api/sendspin/clients/browser-1/mute",
            json={"muted": False},
        )
        assert resp.status_code == 503


def test_set_client_mute_returns_404_for_unknown_client(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        fake = FakeSendspinService(_clients=SAMPLE_CLIENTS)
        app.state.sendspin_service = fake
        resp = client.post(
            "/api/sendspin/clients/ghost/mute",
            json={"muted": True},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/sendspin/group/volume
# ---------------------------------------------------------------------------

def test_set_group_volume_succeeds(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        fake = FakeSendspinService()
        app.state.sendspin_service = fake
        resp = client.post("/api/sendspin/group/volume", json={"volume": 65})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert fake.last_group_volume == 65


def test_set_group_volume_returns_503_when_disabled(tmp_path):
    client, _app = _build_test_client(tmp_path)
    with client:
        resp = client.post("/api/sendspin/group/volume", json={"volume": 50})
        assert resp.status_code == 503


def test_set_group_volume_validates_range(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        fake = FakeSendspinService()
        app.state.sendspin_service = fake
        resp = client.post("/api/sendspin/group/volume", json={"volume": 101})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/sendspin/group/mute
# ---------------------------------------------------------------------------

def test_set_group_mute_succeeds(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        fake = FakeSendspinService()
        app.state.sendspin_service = fake
        resp = client.post("/api/sendspin/group/mute", json={"muted": True})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert fake.last_group_muted is True


def test_set_group_mute_returns_503_when_disabled(tmp_path):
    client, _app = _build_test_client(tmp_path)
    with client:
        resp = client.post("/api/sendspin/group/mute", json={"muted": False})
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Snapshot includes sendspin data
# ---------------------------------------------------------------------------

def test_ui_snapshot_includes_sendspin_block(tmp_path):
    client, app = _build_test_client(tmp_path)
    with client:
        fake = FakeSendspinService(_clients=SAMPLE_CLIENTS)
        app.state.sendspin_service = fake
        with client.websocket_connect("/api/ws/events") as ws:
            snapshot = ws.receive_json()
        assert snapshot["type"] == "snapshot"
        assert "sendspin" in snapshot
        assert len(snapshot["sendspin"]["clients"]) == 2
        assert snapshot["sendspin"]["group"]["volume"] == 50
