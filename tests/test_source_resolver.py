from unittest.mock import patch

from app.services.resolver.direct_resolver import DirectUrlResolver
from app.services.resolver.extractors import get_extractor, duration_seconds_parse
from app.services.resolver.extractors import generic, soundcloud, youtube
from app.services.resolver.extractors._common import normalize_upload_date
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


def test_extractor_duration_seconds_parse():
    """Shared duration parsing used by all extractors."""
    assert duration_seconds_parse(242.0) == 242
    assert duration_seconds_parse("340.9") == 340
    assert duration_seconds_parse(None) is None
    assert duration_seconds_parse(100) == 100


def test_youtube_extractor_title_uses_title():
    ext = youtube.youtube_extractor
    assert ext.title_from_info({"title": "My Track"}) == "My Track"
    assert ext.title_from_info({"title": "  Trimmed  "}) == "Trimmed"
    assert ext.title_from_info({}) is None
    assert ext.title_from_info({"fulltitle": "Ignored"}) is None


def test_youtube_extractor_thumbnail_uses_thumbnail():
    ext = youtube.youtube_extractor
    assert ext.thumbnail_from_info({"thumbnail": "https://example.com/thumb.jpg"}) == "https://example.com/thumb.jpg"
    assert ext.thumbnail_from_info({}) is None


def test_youtube_extractor_channel_uses_uploader_or_channel():
    ext = youtube.youtube_extractor
    assert ext.channel_from_info({"uploader": "Channel A"}) == "Channel A"
    assert ext.channel_from_info({"channel": "Channel B"}) == "Channel B"
    assert ext.channel_from_info({"uploader": "A", "channel": "B"}) == "A"


def test_soundcloud_extractor_title_prefers_fulltitle():
    """SoundCloud search/flat-playlist often uses fulltitle."""
    ext = soundcloud.soundcloud_extractor
    assert ext.title_from_info({"fulltitle": "Drum and Bass Mix 2026"}) == "Drum and Bass Mix 2026"
    assert ext.title_from_info({"title": "Fallback Title"}) == "Fallback Title"
    assert ext.title_from_info({"title": "Title", "fulltitle": "Full"}) == "Full"
    assert ext.title_from_info({}) is None


def test_soundcloud_extractor_thumbnail_uses_artwork_url_then_thumbnails():
    ext = soundcloud.soundcloud_extractor
    info = {"artwork_url": "https://i1.sndcdn.com/artworks-abc-large.jpg"}
    assert ext.thumbnail_from_info(info) == "https://i1.sndcdn.com/artworks-abc-large.jpg"
    assert ext.thumbnail_from_info({}) is None
    assert ext.thumbnail_from_info({"thumbnail": "", "artwork_url": "https://art.jpg"}) == "https://art.jpg"
    thumb_list = [{"id": "t300x300", "url": "https://thumb300.jpg"}]
    assert ext.thumbnail_from_info({"thumbnails": thumb_list}) == "https://thumb300.jpg"


def test_generic_extractor_title_fallback_title_or_fulltitle():
    ext = generic.generic_extractor
    assert ext.title_from_info({"title": "My Track"}) == "My Track"
    assert ext.title_from_info({"fulltitle": "Drum and Bass Mix 2026"}) == "Drum and Bass Mix 2026"
    assert ext.title_from_info({"title": "Title", "fulltitle": "Full"}) == "Title"
    assert ext.title_from_info({}) is None
    assert ext.title_from_info({"title": "", "fulltitle": "Fallback"}) == "Fallback"


def test_generic_extractor_thumbnail_fallback_thumbnail_artwork_thumbnails():
    ext = generic.generic_extractor
    assert ext.thumbnail_from_info({"thumbnail": "https://example.com/thumb.jpg"}) == "https://example.com/thumb.jpg"
    assert ext.thumbnail_from_info({"artwork_url": "https://i1.sndcdn.com/artworks-abc.jpg"}) == "https://i1.sndcdn.com/artworks-abc.jpg"
    assert ext.thumbnail_from_info({}) is None


def test_normalize_upload_date_from_upload_date_yyyymmdd():
    assert normalize_upload_date({"upload_date": "20230510"}) == "2023-05-10"
    assert normalize_upload_date({"upload_date": "20101028"}) == "2010-10-28"
    assert normalize_upload_date({}) is None
    assert normalize_upload_date({"upload_date": "invalid"}) is None
    assert normalize_upload_date({"upload_date": "123"}) is None


def test_normalize_upload_date_from_timestamp():
    # 2023-05-10 00:00:00 UTC
    assert normalize_upload_date({"timestamp": 1683676800}) == "2023-05-10"
    assert normalize_upload_date({"upload_date_timestamp": 1683676800}) == "2023-05-10"
    assert normalize_upload_date({"timestamp": 1683676800, "upload_date": "20230510"}) == "2023-05-10"


def test_extractor_uploaded_at_from_info():
    for ext in (youtube.youtube_extractor, soundcloud.soundcloud_extractor, generic.generic_extractor):
        assert ext.uploaded_at_from_info({"upload_date": "20230510"}) == "2023-05-10"
        assert ext.uploaded_at_from_info({"timestamp": 1683676800}) == "2023-05-10"
        assert ext.uploaded_at_from_info({}) is None


def test_get_extractor_dispatches_by_extractor_key():
    assert get_extractor({"extractor": "youtube"}) is youtube.youtube_extractor
    assert get_extractor({"extractor": "Soundcloud"}) is soundcloud.soundcloud_extractor
    assert get_extractor({"extractor_key": "Youtube"}) is youtube.youtube_extractor
    assert get_extractor({"extractor": "vimeo"}) is generic.generic_extractor
    assert get_extractor({}) is generic.generic_extractor


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
                "upload_date": "20240115",
            }
        ],
    }
    with patch.object(resolver, "_run_json", return_value=fake_data):
        track = resolver.resolve_video("https://soundcloud.com/user/drum-and-bass-mix-2026")
    assert track.title == "Drum and Bass Mix 2026"
    assert track.stream_url == "https://cdn.soundcloud.com/stream/abc"
    assert track.channel == "DJ User"
    assert track.uploaded_at == "2024-01-15"

