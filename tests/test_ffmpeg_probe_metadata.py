from app.services.ffmpeg_pipeline import _looks_like_audio_stream_codec_label


def test_looks_like_codec_label_flags_common_stream_titles():
    assert _looks_like_audio_stream_codec_label("TrueHD 7.1 Atmos")
    assert _looks_like_audio_stream_codec_label("DTS-HD Master Audio 5.1")
    assert _looks_like_audio_stream_codec_label("E-AC-3 JOC 5.1")


def test_looks_like_codec_label_allows_real_titles():
    assert not _looks_like_audio_stream_codec_label("Bohemian Rhapsody")
    assert not _looks_like_audio_stream_codec_label("Episode 12 — The Finale")
    assert not _looks_like_audio_stream_codec_label("Some Song (Live)")
