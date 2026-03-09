import { ref } from "vue";

import { fetchJson } from "./useApi";

const playbackState = ref({
  mode: "idle",
  now_playing_title: null,
  now_playing_channel: null,
  now_playing_thumbnail_url: null,
  duration_seconds: null,
  elapsed_seconds: null,
  progress_percent: null,
  stream_url: null,
});

let playbackTicker = null;
let initialized = false;

function applyPlaybackState(nextState) {
  if (!nextState || typeof nextState !== "object") return;
  playbackState.value = nextState;
}

function startPlaybackTicker() {
  if (playbackTicker) clearInterval(playbackTicker);
  playbackTicker = setInterval(() => {
    const state = playbackState.value;
    if (!state || state.mode !== "playing" || state.started_at == null) return;
    const startedAt = Number(state.started_at);
    if (!Number.isFinite(startedAt)) return;
    const elapsed = Math.max(0, Date.now() / 1000 - startedAt);
    const duration = Number(state.duration_seconds);
    const progress =
      Number.isFinite(duration) && duration > 0 ? Math.min(100, (elapsed / duration) * 100) : null;
    playbackState.value = {
      ...state,
      elapsed_seconds: elapsed,
      progress_percent: progress,
    };
  }, 1000);
}

async function refreshPlaybackState() {
  playbackState.value = await fetchJson("/api/state");
}

export async function initializePlaybackState() {
  if (!initialized) {
    initialized = true;
    startPlaybackTicker();
  }
  await refreshPlaybackState();
}

export function usePlaybackState() {
  return {
    playbackState,
    applyPlaybackState,
  };
}
