<template>
  <footer class="sticky bottom-3 z-10 rounded-xl border border-neutral-700 bg-neutral-900 p-3">
    <div class="grid gap-3 xl:grid-cols-[minmax(0,1.2fr)_minmax(120px,0.9fr)_minmax(220px,1fr)_auto] xl:items-center">
      <div class="min-w-0">
        <div class="break-words text-2xl font-bold">{{ state.now_playing_title || "No active track" }}</div>
        <div class="text-xs uppercase text-neutral-400">
          {{ state.mode?.toUpperCase() }}
          <span v-if="state.elapsed_seconds != null"> · {{ prettyTime(state.elapsed_seconds) }}</span>
          <span v-if="state.duration_seconds"> / {{ prettyTime(state.duration_seconds) }}</span>
        </div>
      </div>

      <progress class="w-full" :max="100" :value="state.progress_percent || 0"></progress>

      <audio class="w-full min-w-0" controls :src="state.stream_url"></audio>

      <div class="flex items-center gap-2">
        <a class="text-sm font-medium text-emerald-400 hover:text-emerald-300" :href="state.stream_url" target="_blank" rel="noreferrer">Stream</a>
        <button type="button" class="rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1 text-sm hover:bg-neutral-700" @click="$emit('skip')">
          Skip
        </button>
      </div>
    </div>
  </footer>
</template>

<script setup>
defineProps({
  state: {
    type: Object,
    required: true,
  },
});

defineEmits(["skip"]);

function prettyTime(value) {
  const totalSeconds = Math.max(0, Math.floor(value || 0));
  const mins = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const secs = String(totalSeconds % 60).padStart(2, "0");
  return `${mins}:${secs}`;
}
</script>
