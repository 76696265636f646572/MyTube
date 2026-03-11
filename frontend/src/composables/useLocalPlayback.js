import { computed, onUnmounted, ref, watch } from "vue";

import { usePlaybackState } from "./usePlaybackState";

/**
 * Single audio element and local playback state for the app.
 * Use from app root: mount the returned audioRef on <audio>, then provide
 * { startLocalPlayback, stopLocalPlayback, isLocalPlaybackActive } to children.
 */
export function useLocalPlayback() {
  const playbackState = usePlaybackState();
  const audioRef = ref(null);
  const wantsLocalPlayback = ref(false);

  const isLocalPlaybackActive = computed(
    () => wantsLocalPlayback.value && Boolean(playbackState.value.stream_url)
  );

  async function startLocalPlayback() {
    if (!audioRef.value || !playbackState.value.stream_url) return;
    wantsLocalPlayback.value = true;
    audioRef.value.load();
    try {
      await audioRef.value.play();
    } catch {
      wantsLocalPlayback.value = false;
    }
  }

  function stopLocalPlayback() {
    wantsLocalPlayback.value = false;
    if (!audioRef.value) return;
    audioRef.value.pause();
    try {
      audioRef.value.currentTime = 0;
    } catch {
      // Some live streams do not support seeking back to the start.
    }
  }

  watch(
    () => playbackState.value.stream_url,
    async (streamUrl) => {
      if (!audioRef.value) return;
      if (!streamUrl) {
        stopLocalPlayback();
        return;
      }
      if (!wantsLocalPlayback.value) return;
      audioRef.value.load();
      try {
        await audioRef.value.play();
      } catch {
        wantsLocalPlayback.value = false;
      }
    },
    { immediate: true }
  );

  onUnmounted(() => {
    if (!audioRef.value) return;
    audioRef.value.pause();
  });

  return {
    audioRef,
    startLocalPlayback,
    stopLocalPlayback,
    isLocalPlaybackActive,
  };
}
