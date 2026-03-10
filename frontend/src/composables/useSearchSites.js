import { ref } from "vue";

import { fetchJson } from "./useApi";

const STORAGE_KEY = "mytube:settings:searchSites";

const SEARCH_SITES_FALLBACK = [
  "youtube", "vimeo", "dailymotion", "bilibili", "peertube", "soundcloud",
  "bandcamp", "audiomack", "mixcloud", "hearthis", "boomplay", "anghami",
  "jamendo", "archive", "fma", "housemixes", "tracklists1001", "nts",
  "applepodcasts", "tunein", "podbean", "spreaker", "tiktok", "twitch", "facebook",
];

const availableSites = ref([...SEARCH_SITES_FALLBACK]);
const defaultEnabledSites = ref([]);
const enabledSites = ref([]);
const loadingSites = ref(false);

let initialized = false;

function readStoredSites() {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((site) => typeof site === "string") : null;
  } catch {
    return null;
  }
}

function persistEnabledSites() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(enabledSites.value));
  } catch {
    // Ignore storage failures and keep in-memory preference.
  }
}

function clampEnabledSites(candidates) {
  const allowed = new Set(availableSites.value);
  const deduped = [];
  for (const site of candidates) {
    if (!allowed.has(site) || deduped.includes(site)) continue;
    deduped.push(site);
  }
  return deduped.length ? deduped : [...defaultEnabledSites.value];
}

async function loadSearchSitesConfig() {
  loadingSites.value = true;
  try {
    const payload = await fetchJson("/api/search/sites");
    if (Array.isArray(payload?.sites) && payload.sites.length > 0) {
      availableSites.value = payload.sites;
    }
    if (Array.isArray(payload?.default_enabled_sites)) {
      defaultEnabledSites.value = payload.default_enabled_sites;
    }
  } catch {
    // Keep frontend defaults if endpoint is unavailable.
  } finally {
    loadingSites.value = false;
  }

  const stored = readStoredSites();
  enabledSites.value = clampEnabledSites(stored || defaultEnabledSites.value);
  persistEnabledSites();
}

export async function initializeSearchSites() {
  if (initialized) return;
  initialized = true;
  await loadSearchSitesConfig();
}

export function useSearchSites() {
  function setSiteEnabled(site, enabled) {
    const next = new Set(enabledSites.value);
    if (enabled) next.add(site);
    else next.delete(site);
    enabledSites.value = clampEnabledSites(Array.from(next));
    persistEnabledSites();
  }

  function enabledSitesParam() {
    return enabledSites.value.join(",");
  }

  
  return {
    availableSites,
    defaultEnabledSites,
    enabledSites,
    loadingSites,
    initializeSearchSites,
    setSiteEnabled,
    enabledSitesParam,
  };
}

