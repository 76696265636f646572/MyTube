<template>
  <section class="min-h-0 overflow-hidden rounded-xl border border-neutral-700 bg-neutral-900 p-3">
    <h2 class="text-2xl font-bold">Queue</h2>
    <ul class="mt-3 max-h-[34vh] space-y-2 overflow-auto pr-1">
      <li v-for="item in queue" :key="item.id" class="rounded-md border border-neutral-700 p-2">
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div class="min-w-0 flex-1">
            <span class="block break-words text-sm font-medium">#{{ item.queue_position }} {{ item.title || item.source_url }}</span>
            <span class="text-xs text-neutral-400">{{ item.status }} · {{ item.channel || "unknown" }}</span>
          </div>
          <div class="flex flex-wrap justify-end gap-1">
            <button
              type="button"
              class="rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1 text-xs hover:bg-neutral-700"
              @click="$emit('reorder', { itemId: item.id, newPosition: Math.max(0, item.queue_position - 2) })"
            >
              Up
            </button>
            <button
              type="button"
              class="rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1 text-xs hover:bg-neutral-700"
              @click="$emit('reorder', { itemId: item.id, newPosition: item.queue_position })"
            >
              Down
            </button>
            <button
              type="button"
              class="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs hover:bg-neutral-800"
              @click="$emit('remove', item.id)"
            >
              Remove
            </button>
            <button
              type="button"
              :disabled="!activePlaylistId"
              class="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-40"
              @click="$emit('save-to-playlist', item)"
            >
              Save
            </button>
          </div>
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup>
defineProps({
  queue: {
    type: Array,
    default: () => [],
  },
  activePlaylistId: {
    type: Number,
    default: null,
  },
});

defineEmits(["remove", "reorder", "save-to-playlist"]);
</script>
