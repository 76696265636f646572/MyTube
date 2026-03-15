from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
from typing import Any


logger = logging.getLogger(__name__)


class YtDlpError(RuntimeError):
    pass


class YtDlpClient:
    def __init__(self, binary_path: str, ffmpeg_path: str, deno_path: str) -> None:
        self.binary_path = binary_path
        self.ffmpeg_path = ffmpeg_path
        self.deno_path = deno_path

    def ensure_available(self) -> None:
        if shutil.which(self.binary_path) is None and not os.path.exists(self.binary_path):
            raise YtDlpError(
                f"yt-dlp binary not found at '{self.binary_path}'. "
                "Install yt-dlp or set AIRWAVE_YT_DLP_PATH."
            )

    def _run_json(self, *args: str) -> dict[str, Any]:
        cmd = [
            self.binary_path,
            "-v",
            "--js-runtimes",
            f"deno:{self.deno_path}",
            "--js-runtimes",
            "node",
            "--ffmpeg-location",
            self.ffmpeg_path,
            *args,
        ]
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

    def _run_text(self, *args: str) -> str:
        cmd = [
            self.binary_path,
            "--js-runtimes",
            f"deno:{self.deno_path}",
            "--js-runtimes",
            "node",
            "--ffmpeg-location",
            self.ffmpeg_path,
            *args,
        ]
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

    def get_single_json(self, url: str) -> dict[str, Any]:
        return self._run_json("--no-playlist", "--skip-download", "-J", url)

    def get_playlist_json(self, url: str) -> dict[str, Any]:
        return self._run_json("--flat-playlist", "--skip-download", "-J", url)

    def get_stream_url(self, url: str) -> str:
        output = self._run_text("--no-playlist", "-f", "bestaudio/best", "-g", url)
        stream_url = next((line.strip() for line in output.splitlines() if line.strip()), "")
        if not stream_url:
            raise YtDlpError("Could not resolve direct stream URL")
        return stream_url

    def spawn_audio_stream(self, url: str) -> subprocess.Popen[bytes]:
        cmd = [
            self.binary_path,
            "--js-runtimes",
            f"deno:{self.deno_path}",
            "--js-runtimes",
            "node",
            "--ffmpeg-location",
            self.ffmpeg_path,
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

    def search_json(self, query: str, provider: str, limit: int = 10) -> dict[str, Any]:
        bounded_limit = max(1, min(limit, 100))
        search_terms = {
            "youtube": f"ytsearch{bounded_limit}:{query}",
            "soundcloud": f"scsearch{bounded_limit}:{query}",
        }
        search_term = search_terms.get(provider)
        if search_term is None:
            return {"entries": []}
        return self._run_json("--flat-playlist", "--skip-download", "-J", search_term)
