<template>
  <section class="min-h-0 h-full overflow-hidden rounded-xl border border-neutral-700 bg-neutral-900 p-3 flex flex-col">
    <div class="flex items-center justify-between gap-3">
      <h2 class="text-2xl font-bold">Play History</h2>
      <UButton
        type="button"
        color="error"
        variant="soft"
        size="xs"
        :disabled="!filteredHistory.length"
        class="shrink-0"
        @click="clearHistory"
      >
        Clear History
      </UButton>
    </div>
    <ul class="mt-3 min-h-0 flex-1 space-y-2 overflow-auto pr-1">
      <li v-for="item in filteredHistory" :key="item.id">
        <Song
          :item="item"
          mode="history"
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

const { queue, history, playlists, clearHistory } = useLibraryState();
const { filteredHistory } = useQueueHistoryFilters(queue, history);
</script>
