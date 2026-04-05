<template>
  <li
    class="group flex items-start gap-2 rounded-md border p-2 cursor-pointer transition-colors playlist-card"
    :class="isActive ? 'bg-primary-500/20' : 'hover:bg-neutral-700/50'"
    @click="$emit('click', playlist)"
  >
    <div
      class="min-w-0 flex-1 flex items-center gap-2 rounded py-1.5 -m-1"
      :class="isActive ? 'text-primary-400' : ''"
    >
      <img
        v-if="thumbnailSrc"
        :src="thumbnailSrc"
        alt=""
        class="h-10 w-10 shrink-0 rounded object-cover"
      />
      <div class="min-w-0 text-left">
        <span class="flex items-center gap-1 text-sm font-medium">
          <span class="truncate">{{ playlist.title }}</span>
          <UIcon
            v-if="playlist.pinned"
            name="i-bi-pin-fill"
            class="size-3 shrink-0 text-muted"
            aria-hidden="true"
          />
        </span>
        <span class="block text-xs text-muted">{{ label }} · {{ playlist.entry_count }}</span>
      </div>
    </div>
    <div class="shrink-0 opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100" @click.stop>
      <UDropdownMenu
        :items="dropdownItems"
        :ui="{ separator: 'hidden' }"
        @update:open="(open) => !open && resetSearch()"
      >
        <template #playlist-filter>
          <PlaylistSelectorFilter
            v-model="playlistSearchTerm"
            placeholder="Find a playlist"
            @playlist-created="onAddToNewPlaylist"
          />
        </template>
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
          Delete "{{ playlist ? (playlist.title || "Untitled playlist") : "" }}"?
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
</template>

<script setup>
import { computed, ref } from "vue";

import PlaylistSelectorFilter from "./PlaylistSelectorFilter.vue";
import { fetchJson } from "../composables/useApi";
import { useLibraryState } from "../composables/useLibraryState";
import { usePlaylistSelector } from "../composables/usePlaylistSelector";

const props = defineProps({
  playlist: {
    type: Object,
    required: true,
  },
  activePlaylistId: {
    type: Number,
    default: null,
  },
  isRemotePlaylist: {
    type: Function,
    required: true,
  },
  thumbnailSrc: {
    type: String,
    default: "",
  },
  label: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["click", "clear-active-playlist"]);

const { playlists, importPlaylistUrl, queuePlaylist, playPlaylistNow, addEntriesToPlaylist, updatePlaylist, setPlaylistPinned, deletePlaylist } = useLibraryState();
const { playlistSearchTerm, filteredPlaylists, resetSearch } = usePlaylistSelector(() => playlists.value);
const editModalOpen = ref(false);
const editTitle = ref("");
const editDescription = ref("");
const deleteModalOpen = ref(false);

const isActive = computed(() => props.playlist.id === props.activePlaylistId && !props.isRemotePlaylist(props.playlist));
const canAddToPlaylist = computed(() => (
  !props.isRemotePlaylist(props.playlist)
  && Number(props.playlist?.entry_count || 0) > 0
));

const dropdownItems = computed(() => {
  if (props.isRemotePlaylist(props.playlist)) {
    return [
      [
        {
          label: "Import",
          icon: "i-bi-download",
          class: "cursor-pointer",
          onSelect: () => importPlaylistUrl(props.playlist.source_url),
        },
      ],
    ];
  }

  const items = [
    [
      {
        label: "Play now",
        icon: "i-bi-play-fill",
        class: "cursor-pointer",
        onSelect: () => playPlaylistNow(props.playlist.id),
      },
      {
        label: "Queue",
        icon: "i-bi-music-note-list",
        class: "cursor-pointer",
        onSelect: () => queuePlaylist(props.playlist.id),
      },
      
    ],
  ];

  if (canAddToPlaylist.value) {
    const addToPlaylistChildren = [
      { type: "label", slot: "playlist-filter" },
      ...(filteredPlaylists.value ?? [])
        .filter((p) => p.id !== props.playlist.id)
        .map((p) => ({
          label: p.title || "Untitled playlist",
          onSelect: () => addPlaylistToPlaylist(p.id),
        })),
    ];
    items.push([
      {
        label: "Add to playlist",
        icon: "i-bi-plus",
        children: [addToPlaylistChildren],
      },
    ]);
  }

  const pinned = !!props.playlist.pinned;
  items.push([
    {
      label: "Edit",
      icon: "i-bi-pencil-fill",
      class: "cursor-pointer",
      onSelect: openEditModal,
    },
    {
      label: pinned ? "Unpin" : "Pin",
      icon: pinned ? "i-bi-pin" : "i-bi-pin-fill",
      class: "cursor-pointer",
      onSelect: () => setPlaylistPinned(props.playlist.id, !pinned),
    },
    {
      label: "Delete",
      icon: "i-bi-trash-fill",
      class: "cursor-pointer",
      onSelect: openDeleteModal,
      color: "error",
    },
  ]);
  return items;
});

function openEditModal() {
  editTitle.value = props.playlist?.title || "";
  editDescription.value = props.playlist?.description || "";
  editModalOpen.value = true;
}

function openDeleteModal() {
  deleteModalOpen.value = true;
}

async function submitEdit() {
  const title = editTitle.value.trim();
  if (!title || !props.playlist?.id) return;
  await updatePlaylist(props.playlist.id, {
    title,
    description: editDescription.value.trim(),
  });
  editModalOpen.value = false;
}

async function submitDelete() {
  if (!props.playlist?.id) return;
  const wasSelected = props.playlist.id === props.activePlaylistId;
  deleteModalOpen.value = false;
  await deletePlaylist(props.playlist.id);
  if (wasSelected) {
    emit("clear-active-playlist");
  }
}

async function addPlaylistToPlaylist(targetPlaylistId) {
  if (!props.playlist?.id || !targetPlaylistId || props.playlist.id === targetPlaylistId) return;
  const entries = await fetchJson(`/api/playlists/${encodeURIComponent(props.playlist.id)}/entries`);
  if (!Array.isArray(entries) || entries.length === 0) return;
  await addEntriesToPlaylist(targetPlaylistId, entries);
  resetSearch();
}

function onAddToNewPlaylist(created) {
  if (created?.id != null) addPlaylistToPlaylist(created.id);
}
</script>
