<template>
  <section class="min-h-0 h-full overflow-hidden rounded-xl border border-neutral-700 bg-neutral-900 p-3 flex flex-col">
    <h2 class="text-2xl font-bold">Queue</h2>
    <ul class="mt-3 min-h-0 flex-1 space-y-2 overflow-auto pr-1">
      <li v-for="item in queue" :key="item.id">
        <Song
          :item="item"
          mode="queue"
          :playlists="playlists"
          :on-add-to-playlist="onAddToPlaylist"
          :on-add-to-queue="onAddToQueue"
          :on-play-now="onPlayNow"
        />
      </li>
    </ul>
  </section>
</template>

<script setup>
import Song from "./Song.vue";

defineProps({
  queue: { type: Array, default: () => [] },
  playlists: { type: Array, default: () => [] },
  onAddToPlaylist: { type: Function, default: null },
  onAddToQueue: { type: Function, default: null },
  onPlayNow: { type: Function, default: null },
});
</script>
