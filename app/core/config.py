from __future__ import annotations

import json
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


def _is_special_local_host(host: str | None) -> bool:
    """True if host is a placeholder or special local host that should trigger fallback."""
    if not host or host in _PLACEHOLDER_HOSTS or host in _SPECIAL_LOCAL_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_unspecified or _is_docker_address(host)
    except ValueError:
        return False


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

    app_name: str = "Airwave"
    db_url: str = "sqlite+pysqlite:///./data/airwave.db"
    host: str = "0.0.0.0"
    port: int = 8000
    public_base_url: str = "http://127.0.0.1:8000"
    stream_path: str = "/stream/live.mp3"
    yt_dlp_path: str = "./bin/yt-dlp"
    ffmpeg_path: str = "./bin/ffmpeg"
    ffprobe_path: str = "./bin/ffprobe"
    deno_path: str = "./bin/deno"
    mp3_bitrate: str = "320k"
    # Keep FFmpeg reads large enough to tolerate scheduler jitter without adding
    # noticeable live-stream latency. Tiny chunks can cause occasional underruns.
    chunk_size: int = 4096
    stream_queue_size: int = 16
    queue_poll_seconds: float = Field(default=1.0, ge=0.1, le=10.0)
    stream_stats_log_seconds: float = Field(default=15.0, ge=1.0, le=300.0)
    history_limit: int = 50
    log_level: str = Field(default="INFO", description="Logging level (debug, info, warning, error)")
    playlist_sync_interval_seconds: int = Field(default=3600, ge=30)
    playlist_sync_max_concurrent: int = Field(default=2, ge=1, le=10)
    # Must remain `str` (not list[str]): pydantic-settings JSON-decodes list fields from env before
    # validators run, so values like `/mnt` or `a,b` would raise. Parse via local_media_roots_list.
    local_media_roots: str = Field(
        default="",
        description="Comma-separated paths, or a JSON array string, for AIRWAVE_LOCAL_MEDIA_ROOTS",
    )
    sendspin_enabled: bool = True
    sendspin_port: int = 8927
    sendspin_name: str = Field(default="Airwave", description="Name of the SendSpin server")
    sendspin_mdns_enabled: bool = True

    @staticmethod
    def _parse_local_media_roots_input(raw: str) -> list[str]:
        text = (raw or "").strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return [p.strip() for p in text.split(",") if p.strip()]
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        return [p.strip() for p in text.split(",") if p.strip()]

    @property
    def local_media_roots_list(self) -> list[str]:
        return self._parse_local_media_roots_input(self.local_media_roots)

    @property
    def stream_url(self) -> str:
        return self.stream_url_for()

    def resolved_public_base_url(self, request_base_url: str | None = None) -> str:
        configured = self.public_base_url.rstrip("/")
        configured_parts = urlsplit(configured)
        configured_host = _extract_host(configured)
        if not _is_special_local_host(configured_host):
            return configured

        detected_host = _detect_local_ip()
        request_host = _extract_host(request_base_url)

        if detected_host and not _is_docker_address(detected_host):
            resolved_host = detected_host
        elif request_host and not _is_special_local_host(request_host):
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
