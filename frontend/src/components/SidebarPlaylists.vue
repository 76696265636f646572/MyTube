<template>
  <aside class="min-h-0 overflow-hidden rounded-xl border border-neutral-700 bg-neutral-900 p-3">
    <h2 class="text-2xl font-bold">Playlists</h2>
    <form class="mt-3 flex gap-2" @submit.prevent="submitCreatePlaylist">
      <input
        v-model="newTitle"
        type="text"
        placeholder="New playlist"
        required
        class="h-10 min-w-0 flex-1 rounded-md border border-neutral-700 bg-neutral-800 px-3 text-sm"
      />
      <button type="submit" class="h-10 rounded-md border border-neutral-700 bg-neutral-800 px-3 text-sm hover:bg-neutral-700">
        Create
      </button>
    </form>

    <ul class="mt-3 max-h-[60vh] space-y-2 overflow-auto pr-1">
      <li
        v-for="playlist in playlists"
        :key="playlist.id"
        class="flex items-start gap-2 rounded-md border border-neutral-700 p-2"
        :class="playlist.id === activePlaylistId ? 'bg-neutral-800' : ''"
      >
        <button type="button" class="min-w-0 flex-1 text-left" @click="$emit('select-playlist', playlist.id)">
          <span class="block truncate text-sm font-medium">{{ playlist.title }}</span>
          <span class="text-xs text-neutral-400">{{ playlist.kind }} · {{ playlist.entry_count }}</span>
        </button>
        <button
          type="button"
          class="rounded-md border border-neutral-700 bg-neutral-800 px-2 py-1 text-xs hover:bg-neutral-700"
          @click="$emit('queue-playlist', playlist.id)"
        >
          Queue
        </button>
      </li>
    </ul>
  </aside>
</template>

<script setup>
import { ref } from "vue";

defineProps({
  playlists: {
    type: Array,
    default: () => [],
  },
  activePlaylistId: {
    type: Number,
    default: null,
  },
});

const emit = defineEmits(["create-playlist", "select-playlist", "queue-playlist"]);
const newTitle = ref("");

function submitCreatePlaylist() {
  const title = newTitle.value.trim();
  if (!title) return;
  emit("create-playlist", title);
  newTitle.value = "";
}
</script>
