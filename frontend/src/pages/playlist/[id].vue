<template>
  <section class="min-h-0 h-full rounded-xl border border-neutral-700 bg-neutral-900 p-6 overflow-auto">
    <div v-if="loading" class="text-sm text-neutral-300">Loading playlist...</div>
    <div v-else-if="notFound" class="text-sm text-red-300">Playlist not found.</div>
    <div v-else-if="errorMessage" class="text-sm text-red-300">{{ errorMessage }}</div>

    <template v-else>
      <h2 class="text-2xl font-bold">{{ playlist.title || "Untitled playlist" }}</h2>
      <p class="mt-1 text-sm text-neutral-400">
        {{ playlist.channel || "Unknown channel" }} · {{ playlist.entry_count || 0 }} items
      </p>

      <div v-if="!entries.length" class="mt-4 text-sm text-neutral-300">This playlist has no entries yet.</div>

      <ul v-else class="mt-4 space-y-2">
        <li v-for="entry in entries" :key="entry.id">
          <Song
            :item="entry"
            mode="search"
            :playlists="playlists"
          />
        </li>
      </ul>
    </template>
  </section>
</template>

<script setup>
import { ref, watch } from "vue";
import { useRoute } from "vue-router";

import Song from "../../components/Song.vue";
import { fetchJson } from "../../composables/useApi";
import { useLibraryState } from "../../composables/useLibraryState";

const { playlists } = useLibraryState();

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

watch(
  () => route.params.id,
  () => {
    loadPlaylist();
  },
  { immediate: true },
);
</script>
