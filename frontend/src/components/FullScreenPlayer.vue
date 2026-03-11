<template>
  <Teleport to="body">
    <div
      v-show="fullScreenPlayerOpen"
      class="fullscreen-player fixed inset-0 z-[100] flex flex-col bg-[var(--app-body-bg)]"
      role="dialog"
      aria-label="Now playing"
    >
      <!-- Header: back, context, title, menu -->
      <header class="fullscreen-player-header flex shrink-0 items-center justify-between gap-3 px-4 pb-2 pt-[max(1rem,env(safe-area-inset-top))]">
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          icon="i-lucide-chevron-down"
          size="lg"
          class="shrink-0"
          aria-label="Close"
          @click="close"
        />
        <div class="min-w-0 flex-1 text-center">
          <p class="text-xs font-medium uppercase tracking-wider text-muted">
            Playing from {{ playbackState.now_playing_channel || "Radio" }}
          </p>
          <p class="truncate text-lg font-bold">
            {{ playbackState.now_playing_title || "No active track" }}
          </p>
        </div>
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          icon="i-lucide-more-vertical"
          size="lg"
          class="shrink-0"
          aria-label="More options"
        />
      </header>

      <!-- Main: thumbnail as background + overlay with art + info + progress (minimal top spacing) -->
      <div class="fullscreen-player-main relative min-h-0 flex-1 overflow-auto">
        <!-- Background: thumbnail blurred + dark overlay -->
        <div
          class="fullscreen-player-bg absolute inset-0 bg-cover bg-center opacity-30"
          :style="bgStyle"
        />
        <div
          class="fullscreen-player-bg-blur absolute inset-0 bg-cover bg-center"
          :style="bgStyle"
        />
        <div class="absolute inset-0 bg-gradient-to-b from-black/60 via-black/40 to-black/80" aria-hidden="true" />

        <!-- Content overlay: thumbnail + title + artists + add, then progress -->
        <div class="relative flex flex-col gap-4 px-4 pt-4 pb-6">
          <div class="flex items-start gap-4">
            <div class="h-24 w-24 shrink-0 overflow-hidden rounded-lg border border-white/10 shadow-xl">
              <img
                v-if="playbackState.now_playing_thumbnail_url"
                :src="playbackState.now_playing_thumbnail_url"
                alt=""
                class="h-full w-full object-cover"
              />
              <div
                v-else
                class="flex h-full w-full items-center justify-center bg-neutral-800 text-4xl text-muted"
              >
                <UIcon name="i-lucide-music" />
              </div>
            </div>
            <div class="min-w-0 flex-1 pt-1">
              <h2 class="text-xl font-bold leading-tight">
                {{ playbackState.now_playing_title || "No active track" }}
              </h2>
              <p class="mt-0.5 text-sm text-muted">
                {{ (playbackState.now_playing_channel || playbackState.mode || "idle").toUpperCase() }}
              </p>
            </div>
            <UButton
              type="button"
              color="neutral"
              variant="ghost"
              icon="i-lucide-plus"
              size="lg"
              class="shrink-0 rounded-full border border-white/20"
              aria-label="Add to playlist"
            />
          </div>

          <div class="space-y-2">
            <div
              ref="progressTrackEl"
              class="cursor-pointer"
              :class="{ 'pointer-events-none opacity-60': !playbackState.can_seek }"
              role="button"
              tabindex="0"
              :aria-disabled="!playbackState.can_seek"
              aria-label="Seek"
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
            <div class="flex justify-between text-xs text-muted">
              <span>{{ formatDuration(playbackState.elapsed_seconds) }}</span>
              <span>{{ formatDuration(playbackState.duration_seconds) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Controls: shuffle, prev, play/pause (large), next, repeat -->
      <div class="fullscreen-player-controls shrink-0 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-2">
        <div class="flex items-center justify-center gap-4">
          <UButton
            type="button"
            :color="playbackState.shuffle_enabled ? 'primary' : 'neutral'"
            :variant="playbackState.shuffle_enabled ? 'soft' : 'ghost'"
            icon="i-lucide-shuffle"
            size="lg"
            aria-label="Shuffle"
            @click="setShuffleEnabled(!playbackState.shuffle_enabled)"
          />
          <UButton
            type="button"
            color="neutral"
            variant="ghost"
            icon="i-lucide-skip-back"
            size="xl"
            aria-label="Previous"
            @click="previousTrack"
          />
          <UButton
            type="button"
            color="primary"
            variant="solid"
            size="xl"
            class="fullscreen-player-play-button min-h-[4.5rem] min-w-[4.5rem] flex items-center justify-center rounded-full p-0"
            aria-label="Play / Pause"
            @click="togglePause"
          >
            <span class="flex size-full items-center justify-center">
              <UIcon :name="playPauseIcon" class="size-8 shrink-0" />
            </span>
          </UButton>
          <UButton
            type="button"
            color="neutral"
            variant="ghost"
            icon="i-lucide-skip-forward"
            size="xl"
            aria-label="Next"
            @click="skipCurrent"
          />
          <UButton
            type="button"
            :color="playbackState.repeat_mode !== 'off' ? 'primary' : 'neutral'"
            :variant="playbackState.repeat_mode !== 'off' ? 'soft' : 'ghost'"
            :icon="repeatIcon"
            size="lg"
            :aria-label="repeatLabel"
            @click="cycleRepeatMode"
          />
        </div>
        <div class="mt-3 flex flex-wrap items-center justify-center gap-2">
          <a
            class="text-xs font-medium text-emerald-400 hover:text-emerald-300"
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
    </div>
  </Teleport>
</template>

<script setup>
import { computed, inject, ref, watch } from "vue";
import { formatDuration } from "../composables/useDuration";
import { useLibraryState } from "../composables/useLibraryState";
import { usePlaybackState } from "../composables/usePlaybackState";
import { useUiState } from "../composables/useUiState";

const progressTrackEl = ref(null);
const { playbackState } = usePlaybackState();
const { fullScreenPlayerOpen } = useUiState();
const { startLocalPlayback, stopLocalPlayback, isLocalPlaybackActive } = inject("localPlayback", {
  startLocalPlayback: () => {},
  stopLocalPlayback: () => {},
  isLocalPlaybackActive: computed(() => false),
});

watch(fullScreenPlayerOpen, (open) => {
  if (typeof document === "undefined") return;
  document.body.style.overflow = open ? "hidden" : "";
});
const { skipCurrent, previousTrack, togglePause, setRepeatMode, setShuffleEnabled, seekToPercent } = useLibraryState();

const bgStyle = computed(() => {
  const url = playbackState.value.now_playing_thumbnail_url;
  if (!url) return {};
  return { backgroundImage: `url(${url})` };
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

function close() {
  fullScreenPlayerOpen.value = false;
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

<style scoped>
.fullscreen-player-bg-blur {
  filter: blur(80px);
  opacity: 0.5;
}

/* Center play/pause icon (same optical nudge as mobile player bar) */
.fullscreen-player-play-button > * {
  display: flex;
  align-items: center;
  justify-content: center;
}
.fullscreen-player-play-button :deep(svg) {
  display: block;
  margin: 0;
  flex-shrink: 0;
  transform: translateX(-1px);
}
</style>
