from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


class SpotdlError(RuntimeError):
    pass


class SpotdlClient:
    def __init__(self, binary_path: str) -> None:
        self.binary_path = binary_path

    def ensure_available(self) -> None:
        if shutil.which(self.binary_path) is None and not os.path.exists(self.binary_path):
            raise SpotdlError(
                f"spotdl binary not found at '{self.binary_path}'. "
                "Install spotdl or set AIRWAVE_SPOTDL_PATH."
            )

    def fetch_playlist_metadata(self, url: str) -> dict[str, Any]:
        self.ensure_available()
        with TemporaryDirectory(prefix="airwave-spotdl-") as temp_dir:
            save_path = Path(temp_dir) / "playlist.spotdl"
            cmd = [
                self.binary_path,
                "save",
                url,
                "--save-file",
                str(save_path),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "").strip()
                raise SpotdlError(detail or "spotdl save failed")
            if not save_path.exists():
                raise SpotdlError("spotdl did not produce a save file")
            try:
                payload = json.loads(save_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise SpotdlError("Failed parsing spotdl save output") from exc
        if not isinstance(payload, list):
            raise SpotdlError("spotdl save output format was not a track list")
        return {"entries": payload}
