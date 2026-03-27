from app.services.spotify_free_service import (
    is_spotify_playlist_url,
    normalize_spotify_playlist_url,
    spotify_playlist_id_from_url,
)


def test_spotify_playlist_id_from_url_open_and_www():
    assert spotify_playlist_id_from_url("https://open.spotify.com/playlist/5HjIEt9cfj8xds1hwhqENb?si=07123ef4876e4c37") == "5HjIEt9cfj8xds1hwhqENb"
    assert spotify_playlist_id_from_url("https://www.spotify.com/playlist/abcXYZ") == "abcXYZ"


def test_spotify_playlist_id_rejects_non_playlist():
    assert spotify_playlist_id_from_url("https://open.spotify.com/track/67Hna13dNDkZvBpTXRIaOJ") is None
    assert spotify_playlist_id_from_url("https://youtube.com/playlist?list=x") is None


def test_is_spotify_playlist_url():
    assert is_spotify_playlist_url("https://open.spotify.com/playlist/abc")
    assert not is_spotify_playlist_url("https://open.spotify.com/album/abc")


def test_normalize_spotify_playlist_url():
    assert normalize_spotify_playlist_url("5HjIEt9cfj8xds1hwhqENb") == "https://open.spotify.com/playlist/5HjIEt9cfj8xds1hwhqENb"
