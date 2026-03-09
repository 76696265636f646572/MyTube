<template>
  <footer class="sticky bottom-0 z-10 shrink-0 rounded-xl border border-neutral-700 bg-neutral-900 px-2 py-2 sm:px-3 md:static">
    <div class="grid items-center gap-2 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto]">
      <div class="flex min-w-0 items-center gap-3">
        <div class="h-12 w-12 shrink-0 overflow-hidden rounded-md border border-neutral-700 bg-neutral-800">
          <img
            v-if="playbackState.now_playing_thumbnail_url"
            :src="playbackState.now_playing_thumbnail_url"
            alt="Now playing cover"
            class="h-full w-full object-cover"
          />
        </div>
        <div class="min-w-0">
          <p class="truncate text-base font-semibold">
            {{ playbackState.now_playing_title || "No active track" }}
          </p>
          <p class="truncate text-xs text-neutral-400">
            {{ (playbackState.now_playing_channel || playbackState.mode || "idle").toUpperCase() }}
            <span v-if="playbackState.elapsed_seconds != null"> · {{ formatDuration(playbackState.elapsed_seconds) }}</span>
            <span v-if="playbackState.duration_seconds"> / {{ formatDuration(playbackState.duration_seconds) }}</span>
          </p>
        </div>
      </div>

      <div class="flex min-w-0 items-center gap-2">
        <UProgress
          :model-value="playbackState.progress_percent || 0"
          :max="100"
          color="neutral"
          size="md"
          class="w-full"
        />
        <span class="shrink-0 whitespace-nowrap text-right text-xs text-neutral-400">
          {{ formatDuration(playbackState.elapsed_seconds) }} / {{ formatDuration(playbackState.duration_seconds) }}
        </span>
      </div>

      <div class="flex flex-wrap items-center gap-2 md:justify-end">
          <div class="flex items-center gap-2">
            <UButton
              type="button"
              :color="sidebarView === SIDEBAR_QUEUE_VIEW ? 'primary' : 'neutral'"
              :variant="sidebarView === SIDEBAR_QUEUE_VIEW ? 'soft' : 'ghost'"
              icon="i-lucide-list-music"
              aria-label="Show queue and history"
              @click="sidebarView = SIDEBAR_QUEUE_VIEW"
            />
            <UButton
              type="button"
              :color="sidebarView === SIDEBAR_SONOS_VIEW ? 'primary' : 'neutral'"
              :variant="sidebarView === SIDEBAR_SONOS_VIEW ? 'soft' : 'ghost'"
              icon="i-lucide-speaker"
              aria-label="Show Sonos speakers"
              @click="sidebarView = SIDEBAR_SONOS_VIEW"
            />
          </div>
        <a
          class="mr-1 text-xs font-medium text-emerald-400 hover:text-emerald-300"
          :href="playbackState.stream_url"
          target="_blank"
          rel="noreferrer"
        >
          Stream
        </a>
        <UButton
          type="button"
          color="primary"
          variant="soft"
          size="xs"
          :disabled="!playbackState.stream_url || isLocalPlaybackActive"
          @click="startLocalPlayback"
        >
          Play Local
        </UButton>
        <UButton
          type="button"
          color="neutral"
          variant="outline"
          size="xs"
          :disabled="!isLocalPlaybackActive"
          @click="stopLocalPlayback"
        >
          Stop Local
        </UButton>
          <UButton type="button" color="neutral" variant="outline" size="xs" @click="skipCurrent">
          Skip
        </UButton>
      </div>
    </div>

    <audio ref="audioEl" class="hidden" :src="playbackState.stream_url" preload="none"></audio>
  </footer>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from "vue";
import { formatDuration } from "../composables/useDuration";
import { useLibraryState } from "../composables/useLibraryState";
import { usePlaybackState } from "../composables/usePlaybackState";
import { SIDEBAR_QUEUE_VIEW, SIDEBAR_SONOS_VIEW, useUiState } from "../composables/useUiState";

const audioEl = ref(null);
const wantsLocalPlayback = ref(false);
const { playbackState } = usePlaybackState();
const { sidebarView } = useUiState();
const { skipCurrent } = useLibraryState();

const isLocalPlaybackActive = computed(() => wantsLocalPlayback.value && Boolean(playbackState.value.stream_url));

async function startLocalPlayback() {
  if (!audioEl.value || !playbackState.value.stream_url) return;
  wantsLocalPlayback.value = true;
  audioEl.value.load();
  try {
    await audioEl.value.play();
  } catch {
    wantsLocalPlayback.value = false;
  }
}

function stopLocalPlayback() {
  wantsLocalPlayback.value = false;
  if (!audioEl.value) return;
  audioEl.value.pause();
  try {
    audioEl.value.currentTime = 0;
  } catch {
    // Some live streams do not support seeking back to the start.
  }
}

watch(
  () => playbackState.value.stream_url,
  async (streamUrl) => {
    if (!audioEl.value) return;
    if (!streamUrl) {
      stopLocalPlayback();
      return;
    }
    if (!wantsLocalPlayback.value) return;
    audioEl.value.load();
    try {
      await audioEl.value.play();
    } catch {
      wantsLocalPlayback.value = false;
    }
  },
  { immediate: true }
);

onUnmounted(() => {
  if (!audioEl.value) return;
  audioEl.value.pause();
});
</script>
