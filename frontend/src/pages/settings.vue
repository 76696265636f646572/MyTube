<template>
  <section class="min-h-0 h-full rounded-xl border border-neutral-700 p-6 surface-panel overflow-auto">
    <h2 class="text-2xl font-bold">Settings</h2>
    <p class="mt-1 text-sm text-muted">
      Theme and search-source preferences are saved in local storage.
    </p>

    <div class="mt-6 max-w-sm">
      <label for="theme-select" class="block text-sm font-medium">Theme</label>
      <select
        id="theme-select"
        :value="currentTheme"
        class="mt-2 h-10 w-full rounded-md border px-3 text-sm surface-input"
        @change="onThemeChange($event.target.value)"
      >
        <option value="dark">Dark</option>
        <option value="night">Night</option>
      </select>
    </div>

    <div class="mt-8 max-w-md">
      <h3 class="text-sm font-semibold uppercase tracking-wide text-muted">Search Sources</h3>
      <p class="mt-1 text-xs text-muted">Choose which sites are used for multi-site search.</p>
      <div v-if="loadingSites" class="mt-3 text-sm text-muted">Loading search sources...</div>
      <div v-else class="mt-3 space-y-2">
        <label
          v-for="site in availableSites"
          :key="site"
          class="flex items-center justify-between rounded-md border border-neutral-700 px-3 py-2"
        >
          <span class="text-sm">{{ siteLabel(site) }}</span>
          <input
            type="checkbox"
            :checked="enabledSites.includes(site)"
            @change="onToggleSite(site, $event.target.checked)"
          />
        </label>
      </div>
    </div>
  </section>
</template>

<script setup>
import { useTheme } from "../composables/useTheme";
import { onMounted } from "vue";
import { SOURCE_LABELS } from "../composables/collectionUrl";
import { useSearchSites } from "../composables/useSearchSites";

const { currentTheme, setTheme } = useTheme();
const { availableSites, enabledSites, loadingSites, initializeSearchSites, setSiteEnabled } = useSearchSites();

function siteLabel(site) {
  return SOURCE_LABELS[site] || (site ? `${site.charAt(0).toUpperCase()}${site.slice(1)}` : site);
}

function onThemeChange(value) {
  setTheme(value);
}

function onToggleSite(site, checked) {
  setSiteEnabled(site, checked);
}

onMounted(() => {
  initializeSearchSites();
});
</script>
