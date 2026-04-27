<template>
  <footer class="player-bar sticky bottom-0 z-10 shrink-0 rounded-xl border border-neutral-700 px-2 py-2 sm:px-3 md:static surface-panel">
    <!-- Mobile: minimal bar — thumbnail, title, play/pause only (controls live in fullscreen player) -->
    <div class="flex md:hidden min-w-0 items-center gap-3">
      <div
        class="player-bar-strip flex min-w-0 flex-1 cursor-pointer items-center gap-3"
        role="button"
        tabindex="0"
        aria-label="Go to fullscreen player"
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
            <UIcon name="i-bi-music-note-beamed" class="size-6" />
          </div>
        </div>
        <div class="min-w-0 flex-1">
          <p class="flex items-center gap-1.5 truncate text-sm font-semibold">
            <span class="min-w-0 truncate">{{ playbackState.now_playing_title || "No active track" }}</span>
            <UButton
              v-if="playbackState.now_playing_id"
              type="button"
              :color="playbackState.now_playing_is_liked ? 'success' : 'neutral'"
              variant="ghost"
              size="xs"
              class="shrink-0 p-0.5"
              :aria-label="playbackState.now_playing_is_liked ? 'Unlike current song' : 'Like current song'"
              @click.stop.prevent="toggleLikeCurrentSong"
            >
              <UIcon :name="playbackState.now_playing_is_liked ? 'i-bi-heart-fill' : 'i-bi-heart'" class="size-4" />
            </UButton>
            <UBadge v-if="playbackState.now_playing_is_live" label="Live" color="error" variant="soft" class="shrink-0" />
          </p>
          <p class="truncate text-xs text-muted">
            {{ (playbackState.now_playing_channel || playbackState.mode || "idle").toUpperCase() }}
          </p>
        </div>
      </div>
      <UButton
        type="button"
        color="neutral"
        variant="ghost"
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
        class="player-bar-strip flex min-w-0 cursor-pointer items-center gap-3"
        role="button"
        tabindex="0"
        aria-label="Go to fullscreen player"        
        @click="onStripClick"
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
          <p class="flex items-center gap-1.5 truncate text-base font-semibold">
            <span class="min-w-0 truncate">{{ playbackState.now_playing_title || "No active track" }}</span>
            <UButton
              v-if="playbackState.now_playing_id"
              type="button"
              :color="playbackState.now_playing_is_liked ? 'success' : 'neutral'"
              variant="ghost"
              size="xs"
              class="shrink-0 p-0.5"
              :aria-label="playbackState.now_playing_is_liked ? 'Unlike current song' : 'Like current song'"
              @click.stop.prevent="toggleLikeCurrentSong"
            >
              <UIcon :name="playbackState.now_playing_is_liked ? 'i-bi-heart-fill' : 'i-bi-heart'" class="size-4" />
            </UButton>
            <UBadge v-if="playbackState.now_playing_is_live" label="Live" color="error" variant="soft" class="shrink-0" />
          </p>
          <p class="truncate text-xs text-muted">
            {{ (playbackState.now_playing_channel || playbackState.mode || "idle").toUpperCase() }}
          </p>
        </div>
      </div>

      <div class="min-w-0 flex flex-col items-center">
        <div class="mb-3 flex w-full items-center justify-center gap-2">
          <UButton
            type="button"
            :color="playbackState.shuffle_enabled ? 'primary' : 'neutral'"
            :variant="playbackState.shuffle_enabled ? 'soft' : 'ghost'"
            icon="i-bi-shuffle"
            aria-label="Toggle shuffle"
            class="cursor-pointer"
            @click="setShuffleEnabled(!playbackState.shuffle_enabled)"
          />
          <UButton type="button" color="neutral" variant="ghost" icon="i-bi-skip-backward-fill" aria-label="Previous" class="cursor-pointer" @click="previousTrack" />
          <UButton
            type="button"
            color="neutral"
            variant="solid"
            :icon="playPauseIcon"
            aria-label="Toggle play pause"
            class="rounded-full cursor-pointer"
            @click="togglePause"
          />
          <UButton type="button" color="neutral" variant="ghost" icon="i-bi-skip-forward-fill" aria-label="Next" class="cursor-pointer" @click="skipCurrent" />
          <UButton
            type="button"
            :color="playbackState.repeat_mode !== 'off' ? 'primary' : 'neutral'"
            :variant="playbackState.repeat_mode !== 'off' ? 'soft' : 'ghost'"
            :icon="repeatIcon"
            :aria-label="repeatLabel"
            class="cursor-pointer"
            @click="cycleRepeatMode"
          />
        </div>

        <SongProgress
          :progress-percent="playbackState.progress_percent ?? 0"
          :elapsed-seconds="playbackState.elapsed_seconds"
          :duration-seconds="playbackState.duration_seconds"
          :can-seek="playbackState.can_seek"
          size="md"
          class="cursor-pointer"
          @seek="seekToPercent"
        />
      </div>

      <div class="flex flex-wrap items-center gap-2 md:justify-end md:pl-4">
          <div class="hidden items-center gap-2 md:flex">
            <UButton
              type="button"
              :color="queueSidebarButtonActive ? 'primary' : 'neutral'"
              :variant="queueSidebarButtonActive ? 'soft' : 'ghost'"
              icon="i-bi-music-note-list"
              aria-label="Show queue and history"
              class="cursor-pointer"
              @click="toggleRightSidebar(SIDEBAR_QUEUE_VIEW)"
            />
            <UButton
              type="button"
              :color="speakersSidebarButtonActive ? 'primary' : 'neutral'"
              :variant="speakersSidebarButtonActive ? 'soft' : 'ghost'"
              icon="i-bi-speaker-fill"
              aria-label="Show speakers"
              class="cursor-pointer"
              @click="toggleRightSidebar(SIDEBAR_SPEAKERS_VIEW)"
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
          :disabled="isLocalPlaybackActive"
          class="cursor-pointer"
          @click="startLocalPlayback"
        >
          Connect
        </UButton>
        <UButton
          type="button"
          color="neutral"
          variant="outline"
          size="xs"
          :disabled="!isLocalPlaybackActive"
          class="cursor-pointer"
          @click="stopLocalPlayback"
        >
          Disconnect
        </UButton>
        <div class="ml-1 flex w-[220px] items-center gap-2">
          <UButton
            type="button"
            color="neutral"
            variant="ghost"
            :icon="localVolumeIcon"
            aria-label="Toggle local audio mute"
            :disabled="!playbackState.stream_url"
            class="cursor-pointer"
            @click="toggleMuted"
          />
          <USlider
            :model-value="localVolumePercent"
            :min="0"
            :max="100"
            color="neutral"
            size="sm"
            :disabled="!playbackState.stream_url"
            :ui="{ root: 'group', range: 'transition-colors group-hover:bg-primary', thumb: 'opacity-0 cursor-pointer transition-opacity group-hover:opacity-100' }"
            aria-label="Local audio volume"
            class="cursor-pointer"
            @update:model-value="onLocalVolumeChange"
          />
        </div>
      </div>
    </div>

  </footer>
</template>

<script setup>
import { computed, inject } from "vue";
import { useRouter } from "vue-router";
import { useBreakpoint } from "../composables/useBreakpoint";
import { useLibraryState } from "../composables/useLibraryState";
import { usePlaybackState } from "../composables/usePlaybackState";
import { SIDEBAR_QUEUE_VIEW, SIDEBAR_SPEAKERS_VIEW, useUiState } from "../composables/useUiState";

const {
  startLocalPlayback,
  stopLocalPlayback,
  localVolume,
  isMuted,
  setLocalVolume,
  toggleMuted,
  isLocalPlaybackActive,
} = inject("localPlayback"); 

const router = useRouter();
const { playbackState } = usePlaybackState();
const { isTabletLayout } = useBreakpoint();
const { sidebarView, rightSidebarOpen } = useUiState();
const { skipCurrent, previousTrack, togglePause, setRepeatMode, setShuffleEnabled, seekToPercent, toggleLikeCurrentSong } = useLibraryState();

/** Tablet: highlight only while the overlay is open; desktop: highlight matches visible sidebar. */
const queueSidebarButtonActive = computed(() => {
  if (isTabletLayout.value) {
    return rightSidebarOpen.value && sidebarView.value === SIDEBAR_QUEUE_VIEW;
  }
  return sidebarView.value === SIDEBAR_QUEUE_VIEW;
});

const speakersSidebarButtonActive = computed(() => {
  if (isTabletLayout.value) {
    return rightSidebarOpen.value && sidebarView.value === SIDEBAR_SPEAKERS_VIEW;
  }
  return sidebarView.value === SIDEBAR_SPEAKERS_VIEW;
});

const playPauseIcon = computed(() =>
  playbackState.value.mode === "playing" && !playbackState.value.paused ? "i-bi-pause-fill" : "i-bi-play-fill"
);

const repeatIcon = computed(() => (playbackState.value.repeat_mode === "one" ? "i-bi-repeat-1" : "i-bi-repeat"));
const repeatLabel = computed(() => {
  if (playbackState.value.repeat_mode === "all") return "Repeat all";
  if (playbackState.value.repeat_mode === "one") return "Repeat one";
  return "Repeat off";
});
const localVolumePercent = computed(() => Math.round((localVolume.value || 0) * 100));
const localVolumeIcon = computed(() => {
  if (isMuted.value || localVolume.value <= 0) return "i-bi-volume-mute-fill";
  if (localVolume.value < 0.5) return "i-bi-volume-down-fill";
  return "i-bi-volume-up-fill";
});

function toggleRightSidebar(view) {
  if (isTabletLayout.value) {
    if (rightSidebarOpen.value && sidebarView.value === view) {
      rightSidebarOpen.value = false;
      return;
    }
    sidebarView.value = view;
    rightSidebarOpen.value = true;
    return;
  }
  sidebarView.value = view;
}

function onStripClick() {
  router.push("/fullscreen-player");
}

function cycleRepeatMode() {
  const modes = ["off", "all", "one"];
  const currentMode = playbackState.value.repeat_mode || "off";
  const nextMode = modes[(modes.indexOf(currentMode) + 1) % modes.length];
  setRepeatMode(nextMode);
}

function onLocalVolumeChange(value) {
  const sliderValue = Array.isArray(value) ? value[0] : value;
  const nextPercent = Number(sliderValue ?? 0);
  if (!Number.isFinite(nextPercent)) return;
  setLocalVolume(nextPercent / 100);
}
</script>
