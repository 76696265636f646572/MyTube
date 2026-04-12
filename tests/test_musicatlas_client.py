from __future__ import annotations

import json
import logging

import httpx
import pytest

from app.services.musicatlas_client import (
    MusicAtlasClient,
    MusicAtlasDisabledError,
    MusicAtlasKeysExhaustedError,
    parse_musicatlas_api_keys,
)


def test_parse_musicatlas_api_keys_splits_trims_and_drops_empties() -> None:
    assert parse_musicatlas_api_keys("") == []
    assert parse_musicatlas_api_keys("   ") == []
    assert parse_musicatlas_api_keys(None) == []
    assert parse_musicatlas_api_keys("alpha") == ["alpha"]
    assert parse_musicatlas_api_keys(" alpha , beta ") == ["alpha", "beta"]
    assert parse_musicatlas_api_keys("a,, b ,\n c") == ["a", "b", "c"]


def test_similar_tracks_succeeds_with_first_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/similar_tracks"
        payload = json.loads(request.content.decode())
        assert payload["artist"] == "A" and payload["track"] == "B"
        return httpx.Response(200, json={"success": True})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://api.musicatlas.ai") as http:
        client = MusicAtlasClient(api_keys=["only"], http_client=http)
        out = client.similar_tracks(artist="A", track="B")
    assert out == {"success": True}
    assert client.active_key_index == 0


def test_rotates_on_403_and_succeeds_with_next_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization", "")
        if auth.endswith("bad"):
            return httpx.Response(403, json={"error": "invalid"})
        if auth.endswith("good"):
            return httpx.Response(200, json={"tier": "second"})
        return httpx.Response(500, json={"unexpected": True})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://api.musicatlas.ai") as http:
        client = MusicAtlasClient(api_keys=["bad", "good"], http_client=http)
        out = client.similar_tracks(artist="A", track="B")
    assert out == {"tier": "second"}
    assert client.active_key_index == 1


def test_rotates_on_429() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization", "")
        calls.append(auth)
        if auth.endswith("k1"):
            return httpx.Response(429, json={"retry": True})
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://api.musicatlas.ai") as http:
        client = MusicAtlasClient(api_keys=["k1", "k2"], http_client=http)
        assert client.similar_tracks(artist="X", track="Y") == {"ok": True}
    assert len(calls) == 2
    assert calls[0].endswith("k1")
    assert calls[1].endswith("k2")


def test_rotates_on_401() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization", "")
        if auth.endswith("old"):
            return httpx.Response(401, json={"auth": "no"})
        return httpx.Response(200, json={"fresh": True})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://api.musicatlas.ai") as http:
        client = MusicAtlasClient(api_keys=["old", "new"], http_client=http)
        assert client.similar_tracks(artist="A", track="B") == {"fresh": True}


def test_exhausts_keys_raises_clear_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"nope": True})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://api.musicatlas.ai") as http:
        client = MusicAtlasClient(api_keys=["a", "b"], http_client=http)
        with pytest.raises(MusicAtlasKeysExhaustedError) as excinfo:
            client.similar_tracks(artist="A", track="B")
    err = excinfo.value
    assert err.keys_tried == 2
    assert err.last_status_code == 403


def test_disabled_client_raises() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    with httpx.Client(transport=transport, base_url="https://api.musicatlas.ai") as http:
        client = MusicAtlasClient(api_keys=[], http_client=http)
    assert client.enabled is False
    assert client.active_key is None
    assert client.active_key_index is None
    with pytest.raises(MusicAtlasDisabledError):
        client.similar_tracks(artist="A", track="B")


def test_similar_tracks_multi_payload_shape() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"success": True})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://api.musicatlas.ai") as http:
        client = MusicAtlasClient(api_keys=["k"], http_client=http)
        client.similar_tracks_multi(
            liked_tracks=[{"artist": "A", "title": "T"}],
            disliked_tracks=[{"artist": "B", "title": "U"}],
        )
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["liked_tracks"] == [{"artist": "A", "title": "T"}]
    assert payload["disliked_tracks"] == [{"artist": "B", "title": "U"}]


def test_add_track_accepts_200_and_409() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        if request.method == "POST" and request.url.path == "/add_track":
            payload = json.loads(request.content.decode())
            if payload.get("title") == "exists":
                return httpx.Response(409, json={"message": "already there"})
            return httpx.Response(200, json={"success": True, "job_id": "jid_1"})
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://api.musicatlas.ai") as http:
        client = MusicAtlasClient(api_keys=["k"], http_client=http)
        s200, b200 = client.add_track(artist="A", title="new")
        s409, b409 = client.add_track(artist="A", title="exists")
    assert s200 == 200 and b200["job_id"] == "jid_1"
    assert s409 == 409 and b409["message"] == "already there"
    assert len(calls) == 2


def test_add_track_progress_gets_query_param() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"status": "queued", "percent_complete": 1})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://api.musicatlas.ai") as http:
        client = MusicAtlasClient(api_keys=["k"], http_client=http)
        out = client.add_track_progress(job_id="addtrack_xyz")
    assert out["status"] == "queued"
    assert "job_id=addtrack_xyz" in seen[0]


def test_warning_logs_do_not_contain_raw_key(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"msg": "no"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="https://api.musicatlas.ai") as http:
        client = MusicAtlasClient(api_keys=["super-secret-key-xyz", "other"], http_client=http)
        with pytest.raises(MusicAtlasKeysExhaustedError):
            client.similar_tracks(artist="A", track="B")

    assert "super-secret-key-xyz" not in caplog.text
