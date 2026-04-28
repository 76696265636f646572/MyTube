from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from app.api.common.dependencies import _services
from app.api.common.models import MusicAtlasGeneratePlaylistRequest
from app.api.common.serializers import serialize_musicatlas_matches_for_queue_ui
from app.services.musicatlas_client import (
    MusicAtlasDisabledError,
    MusicAtlasHttpError,
    MusicAtlasKeysExhaustedError,
    MusicAtlasTimeoutError,
    MusicAtlasTransportError,
)
from app.services.musicatlas_client import extract_artist_song_title
from app.services.musicatlas_playlist_service import MusicAtlasSeedOptions, build_musicatlas_liked_tracks

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


@router.get("/status")
def musicatlas_status(request: Request) -> dict[str, Any]:
    client = _call_musicatlas(request)
    if client is None:
        return {"enabled": False, "message": _DISABLED_MESSAGE}
    return {"enabled": True, "message": None}


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
    artist, title = extract_artist_song_title(ch, title)
    if artist:
        ch = artist
    if ch and title:
        return ch, title
    raise HTTPException(
        status_code=400,
        detail="Nothing is playing and artist/track were not provided.",
    )


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
    return build_musicatlas_liked_tracks(
        repository=services["repo"],
        stream_engine=services["engine"],
        seed_options=MusicAtlasSeedOptions(
            history_limit=payload.history_limit,
            max_seeds=payload.max_seeds,
            include_now_playing=payload.include_now_playing,
        ),
    )


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

    if artist == "_airwave_probe" and track == "_airwave_probe":
        return {
            "enabled": True,
            "items": [],
            "seed": {"artist": artist, "track": track},
            "notice": None,
            "catalog_ingestion": None,
        }

    services = _services(request)
    registry = services.get("musicatlas_catalog_jobs")
    artist, track = extract_artist_song_title(artist, track)
    job_param = (catalog_job_id or "").strip()
    if job_param:
        if registry is None:
            raise HTTPException(
                status_code=503,
                detail={"error": "musicatlas_catalog_jobs_unavailable", "message": "Catalog job registry is not initialized."},
            )
        registry.prune_expired()
        seed = registry.get_seed_for_job(job_param)
        if seed is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "musicatlas_unknown_catalog_job",
                    "message": "Unknown or expired catalog_job_id for this server process.",
                },
            )
        catalog_ingestion = _fetch_catalog_progress(client=client, job_id=job_param, registry=registry)
        seed_artist, seed_track = seed
        a = (artist or "").strip()
        t = (track or "").strip()
        if (a and a.lower() != seed_artist.lower()) or (t and t.lower() != seed_track.lower()):
            raise HTTPException(
                status_code=400,
                detail={"error": "musicatlas_catalog_job_seed_mismatch"},
            )
        seed_out = {"artist": seed_artist, "track": seed_track}
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
