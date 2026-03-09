<template>
  <aside class="min-h-0 h-full overflow-hidden rounded-xl border border-neutral-700 bg-neutral-900 p-3 flex flex-col">
    <h2 class="text-2xl font-bold">Playlists</h2>
    <form class="mt-3 flex gap-2" @submit.prevent="submitCreatePlaylist">
      <input
        v-model="newTitle"
        type="text"
        placeholder="New playlist"
        required
        class="h-10 min-w-0 flex-1 rounded-md border border-neutral-700 bg-neutral-800 px-3 text-sm"
      />
      <UButton type="submit" color="primary" variant="solid" size="md">
        Create
      </UButton>
    </form>

    <ul class="mt-3 min-h-0 flex-1 space-y-2 overflow-auto pr-1">
      <li
        v-for="playlist in playlists"
        :key="playlist.id"
        class="flex items-start gap-2 rounded-md border border-neutral-700 p-2"
        :class="playlist.id === activePlaylistId ? 'bg-neutral-800' : ''"
      >
        <UButton
          type="button"
          :color="playlist.id === activePlaylistId ? 'primary' : 'neutral'"
          :variant="playlist.id === activePlaylistId ? 'soft' : 'ghost'"
          size="sm"
          class="min-w-0 flex-1 justify-start"
          @click="selectPlaylist(router, playlist.id)"
        >
          <div class="min-w-0 text-left">
            <span class="block truncate text-sm font-medium">{{ playlist.title }}</span>
            <span class="block text-xs text-neutral-400">{{ playlist.kind }} · {{ playlist.entry_count }}</span>
          </div>
        </UButton>
        <UButton type="button" color="neutral" variant="outline" size="xs" @click="queuePlaylist(playlist.id)">
          Queue
        </UButton>
      </li>
    </ul>
  </aside>
</template>

<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";

import { useLibraryState } from "../composables/useLibraryState";
import { useUiState } from "../composables/useUiState";

const newTitle = ref("");
const router = useRouter();
const { playlists, createPlaylist, queuePlaylist } = useLibraryState();
const { activePlaylistId, selectPlaylist } = useUiState();

function submitCreatePlaylist() {
  const title = newTitle.value.trim();
  if (!title) return;
  createPlaylist(title);
  newTitle.value = "";
}
</script>
