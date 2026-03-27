<template>
  <section class="min-h-0 h-full flex flex-col rounded-xl border border-neutral-700 surface-panel overflow-hidden">
    <div class="shrink-0 border-b border-neutral-700 px-4 py-3 flex flex-wrap items-center justify-between gap-2">
      <div class="min-w-0">
        <h2 class="text-lg font-semibold truncate">Spotify import</h2>
        <p v-if="progressLabel" class="text-xs text-muted truncate">{{ progressLabel }}</p>
      </div>
      <div class="flex items-center gap-2">
        <UButton
          v-if="playlistId"
          type="button"
          color="neutral"
          variant="ghost"
          size="sm"
          @click="goToPlaylist"
        >
          Open playlist
        </UButton>
      </div>
    </div>

    <div v-if="loadError" class="p-4 text-sm text-red-300">{{ loadError }}</div>

    <div v-else class="min-h-0 flex-1 flex flex-col md:flex-row overflow-hidden">
      <UScrollArea class="md:w-72 shrink-0 border-b md:border-b-0 md:border-r border-neutral-700 min-h-[160px] md:min-h-0 max-h-[40vh] md:max-h-none">
        <ul class="p-2 space-y-1">
          <li v-if="items.length === 0">c
            <p class="text-sm text-muted">Loading tracks...</p>
          </li>
          <li v-for="item in items" :key="item.id">
            <button
              type="button"
              class="w-full text-left rounded-md border px-2 py-2 text-sm transition-colors surface-panel"
              :class="item.id === activeItemId ? 'border-primary-500 bg-primary-500/10' : 'border-transparent hover:border-neutral-600'"
              @click="activeItemId = item.id"
            >
              <p class="truncate font-medium">{{ item.title || "Untitled" }}</p>
              <p v-if="item.channel" class="truncate text-xs text-muted">{{ item.channel }}</p>
              <UBadge
                class="mt-1"
                size="xs"
                :color="statusBadgeColor(item.status)"
                variant="soft"
                :label="statusLabel(item.status)"
              />
            </button>
          </li>
        </ul>
      </UScrollArea>

      <div class="min-h-0 flex-1 flex flex-col overflow-hidden p-4">
        <div v-if="!activeItem" class="text-sm text-muted">Select a track.</div>
        <template v-else>
          <div class="shrink-0 mb-3">
            <p class="text-sm font-medium">{{ activeItem.title }}</p>
            <p v-if="activeItem.channel" class="text-xs text-muted">{{ activeItem.channel }}</p>
          </div>
          <UScrollArea class="min-h-0 flex-1">
            <div class="space-y-6 pr-2">
              <div v-for="prov in providerOrder" :key="prov">
                <h3 class="text-xs font-semibold uppercase tracking-wide text-muted mb-2">
                  {{ providerLabel(prov) }}
                </h3>
                <ul v-if="(activeItem.results_by_provider?.[prov] || []).length" class="space-y-2">
                  <li v-for="(hit, idx) in activeItem.results_by_provider[prov]" :key="hit.source_url + idx">
                 
                      <Song :item="hit" mode="search"  :class="isHitSelected(activeItem, hit) ? 'border-primary-500 bg-primary-500/10' : 'border-neutral-600 hover:border-neutral-500'"
                      @click="selectHit(activeItem, hit)" />
                  </li>
                </ul>
                <p v-else class="text-xs text-muted">No results</p>
              </div>
            </div>
          </UScrollArea>
        </template>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { fetchJson } from "../../composables/useApi";
import { useNotifications } from "../../composables/useNotifications";

const route = useRoute();
const router = useRouter();
const { notifyError } = useNotifications();

const playlistId = computed(() => route.params.id);
const items = ref([]);
const searchDone = ref(false);
const progress = ref({});
const loadError = ref("");
const activeItemId = ref(null);
const runningSearch = ref(false);

const providerOrder = ["youtube", "soundcloud", "mixcloud"];

const activeItem = computed(() => items.value.find((i) => i.id === activeItemId.value) || null);

const progressLabel = computed(() => {
  if (runningSearch.value && !searchDone.value) {
    const p = progress.value || {};
    const prov = p.provider ? providerLabel(p.provider) : "";
    const total = p.tracks_total;
    const done = p.tracks_completed;
    const countLabel =
      typeof total === "number" && total > 0 && typeof done === "number"
        ? ` (${done}/${total})`
        : "";
    if (prov) {
      const ti = p.track_index != null ? p.track_index + 1 : "";
      return `Searching ${prov}…${ti ? ` (track ${ti})` : ""}${countLabel}`;
    }
    if (p.parallel_providers) {
      return `Searching providers in parallel…${countLabel}`;
    }
    return `Searching…${countLabel}`;
  }
  if (searchDone.value) return "Search complete";
  return "";
});

function providerLabel(id) {
  if (!id) return "";
  return id.charAt(0).toUpperCase() + id.slice(1);
}

function statusLabel(s) {
  if (s === "matched") return "Matched";
  if (s === "no_match") return "No match";
  if (s === "searching") return "Searching…";
  return s || "";
}

function statusBadgeColor(s) {
  if (s === "matched") return "success";
  if (s === "no_match") return "error";
  if (s === "searching") return "warning";
  return "neutral";
}

function isHitSelected(item, hit) {
  const sel = item?.selected;
  if (!sel || !hit?.source_url) return false;
  return sel.source_url === hit.source_url && (sel.provider || "") === (hit.provider || "");
}

function applySnapshot(out) {
  if (!out || typeof out !== "object") return;
  if (Array.isArray(out.items)) items.value = out.items;
  searchDone.value = !!out.search_done;
  progress.value = out.progress || {};
  if (!activeItemId.value && items.value.length) {
    activeItemId.value = items.value[0].id;
  }
}

async function runSearchLoop() {
  const id = playlistId.value;
  if (!id) return;
  runningSearch.value = true;
  try {
    let done = false;
    while (!done) {
      const out = await fetchJson(`/api/spotify/import/${id}/advance`, { method: "POST" });
      applySnapshot(out);
      done = !!out.search_done;
    }
  } catch (error) {
    notifyError("Search failed", error);
    loadError.value = error instanceof Error ? error.message : "Search failed";
  } finally {
    runningSearch.value = false;
  }
}

async function selectHit(item, hit) {
  const id = playlistId.value;
  if (!id || !item?.id || !hit?.source_url) return;
  try {
    const out = await fetchJson(`/api/spotify/import/${id}/entries/${item.id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        source_url: hit.source_url,
        normalized_url: hit.normalized_url || hit.source_url,
        provider: hit.provider ?? null,
        provider_item_id: hit.provider_item_id ?? null,
        title: hit.title ?? null,
        channel: hit.channel ?? null,
        duration_seconds: hit.duration_seconds ?? null,
        thumbnail_url: hit.thumbnail_url ?? null,
      }),
    });
    applySnapshot(out);
  } catch (error) {
    notifyError("Could not save selection", error);
  }
}

function goToPlaylist() {
  if (playlistId.value) router.push(`/playlist/${playlistId.value}`);
}

watch(
  () => route.params.id,
  async () => {
    loadError.value = "";
    await loadPage();
  },
);

async function loadPage() {
  const id = playlistId.value;
  if (!id) {
    loadError.value = "Missing playlist id";
    return;
  }
  const storageKey = `airwave-spotify-import-seen:${id}`;
  try {
    if (sessionStorage.getItem(storageKey)) {
      await fetchJson(`/api/spotify/import/${id}/restart-search`, { method: "POST" });
    }
    sessionStorage.setItem(storageKey, "1");

    const initial = await fetchJson(`/api/spotify/import/${id}/state`);
    applySnapshot(initial);
    if (!initial.search_done) {
      await runSearchLoop();
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : "Failed to load import";
    notifyError("Spotify import", error);
  }
}

onMounted(() => {
  loadPage();
});
</script>
