<template>
  <footer class="player-bar sticky bottom-0 z-10 shrink-0 rounded-xl border border-neutral-700 px-2 py-2 sm:px-3 md:static surface-panel">
    <!-- Mobile: minimal bar — thumbnail, title, play/pause only (controls live in fullscreen player) -->
    <div class="flex md:hidden min-w-0 items-center gap-3">
      <div
        class="player-bar-strip flex min-w-0 flex-1 cursor-pointer items-center gap-3"
        role="button"
        tabindex="0"
        aria-label="Expand player"
        @click="onStripClick"
      >
        <div class="h-12 w-12 shrink-0 overflow-hidden rounded-md border border-neutral-700 surface-elevated">
          <img
            v-if="playbackState.now_playing_thumbnail_url"
            :src="playbackState.now_playing_thumbnail_url"
            alt=""
            class="h-full w-full object-cover"
          />
          <div v-else class="flex h-full w-full items-center justify-center bg-neutral-800 text-muted">
            <UIcon name="i-lucide-music" class="size-6" />
          </div>
        </div>
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-semibold">
            {{ playbackState.now_playing_title || "No active track" }}
          </p>
          <p class="truncate text-xs text-muted">
            {{ (playbackState.now_playing_channel || playbackState.mode || "idle").toUpperCase() }}
          </p>
        </div>
      </div>
      <UButton
        type="button"
        color="primary"
        variant="solid"
        class="player-bar-mobile-play shrink-0 min-h-[2.75rem] min-w-[2.75rem] flex items-center justify-center p-0"
        aria-label="Play / Pause"
        @click.stop="togglePause"
      >
        <span class="flex items-center justify-center size-full">
          <UIcon :name="playPauseIcon" class="size-6 shrink-0" />
        </span>
      </UButton>
    </div>

    <!-- Desktop: full bar with progress and all controls -->
    <div class="hidden grid items-center gap-3 md:grid md:grid-cols-[minmax(0,1fr)_minmax(340px,560px)_minmax(0,1fr)]">
      <div
        class="player-bar-strip flex min-w-0 cursor-default items-center gap-3"
      >
        <div class="h-12 w-12 shrink-0 overflow-hidden rounded-md border border-neutral-700 surface-elevated">
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
          <p class="truncate text-xs text-muted">
            {{ (playbackState.now_playing_channel || playbackState.mode || "idle").toUpperCase() }}
            <span v-if="playbackState.elapsed_seconds != null"> · {{ formatDuration(playbackState.elapsed_seconds) }}</span>
            <span v-if="playbackState.duration_seconds"> / {{ formatDuration(playbackState.duration_seconds) }}</span>
          </p>
        </div>
      </div>

      <div class="min-w-0 flex flex-col items-center">
        <div class="mb-2 flex w-full items-center justify-center gap-2">
          <UButton
            type="button"
            :color="playbackState.shuffle_enabled ? 'primary' : 'neutral'"
            :variant="playbackState.shuffle_enabled ? 'soft' : 'ghost'"
            icon="i-lucide-shuffle"
            aria-label="Toggle shuffle"
            @click="setShuffleEnabled(!playbackState.shuffle_enabled)"
          />
          <UButton type="button" color="neutral" variant="ghost" icon="i-lucide-skip-back" aria-label="Previous" @click="previousTrack" />
          <UButton
            type="button"
            color="primary"
            variant="solid"
            :icon="playPauseIcon"
            aria-label="Toggle play pause"
            @click="togglePause"
          />
          <UButton type="button" color="neutral" variant="ghost" icon="i-lucide-skip-forward" aria-label="Next" @click="skipCurrent" />
          <UButton
            type="button"
            :color="playbackState.repeat_mode !== 'off' ? 'primary' : 'neutral'"
            :variant="playbackState.repeat_mode !== 'off' ? 'soft' : 'ghost'"
            :icon="repeatIcon"
            :aria-label="repeatLabel"
            @click="cycleRepeatMode"
          />
        </div>

        <div
          ref="progressTrackEl"
          class="group w-full cursor-pointer"
          :class="{ 'pointer-events-none opacity-60': !playbackState.can_seek }"
          role="button"
          tabindex="0"
          :aria-disabled="!playbackState.can_seek"
          aria-label="Seek current track"
          @click="onProgressClick"
        >
          <UProgress
            :model-value="playbackState.progress_percent || 0"
            :max="100"
            color="primary"
            size="md"
            class="w-full"
          />
        </div>
        <div class="mt-1 flex w-full items-center justify-between text-xs text-muted">
          <span>{{ formatDuration(playbackState.elapsed_seconds) }}</span>
          <span>{{ formatDuration(playbackState.duration_seconds) }}</span>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2 md:justify-end md:pl-4">
          <div class="hidden items-center gap-2 md:flex">
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
      </div>
    </div>

  </footer>
</template>

<script setup>
import { computed, inject, ref } from "vue";
import { formatDuration } from "../composables/useDuration";
import { useBreakpoint } from "../composables/useBreakpoint";
import { useLibraryState } from "../composables/useLibraryState";
import { usePlaybackState } from "../composables/usePlaybackState";
import { SIDEBAR_QUEUE_VIEW, SIDEBAR_SONOS_VIEW, fullScreenPlayerOpen, useUiState } from "../composables/useUiState";

const progressTrackEl = ref(null);
const { isMobile } = useBreakpoint();
const { playbackState } = usePlaybackState();
const { sidebarView } = useUiState();
const { skipCurrent, previousTrack, togglePause, setRepeatMode, setShuffleEnabled, seekToPercent } = useLibraryState();
const { startLocalPlayback, stopLocalPlayback, isLocalPlaybackActive } = inject("localPlayback", {
  startLocalPlayback: () => {},
  stopLocalPlayback: () => {},
  isLocalPlaybackActive: computed(() => false),
});
const playPauseIcon = computed(() =>
  playbackState.value.mode === "playing" && !playbackState.value.paused ? "i-lucide-pause" : "i-lucide-play"
);
const repeatIcon = computed(() => (playbackState.value.repeat_mode === "one" ? "i-lucide-repeat-1" : "i-lucide-repeat"));
const repeatLabel = computed(() => {
  if (playbackState.value.repeat_mode === "all") return "Repeat all";
  if (playbackState.value.repeat_mode === "one") return "Repeat one";
  return "Repeat off";
});

function onStripClick() {
  if (isMobile.value) fullScreenPlayerOpen.value = true;
}

function cycleRepeatMode() {
  const modes = ["off", "all", "one"];
  const currentMode = playbackState.value.repeat_mode || "off";
  const nextMode = modes[(modes.indexOf(currentMode) + 1) % modes.length];
  setRepeatMode(nextMode);
}

function onProgressClick(event) {
  if (!progressTrackEl.value || !playbackState.value.can_seek) return;
  const bounds = progressTrackEl.value.getBoundingClientRect();
  if (!bounds.width) return;
  const raw = ((event.clientX - bounds.left) / bounds.width) * 100;
  const percent = Math.max(0, Math.min(100, raw));
  seekToPercent(percent);
}
</script>
