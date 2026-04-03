from __future__ import annotations

import pathlib
from unittest.mock import MagicMock

import pytest

from app.db.repository import NewQueueItem, Repository
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


def test_list_candidate_audio_files_uses_natural_order(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    for name in ("track 1.mp3", "track 10.mp3", "track 2.mp3"):
        (root / name).write_bytes(b"x")
    ffmpeg = FakeFfmpegProbe()
    resolver = MediaSourceResolver(ffmpeg, [str(root)])

    ordered = resolver.list_candidate_audio_files(str(root), recursive=False)

    assert [path.rsplit("/", 1)[-1] for path in ordered] == [
        "track 1.mp3",
        "track 2.mp3",
        "track 10.mp3",
    ]


def test_list_candidate_audio_files_groups_recursive_subfolders(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    folder_a = root / "folder a"
    folder_b = root / "folder b"
    folder_a.mkdir()
    folder_b.mkdir()
    for name in ("song 1.mp3", "song 3.mp3", "song 2.mp3"):
        (folder_a / name).write_bytes(b"x")
        (folder_b / name).write_bytes(b"x")
    ffmpeg = FakeFfmpegProbe()
    resolver = MediaSourceResolver(ffmpeg, [str(root)])

    ordered = resolver.list_candidate_audio_files(str(root), recursive=True)

    assert [str(pathlib.Path(path).relative_to(root)) for path in ordered] == [
        "folder a/song 1.mp3",
        "folder a/song 2.mp3",
        "folder a/song 3.mp3",
        "folder b/song 1.mp3",
        "folder b/song 2.mp3",
        "folder b/song 3.mp3",
    ]


def test_reorder_queued_items_moves_entire_folder_block_before_existing(tmp_path):
    """Guards play-now-local-folder: all new folder tracks must play as a contiguous block next."""
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/q.db")
    repo.init_db()

    def qitem(label: str) -> NewQueueItem:
        return NewQueueItem(
            source_url=f"local://{label}",
            normalized_url=f"local://{label}",
            source_type="file",
            title=label,
        )

    first_batch = repo.enqueue_items([qitem("prior_a"), qitem("prior_b")])
    a_id, b_id = first_batch[0].id, first_batch[1].id
    folder_batch = repo.enqueue_items([qitem("f1"), qitem("f2")])
    c_id, d_id = folder_batch[0].id, folder_batch[1].id

    repo.reorder_queued_items([c_id, d_id])
    assert repo.list_queued_ids() == [c_id, d_id, a_id, b_id]


def test_add_local_folder_queues_multiple(tmp_path):
    repo = Repository(f"sqlite+pysqlite:///{tmp_path}/q.db")
    repo.init_db()
    root = tmp_path / "m"
    root.mkdir()
    (root / "track 1.mp3").write_bytes(b"x")
    (root / "track 10.mp3").write_bytes(b"x")
    (root / "track 2.mp3").write_bytes(b"x")
    ffmpeg = FakeFfmpegProbe()
    resolver = MediaSourceResolver(ffmpeg, [str(root)])
    yt = MagicMock(spec=YtDlpService)
    pl = PlaylistService(repo, yt, resolver)
    result = pl.add_local_folder(str(root), recursive=False)
    assert result["type"] == "folder"
    assert result["count"] == 3
    assert [item.title for item in repo.list_queue()] == [
        "track 1.mp3",
        "track 2.mp3",
        "track 10.mp3",
    ]


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
