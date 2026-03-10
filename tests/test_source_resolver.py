from unittest.mock import patch

from app.services.resolver.direct_resolver import DirectUrlResolver
from app.services.resolver.yt_dlp_resolver import YtDlpResolver
from app.services.source_resolver import CompositeSourceResolver


def test_direct_resolver_handles_generic_live_stream_url():
    resolver = DirectUrlResolver()
    assert resolver.can_handle_url("https://radio.example.com/live/stream")
    resolved = resolver.resolve_video("https://radio.example.com/live/stream")
    assert resolved.is_live is True
    assert resolved.can_seek is False


def test_direct_resolver_rejects_plain_web_page_without_stream_hints():
    resolver = DirectUrlResolver()
    assert resolver.can_handle_url("https://example.com/about") is False


def test_direct_resolver_does_not_handle_youtube_url():
    resolver = DirectUrlResolver()
    assert resolver.can_handle_url("https://www.youtube.com/watch?v=abc") is False


def test_composite_resolver_filters_search_sites():
    composite = CompositeSourceResolver(
        yt_dlp_resolver=YtDlpResolver("/bin/echo"),
        direct_resolver=DirectUrlResolver(),
        searchable_sites=["youtube", "soundcloud"],
        default_enabled_search_sites=["youtube", "soundcloud"],
    )
    assert composite.effective_search_sites(["youtube", "vimeo"]) == ["youtube"]
    assert composite.searchable_sites_payload() == {
        "sites": ["youtube", "soundcloud"],
        "default_enabled_sites": ["youtube", "soundcloud"],
    }


def test_composite_resolver_empty_default_enabled_returns_no_sites():
    composite = CompositeSourceResolver(
        yt_dlp_resolver=YtDlpResolver("/bin/echo"),
        direct_resolver=DirectUrlResolver(),
        searchable_sites=["youtube", "soundcloud", "vimeo"],
        default_enabled_search_sites=[],
    )
    assert composite.effective_search_sites() == []
    assert composite.effective_search_sites([]) == []
    payload = composite.searchable_sites_payload()
    assert payload["sites"] == ["youtube", "soundcloud", "vimeo"]
    assert payload["default_enabled_sites"] == []


def test_yt_dlp_resolver_coerces_float_duration_seconds():
    assert YtDlpResolver._duration_seconds(242.0) == 242
    assert YtDlpResolver._duration_seconds("340.9") == 340
    assert YtDlpResolver._duration_seconds(None) is None


def test_yt_dlp_resolver_title_from_info_uses_title():
    assert YtDlpResolver._title_from_info({"title": "My Track"}) == "My Track"
    assert YtDlpResolver._title_from_info({"title": "  Trimmed  "}) == "Trimmed"


def test_yt_dlp_resolver_title_from_info_falls_back_to_fulltitle():
    """Some extractors (e.g. SoundCloud) provide fulltitle instead of title."""
    assert YtDlpResolver._title_from_info({"fulltitle": "Drum and Bass Mix 2026"}) == "Drum and Bass Mix 2026"
    assert YtDlpResolver._title_from_info({}) is None
    assert YtDlpResolver._title_from_info({"title": "", "fulltitle": "Fallback"}) == "Fallback"


def test_yt_dlp_resolver_title_from_info_prefers_title_over_fulltitle():
    assert YtDlpResolver._title_from_info({"title": "Title", "fulltitle": "Full"}) == "Title"


def test_yt_dlp_resolver_title_from_info_returns_none_when_both_missing_or_empty():
    assert YtDlpResolver._title_from_info({}) is None
    assert YtDlpResolver._title_from_info({"title": "", "fulltitle": ""}) is None
    assert YtDlpResolver._title_from_info({"title": None, "fulltitle": None}) is None


def test_yt_dlp_resolver_thumbnail_from_info_uses_thumbnail():
    assert YtDlpResolver._thumbnail_from_info({"thumbnail": "https://example.com/thumb.jpg"}) == "https://example.com/thumb.jpg"


def test_yt_dlp_resolver_thumbnail_from_info_falls_back_to_artwork_url():
    """SoundCloud uses artwork_url instead of thumbnail."""
    info = {"artwork_url": "https://i1.sndcdn.com/artworks-abc-large.jpg"}
    assert YtDlpResolver._thumbnail_from_info(info) == "https://i1.sndcdn.com/artworks-abc-large.jpg"
    assert YtDlpResolver._thumbnail_from_info({}) is None
    assert YtDlpResolver._thumbnail_from_info({"thumbnail": "", "artwork_url": "https://art.jpg"}) == "https://art.jpg"


def test_yt_dlp_resolver_resolve_video_uses_single_entry_when_playlist_returned():
    """When yt-dlp returns a single-entry playlist (e.g. SoundCloud), resolve_video uses that entry for title/url."""
    resolver = YtDlpResolver("/usr/bin/true")
    # Top-level has no url/title; real data is in entries[0] (e.g. SoundCloud)
    fake_data = {
        "_type": "playlist",
        "entries": [
            {
                "url": "https://cdn.soundcloud.com/stream/abc",
                "fulltitle": "Drum and Bass Mix 2026",
                "uploader": "DJ User",
                "duration": 3600,
                "thumbnail": "https://i1.sndcdn.com/art.jpg",
            }
        ],
    }
    with patch.object(resolver, "_run_json", return_value=fake_data):
        track = resolver.resolve_video("https://soundcloud.com/user/drum-and-bass-mix-2026")
    assert track.title == "Drum and Bass Mix 2026"
    assert track.stream_url == "https://cdn.soundcloud.com/stream/abc"
    assert track.channel == "DJ User"

