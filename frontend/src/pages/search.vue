<template>
  <section class="min-h-0 h-full rounded-xl border border-neutral-700 bg-neutral-900 p-6 overflow-auto">
    <h2 class="text-2xl font-bold">YouTube Search</h2>
    <p class="mt-1 text-sm text-neutral-400">
      <template v-if="query">
        Showing results for "{{ query }}"
      </template>
      <template v-else>
        Enter a search in the top bar and press Enter.
      </template>
    </p>

    <div v-if="loading" class="mt-4 text-sm text-neutral-300">Searching...</div>
    <div v-else-if="errorMessage" class="mt-4 text-sm text-red-300">{{ errorMessage }}</div>
    <div v-else-if="query && !results.length" class="mt-4 text-sm text-neutral-300">No results found.</div>

    <ul v-if="results.length" class="mt-4 space-y-2">
      <li v-for="item in results" :key="item.id || item.source_url">
        <Song
          :item="item"
          mode="search"
          :playlists="playlists"
        />
      </li>
    </ul>
  </section>
</template>

<script setup>
import { ref, watch } from "vue";
import { useRoute } from "vue-router";

import Song from "../components/Song.vue";
import { fetchJson } from "../composables/useApi";
import { useLibraryState } from "../composables/useLibraryState";

const { playlists } = useLibraryState();

const route = useRoute();
const query = ref("");
const results = ref([]);
const loading = ref(false);
const errorMessage = ref("");

let requestId = 0;

function normalizeQuery(value) {
  if (Array.isArray(value)) return (value[0] || "").trim();
  return typeof value === "string" ? value.trim() : "";
}

async function searchYoutube(rawQuery) {
  const normalized = normalizeQuery(rawQuery);
  query.value = normalized;

  if (!normalized) {
    results.value = [];
    errorMessage.value = "";
    loading.value = false;
    return;
  }

  const activeRequestId = ++requestId;
  loading.value = true;
  errorMessage.value = "";

  try {
    const payload = await fetchJson(`/api/search/youtube?q=${encodeURIComponent(normalized)}&limit=10`);
    if (activeRequestId !== requestId) return;
    results.value = Array.isArray(payload?.results) ? payload.results : [];
  } catch (error) {
    if (activeRequestId !== requestId) return;
    results.value = [];
    errorMessage.value = error instanceof Error ? error.message : "Search failed";
  } finally {
    if (activeRequestId === requestId) {
      loading.value = false;
    }
  }
}

watch(
  () => route.query.q,
  (value) => {
    searchYoutube(value);
  },
  { immediate: true },
);
</script>
