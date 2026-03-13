from __future__ import annotations

import ipaddress
import socket
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_PLACEHOLDER_HOSTS = {"testserver"}
_SPECIAL_LOCAL_HOSTS = {"localhost", "0.0.0.0", "host.docker.internal"}


def _extract_host(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value if "://" in value else f"http://{value}")
    host = parsed.hostname
    return host.lower() if host else None


def _is_docker_address(host: str | None) -> bool:
    if not host:
        return False
    if host in {"host.docker.internal"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("172.17.0.0/16")


def _is_reachable_host(host: str | None) -> bool:
    if not host or host in _PLACEHOLDER_HOSTS or host in _SPECIAL_LOCAL_HOSTS:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not ip.is_loopback and not ip.is_unspecified and not _is_docker_address(host)


def _detect_local_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            detected_ip = sock.getsockname()[0]
    except OSError:
        return None
    return detected_ip or None


def _format_netloc(host: str, port: int | None, scheme: str) -> str:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    formatted_host = f"[{host}]" if isinstance(ip, ipaddress.IPv6Address) else host
    default_port = 443 if scheme == "https" else 80
    if port in (None, default_port):
        return formatted_host
    return f"{formatted_host}:{port}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIRWAVE_", env_file=".env", extra="ignore")

    app_name: str = "AirWave"
    db_url: str = "sqlite+pysqlite:///./data/airwave.db"
    host: str = "0.0.0.0"
    port: int = 8000
    public_base_url: str = "http://127.0.0.1:8000"
    stream_path: str = "/stream/live.mp3"
    yt_dlp_path: str = "./bin/yt-dlp"
    ffmpeg_path: str = "./bin/ffmpeg"
    deno_path: str = "./bin/deno"
    mp3_bitrate: str = "128k"
    chunk_size: int = 2048
    queue_poll_seconds: float = Field(default=1.0, ge=0.1, le=10.0)
    stream_stats_log_seconds: float = Field(default=15.0, ge=1.0, le=300.0)
    history_limit: int = 50
    log_level: str = Field(default="INFO", description="Logging level (debug, info, warning, error)")


    @property
    def stream_url(self) -> str:
        return self.stream_url_for()

    def resolved_public_base_url(self, request_base_url: str | None = None) -> str:
        configured = self.public_base_url.rstrip("/")
        configured_parts = urlsplit(configured)
        configured_host = _extract_host(configured)
        if _is_reachable_host(configured_host):
            return configured

        detected_host = _detect_local_ip()
        request_host = _extract_host(request_base_url)

        if detected_host and not _is_docker_address(detected_host):
            resolved_host = detected_host
        elif _is_reachable_host(request_host):
            resolved_host = request_host
        else:
            resolved_host = configured_host or "127.0.0.1"

        scheme = configured_parts.scheme or urlsplit(request_base_url or "").scheme or "http"
        port = configured_parts.port or urlsplit(request_base_url or "").port or self.port
        path = configured_parts.path.rstrip("/")
        return urlunsplit((scheme, _format_netloc(resolved_host, port, scheme), path, "", ""))

    def stream_url_for(self, request_base_url: str | None = None) -> str:
        return f"{self.resolved_public_base_url(request_base_url)}{self.stream_path}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
