from app.services.extractors.dispatcher import ExtractorDispatcher
from app.services.extractors.mixcloud import MixcloudExtractor
from app.services.extractors.soundcloud import SoundCloudExtractor
from app.services.extractors.youtube import YouTubeExtractor


def test_dispatcher_provider_and_playlist_detection():
    dispatcher = ExtractorDispatcher()
    assert dispatcher.detect_provider("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"
    assert dispatcher.is_playlist_url("https://www.youtube.com/playlist?list=PL123") is True
    assert dispatcher.is_playlist_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is False
    assert dispatcher.detect_provider("https://soundcloud.com/artist/track") == "soundcloud"
    assert dispatcher.is_playlist_url("https://soundcloud.com/artist/sets/party") is True
    assert dispatcher.detect_provider("https://www.mixcloud.com/user/show/") == "mixcloud"
    assert dispatcher.is_playlist_url("https://www.mixcloud.com/user/show/") is False


def test_youtube_single_and_playlist_extraction():
    extractor = YouTubeExtractor()
    single_raw = {
        "id": "dQw4w9WgXcQ",
        "title": "Never Gonna Give You Up",
        "uploader": "Rick Astley",
        "duration": 213,
        "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    }
    single = extractor.extract_single("https://youtu.be/dQw4w9WgXcQ", single_raw)
    assert single.provider == "youtube"
    assert single.provider_item_id == "dQw4w9WgXcQ"
    assert single.source_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert single.duration_seconds == 213

    playlist_raw = {
        "title": "Sample Playlist",
        "entries": [
            {"id": "abc123", "title": "Track A", "uploader": "Channel A", "duration": 100},
            {"id": "def456", "title": "Track B", "uploader": "Channel B", "duration": 200},
            {"title": "Missing id"},
        ],
    }
    collection = extractor.extract_playlist("https://www.youtube.com/playlist?list=PL123", playlist_raw)
    assert collection.provider == "youtube"
    assert collection.title == "Sample Playlist"
    assert len(collection.items) == 2
    assert collection.items[0].source_url == "https://www.youtube.com/watch?v=abc123"


def test_soundcloud_single_and_playlist_extraction():
    extractor = SoundCloudExtractor()
    single_raw = {
        "id": 987654321,
        "title": "Atomic Technopsytrance DJ Set",
        "uploader": "cristobalpesce",
        "duration": 3120,
        "thumbnail": "https://i1.sndcdn.com/artworks-xyz-t500x500.jpg",
        "webpage_url": "https://soundcloud.com/cristobalpesce/atomic-technopsytrance-dj-set",
    }
    single = extractor.extract_single(single_raw["webpage_url"], single_raw)
    assert single.provider == "soundcloud"
    assert single.provider_item_id == "987654321"
    assert single.title == "Atomic Technopsytrance DJ Set"
    assert single.thumbnail_url == "https://i1.sndcdn.com/artworks-xyz-t500x500.jpg"

    playlist_raw = {
        "title": "Where The Party At",
        "entries": [
            {
                "id": 1,
                "title": "Track 1",
                "uploader": "le_boeuf",
                "duration": 180,
                "webpage_url": "https://soundcloud.com/le_boeuf/track-1",
                "thumbnails": [
                    {"id": "small", "url": "https://i1.sndcdn.com/track-1-small.jpg", "width": 32, "height": 32},
                    {"id": "t500x500", "url": "https://i1.sndcdn.com/track-1-500.jpg", "width": 500, "height": 500},
                ],
            },
            {
                "id": 2,
                "title": "Track 2",
                "uploader": "le_boeuf",
                "duration": None,
                "webpage_url": "https://soundcloud.com/le_boeuf/track-2",
            },
        ],
    }
    collection = extractor.extract_playlist("https://soundcloud.com/le_boeuf/sets/where-the-party-at", playlist_raw)
    assert collection.provider == "soundcloud"
    assert len(collection.items) == 2
    assert collection.items[1].duration_seconds is None
    assert collection.items[0].thumbnail_url == "https://i1.sndcdn.com/track-1-500.jpg"


def test_soundcloud_single_uses_thumbnails_when_thumbnail_missing():
    extractor = SoundCloudExtractor()
    single_raw = {
        "id": 2140467141,
        "title": "Before You",
        "uploader": "Bailey Zimmerman",
        "duration": 171.25,
        "webpage_url": "https://soundcloud.com/baileyzimmerman-music/before-you",
        "thumbnails": [
            {"id": "small", "url": "https://i1.sndcdn.com/artworks-small.jpg", "width": 32, "height": 32},
            {"id": "original", "url": "https://i1.sndcdn.com/artworks-original.jpg", "preference": 10},
        ],
    }
    single = extractor.extract_single(single_raw["webpage_url"], single_raw)
    assert single.thumbnail_url == "https://i1.sndcdn.com/artworks-original.jpg"


def test_mixcloud_single_extraction_and_playlist_not_supported():
    extractor = MixcloudExtractor()
    single_raw = {
        "id": "12345",
        "title": "Totally 80s Dance Mix",
        "uploader": "cristinabalce",
        "duration": 3580,
        "webpage_url": "https://www.mixcloud.com/cristinabalce/totally-80s-dance-mix/",
    }
    single = extractor.extract_single(single_raw["webpage_url"], single_raw)
    assert single.provider == "mixcloud"
    assert single.provider_item_id == "12345"
    assert single.duration_seconds == 3580

    try:
        extractor.extract_playlist("https://www.mixcloud.com/discover/electronic/", {"entries": []})
    except NotImplementedError:
        pass
    else:
        raise AssertionError("Expected Mixcloud playlist extraction to be unsupported")
