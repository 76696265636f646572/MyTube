import { nextTick, watch } from "vue";

import { useLibraryState } from "./useLibraryState";
import { usePlaybackState } from "./usePlaybackState";

const FALLBACK_ARTWORK_URL = "/web-app-manifest-192x192.png";
const ARTWORK_SIZES = [96, 128, 192, 256, 384, 512];
const DEFAULT_SKIP_TIME = 10;

function buildArtwork(thumbnailUrl) {
  const src = thumbnailUrl || FALLBACK_ARTWORK_URL;
  return ARTWORK_SIZES.map((size) => ({
    src,
    sizes: `${size}x${size}`,
    type: "image/png",
  }));
}

export function useMediaSession(localPlayback) {
  if (typeof navigator === "undefined" || !("mediaSession" in navigator)) {
    return;
  }

  const { pauseLocalPlayback, resumeLocalPlayback, stopLocalPlayback, localPlaybackStatus, localPlaybackSessionDeps } =
    localPlayback ?? {};

  const { playbackState } = usePlaybackState();
  const { skipCurrent, previousTrack, seekToPercent, togglePause } = useLibraryState();

  function updatePositionState() {
    if (!("setPositionState" in navigator.mediaSession)) return;

    const state = playbackState.value;
    const duration = Number(state?.duration_seconds);
    const position = Number(state?.elapsed_seconds ?? 0);

    if (!Number.isFinite(duration) || duration <= 0 || !state?.can_seek) return;

    try {
      navigator.mediaSession.setPositionState({
        duration,
        playbackRate: 1,
        position: Math.min(Math.max(position, 0), duration),
      });
    } catch {
      // Position state may be unsupported or invalid
    }
  }

  function updateMetadata() {
    const state = playbackState.value;

    navigator.mediaSession.metadata = new MediaMetadata({
      title: state?.now_playing_title || "Airwave",
      artist: state?.now_playing_channel || "",
      album: "",
      artwork: buildArtwork(state?.now_playing_thumbnail_url),
    });

    let isPlaying = state?.mode === "playing" && !state?.paused;
    if (localPlaybackStatus) {
      const local = localPlaybackStatus();
      if (local.isLocalPlaybackActive) {
        if (local.isLocalPlaybackPaused) {
          isPlaying = false;
        } else {
          isPlaying = true;
        }
      } else {
        isPlaying = false;
      }
    }
    navigator.mediaSession.playbackState = isPlaying ? "playing" : "paused";
    updatePositionState();
  }

  navigator.mediaSession.setActionHandler("play", () => {
    if (localPlaybackStatus?.()?.isLocalPlaybackActive) {
      void Promise.resolve(resumeLocalPlayback?.()).finally(() => {
        nextTick(updateMetadata);
      });
    } else {
      togglePause();
    }
  });
  navigator.mediaSession.setActionHandler("pause", () => {
    if (localPlaybackStatus?.()?.isLocalPlaybackActive) {
      pauseLocalPlayback?.();
      nextTick(updateMetadata);
    } else {
      togglePause();
    }
  });
  navigator.mediaSession.setActionHandler("previoustrack", () => previousTrack());
  navigator.mediaSession.setActionHandler("nexttrack", () => skipCurrent());

  navigator.mediaSession.setActionHandler("seekbackward", (event) => {
    const state = playbackState.value;
    const duration = Number(state?.duration_seconds);
    const elapsed = Number(state?.elapsed_seconds ?? 0);
    if (!Number.isFinite(duration) || duration <= 0 || !state?.can_seek) return;

    const skipTime = event?.seekOffset ?? DEFAULT_SKIP_TIME;
    const newPosition = Math.max(elapsed - skipTime, 0);
    seekToPercent((newPosition / duration) * 100);
  });

  navigator.mediaSession.setActionHandler("seekforward", (event) => {
    const state = playbackState.value;
    const duration = Number(state?.duration_seconds);
    const elapsed = Number(state?.elapsed_seconds ?? 0);
    if (!Number.isFinite(duration) || duration <= 0 || !state?.can_seek) return;

    const skipTime = event?.seekOffset ?? DEFAULT_SKIP_TIME;
    const newPosition = Math.min(elapsed + skipTime, duration);
    seekToPercent((newPosition / duration) * 100);
  });

  try {
    navigator.mediaSession.setActionHandler("seekto", (event) => {
      const state = playbackState.value;
      const duration = Number(state?.duration_seconds);
      if (!Number.isFinite(duration) || duration <= 0 || !state?.can_seek) return;
      if (event?.seekTime == null) return;

      const seekTime = Math.min(Math.max(Number(event.seekTime), 0), duration);
      seekToPercent((seekTime / duration) * 100);
    });
  } catch {
    // seekto is not supported (e.g. Chrome < 78)
  }

  try {
    navigator.mediaSession.setActionHandler("stop", () => {
      if (localPlaybackStatus?.()?.isLocalPlaybackActive) {
        stopLocalPlayback?.();
        nextTick(updateMetadata);
      } else {
        togglePause();
      }
    });
  } catch {
    // stop is not supported (e.g. Chrome < 77)
  }

  const mediaSessionWatchSources = localPlaybackSessionDeps ? [playbackState, localPlaybackSessionDeps] : [playbackState];
  watch(mediaSessionWatchSources, updateMetadata, { immediate: true, deep: true });
}
