import app.core.config as config_module
from app.core.config import Settings


def test_chunk_size_default_uses_streaming_safe_baseline():
    settings = Settings()

    assert settings.chunk_size == 4096


def test_resolved_public_base_url_uses_detected_lan_ip(monkeypatch):
    monkeypatch.setattr(config_module, "_detect_local_ip", lambda: "192.168.1.44")
    settings = Settings(public_base_url="http://127.0.0.1:8000")

    assert settings.stream_url_for() == "http://192.168.1.44:8000/stream/live.mp3"


def test_resolved_public_base_url_falls_back_to_configured_when_detected_is_docker(monkeypatch):
    monkeypatch.setattr(config_module, "_detect_local_ip", lambda: "172.17.0.3")
    settings = Settings(public_base_url="http://127.0.0.1:8000")

    assert settings.stream_url_for() == "http://127.0.0.1:8000/stream/live.mp3"


def test_resolved_public_base_url_keeps_explicit_public_host(monkeypatch):
    monkeypatch.setattr(config_module, "_detect_local_ip", lambda: "192.168.1.44")
    settings = Settings(public_base_url="http://radio.example.com:9000")

    assert settings.stream_url_for() == "http://radio.example.com:9000/stream/live.mp3"


def test_resolved_public_base_url_keeps_non_reachable_domain(monkeypatch):
    """Domains like airwave.local.example.com are used as-is (no DNS resolution in container)."""
    monkeypatch.setattr(config_module, "_detect_local_ip", lambda: "192.168.1.44")
    settings = Settings(public_base_url="http://airwave.local.example.com:8000")

    assert settings.stream_url_for() == "http://airwave.local.example.com:8000/stream/live.mp3"
