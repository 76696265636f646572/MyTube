<template>
  <section class="min-h-0 h-full flex flex-col rounded-xl border border-neutral-700 p-6 overflow-hidden surface-panel">
    <div v-if="loading" class="text-sm text-muted">Loading playlist...</div>
    <div v-else-if="notFound" class="text-sm text-red-300">Playlist not found.</div>
    <div v-else-if="errorMessage" class="text-sm text-red-300">{{ errorMessage }}</div>

    <template v-else>
      <!-- Hero section -->
      <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:gap-6">
        <div class="shrink-0">
          <img
            v-if="firstTrackThumbnail"
            :src="firstTrackThumbnail"
            :alt="playlist.title || 'Playlist'"
            class="h-40 w-40 rounded-lg object-cover sm:h-48 sm:w-48 surface-elevated shadow-lg"
          />
          <div
            v-else
            class="flex h-40 w-40 items-center justify-center rounded-lg bg-neutral-700/50 sm:h-48 sm:w-48 surface-elevated"
          >
            <UIcon name="i-bi-music-note-beamed" class="size-16 text-muted" />
          </div>
        </div>
        <div class="min-w-0 flex-1">
          <h2 class="text-2xl font-bold tracking-tight sm:text-3xl">{{ playlist.title || "Untitled playlist" }}</h2>
          <p v-if="playlist.description" class="mt-1 text-sm text-muted">{{ playlist.description }}</p>
          <p class="mt-2 text-sm text-muted">
            {{ songCount }} {{ songCount === 1 ? "song" : "songs" }}, {{ formattedTotalDuration }}
          </p>
        </div>
      </div>

      <!-- Action row -->
      <div class="mt-4 flex items-center gap-2">
        <template v-if="isRemotePlaylistView">
          <UButton
            type="button"
            color="primary"
            variant="solid"
            size="sm"
            icon="i-bi-download"
            @click="importRemotePlaylist"
          >
            Import playlist
          </UButton>
        </template>
        <template v-else>
        <UButton
          type="button"
          color="primary"
          variant="solid"
          size="lg"
          icon="i-bi-play-fill"
          :ui="{ rounded: 'rounded-full' }"
          :disabled="!entries.length"
          aria-label="Play playlist"
          @click="playPlaylistNow(playlist.id)"
        />
        <UDropdownMenu :items="dropdownItems" :ui="{ separator: 'hidden' }" @update:open="(open) => !open && playlistSelector.resetSearch()">
          <template #playlist-filter>
            <PlaylistSelectorFilter v-model="playlistSelector.playlistSearchTerm" placeholder="Find a playlist" />
          </template>
          <UButton
            type="button"
            icon="i-bi-three-dots"
            color="neutral"
            variant="ghost"
            size="lg"
            aria-label="More actions"
            class="cursor-pointer"
          />
        </UDropdownMenu>
        </template>
      </div>

      <div v-if="isRemotePlaylistView" class="mt-6 text-sm text-muted">
        This playlist is from your YouTube account and is not in the local library yet.
      </div>
      <div v-else-if="!entries.length" class="mt-6 text-sm text-muted">This playlist has no entries yet.</div>

      <UScrollArea
        v-else-if="!isRemotePlaylistView"
        :ui="{ viewport: 'mt-6 gap-2' }"
        class="min-h-0 flex-1"
      >
        <VueDraggable
          v-model="entries"
          tag="ul"
          class="space-y-2"
          :animation="150"
          :delay="200"
          :delay-on-touch-only="true"
          ghost-class="queue-drag-ghost"
          chosen-class="queue-drag-chosen"
          @end="onReorderEnd"
        >
          <li v-for="entry in entries" :key="entry.id">
            <Song
              :item="entry"
              mode="search"
              :playlists="playlists"
              :playlist-id="playlist.id"
              :entry-id="entry.id"
              @deleted="loadPlaylist()"
            />
          </li>
        </VueDraggable>
      </UScrollArea>
    </template>
  </section>

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
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { VueDraggable } from "vue-draggable-plus";

import PlaylistSelectorFilter from "../../components/PlaylistSelectorFilter.vue";
import Song from "../../components/Song.vue";
import { fetchJson } from "../../composables/useApi";
import { formatTotalDuration } from "../../composables/useDuration";
import { useLibraryState } from "../../composables/useLibraryState";
import { usePlaylistSelector } from "../../composables/usePlaylistSelector";

const {
  playlists,
  importPlaylistUrl,
  reorderPlaylistEntry,
  playPlaylistNow,
  queuePlaylist,
  addEntriesToPlaylist,
  updatePlaylist,
  setPlaylistPinned,
  deletePlaylist,
} = useLibraryState();
const playlistSelector = usePlaylistSelector(() => playlists.value);
const route = useRoute();
const router = useRouter();
const playlist = ref({});
const entries = ref([]);
const loading = ref(false);
const notFound = ref(false);
const errorMessage = ref("");
const editModalOpen = ref(false);
const editTitle = ref("");
const editDescription = ref("");
const playlistToEdit = ref(null);
const deleteModalOpen = ref(false);
const playlistToDelete = ref(null);

const firstTrackThumbnail = computed(() => {
  const first = entries.value[0];
  if (first?.thumbnail_url) return first.thumbnail_url;
  if (first?.provider === "youtube" && first?.provider_item_id) {
    return `https://i.ytimg.com/vi/${first.provider_item_id}/hqdefault.jpg`;
  }
  return playlist.value?.thumbnail_url || "";
});

const songCount = computed(() => entries.value.length || playlist.value?.entry_count || 0);
const isRemotePlaylistView = computed(() => playlist.value?.kind === "remote_youtube");

const totalDurationSeconds = computed(() =>
  entries.value.reduce((sum, e) => sum + (e.duration_seconds || 0), 0)
);

const formattedTotalDuration = computed(() => formatTotalDuration(totalDurationSeconds.value));

const dropdownItems = computed(() => {
  const pl = playlist.value;
  if (!pl?.id) return [];
  const items = [
      { label: "Queue", icon: "i-bi-music-note-list", class: "cursor-pointer", onSelect: () => queuePlaylist(pl.id) },
      { label: "Play now", icon: "i-bi-play-fill", class: "cursor-pointer", onSelect: () => playPlaylistNow(pl.id) },
  ];
  const otherPlaylists = (playlistSelector.filteredPlaylists.value ?? []).filter((p) => p.id !== pl.id);
  if (entries.value.length > 0 && playlists.value?.length > 0) {
    const addToPlaylistChildren = [
      { type: "label", slot: "playlist-filter" },
      ...otherPlaylists.map((p) => ({
        label: p.title || "Untitled playlist",
        onSelect: () => addAllEntriesToPlaylist(p.id, entries.value),
      })),
    ];
    items.push(
      {
        label: "Add to playlist",
        icon: "i-bi-plus",
        children: [addToPlaylistChildren],
      },
    );
  }
  const pinned = !!pl.pinned;
  items.push(
    { label: "Edit", icon: "i-bi-pencil-fill", class: "cursor-pointer", onSelect: () => openEditModal(pl) },
    {
      label: pinned ? "Unpin" : "Pin",
      icon: pinned ? "i-bi-pin" : "i-bi-pin-fill",
      class: "cursor-pointer",
      onSelect: () => setPlaylistPinned(pl.id, !pinned),
    },
    {
      label: "Delete",
      icon: "i-bi-trash-fill",
      class: "cursor-pointer",
      onSelect: () => openDeleteModal(pl),
      color: "error",
    },
  );
  return items;
});

async function addAllEntriesToPlaylist(targetPlaylistId, entriesToAdd) {
  const list = entriesToAdd ?? entries.value;
  await addEntriesToPlaylist(targetPlaylistId, list, { onComplete: loadPlaylist });
  playlistSelector.resetSearch();
}

function importRemotePlaylist() {
  if (!playlist.value?.source_url) return;
  importPlaylistUrl(playlist.value.source_url);
}

function openEditModal(pl) {
  playlistToEdit.value = pl;
  editModalOpen.value = true;
}

function openDeleteModal(pl) {
  playlistToDelete.value = pl;
  deleteModalOpen.value = true;
}

async function submitEdit() {
  const title = editTitle.value.trim();
  if (!title || !playlistToEdit.value) return;
  await updatePlaylist(playlistToEdit.value.id, {
    title,
    description: editDescription.value.trim(),
  });
  editModalOpen.value = false;
  playlistToEdit.value = null;
  loadPlaylist();
}

async function submitDelete() {
  const pl = playlistToDelete.value;
  if (!pl) return;
  deleteModalOpen.value = false;
  playlistToDelete.value = null;
  await deletePlaylist(pl.id);
  router.push("/playlists");
}

let requestId = 0;

watch(playlistToEdit, (p) => {
  editTitle.value = p ? (p.title || "") : "";
  editDescription.value = p ? (p.description || "") : "";
});

function playlistIdFromRoute() {
  const value = route.params.id;
  if (Array.isArray(value)) return value[0] || "";
  return typeof value === "string" ? value : "";
}

async function loadPlaylist() {
  const playlistId = playlistIdFromRoute().trim();
  const activeRequestId = ++requestId;

  if (!playlistId) {
    playlist.value = {};
    entries.value = [];
    loading.value = false;
    notFound.value = true;
    errorMessage.value = "";
    return;
  }

  loading.value = true;
  notFound.value = false;
  errorMessage.value = "";

  if (playlistId.startsWith("remote:youtube:")) {
    const match = (playlists.value || []).find((item) => item?.id === playlistId);
    if (activeRequestId !== requestId) return;
    if (!match) {
      playlist.value = {};
      entries.value = [];
      loading.value = false;
      notFound.value = true;
      return;
    }
    playlist.value = match;
    entries.value = [];
    loading.value = false;
    return;
  }

  try {
    const playlistPayload = await fetchJson(`/api/playlists/${encodeURIComponent(playlistId)}`);
    if (activeRequestId !== requestId) return;
    playlist.value = playlistPayload || {};
  } catch (error) {
    if (activeRequestId !== requestId) return;
    const message = error instanceof Error ? error.message : String(error || "Request failed");
    notFound.value = message.toLowerCase().includes("404");
    errorMessage.value = notFound.value ? "" : message;
    playlist.value = {};
    entries.value = [];
    loading.value = false;
    return;
  }

  try {
    const entriesPayload = await fetchJson(`/api/playlists/${encodeURIComponent(playlistId)}/entries`);
    if (activeRequestId !== requestId) return;
    entries.value = Array.isArray(entriesPayload) ? entriesPayload : [];
  } catch (error) {
    if (activeRequestId !== requestId) return;
    entries.value = [];
    errorMessage.value = error instanceof Error ? error.message : "Could not load playlist entries";
  } finally {
    if (activeRequestId === requestId) {
      loading.value = false;
    }
  }
}

function onReorderEnd(evt) {
  const { oldIndex, newIndex } = evt;
  if (oldIndex === newIndex) return;
  const entry = entries.value[newIndex];
  if (!entry?.id) return;
  reorderPlaylistEntry(entry.id, newIndex);
}

watch(
  () => route.params.id,
  () => {
    loadPlaylist();
  },
  { immediate: true },
);
</script>
