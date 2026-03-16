from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from hashlib import sha256
from tempfile import NamedTemporaryFile
from typing import Any


logger = logging.getLogger(__name__)


class YtDlpError(RuntimeError):
    pass


@dataclass
class _CookieCacheEntry:
    value_hash: str
    path: str


class YtDlpClient:
    def __init__(self, binary_path: str, ffmpeg_path: str, deno_path: str) -> None:
        self.binary_path = binary_path
        self.ffmpeg_path = ffmpeg_path
        self.deno_path = deno_path
        self._cookie_cache: dict[str, _CookieCacheEntry] = {}
        self._cookie_cache_lock = threading.Lock()

    def ensure_available(self) -> None:
        if shutil.which(self.binary_path) is None and not os.path.exists(self.binary_path):
            raise YtDlpError(
                f"yt-dlp binary not found at '{self.binary_path}'. "
                "Install yt-dlp or set AIRWAVE_YT_DLP_PATH."
            )

    def _build_base_cmd(self, cookie_file: str | None = None, verbose: bool = False) -> list[str]:
        cmd = [
            self.binary_path,
            "--js-runtimes",
            f"deno:{self.deno_path}",
            "--js-runtimes",
            "node",
            "--ffmpeg-location",
            self.ffmpeg_path,
        ]
        if verbose:
            cmd.insert(1, "-v")
        if cookie_file:
            cmd.extend(["--cookies", cookie_file])
        return cmd

    @staticmethod
    def _looks_like_cookie_content(value: str) -> bool:
        stripped = value.strip()
        return (
            stripped.startswith("# Netscape HTTP Cookie File")
            or "\n" in stripped
            or "\t" in stripped
        )

    @staticmethod
    def _normalize_cookie_value(value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        return stripped

    def resolve_cookie_file(self, provider: str, value: str | None) -> str | None:
        normalized = self._normalize_cookie_value(value)
        if normalized is None:
            return None
        if not self._looks_like_cookie_content(normalized):
            return os.path.expanduser(normalized)

        value_hash = sha256(normalized.encode("utf-8")).hexdigest()
        with self._cookie_cache_lock:
            cached = self._cookie_cache.get(provider)
            if cached is not None and cached.value_hash == value_hash and os.path.exists(cached.path):
                return cached.path

            if cached is not None and os.path.exists(cached.path):
                try:
                    os.unlink(cached.path)
                except OSError:
                    logger.debug("Failed deleting stale cookie file", exc_info=True)

            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=f"airwave-cookies-{provider}-",
                suffix=".txt",
                delete=False,
            ) as handle:
                handle.write(normalized)
                path = handle.name

            self._cookie_cache[provider] = _CookieCacheEntry(value_hash=value_hash, path=path)
            return path

    def _run_json(self, *args: str, cookie_file: str | None = None) -> dict[str, Any]:
        cmd = [*self._build_base_cmd(cookie_file=cookie_file, verbose=True), *args]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        def read_stream(stream, collector: list[str]) -> None:
            try:
                for line in iter(stream.readline, ""):
                    collector.append(line.rstrip("\n"))
            except Exception:
                logger.debug("Failed reading yt-dlp stream", exc_info=True)

        out_thread = threading.Thread(target=read_stream, args=(proc.stdout, stdout_lines))
        err_thread = threading.Thread(target=read_stream, args=(proc.stderr, stderr_lines))
        out_thread.start()
        err_thread.start()
        proc.wait()
        if proc.stdout is not None:
            proc.stdout.close()
        if proc.stderr is not None:
            proc.stderr.close()
        out_thread.join()
        err_thread.join()

        stdout = "\n".join(stdout_lines)
        stderr = "\n".join(stderr_lines)
        if proc.returncode != 0:
            raise YtDlpError(stderr.strip() or "yt-dlp failed")
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise YtDlpError("Invalid JSON from yt-dlp") from exc

    def _run_text(self, *args: str, cookie_file: str | None = None) -> str:
        cmd = [*self._build_base_cmd(cookie_file=cookie_file), *args]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise YtDlpError(
                f"yt-dlp binary not found at '{self.binary_path}'. "
                "Install yt-dlp or set AIRWAVE_YT_DLP_PATH."
            ) from exc
        if proc.returncode != 0:
            raise YtDlpError(proc.stderr.strip() or "yt-dlp failed")
        return proc.stdout.strip()

    def get_single_json(self, url: str, cookie_file: str | None = None) -> dict[str, Any]:
        return self._run_json("--no-playlist", "--skip-download", "-J", url, cookie_file=cookie_file)

    def get_playlist_json(self, url: str, cookie_file: str | None = None) -> dict[str, Any]:
        return self._run_json("--flat-playlist", "--skip-download", "-J", url, cookie_file=cookie_file)

    def get_stream_url(self, url: str, cookie_file: str | None = None) -> str:
        output = self._run_text("--no-playlist", "-f", "bestaudio/best", "-g", url, cookie_file=cookie_file)
        stream_url = next((line.strip() for line in output.splitlines() if line.strip()), "")
        if not stream_url:
            raise YtDlpError("Could not resolve direct stream URL")
        return stream_url

    def spawn_audio_stream(self, url: str, cookie_file: str | None = None) -> subprocess.Popen[bytes]:
        cmd = [
            *self._build_base_cmd(cookie_file=cookie_file),
            "--no-playlist",
            "-f",
            "bestaudio/best",
            "--no-progress",
            "--quiet",
            "-o",
            "-",
            url,
        ]
        try:
            return subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise YtDlpError(
                f"yt-dlp binary not found at '{self.binary_path}'. "
                "Install yt-dlp or set AIRWAVE_YT_DLP_PATH."
            ) from exc

    def search_json(
        self,
        query: str,
        provider: str,
        limit: int = 10,
        cookie_file: str | None = None,
    ) -> dict[str, Any]:
        bounded_limit = max(1, min(limit, 100))
        search_terms = {
            "youtube": f"ytsearch{bounded_limit}:{query}",
            "soundcloud": f"scsearch{bounded_limit}:{query}",
        }
        search_term = search_terms.get(provider)
        if search_term is None:
            return {"entries": []}
        return self._run_json("--flat-playlist", "--skip-download", "-J", search_term, cookie_file=cookie_file)
