import { computed, ref, watch } from "vue";

const SIDEBAR_VIEW_STORAGE_KEY = "mytube:settings:sidebar-view";
const SIDEBAR_TAB_STORAGE_KEY = "mytube:settings:sidebar-tab";

export const SIDEBAR_QUEUE_VIEW = "queue";
export const SIDEBAR_SONOS_VIEW = "sonos";
export const QUEUE_TAB = "queue";
export const HISTORY_TAB = "history";

export const queueSidebarTabs = [
  { label: "Queue", icon: "i-lucide-list-music", slot: "queue", value: QUEUE_TAB },
  { label: "History", icon: "i-lucide-history", slot: "history", value: HISTORY_TAB },
];

const sidebarView = ref(SIDEBAR_QUEUE_VIEW);
const activeQueueTab = ref(QUEUE_TAB);
const searchText = ref("");
const activePlaylistId = ref(null);

let initialized = false;

function readStoredSetting(key) {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStoredSetting(key, value) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Ignore storage write failures and keep in-memory state.
  }
}

function applyStoredSidebarSettings() {
  const storedView = readStoredSetting(SIDEBAR_VIEW_STORAGE_KEY);
  const storedTab = readStoredSetting(SIDEBAR_TAB_STORAGE_KEY);
  if (storedView === SIDEBAR_QUEUE_VIEW || storedView === SIDEBAR_SONOS_VIEW) {
    sidebarView.value = storedView;
  }
  if (storedTab === QUEUE_TAB || storedTab === HISTORY_TAB) {
    activeQueueTab.value = storedTab;
  }
}

function firstQueryValue(value) {
  if (Array.isArray(value)) return value[0] || "";
  return typeof value === "string" ? value : "";
}

function onSearchTextChange(value) {
  searchText.value = value;
}

async function onYoutubeSearch(router, route, query) {
  const trimmed = query.trim();
  if (!trimmed) {
    if (route.path === "/search") {
      await router.push({ path: "/search" });
    }
    return;
  }
  await router.push({ path: "/search", query: { q: trimmed } });
}

async function selectPlaylist(router, playlistId) {
  activePlaylistId.value = playlistId;
  try {
    await router.push({ path: `/playlist/${playlistId}` });
  } catch {
    // Ignore navigation errors for repeated clicks on the same route.
  }
}

function initializeUiState(route) {
  if (initialized) return;
  initialized = true;

  applyStoredSidebarSettings();

  watch(sidebarView, (value) => {
    writeStoredSetting(SIDEBAR_VIEW_STORAGE_KEY, value);
  });

  watch(activeQueueTab, (value) => {
    writeStoredSetting(SIDEBAR_TAB_STORAGE_KEY, value);
  });

  watch(
    () => [route.path, route.query.q],
    ([path, query]) => {
      if (path !== "/search") return;
      searchText.value = firstQueryValue(query);
    },
    { immediate: true },
  );

  watch(
    () => [route.path, route.params.id],
    ([path, playlistId]) => {
      if (!path.startsWith("/playlist/")) {
        activePlaylistId.value = null;
        return;
      }
      activePlaylistId.value = Array.isArray(playlistId) ? playlistId[0] || null : playlistId || null;
    },
    { immediate: true },
  );
}

export function useUiState() {
  return {
    sidebarView,
    activeQueueTab,
    searchText,
    activePlaylistId,
    queueSidebarTabs,
    initializeUiState,
    onSearchTextChange,
    onYoutubeSearch,
    selectPlaylist,
  };
}

export function useQueueHistoryFilters(queue, history) {
  const filteredQueue = computed(() => {
    if (!searchText.value.trim()) return queue.value;
    const needle = searchText.value.toLowerCase();
    return queue.value.filter((item) => {
      const haystack = `${item.title || ""} ${item.source_url || ""} ${item.channel || ""}`.toLowerCase();
      return haystack.includes(needle);
    });
  });

  const filteredHistory = computed(() => {
    if (!searchText.value.trim()) return history.value;
    const needle = searchText.value.toLowerCase();
    return history.value.filter((item) => {
      const haystack = `${item.title || ""} ${item.source_url || ""} ${item.status || ""}`.toLowerCase();
      return haystack.includes(needle);
    });
  });

  return { filteredQueue, filteredHistory };
}

