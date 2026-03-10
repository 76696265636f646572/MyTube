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

