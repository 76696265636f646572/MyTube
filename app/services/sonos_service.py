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
    is_coordinator: bool


class SonosService:
    @staticmethod
    def _playback_target(speaker):
        group = getattr(speaker, "group", None)
        if group is None:
            return speaker
        coordinator = getattr(group, "coordinator", None)
        return coordinator or speaker

    def discover_speakers(self, timeout: int = 2) -> list[SonosSpeaker]:
        if discover is None:
            return []
        speakers = discover(timeout=timeout) or set()
        result: list[SonosSpeaker] = []
        for speaker in speakers:
            uid = str(getattr(speaker, "uid", speaker.ip_address))
            group = getattr(speaker, "group", None)
            coordinator_uid = None
            group_member_uids: list[str] = []
            is_coordinator = True
            if group is not None:
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
            result.append(
                SonosSpeaker(
                    ip=speaker.ip_address,
                    name=speaker.player_name,
                    uid=uid,
                    coordinator_uid=coordinator_uid,
                    group_member_uids=group_member_uids,
                    volume=volume,
                    is_coordinator=is_coordinator,
                )
            )
        return result

    def play_stream(self, speaker_ip: str, stream_url: str) -> None:
        if SoCo is None:
            raise RuntimeError("SoCo not installed")
        speaker = SoCo(speaker_ip)
        target = self._playback_target(speaker)
        target.play_uri(stream_url, title="MyTube Radio")

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
