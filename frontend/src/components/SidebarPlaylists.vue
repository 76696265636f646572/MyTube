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
        class="group flex items-start gap-2 rounded-md border border-neutral-700 p-2"
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
        <div class="shrink-0 opacity-0 transition-opacity group-hover:opacity-100" @click.stop>
          <UDropdownMenu :items="dropdownItemsFor(playlist)">
            <UButton
              type="button"
              icon="i-lucide-more-horizontal"
              color="neutral"
              variant="ghost"
              size="xs"
              aria-label="More actions"
            />
          </UDropdownMenu>
        </div>
      </li>
    </ul>

    <UModal v-model:open="renameModalOpen" :ui="{ width: 'max-w-sm' }">
      <template #content>
        <form class="p-4" @submit.prevent="submitRename">
          <h3 class="text-lg font-semibold">Rename playlist</h3>
          <input
            v-model="renameTitle"
            type="text"
            class="mt-3 w-full rounded-md border border-neutral-700 bg-neutral-800 px-3 py-2 text-sm"
            placeholder="Playlist name"
            @keydown.enter.prevent="submitRename"
          />
          <div class="mt-4 flex justify-end gap-2">
            <UButton type="button" color="neutral" variant="ghost" @click="renameModalOpen = false">
              Cancel
            </UButton>
            <UButton type="submit" color="primary" variant="solid">
              Save
            </UButton>
          </div>
        </form>
      </template>
    </UModal>
  </aside>
</template>

<script setup>
import { ref, watch } from "vue";
import { useRouter } from "vue-router";

import { useLibraryState } from "../composables/useLibraryState";
import { useUiState } from "../composables/useUiState";

const newTitle = ref("");
const renameModalOpen = ref(false);
const renameTitle = ref("");
const playlistToRename = ref(null);
const router = useRouter();
const {
  playlists,
  createPlaylist,
  queuePlaylist,
  playPlaylistNow,
  renamePlaylist,
  setPlaylistPinned,
} = useLibraryState();
const { activePlaylistId, selectPlaylist } = useUiState();

watch(playlistToRename, (p) => {
  renameTitle.value = p ? (p.title || "") : "";
});

function dropdownItemsFor(playlist) {
  const items = [
    [
      { label: "Queue", icon: "i-lucide-list-music", onSelect: () => queuePlaylist(playlist.id) },
    ],
    [
      { label: "Play now", icon: "i-lucide-play", onSelect: () => playPlaylistNow(playlist.id) },
    ],
  ];
  if (playlist.kind === "custom") {
    items.push([
      { label: "Rename", icon: "i-lucide-pencil", onSelect: () => openRenameModal(playlist) },
    ]);
  }
  const pinned = !!playlist.pinned;
  items.push([
    {
      label: pinned ? "Unpin" : "Pin",
      icon: pinned ? "i-lucide-pin-off" : "i-lucide-pin",
      onSelect: () => setPlaylistPinned(playlist.id, !pinned),
    },
  ]);
  return items;
}

function openRenameModal(playlist) {
  playlistToRename.value = playlist;
  renameModalOpen.value = true;
}

function submitRename() {
  const title = renameTitle.value.trim();
  if (!title || !playlistToRename.value) return;
  renamePlaylist(playlistToRename.value.id, title);
  renameModalOpen.value = false;
  playlistToRename.value = null;
}

function submitCreatePlaylist() {
  const title = newTitle.value.trim();
  if (!title) return;
  createPlaylist(title);
  newTitle.value = "";
}
</script>
