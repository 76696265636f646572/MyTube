<template>
  <section
    class="fullscreen-player min-h-dvh w-full flex flex-col overflow-hidden bg-[var(--app-body-bg)]"
    aria-label="Now playing"
  >
      <!-- Header: back, context, title, menu -->
      <header class="fullscreen-player-header flex shrink-0 items-center justify-between gap-3 px-6 pb-2 pt-[max(1rem,env(safe-area-inset-top))]">
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          icon="i-bi-chevron-down"
          size="lg"
          class="shrink-0"
          aria-label="Close"
          @click="close"
        />
        <div class="min-w-0 flex-1 text-center">
          <p class="text-xs font-medium uppercase tracking-wider text-muted">
            Playing from {{ playbackState.now_playing_channel || "Radio" }}
          </p>
          <p class="flex items-center justify-center gap-2 truncate text-lg font-bold">
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
          </p>
        </div>
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          icon="i-bi-three-dots-vertical"
          size="lg"
          class="shrink-0"
          aria-label="More options"
        />
      </header>

      <!-- Main: thumbnail as background + overlay with art + info + progress (minimal top spacing) -->
      <div class="fullscreen-player-main relative min-h-0 flex-1 overflow-auto">
        <!-- Background: thumbnail blurred + dark overlay -->
        <div
          class="fullscreen-player-bg absolute inset-0 bg-cover bg-center bg-no-repeat opacity-30"
          :style="bgStyle"
        />
        <div
          class="fullscreen-player-bg-blur absolute inset-0 bg-cover bg-center bg-no-repeat"
          :style="bgStyle"
        />
        <div class="absolute inset-0 bg-gradient-to-b from-black/60 via-black/40 to-black/80" aria-hidden="true" />

        <!-- Content overlay: thumbnail + title + artists + add, then progress -->
        <div class="relative flex flex-col gap-4 px-6 pt-4 pb-6">
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
                <UIcon name="i-bi-music-note-beamed" />
              </div>
            </div>
            <div class="min-w-0 flex-1 pt-1">
              <h2 class="flex items-center gap-2 text-xl font-bold leading-tight">
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
              </h2>
              <UBadge v-if="playbackState.now_playing_is_live" label="Live" color="error" variant="soft" class="shrink-0" />
              <p class="mt-0.5 text-sm text-muted">
                {{ (playbackState.now_playing_channel || playbackState.mode || "idle").toUpperCase() }}
              </p>
            </div>
            <UButton
              type="button"
              color="neutral"
              variant="ghost"
              icon="i-bi-plus"
              size="lg"
              class="shrink-0 rounded-full border border-white/20"
              aria-label="Add to playlist"
            />
          </div>

          <div class="space-y-2">
            <SongProgress
              :progress-percent="playbackState.progress_percent ?? 0"
              :elapsed-seconds="playbackState.elapsed_seconds"
              :duration-seconds="playbackState.duration_seconds"
              :can-seek="playbackState.can_seek"
              size="md"
              @seek="seekToPercent"
            />
          </div>
        </div>
      </div>

      <!-- Controls: shuffle, prev, play/pause (large), next, repeat -->
      <div class="fullscreen-player-controls shrink-0 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-2">
        <div class="flex items-center justify-center gap-4 mb-10">
          <UButton
            type="button"
            :color="playbackState.shuffle_enabled ? 'primary' : 'neutral'"
            :variant="playbackState.shuffle_enabled ? 'soft' : 'ghost'"
            icon="i-bi-shuffle"
            size="lg"
            aria-label="Shuffle"
            @click="setShuffleEnabled(!playbackState.shuffle_enabled)"
          />
          <UButton
            type="button"
            color="neutral"
            variant="ghost"
            icon="i-bi-skip-backward-fill"
            size="xl"
            aria-label="Previous"
            @click="previousTrack"
          />
          <UButton
            type="button"
            color="neutral"
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
            icon="i-bi-skip-forward-fill"
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
        <div class="fullscreen-player-local-controls mt-3 flex flex-wrap items-center justify-center gap-2">
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
            :disabled="isLocalPlaybackActive"
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
            @click="stopLocalPlayback"
          >
            Disconnect
          </UButton>
          <div class="mt-1 flex w-full max-w-xs items-center gap-2 px-2">
            <UButton
              type="button"
              color="neutral"
              variant="ghost"
              :icon="localVolumeIcon"
              aria-label="Toggle local audio mute"
              :disabled="!playbackState.stream_url"
              @click="toggleMuted"
            />
            <USlider
              :model-value="localVolumePercent"
              :min="0"
              :max="100"
              color="neutral"
              size="sm"
              class="flex-1"
              :disabled="!playbackState.stream_url"
              aria-label="Local audio volume"
              @update:model-value="onLocalVolumeChange"
            />
          </div>
        </div>
      </div>
  </section>
</template>

<script setup>
import { computed, inject } from "vue";
import { useRouter } from "vue-router";
import { useLibraryState } from "../composables/useLibraryState";
import { usePlaybackState } from "../composables/usePlaybackState";

const {
  startLocalPlayback,
  stopLocalPlayback,
  isLocalPlaybackActive,
  localVolume,
  isMuted,
  setLocalVolume,
  toggleMuted,
} = inject("localPlayback");

const router = useRouter();
const { playbackState } = usePlaybackState();
const { skipCurrent, previousTrack, togglePause, setRepeatMode, setShuffleEnabled, seekToPercent, toggleLikeCurrentSong } = useLibraryState();

const bgStyle = computed(() => {
  const url = playbackState.value.now_playing_thumbnail_url;
  if (!url) return {};
  return { backgroundImage: `url(${url})` };
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

function close() {
  const backPath = typeof window !== "undefined" ? window.history.state?.back : null;
  if (typeof backPath === "string" && backPath.startsWith("/")) {
    router.back();
    return;
  }
  router.push("/");
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
