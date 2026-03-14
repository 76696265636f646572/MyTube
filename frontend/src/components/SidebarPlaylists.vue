<template>
  <aside class="min-h-0 h-full overflow-hidden rounded-xl border border-neutral-700 p-3 flex flex-col surface-panel">
    <h2 class="text-2xl font-bold">Playlists</h2>
    <form class="mt-3 flex gap-2" @submit.prevent="submitCreatePlaylist">
      <input
        v-model="newTitle"
        type="text"
        placeholder="New playlist"
        required
        class="h-10 min-w-0 flex-1 rounded-md border px-3 text-sm surface-input"
      />
      <UButton type="submit" color="primary" variant="solid" size="md">
        Create
      </UButton>
    </form>

    <ul
      class="mt-3 min-h-0 flex-1 space-y-2 overflow-auto pr-1"
      @click="(e) => e.target === e.currentTarget && selectPlaylist(router, null)"
    >
      <li
        v-for="playlist in playlists"
        :key="playlist.id"
        class="group flex items-start gap-2 rounded-md border p-2 cursor-pointer transition-colors playlist-card"
        :class="playlist.id === activePlaylistId ? 'bg-primary-500/20' : 'hover:bg-neutral-700/50'"
        @click="togglePlaylistSelection(playlist.id)"
      >
        <div
          class="min-w-0 flex-1 flex items-center gap-2 rounded py-1.5 -m-1"
          :class="playlist.id === activePlaylistId ? 'text-primary-400' : ''"
        >
          <img
            v-if="playlistThumbnailSrc(playlist)"
            :src="playlistThumbnailSrc(playlist)"
            alt=""
            class="h-10 w-10 shrink-0 rounded object-cover"
          />
          <div class="min-w-0 text-left">
            <span class="block truncate text-sm font-medium">{{ playlist.title }}</span>
            <span class="block text-xs text-muted">{{ playlist.kind }} · {{ playlist.entry_count }}</span>
          </div>
        </div>
        <div class="shrink-0 opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100" @click.stop>
          <UDropdownMenu :items="dropdownItemsFor(playlist)" :ui="{ separator: 'hidden' }">
            <UButton
              type="button"
              icon="i-bi-three-dots"
              color="neutral"
              variant="ghost"
              size="xs"
              aria-label="More actions"
              class="cursor-pointer"
            />
          </UDropdownMenu>
        </div>
      </li>
    </ul>

    <UModal v-model:open="editModalOpen" :ui="{ width: 'max-w-sm' }">
      <template #content>
        <form class="p-4" @submit.prevent="submitEdit">
          <h3 class="text-lg font-semibold">Edit playlist</h3>
          <input
            v-model="editTitle"
            type="text"
            class="mt-3 w-full rounded-md border px-3 py-2 text-sm surface-input"
            placeholder="Playlist name"
            @keydown.enter.prevent="submitEdit"
          />
          <textarea
            v-model="editDescription"
            class="mt-3 w-full rounded-md border px-3 py-2 text-sm surface-input resize-none"
            placeholder="Description (optional)"
            rows="3"
          />
          <div class="mt-4 flex justify-end gap-2">
            <UButton type="button" color="neutral" variant="ghost" @click="editModalOpen = false">
              Cancel
            </UButton>
            <UButton type="submit" color="primary" variant="solid">
              Save
            </UButton>
          </div>
        </form>
      </template>
    </UModal>

    <UModal v-model:open="deleteModalOpen" :ui="{ width: 'max-w-sm' }">
      <template #content>
        <div class="p-4">
          <h3 class="text-lg font-semibold">Delete playlist</h3>
          <p class="mt-2 text-sm text-muted">
            Delete "{{ playlistToDelete ? (playlistToDelete.title || 'Untitled playlist') : '' }}"?
            This cannot be undone.
          </p>
          <div class="mt-4 flex justify-end gap-2">
            <UButton type="button" color="neutral" variant="ghost" @click="deleteModalOpen = false">
              Cancel
            </UButton>
            <UButton
              type="button"
              color="error"
              variant="solid"
              @click="submitDelete"
            >
              Delete
            </UButton>
          </div>
        </div>
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
const editModalOpen = ref(false);
const editTitle = ref("");
const editDescription = ref("");
const playlistToEdit = ref(null);
const deleteModalOpen = ref(false);
const playlistToDelete = ref(null);
const router = useRouter();
const {
  playlists,
  createPlaylist,
  queuePlaylist,
  playPlaylistNow,
  updatePlaylist,
  setPlaylistPinned,
  deletePlaylist,
} = useLibraryState();
const { activePlaylistId, selectPlaylist } = useUiState();

function togglePlaylistSelection(playlistId) {
  if (activePlaylistId.value === playlistId) {
    selectPlaylist(router, null);
  } else {
    selectPlaylist(router, playlistId);
  }
}

watch(playlistToEdit, (p) => {
  editTitle.value = p ? (p.title || "") : "";
  editDescription.value = p ? (p.description || "") : "";
});

function dropdownItemsFor(playlist) {
  const items = [
    [
      { label: "Queue", icon: "i-bi-music-note-list", class: "cursor-pointer", onSelect: () => queuePlaylist(playlist.id) },
      { label: "Play now", icon: "i-bi-play-fill", class: "cursor-pointer", onSelect: () => playPlaylistNow(playlist.id) },
    ],
  ];
  let children = [];
  children.push(
    { label: "Edit", icon: "i-bi-pencil-fill", class: "cursor-pointer", onSelect: () => openEditModal(playlist) },
  );
  
  const pinned = !!playlist.pinned;
  children.push(
    {
      label: pinned ? "Unpin" : "Pin",
      icon: pinned ? "i-bi-pin" : "i-bi-pin-fill",
      class: "cursor-pointer",
      onSelect: () => setPlaylistPinned(playlist.id, !pinned),
    },  
  );
  children.push(
    {
      label: "Delete",
      icon: "i-bi-trash-fill",
      class: "cursor-pointer",
      onSelect: () => openDeleteModal(playlist),
      color: "error",
    },
  );
  items.push(children);
  return items;
}

function openDeleteModal(playlist) {
  playlistToDelete.value = playlist;
  deleteModalOpen.value = true;
}

async function submitDelete() {
  const playlist = playlistToDelete.value;
  if (!playlist) return;
  const wasSelected = activePlaylistId.value === playlist.id;
  deleteModalOpen.value = false;
  playlistToDelete.value = null;
  await deletePlaylist(playlist.id);
  if (wasSelected) {
    selectPlaylist(router, null);
  }
}

function openEditModal(playlist) {
  playlistToEdit.value = playlist;
  editModalOpen.value = true;
}

function submitEdit() {
  const title = editTitle.value.trim();
  if (!title || !playlistToEdit.value) return;
  updatePlaylist(playlistToEdit.value.id, {
    title,
    description: editDescription.value.trim(),
  });
  editModalOpen.value = false;
  playlistToEdit.value = null;
}

function submitCreatePlaylist() {
  const title = newTitle.value.trim();
  if (!title) return;
  createPlaylist(title);
  newTitle.value = "";
}

function playlistThumbnailSrc(playlist) {
  if (!playlist) return "";
  return playlist.thumbnail_url || "";
}
</script>
