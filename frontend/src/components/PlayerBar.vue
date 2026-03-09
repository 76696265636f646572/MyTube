<template>
  <footer class="sticky bottom-0 z-10 shrink-0 rounded-xl border border-neutral-700 bg-neutral-900 px-2 py-2 sm:px-3 md:static">
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
            <span v-if="state.elapsed_seconds != null"> · {{ formatDuration(state.elapsed_seconds) }}</span>
            <span v-if="state.duration_seconds"> / {{ formatDuration(state.duration_seconds) }}</span>
          </p>
        </div>
      </div>

      <div class="flex min-w-0 items-center gap-2">
        <UProgress
          :model-value="state.progress_percent || 0"
          :max="100"
          color="neutral"
          size="md"
          class="w-full"
        />
        <span class="shrink-0 whitespace-nowrap text-right text-xs text-neutral-400">
          {{ formatDuration(state.elapsed_seconds) }} / {{ formatDuration(state.duration_seconds) }}
        </span>
      </div>

      <div class="flex flex-wrap items-center gap-2 md:justify-end">
          <div class="flex items-center gap-2">
            <UButton
              type="button"
              :color="sidebarView === sidebarQueueView ? 'primary' : 'neutral'"
              :variant="sidebarView === sidebarQueueView ? 'soft' : 'ghost'"
              icon="i-lucide-list-music"
              aria-label="Show queue and history"
              @click="emit('set-sidebar-view', sidebarQueueView)"
            />
            <UButton
              type="button"
              :color="sidebarView === sidebarSonosView ? 'primary' : 'neutral'"
              :variant="sidebarView === sidebarSonosView ? 'soft' : 'ghost'"
              icon="i-lucide-speaker"
              aria-label="Show Sonos speakers"
              @click="emit('set-sidebar-view', sidebarSonosView)"
            />
          </div>
        <a
          class="mr-1 text-xs font-medium text-emerald-400 hover:text-emerald-300"
          :href="state.stream_url"
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
          :disabled="!state.stream_url || isLocalPlaybackActive"
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
        <UButton type="button" color="neutral" variant="outline" size="xs" @click="emit('skip')">
          Skip
        </UButton>
      </div>
    </div>

    <audio ref="audioEl" class="hidden" :src="state.stream_url" preload="none"></audio>
  </footer>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from "vue";
import { formatDuration } from "../composables/useDuration";

const props = defineProps({
  state: {
    type: Object,
    required: true,
  },
  sidebarView: {
    type: String,
    required: true,
  },
  sidebarQueueView: {
    type: String,
    required: true,
  },
  sidebarSonosView: {
    type: String,
    required: true,
  },
});

const emit = defineEmits(["skip", "set-sidebar-view"]);

const audioEl = ref(null);
const wantsLocalPlayback = ref(false);

const isLocalPlaybackActive = computed(() => wantsLocalPlayback.value && Boolean(props.state.stream_url));

async function startLocalPlayback() {
  if (!audioEl.value || !props.state.stream_url) return;
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
  () => props.state.stream_url,
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
