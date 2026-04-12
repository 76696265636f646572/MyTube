from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from app.api.common.dependencies import _services
from app.api.common.models import MusicAtlasGeneratePlaylistRequest
from app.api.common.serializers import serialize_musicatlas_matches_for_queue_ui
from app.db.models import PlayHistory
from app.services.musicatlas_client import (
    MusicAtlasDisabledError,
    MusicAtlasHttpError,
    MusicAtlasKeysExhaustedError,
    MusicAtlasTimeoutError,
    MusicAtlasTransportError,
)
from app.services.musicatlas_client import extract_artist, extract_song_title

router = APIRouter()

_DISABLED_MESSAGE = "MusicAtlas is not configured (set AIRWAVE_MUSICATLAS_API_KEY)."

def _disabled_payload() -> dict[str, Any]:
    return {
        "enabled": False,
        "items": [],
        "message": _DISABLED_MESSAGE,
        "seed": None,
        "notice": None,
        "catalog_ingestion": None,
    }


def _call_musicatlas(request: Request) -> Any:
    client = _services(request)["musicatlas"]
    if client is None or not getattr(client, "enabled", False):
        return None
    return client


def _http_exc_from_musicatlas(exc: Exception) -> HTTPException:
    if isinstance(exc, MusicAtlasKeysExhaustedError):
        return HTTPException(
            status_code=503,
            detail={
                "error": "musicatlas_keys_exhausted",
                "message": str(exc),
                "path": exc.path,
                "last_status_code": exc.last_status_code,
                "keys_tried": exc.keys_tried,
            },
        )
    if isinstance(exc, MusicAtlasHttpError):
        detail: dict[str, Any] = {
            "error": "musicatlas_http_error",
            "message": str(exc),
            "status_code": exc.status_code,
            "path": exc.path,
        }
        if exc.response_body_preview:
            detail["response_body_preview"] = exc.response_body_preview
        code = exc.status_code if 400 <= exc.status_code < 600 else 502
        return HTTPException(status_code=code, detail=detail)
    if isinstance(exc, MusicAtlasTimeoutError):
        return HTTPException(
            status_code=504,
            detail={
                "error": "musicatlas_timeout",
                "message": str(exc),
                "path": exc.path,
                "timeout_seconds": exc.timeout_seconds,
            },
        )
    if isinstance(exc, MusicAtlasTransportError):
        return HTTPException(
            status_code=502,
            detail={"error": "musicatlas_transport", "message": str(exc), "path": exc.path},
        )
    if isinstance(exc, MusicAtlasDisabledError):
        return HTTPException(status_code=503, detail={"error": "musicatlas_disabled", "message": str(exc)})
    return HTTPException(status_code=502, detail={"error": "musicatlas_unknown", "message": str(exc)})


def _parse_embed(embed: int | None) -> int | None:
    if embed is None:
        return None
    if embed in (0, 1):
        return embed
    raise HTTPException(status_code=400, detail="embed must be 0 or 1 when provided")


def _resolve_suggestion_seed(
    *,
    artist_q: str | None,
    track_q: str | None,
    engine: Any,
) -> tuple[str, str]:
    a = (artist_q or "").strip()
    t = (track_q or "").strip()
    if a and t:
        return a, t
    if a or t:
        raise HTTPException(
            status_code=400,
            detail="Provide both artist and track query parameters, or omit both to use the current track.",
        )
    ch = (getattr(engine.state, "now_playing_channel", None) or "").strip()
    title = (getattr(engine.state, "now_playing_title", None) or "").strip()
    ch = extract_artist(ch)
    title = extract_song_title(ch, title)
    if ch and title:
        return ch, title
    raise HTTPException(
        status_code=400,
        detail="Nothing is playing and artist/track were not provided.",
    )


def _history_row_seed(repo: Any, row: PlayHistory) -> dict[str, str] | None:
    title = (row.title or "").strip()
    if not title:
        return None
    artist: str | None = None
    qid = row.queue_item_id
    if qid is not None:
        item = repo.get_item(int(qid))
        if item is not None:
            ch = (item.channel or "").strip()
            if ch:
                artist = ch
    if not artist:
        parts = title.split(" - ", 1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            artist, title = parts[0].strip(), parts[1].strip()
        else:
            artist = "Unknown Artist"
    return {"artist": artist, "title": title}


def _dedupe_liked_tracks(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for it in items:
        artist = (it.get("artist") or "").strip()
        title = (it.get("title") or "").strip()
        if not artist or not title:
            continue
        key = (artist.lower(), title.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({"artist": artist, "title": title})
    return out


def _catalog_ingestion_from_progress(*, job_id: str, progress: dict[str, Any]) -> dict[str, Any]:
    status = str(progress.get("status") or "").strip() or "unknown"
    terminal = status in ("done", "error")
    return {
        "job_id": job_id,
        "status": status,
        "percent_complete": progress.get("percent_complete"),
        "eta_seconds": progress.get("eta_seconds"),
        "message": progress.get("message"),
        "terminal": terminal,
    }


def _fetch_catalog_progress(
    *,
    client: Any,
    job_id: str,
    registry: Any,
) -> dict[str, Any]:
    try:
        progress = client.add_track_progress(job_id=job_id)
    except (
        MusicAtlasKeysExhaustedError,
        MusicAtlasHttpError,
        MusicAtlasTimeoutError,
        MusicAtlasTransportError,
    ) as exc:
        raise _http_exc_from_musicatlas(exc) from exc
    if not isinstance(progress, dict):
        raise HTTPException(status_code=502, detail={"error": "musicatlas_bad_progress_payload"})
    snapshot = _catalog_ingestion_from_progress(job_id=job_id, progress=progress)
    if snapshot["terminal"]:
        registry.mark_terminal(job_id)
    return snapshot


def _build_multi_seeds(request: Request, payload: MusicAtlasGeneratePlaylistRequest) -> list[dict[str, str]]:
    services = _services(request)
    repo = services["repo"]
    engine = services["engine"]
    candidates: list[dict[str, str]] = []

    if payload.include_now_playing:
        ch = (getattr(engine.state, "now_playing_channel", None) or "").strip()
        title = (getattr(engine.state, "now_playing_title", None) or "").strip()
        if ch and title:
            candidates.append({"artist": ch, "title": title})

    history = repo.list_history(limit=payload.history_limit)
    for row in history:
        seed = _history_row_seed(repo, row)
        if seed is not None:
            candidates.append(seed)

    deduped = _dedupe_liked_tracks(candidates)
    return deduped[: payload.max_seeds]


@router.get("/suggestions")
def musicatlas_suggestions(
    request: Request,
    artist: str | None = Query(default=None),
    track: str | None = Query(default=None),
    embed: int | None = Query(default=None),
    catalog_job_id: str | None = Query(default=None),
) -> dict[str, Any]:
    client = _call_musicatlas(request)
    if client is None:
        return _disabled_payload()

    services = _services(request)
    registry = services.get("musicatlas_catalog_jobs")
    job_param = (catalog_job_id or "").strip()
    if job_param:
        if registry is None:
            raise HTTPException(
                status_code=503,
                detail={"error": "musicatlas_catalog_jobs_unavailable", "message": "Catalog job registry is not initialized."},
            )
        registry.prune_expired()
        if registry.get_seed_for_job(job_param) is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "musicatlas_unknown_catalog_job",
                    "message": "Unknown or expired catalog_job_id for this server process.",
                },
            )
        catalog_ingestion = _fetch_catalog_progress(client=client, job_id=job_param, registry=registry)
        seed_out: dict[str, str] | None = None
        a = (artist or "").strip()
        t = (track or "").strip()
        if a and t:
            seed_out = {"artist": a, "track": _extract_song_title(a, t)}
        return {
            "enabled": True,
            "items": [],
            "seed": seed_out,
            "notice": None,
            "catalog_ingestion": catalog_ingestion,
        }

    seed_artist, seed_track = _resolve_suggestion_seed(
        artist_q=artist,
        track_q=track,
        engine=services["engine"],
    )
    embed_val = _parse_embed(embed)

    try:
        raw = client.similar_tracks(artist=seed_artist, track=seed_track, embed=embed_val)
    except MusicAtlasDisabledError:
        return _disabled_payload()
    except (
        MusicAtlasKeysExhaustedError,
        MusicAtlasHttpError,
        MusicAtlasTimeoutError,
        MusicAtlasTransportError,
    ) as exc:
        raise _http_exc_from_musicatlas(exc) from exc

    matches = raw.get("matches") if isinstance(raw, dict) else None
    match_list = matches if isinstance(matches, list) else []
    items = serialize_musicatlas_matches_for_queue_ui(match_list)
    notice: str | None = None
    catalog_ingestion: dict[str, Any] | None = None
    if isinstance(raw, dict) and raw.get("in_catalog") is False:
        notice = str(raw.get("message") or "Track not found in MusicAtlas catalog.")
        if registry is not None:
            registry.prune_expired()
            job_id: str | None = registry.get_active_job_id(seed_artist, seed_track)
            if job_id is None:
                try:
                    add_status, add_body = client.add_track(artist=seed_artist, title=seed_track)
                except (
                    MusicAtlasKeysExhaustedError,
                    MusicAtlasHttpError,
                    MusicAtlasTimeoutError,
                    MusicAtlasTransportError,
                ) as exc:
                    raise _http_exc_from_musicatlas(exc) from exc
                if add_status == 409:
                    registry.forget_seed(seed_artist, seed_track)
                    catalog_ingestion = {
                        "job_id": None,
                        "status": "conflict",
                        "percent_complete": None,
                        "eta_seconds": None,
                        "message": str(add_body.get("message") or "Track is already in the MusicAtlas catalog."),
                        "terminal": True,
                    }
                    notice = str(
                        add_body.get("message") or (notice or "Track is already in the MusicAtlas catalog.")
                    )
                else:
                    new_job = str(add_body.get("job_id") or "").strip()
                    if not new_job:
                        raise HTTPException(
                            status_code=502,
                            detail={"error": "musicatlas_missing_job_id", "message": "add_track response missing job_id."},
                        )
                    registry.register_job(seed_artist, seed_track, new_job)
                    job_id = new_job
            if job_id is not None:
                catalog_ingestion = _fetch_catalog_progress(
                    client=client,
                    job_id=job_id,
                    registry=registry,
                )

    return {
        "enabled": True,
        "items": items,
        "seed": {"artist": seed_artist, "track": seed_track},
        "notice": notice,
        "catalog_ingestion": catalog_ingestion,
    }


@router.post("/generate-playlist")
def musicatlas_generate_playlist(
    request: Request,
    payload: MusicAtlasGeneratePlaylistRequest = Body(default_factory=MusicAtlasGeneratePlaylistRequest),
) -> dict[str, Any]:
    client = _call_musicatlas(request)
    if client is None:
        return _disabled_payload()

    liked = _build_multi_seeds(request, payload)
    if not liked:
        raise HTTPException(
            status_code=400,
            detail="No seed tracks available from now playing or play history.",
        )

    try:
        raw = client.similar_tracks_multi(liked_tracks=liked)
    except MusicAtlasDisabledError:
        return _disabled_payload()
    except (
        MusicAtlasKeysExhaustedError,
        MusicAtlasHttpError,
        MusicAtlasTimeoutError,
        MusicAtlasTransportError,
    ) as exc:
        raise _http_exc_from_musicatlas(exc) from exc

    matches = raw.get("matches") if isinstance(raw, dict) else None
    match_list = matches if isinstance(matches, list) else []
    items = serialize_musicatlas_matches_for_queue_ui(match_list)
    notice: str | None = None
    if isinstance(raw, dict) and raw.get("success") is False:
        notice = str(raw.get("message") or "MusicAtlas could not build recommendations.")

    return {
        "enabled": True,
        "items": items,
        "seeds": liked,
        "notice": notice,
    }
