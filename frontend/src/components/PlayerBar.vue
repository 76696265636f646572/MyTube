<template>
  <footer class="sticky bottom-2 z-10 rounded-xl border border-neutral-700 bg-neutral-900 px-3 py-2">
    <div class="grid items-center gap-2 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto]">
      <div class="flex min-w-0 items-center gap-3">
        <div class="h-12 w-12 shrink-0 overflow-hidden rounded-md border border-neutral-700 bg-neutral-800">
          <img
            v-if="state.now_playing_thumbnail_url"
            :src="state.now_playing_thumbnail_url"
            alt="Now playing cover"
            class="h-full w-full object-cover"
          />
        </div>
        <div class="min-w-0">
          <p class="truncate text-base font-semibold">
            {{ state.now_playing_title || "No active track" }}
          </p>
          <p class="truncate text-xs text-neutral-400">
            {{ (state.now_playing_channel || state.mode || "idle").toUpperCase() }}
            <span v-if="state.elapsed_seconds != null"> · {{ prettyTime(state.elapsed_seconds) }}</span>
            <span v-if="state.duration_seconds"> / {{ prettyTime(state.duration_seconds) }}</span>
          </p>
        </div>
      </div>

      <div class="flex min-w-0 items-center gap-2">
        <progress class="h-2 w-full overflow-hidden rounded bg-neutral-700" :max="100" :value="state.progress_percent || 0"></progress>
        <span class="w-20 shrink-0 text-right text-xs text-neutral-400">
          {{ prettyTime(state.elapsed_seconds) }} / {{ prettyTime(state.duration_seconds) }}
        </span>
      </div>

      <div class="flex items-center gap-2">
        <a
          class="text-xs font-medium text-emerald-400 hover:text-emerald-300"
          :href="state.stream_url"
          target="_blank"
          rel="noreferrer"
        >
          Stream
        </a>
        <button
          type="button"
          class="rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1 text-xs hover:bg-neutral-700"
          @click="$emit('skip')"
        >
          Skip
        </button>
      </div>
    </div>

    <audio ref="audioEl" class="hidden" :src="state.stream_url" preload="none"></audio>
  </footer>
</template>

<script setup>
import { ref, watch } from "vue";

const props = defineProps({
  state: {
    type: Object,
    required: true,
  },
});

defineEmits(["skip"]);

const audioEl = ref(null);

watch(
  () => props.state.stream_url,
  async (streamUrl) => {
    if (!streamUrl || !audioEl.value) return;
    try {
      await audioEl.value.play();
    } catch {
      // Browser autoplay policies may block playback until user interaction.
    }
  },
  { immediate: true }
);

function prettyTime(value) {
  const totalSeconds = Math.max(0, Math.floor(value || 0));
  const mins = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const secs = String(totalSeconds % 60).padStart(2, "0");
  return `${mins}:${secs}`;
}
</script>
