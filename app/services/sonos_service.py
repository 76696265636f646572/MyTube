from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

try:
    from soco import SoCo, discover
    from soco.exceptions import NotSupportedException
except Exception:  # pragma: no cover - optional runtime dependency
    SoCo = None
    discover = None

    class NotSupportedException(Exception):
        """Placeholder when SoCo is not installed."""

        pass


@dataclass
class SonosSpeaker:
    ip: str
    name: str
    uid: str
    coordinator_uid: str | None
    group_member_uids: list[str]
    volume: int | None
    transport_state: str | None
    is_playing: bool
    is_coordinator: bool


# Fixed v1 API keys (order for UI is defined in the frontend).
SONOS_V1_SETTING_KEYS: tuple[str, ...] = (
    "balance",
    "bass",
    "cross_fade",
    "loudness",
    "mic_enabled",
    "music_surround_level",
    "night_mode",
    "speech_enhancement",
    "sub_enabled",
    "sub_gain",
    "surround_enabled",
    "surround_level",
    "surround_full_volume_enabled",
    "treble",
    "audio_delay",
    "audio_input_format",
)

READONLY_SETTINGS = frozenset({"audio_input_format", "mic_enabled"})


class SonosSettingsError(ValueError):
    """Invalid setting name, value, or update target (maps to HTTP 400)."""


def _safe_read(getter):
    try:
        return getter()
    except Exception:
        return None


def _read_balance_value(speaker) -> int | None:
    def _inner():
        bal = speaker.balance
        if not isinstance(bal, tuple) or len(bal) != 2:
            return None
        left, right = int(bal[0]), int(bal[1])
        return max(-100, min(100, right - left))

    return _safe_read(_inner)


def _read_speech_enhancement(speaker) -> bool | None:
    def _speech():
        value = speaker.speech_enhance_enabled
        if value is None:
            return None
        return bool(value)

    primary = _safe_read(_speech)
    if primary is not None:
        return primary

    def _dialog():
        value = speaker.dialog_mode
        if value is None:
            return None
        return bool(value)

    return _safe_read(_dialog)


def _read_audio_input_format(speaker) -> str | None:
    return _safe_read(lambda: speaker.soundbar_audio_input_format)


def _read_surround_full_volume(speaker) -> bool | None:
    def _inner():
        raw = speaker.surround_full_volume_enabled
        if raw is None:
            return None
        return bool(int(raw))

    return _safe_read(_inner)


def _read_mic_enabled(speaker) -> bool | None:
    return _safe_read(lambda: speaker.mic_enabled)


def _snapshot_dict(speaker) -> dict[str, Any]:
    return {
        "audio_delay": _safe_read(lambda: speaker.audio_delay),
        "audio_input_format": _read_audio_input_format(speaker),
        "balance": _read_balance_value(speaker),
        "bass": _safe_read(lambda: speaker.bass),
        "cross_fade": _safe_read(lambda: bool(speaker.cross_fade)),
        "loudness": _safe_read(lambda: bool(speaker.loudness)),
        "mic_enabled": _read_mic_enabled(speaker),
        "music_surround_level": _safe_read(lambda: speaker.music_surround_level),
        "night_mode": _safe_read(lambda: speaker.night_mode),
        "speech_enhancement": _read_speech_enhancement(speaker),
        "sub_gain": _safe_read(lambda: speaker.sub_gain),
        "sub_enabled": _safe_read(lambda: speaker.sub_enabled),
        "surround_enabled": _safe_read(lambda: speaker.surround_enabled),
        "surround_level": _safe_read(lambda: speaker.surround_level),
        "surround_full_volume_enabled": _read_surround_full_volume(speaker),
        "treble": _safe_read(lambda: speaker.treble),
    }


def _coerce_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int) and raw in (0, 1):
        return bool(raw)
    raise SonosSettingsError("Value must be a boolean")


def _coerce_int(raw: Any) -> int:
    if isinstance(raw, bool):
        raise SonosSettingsError("Value must be an integer")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    raise SonosSettingsError("Value must be an integer")


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def _balance_tuple_from_ui(balance: int) -> tuple[int, int]:
    b = _clamp_int(balance, -100, 100)
    left = 100 - max(0, b)
    right = 100 + min(0, b)
    return left, right


def _apply_write(speaker, setting: str, value: Any) -> Any:
    if setting == "balance":
        b = _clamp_int(_coerce_int(value), -100, 100)
        speaker.balance = _balance_tuple_from_ui(b)
        return b

    if setting == "bass":
        v = _clamp_int(_coerce_int(value), -10, 10)
        speaker.bass = v
        return v

    if setting == "treble":
        v = _clamp_int(_coerce_int(value), -10, 10)
        speaker.treble = v
        return v

    if setting == "sub_gain":
        v = _clamp_int(_coerce_int(value), -15, 15)
        speaker.sub_gain = v
        return v

    if setting == "surround_level":
        v = _clamp_int(_coerce_int(value), -15, 15)
        speaker.surround_level = v
        return v

    if setting == "music_surround_level":
        v = _clamp_int(_coerce_int(value), -15, 15)
        speaker.music_surround_level = v
        return v

    if setting == "audio_delay":
        v = _clamp_int(_coerce_int(value), 0, 5)
        speaker.audio_delay = v
        return v

    if setting == "cross_fade":
        b = _coerce_bool(value)
        speaker.cross_fade = b
        return b

    if setting == "loudness":
        b = _coerce_bool(value)
        speaker.loudness = b
        return b

    if setting == "night_mode":
        b = _coerce_bool(value)
        speaker.night_mode = b
        return b

    if setting == "speech_enhancement":
        b = _coerce_bool(value)
        try:
            speaker.speech_enhance_enabled = b
            return b
        except NotSupportedException:
            pass
        try:
            dialog = speaker.dialog_mode
        except Exception as exc:
            raise SonosSettingsError("speech_enhancement is not supported on this speaker") from exc
        if dialog is None:
            raise SonosSettingsError("speech_enhancement is not supported on this speaker")
        speaker.dialog_mode = b
        return b

    if setting == "sub_enabled":
        b = _coerce_bool(value)
        speaker.sub_enabled = b
        return b

    if setting == "surround_enabled":
        b = _coerce_bool(value)
        speaker.surround_enabled = b
        return b

    if setting == "surround_full_volume_enabled":
        b = _coerce_bool(value)
        speaker.surround_full_volume_enabled = 1 if b else 0
        return b

    raise SonosSettingsError(f"Unknown setting: {setting}")


def _radio_stream_uri(stream_url: str) -> str:
    parts = urlsplit(stream_url)
    if parts.scheme.lower() not in {"http", "https"}:
        return stream_url
    return urlunsplit(("x-rincon-mp3radio", parts.netloc, parts.path, parts.query, parts.fragment))


class SonosService:
    ACTIVE_TRANSPORT_STATES = {"PLAYING", "TRANSITIONING"}

    @staticmethod
    def _playback_target(speaker):
        group = getattr(speaker, "group", None)
        if group is None:
            return speaker
        coordinator = getattr(group, "coordinator", None)
        return coordinator or speaker

    @classmethod
    def _output_from_target(cls, speaker, output_cache: dict[str, str | None]) -> str | None:
        target = cls._playback_target(speaker)
        cache_key = str(
            getattr(target, "uid", None)
            or getattr(target, "ip_address", None)
            or getattr(speaker, "uid", None)
            or getattr(speaker, "ip_address", "")
        )
        if cache_key in output_cache:
            return output_cache[cache_key]
        output = _safe_read(lambda: target.music_source)
        normalized_output = None
        if output:
            normalized_output = str(output).strip().upper() or None
        output_cache[cache_key] = normalized_output
        return normalized_output

    @classmethod
    def _transport_state_from_target(cls, speaker, transport_cache: dict[str, str | None], output_cache: dict[str, str | None]) -> str | None:
        target = cls._playback_target(speaker)
        cache_key = str(
            getattr(target, "uid", None)
            or getattr(target, "ip_address", None)
            or getattr(speaker, "uid", None)
            or getattr(speaker, "ip_address", "")
        )
        if cache_key in transport_cache:
            return transport_cache[cache_key]
        try:
            transport_info = target.get_current_transport_info() or {}
            transport_state = transport_info.get("current_transport_state")
        except Exception:
            transport_state = None
        normalized_state = None
        if transport_state:
            normalized_state = str(transport_state).strip().upper() or None
        output = cls._output_from_target(speaker, output_cache)
        if output == "TV":
            normalized_state = "STOPPED"
        transport_cache[cache_key] = normalized_state
        return normalized_state

    def discover_speakers(self, timeout: int = 2) -> list[SonosSpeaker]:
        if discover is None:
            return []
        speakers = discover(timeout=timeout) or set()
        result: list[SonosSpeaker] = []
        transport_cache: dict[str, str | None] = {}
        output_cache: dict[str, str | None] = {}
        for speaker in speakers:
            uid = str(getattr(speaker, "uid", speaker.ip_address))
            group = getattr(speaker, "group", None)
            group_member_uids: list[str] = [str(getattr(speaker, "uid", uid))]
            coordinator_uid = group_member_uids[0]
            is_coordinator = True
            if group is not None:
                coordinator_uid = None
                group_member_uids = []
                coordinator = getattr(group, "coordinator", None)
                if coordinator is not None:
                    coordinator_uid = str(getattr(coordinator, "uid", None) or getattr(coordinator, "ip_address", ""))
                    is_coordinator = coordinator_uid == uid
                members = getattr(group, "members", [])
                group_member_uids = [str(getattr(member, "uid", member.ip_address)) for member in members]
            try:
                volume = int(speaker.volume)
            except Exception:
                volume = None
            transport_state = self._transport_state_from_target(speaker, transport_cache, output_cache)
            result.append(
                SonosSpeaker(
                    ip=speaker.ip_address,
                    name=speaker.player_name,
                    uid=uid,
                    coordinator_uid=coordinator_uid,
                    group_member_uids=group_member_uids,
                    volume=volume,
                    transport_state=transport_state,
                    is_playing=transport_state in self.ACTIVE_TRANSPORT_STATES,
                    is_coordinator=is_coordinator,
                )
            )
        return result

    def play_stream(self, speaker_ip: str, stream_url: str) -> None:
        if SoCo is None:
            raise RuntimeError("SoCo not installed")
        speaker = SoCo(speaker_ip)
        target = self._playback_target(speaker)
        target.play_uri(_radio_stream_uri(stream_url), title="Airwave")

    def stop_stream(self, speaker_ip: str) -> None:
        if SoCo is None:
            raise RuntimeError("SoCo not installed")
        speaker = SoCo(speaker_ip)
        try:
            target = self._playback_target(speaker)
            target.stop()
        except Exception as e:
            raise RuntimeError(f"Failed to stop stream: {e}") from e

    def group_speaker(self, coordinator_ip: str, member_ip: str) -> None:
        if SoCo is None:
            raise RuntimeError("SoCo not installed")
        coordinator = SoCo(coordinator_ip)
        member = SoCo(member_ip)
        member.join(coordinator)

    def ungroup_speaker(self, speaker_ip: str) -> None:
        if SoCo is None:
            raise RuntimeError("SoCo not installed")
        speaker = SoCo(speaker_ip)
        speaker.unjoin()

    def set_volume(self, speaker_ip: str, volume: int) -> None:
        if SoCo is None:
            raise RuntimeError("SoCo not installed")
        speaker = SoCo(speaker_ip)
        speaker.volume = max(0, min(100, int(volume)))

    def get_speaker_settings(self, speaker_ip: str) -> dict[str, Any]:
        if SoCo is None:
            raise RuntimeError("SoCo not installed")
        speaker = SoCo(speaker_ip)
        name = _safe_read(lambda: speaker.player_name) or ""
        settings = _snapshot_dict(speaker)
        for key in SONOS_V1_SETTING_KEYS:
            settings.setdefault(key, None)
        return {
            "speaker_ip": speaker_ip,
            "speaker_name": name,
            "settings": settings,
        }

    def update_speaker_setting(self, speaker_ip: str, setting: str, value: Any) -> Any:
        if SoCo is None:
            raise RuntimeError("SoCo not installed")
        if setting not in SONOS_V1_SETTING_KEYS:
            raise SonosSettingsError(f"Unknown setting: {setting}")
        if setting in READONLY_SETTINGS:
            raise SonosSettingsError(f"Setting {setting} is read-only")

        speaker = SoCo(speaker_ip)

        try:
            return _apply_write(speaker, setting, value)
        except SonosSettingsError:
            raise
        except Exception as exc:
            message = str(exc).strip() or type(exc).__name__
            if "not supported" in message.lower() or "does not support" in message.lower():
                raise SonosSettingsError(message) from exc
            raise
