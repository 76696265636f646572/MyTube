<template>
  <section class="min-h-0 h-full flex flex-col rounded-xl border border-neutral-700 p-6 overflow-hidden surface-panel">
    <div v-if="loading" class="text-sm text-muted">Loading playlist...</div>
    <div v-else-if="notFound" class="text-sm text-red-300">Playlist not found.</div>
    <div v-else-if="errorMessage" class="text-sm text-red-300">{{ errorMessage }}</div>

    <template v-else>
      <h2 class="text-2xl font-bold">{{ playlist.title || "Untitled playlist" }}</h2>
      <p class="mt-1 text-sm text-muted">
        {{ playlist.channel || "Unknown channel" }} · {{ playlist.entry_count || 0 }} items
      </p>

      <div v-if="!entries.length" class="mt-4 text-sm text-muted">This playlist has no entries yet.</div>

      <UScrollArea
        v-else
        :ui="{ viewport: 'mt-4 gap-2' }"
        class="mt-4 min-h-0 flex-1"
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
</template>

<script setup>
import { ref, watch } from "vue";
import { useRoute } from "vue-router";

import { VueDraggable } from "vue-draggable-plus";

import Song from "../../components/Song.vue";
import { fetchJson } from "../../composables/useApi";
import { useLibraryState } from "../../composables/useLibraryState";

const { playlists, reorderPlaylistEntry } = useLibraryState();

const route = useRoute();
const playlist = ref({});
const entries = ref([]);
const loading = ref(false);
const notFound = ref(false);
const errorMessage = ref("");

let requestId = 0;

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
