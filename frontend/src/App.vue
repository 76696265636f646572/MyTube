<template>
  <UApp :toaster="{ position: 'bottom-right' }">
    <div class="min-h-screen bg-neutral-950 pb-24 text-neutral-100 p-3 flex flex-col gap-3 sm:pb-20">
      <TopBar
        :search-text="searchText"
        :search-results="searchResults"
        @add-url="onAddUrl"
        @play-url="onPlayUrl"
        @search="onYoutubeSearch"
        @search-text-change="onSearchTextChange"
      />

      <div class="grid gap-3 xl:grid-cols-[260px_minmax(0,1fr)_320px]">
        <SidebarPlaylists
          :playlists="filteredPlaylists"
          :active-playlist-id="activePlaylistId"
          @create-playlist="onCreatePlaylist"
          @select-playlist="onSelectPlaylist"
          @queue-playlist="onQueuePlaylist"
        />

        <main class="grid gap-3 min-h-0 xl:grid-rows-[minmax(280px,1fr)_minmax(220px,1fr)]">
          <QueuePanel
            :queue="filteredQueue"
            :active-playlist-id="activePlaylistId"
            @remove="onRemoveQueueItem"
            @reorder="onReorderQueueItem"
            @save-to-playlist="onSaveQueueToPlaylist"
          />
          <HistoryPanel :history="filteredHistory" @clear="onClearHistory" />
        </main>

        <SonosPanel
          :speakers="speakers"
          @refresh="onRefreshSonosManual"
          @play="playOnSpeaker"
          @group="groupSpeaker"
          @ungroup="ungroupSpeaker"
          @set-volume="setSpeakerVolume"
        />
      </div>

      <PlayerBar :state="playbackState" @skip="skipCurrent" />
    </div>
  </UApp>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";

import HistoryPanel from "./components/HistoryPanel.vue";
import PlayerBar from "./components/PlayerBar.vue";
import QueuePanel from "./components/QueuePanel.vue";
import SidebarPlaylists from "./components/SidebarPlaylists.vue";
import SonosPanel from "./components/SonosPanel.vue";
import TopBar from "./components/TopBar.vue";
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
const searchResults = ref([]);
const activePlaylistId = ref(null);
const toast = useToast();

let fastPollTimer = null;
let regularPollTimer = null;
let sonosPollTimer = null;

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
    await refreshCore();
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
    await refreshCore();
    notifySuccess("Playing now", "URL queued and playback started.");
  } catch (error) {
    notifyError("Could not play URL", error);
  }
}

async function onYoutubeSearch(query) {
  if (!query.trim()) {
    searchResults.value = [];
    return;
  }
  try {
    const payload = await fetchJson(`/search/youtube?q=${encodeURIComponent(query)}&limit=10`);
    searchResults.value = payload.results || [];
  } catch (error) {
    searchResults.value = [];
    notifyError("Search failed", error);
  }
}

function onSearchTextChange(value) {
  searchText.value = value;
}

async function onRemoveQueueItem(itemId) {
  try {
    await fetchJson(`/queue/${itemId}`, { method: "DELETE" });
    await refreshCore();
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
    await refreshCore();
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
    await refreshCore();
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
    await refreshCore();
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
    await refreshCore();
    notifySuccess("Saved to playlist", "Queue item saved.");
  } catch (error) {
    notifyError("Could not save to playlist", error);
  }
}

async function onClearHistory() {
  try {
    await fetchJson("/history", { method: "DELETE" });
    await refreshCore();
    notifySuccess("History cleared", "Playback history removed.");
  } catch (error) {
    notifyError("Could not clear history", error);
  }
}

async function skipCurrent() {
  try {
    await fetchJson("/queue/skip", { method: "POST" });
    await refreshCore();
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

onMounted(async () => {
  await Promise.all([refreshCore(), refreshSonos()]);
  fastPollTimer = setInterval(async () => {
    playbackState.value = await fetchJson("/state");
  }, 1000);
  regularPollTimer = setInterval(refreshCore, 4000);
  sonosPollTimer = setInterval(refreshSonos, 8000);
});

onUnmounted(() => {
  if (fastPollTimer) clearInterval(fastPollTimer);
  if (regularPollTimer) clearInterval(regularPollTimer);
  if (sonosPollTimer) clearInterval(sonosPollTimer);
});
</script>
