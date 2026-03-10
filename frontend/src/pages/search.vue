<template>
  <section class="min-h-0 h-full rounded-xl border border-neutral-700 p-6 overflow-auto surface-panel">
    <h2 class="text-2xl font-bold">Search</h2>
    <p class="mt-1 text-sm text-muted">
      <template v-if="query">
        Showing results for "{{ query }}"
      </template>
      <template v-else>
        Enter a search in the top bar and press Enter.
      </template>
    </p>

    <div v-if="loading" class="mt-4 text-sm text-muted">Searching...</div>
    <div v-else-if="errorMessage" class="mt-4 text-sm text-red-300">{{ errorMessage }}</div>
    <div v-else-if="query && !filteredResults.length" class="mt-4 text-sm text-muted">No results found.</div>

    <div v-if="warnings.length" class="mt-4 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
      Some sources had issues: {{ warningText }}
    </div>

    <div v-if="query && !loading && enabledSites.length" class="mt-4 flex flex-wrap gap-2">
      <button
        v-for="site in filterTabs"
        :key="site.value"
        type="button"
        class="rounded-md border px-3 py-1 text-xs"
        :class="activeSiteFilter === site.value ? 'border-primary-500 text-primary-300' : 'border-neutral-700 text-muted'"
        @click="activeSiteFilter = site.value"
      >
        {{ site.label }}
      </button>
    </div>

    <ul v-if="filteredResults.length" class="mt-4 space-y-2">
      <li v-for="item in filteredResults" :key="item.id || item.source_url">
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
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

import Song from "../components/Song.vue";
import { fetchJson } from "../composables/useApi";
import { useLibraryState } from "../composables/useLibraryState";
import { useSearchSites } from "../composables/useSearchSites";

const { playlists } = useLibraryState();

const route = useRoute();
const query = ref("");
const results = ref([]);
const loading = ref(false);
const errorMessage = ref("");
const warnings = ref([]);
const activeSiteFilter = ref("All");
const {
  enabledSites,
  initializeSearchSites,
  enabledSitesParam,
} = useSearchSites();

let requestId = 0;

function normalizeQuery(value) {
  if (Array.isArray(value)) return (value[0] || "").trim();
  return typeof value === "string" ? value.trim() : "";
}
const filterTabs = computed(() => {
  const siteCounts = {};
  for (const item of results.value) {
    const s = normalizedSourceSite(item);
    if (s) siteCounts[s] = (siteCounts[s] || 0) + 1;
  }
  const list = [
    { label: `All (${results.value.length})`, value: "All" },
  ];
  for (const site of enabledSites.value) {
    list.push({
      label: `${formatSiteLabel(site)} (${siteCounts[site] ?? 0})`,
      value: site,
    });
  }
  return list;
});

const filteredResults = computed(() => {
  if (activeSiteFilter.value === "All") return results.value;
  return results.value.filter((item) => normalizedSourceSite(item) === activeSiteFilter.value);
});

function normalizedSourceSite(item) {
  return String(item?.source_site ?? "").toLowerCase();
}

function formatSiteLabel(site) {
  const normalized = String(site || "").trim().toLowerCase();
  const map = {
    youtube: "YouTube",
    soundcloud: "SoundCloud",
    vimeo: "Vimeo",
  };
  return map[normalized] || (normalized ? `${normalized.charAt(0).toUpperCase()}${normalized.slice(1)}` : "Source");
}

const warningText = computed(() =>
  warnings.value
    .map((warning) => {
      if (!warning || typeof warning !== "object") return "";
      const siteLabel = formatSiteLabel(warning.site);
      if (warning.reason === "timeout") return `${siteLabel} timed out`;
      if (warning.message) return `${siteLabel}: ${warning.message}`;
      return `${siteLabel} failed`;
    })
    .filter(Boolean)
    .join(", ")
);

async function searchAllSites(rawQuery) {
  const normalized = normalizeQuery(rawQuery);
  query.value = normalized;

  if (!normalized) {
    results.value = [];
    warnings.value = [];
    errorMessage.value = "";
    loading.value = false;
    return;
  }

  const activeRequestId = ++requestId;
  loading.value = true;
  errorMessage.value = "";

  try {
    const sites = enabledSitesParam();
    const payload = await fetchJson("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        q: normalized,
        limit: 50,
        sites,
      }),
    });
    if (activeRequestId !== requestId) return;
    
    results.value = Array.isArray(payload?.results) ? payload.results : [];
    warnings.value = Array.isArray(payload?.warnings) ? payload.warnings : [];
    activeSiteFilter.value = "All";
  } catch (error) {
    if (activeRequestId !== requestId) return;
    results.value = [];
    warnings.value = [];
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
    searchAllSites(value);
  },
);

watch(
  () => enabledSites.value.join(","),
  () => {
    if (query.value) {
      searchAllSites(query.value);
    }
  },
);

onMounted(async () => {
  await initializeSearchSites();
  const q = normalizeQuery(route.query.q);
  if (q) {
    searchAllSites(route.query.q);
  }
});
</script>
