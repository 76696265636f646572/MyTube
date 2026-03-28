from __future__ import annotations

from dataclasses import dataclass

try:
    from soco import SoCo, discover
except Exception:  # pragma: no cover - optional runtime dependency
    SoCo = None
    discover = None


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
    def _transport_state_from_target(cls, speaker, transport_cache: dict[str, str | None]) -> str | None:
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
        transport_cache[cache_key] = normalized_state
        return normalized_state

    def discover_speakers(self, timeout: int = 2) -> list[SonosSpeaker]:
        if discover is None:
            return []
        speakers = discover(timeout=timeout) or set()
        result: list[SonosSpeaker] = []
        transport_cache: dict[str, str | None] = {}
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
            transport_state = self._transport_state_from_target(speaker, transport_cache)
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
        target.play_uri(stream_url, title="Airwave")

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