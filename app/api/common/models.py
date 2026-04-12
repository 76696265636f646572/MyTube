from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

ImportMode = Literal["check", "add_all", "skip_duplicates"]


class AddUrlRequest(BaseModel):
    url: HttpUrl
    target_playlist_id: UUID | None = None
    import_mode: ImportMode | None = None


class AddLocalPathRequest(BaseModel):
    path: str = Field(min_length=1)
    import_mode: ImportMode | None = None


class AddLocalFolderRequest(BaseModel):
    path: str = Field(min_length=1)
    recursive: bool = True
    import_mode: ImportMode | None = None


class ReorderRequest(BaseModel):
    new_position: int


class SidebarPlaylistReorderRequest(BaseModel):
    playlist_id: str = Field(min_length=1)
    new_position: int
    pinned: bool


class SonosPlayRequest(BaseModel):
    speaker_ip: str


class SonosStopRequest(BaseModel):
    speaker_ip: str


class SonosGroupRequest(BaseModel):
    coordinator_ip: str
    member_ip: str


class SonosUngroupRequest(BaseModel):
    speaker_ip: str


class SonosVolumeRequest(BaseModel):
    speaker_ip: str
    volume: int = Field(ge=0, le=100)


class SonosSettingPatchRequest(BaseModel):
    setting: str = Field(min_length=1)
    value: bool | int


class BatchPlaylistEntryInput(BaseModel):
    source_url: str
    normalized_url: str
    provider: str | None = None
    provider_item_id: str | None = None
    title: str | None = None
    channel: str | None = None
    duration_seconds: int | None = None
    thumbnail_url: str | None = None


class BatchAddPlaylistEntriesRequest(BaseModel):
    entries: list[BatchPlaylistEntryInput] = Field(min_length=1)
    import_mode: ImportMode | None = None


class CreateCustomPlaylistRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class UpdatePlaylistRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    pinned: bool | None = None
    sync_enabled: bool | None = None
    sync_remove_missing: bool | None = None


class SpotifyImportUrlRequest(BaseModel):
    url: HttpUrl


class SpotifyImportSelectHitRequest(BaseModel):
    source_url: str = Field(min_length=1)
    normalized_url: str = Field(min_length=1)
    provider: str | None = None
    provider_item_id: str | None = None
    title: str | None = None
    channel: str | None = None
    duration_seconds: int | None = None
    thumbnail_url: str | None = None


class RepeatModeRequest(BaseModel):
    mode: str = Field(pattern="^(off|all|one)$")


class ShuffleModeRequest(BaseModel):
    enabled: bool


class SeekRequest(BaseModel):
    percent: float = Field(ge=0.0, le=100.0)


class InstallBinaryRequest(BaseModel):
    name: str = Field(pattern="^(yt-dlp|ffmpeg|ffprobe|deno)$")
    stop_stream_first: bool = False


class CookieSettingUpdateRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    value: str = Field(min_length=1)
