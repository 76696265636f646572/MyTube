<template>
  <section class="min-h-0 h-full overflow-hidden rounded-xl border border-neutral-700 p-3 flex flex-col surface-panel">
    <div class="flex items-center justify-between gap-3">
      <h2 class="text-2xl font-bold">Queue</h2>
      <UButton
        type="button"
        color="error"
        variant="soft"
        size="xs"
        :disabled="!filteredQueue.length"
        class="shrink-0"
        @click="clearQueue"
      >
        Clear Queue
      </UButton>
    </div>
    <div class="mt-3 min-h-0 flex-1 overflow-auto pr-1">
      <!-- When filtered: plain list, no drag -->
      <ul v-if="isFiltered" class="space-y-2">
        <li v-for="item in filteredQueue" :key="item.id">
          <Song :item="item" mode="queue" :playlists="playlists" />
        </li>
      </ul>
      <!-- When not filtered: playing items fixed, queued items draggable -->
      <template v-else>
        <ul class="space-y-2">
          <li v-for="item in playingItems" :key="item.id">
            <Song :item="item" mode="queue" :playlists="playlists" />
          </li>
        </ul>
        <VueDraggable
          v-model="queuedItems"
          tag="ul"
          class="space-y-2"
          :animation="150"
          :delay="200"
          :delay-on-touch-only="true"
          ghost-class="queue-drag-ghost"
          chosen-class="queue-drag-chosen"
          @end="onReorderEnd"
        >
          <li v-for="item in queuedItems" :key="item.id">
            <Song :item="item" mode="queue" :playlists="playlists" />
          </li>
        </VueDraggable>
      </template>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from "vue";

import { VueDraggable } from "vue-draggable-plus";

import { useLibraryState } from "../composables/useLibraryState";
import { useQueueHistoryFilters } from "../composables/useUiState";
import Song from "./Song.vue";

const { queue, history, playlists, clearQueue, reorderQueueItem } = useLibraryState();
const { filteredQueue, isFiltered } = useQueueHistoryFilters(queue, history);

const playingItems = computed(() => queue.value.filter((item) => item.status === "playing"));

const queuedItems = ref([]);

function syncQueuedItems() {
  const queued = queue.value.filter((item) => item.status === "queued");
  queuedItems.value = [...queued];
}

watch(queue, syncQueuedItems, { immediate: true });

function onReorderEnd(evt) {
  const { oldIndex, newIndex } = evt;
  if (oldIndex === newIndex) return;
  const item = queuedItems.value[newIndex];
  if (!item?.id) return;
  reorderQueueItem(item.id, newIndex);
}
</script>
