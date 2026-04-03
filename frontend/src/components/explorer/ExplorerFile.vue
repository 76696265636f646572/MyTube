<template>
  <div class="group relative flex min-w-0 items-center gap-3 rounded-md border px-3 py-2 playlist-card md:min-h-[7.5rem] md:flex-col md:justify-center md:gap-2 md:px-2 md:py-3">
    <UIcon name="i-bi-file-earmark-music" class="size-4 shrink-0 text-blue-300 md:size-10" />
    <div class="min-w-0 flex-1 md:flex-none md:text-center">
      <p class="truncate text-sm md:max-w-full md:whitespace-normal md:break-all md:overflow-visible md:text-clip md:text-center" :title="entry.path">
        {{ entry.name }}
      </p>
      <p v-if="showPath" class="hidden truncate text-xs text-muted md:block md:max-w-full md:whitespace-normal md:break-all md:overflow-visible md:text-clip md:text-center">
        {{ entry.path }}
      </p>
    </div>
    <div class="shrink-0 opacity-100 transition-opacity md:absolute md:right-1 md:top-1 md:opacity-0 md:group-hover:opacity-100" @click.stop>
      <ExplorerEntryMenu
        :entry="entry"
        :playlists="playlists"
        @queue="$emit('queue')"
        @play="$emit('play')"
        @add-to-playlist="(playlistId) => $emit('add-to-playlist', playlistId)"
      />
    </div>
  </div>
</template>

<script setup>
import ExplorerEntryMenu from "./ExplorerEntryMenu.vue";

defineProps({
  entry: {
    type: Object,
    required: true,
  },
  playlists: {
    type: Array,
    default: () => [],
  },
  showPath: {
    type: Boolean,
    default: false,
  },
});

defineEmits(["queue", "play", "add-to-playlist"]);
</script>
