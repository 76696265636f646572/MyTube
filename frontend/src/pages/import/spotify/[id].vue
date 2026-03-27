<template>
  <section class="min-h-0 h-full rounded-xl border border-neutral-700 p-4 surface-panel">
    <header class="mb-4">
      <h2 class="text-2xl font-bold">Spotify Import Review</h2>
      <p class="mt-1 text-sm text-muted">
        <template v-if="playlistTitle">{{ playlistTitle }}</template>
        <template v-else>Imported Spotify playlist</template>
      </p>
    </header>

    <div v-if="loading" class="text-sm text-muted">Loading imported tracks...</div>
    <div v-else-if="errorMessage" class="text-sm text-red-300">{{ errorMessage }}</div>
    <div v-else class="grid h-[calc(100%-4rem)] grid-cols-1 gap-3 xl:grid-cols-[280px_minmax(0,1fr)]">
      <aside class="min-h-0 overflow-auto rounded-md border border-neutral-700 p-2">
        <ul class="space-y-2">
          <li v-for="entry in entries" :key="entry.id">
            <button
              type="button"
              class="w-full rounded-md border px-3 py-2 text-left transition"
              :class="entryButtonClass(entry)"
              @click="selectedEntryId = entry.id"
            >
              <p class="truncate text-sm font-medium">{{ entry.title || entry.source_url }}</p>
              <p class="truncate text-xs text-muted">{{ entry.channel || "Unknown artist" }}</p>
              <p class="mt-1 text-xs">{{ statusLabel(entry) }}</p>
            </button>
          </li>
        </ul>
      </aside>

      <div class="min-h-0 overflow-auto rounded-md border border-neutral-700 p-3">
        <template v-if="activeEntry">
          <div class="mb-3 flex items-center justify-between gap-3">
            <div>
              <p class="text-base font-semibold">{{ activeEntry.title || activeEntry.source_url }}</p>
              <p class="text-xs text-muted">{{ activeEntry.channel || "Unknown artist" }}</p>
            </div>
            <UBadge :label="statusLabel(activeEntry)" color="neutral" variant="soft" />
          </div>

          <p v-if="activeEntry.searchQuery" class="mb-2 text-xs text-muted">
            Search: "{{ activeEntry.searchQuery }}"
          </p>

          <div v-if="activeEntry.searching" class="text-sm text-muted">Searching providers...</div>
          <div v-else-if="activeEntry.error" class="text-sm text-red-300">{{ activeEntry.error }}</div>
          <div v-else-if="!activeEntry.results.length" class="text-sm text-muted">
            No provider matches found yet.
          </div>

          <ul v-else class="space-y-2">
            <li v-for="(result, idx) in activeEntry.results" :key="resultKey(result, idx)">
              <button
                type="button"
                class="w-full rounded-md border px-3 py-2 text-left transition"
                :class="resultButtonClass(activeEntry, result)"
                @click="selectResult(activeEntry, result)"
              >
                <p class="truncate text-sm font-medium">{{ result.title || result.source_url }}</p>
                <p class="truncate text-xs text-muted">{{ result.channel || "Unknown channel" }}</p>
                <p class="truncate text-xs text-muted">
                  {{ providerLabel(result.provider) }}
                </p>
              </button>
            </li>
          </ul>
        </template>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";

import { fetchSpotifyReview, searchSpotifyEntry, selectSpotifyEntryResult } from "../../../composables/useSpotifyImport";
import { useNotifications } from "../../../composables/useNotifications";

const route = useRoute();
const { notifyError } = useNotifications();

const loading = ref(false);
const errorMessage = ref("");
const playlistTitle = ref("");
const playlistId = ref("");
const entries = ref([]);
const selectedEntryId = ref(null);
const searching = ref(false);
let loadRequestId = 0;
let searchRunId = 0;

const activeEntry = computed(
  () => entries.value.find((entry) => entry.id === selectedEntryId.value) || entries.value[0] || null,
);

function providerLabel(providerId) {
  if (!providerId) return "Unknown";
  return providerId
    .split(/[\s_-]+/g)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

function resultKey(result, idx) {
  return `${result?.provider || "unknown"}:${result?.provider_item_id || result?.source_url || idx}`;
}

function sameResult(left, right) {
  if (!left || !right) return false;
  return (
    left.source_url === right.source_url
    && left.normalized_url === right.normalized_url
    && left.provider === right.provider
    && (left.provider_item_id || null) === (right.provider_item_id || null)
  );
}

function statusLabel(entry) {
  if (entry.searching) return "Searching";
  if (entry.error) return "Search failed";
  if (entry.results.length === 0 && entry.searched) return "No match found";
  if (entry.selectedResult) return "Matched";
  return "Pending";
}

function entryButtonClass(entry) {
  if (entry.id === selectedEntryId.value) return "border-primary-500 bg-primary-900/20";
  if (entry.selectedResult) return "border-emerald-500/50";
  if (entry.searched && !entry.results.length) return "border-amber-500/50";
  return "border-neutral-700";
}

function resultButtonClass(entry, result) {
  if (sameResult(entry.selectedResult, result)) return "border-primary-500 bg-primary-900/20";
  return "border-neutral-700";
}

async function selectResult(entry, result) {
  if (!entry || !result) return;
  try {
    await selectSpotifyEntryResult(playlistId.value, entry.id, result);
    entry.selectedResult = result;
  } catch (error) {
    notifyError("Could not save selected match", error);
  }
}

async function runSequentialSearch(runId) {
  if (searching.value) return;
  searching.value = true;
  for (const entry of entries.value) {
    if (runId !== searchRunId) break;
    if (entry.searched && entry.results.length > 0) continue;
    entry.searching = true;
    entry.error = "";
    try {
      const payload = await searchSpotifyEntry(playlistId.value, entry.id, 12);
      if (runId !== searchRunId) break;
      entry.searchQuery = payload?.query || "";
      entry.results = Array.isArray(payload?.results) ? payload.results : [];
      entry.searched = true;
      const first = payload?.selected || entry.results[0] || null;
      if (first) {
        await selectSpotifyEntryResult(playlistId.value, entry.id, first);
        if (runId !== searchRunId) break;
        entry.selectedResult = first;
      }
    } catch (error) {
      if (runId !== searchRunId) break;
      entry.error = error instanceof Error ? error.message : "Search failed";
      entry.searched = true;
    } finally {
      entry.searching = false;
    }
  }
  if (runId === searchRunId) {
    searching.value = false;
  }
}

async function loadReview(rawId) {
  const id = Array.isArray(rawId) ? rawId[0] : rawId;
  if (!id) {
    errorMessage.value = "Missing playlist id";
    return;
  }
  const currentLoadId = ++loadRequestId;
  searchRunId += 1;
  searching.value = false;
  loading.value = true;
  errorMessage.value = "";
  entries.value = [];
  selectedEntryId.value = null;
  playlistId.value = id;
  try {
    const payload = await fetchSpotifyReview(id);
    if (currentLoadId !== loadRequestId) return;
    playlistTitle.value = payload?.playlist?.title || "Spotify playlist";
    const importedEntries = Array.isArray(payload?.entries) ? payload.entries : [];
    entries.value = importedEntries.map((entry) => ({
      ...entry,
      searched: false,
      searching: false,
      results: [],
      selectedResult: null,
      searchQuery: "",
      error: "",
    }));
    selectedEntryId.value = entries.value[0]?.id ?? null;
    const currentRunId = ++searchRunId;
    void runSequentialSearch(currentRunId);
  } catch (error) {
    if (currentLoadId !== loadRequestId) return;
    errorMessage.value = error instanceof Error ? error.message : "Could not load import review";
  } finally {
    if (currentLoadId === loadRequestId) {
      loading.value = false;
    }
  }
}

watch(
  () => route.params.id,
  (value) => {
    loadReview(value);
  },
  { immediate: true },
);
</script>
