from __future__ import annotations

from dataclasses import dataclass

from app.services.extractors.base import Extractor
from app.services.extractors.mixcloud import MixcloudExtractor
from app.services.extractors.soundcloud import SoundCloudExtractor
from app.services.extractors.youtube import YouTubeExtractor


@dataclass(frozen=True)
class DispatchResult:
    extractor: Extractor
    is_playlist: bool


class ExtractorDispatcher:
    def __init__(self) -> None:
        self._extractors: list[Extractor] = [
            YouTubeExtractor(),
            SoundCloudExtractor(),
            MixcloudExtractor(),
        ]

    def get_extractor(self, url: str) -> Extractor:
        for extractor in self._extractors:
            if extractor.can_handle(url):
                return extractor
        raise ValueError("Unsupported provider URL")

    def detect_provider(self, url: str) -> str:
        return self.get_extractor(url).provider

    def get_extractor_for_provider(self, provider: str) -> Extractor | None:
        for extractor in self._extractors:
            if extractor.provider == provider:
                return extractor
        return None

    def is_playlist_url(self, url: str) -> bool:
        extractor = self.get_extractor(url)
        return extractor.classify_url(url) == "playlist"

    def dispatch(self, url: str) -> DispatchResult:
        extractor = self.get_extractor(url)
        return DispatchResult(extractor=extractor, is_playlist=extractor.classify_url(url) == "playlist")
