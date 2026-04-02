from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.db.repository import Repository
from app.services.ffmpeg_pipeline import FfmpegPipeline
from app.services.playlist_service import PlaylistService
from app.services.source_resolver import MediaSourceResolver
from app.services.yt_dlp_service import ResolvedTrack, YtDlpService


class FakeFfmpegProbe(FfmpegPipeline):
    def __init__(self) -> None:
        super().__init__("/bin/ffmpeg")

    def probe_audio_streams(self, source: str) -> dict:  # noqa: ARG002
        return {
            "has_audio": True,
            "duration_seconds": 10.0,
            "audio_stream_count": 1,
            "title": None,
            "artist": None,
            "format_name": "mp3",
        }


def test_list_candidate_audio_files_recursive(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "a.mp3").write_bytes(b"x")
    sub = root / "sub"
    sub.mkdir()
    (sub / "b.mp3").write_bytes(b"x")
    (root / "skip.txt").write_bytes(b"x")
    ffmpeg = FakeFfmpegProbe()
    resolver = MediaSourceResolver(ffmpeg, [str(root)])
    shallow = resolver.list_candidate_audio_files(str(root), recursive=False)
    assert sorted(shallow) == [str((root / "a.mp3").resolve())]
    deep = resolver.list_candidate_audio_files(str(root), recursive=True)
    assert len(deep) == 2


def test_add_local_folder_queues_multiple(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/q.db")
    repo.init_db()
    root = tmp_path / "m"
    root.mkdir()
    (root / "1.mp3").write_bytes(b"x")
    (root / "2.mp3").write_bytes(b"x")
    ffmpeg = FakeFfmpegProbe()
    resolver = MediaSourceResolver(ffmpeg, [str(root)])
    yt = MagicMock(spec=YtDlpService)
    pl = PlaylistService(repo, yt, resolver)
    result = pl.add_local_folder(str(root), recursive=False)
    assert result["type"] == "folder"
    assert result["count"] == 2
    assert len(repo.list_queue()) == 2


def test_add_local_folder_to_playlist_uses_dedupe(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/p.db")
    repo.init_db()
    root = tmp_path / "m"
    root.mkdir()
    (root / "t.mp3").write_bytes(b"x")
    ffmpeg = FakeFfmpegProbe()
    resolver = MediaSourceResolver(ffmpeg, [str(root)])
    yt = MagicMock(spec=YtDlpService)
    pl = PlaylistService(repo, yt, resolver)
    playlist = repo.create_custom_playlist(title="P")
    pid = playlist.id
    pl.add_local_folder_to_playlist(pid, str(root), recursive=False, import_mode="add_all")
    r2 = pl.add_local_folder_to_playlist(pid, str(root), recursive=False, import_mode="skip_duplicates")
    assert r2.get("skipped_duplicates") is True
    assert len(repo.list_playlist_entries(pid)) == 1
