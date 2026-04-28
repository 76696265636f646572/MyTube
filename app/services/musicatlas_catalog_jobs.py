from __future__ import annotations

import threading
import time
from dataclasses import dataclass


def normalize_catalog_seed_key(artist: str, track: str) -> tuple[str, str]:
    return (artist.strip().lower(), track.strip().lower())


@dataclass
class _JobRecord:
    seed_key: tuple[str, str]
    seed_display: tuple[str, str]
    terminal: bool
    expires_at_monotonic: float


class MusicAtlasCatalogJobRegistry:
    """
    In-process registry for MusicAtlas catalog-ingestion jobs (add_track).

    - Dedupes add_track by normalized (artist, track) while a job is non-terminal.
    - Retains job_id after terminal states for a TTL so progress-only polling still validates.
    """

    def __init__(self, *, ttl_after_terminal_seconds: float) -> None:
        self._ttl = max(1.0, float(ttl_after_terminal_seconds))
        self._lock = threading.Lock()
        self._seed_to_job: dict[tuple[str, str], str] = {}
        self._jobs: dict[str, _JobRecord] = {}

    def prune_expired(self) -> None:
        now = time.monotonic()
        with self._lock:
            dead: list[str] = []
            for job_id, rec in self._jobs.items():
                if rec.expires_at_monotonic <= now:
                    dead.append(job_id)
            for job_id in dead:
                self._drop_job_locked(job_id)

    def get_active_job_id(self, artist: str, track: str) -> str | None:
        key = normalize_catalog_seed_key(artist, track)
        with self._lock:
            self._prune_expired_locked()
            job_id = self._seed_to_job.get(key)
            if not job_id:
                return None
            rec = self._jobs.get(job_id)
            if rec is None or rec.terminal:
                return None
            return job_id

    def register_job(self, artist: str, track: str, job_id: str) -> None:
        key = normalize_catalog_seed_key(artist, track)
        display = (artist.strip(), track.strip())
        with self._lock:
            self._prune_expired_locked()
            self._seed_to_job[key] = job_id
            self._jobs[job_id] = _JobRecord(
                seed_key=key,
                seed_display=display,
                terminal=False,
                expires_at_monotonic=float("inf"),
            )

    def mark_terminal(self, job_id: str) -> None:
        deadline = time.monotonic() + self._ttl
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec is None:
                return
            rec.terminal = True
            rec.expires_at_monotonic = deadline
            if self._seed_to_job.get(rec.seed_key) == job_id:
                del self._seed_to_job[rec.seed_key]

    def forget_seed(self, artist: str, track: str) -> None:
        key = normalize_catalog_seed_key(artist, track)
        with self._lock:
            job_id = self._seed_to_job.pop(key, None)
            if job_id is not None and job_id in self._jobs:
                self._drop_job_locked(job_id)

    def get_seed_for_job(self, job_id: str) -> tuple[str, str] | None:
        with self._lock:
            self._prune_expired_locked()
            rec = self._jobs.get(job_id)
            if rec is None:
                return None
            return rec.seed_display

    def _prune_expired_locked(self) -> None:
        now = time.monotonic()
        dead = [jid for jid, rec in self._jobs.items() if rec.expires_at_monotonic <= now]
        for jid in dead:
            self._drop_job_locked(jid)

    def _drop_job_locked(self, job_id: str) -> None:
        rec = self._jobs.pop(job_id, None)
        if rec is None:
            return
        if self._seed_to_job.get(rec.seed_key) == job_id:
            del self._seed_to_job[rec.seed_key]
