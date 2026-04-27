from __future__ import annotations

import asyncio
import concurrent.futures
import io
import logging
import subprocess
import threading
import time
from typing import Any, Callable

import httpx
from PIL import Image

from aiosendspin.models.types import (
    MediaCommand,
    PlaybackStateType,
    RepeatMode as SendspinRepeatMode,
)
from aiosendspin.server import (
    AudioFormat,
    ClientAddedEvent,
    ClientRemovedEvent,
    ClientUpdatedEvent,
    GroupRoleEvent,
    GroupStateChangedEvent,
    SendspinClient,
    SendspinEvent,
    SendspinGroup,
    SendspinServer,
)
from aiosendspin.server.push_stream import PushStream
from aiosendspin.server.roles import (
    ArtworkGroupRole,
    ControllerGroupRole,
    ControllerMuteEvent,
    ControllerNextEvent,
    ControllerPauseEvent,
    ControllerPlayEvent,
    ControllerPreviousEvent,
    ControllerRepeatEvent,
    ControllerShuffleEvent,
    ControllerStopEvent,
    ControllerVolumeEvent,
    MetadataGroupRole,
    PlayerGroupRole,
    PlayerV1Role,
)

from app.services.ffmpeg_pipeline import FfmpegError, FfmpegPipeline
from app.services.stream_engine import PlaybackMode, RepeatMode, StreamEngine

logger = logging.getLogger(__name__)

SENDSPIN_SAMPLE_RATE = 48000
SENDSPIN_CHANNELS = 2
SENDSPIN_BIT_DEPTH = 24
SENDSPIN_BYTES_PER_SAMPLE = SENDSPIN_BIT_DEPTH // 8
SENDSPIN_FRAME_BYTES = SENDSPIN_CHANNELS * SENDSPIN_BYTES_PER_SAMPLE

PCM_CHUNK_DURATION_MS = 20
PCM_CHUNK_SAMPLES = SENDSPIN_SAMPLE_RATE * PCM_CHUNK_DURATION_MS // 1000
PCM_CHUNK_BYTES = PCM_CHUNK_SAMPLES * SENDSPIN_FRAME_BYTES

MAX_BUFFER_US = 2_000_000

SUPPORTED_COMMANDS = [
    MediaCommand.PLAY,
    MediaCommand.PAUSE,
    MediaCommand.STOP,
    MediaCommand.NEXT,
    MediaCommand.PREVIOUS,
    MediaCommand.VOLUME,
    MediaCommand.MUTE,
    MediaCommand.REPEAT_OFF,
    MediaCommand.REPEAT_ONE,
    MediaCommand.REPEAT_ALL,
    MediaCommand.SHUFFLE,
    MediaCommand.UNSHUFFLE,
]

REPEAT_MAP_TO_AIRWAVE = {
    SendspinRepeatMode.OFF: "off",
    SendspinRepeatMode.ONE: "one",
    SendspinRepeatMode.ALL: "all",
}

REPEAT_MAP_TO_SENDSPIN = {
    RepeatMode.off: SendspinRepeatMode.OFF,
    RepeatMode.one: SendspinRepeatMode.ONE,
    RepeatMode.all: SendspinRepeatMode.ALL,
}


class SendspinServerService:
    """Wraps aiosendspin.SendspinServer to integrate with the Airwave StreamEngine."""

    def __init__(
        self,
        stream_engine: StreamEngine,
        ffmpeg_pipeline: FfmpegPipeline,
        server_name: str = "Airwave",
        port: int = 8927,
        mdns_enabled: bool = True,
        on_clients_changed: Callable[[], None] | None = None,
    ) -> None:
        self._stream_engine = stream_engine
        self._ffmpeg_pipeline = ffmpeg_pipeline
        self._server_name = server_name
        self._port = port
        self._mdns_enabled = mdns_enabled
        self._on_clients_changed = on_clients_changed

        self._server: SendspinServer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._audio_format = AudioFormat(
            sample_rate=SENDSPIN_SAMPLE_RATE,
            bit_depth=SENDSPIN_BIT_DEPTH,
            channels=SENDSPIN_CHANNELS,
        )

        self._audio_thread: threading.Thread | None = None
        self._audio_stop_event = threading.Event()
        self._active_process: subprocess.Popen[bytes] | None = None
        self._silence_process: subprocess.Popen[bytes] | None = None
        self._process_lock = threading.Lock()

        self._group: SendspinGroup | None = None
        self._push_stream: PushStream | None = None
        self._unsubscribe_server: Callable[[], None] | None = None
        self._unsubscribe_group: Callable[[], None] | None = None

        self._last_track_id: int | None = None
        self._last_artwork_url: str | None = None

        # Last PCM decode session (for seek/resume: stream/clear + restart ffmpeg)
        self._sendspin_pcm_track_id: int | None = None
        self._sendspin_pcm_anchor_monotonic: float | None = None

        # Previous snapshot for push_state_update (pause / stop / track change → stream/clear)
        self._last_push_snapshot_for_clear: tuple[int | None, PlaybackMode, bool] | None = None

    @property
    def server(self) -> SendspinServer | None:
        return self._server

    @property
    def is_running(self) -> bool:
        return self._server is not None

    async def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        server_id = f"{self._server_name.lower().replace(' ', '-')}"
        self._server = SendspinServer(
            loop=loop,
            server_id=server_id,
            server_name=self._server_name,
        )
        self._unsubscribe_server = self._server.add_event_listener(self._on_server_event)

        await self._server.start_server(
            port=self._port,
            host="0.0.0.0",
            discover_clients=self._mdns_enabled,
        )
        logger.info("SendSpin server started on port %s (mDNS=%s)", self._port, self._mdns_enabled)

        self._start_audio_feed()

    async def stop(self) -> None:
        self._stop_audio_feed()
        if self._unsubscribe_group:
            self._unsubscribe_group()
            self._unsubscribe_group = None
        if self._unsubscribe_server:
            self._unsubscribe_server()
            self._unsubscribe_server = None
        if self._push_stream and not self._push_stream.is_stopped:
            self._push_stream.stop()
            self._push_stream = None
        if self._group and self._group.has_active_stream:
            self._group.stop_stream()
        if self._server:
            await self._server.close()
            self._server = None
        logger.info("SendSpin server stopped")

    def _notify_clients_changed(self) -> None:
        if self._on_clients_changed:
            try:
                self._on_clients_changed()
            except Exception:
                logger.debug("Failed notifying clients changed", exc_info=True)

    def _on_server_event(self, server: SendspinServer, event: SendspinEvent) -> None:
        if isinstance(event, ClientAddedEvent):
            client = server.get_client(event.client_id)
            if client:
                self._setup_client(client)
            logger.info("SendSpin client connected: %s", event.client_id)
            self._notify_clients_changed()
        elif isinstance(event, ClientRemovedEvent):
            logger.info("SendSpin client disconnected: %s", event.client_id)
            self._notify_clients_changed()
        elif isinstance(event, ClientUpdatedEvent):
            self._notify_clients_changed()

    def _setup_client(self, client: SendspinClient) -> None:
        if not self._group:
            self._group = client.group
            self._setup_group(self._group)
        elif client.group != self._group:
            try:
                self._loop and self._loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(self._group.add_client(client))
                )
            except Exception:
                logger.debug("Failed adding client to group", exc_info=True)

    def _setup_group(self, group: SendspinGroup) -> None:
        ctrl: ControllerGroupRole | None = group.group_role("controller")
        if ctrl:
            ctrl.set_supported_commands(SUPPORTED_COMMANDS)
            self._sync_controller_state(ctrl)

        self._unsubscribe_group = group.add_event_listener(self._on_group_event)
        self._push_metadata()

    def _sync_controller_state(self, ctrl: ControllerGroupRole) -> None:
        engine = self._stream_engine
        player_grp: PlayerGroupRole | None = self._group.group_role("player") if self._group else None
        if player_grp is not None:
            vol = player_grp.get_group_volume()
            muted = player_grp.get_group_muted()
            if vol is not None:
                ctrl.set_volume(vol)
            if muted is not None:
                ctrl.set_mute(muted)
        repeat = REPEAT_MAP_TO_SENDSPIN.get(engine.state.repeat_mode, SendspinRepeatMode.OFF)
        shuffle = engine.state.shuffle_enabled

        meta: MetadataGroupRole | None = self._group.group_role("metadata") if self._group else None
        if meta:
            meta.update(repeat=repeat, shuffle=shuffle)

    def _on_group_event(self, group: SendspinGroup, event: Any) -> None:
        if isinstance(event, GroupRoleEvent):
            self._handle_controller_event(event)
        elif isinstance(event, GroupStateChangedEvent):
            self._notify_clients_changed()

    def _handle_controller_event(self, event: GroupRoleEvent) -> None:
        engine = self._stream_engine
        try:
            if isinstance(event, ControllerPlayEvent):
                engine.resume_playback()
            elif isinstance(event, ControllerPauseEvent):
                if not engine.state.paused and engine.state.mode == PlaybackMode.playing:
                    engine.toggle_pause()
            elif isinstance(event, ControllerStopEvent):
                engine.stop_playback()
            elif isinstance(event, ControllerNextEvent):
                engine.skip_current()
            elif isinstance(event, ControllerPreviousEvent):
                engine.play_previous_or_restart()
            elif isinstance(event, ControllerVolumeEvent):
                self.set_group_volume(event.volume)
            elif isinstance(event, ControllerMuteEvent):
                self.set_group_muted(event.muted)
            elif isinstance(event, ControllerRepeatEvent):
                airwave_mode = REPEAT_MAP_TO_AIRWAVE.get(event.mode, "off")
                engine.set_repeat_mode(airwave_mode)
            elif isinstance(event, ControllerShuffleEvent):
                engine.set_shuffle_enabled(event.shuffle)
        except Exception:
            logger.exception("Error handling controller event %s", type(event).__name__)

    def push_state_update(self) -> None:
        # Called from notify_ui_state_changed; must not call _notify_clients_changed
        # back or the callback loop will recurse.
        if not self._server or not self._group:
            return
        self._maybe_clear_push_stream_for_playback_snapshot_change()
        self._sync_group_playback_state()
        self._push_metadata()
        self._push_artwork_if_changed()
        self._sync_controller_state_from_group()

    def _sync_group_playback_state(self) -> None:
        if not self._group:
            return

        state = self._stream_engine.state
        if state.mode != PlaybackMode.playing:
            target_state = PlaybackStateType.STOPPED
        elif state.paused:
            target_state = PlaybackStateType.PAUSED
        else:
            target_state = PlaybackStateType.PLAYING

        # aiosendspin does not expose a public playback-state setter for groups,
        # but sendspin-cli relies on this state to decide whether to interpolate
        # progress locally while metadata playback_speed alone is not sufficient.
        current_state = getattr(self._group, "state", None)
        if current_state == target_state:
            return

        set_playback_state = getattr(self._group, "_set_playback_state", None)
        if callable(set_playback_state):
            set_playback_state(target_state)

    def _sync_controller_state_from_group(self) -> None:
        if not self._group:
            return
        ctrl: ControllerGroupRole | None = self._group.group_role("controller")
        if ctrl:
            self._sync_controller_state(ctrl)

    def _push_metadata(self) -> None:
        if not self._group:
            return
        meta: MetadataGroupRole | None = self._group.group_role("metadata")
        if not meta:
            return

        engine = self._stream_engine
        state = engine.state
        progress = engine.playback_progress()

        if state.mode == PlaybackMode.idle:
            meta.clear()
            return

        elapsed_ms = int((progress.get("elapsed_seconds") or 0) * 1000)
        duration_ms = int((state.now_playing_duration_seconds or 0) * 1000)
        playback_speed = 0 if state.paused else 1000

        repeat = REPEAT_MAP_TO_SENDSPIN.get(state.repeat_mode, SendspinRepeatMode.OFF)

        meta.update(
            title=state.now_playing_title,
            artist=state.now_playing_channel,
            track_progress=elapsed_ms,
            track_duration=duration_ms,
            playback_speed=playback_speed,
            repeat=repeat,
            shuffle=state.shuffle_enabled,
        )

    def _push_artwork_if_changed(self) -> None:
        if not self._group:
            return
        state = self._stream_engine.state
        thumb_url = state.now_playing_thumbnail_url
        track_id = state.now_playing_id

        if track_id == self._last_track_id and thumb_url == self._last_artwork_url:
            return

        self._last_track_id = track_id
        self._last_artwork_url = thumb_url

        if not thumb_url:
            if self._loop:
                self._loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(self._clear_artwork())
                )
            return

        if self._loop:
            self._loop.call_soon_threadsafe(
                lambda url=thumb_url: asyncio.ensure_future(self._fetch_and_push_artwork(url))
            )

    async def _clear_artwork(self) -> None:
        if not self._group:
            return
        art: ArtworkGroupRole | None = self._group.group_role("artwork")
        if art:
            await art.set_album_artwork(None)

    async def _fetch_and_push_artwork(self, url: str) -> None:
        if not self._group:
            return
        art: ArtworkGroupRole | None = self._group.group_role("artwork")
        if not art:
            return
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            image = Image.open(io.BytesIO(resp.content))
            await art.set_album_artwork(image)
            logger.debug("Pushed album artwork from %s", url)
        except Exception:
            logger.debug("Failed fetching artwork from %s", url, exc_info=True)
            await art.set_album_artwork(None)

    # --- Audio feed thread ---

    def _start_audio_feed(self) -> None:
        self._audio_stop_event.clear()
        self._audio_thread = threading.Thread(
            target=self._audio_feed_loop,
            daemon=True,
            name="sendspin-audio-feed",
        )
        self._audio_thread.start()

    def _stop_audio_feed(self) -> None:
        self._audio_stop_event.set()
        self._terminate_active_process()
        self._terminate_silence_process()
        if self._audio_thread:
            self._audio_thread.join(timeout=3)
            self._audio_thread = None

    def _terminate_active_process(self) -> None:
        with self._process_lock:
            proc = self._active_process
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                pass

    def _terminate_silence_process(self) -> None:
        with self._process_lock:
            proc = self._silence_process
            self._silence_process = None
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                pass

    def _ensure_silence_process(self) -> subprocess.Popen[bytes] | None:
        with self._process_lock:
            proc = self._silence_process
        if proc and proc.poll() is None:
            return proc
        try:
            proc = self._ffmpeg_pipeline.spawn_pcm_silence(
                sample_rate=SENDSPIN_SAMPLE_RATE,
                channels=SENDSPIN_CHANNELS,
                bit_depth=SENDSPIN_BIT_DEPTH,
            )
        except FfmpegError as exc:
            logger.warning("Failed spawning PCM silence: %s", exc)
            return None
        with self._process_lock:
            self._silence_process = proc
        return proc

    def _push_silence_chunk(self) -> None:
        proc = self._ensure_silence_process()
        if not proc or not proc.stdout:
            return
        chunk = proc.stdout.read(PCM_CHUNK_BYTES)
        if chunk:
            self._push_pcm_chunk(chunk)

    def _audio_feed_loop(self) -> None:
        """Background thread that reads PCM from ffmpeg and pushes to SendSpin."""
        self._ensure_silence_process()
        while not self._audio_stop_event.is_set():
            try:
                self._audio_feed_cycle()
            except Exception:
                logger.exception("SendSpin audio feed error")
                if not self._audio_stop_event.wait(1.0):
                    continue

    def _clear_push_stream_sync(self) -> None:
        """Send Sendspin stream/clear and reset push-stream buffers (player + visualizer)."""
        loop = self._loop
        if not loop or not self._push_stream or self._push_stream.is_stopped:
            return

        async def _clear_push_stream() -> None:
            if self._push_stream and not self._push_stream.is_stopped:
                self._push_stream.clear()

        future = asyncio.run_coroutine_threadsafe(_clear_push_stream(), loop)
        try:
            future.result(timeout=2.0)
        except Exception:
            pass

    def _maybe_clear_push_stream_for_playback_snapshot_change(self) -> None:
        """Emit stream/clear on pause, stop, next, or previous (same as spec seek boundaries)."""
        state = self._stream_engine.state
        prev = self._last_push_snapshot_for_clear
        need_clear = False
        if prev is not None:
            prev_track, prev_mode, prev_paused = prev
            if state.paused and not prev_paused:
                need_clear = True
            elif state.mode == PlaybackMode.idle and prev_mode != PlaybackMode.idle:
                need_clear = True
            elif prev_track is not None and state.now_playing_id != prev_track:
                need_clear = True
        self._last_push_snapshot_for_clear = (
            state.now_playing_id,
            state.mode,
            state.paused,
        )
        if need_clear:
            self._clear_push_stream_sync()

    def _reset_sendspin_pcm_session(self) -> None:
        self._sendspin_pcm_track_id = None
        self._sendspin_pcm_anchor_monotonic = None

    def _maybe_clear_push_stream_for_timeline_jump(self, state: Any) -> None:
        """Send stream/clear when the playback clock jumps on the same track."""
        track_id = state.now_playing_id
        anchor = state.started_at_monotonic_seconds
        if (
            track_id is None
            or track_id != self._sendspin_pcm_track_id
            or self._sendspin_pcm_anchor_monotonic is None
            or anchor is None
            or anchor == self._sendspin_pcm_anchor_monotonic
        ):
            return
        self._clear_push_stream_sync()

    def _audio_feed_cycle(self) -> None:
        engine = self._stream_engine
        state = engine.state

        # Pause / stop / idle: clear once so clients drop buffered audio.
        if state.mode != PlaybackMode.playing or state.paused:
            if self._sendspin_pcm_track_id is not None:
                self._clear_push_stream_sync()
                self._reset_sendspin_pcm_session()
            self._feed_silence_until_state_change()
            return

        pcm_source = self._get_pcm_ffmpeg_input()
        if not pcm_source:
            if self._sendspin_pcm_track_id is not None:
                self._clear_push_stream_sync()
                self._reset_sendspin_pcm_session()
            self._feed_silence_until_state_change()
            return

        # Track change: clear before decoding the next item.
        if (
            self._sendspin_pcm_track_id is not None
            and state.now_playing_id != self._sendspin_pcm_track_id
        ):
            self._clear_push_stream_sync()

        self._maybe_clear_push_stream_for_timeline_jump(state)

        seek_offset = 0.0
        progress = engine.playback_progress()
        elapsed = progress.get("elapsed_seconds")
        if elapsed is not None and elapsed > 0:
            seek_offset = float(elapsed)

        try:
            process = self._ffmpeg_pipeline.spawn_pcm_for_source(
                pcm_source,
                start_at_seconds=seek_offset,
                sample_rate=SENDSPIN_SAMPLE_RATE,
                channels=SENDSPIN_CHANNELS,
                bit_depth=SENDSPIN_BIT_DEPTH,
            )
        except FfmpegError as exc:
            logger.warning("Failed spawning PCM source: %s", exc)
            self._push_silence_chunk()
            return

        state = engine.state
        self._sendspin_pcm_track_id = state.now_playing_id
        self._sendspin_pcm_anchor_monotonic = state.started_at_monotonic_seconds

        with self._process_lock:
            self._active_process = process

        tracking_track_id = state.now_playing_id
        spawn_anchor = state.started_at_monotonic_seconds
        try:
            self._stream_pcm_from_process(process, tracking_track_id, spawn_anchor)
        finally:
            with self._process_lock:
                self._active_process = None
            try:
                process.terminate()
                process.wait(timeout=1)
            except Exception:
                pass

    def _feed_silence_until_state_change(self) -> None:
        engine = self._stream_engine
        last_mode = engine.state.mode
        last_paused = engine.state.paused
        last_track_id = engine.state.now_playing_id

        while not self._audio_stop_event.is_set():
            state = engine.state
            if (
                state.mode != last_mode
                or state.paused != last_paused
                or state.now_playing_id != last_track_id
            ):
                break
            if not self._push_silence_chunk():
                if self._audio_stop_event.wait(0.02):
                    break

    def _stream_pcm_from_process(
        self,
        process: subprocess.Popen[bytes],
        tracking_track_id: int | None,
        spawn_anchor_monotonic: float | None,
    ) -> None:
        engine = self._stream_engine

        while not self._audio_stop_event.is_set():
            state = engine.state
            if state.now_playing_id != tracking_track_id:
                break
            if state.paused:
                break
            if state.mode != PlaybackMode.playing:
                break
            if (
                tracking_track_id is not None
                and spawn_anchor_monotonic is not None
                and state.started_at_monotonic_seconds is not None
                and state.started_at_monotonic_seconds != spawn_anchor_monotonic
            ):
                break

            read_started = time.monotonic()
            chunk = process.stdout.read(PCM_CHUNK_BYTES) if process.stdout else b""
            read_seconds = time.monotonic() - read_started
            if chunk and read_seconds >= 0.08:
                logger.warning(
                    "Slow PCM ffmpeg read track_id=%s read_seconds=%.3f chunk_bytes=%s",
                    tracking_track_id,
                    read_seconds,
                    len(chunk),
                )
            if not chunk:
                break

            self._push_pcm_chunk(chunk)

    def _push_pcm_chunk(self, pcm: bytes) -> None:
        if not self._server or not self._group:
            return

        if not self._push_stream or self._push_stream.is_stopped:
            self._push_stream = self._group.start_stream()

        self._push_stream.prepare_audio(pcm, self._audio_format)

        loop = self._loop
        if not loop:
            return

        future = asyncio.run_coroutine_threadsafe(
            self._commit_audio(), loop
        )
        try:
            future.result(timeout=2.0)
        except concurrent.futures.TimeoutError:
            logger.warning(
                "SendSpin commit_audio timed out after 2.0s (PCM delivery may stutter)",
            )
        except Exception:
            logger.warning("SendSpin commit_audio failed", exc_info=True)

    async def _commit_audio(self) -> None:
        if self._push_stream and not self._push_stream.is_stopped:
            await self._push_stream.commit_audio()
            await self._push_stream.sleep_to_limit_buffer(MAX_BUFFER_US)

    def _get_pcm_ffmpeg_input(self) -> str | None:
        return self._stream_engine.get_current_ffmpeg_input()

    # --- Public API for REST endpoints ---

    def list_clients(self) -> list[dict[str, Any]]:
        if not self._server:
            return []
        result = []
        for client in self._server.connected_clients:
            result.append(self._serialize_client(client))
        return result

    def connected_client_count(self) -> int:
        if not self._server:
            return 0
        return len(self._server.connected_clients)

    def _serialize_client(self, client: SendspinClient) -> dict[str, Any]:
        volume: int | None = None
        muted: bool | None = None
        static_delay_ms: int = 0
        codec: str | None = None

        player_roles = client.roles_by_family("player")
        if player_roles:
            player: PlayerV1Role = player_roles[0]
            volume = player.volume
            muted = player.muted
            static_delay_ms = player.static_delay_ms
            pf = player.preferred_format
            if pf:
                codec = f"{pf.sample_rate}Hz/{pf.bit_depth}bit/{pf.channels}ch"

        info = client.info
        device_info: dict[str, str | None] = {}
        if info and hasattr(info, "device_info") and info.device_info:
            device_info = {
                "product_name": getattr(info.device_info, "product_name", None),
                "manufacturer": getattr(info.device_info, "manufacturer", None),
                "software_version": getattr(info.device_info, "software_version", None),
            }

        roles = client.negotiated_roles if client.negotiated_roles else []

        return {
            "client_id": client.client_id,
            "name": client.name,
            "is_connected": client.is_connected,
            "volume": volume,
            "muted": muted,
            "static_delay_ms": static_delay_ms,
            "codec": codec,
            "device_info": device_info,
            "roles": roles,
        }

    def _set_player_volume(self, player: PlayerV1Role, volume: int) -> None:
        """Send volume command AND update server-side tracked state."""
        clamped = max(0, min(100, volume))
        player.set_player_volume(clamped)
        player.volume = clamped

    def _set_player_muted(self, player: PlayerV1Role, muted: bool) -> None:
        """Send mute command AND update server-side tracked state."""
        player.set_player_mute(muted)
        player.muted = muted

    def set_client_volume(self, client_id: str, volume: int) -> bool:
        if not self._server:
            return False
        client = self._server.get_client(client_id)
        if not client:
            return False
        player_roles = client.roles_by_family("player")
        if not player_roles:
            return False
        self._set_player_volume(player_roles[0], volume)
        self._notify_clients_changed()
        return True

    def set_client_muted(self, client_id: str, muted: bool) -> bool:
        if not self._server:
            return False
        client = self._server.get_client(client_id)
        if not client:
            return False
        player_roles = client.roles_by_family("player")
        if not player_roles:
            return False
        self._set_player_muted(player_roles[0], muted)
        self._notify_clients_changed()
        return True

    def set_group_volume(self, volume: int) -> bool:
        if not self._group:
            return False
        target = max(0, min(100, volume))
        players = self._get_group_players()
        if not players:
            return True
        new_volumes = self._redistribute_volume(players, target)
        for player, vol in new_volumes.items():
            self._set_player_volume(player, vol)
        self._notify_clients_changed()
        return True

    def set_group_muted(self, muted: bool) -> bool:
        if not self._group:
            return False
        players = self._get_group_players()
        for player in players:
            self._set_player_muted(player, muted)
        self._notify_clients_changed()
        return True

    def _get_group_players(self) -> list[PlayerV1Role]:
        if not self._group:
            return []
        player_grp: PlayerGroupRole | None = self._group.group_role("player")
        if not player_grp:
            return []
        return [
            p for c in self._group.clients
            for p in c.roles_by_family("player")
            if isinstance(p, PlayerV1Role)
        ]

    @staticmethod
    def _redistribute_volume(
        players: list[PlayerV1Role], target: int
    ) -> dict[PlayerV1Role, int]:
        """Mirrors the aiosendspin redistribution algorithm."""
        player_vols: dict[PlayerV1Role, float] = {}
        for p in players:
            vol = p.volume
            if vol is not None:
                player_vols[p] = float(vol)
        if not player_vols:
            return {}
        current_avg = sum(player_vols.values()) / len(player_vols)
        delta = target - current_avg
        active = list(player_vols.keys())
        for _ in range(5):
            lost = 0.0
            next_active: list[PlayerV1Role] = []
            for player in active:
                proposed = player_vols[player] + delta
                if proposed > 100:
                    lost += proposed - 100
                    player_vols[player] = 100.0
                elif proposed < 0:
                    lost += proposed
                    player_vols[player] = 0.0
                else:
                    player_vols[player] = proposed
                    next_active.append(player)
            if not next_active or abs(lost) < 0.01:
                break
            delta = lost / len(next_active)
            active = next_active
        return {p: round(v) for p, v in player_vols.items()}

    def get_group_state(self) -> dict[str, Any]:
        if not self._group:
            return {"volume": 0, "muted": False}
        player_grp: PlayerGroupRole | None = self._group.group_role("player")
        return {
            "volume": player_grp.get_group_volume() if player_grp else 0,
            "muted": player_grp.get_group_muted() if player_grp else False,
        }
