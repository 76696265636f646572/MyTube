<template>
  <UApp :toaster="{ position: 'bottom-right' }">
    <div class="h-dvh overflow-hidden bg-neutral-950 p-3 text-neutral-100 flex flex-col gap-3">
      <TopBar
        :search-text="searchText"
        @add-url="onAddUrl"
        @play-url="onPlayUrl"
        @search="onYoutubeSearch"
        @search-text-change="onSearchTextChange"
      />

      <div class="min-h-0 flex-1 grid gap-3 xl:grid-cols-[260px_minmax(0,1fr)_340px]">
        <SidebarPlaylists
          class="h-full"
          :playlists="filteredPlaylists"
          :active-playlist-id="activePlaylistId"
          @create-playlist="onCreatePlaylist"
          @select-playlist="onSelectPlaylist"
          @queue-playlist="onQueuePlaylist"
        />

        <main class="min-h-0 h-full">
          <RouterView v-slot="{ Component }">
            <component :is="Component" :on-add-url="onAddUrl" :on-play-url="onPlayUrl" />
          </RouterView>
        </main>

        <aside class="min-h-0 h-full flex flex-col gap-3">
          <template v-if="sidebarView === SIDEBAR_QUEUE_VIEW">
            <UTabs
              v-model="activeQueueTab"
              :items="queueSidebarTabs"
              class="w-full min-h-0 h-full"
              :ui="{ content: 'h-full min-h-0' }"
              :unmount-on-hide="false"
            >
              <template #queue>
                <QueuePanel
                  class="h-full"
                  :queue="filteredQueue"
                  :active-playlist-id="activePlaylistId"
                  @remove="onRemoveQueueItem"
                  @reorder="onReorderQueueItem"
                  @save-to-playlist="onSaveQueueToPlaylist"
                />
              </template>

              <template #history>
                <HistoryPanel class="h-full" :history="filteredHistory" @clear="onClearHistory" />
              </template>
            </UTabs>
          </template>

          <SonosPanel
            v-else
            class="h-full"
            :speakers="speakers"
            @refresh="onRefreshSonosManual"
            @play="playOnSpeaker"
            @group="groupSpeaker"
            @ungroup="ungroupSpeaker"
            @set-volume="setSpeakerVolume"
          />
        </aside>
      </div>

      <PlayerBar
        :state="playbackState"
        :sidebar-view="sidebarView"
        :sidebar-queue-view="SIDEBAR_QUEUE_VIEW"
        :sidebar-sonos-view="SIDEBAR_SONOS_VIEW"
        @set-sidebar-view="sidebarView = $event"
        @skip="skipCurrent"
      />
    </div>
  </UApp>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import HistoryPanel from "./components/HistoryPanel.vue";
import PlayerBar from "./components/PlayerBar.vue";
import QueuePanel from "./components/QueuePanel.vue";
import SidebarPlaylists from "./components/SidebarPlaylists.vue";
import SonosPanel from "./components/SonosPanel.vue";
import TopBar from "./components/TopBar.vue";
import { onEventBus } from "./composables/eventBus";
import { fetchJson } from "./composables/useApi";

const queue = ref([]);
const history = ref([]);
const playlists = ref([]);
const speakers = ref([]);
const playbackState = ref({
  mode: "idle",
  now_playing_title: null,
  now_playing_channel: null,
  now_playing_thumbnail_url: null,
  duration_seconds: null,
  elapsed_seconds: null,
  progress_percent: null,
  stream_url: null,
});
const searchText = ref("");
const activePlaylistId = ref(null);
const SIDEBAR_VIEW_STORAGE_KEY = "mytube:settings:sidebar-view";
const SIDEBAR_TAB_STORAGE_KEY = "mytube:settings:sidebar-tab";
const SIDEBAR_QUEUE_VIEW = "queue";
const SIDEBAR_SONOS_VIEW = "sonos";
const QUEUE_TAB = "queue";
const HISTORY_TAB = "history";
const sidebarView = ref(SIDEBAR_QUEUE_VIEW);
const activeQueueTab = ref(QUEUE_TAB);
const queueSidebarTabs = [
  { label: "Queue", icon: "i-lucide-list-music", slot: "queue", value: QUEUE_TAB },
  { label: "History", icon: "i-lucide-history", slot: "history", value: HISTORY_TAB },
];
const toast = useToast();
const router = useRouter();
const route = useRoute();

let playbackTickTimer = null;
let unsubscribeWsSnapshot = null;

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

const filteredPlaylists = computed(() => {
  if (!searchText.value.trim()) return playlists.value;
  const needle = searchText.value.toLowerCase();
  return playlists.value.filter((item) => {
    const haystack = `${item.title || ""} ${item.channel || ""} ${item.kind || ""}`.toLowerCase();
    return haystack.includes(needle);
  });
});

async function refreshCore() {
  const [queueData, historyData, stateData, playlistsData] = await Promise.all([
    fetchJson("/queue"),
    fetchJson("/history"),
    fetchJson("/state"),
    fetchJson("/playlists"),
  ]);
  queue.value = queueData;
  history.value = historyData;
  playbackState.value = stateData;
  playlists.value = playlistsData;
}

async function refreshSonos() {
  speakers.value = await fetchJson("/sonos/speakers");
}

function errorMessage(error) {
  const fallback = error instanceof Error ? error.message : String(error || "Request failed");
  try {
    const parsed = JSON.parse(fallback);
    if (Array.isArray(parsed?.detail) && parsed.detail.length) {
      return parsed.detail[0]?.msg || fallback;
    }
    if (typeof parsed?.detail === "string") {
      return parsed.detail;
    }
  } catch {
    // Keep the original message when the payload is not JSON.
  }
  return fallback.length > 180 ? `${fallback.slice(0, 177)}...` : fallback;
}

function notifySuccess(title, description) {
  toast.add({
    title,
    description,
    color: "success",
    icon: "i-lucide-check",
    type: "foreground",
  });
}

function notifyError(title, error) {
  toast.add({
    title,
    description: errorMessage(error),
    color: "error",
    icon: "i-lucide-triangle-alert",
    type: "foreground",
  });
}

async function onAddUrl(url) {
  try {
    await fetchJson("/queue/add", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url }),
    });
    notifySuccess("Added to queue", "URL added successfully.");
  } catch (error) {
    notifyError("Could not add URL", error);
  }
}

async function onPlayUrl(url) {
  try {
    await fetchJson("/queue/play-now", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url }),
    });
    notifySuccess("Playing now", "URL queued and playback started.");
  } catch (error) {
    notifyError("Could not play URL", error);
  }
}

async function onYoutubeSearch(query) {
  const trimmed = query.trim();
  if (!trimmed) {
    if (route.path === "/search") {
      await router.push({ path: "/search" });
    }
    return;
  }
  await router.push({ path: "/search", query: { q: trimmed } });
}

function onSearchTextChange(value) {
  searchText.value = value;
}

function firstQueryValue(value) {
  if (Array.isArray(value)) return value[0] || "";
  return typeof value === "string" ? value : "";
}

async function onRemoveQueueItem(itemId) {
  try {
    await fetchJson(`/queue/${itemId}`, { method: "DELETE" });
    notifySuccess("Removed from queue", "Queue item deleted.");
  } catch (error) {
    notifyError("Could not remove queue item", error);
  }
}

async function onReorderQueueItem({ itemId, newPosition }) {
  try {
    await fetchJson(`/queue/${itemId}/reorder`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ new_position: newPosition }),
    });
  } catch (error) {
    notifyError("Could not reorder queue", error);
  }
}

async function onCreatePlaylist(title) {
  try {
    const created = await fetchJson("/playlists/custom", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title }),
    });
    activePlaylistId.value = created.id;
    notifySuccess("Playlist created", title);
  } catch (error) {
    notifyError("Could not create playlist", error);
  }
}

function onSelectPlaylist(playlistId) {
  activePlaylistId.value = playlistId;
}

async function onQueuePlaylist(playlistId) {
  try {
    await fetchJson(`/playlists/${playlistId}/queue`, { method: "POST" });
    notifySuccess("Playlist queued", "Items added to queue.");
  } catch (error) {
    notifyError("Could not queue playlist", error);
  }
}

async function onSaveQueueToPlaylist(item) {
  if (!activePlaylistId.value) {
    notifyError("Select a playlist first", "Choose a playlist before saving queue items.");
    return;
  }
  try {
    await fetchJson(`/playlists/${activePlaylistId.value}/entries`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url: item.source_url }),
    });
    notifySuccess("Saved to playlist", "Queue item saved.");
  } catch (error) {
    notifyError("Could not save to playlist", error);
  }
}

async function onClearHistory() {
  try {
    await fetchJson("/history", { method: "DELETE" });
    notifySuccess("History cleared", "Playback history removed.");
  } catch (error) {
    notifyError("Could not clear history", error);
  }
}

async function skipCurrent() {
  try {
    await fetchJson("/queue/skip", { method: "POST" });
    notifySuccess("Skipped", "Moved to the next item.");
  } catch (error) {
    notifyError("Could not skip", error);
  }
}

async function onRefreshSonosManual() {
  try {
    await refreshSonos();
    notifySuccess("Sonos refreshed", "Speaker list updated.");
  } catch (error) {
    notifyError("Could not refresh Sonos", error);
  }
}

async function playOnSpeaker(ip) {
  try {
    await fetchJson("/sonos/play", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ speaker_ip: ip }),
    });
    notifySuccess("Playback started", `Streaming to ${ip}.`);
  } catch (error) {
    notifyError("Could not start Sonos playback", error);
  }
}

async function groupSpeaker({ coordinatorIp, memberIp }) {
  try {
    await fetchJson("/sonos/group", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ coordinator_ip: coordinatorIp, member_ip: memberIp }),
    });
    await refreshSonos();
    notifySuccess("Speaker grouped", `${memberIp} joined ${coordinatorIp}.`);
  } catch (error) {
    notifyError("Could not group speaker", error);
  }
}

async function ungroupSpeaker(ip) {
  try {
    await fetchJson("/sonos/ungroup", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ speaker_ip: ip }),
    });
    await refreshSonos();
    notifySuccess("Speaker ungrouped", `${ip} left the group.`);
  } catch (error) {
    notifyError("Could not ungroup speaker", error);
  }
}

async function setSpeakerVolume({ ip, volume }) {
  try {
    await fetchJson("/sonos/volume", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ speaker_ip: ip, volume }),
    });
  } catch (error) {
    notifyError("Could not set volume", error);
  }
}

function applySnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return;
  if (Array.isArray(snapshot.queue)) queue.value = snapshot.queue;
  if (Array.isArray(snapshot.history)) history.value = snapshot.history;
  if (Array.isArray(snapshot.playlists)) playlists.value = snapshot.playlists;
  if (snapshot.state && typeof snapshot.state === "object") playbackState.value = snapshot.state;
}

function startPlaybackTicker() {
  if (playbackTickTimer) clearInterval(playbackTickTimer);
  playbackTickTimer = setInterval(() => {
    const state = playbackState.value;
    if (!state || state.mode !== "playing" || state.started_at == null) return;
    const startedAt = Number(state.started_at);
    if (!Number.isFinite(startedAt)) return;
    const elapsed = Math.max(0, Date.now() / 1000 - startedAt);
    const duration = Number(state.duration_seconds);
    const progress =
      Number.isFinite(duration) && duration > 0 ? Math.min(100, (elapsed / duration) * 100) : null;
    playbackState.value = {
      ...state,
      elapsed_seconds: elapsed,
      progress_percent: progress,
    };
  }, 1000);
}

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

onMounted(async () => {
  applyStoredSidebarSettings();
  await Promise.all([refreshCore(), refreshSonos()]);
  startPlaybackTicker();
  unsubscribeWsSnapshot = onEventBus("ws:snapshot", (payload) => {
    applySnapshot(payload);
  });
});

onUnmounted(() => {
  if (playbackTickTimer) clearInterval(playbackTickTimer);
  if (unsubscribeWsSnapshot) unsubscribeWsSnapshot();
});
</script>
