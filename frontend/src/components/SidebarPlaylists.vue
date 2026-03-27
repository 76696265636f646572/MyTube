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

    <div
      class="mt-3 min-h-0 flex-1 overflow-auto pr-1"
      @click="(e) => e.target === e.currentTarget && selectPlaylist(router, null)"
    >
      <VueDraggable
        v-if="pinnedPlaylists.length"
        v-model="pinnedPlaylists"
        tag="ul"
        class="space-y-2"
        :animation="150"
        :delay="200"
        :delay-on-touch-only="true"
        ghost-class="queue-drag-ghost"
        chosen-class="queue-drag-chosen"
        @end="(evt) => onReorderEnd(evt, true)"
      >
        <PlaylistItem
          v-for="playlist in pinnedPlaylists"
          :key="playlist.id"
          :playlist="playlist"
          :active-playlist-id="activePlaylistId"
          :is-remote-playlist="isRemotePlaylist"
          :thumbnail-src="playlistThumbnailSrc(playlist)"
          :label="playlistLabel(playlist)"
          :dropdown-items="dropdownItemsFor(playlist)"
          @click="onPlaylistClick"
        />
      </VueDraggable>

      <VueDraggable
        v-if="unpinnedPlaylists.length"
        v-model="unpinnedPlaylists"
        tag="ul"
        :class="pinnedPlaylists.length ? 'mt-2 space-y-2' : 'space-y-2'"
        :animation="150"
        :delay="200"
        :delay-on-touch-only="true"
        ghost-class="queue-drag-ghost"
        chosen-class="queue-drag-chosen"
        @end="(evt) => onReorderEnd(evt, false)"
      >
        <PlaylistItem
          v-for="playlist in unpinnedPlaylists"
          :key="playlist.id"
          :playlist="playlist"
          :active-playlist-id="activePlaylistId"
          :is-remote-playlist="isRemotePlaylist"
          :thumbnail-src="playlistThumbnailSrc(playlist)"
          :label="playlistLabel(playlist)"
          :dropdown-items="dropdownItemsFor(playlist)"
          @click="onPlaylistClick"
        />
      </VueDraggable>
    </div>

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
import { VueDraggable } from "vue-draggable-plus";
import PlaylistItem from "./PlaylistItem.vue";

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
  importPlaylistUrl,
  queuePlaylist,
  playPlaylistNow,
  updatePlaylist,
  setPlaylistPinned,
  deletePlaylist,
  reorderSidebarPlaylist,
} = useLibraryState();
const { activePlaylistId, selectPlaylist } = useUiState();
const pinnedPlaylists = ref([]);
const unpinnedPlaylists = ref([]);

function isRemotePlaylist(playlist) {
  return playlist?.kind === "remote_youtube";
}

function onPlaylistClick(playlist) {
  if (isRemotePlaylist(playlist)) {
    importPlaylistUrl(playlist.source_url);
    return;
  }
  const playlistId = playlist?.id;
  if (activePlaylistId.value === playlistId) {
    selectPlaylist(router, null);
  } else {
    selectPlaylist(router, playlistId);
  }
}

function playlistLabel(playlist) {
  if (playlist?.kind === "remote_youtube") return "youtube";
  return playlist?.kind || "playlist";
}

watch(playlistToEdit, (p) => {
  editTitle.value = p ? (p.title || "") : "";
  editDescription.value = p ? (p.description || "") : "";
});

watch(
  playlists,
  (items) => {
    const next = Array.isArray(items) ? items : [];
    pinnedPlaylists.value = next.filter((playlist) => !!playlist?.pinned);
    unpinnedPlaylists.value = next.filter((playlist) => !playlist?.pinned);
  },
  { immediate: true },
);

function dropdownItemsFor(playlist) {
  if (isRemotePlaylist(playlist)) {
    return [
      [
        {
          label: "Import",
          icon: "i-bi-download",
          class: "cursor-pointer",
          onSelect: () => importPlaylistUrl(playlist.source_url),
        },
      ],
    ];
  }
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

async function onReorderEnd(evt, pinned) {
  const { oldIndex, newIndex } = evt;
  if (oldIndex === newIndex) return;
  const list = pinned ? pinnedPlaylists.value : unpinnedPlaylists.value;
  const playlist = list[newIndex];
  if (!playlist?.id) return;
  await reorderSidebarPlaylist(playlist.id, newIndex, pinned);
}

function playlistThumbnailSrc(playlist) {
  if (!playlist) return "";
  return playlist.thumbnail_url || "";
}
</script>
