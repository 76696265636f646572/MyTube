"""Tests for YtDlpService URL detection (no subprocess)."""

import pytest

from app.services.yt_dlp_service import YtDlpService


@pytest.fixture
def service():
    return YtDlpService(binary_path="/bin/echo")


def test_is_playlist_url_playlist_page(service):
    assert service.is_playlist_url("https://www.youtube.com/playlist?list=PLxxx") is True
    assert service.is_playlist_url("https://youtube.com/playlist?list=ABC") is True


def test_is_playlist_url_watch_single_video(service):
    assert service.is_playlist_url("https://www.youtube.com/watch?v=Hjw86NcG8Bo") is False


def test_is_playlist_url_watch_with_list_param_treated_as_single_video(service):
    """watch?v=...&list=... without start_radio should queue/play only the video."""
    url = "https://www.youtube.com/watch?v=Hjw86NcG8Bo&list=PLMmqTuUsDkRIZ1C1T2AsVz5XIxtVDfSOe"
    assert service.is_playlist_url(url) is False


def test_is_start_radio_url(service):
    assert service.is_start_radio_url("https://www.youtube.com/watch?v=u6wOyMUs74I&list=RDu6wOyMUs74I&start_radio=1") is True
    assert service.is_start_radio_url("https://www.youtube.com/watch?v=HMUDVMiITOU&list=RDMMHMUDVMiITOU&start_radio=1") is True
    assert service.is_start_radio_url("https://www.youtube.com/watch?v=Hjw86NcG8Bo&list=PLxxx") is False
    assert service.is_start_radio_url("https://www.youtube.com/watch?v=Hjw86NcG8Bo") is False
    assert service.is_start_radio_url("https://www.youtube.com/playlist?list=PLxxx") is False


def test_is_playlist_url_start_radio(service):
    """watch?v=...&list=...&start_radio=1 should be treated as playlist for import/queue."""
    url = "https://www.youtube.com/watch?v=u6wOyMUs74I&list=RDu6wOyMUs74I&start_radio=1"
    assert service.is_playlist_url(url) is True
