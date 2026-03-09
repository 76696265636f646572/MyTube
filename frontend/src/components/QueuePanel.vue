<template>
  <section class="min-h-0 h-full overflow-hidden rounded-xl border border-neutral-700 bg-neutral-900 p-3 flex flex-col">
    <h2 class="text-2xl font-bold">Queue</h2>
    <ul class="mt-3 min-h-0 flex-1 space-y-2 overflow-auto pr-1">
      <li v-for="item in filteredQueue" :key="item.id">
        <Song
          :item="item"
          mode="queue"
          :playlists="playlists"
        />
      </li>
    </ul>
  </section>
</template>

<script setup>
import { useLibraryState } from "../composables/useLibraryState";
import { useQueueHistoryFilters } from "../composables/useUiState";
import Song from "./Song.vue";

const { queue, history, playlists } = useLibraryState();
const { filteredQueue } = useQueueHistoryFilters(queue, history);
</script>
