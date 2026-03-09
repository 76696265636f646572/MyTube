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
      <li
        v-for="item in results"
        :key="item.id || item.source_url"
        class="flex items-center gap-3 rounded-md border border-neutral-700 px-3 py-2"
      >
        <img
          v-if="thumbnailUrl(item)"
          :src="thumbnailUrl(item)"
          :alt="item.title || 'Result thumbnail'"
          class="h-14 w-24 rounded object-cover bg-neutral-800"
          loading="lazy"
          referrerpolicy="no-referrer"
        />
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm">{{ item.title || item.source_url }}</p>
          <p v-if="item.channel" class="truncate text-xs text-neutral-500">
            {{ item.channel }}
          </p>
          <p v-if="item.duration_seconds != null" class="truncate text-xs text-neutral-400">
            {{ formatDuration(item.duration_seconds) }}
          </p>
        </div>
        <div class="flex gap-2">
          <UButton type="button" color="primary" variant="soft" size="xs" @click="emitAdd(item.source_url)">
            Add
          </UButton>
          <UButton type="button" color="neutral" variant="outline" size="xs" @click="emitPlay(item.source_url)">
            Play
          </UButton>
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup>
import { ref, watch } from "vue";
import { useRoute } from "vue-router";

import { formatDuration } from "../composables/useDuration";
import { fetchJson } from "../composables/useApi";

const props = defineProps({
  onAddUrl: {
    type: Function,
    default: null,
  },
  onPlayUrl: {
    type: Function,
    default: null,
  },
});

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

function thumbnailUrl(item) {
  if (item?.thumbnail_url) return item.thumbnail_url;
  if (item?.id) return `https://i.ytimg.com/vi/${item.id}/hqdefault.jpg`;
  return "";
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
    const payload = await fetchJson(`/search/youtube?q=${encodeURIComponent(normalized)}&limit=10`);
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

function emitAdd(url) {
  if (props.onAddUrl) props.onAddUrl(url);
}

function emitPlay(url) {
  if (props.onPlayUrl) props.onPlayUrl(url);
}

watch(
  () => route.query.q,
  (value) => {
    searchYoutube(value);
  },
  { immediate: true },
);
</script>
